// The actual C DSP boundary runs on the host here; this does not emulate WL82.
#include "../firmware/fm1/dsp_adapter.h"
#include "patch.hpp"
#include "factory_presets.hpp"
#include <algorithm>
#include <array>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <vector>
#include <cstring>
#include <cstdlib>
#include <new>
#include <chrono>

static bool count_allocations;
static uint32_t realtime_allocations;
void* operator new(std::size_t size) {
    if (count_allocations) ++realtime_allocations;
    if (auto* p = std::malloc(size ? size : 1)) return p;
    throw std::bad_alloc();
}
void* operator new[](std::size_t size) { return ::operator new(size); }
void operator delete(void* p) noexcept { std::free(p); }
void operator delete[](void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }
void operator delete[](void* p, std::size_t) noexcept { std::free(p); }

static void require(bool ok, const char* message) {
    if (!ok) throw std::runtime_error(message);
}
static fmer_controls_t snapshot() { fmer_controls_t c{}; fmer_dsp_get_controls(&c); return c; }
static fmer_performance_state_t performance() { fmer_performance_state_t p{}; fmer_dsp_performance(&p); return p; }
struct TappedEvent { uint32_t frame; uint8_t status,note,velocity,source; };
static TappedEvent tapped[1024];
static uint32_t tapped_count;
static void tap(uint32_t frame,uint8_t status,uint8_t note,uint8_t velocity,uint8_t source) {
    if(tapped_count<1024)tapped[tapped_count++]={frame,status,note,velocity,source};
}
static void set(uint32_t id, uint16_t value) {
    auto c = snapshot(); c.value[id] = value;
    require(fmer_dsp_apply_controls(&c), "canonical control accepted");
}
static std::vector<int32_t> audio(uint32_t frames, uint32_t chunk = 128) {
    std::vector<int32_t> result(frames * 2);
    for (uint32_t i = 0; i < frames; i += chunk)
        fmer_dsp_render(result.data() + 2*i, std::min(chunk, frames-i), 1024);
    return result;
}
static fmer_activity_state_t activity() { fmer_activity_state_t s{}; fmer_dsp_get_activity(&s); return s; }
static bool note_in(const uint32_t* words, uint32_t note) { return (words[note/32] & (uint32_t{1}<<(note%32))) != 0; }
static fmer_native_state_t native_snapshot() { fmer_native_state_t s{};fmer_dsp_get_native(&s);return s; }
static bool native_values_equal(const fmer_native_state_t& a,const fmer_native_state_t& b) {
    return !std::memcmp(&a.controls,&b.controls,sizeof a.controls) && !std::memcmp(a.vced,b.vced,155) &&
        !std::memcmp(a.pitch,b.pitch,64) && !std::memcmp(a.velocity,b.velocity,64) &&
        !std::memcmp(a.gate,b.gate,64) && a.length==b.length && a.preset_id==b.preset_id && !std::memcmp(a.patterns,b.patterns,sizeof a.patterns);
}
static void native_state_roundtrip() {
    fmer_dsp_panic();const auto baseline=native_snapshot();
    auto wanted=baseline;
    wanted.preset_id=FMER_NATIVE_CUSTOM_PRESET;
    wanted.vced[134]=11;wanted.controls.value[134]=11;
    const uint8_t exact_name[10]={'m','y',' ','p','a','t',127,0,27,'!'};
    std::copy_n(exact_name,10,wanted.vced+145);
    wanted.controls.value[FMER_ENGINE]=1;wanted.controls.value[FMER_VA_WAVE]=2;
    wanted.controls.value[FMER_ATTACK]=0;wanted.controls.value[FMER_DECAY]=0;
    wanted.controls.value[FMER_SUSTAIN]=100;wanted.controls.value[FMER_RELEASE]=0;
    wanted.controls.value[FMER_LFO_RATE]=777;wanted.controls.value[FMER_LFO_DEPTH]=43;
    wanted.controls.value[FMER_MIDI_CHANNEL]=5;wanted.controls.value[FMER_REVERB_DECAY]=67;
    wanted.controls.value[FMER_VOICE_BUDGET]=3;wanted.controls.value[FMER_ARP_ENABLE]=1;
    wanted.length=7;wanted.controls.value[FMER_SEQ_LENGTH]=7;wanted.controls.value[FMER_SEQ_STEP]=3;
    for(unsigned i=0;i<64;++i){
        wanted.pitch[i]=static_cast<uint8_t>(i%5?24+i:FMER_REST);
        wanted.velocity[i]=static_cast<uint8_t>(1+i);wanted.gate[i]=static_cast<uint8_t>(1+i*7%100);
    }
    for(unsigned bank=0;bank<7;++bank) {
        auto& pattern=wanted.patterns[bank];pattern.length=static_cast<uint8_t>(bank+1);
        for(unsigned step=0;step<64;++step) {
            pattern.pitch[step]=static_cast<uint8_t>((bank*13+step)%129);
            pattern.velocity[step]=static_cast<uint8_t>(1+(bank*9+step)%127);
            pattern.gate[step]=static_cast<uint8_t>(1+(bank*11+step)%100);
        }
    }
    wanted.controls.value[FMER_SEQ_PITCH]=wanted.pitch[3];
    wanted.controls.value[FMER_SEQ_VELOCITY]=wanted.velocity[3];
    wanted.controls.value[FMER_SEQ_GATE]=wanted.gate[3];
    require(fmer_native_state_valid(&wanted)==FMER_NATIVE_OK,"native fixture includes valid complete state");
    const auto old_generation=fmer_dsp_state_generation();set(FMER_TEMPO,137);
    fmer_dsp_midi(0x90,69,100,3);const auto before=native_snapshot();
    const auto active_before=fmer_dsp_active();
    require(!fmer_dsp_set_native(&wanted,old_generation),"stale native generation refused before owner release");
    auto after=native_snapshot();
    require(native_values_equal(before,after) && before.source_generation==after.source_generation &&
            fmer_dsp_active()==active_before,"stale restore leaves notes, complete data and generation unchanged");
    require(!fmer_dsp_set_native(nullptr,after.source_generation),"null native state refused");
    for(unsigned corruption=0;corruption<6;++corruption){
        auto invalid=wanted;
        if(corruption==0)invalid.controls.value[FMER_RESONANCE]=96;
        if(corruption==1)invalid.vced[134]=0;
        if(corruption==2)invalid.gate[63]=0;
        if(corruption==3)invalid.vced[154]=128;
        if(corruption==4)invalid.controls.value[FMER_SEQ_PITCH]=128;
        if(corruption==5)invalid.patterns[6].gate[63]=0;
        require(!fmer_dsp_set_native(&invalid,before.source_generation),"malformed native record refused");
        after=native_snapshot();
        require(native_values_equal(before,after) && before.source_generation==after.source_generation &&
                fmer_dsp_active()==active_before,"malformed native restore is nonmutating including active owners");
    }
    fmer_dsp_midi(0xb0,64,127,1);fmer_dsp_midi(0x90,64,100,1);fmer_dsp_midi(0x80,64,0,1);
    fmer_dsp_transport(FMER_TRANSPORT_PLAY);audio(128);
    const auto allocation_before=realtime_allocations;
    count_allocations=true;
    const auto accepted=fmer_dsp_set_native(&wanted,fmer_dsp_state_generation());
    fmer_native_state_t restored{};fmer_dsp_get_native(&restored);
    count_allocations=false;
    require(accepted && realtime_allocations==allocation_before,"validated full restore and readback allocate nothing");
    require(native_values_equal(wanted,restored),"native roundtrip preserves all198 controls,155 VCED bytes and512 steps including inactive data");
    char display_name[11]{};fmer_dsp_patch_name(display_name);
    require(!std::strcmp(display_name,"MY PAT   !"),"display name sanitizes control glyphs without altering exact native name bytes");
    require(restored.source_generation!=before.source_generation && fmer_dsp_active()==0 &&
            !performance().running && !performance().recording && !performance().arp_held,
            "accepted restore advances generation and clears playback,recording,arp and live owners");
    require(fmer_dsp_voice_limit()==3 && fmer_dsp_preset_id()==FMER_NATIVE_CUSTOM_PRESET && fmer_dsp_sound_dirty(),
            "native restore applies voice budget and honest custom sound identity");
    const auto silent=audio(1024);
    require(std::all_of(silent.begin(),silent.end(),[](int32_t value){return value==0;}),"restored arp configuration cannot resurrect old held notes or FX tails");
    fmer_dsp_transport(FMER_TRANSPORT_RECORD);fmer_dsp_midi(0x90,66,91,3);
    require(performance().recording,"record-mode restore fixture is actually armed");
    require(fmer_dsp_set_native(&wanted,fmer_dsp_state_generation()) && !performance().recording && !fmer_dsp_active(),
            "complete import disarms step entry and retires its live owner");
    set(FMER_ARP_LATCH,1);fmer_dsp_midi(0x90,67,100,3);fmer_dsp_midi(0x80,67,0,3);audio(128);
    require(performance().arp_held==1,"latched-arp restore fixture retains an actual chord");
    require(fmer_dsp_set_native(&wanted,fmer_dsp_state_generation()) && !performance().arp_held && !fmer_dsp_active(),
            "complete import clears latched generated ownership before applying new configuration");
    set(FMER_ARP_ENABLE,0);fmer_dsp_midi(0x90,60,100,3);fmer_dsp_midi(0x80,60,0,3);audio(1);
    require(!fmer_dsp_active(),"restore clears pedal state so a fresh local note releases normally");
    const auto budget_generation=fmer_dsp_state_generation();
    require(fmer_dsp_voice_budget(2) && fmer_dsp_state_generation()!=budget_generation,"direct voice-budget mutation invalidates a captured native generation");
    require(fmer_dsp_set_native(&baseline,fmer_dsp_state_generation()),"complete native baseline restored");
    std::cout<<"707 native adapter: stale and malformed refusal, full hidden-state/name roundtrip, runtime cleanup and no allocation passed\n";
}

