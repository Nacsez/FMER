#include "effects.hpp"
#include "finite_float.hpp"
#include "target_hot.hpp"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <limits>

namespace fmer {
namespace {
constexpr float pi = 3.14159265358979323846f;
constexpr float sample_rate = static_cast<float>(Effects::native_sample_rate);
// Original eight-line orthogonal FDN. Delay lengths are mutually dispersed;
// an orthonormal Hadamard matrix preserves energy before per-line losses.
constexpr unsigned tank_lengths[4][8] = {
    {839,997,1153,1307,1453,1613,1787,1999},
    {907,1069,1237,1429,1559,1699,1871,2039},
    {1117,1283,1423,1553,1669,1789,1907,2039},
    {613,809,1013,1217,1429,1627,1823,2017}};
constexpr unsigned diffuser_lengths[4] = {149,211,263,293};
// Explicit fixed-size bit copies avoid library calls under the audited target
// toolchain's -fno-builtin policy; no aliasing or union-punning assumptions.
FMER_SAMPLE_INLINE std::uint32_t float_bits(float value) noexcept {
    std::uint32_t bits;
#if defined(FMER_DEVICE)
    __builtin_memcpy(&bits, &value, sizeof(bits));
#else
    std::memcpy(&bits, &value, sizeof(bits));
#endif
    return bits;
}
FMER_SAMPLE_INLINE float bits_float(std::uint32_t bits) noexcept {
    float value;
#if defined(FMER_DEVICE)
    __builtin_memcpy(&value, &bits, sizeof(value));
#else
    std::memcpy(&value, &bits, sizeof(value));
#endif
    return value;
}
FMER_SAMPLE_INLINE float magnitude(float value) noexcept { return bits_float(float_bits(value)&0x7fffffffu); }
FMER_SAMPLE_INLINE float output_knee(float x) noexcept {
    const float a = magnitude(x);
    if (a <= .9f) return x;
    const float excess = a - .9f;
    const float limited=.9f + .1f * excess / (.1f + excess);
    return x<0 ? -limited : limited;
}

// Compact delay storage keeps the one-second range and internal headroom.
// Normal values use IEEE binary16 round-to-nearest-even. Subnormal writes
// truncate toward zero so feedback below the 2^-14 normal threshold cannot
// settle into a rounding limit cycle. This is deliberately not Q15 PCM:
// preceding reverb/phaser stages can exceed +/-1 before the final output clamp.
// Both host and device use these exact, bounded conversions; no half runtime
// library, allocation, data-dependent loop or native half-FPU is required.
static_assert(sizeof(float) == sizeof(std::uint32_t) &&
              std::numeric_limits<float>::is_iec559, "delay requires binary32 floats");
FMER_SAMPLE_INLINE std::uint16_t store_delay(float value) noexcept {
    const std::uint32_t bits=float_bits(value);
    const auto sign = static_cast<std::uint16_t>((bits >> 16) & 0x8000u);
    const unsigned exponent = (bits >> 23) & 0xffu;
    const std::uint32_t mantissa = bits & 0x7fffffu;
    if (exponent < 103) return sign;
    if (exponent < 113)
        return static_cast<std::uint16_t>(sign | ((mantissa | 0x800000u) >> (126 - exponent)));
    if (exponent > 142) return static_cast<std::uint16_t>(sign | 0x7bffu);
    const auto rounded = ((exponent - 112) << 10) +
        ((mantissa + 0xfffu + ((mantissa >> 13) & 1u)) >> 13);
    return static_cast<std::uint16_t>(sign | std::min(rounded, 0x7bffu));
}

FMER_SAMPLE_INLINE float delay_sample(std::uint16_t value) noexcept {
    const unsigned exponent = (value >> 10) & 0x1fu;
    const unsigned mantissa = value & 0x3ffu;
    if (!exponent) {
        const float magnitude = static_cast<float>(mantissa) * (1.0f / 16777216.0f);
        return (value & 0x8000u) ? -magnitude : magnitude;
    }
    const std::uint32_t bits = (static_cast<std::uint32_t>(value & 0x8000u) << 16) |
        ((exponent + 112) << 23) | (mantissa << 13);
    return bits_float(bits);
}

FMER_SAMPLE_INLINE float delay_sample(float value) noexcept { return value; }

#if defined(FMER_DEVICE)
// Target FPU is single precision. These bounded original approximations avoid
// per-sample transcendental calls; desktop reference processing is unchanged.
FMER_SAMPLE_INLINE float modulation_sine(float phase) noexcept {
    float quadrant = phase * 4.0f;
    const bool negative = quadrant >= 2.0f;
    if (negative) quadrant -= 2.0f;
    if (quadrant > 1.0f) quadrant = 2.0f - quadrant;
    const float x = quadrant * (pi * 0.5f), square = x * x;
    // Ninth-order Taylor on[0,pi/2], absolute error below0.000004.
    const float value = x * (1.0f + square * (-1.0f/6.0f + square *
        (1.0f/120.0f + square * (-1.0f/5040.0f + square/362880.0f))));
    return negative ? -value : value;
}
// Only the phaser's bounded +/-2.5-octave sweep uses this approximation.
// Reduce 2^x to an exact binary scale and exp(z). Float32 reduction has
// |x-octave| <= .500001 (including rounding at half-octave boundaries).
// Degree7 exp and degree11 tan have analytic truncation errors below 8e-9
// and 3e-10 respectively on this domain, before float32 rounding. The full
// coefficient is checked against the old exp2/tan path, including reduction
// boundaries; its absolute error is bounded by 2e-6 and |a| stays below .983.
// This avoids generic powf/tanf range reduction eight times per128-frame
// block. Phase accumulation and the existing32-sample interpolation remain.
FMER_SAMPLE_INLINE float phaser_coefficient_target(float exponent) noexcept {
    const int octave = static_cast<int>(exponent + 3.5f) - 3;
    const float z = (exponent - static_cast<float>(octave)) * .6931471805599453f;
    const float exponential = 1.f + z * (1.f + z * (.5f + z * (1.f/6.f +
        z * (1.f/24.f + z * (1.f/120.f + z * (1.f/720.f + z/5040.f))))));
    const float scale = bits_float(static_cast<std::uint32_t>(octave + 127) << 23);
    const float frequency = 700.f * (scale * exponential);
    const float x = pi * frequency / sample_rate, square = x * x;
    const float tangent = x + x * square * (1.f/3.f + square * (2.f/15.f +
        square * (17.f/315.f + square * (62.f/2835.f + square * (1382.f/155925.f)))));
    return (tangent - 1.f) / (tangent + 1.f);
}
FMER_SAMPLE_INLINE float soft_clip(float input) noexcept {
    if (input >= 3.0f) return 1.0f;
    if (input <= -3.0f) return -1.0f;
    const float square = input * input;
    return input * (27.0f + square) / (27.0f + 9.0f * square);
}
#else
FMER_SAMPLE_INLINE float modulation_sine(float phase) noexcept { return std::sin(2.0f * pi * phase); }
FMER_SAMPLE_INLINE float soft_clip(float input) noexcept { return std::tanh(input); }
#endif

bool in_range(float value, float lo, float hi) noexcept {
    return std::isfinite(value) && value >= lo && value <= hi;
}

FMER_SAMPLE_INLINE float quiet(float value) noexcept {
    // Avoid denormal state without changing the dry bypass signal.
    // IEEE magnitude ordering gives the same threshold including NaNs,
    // infinities and signed zero, with one integer comparison per state.
    return (float_bits(value)&0x7fffffffu) < float_bits(1.0e-20f) ? 0.0f : value;
}

template<typename Sample, std::size_t Size>
FMER_SAMPLE_INLINE float read_delay(const std::array<Sample, Size>& buffer, std::size_t write,
                 std::size_t filled, float distance) noexcept {
    float position = static_cast<float>(write) - distance;
    if (position < 0) position += static_cast<float>(Size);
    const auto first = static_cast<std::size_t>(position);
    const auto next = first + 1 == Size ? 0 : first + 1;
    const float fraction = position - static_cast<float>(first);
    const float a = first < filled ? delay_sample(buffer[first]) : 0.0f;
    const float b = next < filled ? delay_sample(buffer[next]) : 0.0f;
    return a + (b - a) * fraction;
}

template<typename Sample, std::size_t Size>
void peak_of(const std::array<Sample, Size>& values, float& peak, std::size_t valid = Size,
             std::size_t offset = 0) noexcept {
    for (std::size_t i = 0; i < valid; ++i)
        peak = std::max(peak, magnitude(delay_sample(values[offset + i])));
}

bool valid(const EffectParameters& p) noexcept {
    if (!in_range(p.drive, 0, 1) || !in_range(p.chorus, 0, 1) ||
        !in_range(p.delay, 0, 1) || !in_range(p.delay_ms, 20, 1000) ||
        !in_range(p.feedback, 0, 0.85f) || !in_range(p.reverb, 0, 1) ||
        !in_range(p.cutoff_hz, 20, 20000) || !in_range(p.phaser, 0, 1) ||
        !in_range(p.chorus_rate_hz, 0.1f, 1) || !in_range(p.chorus_depth, 0, 1) ||
        !in_range(p.phaser_rate_hz, 0.5f, 6) || !in_range(p.phaser_depth, 0, 1) ||
        !in_range(p.reverb_decay, 0, 1) || !in_range(p.resonance, 0, 1) ||
        static_cast<unsigned>(p.filter_mode)>2 || static_cast<unsigned>(p.reverb_model)>3 ||
        static_cast<unsigned>(p.delay_model)>1) return false;
    unsigned seen = 0;
    for (EffectKind kind : p.order) {
        const auto index = static_cast<unsigned>(kind);
        if (index >= 6 || (seen & (1u << index))) return false;
        seen |= 1u << index;
    }
    return seen == 63;
}
} // namespace

struct Effects::Impl {
    EffectParameters parameters{};
    EffectStats counters{};
    std::array<float,6> activity{};
    std::array<std::uint16_t, 44101> delay{};
    std::array<float, 2048> chorus{};
    std::array<std::array<float,2048>,8> tank{};
    std::array<std::array<float,293>,4> diffusers{};
    std::array<unsigned,4> diffuse_position{}, diffuse_filled{};
    std::array<float,8> damping{}, tank_gain{}, tank_phase{};
    std::array<unsigned,8> tank_distance{};
    std::array<float,8> tank_fraction{};
    unsigned tank_control_left{};
    unsigned tank_position{}, tank_filled{};
    std::array<float, 4> phaser_state{};
    std::size_t delay_position{}, chorus_position{};
    std::size_t delay_filled{}, chorus_filled{};
    std::array<EffectKind, 6> active_order{};
    std::size_t active_stages{};
    float chorus_phase{}, phaser_phase{}, filter_state{}, filter_state2{};
    float filter_g{6.7f}, filter_k{1.41421356f}, target_g{6.7f}, target_k{1.41421356f};
    float delay_frames{11025.0f}, delay_from{11025.0f}, delay_to{11025.0f};
    unsigned delay_crossfade{};
    float echo_tone{}, reverb_mix{}, delay_mix{}, feedback{}, damping_amount{.5f};
    bool started{}, coefficients_valid{};
    float drive_gain{1}, drive_denominator{1};
#if defined(FMER_DEVICE)
    float phaser_coefficient{}, phaser_delta{};
    unsigned phaser_control_left{};
#endif

