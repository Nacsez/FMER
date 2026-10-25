#include "synth.hpp"
#include "target_hot.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <new>
#if !defined(FMER_DEVICE)
#include <mutex>
#endif
#include "../third_party/msfa/src/synth.h"
#include "../third_party/msfa/src/controllers.h"
#include "../third_party/msfa/src/dx7note.h"
#include "../third_party/msfa/src/exp2.h"
#include "../third_party/msfa/src/freqlut.h"
#include "../third_party/msfa/src/lfo.h"
#include "../third_party/msfa/src/sin.h"
#undef N
#undef LG_N

namespace fmer {
namespace {
constexpr double pi = 3.14159265358979323846;
constexpr std::uint8_t no_part = 255;
constexpr float semitone_q24 = 16777216.0f / 12.0f;
bool valid_va(const VaParameters& p) noexcept {
    const auto range = [](float v, float lo, float hi) { return std::isfinite(v) && v >= lo && v <= hi; };
    return static_cast<unsigned>(p.waveform) <= 4 && range(p.cutoff_hz,20,18000) &&
        range(p.resonance,0,.95f) && range(p.attack_ms,0,10000) &&
        range(p.decay_ms,0,10000) && range(p.sustain,0,1) && range(p.release_ms,0,10000) &&
        range(p.lfo_rate_hz,.1f,10) && range(p.lfo_depth_cents,0,100);
}
bool valid_glide(const GlideParameters& p) noexcept {
    return static_cast<unsigned>(p.mode) <= 2 && static_cast<unsigned>(p.contour) <= 2 &&
        std::isfinite(p.time_ms) && p.time_ms >= 0 && p.time_ms <= 5000;
}
bool same_va(const VaParameters& a, const VaParameters& b) noexcept {
    return a.waveform==b.waveform && a.cutoff_hz==b.cutoff_hz && a.resonance==b.resonance &&
        a.attack_ms==b.attack_ms && a.decay_ms==b.decay_ms && a.sustain==b.sustain &&
        a.release_ms==b.release_ms && a.lfo_rate_hz==b.lfo_rate_hz && a.lfo_depth_cents==b.lfo_depth_cents;
}
#if defined(FMER_DEVICE)
// pi32v2 has single-precision FPU instructions but software double arithmetic.
// Retain the desktop preview's double phase; target pitch accuracy is tested
// separately and does not imply identical target/host floating-point samples.
using VaPhase = float;
#else
using VaPhase = double;
#endif

float poly_blep(VaPhase phase, VaPhase increment) noexcept {
    if (phase < increment) {
        const float x = static_cast<float>(phase / increment);
        return x + x - x * x - 1.0f;
    }
    if (phase > VaPhase(1) - increment) {
        const float x = static_cast<float>((phase - VaPhase(1)) / increment);
        return x * x + x + x + 1.0f;
    }
    return 0.0f;
}

void initialize_tables() {
    // Called only during construction. Every instance has the same native rate,
    // so a later instance cannot change tables while another instance renders.
#if defined(FMER_DEVICE)
    // Construct the target synth before enabling musical callbacks/interrupts.
    // The device adapter has one core owner; this is not a general thread lock.
    static bool initialized = false;
    if (initialized) return;
#else
    static std::once_flag once;
    std::call_once(once, [] {
#endif
        Sin::init();
        Exp2::init();
        Freqlut::init(Synth::native_sample_rate);
        PitchEnv::init(Synth::native_sample_rate);
        Lfo::init(Synth::native_sample_rate);
        Dx7Note::init_tuning();
#if defined(FMER_DEVICE)
    initialized = true;
#else
    });
#endif
}
}

struct Synth::Impl {
    struct VoiceState {
        std::array<char, 156> snapshot{};
        std::uint64_t age{};
        std::size_t cursor{control_block_size};
        std::uint8_t channel{}, note{}, source{};
        std::uint8_t part{no_part};
        bool active{}, held{}, sustained{}, released{}, honor_sustain{true};
        SynthEngine engine{SynthEngine::fm};
        VaParameters va{};
        VaPhase phase{}, increment{}, frequency{};
        std::uint32_t noise_state{0x6d2b79f5u};
        std::uint32_t va_lfo_phase{}, va_lfo_increment{}, wheel_phase{};
        float va_lfo_amount{};
        float lfo_gain{1.f};
        float triangle{}, envelope{}, attack_step{}, decay_step{}, release_step{};
        float ic1{}, ic2{}, filter_a1{}, filter_a2{}, filter_a3{}, filter_k{};
        float velocity_gain{};
        std::uint8_t envelope_stage{};
        // Fixed control-rate trajectory, independent of render call sizes.
        float pitch{}, glide_start{}, glide_target{}, mix_gain{1.f}, dry_gain{-1.f};
        std::uint32_t glide_elapsed{}, glide_frames{}, glide_tick{};
        std::int32_t fm_pitch_offset{};
        GlideContour glide_contour{GlideContour::linear};
        bool pitch_known{};
        float last_sample{}, bridge_offset{};
        std::uint16_t bridge_remaining{};
        bool bridge_pending{};
    };
    struct Voice : VoiceState {
        Dx7Note fm{};
        Lfo lfo{};
        std::array<std::int32_t, control_block_size> block{};
    };
    struct VaCoefficients {
        float cutoff{}, resonance{}, a1{}, a2{}, a3{}, k{};
        bool valid{};
    };
    std::array<VaCoefficients,part_limit+1> va_coefficients{};
    const VaCoefficients& coefficients(const VaParameters& p, std::uint8_t part) noexcept {
        auto& c=va_coefficients[part<part_limit?part:part_limit];
        if(!c.valid || c.cutoff!=p.cutoff_hz || c.resonance!=p.resonance) {
#if defined(FMER_DEVICE)
            const float g=std::tan(static_cast<float>(pi)*p.cutoff_hz/native_sample_rate);
#else
            const float g=static_cast<float>(std::tan(pi*p.cutoff_hz/native_sample_rate));
#endif
            c.k=2.f-1.9f*p.resonance;
            c.a1=1.f/(1.f+g*(g+c.k));c.a2=g*c.a1;c.a3=g*c.a2;
            c.cutoff=p.cutoff_hz;c.resonance=p.resonance;c.valid=true;
        }
        return c;
    }
    // A bounded correction bridges only interrupted voices. A free voice's
    // attack is unchanged; no extra oscillator, allocation or retired voice.
    static float continuous_sample(Voice& v,float sample) noexcept {
        if(v.bridge_remaining) {
            if(v.bridge_pending){v.bridge_offset=v.last_sample-sample;v.bridge_pending=false;}
            sample+=v.bridge_offset*(static_cast<float>(v.bridge_remaining)/128.f);
            --v.bridge_remaining;
        }
        v.last_sample=sample;return sample;
    };

