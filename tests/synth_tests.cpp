#include "synth.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <new>
#include <stdexcept>
#include <string>
#include <vector>
#include "../third_party/msfa/src/synth.h"
#include "../third_party/msfa/src/controllers.h"
#include "../third_party/msfa/src/dx7note.h"
#include "../third_party/msfa/src/lfo.h"
#include "../third_party/msfa/src/sin.h"
#include "../third_party/msfa/src/fm_op_kernel.h"
#undef N
#undef LG_N

// An observable allocation counter around only the bounded musical paths.
// Test vectors and Synth construction happen outside the measured interval.
std::size_t synth_test_allocations{};
void* operator new(std::size_t size) {
    ++synth_test_allocations;
    if(void* pointer=std::malloc(size?size:1))return pointer;
    throw std::bad_alloc();
}
void* operator new[](std::size_t size) { return ::operator new(size); }
void operator delete(void* pointer) noexcept { std::free(pointer); }
void operator delete[](void* pointer) noexcept { std::free(pointer); }
void operator delete(void* pointer,std::size_t) noexcept { std::free(pointer); }
void operator delete[](void* pointer,std::size_t) noexcept { std::free(pointer); }

namespace {
void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

fmer::Patch quick_patch() {
    auto patch = fmer::make_init_patch();
    for (std::size_t op = 0; op < 6; ++op) patch.vced[op * 21 + 3] = 99;
    return patch;
}

std::vector<float> render(fmer::Synth& synth, std::size_t count, std::size_t chunk = 512) {
    std::vector<float> output(count);
    for (std::size_t i = 0; i < count; i += chunk)
        synth.render(output.data() + i, std::min(chunk, count - i));
    return output;
}

double energy(const std::vector<float>& samples) {
    double total = 0;
    for (float value : samples) {
        require(std::isfinite(value), "render must be finite");
        require(std::abs(value) <= 1.0f, "output must remain in float audio range");
        total += value * value;
    }
    return total;
}

double frequency(const std::vector<float>& samples) {
    std::size_t crossings = 0;
    for (std::size_t i = 1; i < samples.size(); ++i)
        if (samples[i - 1] <= 0 && samples[i] > 0) ++crossings;
    return crossings * 44100.0 / samples.size();
}

void basics_and_pitch() {
    fmer::Synth synth;
    require(synth.init(), "native sample rate accepted");
    require(!synth.init(48000), "unsupported rate must be refused");
    require(energy(render(synth, 257)) == 0, "initial silence");
    require(synth.set_patch(quick_patch()), "valid patch accepted");
    synth.note_on(0, 69, 110);
    render(synth, 4096);
    auto tone = render(synth, 16384);
    require(energy(tone) > 0.01, "actual audible FM signal");
    require(std::abs(frequency(tone) - 440.0) < 4.0, "INIT ratio oscillator A4 near 440Hz");
    synth.pitch_bend(0, 16383);
    render(synth, 128);
    tone = render(synth, 16384);
    require(std::abs(frequency(tone) - 523.25) < 4.0, "MSFA positive bend is three semitones");
    synth.panic();
    require(energy(render(synth, 63)) == 0, "panic clears queued voice block immediately");
    require(synth.stats().active_voices == 0, "panic frees voices");
}

void direct_msfa_reference() {
    // Compare the host adapter with a separate, direct MSFA invocation. This
    // verifies packing, transpose, LFO, controllers and gain at the boundary;
    // it is deliberately not a claim of independent hardware sound matching.
    fmer::Synth synth;
    auto patch = quick_patch();
    patch.vced[144] = 36;
    patch.vced[139] = 45;
    patch.vced[143] = 5;
    synth.set_patch(patch);
    synth.note_on(0, 60, 103);
    const auto actual = render(synth, 4096, 19);
    std::array<char, 156> expanded{};
    for (std::size_t i = 0; i < patch.vced.size(); ++i)
        expanded[i] = static_cast<char>(patch.vced[i]);
    expanded[155] = 0x3f;
    Dx7Note reference{};
    Lfo lfo{};
    Controllers controls{};
    controls.values_[kControllerPitch] = 8192;
    reference.init(expanded.data(), 72, 103);
    lfo.reset(expanded.data() + 137);
    lfo.keydown();
    for (std::size_t i = 0; i < actual.size(); i += 64) {
        std::array<std::int32_t, 64> block{};
        reference.compute(block.data(), lfo.getsample(), lfo.getdelay(), &controls);
        for (std::size_t j = 0; j < block.size(); ++j) {
            const float expected = std::clamp(static_cast<float>(block[j]) *
                (0.15f / 16777216.0f), -1.0f, 1.0f);
            require(actual[i + j] == expected, "adapter matches direct MSFA reference samples");
        }
    }
}

std::int32_t sine_reference64(std::uint32_t phase) {
    const auto index=(phase>>13)&2046u;
    return static_cast<std::int32_t>(sintab[index+1]+
        ((static_cast<std::int64_t>(sintab[index])*(phase&16383u))>>14));
}

void exhaustive_sine_and_kernel_reference() {
    fmer::Synth initialize;
    std::int32_t maximum_delta=0;
    for(unsigned i=0;i<1024;++i)maximum_delta=std::max(maximum_delta,std::abs(sintab[2*i]));
    require(maximum_delta==102943 && static_cast<std::int64_t>(maximum_delta)*16383==1686515169,
            "pinned sine table proves signed32 interpolation product bound");
    for(std::uint32_t phase=0;phase<(1u<<24);++phase)
        require(Sin::lookup(static_cast<std::int32_t>(phase))==sine_reference64(phase),
                "every24-bit phase preserves original64-bit sine interpolation exactly");
    std::uint32_t random=0x719719u;
    const auto next=[&](){random=random*1664525u+1013904223u;return random;};
    for(unsigned trial=0;trial<128;++trial)for(unsigned kind=0;kind<3;++kind)for(bool add:{false,true}) {
        std::array<std::int32_t,64> input{},actual{},expected{};
        for(unsigned i=0;i<64;++i) {input[i]=static_cast<std::int32_t>(next());actual[i]=expected[i]=static_cast<std::int32_t>(next());}
        const auto phase0=next()&0xffffffu,freq=next()&0xffffffu;
        const auto gain1=static_cast<std::int32_t>(next()&0x7ffffffu),gain2=static_cast<std::int32_t>(next()&0x7ffffffu);
        const int shift=static_cast<int>(trial%9)+1;
        std::int32_t actual_fb[]{static_cast<std::int32_t>(next()&0xffffu),static_cast<std::int32_t>(next()&0xffffu)};
        std::int32_t previous=actual_fb[0],current=actual_fb[1],gain=gain1;
        const auto delta=(gain2-gain1+32)>>6;
        auto phase=phase0;
        for(unsigned i=0;i<64;++i) {
            gain+=delta;
            std::int32_t modulation=kind==0?input[i]:0;
            if(kind==2) {modulation=(previous+current)>>(shift+1);previous=current;}
            const auto y=sine_reference64(phase+static_cast<std::uint32_t>(modulation));
            const auto sample=(static_cast<std::int64_t>(y)*gain)>>24;
            // The original wide accumulation defines this low32-bit result.
            expected[i]=static_cast<std::int32_t>((add?static_cast<std::int64_t>(expected[i]):0)+sample);
            current=static_cast<std::int32_t>(sample);phase+=freq;
        }
        if(kind==0)FmOpKernel::compute(actual.data(),input.data(),phase0,freq,gain1,gain2,add);
        if(kind==1)FmOpKernel::compute_pure(actual.data(),phase0,freq,gain1,gain2,add);
        if(kind==2)FmOpKernel::compute_fb(actual.data(),phase0,freq,gain1,gain2,actual_fb,shift,add);
        require(actual==expected,"all kernels preserve64-bit reference samples including output wrap");
        if(kind==2)require(actual_fb[0]==previous && actual_fb[1]==current,"feedback state is exact after optimized kernel");
    }
}

void release_and_pedal() {
    fmer::Synth synth;
    synth.set_patch(quick_patch());
    synth.note_on(1, 60, 100);
    render(synth, 4000);
    synth.note_off(1, 60);
    render(synth, 44100);
    require(synth.stats().active_voices == 0, "zero-level release retires voice");
    synth.note_on(1, 64, 100);
    synth.control_change(1, 64, 127);
    synth.note_off(1, 64);
    require(energy(render(synth, 44100)) > 0.01, "pedal sustains audio after note off");
    require(synth.stats().active_voices == 1, "pedal retains bounded voice");
    synth.control_change(1, 64, 0);
    render(synth, 44100);
    require(synth.stats().active_voices == 0, "pedal release releases deferred note");
    synth.note_on(1, 60, 90);
    synth.note_on(1, 60, 0);
    render(synth, 44100);
    require(synth.stats().active_voices == 0, "velocity zero normalizes to off");
}

void ownership_and_stealing() {
    fmer::Synth synth;
    synth.set_patch(quick_patch());
    synth.note_on(0, 60, 100, 1);
    synth.note_on(0, 60, 100, 2);
    synth.note_off(0, 60, 1);
    render(synth, 44100);
    require(synth.stats().active_voices == 1, "source-specific off preserves other owner");
    synth.panic_source(1);
    require(synth.stats().active_voices == 1, "source panic preserves unrelated owner");
    synth.panic_source(2);
    require(synth.stats().active_voices == 0, "source panic clears owner");
    for (std::uint8_t note = 48; note < 60; ++note) synth.note_on(0, note, 100);
    require(synth.stats().active_voices == 12, "twelve voices available");
    synth.note_on(0, 70, 100);
    require(synth.stats().active_voices == 12 && synth.stats().stolen_voices == 1,
        "thirteenth note deterministically steals one voice");
    synth.note_on(0, 70, 100);
    require(synth.stats().retriggers == 1 && synth.stats().active_voices == 12,
        "same-owner retrigger does not allocate another voice");
    synth.control_change(0, 120, 0);
    require(energy(render(synth, 64)) == 0, "channel All Sound Off clears block tails");
}

void chunk_invariance_and_snapshots() {
    fmer::Synth a, b;
    const auto patch = quick_patch();
    a.set_patch(patch); b.set_patch(patch);
    a.note_on(0, 60, 110); b.note_on(0, 60, 110);
    require(render(a, 4099, 4099) == render(b, 4099, 17), "chunk size must not change FM audio");
    auto changed = patch;
    changed.vced[105 + 18] = 3;
    a.set_patch(changed);
    require(render(a, 5031, 123) == render(b, 5031, 1), "held note retains its patch snapshot");
    a.note_off(0, 60); b.note_off(0, 60);
    require(render(a, 8000, 8000) == render(b, 8000, 31), "release block cursor independent of host chunks");
    a.panic(); b.panic();
    a.note_on(0, 60, 110); b.note_on(0, 60, 110);
    require(render(a, 8192) != render(b, 8192), "next note adopts new patch");
}

void algorithms_and_validation() {
    auto patch = quick_patch();
    for (std::size_t op = 0; op < 6; ++op) {
        patch.vced[op * 21 + 16] = 80;
        patch.vced[op * 21 + 18] = static_cast<std::uint8_t>(op + 1);
    }
    for (std::uint8_t algorithm = 0; algorithm < 32; ++algorithm) {
        fmer::Synth a, b;
        patch.vced[134] = algorithm;
        patch.vced[135] = 7;
        require(a.set_patch(patch) && b.set_patch(patch), "all32 algorithms validate");
        a.note_on(0, 60, 100); b.note_on(0, 60, 100);
        const auto x = render(a, 8192, 37), y = render(b, 8192, 1024);
        require(x == y, "feedback state deterministically initialized");
        require(energy(x) > 0.001, "every algorithm produces finite nonzero output");
    }
    fmer::Synth synth;
    auto invalid = quick_patch(); invalid.vced[134] = 32;
    require(!synth.set_patch(invalid), "invalid algorithm rejected before DSP");
    synth.note_on(16, 60, 100);
    synth.pitch_bend(0, 16384);
    synth.render(nullptr, 4);
    require(synth.stats().rejected_events == 4, "invalid input counted without state mutation");
    require(synth.stats().active_voices == 0, "invalid events do not allocate");
    patch.vced[134] = 31;
    for (std::size_t op = 0; op < 6; ++op) {
        patch.vced[op * 21 + 18] = 31;
        patch.vced[op * 21 + 19] = 99;
        patch.vced[op * 21 + 20] = 14;
    }
    for (std::size_t i = 130; i < 134; ++i) patch.vced[i] = 99;
    synth.set_patch(patch);
    synth.note_on(0, 127, 127);
    energy(render(synth, 8192));
}

void va_preview() {
    for (unsigned waveform = 0; waveform < 4; ++waveform) {
        fmer::Synth a, b;
        fmer::VaParameters parameters;
        parameters.waveform = static_cast<fmer::VaWaveform>(waveform);
        parameters.release_ms = 10;
        require(a.set_va_parameters(parameters) && b.set_va_parameters(parameters), "VA settings validate");
        a.set_engine(fmer::SynthEngine::va); b.set_engine(fmer::SynthEngine::va);
        a.note_on(0, 60, 110); b.note_on(0, 60, 110);
        const auto x = render(a, 8192, 51), y = render(b, 8192, 777);
        require(x == y && energy(x) > 0.01, "VA waveforms audible and chunk deterministic");
        a.note_off(0, 60); render(a, 2000);
        require(a.stats().active_voices == 0, "VA release retires voice");
        b.panic(); require(energy(render(b, 17)) == 0, "VA panic immediate");
    }
    fmer::Synth low, high;
    fmer::VaParameters parameters;
    parameters.cutoff_hz = 30;
    parameters.resonance = 0;
    low.set_va_parameters(parameters);
    parameters.cutoff_hz = 15000;
    high.set_va_parameters(parameters);
    low.set_engine(fmer::SynthEngine::va); high.set_engine(fmer::SynthEngine::va);
    low.note_on(0, 69, 127); high.note_on(0, 69, 127);
    render(low, 16000); render(high, 16000);
    require(energy(render(low, 8192)) < energy(render(high, 8192)) * 0.01,
        "VA filter cutoff changes audible spectrum/energy");
    parameters.cutoff_hz = std::nanf("");
    require(!low.set_va_parameters(parameters), "nonfinite VA settings rejected");
}

void bounded_voice_budget() {
    fmer::Synth synth;
    require(synth.voice_budget() == 12, "host keeps12voice default");
    require(!synth.set_voice_budget(0) && !synth.set_voice_budget(13), "invalid budget rejected atomically");
    require(synth.voice_budget() == 12, "refused budget unchanged");
    synth.set_patch(quick_patch());
    for (std::uint8_t note = 60; note < 64; ++note) synth.note_on(0,note,100,1);
    synth.note_off(0,61,1); // released tail outranks even an older held note
    require(synth.set_voice_budget(3), "live budget reduction accepted");
    require(synth.stats().active_voices == 3 && synth.stats().released_voices == 0 &&
            synth.stats().stolen_voices == 1, "budget reduction steals tail first and counts it");
    synth.note_on(0,65,100,2);
    require(synth.stats().active_voices == 3 && synth.stats().stolen_voices == 2,
            "new owner steals within budget instead of halting audio");
    synth.note_off(0,60,1); // oldest held note was stolen, not the new owner
    render(synth,44100);
    require(synth.stats().active_voices == 3, "stolen old owner cannot release replacement");
    require(energy(render(synth,512)) > 0, "budgeted chord keeps sounding");
    synth.set_voice_budget(1);
    require(synth.stats().active_voices == 1 && synth.stats().stolen_voices == 4,
            "reducing to mono retains one voice and records every retirement");
    synth.note_on(0,67,100,3); synth.note_on(0,67,100,3);
    require(synth.stats().active_voices == 1 && synth.stats().retriggers == 1,
            "same-owner retrigger still obeys budget");
    synth.panic(); require(synth.voice_budget() == 1, "panic does not reset overload budget");
}

void mixed_voice_chunk_order() {
    fmer::Synth a, b;
    a.set_patch(quick_patch()); b.set_patch(quick_patch());
    for (auto* synth : {&a,&b}) {
        synth->note_on(1,48,100,1); synth->note_on(2,55,80,2);
        synth->control_change(1,7,89); synth->control_change(2,11,73);
        synth->set_engine(fmer::SynthEngine::va);
        synth->note_on(1,64,110,3);
        synth->note_off(2,55,2);
    }
    require(render(a,12031,12031) == render(b,12031,7),
            "voice-outer block mixing preserves mixed-engine/channel/release chunk order");
}

void va_pitch_extremes() {
    for (unsigned wave = 0; wave < 4; ++wave) for (std::uint8_t note : {36,69,96}) {
        fmer::Synth synth;
        fmer::VaParameters p;
        p.waveform = static_cast<fmer::VaWaveform>(wave);
        p.cutoff_hz = 18000; p.resonance = 0; p.attack_ms = 0; p.decay_ms = 0; p.sustain = 1;
        synth.set_va_parameters(p); synth.set_engine(fmer::SynthEngine::va);
        synth.note_on(0,note,127); render(synth,4096);
        const auto audio = render(synth,44100,127);
        const double expected = 440.0 * std::pow(2.0,(note-69)/12.0);
        require(std::abs(frequency(audio)-expected) < 2.0, "all VA waves retain pitch across the practical keyboard range");
        require(energy(audio) > 0.001, "VA pitch test retains finite audible level");
        synth.pitch_bend(0,16383); render(synth,4096);
        require(std::abs(frequency(render(synth,44100,127))-expected*std::pow(2.0,3.0/12)) < 2.0,
                "VA bend retains documented three-semitone interval");
    }
}

void activity_snapshots() {
    fmer::Synth synth;
    const auto present = [](const std::uint32_t* words, unsigned note) {
        return (words[note / 32] & (std::uint32_t{1} << (note % 32))) != 0;
    };
    require(synth.activity().active_voices == 0, "initial activity is empty");
    for (std::uint8_t note : {0,31,32,63,64,95,96,127}) synth.note_on(0,note,100,1);
    auto state = synth.activity();
    require(state.active_voices == 8, "activity counts actual slots across all mask words");
    for (unsigned word=0; word<4; ++word)
        require(state.active_notes[word] == 0x80000001u && state.gated_notes[word] == 0x80000001u,
                "mask uses unsigned endpoints without pitch folding");
    synth.panic();
    fmer::VaParameters va;
    va.attack_ms=0; va.decay_ms=0; va.sustain=1; va.release_ms=100;
    require(synth.set_engine(fmer::SynthEngine::va) && synth.set_va_parameters(va),"controlled VA release fixture");
    synth.note_on(0,60,100,1); synth.note_on(1,60,100,2); render(synth,128);
    synth.note_off(0,60,1); state=synth.activity();
    require(state.active_voices==2 && present(state.active_notes,60) && present(state.gated_notes,60),
            "same pitch shares a bit while independent owner remains gated");
    synth.note_off(1,60,2); state=synth.activity();
    require(state.active_voices==2 && present(state.active_notes,60) && !present(state.gated_notes,60),
            "released voices remain active but are not gated");
    render(synth,5000); state=synth.activity();
    require(!state.active_voices && !present(state.active_notes,60),"finished release tails disappear without a note event");
    synth.control_change(0,64,127);
    synth.note_on(0,64,100,1); render(synth,128); synth.note_off(0,64,1);
    state=synth.activity();
    require(state.active_voices==1 && present(state.gated_notes,64),"sustain keeps released key gated");
    synth.control_change(0,123,0);
    require(present(synth.activity().gated_notes,64),"CC123 under sustain retains real gated slot");
    synth.note_on(0,67,100,4,false); render(synth,128); synth.note_off(0,67,4);
    state=synth.activity();
    require(present(state.active_notes,67) && !present(state.gated_notes,67) && present(state.gated_notes,64),
            "generated sustain immunity is reflected independently of live held pedal");
    synth.control_change(0,64,0); state=synth.activity();
    require(!present(state.gated_notes,64) && present(state.active_notes,64),"pedal release changes gate before tail retirement");
    synth.panic(); synth.set_voice_budget(4);
    for (std::uint8_t note=60; note<=64; ++note) synth.note_on(0,note,100,1);
    state=synth.activity();
    require(state.active_voices==4 && !present(state.active_notes,60) && present(state.gated_notes,64),
            "oldest stolen held note disappears immediately");
    render(synth,128); synth.note_off(0,61,1); synth.note_on(0,65,100,1);
    state=synth.activity();
    require(!present(state.active_notes,61) && present(state.gated_notes,65),"stealing a tail updates mask before rendering");
    synth.set_voice_budget(2); state=synth.activity();
    require(state.active_voices==2 && !present(state.active_notes,62) && !present(state.active_notes,63) &&
            present(state.active_notes,64) && present(state.active_notes,65),"budget reduction removes exact retired pitches");
    synth.panic(); synth.note_on(0,72,100,1); synth.note_on(1,72,100,2);
    synth.panic_source(1); state=synth.activity();
    require(state.active_voices==1 && present(state.gated_notes,72),"source panic preserves overlapping surviving owner");
    synth.control_change(1,120,0); state=synth.activity();
    require(!state.active_voices && !present(state.active_notes,72),"channel all sound off retires mask immediately");
    synth.note_on(0,76,100,1); synth.panic(); state=synth.activity();
    require(!state.active_voices && !present(state.active_notes,76) && !present(state.gated_notes,76),"panic clears both masks");
    // Ownership pitch deliberately does not pretend to be an audio-frequency meter.
    auto patch=fmer::make_init_patch(); patch.vced[144]=36; synth.set_patch(patch);
    synth.note_on(0,60,100,1); synth.pitch_bend(0,16383); state=synth.activity();
    require(present(state.active_notes,60) && !present(state.active_notes,72),"patch transpose and bend do not relabel input note identity");
    fmer::Synth reference,observed;
    for (auto* s : {&reference,&observed}) {
        s->set_engine(fmer::SynthEngine::va); s->set_va_parameters(va); s->note_on(0,69,100,1);
    }
    const auto counters=observed.stats();
    for(unsigned i=0;i<1024;++i) require(observed.activity().active_voices==1,"repeated read-only snapshot retains note");
    const auto after=observed.stats();
    require(after.rendered_frames==counters.rendered_frames && after.note_ons==counters.note_ons &&
            after.note_offs==counters.note_offs && after.stolen_voices==counters.stolen_voices,
            "activity getter leaves time and counters unchanged");
    require(render(reference,2048)==render(observed,2048),"activity inspection leaves subsequent PCM unchanged");
}

void va_vibrato_and_generated_sustain() {
    fmer::VaParameters p;
    p.waveform=fmer::VaWaveform::sine; p.cutoff_hz=18000; p.resonance=0;
    p.attack_ms=0; p.decay_ms=0; p.sustain=1; p.release_ms=0;
    p.lfo_rate_hz=1; p.lfo_depth_cents=100;
    fmer::Synth a,b,dry;
    for(auto* s:{&a,&b,&dry}) { s->set_engine(fmer::SynthEngine::va); require(s->set_va_parameters(p),"vibrato parameters validate"); }
    p.lfo_depth_cents=0; dry.set_va_parameters(p);
    a.note_on(0,69,127); b.note_on(0,69,127); dry.note_on(0,69,127);
    const auto modulated=render(a,44100,31), reference=render(b,44100,777), unmodulated=render(dry,44100,63);
    require(modulated==reference && modulated!=unmodulated,"VA vibrato is audible and sample/chunk deterministic");
    const auto peak=std::vector<float>(modulated.begin()+6615,modulated.begin()+15435);
    const auto trough=std::vector<float>(modulated.begin()+28665,modulated.begin()+37485);
    require(frequency(peak)>=460 && frequency(trough)<=425,"100cent vibrato moves pitch above and below dry440Hz");
    energy(modulated);
    p.lfo_rate_hz=std::nanf(""); require(!a.set_va_parameters(p),"nonfinite vibrato rate rejected");
    p.lfo_rate_hz=.1f;p.lfo_depth_cents=100.01f;require(!a.set_va_parameters(p),"out-of-range vibrato depth rejected");
    p.lfo_depth_cents=100;require(a.set_va_parameters(p),"minimum vibrato rate accepted exactly");
    // A controller sustain pedal belongs to live input, not sequencer gates.
    a.panic(); a.control_change(0,64,127);
    a.note_on(0,60,100,1); a.note_on(0,64,100,4,false);
    render(a,128); a.note_off(0,60,1); a.note_off(0,64,4); render(a,1);
    require(a.stats().active_voices==1,"generated gate ignores pedal without changing live sustain");
    a.control_change(0,64,0);render(a,1);require(a.stats().active_voices==0,"live sustain still releases normally");
    a.control_change(0,64,127);a.note_on(0,60,100,1);a.note_on(0,64,100,5,false);
    render(a,128);a.control_change(0,123,0);render(a,1);
    require(a.stats().active_voices==1,"CC123 honors sustain immunity as well as source NoteOff");
    a.panic();
}

std::vector<float> direct_amplitude_fixture(unsigned sensitivity,unsigned depth,
                                          std::int32_t lfo,std::int32_t delay) {
    auto patch=quick_patch();
    patch.vced[105+14]=static_cast<std::uint8_t>(sensitivity);
    patch.vced[140]=static_cast<std::uint8_t>(depth);
    std::array<char,156> raw{};
    for(std::size_t i=0;i<155;++i)raw[i]=static_cast<char>(patch.vced[i]);
    raw[155]=0x3f;
    Dx7Note note{};note.init(raw.data(),69,100);
    Controllers controllers{};controllers.values_[kControllerPitch]=8192;
    std::vector<float> audio(8192);
    for(std::size_t offset=0;offset<audio.size();offset+=64){
        std::array<std::int32_t,64> block{};
        note.compute(block.data(),lfo,delay,&controllers);
        for(std::size_t i=0;i<64;++i)audio[offset+i]=block[i]*(0.15f/16777216.0f);
    }
    // Ignore the envelope attack and one gain-interpolation block. The steady
    // sinusoid is an independent amplitude-ratio oracle, not a DSP golden hash.
    return {audio.begin()+4096,audio.end()};
}

void fm_amplitude_modulation() {
    fmer::Synth initialize_tables;
    constexpr std::int32_t unity=1<<24;
    const auto dry=direct_amplitude_fixture(0,99,unity,unity);
    const double dry_energy=energy(dry);
    require(dry==direct_amplitude_fixture(3,0,unity,unity),"AMD zero is exactly the pre-modulation signal");
    require(dry==direct_amplitude_fixture(3,99,unity,0),"LFO delay zero bypasses amplitude modulation exactly");
    require(dry==direct_amplitude_fixture(3,99,0,unity),"LFO zero applies no amplitude attenuation");
    const double expected_amplitude[]={1.0,.5,.25,.0625};
    for(unsigned sensitivity=0;sensitivity<4;++sensitivity){
        const auto audio=direct_amplitude_fixture(sensitivity,99,unity,unity);
        const double ratio=std::sqrt(energy(audio)/dry_energy);
        require(std::abs(ratio-expected_amplitude[sensitivity])<.001,
                "AMS0/1/2/3 peak ratios are unity/half/quarter/sixteenth at full AMD");
    }
    require(std::abs(std::sqrt(energy(direct_amplitude_fixture(3,99,unity,unity/2))/dry_energy)-.25)<.001,
            "half-risen LFO delay reaches halfway attenuation in decibels");
    // Exercise the real LFO and Synth adapter as well as the constant-control
    // oracle. Carrier AMS gives tremolo, modulator AMS changes timbre.
    for(bool carrier : {false,true}) {
        auto patch=quick_patch();
        patch.vced[84+16]=76;patch.vced[84+18]=2;
        patch.vced[(carrier?105:84)+14]=3;
        patch.vced[140]=99;patch.vced[137]=50;patch.vced[142]=4;
        fmer::Synth modulated,chunked,unmodulated;
        modulated.set_patch(patch);chunked.set_patch(patch);
        patch.vced[140]=0;unmodulated.set_patch(patch);
        for(auto* s:{&modulated,&chunked,&unmodulated})s->note_on(0,60,100);
        const auto a=render(modulated,44100,17),b=render(chunked,44100,256),dry_audio=render(unmodulated,44100,64);
        require(a==b && a!=dry_audio && energy(a)>.01,"carrier and modulator AMS audibly work with deterministic chunking");
        modulated.note_off(0,60);render(modulated,44100);
        require(modulated.stats().active_voices==0,"amplitude modulation leaves envelope release retirement intact");
    }
}
}

