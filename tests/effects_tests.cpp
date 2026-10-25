#include "effects.hpp"
#include "finite_float.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <limits>
#include <new>
#include <stdexcept>
#include <vector>

namespace {
std::size_t allocations = 0;
}

// Count ordinary C++ allocations at the boundary of the actual compiled effect
// implementation. Buffers/fixtures/assertion messages are created beforehand.
void* operator new(std::size_t bytes) {
    ++allocations;
    if (void* memory = std::malloc(bytes ? bytes : 1)) return memory;
    throw std::bad_alloc();
}
void* operator new[](std::size_t bytes) { return ::operator new(bytes); }
void operator delete(void* memory) noexcept { std::free(memory); }
void operator delete[](void* memory) noexcept { std::free(memory); }
void operator delete(void* memory, std::size_t) noexcept { std::free(memory); }
void operator delete[](void* memory, std::size_t) noexcept { std::free(memory); }

namespace {
void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

std::vector<float> signal(std::size_t frames) {
    std::vector<float> result(frames);
    for (std::size_t i = 0; i < frames; ++i)
        result[i] = 0.28f * std::sin(static_cast<float>(i) * 0.063f) +
                    0.12f * std::sin(static_cast<float>(i) * 0.791f);
    return result;
}

double energy(const std::vector<float>& samples, std::size_t start = 0,
              std::size_t finish = std::numeric_limits<std::size_t>::max()) {
    double result = 0;
    for (std::size_t i = start; i < std::min(finish, samples.size()); ++i) {
        require(std::isfinite(samples[i]) && std::abs(samples[i]) <= 1,
                "effect output must be finite in audio range");
        result += samples[i] * samples[i];
    }
    return result;
}

void process(fmer::Effects& effects, std::vector<float>& data, std::size_t chunk) {
    for (std::size_t offset = 0; offset < data.size(); offset += chunk)
        effects.process(data.data() + offset, std::min(chunk, data.size() - offset));
}

fmer::EffectParameters all_effects() {
    fmer::EffectParameters p;
    p.drive = 0.4f; p.chorus = 0.35f; p.delay = 0.3f; p.reverb = 0.35f;
    p.phaser = 0.45f; p.cutoff_hz = 6000; p.delay_ms = 120;
    return p;
}

void exact_bypass() {
    fmer::Effects effects;
    auto original = signal(44111), output = original;
    original[0] = output[0] = -0.0f;
    original[1] = output[1] = std::numeric_limits<float>::denorm_min();
    process(effects, output, 37);
    require(std::memcmp(original.data(), output.data(), output.size() * sizeof(float)) == 0,
            "default bypass preserves every finite in-range sample bit");
    require(effects.stats().processed_frames == output.size(), "processed frames counted");
    require(effects.stats().tail_peak == 0, "bypass has no stale effect tails");
    require(fmer::Effects::storage_bytes() < 174080, "complete six-stage storage stays below 174080 bytes");
}

void finite_guard_contract() {
    // Every exponent and sign, with zero, subnormal/normal boundaries, quiet
    // and signaling NaN payloads. This same guard also protects target PCM.
    std::array<float, 512 * 8> values{};
    const std::uint32_t mantissas[]{0, 1, 0x1fffff, 0x3fffff, 0x400000,
                                   0x400001, 0x7ffffe, 0x7fffff};
    unsigned cursor = 0, rejected = 0;
    for (unsigned sign = 0; sign < 2; ++sign)
        for (unsigned exponent = 0; exponent < 256; ++exponent)
            for (auto mantissa : mantissas) {
                const std::uint32_t bits = (sign << 31) | (exponent << 23) | mantissa;
                float value; std::memcpy(&value, &bits, sizeof(value));
                const bool expected = std::isfinite(value);
                require(fmer::finite_float(value) == expected,
                        "IEEE finite guard agrees for every sign/exponent and boundary payload");
                // Match the actual final adapter clamp before int16 conversion.
                const float old_pcm = expected ? std::clamp(value, -1.f, 1.f) : 0.f;
                const float new_pcm = fmer::finite_float(value) ? std::clamp(value, -1.f, 1.f) : 0.f;
                require(std::memcmp(&old_pcm, &new_pcm, sizeof(float)) == 0,
                        "adapter finite guard preserves clamped PCM including signed zero");
                rejected += !expected;
                values[cursor++] = value;
            }
    fmer::Effects fx;
    fx.process(values.data(), values.size());
    require(fx.meters().sanitized_samples == rejected,
            "effects sanitize all NaNs and infinities, never finite extremes/subnormals");
    for (float value : values)
        require(std::isfinite(value) && std::abs(value) <= fmer::Effects::output_ceiling,
                "all IEEE boundary inputs have bounded finite output");
}

void final_guard() {
    fmer::Effects fx;
    std::array<float,9> signal{{-.981f,-.98f,-.9f,-0.f,0.f,.9f,.98f,.981f,100.f}};
    const auto original=signal;fx.process(signal.data(),signal.size());
    for(unsigned i=1;i<7;i++)require(!std::memcmp(&signal[i],&original[i],sizeof(float)),"hard guard is bit-exact below its ceiling");
    require(signal[0]==-.98f && signal[7]==.98f && signal[8]==.98f,"hard guard bounds all dry peaks");
    const auto m=fx.meters();require(m.guarded_samples==3 && m.peak_input==100 && m.peak_output==.98f,"cached guard meters distinguish pre/post peaks");
    fx.reset();require(!fx.meters().guarded_samples && !fx.meters().peak_output,"guard meter epoch resets explicitly");
}

#if defined(FMER_DEVICE)
void target_phaser_reference_accuracy() {
    // Independent pre-optimization target reference: retain the established
    // target sine and32-sample coefficient schedule, use full exp2/tan math.
    // Low levels avoid the limiter masking the approximation's error.
    const auto sine=[](float phase) {
        float q=phase*4.f;const bool negative=q>=2.f;if(negative)q-=2.f;
        if(q>1.f)q=2.f-q;const float x=q*(3.14159265358979323846f*.5f),s=x*x;
        const float v=x*(1.f+s*(-1.f/6.f+s*(1.f/120.f+s*(-1.f/5040.f+s/362880.f))));
        return negative?-v:v;
    };
    double worst_snr=300;float worst_delta=0;
    for(float rate:{.5f,6.f})for(float depth:{0.f,1.f})for(float mix:{.5f,1.f}) {
        fmer::Effects fx;fmer::EffectParameters p;p.phaser=mix;p.phaser_rate_hz=rate;p.phaser_depth=depth;
        require(fx.set_parameters(p),"phaser sweep settings accepted");
        std::vector<float> actual(44100*4),expected(actual.size());
        std::uint32_t noise=719;double chirp_phase=0;
        for(std::size_t i=0;i<actual.size();++i) {
            noise=noise*1664525u+1013904223u;
            const double frequency=20.*std::pow(1000.,double(i)/actual.size());
            chirp_phase+=2.*3.14159265358979323846*frequency/44100.;
            actual[i]=i>actual.size()-22050?0.f:.12f*float(std::sin(chirp_phase))+
                .08f*float(std::int32_t(noise))/2147483648.f;
        }
        actual[0]+=.25f;expected=actual;
        constexpr std::size_t edit=44100+31;float phase=0,coefficient=0,delta=0;
        unsigned left=0;std::array<float,4> state{};
        for(std::size_t i=0;i<expected.size();++i) {
            if(i==edit){p.phaser_rate_hz=rate==.5f?6.f:.5f;p.phaser_depth=depth==0.f?1.f:.25f;left=0;}
            const auto at=[&](float x) {
                const float frequency=700.f*std::exp2(2.5f*p.phaser_depth*sine(x));
                const float t=std::tan(3.14159265358979323846f*frequency/44100.f);
                return (t-1.f)/(t+1.f);
            };
            if(!left) {
                coefficient=at(phase);float future=phase+32.f*p.phaser_rate_hz/44100.f;
                if(future>=1.f)future-=1.f;delta=(at(future)-coefficient)/32.f;left=32;
            }
            const float a=coefficient;coefficient+=delta;--left;float wet=expected[i];
            for(float& memory:state){const float output=a*wet+memory;memory=wet-a*output;
                if(std::abs(memory)<1e-20f)memory=0;wet=output;}
            phase+=p.phaser_rate_hz/44100.f;if(phase>=1.f)phase-=1.f;
            // The musical mix control spans 0..50% wet, as documented by
            // EffectParameters. The reference must use that same gain.
            expected[i]+=(.5f*mix)*(wet-expected[i]);
            require(std::abs(expected[i])<.9f,"reference input stays below output knee");
        }
        p.phaser_rate_hz=rate;p.phaser_depth=depth;
        const unsigned chunks[]{1,17,31,32,33,128};unsigned chunk=0;
        for(std::size_t at=0;at<actual.size();) {
            if(at==edit){p.phaser_rate_hz=rate==.5f?6.f:.5f;p.phaser_depth=depth==0.f?1.f:.25f;
                require(fx.set_parameters(p),"mid-control phaser edit accepted");}
            std::size_t count=std::min<std::size_t>(chunks[chunk++%6],actual.size()-at);
            if(at<edit)count=std::min(count,edit-at);
            fx.process(actual.data()+at,count);at+=count;
        }
        double e=0,s=0;float peak=0;
        for(std::size_t i=0;i<actual.size();++i){const double d=double(actual[i])-expected[i];
            e+=d*d;s+=double(expected[i])*expected[i];peak=std::max(peak,float(std::abs(d)));}
        const double snr=e?10.*std::log10(s/e):300.;worst_snr=std::min(worst_snr,snr);worst_delta=std::max(worst_delta,peak);
        require(snr>=85 && peak<=.0002f,"target phaser matches full-math reference within85dB / .0002FS");
        require(fx.meters().sanitized_samples==0 && fx.meters().limited_samples==0 && fx.meters().guarded_samples==0,
                "phaser comparison never masks error using sanitization or limiting");
    }
    std::cout<<"target phaser:8 reference cases, worst SNR="<<worst_snr<<" dB, max error="<<worst_delta<<'\n';
}
#endif

// Independent float32 delay oracle retains the 706 storage/feedback behavior.
// It deliberately has no compact-sample encoder or decoder shared with Effects.
std::vector<float> float_delay_reference(const std::vector<float>& input,
                                       const fmer::EffectParameters& p) {
    std::vector<float> ring(44101), output(input.size());
    std::size_t write = 0;
    const float distance = 44100.0f * p.delay_ms / 1000.0f;
    for (std::size_t i = 0; i < input.size(); ++i) {
        float position = static_cast<float>(write) - distance;
        if (position < 0) position += static_cast<float>(ring.size());
        const auto first = static_cast<std::size_t>(position);
        const auto next = first + 1 == ring.size() ? 0 : first + 1;
        const float fraction = position - static_cast<float>(first);
        const float echo = ring[first] + (ring[next] - ring[first]) * fraction;
        ring[write] = input[i] + echo * p.feedback;
        if (++write == ring.size()) write = 0;
        output[i] = input[i] + .68f*p.delay*echo;
        const float a=std::abs(output[i]);
        if(a>.9f)output[i]=std::copysign(.9f+.1f*(a-.9f)/(.1f+a-.9f),output[i]);
        output[i]=std::clamp(output[i],-.98f,.98f);
    }
    return output;
}

void compact_delay_accuracy_and_duration() {
    double worst_normal_snr = 200, worst_quiet_snr = 200;
    float maximum_normal_error = 0, maximum_quiet_error = 0;
    for (float amplitude : {0.8f, 0.001f}) {
        for (float milliseconds : {20.0f, 137.25f, 1000.0f}) {
            for (float feedback : {0.0f, 0.5f, 0.85f}) {
                fmer::Effects effects;
                fmer::EffectParameters p;
                p.delay = 1; p.delay_ms = milliseconds; p.feedback = feedback;
                require(effects.set_parameters(p), "compact quality fixture accepted");
                // Two seconds of independently generated music-like tones,
                // followed by four seconds of silence to include feedback tails.
                std::vector<float> input(44100 * 6);
                for (std::size_t i = 0; i < 44100 * 2; ++i) {
                    const double time = static_cast<double>(i) / 44100;
                    input[i] = amplitude * static_cast<float>(0.55 * std::sin(2 * 3.141592653589793 * 221 * time) +
                        0.25 * std::sin(2 * 3.141592653589793 * 1297 * time) +
                        0.20 * std::sin(2 * 3.141592653589793 * 10103 * time));
                }
                const auto expected = float_delay_reference(input, p);
                auto actual = input;
                process(effects, actual, 113);
                double reference_energy = 0, error_energy = 0;
                float peak_error = 0;
                for (std::size_t i = 0; i < actual.size(); ++i) {
                    const double error = static_cast<double>(actual[i]) - expected[i];
                    error_energy += error * error;
                    reference_energy += static_cast<double>(expected[i]) * expected[i];
                    peak_error = std::max(peak_error, static_cast<float>(std::abs(error)));
                }
                const double snr = 10 * std::log10(reference_energy / error_energy);
                require(std::isfinite(snr), "compact delay quality result is finite");
                if (amplitude > 0.1f) {
                    worst_normal_snr = std::min(worst_normal_snr, snr);
                    maximum_normal_error = std::max(maximum_normal_error, peak_error);
                    require(snr > 65 && peak_error < 0.0008f,
                            "normal-level delay remains above 65dB reference SNR with bounded peak error");
                } else {
                    worst_quiet_snr = std::min(worst_quiet_snr, snr);
                    maximum_quiet_error = std::max(maximum_quiet_error, peak_error);
                    require(snr > 48 && peak_error < 0.0000015f,
                            "minus60dB input and tails retain above 48dB relative SNR");
                }
                require(effects.stats().sanitized_samples == 0 && effects.stats().clipped_samples == 0,
                        "compact quality fixtures require no clipping or nonfinite recovery");
            }
        }
    }
    fmer::Effects longest;
    fmer::EffectParameters p;
    p.delay = 1; p.delay_ms = 1000; p.feedback = 0;
    longest.set_parameters(p);
    std::vector<float> impulse(88201); impulse[0] = -1;
    process(longest, impulse, 127);
    require(impulse[0]<-.9f && energy(impulse, 1, 44100) == 0 && impulse[44100] == -.68f &&
            energy(impulse, 44101) == 0,
            "negative full-scale impulse arrives at exactly one second without shortening or extra echoes");
    std::cout << "compact delay: 18 float-reference cases; worst normal SNR=" << worst_normal_snr
        << " dB, max error=" << maximum_normal_error << "; worst -60dB input SNR="
        << worst_quiet_snr << " dB, max error=" << maximum_quiet_error << '\n';
}

void compact_delay_quiet_tail_and_no_limit_cycles() {
    fmer::Effects effects;
    fmer::EffectParameters p;
    p.delay = 1; p.delay_ms = 20; p.feedback = 0.85f;
    effects.set_parameters(p);
    std::vector<float> input(44100 * 4);
    input[0] = 0.00001f; input[1] = -0.00001f;
    process(effects, input, 89);
    require(input[882] > 0.0000067f && input[882] < 0.0000069f && input[883] == -input[882],
            "minus100dB bipolar input survives compact delay with correct polarity");
    require(energy(input, 44100 * 3) == 0 && effects.stats().tail_peak == 0,
            "subnormal feedback decays to exact silence with no rounding limit cycle");
    effects.reset();
    std::fill(input.begin(), input.end(), 0.0f); input[0] = 1;
    process(effects, input, 137);
    require(energy(input, 44100 * 3) == 0 && effects.stats().tail_peak == 0,
            "full-scale maximum-feedback impulse also reaches exact silence at short delay");
}

// Independent float32 delay oracle also exercises repeated over-range internal
// state: compact storage must not silently saturate at +/-1 before output knee.
void compact_delay_preserves_internal_headroom() {
    std::vector<float> input(44100*4,.8f);
    std::fill(input.begin()+44100*2,input.end(),0.f);
    fmer::EffectParameters p;p.delay=1;p.delay_ms=20;p.feedback=.85f;
    const auto expected=float_delay_reference(input,p);
    auto actual=input;fmer::Effects fx;fx.set_parameters(p);process(fx,actual,127);
    double err=0,ref=0;
    for(unsigned i=0;i<actual.size();++i){const double e=actual[i]-expected[i];err+=e*e;ref+=expected[i]*expected[i];}
    require(10*std::log10(ref/err)>60,"compact delay retains feedback state above full scale");
    require(actual[88200]>.95f,"dry release exposes echo accumulated above unit amplitude");
    require(fx.stats().limited_samples>0 && !fx.stats().clipped_samples,"musical peaks use reported soft knee, not hard clipping");
}

void fdn_models_and_filter_response() {
    std::array<std::vector<float>,2> responses;
    for(unsigned model=0;model<2;++model) {
        fmer::Effects fx;fmer::EffectParameters p;p.reverb=1;p.reverb_decay=.5f;
        p.reverb_model=static_cast<fmer::ReverbModel>(model);fx.set_parameters(p);
        auto& out=responses[model];out.resize(44100*4);out[0]=.25f;process(fx,out,73);
        require(out[0]==.25f,"reverb preserves the initial dry attack at full send");
        unsigned nonzero=0;for(unsigned i=4410;i<8820;++i)if(std::abs(out[i])>1e-6f)++nonzero;
        require(nonzero>4000,"FDN builds a dense non-sparse tail within 100ms");
        require(energy(out,44100*3)<energy(out,4410,8820)*.01,"both FDN models decay");
    }
    require(responses[0]!=responses[1],"Room and Plate produce distinct actual impulse responses");
    const auto gain=[](unsigned mode,float resonance,float hz) {
        fmer::Effects fx;fmer::EffectParameters p;p.cutoff_hz=1000;p.resonance=resonance;
        p.filter_mode=static_cast<fmer::FilterMode>(mode);fx.set_parameters(p);
        std::vector<float> out(22050);for(unsigned i=0;i<out.size();++i)out[i]=.01f*std::sin(6.28318530718f*hz*i/44100.f);
        process(fx,out,79);return std::sqrt(energy(out,11025)/11025)*141.421356;
    };
    require(gain(0,0,100)>gain(0,0,10000)*40,"LP passes lows and rejects highs");
    require(gain(1,0,10000)>gain(1,0,100)*40,"HP passes highs and rejects lows");
    require(gain(2,1,1000)>gain(2,1,100)*40,"BP selects target frequency with normalized peak");
    require(gain(0,1,1000)>gain(0,0,1000)*10,"resonance creates a strong measured cutoff peak");
    // Extreme cutoff/Q changes remain finite while processing existing state.
    fmer::Effects fx;fmer::EffectParameters p;p.resonance=1;std::vector<float> chunk(64,.01f);
    for(unsigned i=0;i<2000;++i){p.cutoff_hz=i%2?20.f:20000.f;p.filter_mode=static_cast<fmer::FilterMode>(i%3);fx.set_parameters(p);std::fill(chunk.begin(),chunk.end(),.01f);fx.process(chunk.data(),chunk.size());energy(chunk);}
    require(!fx.stats().sanitized_samples,"extreme resonant sweeps keep internal state finite");
}

void delay_time_edits_and_voicing() {
    fmer::Effects fx;fmer::EffectParameters p;p.delay=1;p.feedback=.6f;p.delay_ms=120;fx.set_parameters(p);
    auto warm=signal(44100);process(fx,warm,128);
    // A DC-filled ring makes an instantaneous jump obvious without confusing
    // the test with the derivative of high-frequency music.
    std::vector<float> dc(44100*5,.05f);process(fx,dc,128);
    float previous=dc.back(),jump=0;
    for(unsigned k=0;k<150;++k){p.delay_ms=20.f+(k*137u)%981;fx.set_parameters(p);std::array<float,64> block;block.fill(.05f);fx.process(block.data(),block.size());for(float x:block){jump=std::max(jump,std::abs(x-previous));previous=x;}}
    require(jump<.01f,"rapid delay time edits crossfade readheads without discontinuous DC jumps");
    fmer::Effects clean, dark;p.delay_ms=100;p.feedback=.5f;p.delay_model=fmer::DelayModel::clean;clean.set_parameters(p);p.delay_model=fmer::DelayModel::warm;dark.set_parameters(p);
    auto a=signal(44100),b=a;process(clean,a,71);process(dark,b,71);
    require(a!=b,"warm delay actually changes repeat tone");
}

void optional_stage_host_profile() {
    const auto source = signal(44100 * 2);
    auto output = source;
    const std::array<const char*, 7> names{{"bypass", "filter", "reverb", "delay", "drive", "chorus", "phaser"}};
    std::cout << "host-only two-second stage profile (microseconds; not device deadlines):";
    for (unsigned stage = 0; stage < names.size(); ++stage) {
        fmer::Effects effects;
        fmer::EffectParameters p;
        if (stage == 1) p.cutoff_hz = 5000;
        if (stage == 2) p.reverb = 0.5f;
        if (stage == 3) p.delay = 0.5f;
        if (stage == 4) p.drive = 0.5f;
        if (stage == 5) p.chorus = 0.5f;
        if (stage == 6) p.phaser = 0.5f;
        effects.set_parameters(p);
        double best = std::numeric_limits<double>::max();
        for (unsigned repeat = 0; repeat < 3; ++repeat) {
            effects.reset(); output = source;
            const auto begin = std::chrono::steady_clock::now();
            process(effects, output, 128);
            const auto end = std::chrono::steady_clock::now();
            best = std::min(best, std::chrono::duration<double, std::micro>(end - begin).count());
            require(energy(output) > 0, "profile processes audible samples");
        }
        std::cout << ' ' << names[stage] << '=' << best;
    }
    std::cout << '\n';
}

void delay_impulse_and_feedback() {
    fmer::Effects effects;
    fmer::EffectParameters p;
    p.delay = 1; p.delay_ms = 100; p.feedback = 0.5f;
    require(effects.set_parameters(p), "delay parameters accepted");
    std::vector<float> output(44100);
    output[0] = 1;
    process(effects, output, 13);
    require(output[0]>.9f && energy(output,1,4410)==0,"full send preserves attack, no early echo");
    require(output[4410] == 0.68f, "100ms echo gain is independent of feedback injection");
    require(output[8820] == 0.34f && output[13230] == 0.17f,
            "feedback repeats at exact interval and decays geometrically");
    require(energy(output) > 0 && effects.stats().tail_peak > 0, "delay reports surviving tail");
    effects.reset();
    std::fill(output.begin(), output.end(), 0.0f);
    process(effects, output, 1024);
    require(energy(output) == 0 && effects.stats().tail_peak == 0, "reset clears delay tail");
    require(effects.parameters().feedback == 0.5f, "reset preserves settings");
}

void independent_stages() {
    const auto source = signal(12000);
    for (unsigned stage = 0; stage < 6; ++stage) {
        fmer::Effects effects;
        fmer::EffectParameters p;
        switch (static_cast<fmer::EffectKind>(stage)) {
        case fmer::EffectKind::filter: p.cutoff_hz = 200; break;
        case fmer::EffectKind::reverb: p.reverb = 0.5f; break;
        case fmer::EffectKind::delay: p.delay = 0.5f; p.delay_ms = 30; break;
        case fmer::EffectKind::drive: p.drive = 0.5f; break;
        case fmer::EffectKind::chorus: p.chorus = 0.5f; break;
        case fmer::EffectKind::phaser: p.phaser = 0.5f; break;
        }
        require(effects.set_parameters(p), "each individual stage validates");
        auto output = source;
        process(effects, output, 77);
        require(output != source && energy(output) > 0.001, "every named stage changes audible samples");
        if (stage == static_cast<unsigned>(fmer::EffectKind::filter))
            require(energy(output, 1000) < energy(source, 1000) * 0.15,
                    "low cutoff attenuates independently generated high frequencies");
    }
}

void reverb_tail_and_decay() {
    fmer::EffectParameters p;
    p.reverb = 1; p.reverb_decay = 0.8f;
    fmer::Effects effects;
    effects.set_parameters(p);
    std::vector<float> output(44100 * 6);
    output[0] = 1;
    process(effects, output, 255);
    require(energy(output, 1000, 12000) > 0.0001, "reverb impulse has dispersed early tail");
    require(energy(output, 44100, 88200) > 0, "reverb has a decaying late tail");
    require(energy(output, 44100 * 5) < energy(output, 44100, 88200) * 0.001,
            "reverb tail decays rather than building or holding");
    require(effects.stats().clipped_samples == 0, "small reverb impulse remains unclipped");
}

void deterministic_chunks_and_reorder() {
    fmer::Effects a, b;
    auto p = all_effects();
    a.set_parameters(p); b.set_parameters(p);
    auto x = signal(88213), y = x;
    process(a, x, x.size()); process(b, y, 17);
    require(x == y, "all six stages independent of host block sizes");
    a.reset(); b.reset();
    std::reverse(p.order.begin(), p.order.end());
    b.set_parameters(p);
    x = signal(40000); y = x;
    process(a, x, 64); process(b, y, 64);
    require(x != y, "changing effect order changes actual DSP routing");
    require(energy(x) > 0 && energy(y) > 0, "both orders produce valid audible output");
}

void atomic_validation() {
    fmer::Effects a, b;
    const auto good = all_effects();
    a.set_parameters(good); b.set_parameters(good);
    auto prefix_a = signal(999), prefix_b = prefix_a;
    process(a, prefix_a, 999); process(b, prefix_b, 999);
    auto invalid = good;
    invalid.drive = 0.9f; invalid.delay_ms = std::numeric_limits<float>::quiet_NaN();
    require(!a.set_parameters(invalid), "NaN rejects complete settings transaction");
    invalid = good; invalid.feedback = 0.851f;
    require(!a.set_parameters(invalid), "unstable feedback proposal rejected");
    invalid = good; invalid.order[0] = invalid.order[1];
    require(!a.set_parameters(invalid), "duplicate stage rejected");
    invalid = good; invalid.order[1] = static_cast<fmer::EffectKind>(255);
    require(!a.set_parameters(invalid), "unknown stage rejected");
    invalid = good; invalid.phaser_rate_hz = std::numeric_limits<float>::infinity();
    require(!a.set_parameters(invalid), "infinity rejected");
    require(!a.init(48000), "unsupported clock refused without resetting live state");
    auto x = signal(33000), y = x;
    process(a, x, 41); process(b, y, 1000);
    require(x == y, "failed settings and init preserve parameters plus every DSP state");
    require(a.parameters().drive == good.drive && a.stats().rejected_parameters == 6,
            "atomic refusal counted with unchanged valid values");
}

void full_validation_matrix() {
    using P = fmer::EffectParameters;
    struct Field { float P::*member; float lo; float hi; };
    const std::array<Field, 14> fields{{
        {&P::drive, 0, 1}, {&P::chorus, 0, 1}, {&P::delay, 0, 1},
        {&P::delay_ms, 20, 1000}, {&P::feedback, 0, 0.85f}, {&P::reverb, 0, 1},
        {&P::cutoff_hz, 20, 20000}, {&P::phaser, 0, 1}, {&P::chorus_rate_hz, 0.1f, 1},
        {&P::chorus_depth, 0, 1}, {&P::phaser_rate_hz, 0.5f, 6},
        {&P::phaser_depth, 0, 1}, {&P::reverb_decay, 0, 1}, {&P::resonance, 0, 1}}};
    fmer::Effects effects;
    for (const auto field : fields) {
        for (float value : {field.lo, field.hi}) {
            P p; p.*(field.member) = value;
            require(effects.set_parameters(p), "parameter bounds accepted");
        }
        for (float value : {std::nextafter(field.lo, -std::numeric_limits<float>::infinity()),
                            std::nextafter(field.hi, std::numeric_limits<float>::infinity()),
                            std::numeric_limits<float>::quiet_NaN(),
                            std::numeric_limits<float>::infinity()}) {
            P p; p.*(field.member) = value;
            require(!effects.set_parameters(p), "all out-of-range and nonfinite values refused");
        }
    }
}

void disable_clears_tail() {
    fmer::Effects effects;
    const auto enabled = all_effects();
    effects.set_parameters(enabled);
    auto x = signal(12000);
    process(effects, x, 64);
    effects.set_parameters({});
    require(effects.stats().tail_peak == 0, "disabled stages have no pending tail");
    effects.set_parameters(enabled);
    std::fill(x.begin(), x.end(), 0.0f);
    process(effects, x, 64);
    require(energy(x) == 0, "reenabling an effect cannot resurrect stale notes");
}

void extremes_no_allocations_and_sanitize() {
    fmer::Effects effects;
    auto p = all_effects();
    p.drive = p.chorus = p.delay = p.reverb = p.phaser = 1;
    p.chorus_depth = p.phaser_depth = p.reverb_decay = 1;
    p.chorus_rate_hz = 1; p.phaser_rate_hz = 6;
    p.delay_ms = 20; p.feedback = 0.85f; p.cutoff_hz = 20;
    std::vector<float> output(44100 * 8);
    for (std::size_t i = 0; i < output.size(); ++i) output[i] = (i % 100) < 50 ? 1.0f : -1.0f;
    const auto allocation_count = allocations;
    const bool accepted = effects.set_parameters(p);
    process(effects, output, 31);
    const auto stats = effects.stats();
    effects.reset();
    const bool allocated = allocations != allocation_count;
    require(accepted && !allocated, "settings, process, stats and reset allocate no C++ memory");
    require(energy(output) > 0 && stats.sanitized_samples == 0,
            "maximum feedback/modulation extreme is stable for eight-second audio run");
    // Exercise the longest delay as well as the shortest; do not infer target timing.
    p.delay_ms = 1000; p.cutoff_hz = 19999;
    effects.set_parameters(p);
    std::fill(output.begin(), output.end(), 0.0f); output[0] = 1;
    process(effects, output, 499);
    require(energy(output) > 0 && effects.stats().sanitized_samples == 0,
            "maximum one-second delay remains finite at maximum feedback");
    effects.reset(); effects.set_parameters({});
    std::array<float, 5> bad{{std::numeric_limits<float>::quiet_NaN(),
        std::numeric_limits<float>::infinity(), -std::numeric_limits<float>::infinity(),
        3.0f, -3.0f}};
    effects.process(bad.data(), bad.size());
    require(bad == std::array<float, 5>{{0, 0, 0, .98f, -.98f}}, "invalid input sanitized and oversized input clamped");
    effects.process(nullptr, 0); effects.process(nullptr, 1);
    const auto final_stats = effects.stats();
    require(final_stats.sanitized_samples == 3 && final_stats.clipped_samples == 2 &&
            final_stats.guarded_samples == 2 && final_stats.peak_output == .98f &&
            final_stats.rejected_buffers == 1 && final_stats.processed_frames == 5,
            "diagnostics distinguish sanitation, clipping and invalid buffer");
}

void reordered_extremes() {
    fmer::Effects effects;
    auto p = all_effects();
    p.drive = p.chorus = p.delay = p.reverb = p.phaser = 1;
    p.chorus_depth = p.phaser_depth = p.reverb_decay = 1;
    p.chorus_rate_hz = 1; p.phaser_rate_hz = 6;
    p.delay_ms = 20; p.feedback = 0.85f; p.cutoff_hz = 19999;
    std::vector<float> source(44100), output(source.size());
    std::uint32_t noise = 0x419315u;
    for (std::size_t i = 0; i < source.size(); ++i) {
        noise = noise * 1664525u + 1013904223u;
        source[i] = (noise >> 31) ? 1.0f : -1.0f;
    }
    // Move every stage through all positions, in both directions. Full-scale
    // broadband input with an open filter exposes overshoot that a low cutoff
    // would hide. This checks bounded behavior, not perceptual sound quality.
    for (unsigned order = 0; order < 12; ++order) {
        if (order == 6) std::reverse(p.order.begin(), p.order.end());
        std::rotate(p.order.begin(), p.order.begin() + 1, p.order.end());
        effects.reset();
        require(effects.set_parameters(p), "all extreme routing permutations validate");
        std::copy(source.begin(), source.end(), output.begin());
        process(effects, output, 127);
        energy(output);
        require(effects.stats().sanitized_samples == 0,
                "extreme reordered full-band chains never create nonfinite state");
    }
}

void lazy_clear_matches_fresh_state() {
    fmer::Effects used, fresh;
    auto enabled = all_effects();
    enabled.delay_ms = 1000;
    used.set_parameters(enabled); fresh.set_parameters(enabled);
    // Fill/wrap every ring, then ensure logical reset cannot resurrect old
    // samples later when a long delay's read cursor reaches untouched storage.
    auto warm = signal(100003);
    process(used,warm,137);
    used.reset();
    require(used.stats().tail_peak == 0, "lazy invalidation hides all old ring state");
    auto input = signal(97003), expected = input;
    process(used,input,113); process(fresh,expected,269);
    require(input == expected, "reset wrapped rings is sample-identical to fresh storage through refilling");
    used.set_parameters({}); fresh.set_parameters({});
    used.set_parameters(enabled); fresh.set_parameters(enabled);
    input = signal(100011); expected = input;
    process(used,input,71); process(fresh,expected,512);
    require(input == expected, "disable/re-enable invalidates every ring independently without old-tail revival");
}

void reset_then_parameter_restore_matches_fresh() {
    // Exercise the native import path: reset, optional repeated reset, then
    // parameter publication before the first rendered sample. Coefficients
    // may be reused, but new cutoff/decay/model values must take effect now.
    fmer::Effects used;
    auto warm = signal(6001);
    for(unsigned scenario=0;scenario<8;++scenario) {
        auto old=all_effects();old.cutoff_hz=1234;old.reverb_decay=.61f;
        require(used.set_parameters(old),"pre-restore effect parameters accepted");
        process(used,warm,127);
        used.reset();used.reset();
        auto requested=old;
        switch(scenario) {
        case 1:requested.cutoff_hz=20;break;
        case 2:requested.cutoff_hz=20000;break;
        case 3:requested.reverb_decay=0;break;
        case 4:requested.reverb_decay=1;break;
        case 5:requested.reverb_model=fmer::ReverbModel::plate;break;
        case 6:requested.reverb=0;requested.delay=0;break;
        case 7:requested.reverb_model=fmer::ReverbModel::plate;requested.reverb_decay=1;
               requested.cutoff_hz=20;requested.filter_mode=fmer::FilterMode::band_pass;break;
        default:break;
        }
        auto bad=requested;bad.reverb_decay=1.01f;
        require(!used.set_parameters(bad),"invalid restore cannot publish coefficients");
        require(used.set_parameters(requested) && used.set_parameters(requested),
                "repeated restore parameter publication accepted before processing");
        fmer::Effects fresh;
        require(fresh.set_parameters(requested),"fresh restore reference accepted");
        require(used.stats().tail_peak==0,"reset discards tails while retaining coefficient cache");
        auto actual=signal(50003),expected=actual;
        const auto before=allocations;
        process(used,actual,113);process(fresh,expected,269);
        require(allocations==before,"restored coefficient processing allocates no memory");
        require(std::memcmp(actual.data(),expected.data(),actual.size()*sizeof(float))==0,
                "reset/parameter restore matches fresh-instance PCM bits across coefficient boundaries");
    }
}

void four_reverb_characters(){
    std::array<double,4> energy_by_model{};
    for(unsigned model=0;model<4;++model){
        fmer::Effects e;fmer::EffectParameters p;p.reverb=1;p.reverb_decay=1;p.reverb_model=static_cast<fmer::ReverbModel>(model);
        require(e.set_parameters(p),"all four reverb characters accepted");
        auto x=std::vector<float>(44100*12,0.f);x[0]=.25f;
        const auto count=allocations;process(e,x,128);
        require(allocations==count && e.stats().sanitized_samples==0,"new long reverbs allocate nothing and remain finite");
        energy_by_model[model]=energy(x);
        require(energy_by_model[model]>.0625,"every model has an audible return beyond the dry impulse");
        for(float v:x)require(std::isfinite(v) && std::abs(v)<=.98f,"reverb output respects final guard");
        e.reset();std::fill(x.begin(),x.end(),0);process(e,x,128);require(energy(x)==0,"reset removes every new tail");
    }
    for(unsigned a=0;a<4;++a)for(unsigned b=a+1;b<4;++b)require(std::abs(energy_by_model[a]-energy_by_model[b])>1e-6,"four characters have distinct impulse responses");
}
} // namespace