static void factory_and_external_midi() {
    fmer_dsp_panic();const auto baseline=native_snapshot();
    set(FMER_TEMPO,137);set(FMER_DELAY,17);set(FMER_REVERB,23);set(FMER_REVERB_DECAY,68);
    set(FMER_SEQ_PATTERN,5);set(FMER_SEQ_CHAIN_MASK,37);set(FMER_SEQ_CHAIN,1);
    set(FMER_MIDI_CHANNEL,5);set(FMER_VOICE_BUDGET,3);set(FMER_SEQ_LENGTH,4);
    set(FMER_SEQ_STEP,2);set(FMER_SEQ_PITCH,74);set(FMER_SEQ_VELOCITY,93);set(FMER_SEQ_GATE,31);
    const auto preserved=native_snapshot();const auto pattern_revision=fmer_dsp_pattern_revision();
    fmer_dsp_transport(FMER_TRANSPORT_PLAY);audio(128);
    for(unsigned id=0;id<64;++id){
        require(fmer_dsp_factory_preset(id),"every factory sound recalls through real C adapter");
        const auto state=native_snapshot();fmer::FactoryPreset original;fmer::load_factory_preset(id,original);
        require(!std::memcmp(state.vced,original.patch.vced.data(),155) && state.preset_id==id &&
                !fmer_dsp_sound_dirty() && fmer_dsp_preset_id()==id,"factory recall publishes original bytes and clean named identity");
        char name[11]{};fmer_dsp_patch_name(name);
        require(!std::memcmp(name,original.patch.vced.data()+145,10) && !name[10] &&
                !std::strcmp(fmer_dsp_factory_name(id),original.name),"display and factory names match actual loaded voice");
        for(unsigned parameter : {FMER_TEMPO,FMER_DELAY,FMER_REVERB,FMER_REVERB_DECAY,FMER_MIDI_CHANNEL,FMER_VOICE_BUDGET,
                                  FMER_SEQ_LENGTH,FMER_SEQ_STEP,FMER_SEQ_PITCH,FMER_SEQ_VELOCITY,FMER_SEQ_GATE,
                                  FMER_SEQ_PATTERN,FMER_SEQ_CHAIN,FMER_SEQ_CHAIN_MASK})
            require(state.controls.value[parameter]==preserved.controls.value[parameter],"factory recall preserves performance, routing and FX controls");
        require(!std::memcmp(state.pitch,preserved.pitch,64) && !std::memcmp(state.velocity,preserved.velocity,64) &&
                !std::memcmp(state.gate,preserved.gate,64) && !std::memcmp(state.patterns,preserved.patterns,sizeof state.patterns) &&
                fmer_dsp_pattern_revision()>=pattern_revision && state.tracks[state.controls.value[FMER_SEQ_TRACK]].sound==64u+id && performance().running,
                "factory recall neither edits pattern nor interrupts sequencing");
    }
    fmer_dsp_panic();auto before=native_snapshot();
    require(!fmer_dsp_factory_preset(64) && !fmer_dsp_factory_name(64),"unknown factory slot refused");
    auto after=native_snapshot();require(native_values_equal(before,after) && before.source_generation==after.source_generation,"invalid recall preserves full state");
    // Device receives external channel5, while local keyboard remains usable.
    for(uint8_t source : {1,2}){
        fmer_dsp_midi(0x90,60,100,source);require(!fmer_dsp_active(),"wrong external channel note is ignored");
        before=native_snapshot();fmer_dsp_midi(0xc0,0,0,source);fmer_dsp_midi(0xb0,74,0,source);
        after=native_snapshot();require(native_values_equal(before,after) && before.source_generation==after.source_generation,"wrong channel program and performance CC cannot alter instrument");
        fmer_dsp_midi(0xc4,8,0,source);require(fmer_dsp_preset_id()==8,"matching external channel program selects intended zero-based factory slot");
        fmer_dsp_midi(0x94,60,100,source);fmer_dsp_midi(0x90,64,100,3);
        require(fmer_dsp_active()==2,"receive-channel filtering keeps independent external and local owners");
        fmer_dsp_midi(0x80,60,0,source);require(note_in(activity().gated_notes,60),"wrong channel off cannot stop accepted channel owner");
        fmer_dsp_midi(0x84,60,0,source);require(!note_in(activity().gated_notes,60) && note_in(activity().gated_notes,64),"accepted external off releases only its note");
        fmer_dsp_panic();
    }
    before=native_snapshot();fmer_dsp_midi(0xc4,127,0,1);after=native_snapshot();
    require(native_values_equal(before,after) && before.source_generation==after.source_generation,"unsupported program number is ignored without recall or state revision");
    for(uint8_t source : {1,2}) {
        fmer_dsp_midi(0xb4,74,0,source);require(snapshot().value[FMER_CUTOFF]==20,"CC74 reaches20Hz exactly");
        uint16_t previous=20;
        for(uint8_t value=1;value<127;++value){
            fmer_dsp_midi(0xb4,74,value,source);const auto hz=snapshot().value[FMER_CUTOFF];
            require(hz>=previous && hz<=20000,"CC74 logarithmic range remains monotonic and bounded");previous=hz;
            if(value==64)require(hz>=640 && hz<=660,"CC74 midpoint is musical logarithmic650Hz, not linear10kHz");
        }
        fmer_dsp_midi(0xb4,74,127,source);require(snapshot().value[FMER_CUTOFF]==20000,"CC74 upper endpoint is exact master bypass");
        for(uint8_t cc : {71,73,72}){
            const auto parameter=cc==71?FMER_RESONANCE:cc==73?FMER_ATTACK:FMER_RELEASE;
            fmer_dsp_midi(0xb4,cc,0,source);require(snapshot().value[parameter]==0,"performance CC lower endpoint exact");
            fmer_dsp_midi(0xb4,cc,127,source);require(snapshot().value[parameter]==fmer_control_max(parameter),"performance CC upper endpoint exact");
        }
    }
    require(fmer_dsp_sound_dirty(),"performance timbre CCs mark working sound edited");
    fmer_dsp_midi(0x94,60,100,1);fmer_dsp_midi(0x90,64,100,3);
    set(FMER_MIDI_CHANNEL,6);require(!fmer_dsp_active() && !performance().arp_held,"channel change retires prior owners instead of leaving unreceivable NoteOffs");
    set(FMER_MIDI_CHANNEL,0);fmer_dsp_midi(0x90,60,100,1);fmer_dsp_midi(0x9f,67,100,2);
    require(fmer_dsp_active()==2,"omni accepts both channel endpoints across USB and TRS adapters");
    fmer_dsp_panic();
    int32_t samples[256]{};const auto allocations_before=realtime_allocations;
    count_allocations=true;
    for(unsigned id=0;id<64;++id){
        fmer_dsp_midi(0xc0,static_cast<uint8_t>(id),0,1);
        fmer_dsp_midi(0x90,60,100,1);fmer_dsp_render(samples,128,1024);fmer_dsp_panic();
    }
    count_allocations=false;
    require(realtime_allocations==allocations_before,"program change, preset recall and audio allocate nothing after init");
    require(fmer_dsp_set_native(&baseline,fmer_dsp_state_generation()),"factory/MIDI full baseline restored");
    std::cout<<"707 factory/MIDI:64 recalls, names, preserved FX/pattern/playback, channel ownership, CC range and no allocation passed\n";
}
static void sixteen_pattern_queue_chain_and_native() {
    fmer_dsp_panic();const auto baseline=native_snapshot();auto bank=baseline;
    bank.controls.value[FMER_ARP_ENABLE]=0;bank.controls.value[FMER_TEMPO]=300;
    bank.controls.value[FMER_SEQ_PATTERN]=0;bank.controls.value[FMER_SEQ_CHAIN]=0;
    bank.controls.value[FMER_SEQ_CHAIN_MASK]=0x8003;bank.controls.value[FMER_SEQ_STEP]=0;
    for(unsigned id=0;id<16;++id) {
        auto* pitches=id?bank.patterns[id-1].pitch:bank.pitch;
        auto* velocities=id?bank.patterns[id-1].velocity:bank.velocity;
        auto* gates=id?bank.patterns[id-1].gate:bank.gate;
        if(id)bank.patterns[id-1].length=1;else bank.length=2;
        for(unsigned step=0;step<64;++step) {
            pitches[step]=static_cast<uint8_t>((60+id+step)%128);velocities[step]=100;gates[step]=75;
        }
    }
    bank.patterns[0].pitch[0]=64;
    bank.controls.value[FMER_SEQ_LENGTH]=2;bank.controls.value[FMER_SEQ_PITCH]=60;
    bank.controls.value[FMER_SEQ_VELOCITY]=100;bank.controls.value[FMER_SEQ_GATE]=75;
    require(fmer_dsp_set_native(&bank,fmer_dsp_state_generation()),"complete sixteen-pattern fixture applies");
    const auto original=native_snapshot();require(native_values_equal(bank,original),"all1024 retained step values round trip through real adapter");
    fmer_dsp_set_event_tap(tap);tapped_count=0;
    require(fmer_dsp_transport(FMER_TRANSPORT_PLAY),"bank0 sequence starts");audio(128);
    const auto first_frame=tapped[0].frame;const auto before_select=fmer_dsp_pattern_revision();
    set(FMER_SEQ_PATTERN,15);
    auto p=performance();fmer_pattern_state_t view{};fmer_dsp_get_pattern(&view);
    require(p.running&&p.selected_pattern==15&&p.playing_pattern==0&&p.queued_pattern==15&&
            view.pitch[0]==75&&view.selected_pattern==15&&fmer_dsp_pattern_revision()!=before_select,
            "edit selection publishes chosen bank while playing bank waits for boundary");
    set(FMER_SEQ_PITCH,79);set(FMER_SEQ_CHAIN,1);
    require(performance().playing_pattern==0&&performance().running,"editing queued inactive bank preserves playing pattern");
    const auto allocation_before=realtime_allocations;count_allocations=true;
    int32_t block[256]{};
    for(unsigned remaining=13231-128;remaining;) {
        const auto count=std::min(remaining,128u);fmer_dsp_render(block,count,1024);remaining-=count;
    }
    count_allocations=false;
    require(realtime_allocations==allocation_before,"sixteen-pattern boundary changes and chaining allocate nothing");
    const uint8_t expected[]={60,61,79,60,61,64,79};unsigned attacks=0;
    for(unsigned i=0;i<tapped_count;++i)if((tapped[i].status&0xf0)==0x90) {
        require(attacks<7&&tapped[i].note==expected[attacks]&&tapped[i].frame-first_frame==attacks*2205u,
                "actual adapter notes follow queued priority, pattern lengths and ascending chain at exact sample frames");
        ++attacks;
    }
    p=performance();require(attacks==7&&p.playing_pattern==15&&p.queued_pattern==16&&p.selected_pattern==15&&p.seq_position==0,
                           "performance snapshot distinguishes edit, play and consumed queue");
    set(FMER_SEQ_PATTERN,1);require(performance().queued_pattern==1,"new target visibly queues");
    fmer_dsp_transport(FMER_TRANSPORT_STOP);require(performance().queued_pattern==16&&!performance().running,"Stop cancels queued pattern");
    set(FMER_SEQ_PATTERN,0);set(FMER_SEQ_LENGTH,64);set(FMER_SEQ_STEP,63);
    set(FMER_SEQ_PATTERN,1);
    require(snapshot().value[FMER_SEQ_STEP]==0&&snapshot().value[FMER_SEQ_LENGTH]==1&&snapshot().value[FMER_SEQ_PITCH]==64,
            "shorter bank selection adopts its length and a valid cursor without overwriting its data");
    set(FMER_SEQ_PATTERN,14);set(FMER_SEQ_STEP,0);set(FMER_SEQ_PITCH,88);
    const auto selected=native_snapshot();require(selected.controls.value[FMER_SEQ_PATTERN]==14&&selected.patterns[13].pitch[0]==88&&
        selected.pitch[0]==60&&selected.patterns[14].pitch[0]==79,"native flat fields always mean bank0 and preserve independently edited banks");
    require(fmer_dsp_set_native(&selected,fmer_dsp_state_generation()),"native restores nonzero editor bank");
    const auto restored=native_snapshot();require(native_values_equal(selected,restored)&&performance().selected_pattern==14&&
        performance().playing_pattern==14&&performance().queued_pattern==16&&!performance().running,
        "nonzero-bank native restore keeps selected step exact and resets runtime transport");
    require(fmer_dsp_set_native(&baseline,fmer_dsp_state_generation()),"sixteen-pattern test restores complete prior state");
    fmer_dsp_set_event_tap(nullptr);
    std::cout<<"720 sixteen-pattern adapter: complete1024steps, queued boundary, bit15 chain, editing separation and no allocation passed\n";
}
static void activity_snapshots(const fmer_controls_t& defaults) {
    static_assert(sizeof(fmer_activity_state_t)==40,"bounded C activity snapshot");
    fmer_dsp_panic(); require(fmer_dsp_apply_controls(&defaults),"activity baseline restored");
    auto c=snapshot(); c.value[FMER_VOICE_BUDGET]=4;c.value[FMER_ENGINE]=1; c.value[FMER_ATTACK]=0;
    c.value[FMER_DECAY]=0; c.value[FMER_SUSTAIN]=100; c.value[FMER_RELEASE]=100;
    require(fmer_dsp_apply_controls(&c),"activity release fixture applied");
    for(uint8_t note:{0,31,64,127}) fmer_dsp_midi(0x90,note,100,1);
    auto s=activity();
    require(s.active_voices==4 && s.active_notes[0]==0x80000001u && s.active_notes[1]==0 &&
            s.active_notes[2]==1 && s.active_notes[3]==0x80000000u &&
            std::equal(s.active_notes,s.active_notes+4,s.gated_notes),"C snapshot preserves all128 pitch bits and gated voices");
    audio(128); fmer_dsp_midi(0x80,0,0,1); s=activity();
    require(note_in(s.active_notes,0) && !note_in(s.gated_notes,0),"C snapshot separates release tail from gate");
    fmer_dsp_midi(0xb0,64,127,1); fmer_dsp_midi(0x80,31,0,1);
    require(note_in(activity().gated_notes,31),"C snapshot retains sustained gate");
    fmer_dsp_midi(0xb0,64,0,1); s=activity();
    require(note_in(s.active_notes,31) && !note_in(s.gated_notes,31),"pedalup exposes active release tail");
    audio(5000); s=activity();
    require(s.active_voices==2 && !note_in(s.active_notes,0) && !note_in(s.active_notes,31),"finished voices leave C masks");
    fmer_dsp_panic();
    for(uint8_t note=60;note<=64;++note) fmer_dsp_midi(0x90,note,100,1);
    s=activity(); require(s.active_voices==4 && !note_in(s.active_notes,60) && note_in(s.gated_notes,64),
                         "C masks omit stolen owner that still has a held input");
    require(fmer_dsp_voice_budget(2),"activity budget reduction accepted"); s=activity();
    require(s.active_voices==2 && !note_in(s.active_notes,61) && !note_in(s.active_notes,62) &&
            note_in(s.gated_notes,63) && note_in(s.gated_notes,64),"C mask immediately reflects overload shedding");
    fmer_dsp_panic(); require(fmer_dsp_voice_budget(4),"activity budget restored");
    fmer_dsp_midi(0x90,60,100,1); fmer_dsp_midi(0x90,60,100,3); audio(128);
    fmer_dsp_midi(0x80,60,0,1); s=activity();
    require(s.active_voices==2 && note_in(s.gated_notes,60),"overlapping USB and local owners keep surviving gate bright");
    fmer_dsp_midi(0x80,60,0,3); s=activity();
    require(s.active_voices==2 && !note_in(s.gated_notes,60),"last overlapping off leaves tails only");
    fmer_dsp_panic(); s=activity();
    require(s.active_voices==0 && std::all_of(s.active_notes,s.active_notes+4,[](uint32_t x){return x==0;}) &&
            std::all_of(s.gated_notes,s.gated_notes+4,[](uint32_t x){return x==0;}),"panic clears C masks immediately");
    // Sequencer clock origin is Start tick0, not an arbitrary wall-clock phase.
    set(FMER_TEMPO,120); set(FMER_SEQ_LENGTH,1); set(FMER_SEQ_STEP,0);
    const auto saved_step=snapshot(); fmer_dsp_transport(FMER_TRANSPORT_CLEAR_STEP);
    require(!activity().beat_on,"stopped sequence has no beat pulse");
    fmer_dsp_transport(FMER_TRANSPORT_PLAY);
    require(activity().beat_on && activity().active_voices==0,"PLAY starts beat bright even on a rest");
    audio(3675); require(activity().beat_on,"firstfour PPQ ticks remain bright up to excluded boundary");
    audio(1); require(!activity().beat_on,"tick4 at frame3675 ends pulse exactly");
    audio(18374); require(!activity().beat_on,"nextquarter boundary remains exclusive at frame22050");
    audio(1); require(activity().beat_on,"tick24 at frame22050 restarts quarter pulse");
    fmer_dsp_transport(FMER_TRANSPORT_STOP); require(!activity().beat_on,"STOP clears pulse despite retained clock count");
    set(FMER_ARP_ENABLE,1); require(!activity().beat_on,"enabled idle arp has no fabricated sequence beat");
    fmer_dsp_midi(0x90,67,100,3); audio(1); s=activity();
    require(!s.beat_on && note_in(s.gated_notes,67),"arp rhythm uses actual gated pitches without a fake quarter clock");
    fmer_dsp_panic(); set(FMER_ARP_ENABLE,0);
    c=snapshot(); c.value[FMER_SEQ_PITCH]=saved_step.value[FMER_SEQ_PITCH];
    c.value[FMER_SEQ_VELOCITY]=saved_step.value[FMER_SEQ_VELOCITY]; c.value[FMER_SEQ_GATE]=saved_step.value[FMER_SEQ_GATE];
    require(fmer_dsp_apply_controls(&c),"rest step fixture restored");
    fmer_dsp_panic(); fmer_dsp_midi(0x90,69,100,1); const auto plain=audio(2048);
    fmer_dsp_panic(); fmer_dsp_midi(0x90,69,100,1);
    const auto before=performance(); const auto allocations_before=realtime_allocations;
    count_allocations=true;
    for(uint32_t i=0;i<1024;++i) { fmer_dsp_get_activity(&s); fmer_dsp_get_activity(nullptr); }
    count_allocations=false;
    const auto after=performance();
    require(realtime_allocations==allocations_before && std::memcmp(&before,&after,sizeof(before))==0,
            "repeated activity queries allocate nothing and leave musical state unchanged");
    require(plain==audio(2048),"activity queries preserve subsequent PCM exactly");
    fmer_dsp_panic(); require(fmer_dsp_apply_controls(&defaults),"activity controls restored");
    std::cout<<"706 activity:128 pitches, gates/tails/sustain/steals/owners, sequencer PPQ pulse and no allocation/audio change passed\n";
}
static void pattern_snapshots(const fmer_controls_t& defaults) {
    static_assert(sizeof(fmer_pattern_state_t) == 716, "bounded C pattern snapshot with four track cursors and count-in phase");
    set(FMER_RECORD_MODE,0);
    fmer_pattern_state_t initial{}, view{};
    fmer_dsp_get_pattern(&initial);
    require(initial.revision != 0 && initial.length == 16, "initial pattern has a valid revision and length");
    const uint8_t melody[] = {60,67,64,67,62,69,65,67};
    for (uint32_t i=0; i<FMER_PATTERN_STEPS; ++i) {
        require(initial.pitch[i] == (i<16 && !(i&1) ? melody[i/2] : FMER_REST),
                "snapshot reads original notes and all inactive trailing rests");
        require(initial.velocity[i] == 100 && initial.gate[i] == 75, "snapshot preserves every default step field");
    }
    fmer_dsp_get_pattern(nullptr);
    set(FMER_SEQ_STEP,1); fmer_dsp_transport(FMER_TRANSPORT_CLEAR_STEP);
    set(FMER_DELAY,1); set(FMER_DELAY,0); set(FMER_TEMPO,121); set(FMER_TEMPO,120);
    fmer_dsp_transport(FMER_TRANSPORT_PLAY); audio(512); fmer_dsp_transport(FMER_TRANSPORT_STOP);
    fmer_dsp_transport(FMER_TRANSPORT_RECORD); fmer_dsp_transport(FMER_TRANSPORT_STOP);
    set(FMER_ARP_ENABLE,1); set(FMER_ARP_ENABLE,0); fmer_dsp_panic();
    fmer_dsp_get_pattern(&view);
    require(!std::memcmp(view.pitch,initial.pitch,sizeof view.pitch) &&
            !std::memcmp(view.velocity,initial.velocity,sizeof view.velocity) &&
            !std::memcmp(view.gate,initial.gate,sizeof view.gate),
            "transport metadata updates preserve all pattern notes, velocities and gates");
    const auto before_edit=view.revision;
    set(FMER_SEQ_STEP,0);
    auto controls=snapshot(); controls.value[FMER_SEQ_PITCH]=64;
    controls.value[FMER_SEQ_VELOCITY]=71; controls.value[FMER_SEQ_GATE]=33;
    require(fmer_dsp_apply_controls(&controls),"pattern data batch accepted");
    fmer_dsp_get_pattern(&view);
    require(view.revision==before_edit+1 && view.pitch[0]==64 && view.velocity[0]==71 && view.gate[0]==33,
            "one pattern edit publishes actual pitch, velocity and gate under a new revision");
    const auto edited_revision=view.revision;
    fmer_dsp_transport(FMER_TRANSPORT_RECORD);
    fmer_dsp_midi(0x90,64,71,3); fmer_dsp_midi(0x80,64,0,3);
    require(fmer_dsp_pattern_revision()==edited_revision && performance().edit_step==1,
            "recording identical step advances cursor without invalidating unchanged pattern");
    set(FMER_SEQ_STEP,0);
    fmer_dsp_midi(0x90,73,94,3); fmer_dsp_midi(0x80,73,0,3);
    fmer_dsp_get_pattern(&view);
    require(view.revision==edited_revision+1 && view.pitch[0]==73 && view.velocity[0]==94 && view.gate[0]==33,
            "recorded pitch and velocity update the snapshot while preserving gate");
    fmer_dsp_panic();
    set(FMER_SEQ_LENGTH,64); set(FMER_SEQ_STEP,63);
    controls=snapshot(); controls.value[FMER_SEQ_PITCH]=127;
    controls.value[FMER_SEQ_VELOCITY]=127; controls.value[FMER_SEQ_GATE]=100;
    require(fmer_dsp_apply_controls(&controls),"last stored step is editable");
    const auto full_revision=fmer_dsp_pattern_revision();
    set(FMER_SEQ_STEP,0); set(FMER_SEQ_LENGTH,1);
    fmer_dsp_get_pattern(&view);
    require(view.length==1 && view.revision==full_revision+1 &&
            view.pitch[63]==127 && view.velocity[63]==127 && view.gate[63]==100,
            "shortening changes revision and retains exact inactive trailing step data");
    fmer_dsp_transport(FMER_TRANSPORT_CLEAR_STEP);
    fmer_dsp_get_pattern(&view);
    require(view.pitch[0]==FMER_REST && view.velocity[0]==94 && view.gate[0]==33,
            "clear reports rest without discarding velocity or gate");
    const auto cleared_revision=view.revision;
    fmer_dsp_transport(FMER_TRANSPORT_CLEAR_STEP);
    require(fmer_dsp_pattern_revision()==cleared_revision,"clearing a rest again leaves revision stable");
    controls=snapshot(); controls.value[FMER_SEQ_GATE]=0;
    require(!fmer_dsp_apply_controls(&controls),"invalid pattern batch rejected");
    fmer_pattern_state_t rejected{}; fmer_dsp_get_pattern(&rejected);
    require(std::memcmp(&view,&rejected,sizeof(view))==0,"rejected edit leaves complete pattern snapshot unchanged");
    // Restore stored contents, including hidden step63, before later tests.
    set(FMER_SEQ_LENGTH,64); set(FMER_SEQ_STEP,63);
    controls=snapshot(); controls.value[FMER_SEQ_PITCH]=FMER_REST;
    controls.value[FMER_SEQ_VELOCITY]=100; controls.value[FMER_SEQ_GATE]=75;
    require(fmer_dsp_apply_controls(&controls),"restore inactive step");
    set(FMER_SEQ_STEP,0); require(fmer_dsp_apply_controls(&defaults),"restore original visible pattern");
    fmer_dsp_get_pattern(&view);
    require(view.length==initial.length && !std::memcmp(view.pitch,initial.pitch,64) &&
            !std::memcmp(view.velocity,initial.velocity,64) && !std::memcmp(view.gate,initial.gate,64),
            "stored musical pattern restored exactly");
    // A UI reader may sample every block. It must never alter event/audio output.
    fmer_dsp_panic(); fmer_dsp_transport(FMER_TRANSPORT_PLAY);
    const auto untouched=audio(2048);
    fmer_dsp_panic(); fmer_dsp_transport(FMER_TRANSPORT_PLAY);
    int32_t sampled[4096]{};
    const auto allocations_before=realtime_allocations;
    count_allocations=true;
    for (unsigned block=0;block<16;++block) {
        fmer_dsp_get_pattern(&view);
        (void)fmer_dsp_pattern_revision();
        fmer_dsp_render(sampled+block*256,128,1024);
    }
    count_allocations=false;
    require(realtime_allocations==allocations_before,"pattern queries and render allocate nothing");
    require(std::equal(untouched.begin(),untouched.end(),sampled),"pattern reads leave rendered audio unchanged");
    require(fmer_dsp_pattern_revision()==view.revision,"playback and repeated snapshots keep pattern revision stable");
    fmer_dsp_panic();
    std::cout<<"705 pattern snapshots: all64 retained steps, revisions, record/clear/length, no allocation/audio change passed\n";
}
static void performance_controls(const fmer_controls_t& defaults) {
    fmer_dsp_panic();
    require(fmer_dsp_apply_controls(&defaults), "initial canonical defaults validate");
    // Repeated invalid edits must not become accepted by a warm validation
    // memo, and rejecting one must leave every other native value unchanged.
    for(unsigned id=0;id<FMER_PARAM_COUNT;++id) {
        if(fmer_control_valid(id,65535))continue;
        auto bad=defaults;bad.value[id]=65535;
        const auto before=native_snapshot();
        for(unsigned repeat=0;repeat<2;++repeat)
            require(!fmer_dsp_apply_controls(&bad),"repeated out-of-range edit rejected");
        require(native_values_equal(before,native_snapshot()),"rejected cached edit preserves native state");
    }
    auto cross=defaults;cross.value[FMER_SEQ_LENGTH]=16;cross.value[FMER_SEQ_STEP]=15;
    require(fmer_dsp_apply_controls(&cross),"valid cursor warms individual value checks");
    cross.value[FMER_SEQ_LENGTH]=8;cross.value[FMER_SEQ_STEP]=7;
    require(fmer_dsp_apply_controls(&cross),"second valid cursor updates memo");
    cross.value[FMER_SEQ_STEP]=15;
    require(!fmer_dsp_apply_controls(&cross),"cached legal values still obey cross-field constraints");
    require(fmer_dsp_apply_controls(&defaults),"restore defaults after validation memo checks");
    auto invalid = defaults; invalid.value[159] = 8;
    require(!fmer_dsp_apply_controls(&invalid), "reserved edit refused");
    invalid = defaults; invalid.value[FMER_ATTACK] = 10001; invalid.value[FMER_ENGINE] = 1;
    require(!fmer_dsp_apply_controls(&invalid), "whole invalid batch refused");
    auto unchanged = snapshot();
    require(std::memcmp(&unchanged,&defaults,sizeof(defaults))==0,"rejected batch leaves every control unchanged");
    invalid = defaults; invalid.value[FMER_ARP_RATE] = 3;
    require(!fmer_dsp_apply_controls(&invalid),"non-power-of-two arp rate rejected");
    invalid = defaults; invalid.value[FMER_SEQ_GATE] = 0;
    require(!fmer_dsp_apply_controls(&invalid),"zero sequence gate rejected");
    // Every control boundary must agree with the actual core setter, including
    // minimum vibrato rate0.1Hz (multiplication by0.01 can round below it).
    for(uint32_t id=160;id<FMER_PARAM_COUNT;++id) {
        for(uint32_t value : {fmer_control_min(id),fmer_control_max(id)}) {
            fmer_dsp_panic(); require(fmer_dsp_apply_controls(&defaults),"restore boundary baseline");
            auto c=snapshot();
            if(id==FMER_SEQ_STEP)c.value[FMER_SEQ_LENGTH]=64;
            c.value[id]=static_cast<uint16_t>(value);
            require(fmer_dsp_apply_controls(&c),"every shared control boundary is implemented");
            require(performance().performance_errors==0,"accepted boundary never fails inside core");
        }
    }
    fmer_dsp_panic(); require(fmer_dsp_apply_controls(&defaults),"restore performance defaults");
    auto c = snapshot(); c.value[FMER_ENGINE]=1; c.value[FMER_VA_WAVE]=0;
    c.value[FMER_ATTACK]=0; c.value[FMER_DECAY]=0; c.value[FMER_SUSTAIN]=100; c.value[FMER_RELEASE]=0;
    c.value[FMER_TEMPO]=300; c.value[FMER_SEQ_LENGTH]=1; c.value[FMER_SEQ_GATE]=50;
    require(fmer_dsp_apply_controls(&c),"deterministic sequence voice");
    fmer_dsp_set_event_tap(tap);tapped_count=0;
    require(fmer_dsp_transport(FMER_TRANSPORT_PLAY),"play starts actual core sequencer");
    const auto first=audio(1102,37);
    require(fmer_dsp_active()==1 && std::any_of(first.begin(),first.end(),[](int32_t x){return x!=0;}),"sequence sounds before exact gate boundary");
    audio(1); require(fmer_dsp_active()==0,"sequence gate releases on sample1102 inside a block");
    require(tapped_count==2 && tapped[0].source==4 && tapped[0].status==0x90 && tapped[1].status==0x80 &&
            tapped[1].frame-tapped[0].frame==1102,"generated tap reports admitted sample-exact gate edges");
    require(performance().running && performance().emitted_notes>0,"sequencer state reports actual events");
    fmer_dsp_panic(); fmer_dsp_transport(FMER_TRANSPORT_PLAY); const auto a=audio(13231,37);
    fmer_dsp_panic(); fmer_dsp_transport(FMER_TRANSPORT_PLAY); const auto b=audio(13231,128);
    require(a==b,"sequence render is invariant to audio chunk boundaries");
    fmer_dsp_panic();
    fmer_dsp_midi(0xb0,64,127,1); fmer_dsp_midi(0x90,69,100,1); fmer_dsp_midi(0x80,69,0,1);
    fmer_dsp_transport(FMER_TRANSPORT_PLAY); audio(1103);
    require(fmer_dsp_active()==1,"generator gates ignore live sustain while live owner remains held");
    fmer_dsp_transport(FMER_TRANSPORT_STOP);
    require(fmer_dsp_active()==1,"stopping sequence preserves unrelated sustained live owner");
    fmer_dsp_midi(0xb0,64,0,1); audio(1); require(fmer_dsp_active()==0,"pedal release still owns live voice");

    // Held input owners are independent even when the arp sees one pitch.
    set(FMER_ARP_ENABLE,1);
    fmer_dsp_midi(0x90,60,100,1); fmer_dsp_midi(0x90,60,90,3); audio(128);
    require(performance().arp_held==1 && fmer_dsp_active()==1,"arp deduplicates shared pitch");
    fmer_dsp_midi(0x80,60,0,1); require(performance().arp_held==1,"one input cannot release another input's arp pitch");
    set(FMER_ARP_ENABLE,0);
    require(fmer_dsp_active()==1,"disabling arp restores remaining live owner");
    fmer_dsp_midi(0x80,60,0,3); audio(1); require(fmer_dsp_active()==0,"restored live owner releases normally");
    fmer_dsp_midi(0x90,64,100,1); fmer_dsp_midi(0x90,64,100,3);
    set(FMER_ARP_ENABLE,1); audio(128); set(FMER_ARP_ENABLE,0);
    require(fmer_dsp_active()==2,"toggle restores two independent live owners of same pitch");
    fmer_dsp_midi(0x80,64,0,1); audio(1); require(fmer_dsp_active()==1,"restored owner release remains isolated");
    fmer_dsp_midi(0x80,64,0,3); audio(1); require(fmer_dsp_active()==0,"all restored notes release");

    set(FMER_ARP_LATCH,1); set(FMER_ARP_ENABLE,1);
    fmer_dsp_midi(0x90,60,100,1); fmer_dsp_midi(0x80,60,0,1); audio(128);
    require(performance().arp_held==1,"latch keeps released chord");
    fmer_dsp_midi(0x90,64,100,1); require(performance().arp_held==1,"new physical chord replaces latch");
    fmer_dsp_midi(0xb0,123,0,1); audio(128);
    require(performance().arp_held==0 && fmer_dsp_active()==0,"all notes off clears latched chord");
    set(FMER_ARP_LATCH,0);
    fmer_dsp_midi(0xb2,64,127,1); fmer_dsp_midi(0x92,60,100,1); fmer_dsp_midi(0x82,60,0,1);
    fmer_dsp_midi(0xb2,123,0,1); audio(128);
    require(performance().arp_held==1,"arp input sustain survives all notes off");
    fmer_dsp_midi(0xb2,64,0,1); audio(5000);
    require(performance().arp_held==0 && fmer_dsp_active()==0,"arp pedal up terminates generated output");
    // All seven real order modes, triplets and swing stay bounded at extremes.
    for(uint16_t order=0;order<10;++order) {
        fmer_dsp_panic(); set(FMER_ARP_ORDER,order); set(FMER_ARP_RATE,32);
        set(FMER_ARP_OCTAVES,4); set(FMER_ARP_TRIPLET,1); set(FMER_ARP_SWING,75);
        fmer_dsp_midi(0x90,36,100,1); fmer_dsp_midi(0x90,40,100,1); fmer_dsp_midi(0x90,43,100,1);
        const auto notes_before=performance().emitted_notes;
        audio(10000,128);
        require(performance().emitted_notes>notes_before && fmer_dsp_active()<=fmer_dsp_voice_limit(),"every arp order runs bounded notes");
        fmer_dsp_midi(0xb0,120,0,1); audio(5000);
        require(performance().arp_held==0 && fmer_dsp_active()==0,"all sound off clears each arp mode");
    }
    require(performance().generated_drops>0,"repeat admission exposes dropped expanded attacks");
    fmer_dsp_panic();set(FMER_ARP_ORDER,6);tapped_count=0;
    fmer_dsp_midi(0x90,36,100,1);fmer_dsp_midi(0x90,40,100,1);fmer_dsp_midi(0x90,43,100,1);
    audio(128);fmer_dsp_panic();
    const auto admitted=fmer_dsp_voice_limit();require(tapped_count==2*admitted,"tap emits only admitted Repeat attacks and matching releases");
    for(uint32_t i=0;i<admitted;++i)require(tapped[i].source==5 && tapped[i].status==0x90 &&
            tapped[i+admitted].status==0x80 && tapped[i].note==tapped[i+admitted].note,"tap never emits orphan dropped-note releases");
    fmer_dsp_set_event_tap(nullptr);

    fmer_dsp_panic(); set(FMER_RECORD_MODE,0);set(FMER_SEQ_LENGTH,4); set(FMER_SEQ_STEP,0);
    require(fmer_dsp_transport(FMER_TRANSPORT_RECORD),"REC enters actual step-entry mode");
    fmer_dsp_midi(0x90,72,87,3); fmer_dsp_midi(0x80,72,0,3);
    require(performance().recording && performance().edit_step==1,"recorded note advances edit cursor");
    set(FMER_DRIVE,1); require(performance().edit_step==1,"unrelated edit preserves recorded cursor");
    set(FMER_SEQ_STEP,0);
    require(snapshot().value[FMER_SEQ_PITCH]==72 && snapshot().value[FMER_SEQ_VELOCITY]==87,"step selection returns actual recorded data");
    require(fmer_dsp_transport(FMER_TRANSPORT_CLEAR_STEP),"clear step command");
    require(snapshot().value[FMER_SEQ_PITCH]==FMER_REST,"clear step becomes explicit rest");
    require(fmer_dsp_transport(FMER_TRANSPORT_PLAY),"play exits step entry");
    require(!performance().recording && performance().running && !snapshot().value[FMER_ARP_ENABLE],"sequence/arp transport modes are exclusive");
    set(FMER_ARP_ENABLE,1); require(performance().running,"single-instrument arp joins the running pattern");
    require(!fmer_dsp_transport(999),"unknown transport refused");

    fmer_dsp_panic(); require(fmer_dsp_apply_controls(&defaults),"restore final allocation baseline");
    c=snapshot(); c.value[FMER_ENGINE]=1; c.value[FMER_LFO_DEPTH]=100;
    c.value[FMER_DRIVE]=50;c.value[FMER_CHORUS]=30;c.value[FMER_DELAY]=30;
    c.value[FMER_REVERB]=30;c.value[FMER_PHASER]=50;c.value[FMER_CUTOFF]=5000;
    require(fmer_dsp_apply_controls(&c),"all effects and vibrato implemented");
    int32_t samples[256]{};
    const auto start=std::chrono::steady_clock::now();
    count_allocations=true;
    for(unsigned pass=0;pass<100;++pass) {
        fmer_dsp_midi(0x90,60,100,1); fmer_dsp_midi(0x90,64,100,1);
        fmer_dsp_midi(0x90,67,100,1); fmer_dsp_midi(0x90,72,100,1);
        for(unsigned block=0;block<8;++block)fmer_dsp_render(samples,128,1024);
        fmer_dsp_apply_controls(&c); fmer_dsp_panic();
        fmer_dsp_transport(FMER_TRANSPORT_PLAY);fmer_dsp_render(samples,128,1024);
        fmer_dsp_transport(FMER_TRANSPORT_RECORD);fmer_dsp_midi(0x90,60,100,3);
        fmer_dsp_transport(FMER_TRANSPORT_STOP);fmer_dsp_panic();
    }
    count_allocations=false;
    require(realtime_allocations==0,"MIDI, controls, generators, effects and panic allocate nothing after init");
    require(performance().performance_errors==0,"all valid performance workflows retain zero core errors");
    std::cout<<"704 adapter: controls/sequence/arp/step-record/no-allocation stress (host elapsed ms, not target timing): "
             <<std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now()-start).count()<<'\n';
}
static void banked_midi() {
    fmer_dsp_panic();auto original=native_snapshot();auto fixture=original;
    fixture.controls.value[FMER_MIDI_CHANNEL]=0;fixture.controls.value[FMER_SEQ_MODE]=0;
    require(fmer_dsp_set_native(&fixture,fmer_dsp_state_generation()),"bank MIDI fixture");
    std::array<uint8_t,FMER_NATIVE_BYTES> wire{};require(fmer_dsp_original_default(8,wire.data()),"user cache fixture");fmer_dsp_cache_sound(5,wire.data());
    fmer_dsp_midi(0xb0,0,1,1);fmer_dsp_midi(0xb0,32,0,1);fmer_dsp_midi(0xc0,5,0,1);
    require(native_snapshot().controls.value[FMER_TRACK_SOUND]==5,"bank1 program5 selects USER6");
    fmer_dsp_midi(0xc0,6,0,2);require(native_snapshot().controls.value[FMER_TRACK_SOUND]==70,"TRS bank independent of USB");
    fmer_dsp_midi(0xc1,7,0,1);require(native_snapshot().controls.value[FMER_TRACK_SOUND]==71,"channels keep separate bank state");
    fmer_dsp_midi(0xb0,32,1,1);const auto before=native_snapshot();fmer_dsp_midi(0xc0,5,0,1);
    require(native_values_equal(before,native_snapshot()),"unsupported bank LSB leaves sound intact");
    fmer_dsp_midi(0xb0,32,0,1);fmer_dsp_midi(0xc0,63,0,1);
    require(native_values_equal(before,native_snapshot()),"empty USER slot leaves sound intact");
    for(auto cc:{12,91,93,95})fmer_dsp_midi(0xb0,static_cast<uint8_t>(cc),127,1);
    auto sends=native_snapshot();for(auto id:{FMER_DELAY,FMER_REVERB,FMER_CHORUS,FMER_PHASER})require(sends.controls.value[id]==100,"shared effects accept full-scale MIDI sends");
    fixture.controls.value[FMER_SEQ_MODE]=1;require(fmer_dsp_set_native(&fixture,fmer_dsp_state_generation()),"four-track MIDI fixture");
    const auto tracks_before=native_snapshot();fmer_dsp_midi(0xb2,0,1,1);fmer_dsp_midi(0xc2,5,0,1);
    auto changed=native_snapshot();require(changed.tracks[2].sound==5,"banked PC selects only addressed unselected track");
    for(int t:{0,1,3})require(changed.tracks[t].sound==tracks_before.tracks[t].sound,"other track assignments survive PC");
    fmer_dsp_midi(0xb0,0,0,1);fmer_dsp_midi(0xb2,0,0,1);fmer_dsp_cache_sound(5,nullptr);
    require(fmer_dsp_set_native(&original,fmer_dsp_state_generation()),"restore bank MIDI fixture");
}
int main() {
    try {
        fmer_pattern_state_t unavailable{};
        fmer_dsp_get_pattern(&unavailable);
        fmer_activity_state_t no_activity{};
        std::fill_n(no_activity.active_notes,4,UINT32_MAX);
        fmer_dsp_get_activity(&no_activity);
        require(!no_activity.active_voices && !no_activity.beat_on &&
                std::all_of(no_activity.active_notes,no_activity.active_notes+4,[](uint32_t x){return x==0;}) &&
                std::all_of(no_activity.gated_notes,no_activity.gated_notes+4,[](uint32_t x){return x==0;}),
                "activity before initialization is empty");
        require(fmer_dsp_pattern_revision()==0 && unavailable.revision==0 && unavailable.length==0,
                "uninitialized pattern snapshot advertises unavailable state");
        require(fmer_dsp_init() == 1, "real core initialization");
        require(fmer_dsp_init() == 1, "initialization is idempotent");
        const auto defaults = snapshot();
        // Reapplying the advertised boot patch must not secretly alter its sound.
        fmer_dsp_midi(0x90,69,100,1); const auto initial_audio=audio(2048); fmer_dsp_panic();
        require(fmer_dsp_apply_controls(&defaults),"canonical boot snapshot can be reapplied");
        fmer_dsp_midi(0x90,69,100,1);
        require(initial_audio==audio(2048),"canonical boot FM readback reproduces the actual initial DSP sound");
        fmer_dsp_panic();
        pattern_snapshots(defaults);
        require(fmer_dsp_voice_limit() == 6, "board advertises six-voice budget");
        require(!fmer_dsp_voice_budget(0) && !fmer_dsp_voice_budget(7) && !fmer_dsp_voice_budget(13),"board budget outside1..6 refused");
        require(!fmer_dsp_voice_controls(5,5,200) && !fmer_dsp_voice_controls(1,10001,200) &&
                !fmer_dsp_voice_controls(1,5,10001),"invalid VA controls refused");
        require(fmer_dsp_voice_controls(4,5,200),"VA noise waveform accepted");
        require(fmer_dsp_voice_controls(1,5,200),"VA waveform/envelope controls accepted");
        std::array<int32_t, 258> stereo{};
        stereo[256] = 12345; stereo[257] = -6789;
        auto patch = fmer::make_init_patch();
        require(!fmer_dsp_patch(nullptr,155), "null patch rejected");
        require(!fmer_dsp_patch(patch.vced.data(),154), "short patch rejected");
        require(fmer_dsp_patch(patch.vced.data(),155), "valid init patch accepted");
        auto invalid = patch; invalid.vced[134] = 32;
        require(!fmer_dsp_patch(invalid.vced.data(),155), "invalid algorithm rejected");
        require(!fmer_dsp_parameter(134,32), "invalid parameter rejected");
        require(!fmer_dsp_parameter(145,0), "name is not numeric parameter");
        require(fmer_dsp_parameter(134,31), "valid algorithm accepted");
        fmer_dsp_midi(0x90,60,100,1);
        fmer_dsp_midi(0x90,64,100,3);
        require(fmer_dsp_active() == 2, "USB and panel note ownership");
        long long energy=0;
        for (int block=0;block<30;++block) {
            fmer_dsp_render(stereo.data(),128,1024);
            for(int i=0;i<256;i+=2) {
                require(stereo[i]==stereo[i+1],"stereo duplication");
                require(std::abs(stereo[i])<=16384,"first bench output gain ceiling");
                energy+=std::abs(stereo[i]);
            }
        }
        require(energy>0,"FM output reaches the board boundary");
        require(stereo[256]==12345 && stereo[257]==-6789,"DMA block boundary preserved");
        fmer_dsp_panic(); fmer_dsp_render(stereo.data(),128,1024);
        require(std::all_of(stereo.begin(),stereo.begin()+256,[](int32_t x){return x==0;}),"panic clears audio and tails");
        for(uint8_t note=60;note<68;++note)fmer_dsp_midi(0x90,note,100,1);
        require(fmer_dsp_active()==6 && fmer_dsp_stolen()==2,"excess board notes steal within advertised budget");
        require(fmer_dsp_voice_budget(3) && fmer_dsp_active()==3 && fmer_dsp_stolen()==5,
                "overload mitigation reduces voices without silencing all sound");
        fmer_dsp_render(stereo.data(),128,1024);
        require(std::any_of(stereo.begin(),stereo.begin()+256,[](int32_t x){return x!=0;}),"remaining chord stays audible after shedding");
        fmer_dsp_panic(); require(fmer_dsp_voice_budget(4),"board budget restored explicitly");
        require(!fmer_dsp_controls(2,2000,0),"invalid engine rejected");
        require(!fmer_dsp_controls(1,19,0),"invalid cutoff rejected");
        require(!fmer_dsp_controls(1,2000,101),"invalid effect mix rejected");
        require(fmer_dsp_controls(1,20000,0),"20 kHz master bypass accepted for VA");
        require(fmer_dsp_controls(1,2000,0),"valid master controls accepted");
        fmer_dsp_midi(0x90,69,100,1);
        energy=0;
        for(int i=0;i<30;++i) {
            fmer_dsp_render(stereo.data(),128,1024);
            for(int j=0;j<256;++j) energy+=std::abs(stereo[j]);
        }
        require(energy>0,"VA output reaches the board boundary");
        const auto measure_filter = [&](uint32_t hz) {
            fmer_dsp_panic();
            require(fmer_dsp_controls(1,hz,0),"filter setting accepted");
            fmer_dsp_midi(0x90,69,100,1);
            long long measured=0;
            for(int block=0;block<80;++block) {
                fmer_dsp_render(stereo.data(),128,1024);
                if(block>=70) for(int j=0;j<256;++j) measured+=std::abs(stereo[j]);
            }
            return measured;
        };
        const auto open=measure_filter(20000), closed=measure_filter(20);
        require(open>0 && closed<open/5,"master cutoff audibly affects the actual signal");
        fmer_dsp_render(stereo.data(),128,0);
        require(std::all_of(stereo.begin(),stereo.begin()+256,[](int32_t x){return x==0;}),"zero master gain is silent");
        stereo[0]=91; fmer_dsp_render(stereo.data(),129,1024);
        require(stereo[0]==91,"oversized render rejected");
        performance_controls(defaults);
        activity_snapshots(defaults);
        native_state_roundtrip();factory_and_external_midi();banked_midi();sixteen_pattern_queue_chain_and_native();
        std::cout << "Board DSP boundary: FM/VA, patch rejection, gain, panic and buffer bounds passed\n";
        return 0;
    } catch(const std::exception& error) { std::cerr<<error.what()<<'\n'; return 1; }
}