void live_program_lfo_gate() {
    for(auto engine:{fmer::SynthEngine::fm,fmer::SynthEngine::va}) {
        fmer::Synth gated,zero,continuous;
        auto patch=quick_patch();patch.vced[139]=70;patch.vced[143]=5;patch.vced[137]=60;
        fmer::VaParameters va;va.lfo_depth_cents=70;va.sustain=.8f;
        for(auto* s:{&gated,&zero,&continuous}){s->set_patch(patch);s->set_va_parameters(va);s->set_engine(engine);}
        auto dry_patch=patch;dry_patch.vced[139]=0;zero.set_patch(dry_patch);
        auto dry_va=va;dry_va.lfo_depth_cents=0;zero.set_va_parameters(dry_va);
        gated.set_lfo_enabled(false);
        for(auto* s:{&gated,&zero,&continuous})s->note_on(0,60,100);
        const auto a=render(gated,22050,17),b=render(zero,22050,73),c=render(continuous,22050,256);
        require(a==b && a!=c,"off gate exactly removes program modulation while preserving dry voice");
        gated.set_lfo_enabled(true);
        const auto enabled=render(gated,22050,17),dry=render(zero,22050,73);
        require(enabled!=dry && gated.stats().active_voices==1 && !gated.stats().retriggers,
                "enabling LFO changes a held note without retriggering or reallocating it");
        gated.set_lfo_enabled(false);render(gated,4410);gated.note_off(0,60);render(gated,44100*2);
        require(!gated.stats().active_voices,"live LFO gate preserves release retirement");
    }
}