    struct Part { PartParameters instrument{}; float level{1.f}; bool muted{}; };
    struct HeldNote {
        std::uint8_t channel{},note{},velocity{},source{};
        bool honor_sustain{};
    };
    struct HeldStack {
        std::array<HeldNote,mono_held_limit> notes{};
        std::uint8_t count{};
        void erase_at(std::uint8_t i) noexcept {
            for(;i+1<count;++i)notes[i]=notes[i+1];
            --count;
        }
        bool erase(std::uint8_t channel,std::uint8_t note,std::uint8_t source) noexcept {
            for(std::uint8_t i=0;i<count;++i)if(notes[i].channel==channel && notes[i].note==note && notes[i].source==source) {
                erase_at(i);return true;
            }
            return false;
        }
        bool push(HeldNote note) noexcept {
            erase(note.channel,note.note,note.source); // retrigger moves priority to newest
            if(count==notes.size())return false;
            notes[count++]=note;return true;
        }
        template<class Predicate> void erase_if(Predicate match) noexcept {
            for(std::uint8_t i=0;i<count;)if(match(notes[i]))erase_at(i);else ++i;
        }
    };
    std::int16_t scope[4][128]{};
    std::uint32_t scope_frame{};
    std::array<Voice, voice_limit> voices{};
    // Standalone mono reuses lane0; mode transitions clear every lane.
    std::array<HeldStack,part_limit> held{};
    std::array<Controllers, 16> controllers{};
    std::array<bool, 16> sustain{};
    std::array<float, 16> volume{}, expression{}, modwheel{};
    Patch patch{make_init_patch()};
    SynthEngine engine{SynthEngine::fm};
    VaParameters va{};
    std::array<Part, part_limit> parts{};
    GlideParameters glide{};
    SynthStats counters{};
    std::uint64_t generation{};
    std::uint32_t budget{voice_limit};
    bool lfo_enabled{true};
    bool mono{}, parts_enabled{};

    void reset() noexcept {
        for (auto& voice : voices) voice = Voice{};
        for (auto& stack : held) stack.count=0;
        for (auto& controller : controllers) {
            controller = Controllers{};
            controller.values_[kControllerPitch] = 8192;
        }
        sustain.fill(false);
        volume.fill(1.0f);
        expression.fill(1.0f);
        modwheel.fill(0.0f);
        patch = make_init_patch();
        engine = SynthEngine::fm;
        va = VaParameters{};
        parts = {}; va_coefficients = {};
        glide = {};
        counters = SynthStats{};
        std::memset(scope,0,sizeof scope);scope_frame=0;
        generation = 0;
        budget = voice_limit;
        lfo_enabled = true;
        mono = parts_enabled = false;
    }

    void trigger(Voice& voice, const Patch& instrument, SynthEngine next_engine,
                 const VaParameters& next_va, const GlideParameters& next_glide,
                 bool next_lfo, std::uint8_t part, std::uint8_t channel,
                 std::uint8_t note, std::uint8_t velocity, std::uint8_t source,
                 bool honor_sustain, bool mono_note) noexcept;

    static void va_pitch(Voice& voice, int bend) noexcept {
#if defined(FMER_DEVICE)
        voice.frequency = 440.0f * std::exp2((voice.glide_target - 69) / 12.0f);
        const float interval = (bend - 8192) * (3.0f / 8192.0f);
        voice.increment = std::min(0.49f, voice.frequency * (bend==8192?1.f:std::exp2(interval / 12.0f)) / native_sample_rate);
#else
        voice.frequency = 440.0 * std::pow(2.0, (voice.glide_target - 69) / 12.0);
        const double interval = (bend - 8192) * (3.0 / 8192.0);
        voice.increment = std::min(VaPhase(.49),voice.frequency * std::pow(2.0,interval/12.0) / native_sample_rate);
#endif
    }

