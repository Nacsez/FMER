#include "factory_presets.hpp"
#include "../third_party/msfa/src/fm_op_kernel.h"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <iostream>
#include <new>
#include <stdexcept>
#include <string>
#include <vector>

namespace { bool track_allocations=false; std::size_t tracked_allocations=0; }
void* operator new(std::size_t size) {
    if(track_allocations)++tracked_allocations;
    if(auto* value=std::malloc(size?size:1))return value;
    throw std::bad_alloc();
}
void* operator new[](std::size_t size) { return ::operator new(size); }
void operator delete(void* value) noexcept { std::free(value); }
void operator delete[](void* value) noexcept { std::free(value); }
void operator delete(void* value,std::size_t) noexcept { std::free(value); }
void operator delete[](void* value,std::size_t) noexcept { std::free(value); }

namespace {
void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

std::vector<float> render(fmer::Synth& synth, std::size_t count, std::size_t chunk) {
    std::vector<float> audio(count);
    for (std::size_t i=0; i<count; i+=chunk)
        synth.render(audio.data()+i,std::min(chunk,count-i));
    return audio;
}

double rms(const std::vector<float>& audio) {
    double sum=0;
    for (auto sample : audio) {
        require(std::isfinite(sample) && std::abs(sample)<=1,"preset audio finite and bounded");
        sum+=sample*sample;
    }
    return std::sqrt(sum/audio.size());
}

void select(fmer::Synth& synth,const fmer::FactoryPreset& preset) {
    require(synth.set_patch(preset.patch) && synth.set_engine(preset.engine) &&
            synth.set_va_parameters(preset.va),"factory sound accepted by actual synth");
    synth.set_lfo_enabled(preset.lfo_enabled);
}

std::array<std::uint8_t,190> sound_bytes(const fmer::FactoryPreset& preset) {
    std::array<std::uint8_t,190> bytes{};
    std::size_t position=0;
    auto byte=[&](std::uint8_t value){bytes[position++]=value;};
    for(auto value:preset.patch.vced)byte(value);
    byte(static_cast<std::uint8_t>(preset.engine));
    byte(static_cast<std::uint8_t>(preset.va.waveform));
    for(auto value:{preset.va.cutoff_hz,preset.va.resonance,preset.va.attack_ms,
                   preset.va.decay_ms,preset.va.sustain,preset.va.release_ms,
                   preset.va.lfo_rate_hz,preset.va.lfo_depth_cents}) {
        std::uint32_t bits;
        static_assert(sizeof(bits)==sizeof(value),"32-bit canonical floats");
        std::memcpy(&bits,&value,sizeof(bits));
        for(unsigned shift=0;shift<32;shift+=8)byte(static_cast<std::uint8_t>(bits>>shift));
    }
    byte(preset.lfo_enabled?1:0);
    require(position==bytes.size(),"sound fingerprint covers every field");
    return bytes;
}

std::uint32_t sound_fingerprint(const fmer::FactoryPreset& preset) {
    std::uint32_t hash=2166136261u;
    for(auto byte:sound_bytes(preset))hash=(hash^byte)*16777619u;
    return hash;
}

void recipes_are_valid_audible_distinct_and_bounded() {
    std::vector<std::string> names;
    std::vector<std::vector<float>> sounds;
    for (std::size_t id=0; id<fmer::factory_preset_count; ++id) {
        fmer::FactoryPreset preset;
        require(fmer::load_factory_preset(id,preset),"all declared factory IDs load");
        require(preset.name==fmer::factory_preset_name(id),"metadata and loaded name agree");
        require(std::strlen(preset.name)>0 && std::strlen(preset.name)<=10,"name fits complete native and DX7 fields");
        require(std::find(names.begin(),names.end(),preset.name)==names.end(),"factory names unique");
        names.emplace_back(preset.name);
        require(fmer::validate_patch(preset.patch).valid,"factory FM bytes validate for either engine");
        for (std::size_t c=0;c<10;++c)
            require(preset.patch.vced[145+c]==(c<names.back().size()?names.back()[c]:' '),"patch name preserves exact padded bytes");
        require(preset.engine==fmer::factory_preset_engine(id),"engine metadata and loaded sound agree");
        std::array<std::uint8_t,fmer::kVmemSize> packed{};
        fmer::Patch roundtrip;
        std::string error;
        require(fmer::pack_vmem(preset.patch,packed,error) &&
                fmer::unpack_vmem(packed,roundtrip,error) && roundtrip.vced==preset.patch.vced,
                "factory compatibility voice round trip is exact");
        if (preset.engine==fmer::SynthEngine::fm) {
            unsigned active=0;
            for(std::size_t op=0;op<6;++op) if(preset.patch.vced[op*21+16]) ++active;
            require(active>=4,"factory FM voices expose useful multi-operator material; intentional four-op recipes may mute unused branches");
        }
        fmer::Synth a,b;
        select(a,preset);select(b,preset);
        a.note_on(0,60,100);b.note_on(0,60,100);
        auto audio=render(a,22050,37);
        require(audio==render(b,22050,128),"every recipe is deterministic across render chunks");
        require(rms(audio)>.001,"every factory sound has usable finite audible output");
        require(std::find(sounds.begin(),sounds.end(),audio)==sounds.end(),"all original factory sounds produce distinct PCM");
        sounds.push_back(audio);
        require(a.stats().clipped_samples==0,"single-note factory voice retains headroom");
        a.note_off(0,60);render(a,441000,128);
        require(a.stats().active_voices==0,"every factory voice releases within ten seconds");
        a.panic();a.set_voice_budget(4);
        double chord_peak=0;
        for(auto octave:{36,60,84}) {
            for(auto note : {0,4,7,12})a.note_on(0,static_cast<std::uint8_t>(octave+note),127);
            const auto chord=render(a,66150,128);
            require(rms(chord)>.0001 && a.stats().clipped_samples==0,
                    "four-note factory chord in each register stays audible without synth clipping");
            for(auto sample:chord)chord_peak=std::max(chord_peak,std::abs(static_cast<double>(sample)));
            a.panic();
        }
        a.panic();require(rms(render(a,128,128))==0,"panic clears each preset");
        std::cout << id << ' ' << preset.name << " rms=" << rms(audio)
                  << " algorithm=" << static_cast<unsigned>(preset.patch.vced[134])
                  << " chord_peak=" << chord_peak
                  << " fingerprint=" << sound_fingerprint(preset) << '\n';
    }
}

void stable_program_ids_and_no_allocation() {
    // 709.1 intentionally revises every sound with owner authorization.
    // 708 bytes remain archived under artifacts/defaults-709/baseline708.
    constexpr const char* legacy_names[16]={"FM KEYS","FM BELL","FM BASS","FM BRASS",
        "FM ORGAN","FM PLUCK","FM REED","FM MOTION","VA ROUND","VA SAW","VA PULSE",
        "VA TRI","VA BASS","VA PLUCK","VA SOFT","VA VIBRA"};
    require(fmer::factory_preset_count==64 && fmer::factory_fm_preset_count==32 &&
            fmer::factory_va_preset_count==32,"declared bank has 32 FM and 32 VA sounds");
    bool seen[64]={};
    fmer::FactoryPreset preset;
    fmer::Synth synth;
    for(auto engine:{fmer::SynthEngine::fm,fmer::SynthEngine::va}) {
        for(std::size_t bank=0;bank<32;++bank) {
            const auto id=fmer::factory_preset_id(engine,bank);
            require(id<64 && !seen[id],"each bank position maps to one distinct stable program ID");
            seen[id]=true;
            require(fmer::factory_preset_engine(id)==engine &&
                    fmer::factory_preset_bank_index(id)==bank,"bank mapping is reversible");
            tracked_allocations=0;track_allocations=true;
            const bool loaded=fmer::load_factory_preset(id,preset);
            const bool applied=synth.set_patch(preset.patch) && synth.set_engine(preset.engine) &&
                synth.set_va_parameters(preset.va);
            track_allocations=false;
            require(loaded && applied && tracked_allocations==0,"constructing and selecting every preset allocates nothing");
            if(id<16) {
                require(std::strcmp(preset.name,legacy_names[id])==0,"program IDs retain named musical roles");
            }
        }
    }
    for(auto invalid:{std::size_t(64),std::size_t(65535),std::size_t(-1)})
        require(fmer::factory_preset_bank_index(invalid)==32 &&
                fmer::factory_preset_engine(invalid)==static_cast<fmer::SynthEngine>(255),
                "invalid IDs do not alias a valid bank sound");
    require(fmer::factory_preset_id(fmer::SynthEngine::fm,32)==64 &&
            fmer::factory_preset_id(fmer::SynthEngine::va,32)==64 &&
            fmer::factory_preset_id(static_cast<fmer::SynthEngine>(255),0)==64,
            "invalid bank requests are refused explicitly");
}

void algorithm_audition_regression() {
    fmer::FactoryPreset preset;
    fmer::load_factory_preset(0,preset);
    fmer::Synth first,parallel;
    select(first,preset);
    preset.patch.vced[134]=31;select(parallel,preset);
    first.note_on(0,60,100);parallel.note_on(0,60,100);
    const auto a=render(first,8192,128),b=render(parallel,8192,128);
    double difference=0;
    for(std::size_t i=0;i<a.size();++i)difference+=(a[i]-b[i])*(a[i]-b[i]);
    require(std::sqrt(difference/a.size())>.01,"FM KEYS algorithm changes produce a substantial audible signal difference");
    fmer::Synth init_a,init_b;
    auto init=fmer::make_init_patch();
    init_a.set_patch(init);init.vced[134]=31;init_b.set_patch(init);
    init_a.note_on(0,60,100);init_b.note_on(0,60,100);
    require(render(init_a,8192,128)==render(init_b,8192,128),
            "old init recipe masks algorithm changes because only OP1 is audible");
}

void percussion_body_regression() {
    for(unsigned id:{19u,21u,23u,32u,34u,39u}) {
        fmer::FactoryPreset p;fmer::load_factory_preset(id,p);fmer::Synth synth;select(synth,p);
        synth.note_on(0,60,100);auto a=render(synth,22050,128);double early=0,total=0;
        for(unsigned i=0;i<a.size();i++){total+=a[i]*a[i];if(i<882)early+=a[i]*a[i];}
        require(total>0 && early<total*.95,"percussion has audible body beyond20ms, not only an onset click");
    }
}

void sustained_fm_character_regression() {
    // Audible/distinct PCM did not catch715's near-pure sustained sine patches.
    // Measure the fundamental by projection over32 cycles (not FFT-bin guesses)
    // and require substantial remaining energy in voices intended to be rich.
    // Intentionally rounded sub/flute sounds are not forced to be bright.
    const double frequency=440.0*std::pow(2.0,(48-69)/12.0);
    const unsigned count=static_cast<unsigned>(32*44100/frequency);
    for(unsigned id:{3u,6u,24u,28u,29u,33u,35u,38u}) {
        fmer::FactoryPreset p;fmer::load_factory_preset(id,p);fmer::Synth s;
        select(s,p);s.set_lfo_enabled(false);s.note_on(0,48,100);
        render(s,22050,128);auto a=render(s,count,128);
        double total=0,cosine=0,sine=0;
        for(unsigned i=0;i<count;++i){const double phase=6.283185307179586*frequency*i/44100;
            total+=a[i]*a[i];cosine+=a[i]*std::cos(phase);sine+=a[i]*std::sin(phase);}
        const double other=1-2*(cosine*cosine+sine*sine)/(count*total);
        std::cout<<"FM sustained character "<<id<<" nonfundamental="<<other<<'\n';
        require(total>0 && other>.04,"brass/reed/arcade/lead retain sustained FM sidebands");
    }
}

void musical_articulation_regression() {
    // An audible bank can still collapse to similar static tones. Check the
    // rendered musical behaviors: struck voices decay, bowed voices bloom,
    // and the brass/slap/squelch attacks have more edge than their bodies.
    auto window=[](const std::vector<float>& a,unsigned start,unsigned end) {
        double power=0,slew=0;
        for(unsigned i=start;i<end;++i){power+=a[i]*a[i];
            if(i>start){const double d=a[i]-a[i-1];slew+=d*d;}}
        require(power>0,"articulation window is audible");
        return std::array<double,2>{std::sqrt(power/(end-start)),std::sqrt(slew/power)};
    };
    for(unsigned id:{0u,3u,5u,17u,18u,27u,29u,30u,33u,36u}){
        fmer::FactoryPreset p;fmer::load_factory_preset(id,p);fmer::Synth s;
        select(s,p);s.set_lfo_enabled(false);s.note_on(0,60,100);
        const auto a=render(s,44100,128);
        const auto front=window(a,882,5292),body=window(a,33075,41895);
        if(id==0||id==5||id==17||id==18||id==30)
            require(body[0]<front[0]*.55,"struck keys and brass stab decay while held");
        if(id==33||id==36)
            require(body[0]>front[0]*1.5,"bowed/pad attack blooms rather than acting like a pluck");
        if(id==3||id==27||id==29)
            require(front[1]>body[1]*1.2,"brass/slap/squelch retain an audible timbral transient before their body");
    }
}

void owner_liked_voices_preserved() {
    // Explicit718 sound fingerprints, independent of file paths/build identity.
    // These protect the successful bank anchors while weaker roles are voiced.
    constexpr std::uint32_t preserved[][2]={
        {1,2893407283u},{4,2128682823u},{7,1695164460u},{16,3015680079u},
        {20,3680691975u},{22,2101327868u},{24,938437625u},{31,2356292708u}};
    for(const auto& row:preserved){fmer::FactoryPreset p;
        require(fmer::load_factory_preset(row[0],p)&&sound_fingerprint(p)==row[1],
                "718 bell/organ/motion/tine/vibes/jingle/arcade/flute recipes remain exact");}
}

void phase_modulation_reference_regression() {
    // Independent floating-point oracle, not a second call to the FM renderer.
    // The kernel uses Q24 *cycles*, hence2*pi is required for a radian index.
    fmer::Synth initialize_tables;
    constexpr double tau=6.283185307179586;
    constexpr int unit=1<<24,frequency=71937;
    std::int32_t input[64],output[64];
    for(double index:{0.0,.3,1.0,3.0,8.0}) {
        double worst=0;
        for(unsigned i=0;i<64;++i)input[i]=static_cast<std::int32_t>(index/tau*unit*std::sin(tau*frequency*2.0*i/unit));
        FmOpKernel::compute(output,input,0,frequency,unit,unit,false);
        for(unsigned i=0;i<64;++i){const double expected=std::sin(tau*(double(frequency)*i+input[i])/unit);
            worst=std::max(worst,std::abs(output[i]/double(unit)-expected));}
        require(worst<.00002,"FM phase/index scaling matches independent sine oracle");
    }
}

void invalid_load_and_sound_scope() {
    fmer::FactoryPreset output;
    require(fmer::load_factory_preset(63,output),"last factory slot is present");
    const auto previous=output;
    for(auto invalid : {fmer::factory_preset_count,std::size_t(65535),std::size_t(-1)}) {
        require(!fmer::load_factory_preset(invalid,output) && !fmer::factory_preset_name(invalid),"out-of-range factory recall refused");
        require(output.name==previous.name && output.patch.vced==previous.patch.vced &&
                output.engine==previous.engine && sound_bytes(output)==sound_bytes(previous),
                "refused recall does not overwrite prior sound");
    }
    // The API changes future note state only; recall policy/panic is an adapter
    // decision and may never create an unowned note as a side effect.
    fmer::Synth synth;
    for(std::size_t id=0;id<fmer::factory_preset_count;++id){
        fmer::load_factory_preset(id,output);select(synth,output);
        require(synth.stats().active_voices==0 && synth.stats().note_ons==0,"preset construction and selection never starts audio");
    }
}
}

int main() {
    try {
        recipes_are_valid_audible_distinct_and_bounded();
        stable_program_ids_and_no_allocation();
        algorithm_audition_regression();
        percussion_body_regression();
        sustained_fm_character_regression();
        musical_articulation_regression();
        owner_liked_voices_preserved();
        phase_modulation_reference_regression();
        invalid_load_and_sound_scope();
        std::cout << "factory presets: original names, sound scope, codec, algorithms, audio, release and capacity passed\n";
        return EXIT_SUCCESS;
    } catch(const std::exception& error) {
        std::cerr << "factory preset failure: " << error.what() << '\n';
        return EXIT_FAILURE;
    }
}