void four_reserved_parts() {
    fmer::Synth synth, reference;
    fmer::PartParameters p;
    p.patch=quick_patch();p.va.attack_ms=0;p.va.decay_ms=0;p.va.sustain=1;p.va.release_ms=5;
    for(auto* s:{&synth,&reference}) {
        require(s->set_voice_budget(4) && s->set_parts_enabled(true),"four-voice parts mode admitted");
        for(std::uint8_t part=0;part<4;++part) {
            p.engine=part%2?fmer::SynthEngine::va:fmer::SynthEngine::fm;
            p.va.waveform=part==1?fmer::VaWaveform::sine:fmer::VaWaveform::saw;
            p.patch.vced[105+18]=part==2?3:1;
            require(s->configure_part(part,p),"independent FM/VA instrument snapshots accepted");
            s->part_note_on(part,0,60,100,4);
        }
    }
    require(synth.stats().active_voices==4 && synth.stats().peak_voices==4,"four parts use exactly four voices");
    require(render(synth,4099,7)==render(reference,4099,71),"mixed FM/VA parts are chunk invariant");
    p.patch.vced[105+18]=7;
    require(synth.configure_part(0,p),"replacement part instrument accepted");
    require(render(synth,3017,13)==render(reference,3017,256),"configuring one part preserves all held snapshots");
    const auto before=synth.stats().rejected_events;
    synth.note_on(0,72,100,9);require(!synth.set_voice_budget(3),"reservation refuses undersized budget");
    require(synth.stats().active_voices==4 && synth.stats().rejected_events==before+2,"unrouted notes cannot steal tracks");
    synth.note_off(0,60,4);
    require(synth.stats().released_voices==0,"standalone off cannot release any part");
    synth.part_note_off(1,0,60,8);
    require(synth.stats().released_voices==0,"wrong source off cannot release a part");
    synth.part_note_off(1,0,60,4);render(synth,2000);
    require(synth.stats().active_voices==3 && !synth.part_activity(1).active_voices && synth.part_activity(0).active_voices==1,
            "part-specific off preserves same pitch and source in other parts");
    synth.part_note_on(2,0,64,100,9);synth.part_note_off(2,0,60,4);
    require(synth.part_activity(2).gated_notes[2]&1u,"stale off cannot release replacement owner on same part");
    synth.panic_part(2);require(synth.stats().active_voices==2,"part panic leaves other parts playing");
    synth.panic_source(4);require(!synth.stats().active_voices,"source panic clears its remaining parts");
    require(synth.set_parts_enabled(false),"standalone mode restored");synth.note_on(0,69,100);
    require(synth.stats().active_voices==1,"standalone engine remains usable after parts mode");
    synth.panic();synth.set_voice_budget(3);
    require(!synth.set_parts_enabled(true),"parts mode never silently exceeds device voice budget");
}