    static void pitch_step(Voice& voice, int bend) noexcept {
        if (!voice.glide_frames) return;
        const auto elapsed = std::min(voice.glide_frames, voice.glide_elapsed);
        float t = static_cast<float>(elapsed) / voice.glide_frames;
        if (voice.glide_contour == GlideContour::ease_in) t *= t;
        else if (voice.glide_contour == GlideContour::ease_out) t = t * (2.f - t);
        voice.pitch = voice.glide_start + (voice.glide_target - voice.glide_start) * t;
        if (voice.engine == SynthEngine::fm) {
            const auto offset = static_cast<std::int32_t>((voice.pitch - voice.glide_target) * semitone_q24);
            voice.fm.shift_ratio_pitch(offset - voice.fm_pitch_offset, voice.snapshot.data());
            voice.fm_pitch_offset = offset;
        } else {
            const auto pitch = 50857777 + static_cast<std::int32_t>(voice.pitch * semitone_q24) + (bend - 8192) * 512;
            voice.increment = std::min(VaPhase(.49),static_cast<VaPhase>(Freqlut::lookup(pitch)) / VaPhase(16777216));
        }
        if (elapsed == voice.glide_frames) {
            voice.glide_frames = 0;
            voice.pitch = voice.glide_target;
        } else voice.glide_elapsed = std::min(voice.glide_frames, elapsed + static_cast<std::uint32_t>(control_block_size));
    }

    static float smooth_mix(Voice& voice,float target) noexcept {
        voice.mix_gain += .004f*(target-voice.mix_gain);
        if(std::abs(target-voice.mix_gain)<.00001f)voice.mix_gain=target;
        return voice.mix_gain;
    }

    static void release(Voice& voice) noexcept {
        voice.held = false;
        voice.sustained = false;
        if (!voice.released) {
            if (voice.engine == SynthEngine::fm) voice.fm.keyup();
            else {
                voice.envelope_stage = 3;
                voice.release_step = voice.va.release_ms > 0 ?
                    voice.envelope / (voice.va.release_ms * 0.001f * native_sample_rate) : 1.0f;
            }
            voice.released = true;
        }
    }

    std::uint32_t active_count() const noexcept {
        std::uint32_t count = 0;
        for (const auto& voice : voices) if (voice.active) ++count;
        return count;
    }

    Voice* steal_candidate() noexcept {
        const auto priority = [](const Voice& voice) {
            return voice.released ? 0 : voice.sustained ? 1 : 2;
        };
        Voice* selected = nullptr;
        for (auto& voice : voices) {
            if (!voice.active) continue;
            if (!selected || priority(voice) < priority(*selected) ||
                (priority(voice) == priority(*selected) && voice.age < selected->age))
                selected = &voice;
        }
        return selected;
    }