int main() {
    try {
        {fmer::Effects e;std::vector<float> a(128,0);e.process(a.data(),a.size());
         for(auto v:e.activity())require(v==0,"silence produces no fake FX activity");
         fmer::EffectParameters p;p.delay=1;p.delay_ms=20;p.feedback=.5f;e.set_parameters(p);
         bool seen=false;
         for(unsigned b=0;b<100;++b){std::fill(a.begin(),a.end(),0);if(b==0)a[0]=.5f;
             e.process(a.data(),a.size());seen|=e.activity()[2]>.001f;
             for(unsigned i=0;i<6;++i)if(i!=2)require(e.activity()[i]==0,"only contributing FX stage lights");}
         require(seen,"delay activity sees an actual echo with silent input");
         e.set_parameters({});for(auto v:e.activity())require(v==0,"bypass clears all indicators");}
        four_reverb_characters();exact_bypass(); finite_guard_contract(); final_guard(); delay_impulse_and_feedback(); independent_stages();
#if defined(FMER_DEVICE)
        target_phaser_reference_accuracy();
#endif
        reverb_tail_and_decay(); deterministic_chunks_and_reorder(); atomic_validation();
        full_validation_matrix(); disable_clears_tail(); extremes_no_allocations_and_sanitize();
        reordered_extremes();
        lazy_clear_matches_fresh_state();
        reset_then_parameter_restore_matches_fresh();
        compact_delay_accuracy_and_duration(); compact_delay_quiet_tail_and_no_limit_cycles();
        fdn_models_and_filter_response(); delay_time_edits_and_voicing(); compact_delay_preserves_internal_headroom();
        optional_stage_host_profile();
        std::cout << "effects: 20 groups passed; exact bypass, IEEE finite guards, six audible stages, timed echoes, "
            "tails/reset, chunk determinism, reorder, atomic validation, extrema and no allocations; "
            << fmer::Effects::storage_bytes() << " bytes implementation storage\n";
        return EXIT_SUCCESS;
    } catch (const std::exception& error) {
        std::cerr << "effects failure: " << error.what() << '\n';
        return EXIT_FAILURE;
    }
}