void part_mixer_and_validation() {
    fmer::Synth a,b;
    fmer::PartParameters p;p.engine=fmer::SynthEngine::va;p.va.waveform=fmer::VaWaveform::sine;
    p.va.attack_ms=0;p.va.decay_ms=0;p.va.sustain=1;p.va.release_ms=10;
    for(auto* s:{&a,&b}) {s->configure_part(0,p);s->set_parts_enabled(true);s->part_note_on(0,0,69,100,4);}
    require(render(a,4096)==render(b,4096),"default unity mixer preserves dry signal");
    a.set_part_mix(0,.5f,false);render(a,4096);render(b,4096);
    require(std::abs(std::sqrt(energy(render(a,4096))/energy(render(b,4096)))-.5)<.001,
            "part level settles to the displayed linear amplitude gain");
    a.set_part_mix(0,.5f,true);render(a,4096);
    require(energy(render(a,4096))==0 && a.part_activity(0).active_voices==1,"mute silences output without forgetting ownership");
    a.part_note_off(0,0,69,4);render(a,1000);a.set_part_mix(0,.5f,false);
    require(!a.part_activity(0).active_voices && energy(render(a,128))==0,"note off while muted retires normally and unmute cannot revive it");
    require(!a.configure_part(4,p) && !a.set_part_mix(4,1,false) && !a.set_part_mix(0,std::nanf(""),false) &&
            !a.set_part_mix(0,1.01f,false),"invalid mix and part indices are rejected");
    p.patch.vced[134]=32;require(!a.configure_part(0,p),"invalid part patch is rejected atomically");
    p.patch=quick_patch();p.va.cutoff_hz=std::nanf("");require(!a.configure_part(0,p),"invalid VA part parameters are rejected");
    fmer::GlideParameters glide;glide.time_ms=5001;require(!a.set_glide(glide),"out-of-range glide time rejected");
    glide.time_ms=std::nanf("");require(!a.set_glide(glide),"nonfinite glide time rejected");
    glide.time_ms=500;glide.mode=static_cast<fmer::GlideMode>(3);require(!a.set_glide(glide),"invalid glide mode rejected");
    glide.mode=fmer::GlideMode::always;glide.contour=static_cast<fmer::GlideContour>(3);
    require(!a.set_glide(glide),"invalid glide contour rejected");
}