    FMER_SAMPLE_INLINE void clear(EffectKind kind) noexcept {
        switch (kind) {
        case EffectKind::filter: filter_state = filter_state2 = 0; break;
        // Invalidate rings instead of clearing ~125KB from an audio callback.
        // Until a ring fills, positions below its fill count are the only
        // written samples. Every reset restarts its cursor at zero.
        case EffectKind::delay:
            delay_filled = delay_position = delay_crossfade = 0; echo_tone = 0;
            delay_from = delay_to = delay_frames; break;
        case EffectKind::chorus:
            chorus_filled = chorus_position = 0; chorus_phase = 0; break;
        case EffectKind::phaser:
            phaser_state.fill(0); phaser_phase = 0;
#if defined(FMER_DEVICE)
            phaser_control_left = 0;
#endif
            break;
        case EffectKind::reverb:
            tank_position = tank_filled = tank_control_left = 0; damping.fill(0);
            diffuse_position.fill(0); diffuse_filled.fill(0);
            for(unsigned i=0;i<8;++i) tank_phase[i]=static_cast<float>(i)*.123f;
            break;
        case EffectKind::drive: break;
        }
    }

    // The target's general stage dispatcher otherwise saves a large common
    // frame once per active stage per sample. Keep sample/stage ordering and
    // recovery unchanged while allowing the caller to share that setup.
#if defined(FMER_DEVICE)
#if defined(_MSC_VER)
    __forceinline
#else
    __attribute__((always_inline))
#endif
#endif
    float apply(EffectKind kind, float input) noexcept {
        const auto& p = parameters;
        switch (kind) {
        case EffectKind::filter: {
            // Trapezoidal SVF, after Simper/Cytomic. Smooth positive g/k rather
            // than unconstrained biquad coefficients. One bounded sample path.
            filter_g += .004f*(target_g-filter_g);
            filter_k += .004f*(target_k-filter_k);
            const float a1=1.f/(1.f+filter_g*(filter_g+filter_k));
            const float a2=filter_g*a1, a3=filter_g*a2;
            const float v3=input-filter_state2;
            const float band=a1*filter_state+a2*v3;
            const float low=filter_state2+a2*filter_state+a3*v3;
            filter_state=quiet(2.f*band-filter_state);
            filter_state2=quiet(2.f*low-filter_state2);
            if(p.filter_mode==FilterMode::high_pass) return input-filter_k*band-low;
            if(p.filter_mode==FilterMode::band_pass) return (.7f+.3f*filter_k)*band;
            return low;
        }
        case EffectKind::drive: {
            if (p.drive == 0) return input;
            const float driven = soft_clip(input * drive_gain) / drive_denominator;
            return input + p.drive * (driven - input);
        }
        case EffectKind::delay: {
            if (p.delay == 0) return input;
            if(!delay_crossfade && delay_frames!=delay_to) {
                delay_from=delay_to; delay_to=delay_frames; delay_crossfade=2048;
            }
            float echo=read_delay(delay,delay_position,delay_filled,delay_to);
            if(delay_crossfade) {
                const float old=read_delay(delay,delay_position,delay_filled,delay_from);
                echo=old+(echo-old)*(1.f-static_cast<float>(delay_crossfade)/2048.f);
                --delay_crossfade;
            }
            // Feedback never scales the input injection. Warm gently rolls off
            // repeats; both styles share the same one-second compact ring.
            echo_tone=quiet(echo_tone+.22f*(echo-echo_tone));
            if(p.delay_model==DelayModel::warm) echo=echo_tone;
            feedback+=.004f*(p.feedback-feedback);
            delay[delay_position]=store_delay(input+echo*feedback);
            if(delay_filled<delay.size()) ++delay_filled;
            if(++delay_position==delay.size()) delay_position=0;
            delay_mix+=.004f*(p.delay-delay_mix);
            return input+.68f*delay_mix*echo;
        }
        case EffectKind::chorus: {
            if (p.chorus == 0) return input;
            const float distance = sample_rate * (0.018f + 0.008f * p.chorus_depth *
                modulation_sine(chorus_phase));
            const float modulated = read_delay(chorus, chorus_position, chorus_filled, distance);
            chorus[chorus_position] = input;
            if (chorus_filled < chorus.size()) ++chorus_filled;
            if (++chorus_position == chorus.size()) chorus_position = 0;
            chorus_phase += p.chorus_rate_hz / sample_rate;
            if (chorus_phase >= 1) chorus_phase -= 1;
            return input + (.5f * p.chorus) * (modulated - input);
        }
        case EffectKind::phaser: {
            if (p.phaser == 0) return input;
            // Four first-order all-pass sections, with no regenerative feedback.
            const auto coefficient_at = [&p](float phase) {
                const float sweep = modulation_sine(phase);
#if defined(FMER_DEVICE)
                return phaser_coefficient_target(2.5f * p.phaser_depth * sweep);
#else
                const float frequency = 700 * std::exp2(2.5f * p.phaser_depth * sweep);
                const float tangent = std::tan(pi * frequency / sample_rate);
                return (tangent - 1) / (tangent + 1);
#endif
            };
#if defined(FMER_DEVICE)
            if (!phaser_control_left) {
                // Phase endpoints every32samples, interpolated between.
                // State survives chunk boundaries and resets with the effect.
                phaser_coefficient = coefficient_at(phaser_phase);
                float future = phaser_phase + 32.0f * p.phaser_rate_hz / sample_rate;
                if (future >= 1.0f) future -= 1.0f;
                phaser_delta = (coefficient_at(future) - phaser_coefficient) / 32.0f;
                phaser_control_left = 32;
            }
            const float coefficient = phaser_coefficient;
            phaser_coefficient += phaser_delta;
            --phaser_control_left;
#else
            const float coefficient = coefficient_at(phaser_phase);
#endif
            float wet = input;
            FMER_FIXED_UNROLL
            for (float& state : phaser_state) {
                const float output = coefficient * wet + state;
                state = quiet(wet - coefficient * output);
                wet = output;
            }
            phaser_phase += p.phaser_rate_hz / sample_rate;
            if (phaser_phase >= 1) phaser_phase -= 1;
            return input + (.5f * p.phaser) * (wet - input);
        }
        case EffectKind::reverb: {
            if (p.reverb == 0) return input;
            float injection=input;
            FMER_FIXED_UNROLL
            for(unsigned i=0;i<4;++i) {
                auto& pos=diffuse_position[i]; auto& filled=diffuse_filled[i];
                const float old=pos<filled?diffusers[i][pos]:0.f;
                const float diffused=old-.65f*injection;
                diffusers[i][pos]=quiet(injection+.65f*diffused);
                if(filled<diffuser_lengths[i]) ++filled;
                if(++pos==diffuser_lengths[i]) pos=0;
                injection=diffused;
            }
            float lines[8], mixed[8], wet=0;
            const auto model=static_cast<unsigned>(p.reverb_model);
            if(!tank_control_left) {
                // Slow (<.2Hz) micro-modulation moves <.002 samples per update.
                // Cache integer/fractional read coordinates every32samples;
                // avoid eight float/int conversions and LFO calculations per
                // sample. State persists across arbitrary callback boundaries.
                for(unsigned i=0;i<8;++i) {
                    const float triangle=1.f-4.f*magnitude(tank_phase[i]-.5f);
                    const float distance=static_cast<float>(tank_lengths[model][i])+triangle*(model==3?5.f:model?3.f:1.f);
                    tank_distance[i]=static_cast<unsigned>(distance);
                    tank_fraction[i]=distance-static_cast<float>(tank_distance[i]);
                    tank_phase[i]+=32.f*(.09f+.013f*i)/sample_rate;
                    if(tank_phase[i]>=1.f)tank_phase[i]-=1.f;
                }
                tank_control_left=32;
            }
            --tank_control_left;
            // These fixed-size lines keep their original accumulation order.
            // Constant indices avoid repeated address/loop work on pi32v2.
            FMER_FIXED_UNROLL
            for(unsigned i=0;i<8;++i) {
                const unsigned newer=(tank_position+2048-tank_distance[i])&2047u;
                const unsigned older=(newer+2047)&2047u;
                const float a=newer<tank_filled?tank[i][newer]:0.f;
                const float b=older<tank_filled?tank[i][older]:0.f;
                const float delayed=a+(b-a)*tank_fraction[i];
                damping[i]=quiet(damping[i]+damping_amount*(delayed-damping[i]));
                lines[i]=damping[i]; mixed[i]=lines[i];
                wet+=((i&1)?-1.f:1.f)*delayed*.3535533906f;
            }
            // Fast Walsh-Hadamard transform: 24 add/subtracts, no dense matrix.
            const auto butterfly=[&mixed](unsigned a,unsigned b) {
                const float x=mixed[a],y=mixed[b];mixed[a]=x+y;mixed[b]=x-y;
            };
            // Fixed indices expose the same operation order to the target
            // compiler without three nested per-sample index loops.
            butterfly(0,1);butterfly(2,3);butterfly(4,5);butterfly(6,7);
            butterfly(0,2);butterfly(1,3);butterfly(4,6);butterfly(5,7);
            butterfly(0,4);butterfly(1,5);butterfly(2,6);butterfly(3,7);
            FMER_FIXED_UNROLL
            for(unsigned i=0;i<8;++i)
                tank[i][tank_position]=quiet(injection*.3535533906f+
                    mixed[i]*.3535533906f*tank_gain[i]);
            if(tank_filled<2048) ++tank_filled;
            tank_position=(tank_position+1)&2047u;
            reverb_mix+=.004f*(p.reverb-reverb_mix);
            return input+.82f*reverb_mix*wet;
        }
        }
        return input;
    }
};

Effects::Effects() : impl_(std::make_unique<Impl>()) { init(); }
Effects::~Effects() = default;

bool Effects::init(std::uint32_t sample_rate_hz) noexcept {
    if (sample_rate_hz != native_sample_rate) {
        ++impl_->counters.rejected_parameters;
        return false;
    }
    reset();
    return true;
}

bool Effects::set_parameters(const EffectParameters& parameters) noexcept {
    if (!valid(parameters)) {
        ++impl_->counters.rejected_parameters;
        return false;
    }
    const auto& previous = impl_->parameters;
    // Disabling a stage discards its tail; re-enabling never resurrects old audio.
    if (parameters.cutoff_hz == 20000 && parameters.resonance == 0 && parameters.filter_mode == FilterMode::low_pass)
        impl_->clear(EffectKind::filter);
    if (parameters.delay == 0 && previous.delay != 0) impl_->clear(EffectKind::delay);
    if (parameters.chorus == 0 && previous.chorus != 0) impl_->clear(EffectKind::chorus);
    if (parameters.reverb == 0 && previous.reverb != 0) impl_->clear(EffectKind::reverb);
    if (parameters.phaser == 0 && previous.phaser != 0) impl_->clear(EffectKind::phaser);
    if(parameters.reverb_model!=previous.reverb_model) impl_->clear(EffectKind::reverb);
    if(parameters.filter_mode!=previous.filter_mode) impl_->clear(EffectKind::filter);
    // Reset invalidates audio history, not parameter-derived coefficients.
    // A native restore can reset and apply again before processing a sample;
    // do not repeat tan/eight pow calls merely because smoothing is unstarted.
    if(!impl_->coefficients_valid || parameters.cutoff_hz!=previous.cutoff_hz)
        impl_->target_g=std::tan(pi*parameters.cutoff_hz/sample_rate);
    const float q=.70710678f+13.29289322f*parameters.resonance*parameters.resonance;
    impl_->target_k=1.f/q;
    if (parameters.drive != previous.drive) {
        impl_->drive_gain = 1 + 15 * parameters.drive;
        impl_->drive_denominator = soft_clip(impl_->drive_gain);
    }
#if defined(FMER_DEVICE)
    if (parameters.phaser_rate_hz != previous.phaser_rate_hz || parameters.phaser_depth != previous.phaser_depth)
        impl_->phaser_control_left = 0;
#endif
    impl_->delay_frames = sample_rate * parameters.delay_ms / 1000;
    if(!impl_->coefficients_valid || parameters.reverb_decay!=previous.reverb_decay || parameters.reverb_model!=previous.reverb_model) {
        const float extension=parameters.reverb_model==ReverbModel::hall?1.2f:parameters.reverb_model==ReverbModel::cloud?1.5f:1.f;
        const float t60=.3f+7.7f*parameters.reverb_decay*parameters.reverb_decay*extension;
        for(unsigned i=0;i<8;++i) impl_->tank_gain[i]=std::pow(.001f,
            static_cast<float>(tank_lengths[static_cast<unsigned>(parameters.reverb_model)][i])/(sample_rate*t60));
    }
    impl_->parameters = parameters;
    impl_->coefficients_valid = true;
    impl_->damping_amount=parameters.reverb_model==ReverbModel::plate?.65f:parameters.reverb_model==ReverbModel::hall?.28f:parameters.reverb_model==ReverbModel::cloud?.2f:.4f;
    if(!impl_->started) {
        impl_->filter_g=impl_->target_g; impl_->filter_k=impl_->target_k;
        impl_->delay_to=impl_->delay_from=impl_->delay_frames;
        impl_->delay_mix=parameters.delay; impl_->reverb_mix=parameters.reverb;
        impl_->feedback=parameters.feedback;
    }
    impl_->active_stages = 0;
    const auto enabled = [&parameters](EffectKind kind) {
        switch (kind) {
        case EffectKind::filter: return parameters.cutoff_hz != 20000 || parameters.resonance != 0 || parameters.filter_mode != FilterMode::low_pass;
        case EffectKind::delay: return parameters.delay != 0;
        case EffectKind::chorus: return parameters.chorus != 0;
        case EffectKind::phaser: return parameters.phaser != 0;
        case EffectKind::reverb: return parameters.reverb != 0;
        case EffectKind::drive: return parameters.drive != 0;
        }
        return false;
    };
    for (auto stage : parameters.order)
        if (enabled(stage)) impl_->active_order[impl_->active_stages++] = stage;
    for(unsigned i=0;i<6;++i)if(!enabled(static_cast<EffectKind>(i)))impl_->activity[i]=0;
    return true;
}

EffectParameters Effects::parameters() const noexcept { return impl_->parameters; }

FMER_DSP_HOT void Effects::process(float* mono, std::size_t frames) noexcept {
    if (!mono && frames != 0) { ++impl_->counters.rejected_buffers; return; }
    if(frames) impl_->started=true;
    std::array<float,6> peaks{};
    for (std::size_t i = 0; i < frames; ++i) {
        float value = mono[i];
        bool clipped = false;
        if (!finite_float(value)) { value = 0; ++impl_->counters.sanitized_samples; }
        impl_->counters.peak_input = std::max(impl_->counters.peak_input, magnitude(value));
        if (value < -1 || value > 1) {
            value = std::clamp(value, -1.0f, 1.0f);
            clipped = true;
        }
        for (std::size_t stage = 0; stage < impl_->active_stages; ++stage) {
            const float dry=value;const auto kind=impl_->active_order[stage];
            value = impl_->apply(kind, value);
            if((i&7u)==0u && finite_float(value))
                peaks[static_cast<unsigned>(kind)]=std::max(peaks[static_cast<unsigned>(kind)],magnitude(value-dry));
        }
        if (!finite_float(value)) {
            // Defensive isolation; accepted finite input/settings cannot reach
            // this through the bounded feedback paths in the tested contract.
            value = 0; ++impl_->counters.sanitized_samples;
            for (const auto stage : impl_->parameters.order) impl_->clear(stage);
        }
        // Preserve exact bypass. Active sends/resonance can add headroom:
        // a bounded soft knee catches peaks, counted separately from bad input.
        if(impl_->active_stages && magnitude(value)>.9f) {
            ++impl_->counters.limited_samples; value=output_knee(value);
        }
        if (value < -1 || value > 1) {
            value = std::clamp(value, -1.0f, 1.0f);
            clipped = true;
        }
        if (clipped) ++impl_->counters.clipped_samples;
        if(magnitude(value)>output_ceiling) {
            ++impl_->counters.guarded_samples;
            value=std::clamp(value,-output_ceiling,output_ceiling);
        }
        mono[i] = value;
        impl_->counters.peak_output = std::max(impl_->counters.peak_output, magnitude(value));
    }
    impl_->counters.processed_frames += frames;
    const float decay=1.f/(1.f+static_cast<float>(frames)/6615.f);
    for(unsigned i=0;i<6;++i)impl_->activity[i]=std::max(peaks[i],impl_->activity[i]*decay);
}

void Effects::reset() noexcept {
    for (const auto stage : impl_->parameters.order) impl_->clear(stage);
    impl_->counters = {}; impl_->started=false;
    impl_->activity.fill(0);
    // Synchronize smoothed parameters without allocating or clearing arrays.
    const auto p=impl_->parameters; set_parameters(p);
}

EffectStats Effects::meters() const noexcept { return impl_->counters; }
const std::array<float,6>& Effects::activity() const noexcept { return impl_->activity; }

EffectStats Effects::stats() const noexcept {
    auto result = impl_->counters;
    const auto& p = impl_->parameters;
    if (p.cutoff_hz != 20000 || p.resonance || p.filter_mode!=FilterMode::low_pass)
        result.tail_peak = std::max(magnitude(impl_->filter_state),magnitude(impl_->filter_state2));
    if (p.delay != 0) peak_of(impl_->delay, result.tail_peak, impl_->delay_filled);
    if (p.chorus != 0) peak_of(impl_->chorus, result.tail_peak, impl_->chorus_filled);
    if (p.phaser != 0) peak_of(impl_->phaser_state, result.tail_peak);
    if (p.reverb != 0) {
        for(const auto& line:impl_->tank) peak_of(line,result.tail_peak,impl_->tank_filled);
        peak_of(impl_->damping,result.tail_peak);
        for(unsigned i=0;i<4;++i) peak_of(impl_->diffusers[i],result.tail_peak,impl_->diffuse_filled[i]);
    }
    return result;
}

std::size_t Effects::storage_bytes() noexcept { return sizeof(Impl); }

} // namespace fmer