    // Avoid a register-save/call/restore for every voice on every sample.
    FMER_SAMPLE_INLINE static float va_sample(Voice& voice,float wheel,bool lfo_enabled) noexcept {
        voice.lfo_gain += .004f*((lfo_enabled?1.f:0.f)-voice.lfo_gain);
        if (voice.envelope_stage == 0) {
            voice.envelope += voice.attack_step;
            if (voice.envelope >= 1.0f) { voice.envelope = 1.0f; voice.envelope_stage = 1; }
        } else if (voice.envelope_stage == 1) {
            voice.envelope -= voice.decay_step;
            if (voice.envelope <= voice.va.sustain) {
                voice.envelope = voice.va.sustain; voice.envelope_stage = 2;
            }
        } else if (voice.envelope_stage == 3) {
            voice.envelope -= voice.release_step;
            if (voice.envelope <= 0) { voice.active = false; return 0; }
        }
        const VaPhase t = voice.phase;
        VaPhase dt = voice.increment;
        if(wheel>0.f) {
            // Independent 5 Hz performance vibrato, up to +/-50 cents.
            const float x=static_cast<float>(Sin::lookup(static_cast<int32_t>(voice.wheel_phase))) * (0.0288811325f/16777216.f) * wheel;
            dt=std::min(VaPhase(0.49),dt*static_cast<VaPhase>(1.f+x*(1.f+x*(0.5f+x/6.f))));
            voice.wheel_phase=(voice.wheel_phase+1902u)&0xffffffu;
        }
        if (voice.va_lfo_amount > 0.0f) {
            const float lfo = static_cast<float>(Sin::lookup(static_cast<int32_t>(voice.va_lfo_phase))) / 16777216.0f;
            const float x = lfo * voice.va_lfo_amount * voice.lfo_gain;
            // exp(x), |x| <= ln(2)/12: error below 5e-7, <0.001 cent.
            const float ratio = 1.0f + x * (1.0f + x * (0.5f + x * (1.0f / 6.0f)));
            dt = std::min(VaPhase(0.49), dt * static_cast<VaPhase>(ratio));
            voice.va_lfo_phase = (voice.va_lfo_phase + voice.va_lfo_increment) & 0xFFFFFFu;
        }
        float oscillator = 0;
        switch (voice.va.waveform) {
        case VaWaveform::sine:
#if defined(FMER_DEVICE)
            oscillator = static_cast<float>(Sin::lookup(static_cast<int32_t>(t * 16777216.0f))) / 16777216.0f;
#else
            oscillator = static_cast<float>(std::sin(2.0 * pi * t));
#endif
            break;
        case VaWaveform::noise:
            voice.noise_state ^= voice.noise_state << 13;
            voice.noise_state ^= voice.noise_state >> 17;
            voice.noise_state ^= voice.noise_state << 5;
            oscillator = static_cast<float>(voice.noise_state >> 8) * (2.f/16777215.f) - 1.f;
            break;
        case VaWaveform::saw: oscillator = static_cast<float>(VaPhase(2) * t - VaPhase(1)) - poly_blep(t, dt); break;
        case VaWaveform::square:
        case VaWaveform::triangle: {
            float square = (t < VaPhase(0.5) ? 1.0f : -1.0f) + poly_blep(t, dt);
            const VaPhase half_phase = t < VaPhase(0.5) ? t + VaPhase(0.5) : t - VaPhase(0.5);
            square -= poly_blep(half_phase, dt);
            if (voice.va.waveform == VaWaveform::square) oscillator = square;
            else {
                // Leaky integration controls DC; spectral equivalence to the
                // hardware's triangle implementation has not been established.
                voice.triangle = static_cast<float>((VaPhase(1) - dt) * voice.triangle + VaPhase(4) * dt * square);
                oscillator = voice.triangle;
            }
            break;
        }
        }
        voice.phase += dt;
        if (voice.phase >= VaPhase(1)) voice.phase -= VaPhase(1);
        // Trapezoidal state-variable low-pass; coefficients are computed at
        // note-on, not in this sample path. Each voice owns its filter state.
        const float v3 = oscillator - voice.ic2;
        const float v1 = voice.filter_a1 * voice.ic1 + voice.filter_a2 * v3;
        const float v2 = voice.ic2 + voice.filter_a2 * voice.ic1 + voice.filter_a3 * v3;
        voice.ic1 = 2.0f * v1 - voice.ic1;
        voice.ic2 = 2.0f * v2 - voice.ic2;
        return v2 * voice.envelope * voice.velocity_gain * 0.15f;
    }
};

void Synth::Impl::trigger(Voice& voice, const Patch& instrument, SynthEngine next_engine,
                         const VaParameters& next_va, const GlideParameters& next_glide,
                         bool next_lfo, std::uint8_t part_id, std::uint8_t channel,
                         std::uint8_t note, std::uint8_t velocity, std::uint8_t source,
                         bool honor_sustain, bool mono_note) noexcept {
    const float target = static_cast<float>(std::clamp(static_cast<int>(note) +
        static_cast<int>(instrument.vced[144]) - 24,0,127));
    const bool interrupted = voice.active;
    const float previous_sample=voice.last_sample;
    const bool overlapping = voice.active && voice.held;
    const bool should_glide = mono_note && next_glide.mode != GlideMode::off && voice.pitch_known &&
        (next_glide.mode == GlideMode::always || overlapping) && next_glide.time_ms > 0;
    const float from = voice.pitch;
    // Comparing an immutable snapshot is only useful when this event can
    // preserve an overlapping mono envelope. Ordinary retriggers need none.
    bool same_instrument = mono_note && next_glide.mode != GlideMode::off &&
        overlapping && voice.engine == next_engine;
    if (same_instrument) for (std::size_t i=0;i<instrument.vced.size();++i)
        if (voice.snapshot[i] != static_cast<char>(instrument.vced[i])) { same_instrument=false; break; }
    if (same_instrument && next_engine == SynthEngine::va && !same_va(voice.va,next_va)) same_instrument=false;
    const bool preserve = mono_note && next_glide.mode != GlideMode::off && overlapping && same_instrument;
    if (preserve) {
        if (voice.engine == SynthEngine::fm) {
            // Normalize to the new target first; the next control block applies
            // the new trajectory offset. Envelopes and fixed oscillators stay.
            const auto shift=static_cast<std::int32_t>((target-voice.glide_target)*semitone_q24)-voice.fm_pitch_offset;
            voice.fm.shift_ratio_pitch(shift,voice.snapshot.data());
        }
    } else {
        // Value-initialize in the already reserved slot. The target compiler
        // otherwise materializes a large temporary and copies all FM scratch
        // buffers a second time. Placement construction performs no allocation
        // and retains every default, including LFO random/phase reset.
        if(next_engine==SynthEngine::va) {
            // FM scratch is not read by VA. Reset all shared/VA state without
            // clearing thousands of unrelated bytes on every VA note attack.
            static_cast<VoiceState&>(voice)=VoiceState{};
        } else {
            voice.~Voice();
            ::new (static_cast<void*>(&voice)) Voice{};
        }
        if(interrupted){voice.last_sample=previous_sample;voice.bridge_pending=true;voice.bridge_remaining=128;}
        voice.lfo_gain=next_lfo?1.f:0.f;
        for(std::size_t i=0;i<instrument.vced.size();++i)voice.snapshot[i]=static_cast<char>(instrument.vced[i]);
        voice.snapshot[155]=0x3f;
        voice.engine=next_engine;
        if(next_engine==SynthEngine::fm) {
            voice.fm.init(voice.snapshot.data(),static_cast<int>(target),velocity);
            voice.lfo.reset(voice.snapshot.data()+137); voice.lfo.keydown();
        } else {
            voice.va=next_va;
            voice.va_lfo_increment=static_cast<std::uint32_t>(next_va.lfo_rate_hz*(16777216.f/native_sample_rate)+.5f);
            voice.va_lfo_amount=next_va.lfo_depth_cents*(.6931471805599453f/1200.f);
            voice.velocity_gain=velocity/127.f;
            voice.attack_step=next_va.attack_ms>0?1.f/(next_va.attack_ms*.001f*native_sample_rate):1.f;
            voice.decay_step=next_va.decay_ms>0?(1.f-next_va.sustain)/(next_va.decay_ms*.001f*native_sample_rate):1.f;
            const auto& c=coefficients(next_va,part_id);
            voice.filter_k=c.k;voice.filter_a1=c.a1;voice.filter_a2=c.a2;voice.filter_a3=c.a3;
        }
        if(part_id<part_limit)voice.mix_gain=parts[part_id].muted?0.f:parts[part_id].level;
    }
    voice.channel=channel;voice.note=note;voice.source=source;voice.part=part_id;
    voice.honor_sustain=honor_sustain;voice.age=++generation;
    voice.active=voice.held=true;voice.released=voice.sustained=false;
    voice.glide_target=target;voice.glide_start=should_glide?from:target;
    voice.pitch=voice.glide_start;voice.pitch_known=true;voice.fm_pitch_offset=0;
    voice.glide_frames=should_glide?std::max(1u,static_cast<std::uint32_t>(next_glide.time_ms*(native_sample_rate/1000.f))):0;
    voice.glide_elapsed=voice.glide_tick=0;voice.glide_contour=next_glide.contour;
    if(next_engine==SynthEngine::va)va_pitch(voice,controllers[channel].values_[kControllerPitch]);
    ++counters.note_ons;
    counters.peak_voices=std::max(counters.peak_voices,active_count());
}

Synth::Synth() : impl_(std::make_unique<Impl>()) {
    initialize_tables();
    impl_->reset();
}

Synth::~Synth() = default;

bool Synth::init(std::uint32_t sample_rate) noexcept {
    if (sample_rate != native_sample_rate) return false;
    impl_->reset();
    return true;
}

bool Synth::set_patch(const Patch& patch) noexcept {
    if (!validate_patch(patch).valid) {
        ++impl_->counters.rejected_events;
        return false;
    }
    impl_->patch = patch;
    return true;
}

bool Synth::set_engine(SynthEngine engine) noexcept {
    if (engine != SynthEngine::fm && engine != SynthEngine::va) {
        ++impl_->counters.rejected_events;
        return false;
    }
    impl_->engine = engine;
    return true;
}

bool Synth::set_va_parameters(const VaParameters& parameters) noexcept {
    if (!valid_va(parameters)) {
        ++impl_->counters.rejected_events;
        return false;
    }
    impl_->coefficients(parameters,no_part);
    impl_->va = parameters;
    return true;
}

bool Synth::set_voice_budget(std::uint32_t voices) noexcept {
    if (voices == 0 || voices > voice_limit || (impl_->parts_enabled && voices < part_limit)) {
        ++impl_->counters.rejected_events;
        return false;
    }
    impl_->budget = voices;
    while (impl_->active_count() > voices) {
        impl_->steal_candidate()->active = false;
        ++impl_->counters.stolen_voices;
    }
    return true;
}

std::uint32_t Synth::voice_budget() const noexcept { return impl_->budget; }

bool Synth::set_mono(bool enabled) noexcept {
    if (impl_->mono != enabled) { panic(); impl_->mono=enabled; }
    return true;
}

bool Synth::set_glide(const GlideParameters& parameters) noexcept {
    if (!valid_glide(parameters)) { ++impl_->counters.rejected_events; return false; }
    impl_->glide=parameters; return true;
}

bool Synth::configure_part(std::uint8_t part, const PartParameters& parameters) noexcept {
    if (part >= part_limit || !validate_patch(parameters.patch).valid ||
        static_cast<unsigned>(parameters.engine)>1 || !valid_va(parameters.va) || !valid_glide(parameters.glide)) {
        ++impl_->counters.rejected_events; return false;
    }
    impl_->coefficients(parameters.va,part);
    impl_->parts[part].instrument=parameters; return true;
}

bool Synth::set_parts_enabled(bool enabled) noexcept {
    if(enabled && impl_->budget<part_limit) { ++impl_->counters.rejected_events; return false; }
    if(impl_->parts_enabled!=enabled) { panic(); impl_->parts_enabled=enabled; }
    return true;
}

bool Synth::set_part_mix(std::uint8_t part, float level, bool muted) noexcept {
    if(part>=part_limit || !std::isfinite(level) || level<0.f || level>1.f) {
        ++impl_->counters.rejected_events; return false;
    }
    impl_->parts[part].level=level;impl_->parts[part].muted=muted;return true;
}

void Synth::part_note_on(std::uint8_t part,std::uint8_t channel,std::uint8_t note,
                         std::uint8_t velocity,std::uint8_t source,bool honor_sustain) noexcept {
    if(part>=part_limit || !impl_->parts_enabled || channel>15 || note>127 || velocity>127) {
        ++impl_->counters.rejected_events;return;
    }
    if(!velocity) { part_note_off(part,channel,note,source);return; }
    if(!impl_->held[part].push({channel,note,velocity,source,honor_sustain})) {
        ++impl_->counters.rejected_events;return;
    }
    auto& selected=impl_->voices[part];
    if(selected.active) {
        if(selected.held && selected.note==note && selected.source==source && selected.channel==channel)
            ++impl_->counters.retriggers;
        else ++impl_->counters.stolen_voices;
    }
    const auto& p=impl_->parts[part].instrument;
    impl_->trigger(selected,p.patch,p.engine,p.va,p.glide,p.lfo_enabled,part,channel,note,velocity,source,honor_sustain,true);
}

void Synth::part_note_off(std::uint8_t part,std::uint8_t channel,std::uint8_t note,std::uint8_t source) noexcept {
    if(part>=part_limit || !impl_->parts_enabled || channel>15 || note>127) {
        ++impl_->counters.rejected_events;return;
    }
    auto& v=impl_->voices[part];
    auto& held=impl_->held[part];
    if(!held.erase(channel,note,source))return;
    ++impl_->counters.note_offs;
    if(v.part!=part || v.channel!=channel || v.note!=note || v.source!=source)return;
    if(held.count) {
        const auto& next=held.notes[held.count-1];const auto& p=impl_->parts[part].instrument;
        impl_->trigger(v,p.patch,p.engine,p.va,p.glide,p.lfo_enabled,part,next.channel,next.note,next.velocity,
                       next.source,next.honor_sustain,true);
        return;
    }
    if(!v.active || !v.held)return;
    v.held=false;
    if(v.honor_sustain && impl_->sustain[channel])v.sustained=true;else Impl::release(v);
}

void Synth::panic_part(std::uint8_t part) noexcept {
    if(part>=part_limit) { ++impl_->counters.rejected_events;return; }
    impl_->held[part].count=0;
    for(auto& v:impl_->voices)if(v.part==part){v.active=false;v.pitch_known=false;}
}

void Synth::note_on(std::uint8_t channel, std::uint8_t note,
                    std::uint8_t velocity, std::uint8_t source, bool honor_sustain) noexcept {
    if (channel > 15 || note > 127 || velocity > 127) {
        ++impl_->counters.rejected_events;
        return;
    }
    if(impl_->parts_enabled) { ++impl_->counters.rejected_events; return; }
    if (velocity == 0) { note_off(channel, note, source); return; }
    auto& state = *impl_;
    Impl::Voice* selected = nullptr;
    if(state.mono) {
        if(!state.held[0].push({channel,note,velocity,source,honor_sustain})) {
            ++state.counters.rejected_events;return;
        }
        selected=&state.voices[0];
        if(selected->active) {
            if(selected->held && selected->channel==channel && selected->note==note && selected->source==source)
                ++state.counters.retriggers;
            else ++state.counters.stolen_voices;
        }
    }
    // Repeated Note On from the same owner retriggers one voice. Different
    // owners or channels can play the same pitch independently.
    for (auto& voice : state.voices) {
        if(selected)break;
        if (voice.active && voice.held && voice.channel == channel &&
            voice.note == note && voice.source == source) {
            selected = &voice;
            ++state.counters.retriggers;
            break;
        }
    }
    if (!selected && state.active_count() < state.budget) for (auto& voice : state.voices) {
        if (!voice.active) { selected = &voice; break; }
    }
    if (!selected) {
        // Released tails first, then pedal-held notes, then held notes; oldest
        // within each class, with array order breaking equal-age ties.
        selected = state.steal_candidate();
        ++state.counters.stolen_voices;
    }
    state.trigger(*selected,state.patch,state.engine,state.va,state.glide,state.lfo_enabled,
                  no_part,channel,note,velocity,source,honor_sustain,state.mono);
}

void Synth::note_off(std::uint8_t channel, std::uint8_t note,
                     std::uint8_t source) noexcept {
    if (channel > 15 || note > 127) { ++impl_->counters.rejected_events; return; }
    if(impl_->mono && !impl_->parts_enabled) {
        auto& held=impl_->held[0];auto& voice=impl_->voices[0];
        if(!held.erase(channel,note,source))return;
        ++impl_->counters.note_offs;
        if(voice.channel!=channel || voice.note!=note || voice.source!=source)return;
        if(held.count) {
            const auto& next=held.notes[held.count-1];
            impl_->trigger(voice,impl_->patch,impl_->engine,impl_->va,impl_->glide,impl_->lfo_enabled,no_part,
                           next.channel,next.note,next.velocity,next.source,next.honor_sustain,true);
            return;
        }
        if(voice.active && voice.held) {
            voice.held=false;
            if(voice.honor_sustain && impl_->sustain[channel])voice.sustained=true;else Impl::release(voice);
        }
        return;
    }
    for (auto& voice : impl_->voices) {
        if (voice.part != no_part || !voice.active || !voice.held || voice.channel != channel ||
            voice.note != note || voice.source != source) continue;
        voice.held = false;
        if (voice.honor_sustain && impl_->sustain[channel]) voice.sustained = true;
        else Impl::release(voice);
        ++impl_->counters.note_offs;
    }
}

void Synth::control_change(std::uint8_t channel, std::uint8_t cc,
                           std::uint8_t value) noexcept {
    if (channel > 15 || cc > 127 || value > 127) {
        ++impl_->counters.rejected_events;
        return;
    }
    auto& state = *impl_;
    switch (cc) {
    case 1: state.modwheel[channel] = value / 127.0f; break;
    case 7: state.volume[channel] = value / 127.0f; break;
    case 11: state.expression[channel] = value / 127.0f; break;
    case 64:
        state.sustain[channel] = value >= 64;
        if (value < 64) for (auto& voice : state.voices)
            if (voice.active && voice.channel == channel && voice.sustained)
                Impl::release(voice);
        break;
    case 120: // MIDI All Sound Off: immediate channel silence, pedal unchanged.
        for(auto& held:state.held)held.erase_if([channel](const Impl::HeldNote& n){return n.channel==channel;});
        for (auto& voice : state.voices) if (voice.channel == channel) voice.active = false;
        break;
    case 121:
        state.volume[channel] = state.expression[channel] = 1.0f;
        state.modwheel[channel]=0.f;
        pitch_bend(channel, 8192);
        control_change(channel, 64, 0);
        break;
    case 123: // All Notes Off respects the sustain pedal.
        for(auto& held:state.held)held.erase_if([channel](const Impl::HeldNote& n){return n.channel==channel;});
        for (auto& voice : state.voices) if (voice.active && voice.channel == channel && voice.held) {
            voice.held = false;
            if (voice.honor_sustain && state.sustain[channel]) voice.sustained = true;
            else Impl::release(voice);
        }
        break;
    default: ++state.counters.rejected_events; break;
    }
}

void Synth::pitch_bend(std::uint8_t channel, std::uint16_t value14) noexcept {
    if (channel > 15 || value14 > 16383) { ++impl_->counters.rejected_events; return; }
    impl_->controllers[channel].values_[kControllerPitch] = value14;
    bool any_va = false;
    for (const auto& voice : impl_->voices)
        if (voice.active && voice.engine == SynthEngine::va && voice.channel == channel) any_va = true;
    if (!any_va) return;
#if defined(FMER_DEVICE)
    const float bend = (static_cast<int>(value14) - 8192) * (3.0f / 8192.0f);
    const float multiplier = std::exp2(bend / 12.0f) / native_sample_rate;
#else
    const double bend = (static_cast<int>(value14) - 8192) * (3.0 / 8192.0);
    const double multiplier = std::pow(2.0, bend / 12.0) / native_sample_rate;
#endif
    for (auto& voice : impl_->voices)
        if (voice.active && voice.engine == SynthEngine::va && voice.channel == channel) {
            if(voice.glide_frames) {
                const auto pitch=50857777+static_cast<std::int32_t>(voice.pitch*semitone_q24)+(static_cast<int>(value14)-8192)*512;
                voice.increment=std::min(VaPhase(.49),static_cast<VaPhase>(Freqlut::lookup(pitch))/VaPhase(16777216));
            } else voice.increment = std::min(VaPhase(0.49), voice.frequency * multiplier);
        }
}

void Synth::set_lfo_enabled(bool enabled) noexcept { impl_->lfo_enabled=enabled; }

void Synth::render(float* mono, std::size_t frames, float* dry, std::uint8_t bypass_mask, std::uint8_t preview_sources) noexcept {
    if (!mono && frames) { ++impl_->counters.rejected_events; return; }
    auto& state = *impl_;
    constexpr float gain = 0.15f / 16777216.0f; // Q24 plus fixed mix headroom.
    if (!frames) return;
    std::fill_n(mono, frames, 0.0f);
    if(dry)std::fill_n(dry,frames,0.f);
    if(state.parts_enabled)for(std::size_t i=0;i<frames;++i)if(((state.scope_frame+i)&3u)==0u)
        for(unsigned t=0;t<4;t++)state.scope[t][((state.scope_frame+i)/4u)%128u]=0;
    // Voice order (and each sample's arithmetic order) stays unchanged. Work
    // over contiguous blocks so inactive voices and metadata are not rescanned
    // for every sample; no event can arrive during this single-owner call.
    for (auto& voice : state.voices) {
        if (!voice.active) continue;
        const float volume = state.volume[voice.channel], expression = state.expression[voice.channel];
        const bool unity = volume == 1.0f && expression == 1.0f;
        const bool is_part=voice.part<part_limit;
        const auto tap=[&](std::size_t at,float value){
            const auto absolute=state.scope_frame+static_cast<std::uint32_t>(at);
            if(is_part && !(absolute&3u))state.scope[voice.part][(absolute/4u)%128u]=static_cast<std::int16_t>(std::clamp(value*32767.f,-32767.f,32767.f));
        };
        const float dry_target=dry && is_part && (bypass_mask&(1u<<voice.part))?1.f:0.f;
        if(voice.dry_gain<0.f || !dry)voice.dry_gain=dry_target;
        const bool stable_route=voice.dry_gain==dry_target;
        float* destination=dry_target?dry:mono;
        const auto route_sample=[&](std::size_t at,float sample){
            if(voice.dry_gain<dry_target)voice.dry_gain=std::min(dry_target,voice.dry_gain+1.f/128.f);
            else voice.dry_gain=std::max(dry_target,voice.dry_gain-1.f/128.f);
            mono[at]+=sample*(1.f-voice.dry_gain);dry[at]+=sample*voice.dry_gain;
        };
        // Stopped-transport audition can bypass a part's mute for explicitly
        // selected input sources. Level, routing, envelopes and saved mix stay intact.
        bool quiet=is_part && state.parts[voice.part].muted;
        if(quiet && preview_sources && voice.source<8 && (preview_sources&(1u<<voice.source)))quiet=false;
        const float part_gain=is_part?(quiet?0.f:state.parts[voice.part].level):1.f;
        // Once the ramp has snapped to its exact target it remains there for
        // this single-owner call. Avoid per-sample smoothing/fabsf calls in
        // steady state; changing levels still uses the identical recurrence.
        const bool stable_mix=!is_part || voice.mix_gain==part_gain;
        const bool lfo_enabled=is_part?state.parts[voice.part].instrument.lfo_enabled:state.lfo_enabled;
        if (voice.engine == SynthEngine::va) {
            for (std::size_t frame = 0; frame < frames && voice.active; ++frame) {
                if(voice.glide_frames) {
                    if(!voice.glide_tick)Impl::pitch_step(voice,state.controllers[voice.channel].values_[kControllerPitch]);
                    voice.glide_tick=(voice.glide_tick+1)%control_block_size;
                }
                const float sample = Impl::continuous_sample(voice,Impl::va_sample(voice,state.modwheel[voice.channel],lfo_enabled));
                if(is_part)tap(frame,sample*volume*expression);
                if(!stable_route)route_sample(frame,sample*volume*expression*(stable_mix?part_gain:Impl::smooth_mix(voice,part_gain)));
                else if(is_part && !stable_mix)destination[frame]+=sample*volume*expression*Impl::smooth_mix(voice,part_gain);
                else if(is_part && part_gain!=1.f)destination[frame]+=sample*volume*expression*part_gain;
                else destination[frame] += unity ? sample : sample * volume * expression;
            }
            continue;
        }
        std::size_t frame = 0;
        while (frame < frames) {
            if (voice.cursor == control_block_size) {
                if (voice.released && voice.fm.finished()) { voice.active = false; break; }
                voice.block.fill(0);
                auto& controller=state.controllers[voice.channel];
                Impl::pitch_step(voice,controller.values_[kControllerPitch]);
                const auto bend=controller.values_[kControllerPitch];
                if(state.modwheel[voice.channel]>0.f) {
                    controller.values_[kControllerPitch]=bend+static_cast<int>(static_cast<float>(Sin::lookup(static_cast<int32_t>(voice.wheel_phase))) * (1365.333333f/16777216.f) * state.modwheel[voice.channel]);
                    voice.wheel_phase=(voice.wheel_phase+121740u)&0xffffffu;
                }
                voice.lfo_gain+=.22625f*((lfo_enabled?1.f:0.f)-voice.lfo_gain);
                const auto lfo_sample=voice.lfo.getsample(), lfo_delay=voice.lfo.getdelay();
                voice.fm.compute(voice.block.data(), lfo_sample,
                    static_cast<int32_t>(static_cast<float>(lfo_delay)*voice.lfo_gain), &controller);
                controller.values_[kControllerPitch]=bend;
                voice.cursor = 0;
            }
            const auto count = std::min(frames-frame, control_block_size-voice.cursor);
            const bool bridging=voice.bridge_remaining!=0;
            if(bridging)for(std::size_t i=0;i<count;++i) {
                const float sample=Impl::continuous_sample(voice,static_cast<float>(voice.block[voice.cursor+i])*gain)*volume*expression;
                if(is_part)tap(frame+i,sample);
                const float mixed=sample*(stable_mix?part_gain:Impl::smooth_mix(voice,part_gain));
                if(!stable_route)route_sample(frame+i,mixed);else destination[frame+i]+=mixed;
            }
            else if(!stable_route)for(std::size_t i=0;i<count;++i)
                route_sample(frame+i,static_cast<float>(voice.block[voice.cursor+i])*gain*volume*expression*(stable_mix?part_gain:Impl::smooth_mix(voice,part_gain)));
            else if(is_part && !stable_mix)for(std::size_t i=0;i<count;++i)
                destination[frame+i]+=static_cast<float>(voice.block[voice.cursor+i])*gain*volume*expression*Impl::smooth_mix(voice,part_gain);
            else if(is_part && part_gain!=1.f)for(std::size_t i=0;i<count;++i)
                destination[frame+i]+=static_cast<float>(voice.block[voice.cursor+i])*gain*volume*expression*part_gain;
            else if (unity) for (std::size_t i = 0; i < count; ++i)
                destination[frame+i] += static_cast<float>(voice.block[voice.cursor+i]) * gain;
            else for (std::size_t i = 0; i < count; ++i)
                destination[frame+i] += static_cast<float>(voice.block[voice.cursor+i]) * gain * volume * expression;
            if(!bridging)voice.last_sample=static_cast<float>(voice.block[voice.cursor+count-1])*gain;
            if(is_part && !bridging)for(std::size_t i=(4u-((state.scope_frame+frame)&3u))&3u;i<count;i+=4u)
                tap(frame+i,static_cast<float>(voice.block[voice.cursor+i])*gain*volume*expression);
            voice.cursor += count;
            frame += count;
        }
    }
    for (std::size_t frame = 0; frame < frames; ++frame) {
        const float sample = mono[frame];
        if (sample > 1.0f || sample < -1.0f) ++state.counters.clipped_samples;
        mono[frame] = std::clamp(sample, -1.0f, 1.0f);
    }
    state.scope_frame+=static_cast<std::uint32_t>(frames);
    state.counters.rendered_frames += frames;
}

void Synth::part_scopes(std::int16_t out[4][32]) const noexcept {
    if(!out)return;
    const auto& s=*impl_;unsigned oldest=(s.scope_frame+3u)/4u%128u;
    for(unsigned t=0;t<4;t++){
        unsigned start=oldest;
        for(unsigned i=1;i<32;i++)if(s.scope[t][(oldest+i-1)%128]<=0 && s.scope[t][(oldest+i)%128]>0){start=(oldest+i)%128;break;}
        for(unsigned i=0;i<32;i++)out[t][i]=s.parts_enabled?s.scope[t][(start+i*3)%128]:0;
    }
}

void Synth::panic() noexcept {
    for(auto& held:impl_->held)held.count=0;
    for (auto& voice : impl_->voices) {voice.active = false;voice.pitch_known=false;}
    impl_->sustain.fill(false);
}

void Synth::panic_source(std::uint8_t source) noexcept {
    for(auto& held:impl_->held)held.erase_if([source](const Impl::HeldNote& n){return n.source==source;});
    for (auto& voice : impl_->voices) if (voice.source == source) {voice.active = false;voice.pitch_known=false;}
}

SynthStats Synth::stats() const noexcept {
    auto result = impl_->counters;
    result.active_voices = impl_->active_count();
    for (const auto& voice : impl_->voices) if (voice.active && voice.released) ++result.released_voices;
    return result;
}

SynthActivity Synth::activity() const noexcept {
    SynthActivity result{};
    for (const auto& voice : impl_->voices) {
        if (!voice.active) continue;
        const auto word = voice.note / 32u;
        const auto bit = std::uint32_t{1} << (voice.note % 32u);
        result.active_notes[word] |= bit;
        if (voice.held || voice.sustained) result.gated_notes[word] |= bit;
        ++result.active_voices;
    }
    return result;
}

SynthActivity Synth::part_activity(std::uint8_t part) const noexcept {
    SynthActivity result{};
    if(part>=part_limit)return result;
    for(const auto& voice:impl_->voices) {
        if(!voice.active || voice.part!=part)continue;
        const auto word=voice.note/32u, bit=std::uint32_t{1}<<(voice.note%32u);
        result.active_notes[word]|=bit;
        if(voice.held || voice.sustained)result.gated_notes[word]|=bit;
        ++result.active_voices;
    }
    return result;
}

} // namespace fmer