void part_mixer_matches_sample_recurrence() {
    // A separate dry voice plus the documented gain recurrence is the oracle.
    // It exercises both the settling transition and long stable regions; the
    // reference never uses the part mixer or its optimized stable branch.
    for(unsigned family=0;family<5;++family) {
        fmer::Synth part,dry;
        fmer::PartParameters p;p.patch=quick_patch();
        p.engine=family?fmer::SynthEngine::va:fmer::SynthEngine::fm;
        p.va.waveform=static_cast<fmer::VaWaveform>(family?family-1:0);
        p.va.attack_ms=0;p.va.decay_ms=0;p.va.sustain=1;p.va.resonance=0;
        require(part.configure_part(0,p) && part.set_parts_enabled(true),"mixer reference setup");
        dry.set_patch(p.patch);dry.set_engine(p.engine);dry.set_va_parameters(p.va);
        part.part_note_on(0,0,57,83,4);dry.note_on(0,57,83,4);
        std::array<float,257> actual{},reference{};
        float gain=1.f;
        constexpr float levels[]{1.f,.75f,.013f,.8f,1.f};
        constexpr std::size_t chunks[]{1,17,63,64,127,257};
        for(unsigned section=0;section<5;++section) {
            const bool muted=section==3;
            const float target=muted?0.f:levels[section];
            require(part.set_part_mix(0,levels[section],muted),"mix value admitted");
            part.control_change(0,7,section%2?87:127);dry.control_change(0,7,section%2?87:127);
            part.control_change(0,11,section%2?59:127);dry.control_change(0,11,section%2?59:127);
            for(std::size_t offset=0,chunk=0;offset<4000;++chunk) {
                const auto count=std::min<std::size_t>(4000-offset,chunks[chunk%6]);
                part.render(actual.data(),count);dry.render(reference.data(),count);
                for(std::size_t i=0;i<count;++i) {
                    gain+=.004f*(target-gain);
                    if(std::abs(target-gain)<.00001f)gain=target;
                    require(actual[i]==reference[i]*gain,
                            "FM/VA mixer preserves every sample of the independent gain recurrence");
                }
                offset+=count;
            }
            require(gain==target,"test reaches exact stable gain after every ramp");
        }
    }
}

void mono_glide_pitch_and_contours() {
    for(auto engine:{fmer::SynthEngine::fm,fmer::SynthEngine::va}) {
        double centers[3]{};
        for(unsigned shape=0;shape<3;++shape) {
            fmer::Synth a,b;
            fmer::VaParameters va;va.waveform=fmer::VaWaveform::sine;va.attack_ms=0;va.decay_ms=0;
            va.sustain=1;va.release_ms=5;va.cutoff_hz=18000;va.resonance=0;
            fmer::GlideParameters glide;glide.mode=fmer::GlideMode::legato;glide.time_ms=1000;
            glide.contour=static_cast<fmer::GlideContour>(shape);
            for(auto* s:{&a,&b}) {
                s->set_patch(quick_patch());s->set_va_parameters(va);s->set_engine(engine);s->set_mono(true);s->set_glide(glide);
                s->note_on(0,69,110,1);render(*s,4096);s->note_on(0,81,110,1);
            }
            require(a.stats().active_voices==1,"mono overlap uses exactly one voice");
            const auto x=render(a,44100,17),y=render(b,44100,511);
            require(x==y && energy(x)>.01,"glide is audible and independent of caller chunk sizes");
            centers[shape]=frequency({x.begin()+19845,x.begin()+24255});
            render(a,256);
            require(std::abs(frequency(render(a,22050))-880)<4,"glide reaches exact musical destination within one control block");
            a.note_off(0,69,1);
            require(a.activity().gated_notes[2]&(1u<<17),"old mono note off cannot release the current note");
            a.note_off(0,81,1);render(a,44100);
            require(!a.stats().active_voices,"glide leaves normal envelope release intact");
        }
        require(centers[1]>500 && centers[1]<centers[0]-65 && centers[0]>600 && centers[0]<650 && centers[2]>centers[0]+70,
                "ease-in, linear and ease-out produce distinct predictable midpoint pitches");
    }
}

void glide_modes_fixed_operators_and_parts() {
    for(auto engine:{fmer::SynthEngine::fm,fmer::SynthEngine::va}) {
        fmer::VaParameters va;va.waveform=fmer::VaWaveform::sine;va.attack_ms=0;va.decay_ms=0;va.sustain=1;va.release_ms=0;
        for(auto mode:{fmer::GlideMode::off,fmer::GlideMode::legato,fmer::GlideMode::always}) {
            fmer::Synth s;fmer::GlideParameters glide;glide.mode=mode;glide.time_ms=1000;
            s.set_patch(quick_patch());s.set_engine(engine);s.set_va_parameters(va);s.set_mono(true);s.set_glide(glide);
            s.note_on(0,69,110);render(s,4096);s.note_off(0,69);render(s,44100);
            s.note_on(0,81,110);render(s,128);const auto first=render(s,4410);
            require(mode==fmer::GlideMode::always?frequency(first)<490:frequency(first)>860,
                    "always glides detached notes while off and legato retrigger at destination");
        }
    }
    fmer::Synth a,b;auto fixed=quick_patch();fixed.vced[105+17]=1;fixed.vced[105+18]=2;fixed.vced[105+19]=0;
    fmer::GlideParameters glide;glide.mode=fmer::GlideMode::legato;glide.time_ms=500;
    for(auto* s:{&a,&b}) {s->set_patch(fixed);s->set_mono(true);s->set_glide(glide);s->note_on(0,60,100);render(*s,4096);}
    a.note_on(0,96,100);
    require(render(a,24000,31)==render(b,24000,127),"fixed FM oscillators retain exact phase, frequency and envelope through portamento");
    fmer::Synth part;fmer::PartParameters p;p.patch=quick_patch();p.glide=glide;
    part.configure_part(3,p);part.set_parts_enabled(true);part.part_note_on(3,0,69,100,4);render(part,4096);
    part.part_note_on(3,0,81,100,4);render(part,8000);
    require(frequency(render(part,4410))>530 && part.stats().active_voices==1,"reserved parts use their own glide settings");
    part.panic();part.part_note_on(3,0,81,100,4);render(part,128);
    require(frequency(render(part,4410))>860,"panic clears stale glide origin");
}

void parts_and_glide_do_not_allocate() {
    fmer::Synth synth;fmer::PartParameters p;p.patch=quick_patch();p.glide.mode=fmer::GlideMode::always;
    p.glide.time_ms=25;std::array<float,127> audio{};
    const auto before=synth_test_allocations;
    synth.set_voice_budget(4);synth.set_parts_enabled(true);
    for(std::uint8_t part=0;part<4;++part) {
        p.engine=part%2?fmer::SynthEngine::va:fmer::SynthEngine::fm;
        synth.configure_part(part,p);synth.set_part_mix(part,.75f,false);synth.part_note_on(part,part,48+part*5,100,4);
    }
    for(unsigned block=0;block<100;++block) {
        if(block==10)for(std::uint8_t part=0;part<4;++part)synth.part_note_on(part,part,60+part*5,100,4);
        if(block==20)synth.pitch_bend(1,12000);
        if(block==30)synth.set_part_mix(0,.3f,true);
        if(block==40)for(std::uint8_t part=0;part<4;++part)synth.part_note_off(part,part,60+part*5,4);
        synth.render(audio.data(),audio.size());
    }
    synth.panic();synth.set_parts_enabled(false);synth.set_mono(true);synth.set_glide(p.glide);
    synth.note_on(0,60,100);synth.render(audio.data(),audio.size());synth.note_on(0,72,100);
    synth.render(audio.data(),audio.size());synth.note_off(0,72);synth.panic();
    require(synth_test_allocations==before,"configuration, four-part MIDI, mixing, glide, release and panic allocate nothing");
}

void mono_return_to_held_key() {
    for(auto engine:{fmer::SynthEngine::fm,fmer::SynthEngine::va})for(bool parts:{false,true}) {
        fmer::Synth actual,reference;
        fmer::PartParameters p;p.patch=quick_patch();p.engine=engine;p.glide.mode=fmer::GlideMode::legato;
        p.glide.time_ms=1000;p.va.waveform=fmer::VaWaveform::sine;p.va.attack_ms=0;p.va.decay_ms=0;
        p.va.sustain=1;p.va.release_ms=5;p.va.cutoff_hz=18000;p.va.resonance=0;
        auto on=[&](fmer::Synth& s,unsigned note,unsigned velocity=110){
            if(parts)s.part_note_on(2,1,note,velocity,3,true);else s.note_on(1,note,velocity,3);
        };
        auto off=[&](fmer::Synth& s,unsigned note){if(parts)s.part_note_off(2,1,note,3);else s.note_off(1,note,3);};
        for(auto* s:{&actual,&reference}) {
            s->set_patch(p.patch);s->set_engine(engine);s->set_va_parameters(p.va);s->set_glide(p.glide);
            s->configure_part(2,p);if(parts)s->set_parts_enabled(true);else s->set_mono(true);
            on(*s,69,83);render(*s,4096);on(*s,81);render(*s,48000);
        }
        off(actual,81);on(reference,69,83);
        const auto returned=render(actual,44100,13),expected=render(reference,44100,257);
        require(returned==expected,"releasing newest key returns along exact same glide/envelope path as a held-key retarget");
        const auto middle=frequency({returned.begin()+19845,returned.begin()+24255});
        require(middle>600 && middle<650,"return glide travels downward instead of jumping or staying at newer key");
        require(std::abs(frequency(render(actual,22050))-440)<4,"return glide reaches previous held pitch");
        const auto activity=actual.activity();
        require(activity.active_voices==1 && (activity.gated_notes[2]&(1u<<5)) && !(activity.gated_notes[2]&(1u<<17)),
                "actual active note ownership moves back to original held key");
        off(actual,69);render(actual,44100);require(!actual.stats().active_voices,"final physical key release ends restored voice normally");
    }
}

void mono_stack_priority_cleanup_and_capacity() {
    fmer::Synth s;s.set_mono(true);s.set_patch(quick_patch());
    auto active=[&](unsigned pitch){return (s.activity().gated_notes[pitch/32]&(1u<<(pitch%32)))!=0;};
    s.note_on(0,60,90,1);s.note_on(0,64,100,1);s.note_on(0,67,110,1);
    s.note_off(0,64,1);s.note_off(0,67,1);
    require(active(60) && !active(64),"released middle key cannot be revived by last-note priority");
    s.note_on(1,60,100,2);s.note_off(0,60,2);s.note_off(1,60,1);
    require(active(60) && !s.stats().released_voices,"wrong channel/source releases never remove held ownership");
    s.note_off(1,60,2);require(active(60),"identical pitch from a different owner restores original owner");
    s.note_off(0,60,1);require(!active(60),"restored owner has independent final release");
    s.panic();s.note_on(0,60,90,1);s.note_on(0,64,90,1);s.note_on(0,60,100,1);s.note_off(0,60,1);
    require(active(64),"repeated key updates priority without leaving duplicate held entries");
    s.control_change(0,64,127);s.note_off(0,64,1);require(active(64),"last physical release respects sustain pedal");
    s.control_change(0,64,0);require(!active(64),"pedal release retires final sustained key");
    for(unsigned cc:{120u,123u}) {
        s.panic();s.note_on(0,60,100,1);s.note_on(0,64,100,1);s.control_change(0,cc,0);
        s.note_on(0,67,100,1);s.note_off(0,67,1);require(!active(60) && !active(64),"channel termination clears dormant mono keys");
    }
    s.panic();s.note_on(0,60,100,1);s.note_on(0,64,100,2);s.panic_source(1);s.note_off(0,64,2);
    require(!active(60),"source panic removes dormant keys before later return");
    s.panic();const auto rejected=s.stats().rejected_events;
    for(unsigned i=0;i<fmer::Synth::mono_held_limit;++i)s.note_on(0,40+i,100,1);
    s.note_on(0,100,100,1);
    require(s.stats().rejected_events==rejected+1 && active(71),"held-note overflow reports rejection and preserves existing latest key");
    for(unsigned i=fmer::Synth::mono_held_limit;i--;) {
        require(active(40+i),"full bounded stack unwinds in last-held order");s.note_off(0,40+i,1);
    }
    require(!s.activity().gated_notes[1] && !s.activity().gated_notes[2],"full held stack releases without ghost keys");
    s.panic();s.note_on(0,60,100);s.set_mono(false);s.set_mono(true);s.note_on(0,67,100);s.note_off(0,67);
    require(!active(60),"mode transitions clear old mono ownership");
    s.set_parts_enabled(true);fmer::PartParameters p;p.patch=quick_patch();
    for(unsigned part=0;part<4;++part){s.configure_part(part,p);s.part_note_on(part,part,50+part,100,1);s.part_note_on(part,part,62+part,100,1);}
    for(unsigned part=0;part<4;++part) {
        s.part_note_off(part,part,62+part,1);const auto a=s.part_activity(part);
        require(a.active_voices==1 && (a.gated_notes[(50+part)/32]&(1u<<((50+part)%32))),"each part returns only to its own held key");
    }
    s.panic_part(2);s.part_note_on(2,2,80,100,1);s.part_note_off(2,2,80,1);
    require(!(s.part_activity(2).gated_notes[1]&(1u<<20)) && s.part_activity(1).active_voices==1,"part panic clears its stack without disturbing other parts");
}

int main() {
    try {
        basics_and_pitch();
        direct_msfa_reference();
        exhaustive_sine_and_kernel_reference();
        release_and_pedal();
        ownership_and_stealing();
        chunk_invariance_and_snapshots();
        algorithms_and_validation();
        va_preview();
        bounded_voice_budget(); mixed_voice_chunk_order(); va_pitch_extremes();
        va_vibrato_and_generated_sustain(); activity_snapshots(); fm_amplitude_modulation();
        live_program_lfo_gate();
        four_reserved_parts();part_mixer_and_validation();part_mixer_matches_sample_recurrence();
        mono_glide_pitch_and_contours();glide_modes_fixed_operators_and_parts();
        parts_and_glide_do_not_allocate();
        mono_return_to_held_key();mono_stack_priority_cleanup_and_capacity();
        std::cout << "synth: pitch, release, sustain, ownership, capacity, chunk invariance, "
                     "patch snapshots, all32 algorithms, VA waveforms/filter and malformed-input checks passed\n";
        return EXIT_SUCCESS;
    } catch (const std::exception& error) {
        std::cerr << "synth failure: " << error.what() << '\n';
        return EXIT_FAILURE;
    }
}
