// Actual board DSP boundary, portable host evidence only; no WL82 emulation.
#include "../firmware/fm1/dsp_adapter.h"
#include "../firmware/fm1/panel_model.h"
#include "factory_presets.hpp"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <new>
#include <stdexcept>
#include <vector>

std::size_t adapter_multitrack_allocations{};
void* operator new(std::size_t n){++adapter_multitrack_allocations;if(auto* p=std::malloc(n?n:1))return p;throw std::bad_alloc();}
void* operator new[](std::size_t n){return ::operator new(n);}
void operator delete(void* p) noexcept{std::free(p);}
void operator delete[](void* p) noexcept{std::free(p);}
void operator delete(void* p,std::size_t) noexcept{std::free(p);}
void operator delete[](void* p,std::size_t) noexcept{std::free(p);}

namespace {
void check(bool okay,const char* message){if(!okay)throw std::runtime_error(message);}
struct Midi {std::uint64_t frame;std::uint8_t status,a,b;};
struct Tap {std::uint32_t frame;std::uint8_t status,note,velocity,source;};
std::array<Midi,8192> midi{};std::size_t midi_count{};
std::array<Tap,8192> tapped{};std::size_t tap_count{};
std::uint64_t now{};
fmer_native_state_t initial{};
int midi_output(uint8_t status,uint8_t a,uint8_t b){if(midi_count<midi.size())midi[midi_count++]={now,status,a,b};return 1;}
void tap(uint32_t frame,uint8_t status,uint8_t a,uint8_t b,uint8_t source){if(tap_count<tapped.size())tapped[tap_count++]={frame,status,a,b,source};}
fmer_controls_t controls(){fmer_controls_t c{};fmer_dsp_get_controls(&c);return c;}
fmer_native_state_t native(){fmer_native_state_t s{};fmer_dsp_get_native(&s);return s;}
fmer_pattern_state_t pattern(){fmer_pattern_state_t p{};fmer_dsp_get_pattern(&p);return p;}
fmer_performance_state_t performance(){fmer_performance_state_t s{};fmer_dsp_performance(&s);return s;}
void apply(const fmer_controls_t& c){check(fmer_dsp_apply_controls(&c)!=0,"control batch accepted");}
void set(unsigned id,unsigned value){auto c=controls();c.value[id]=static_cast<std::uint16_t>(value);apply(c);}
void restore(const fmer_native_state_t& s) {
    check(fmer_native_state_valid(&s)==FMER_NATIVE_OK,"fixture is a valid native scene");
    check(fmer_dsp_set_native(&s,fmer_dsp_state_generation())!=0,"native scene restore accepted");
}
double render(unsigned frames,std::vector<float>* samples=nullptr) {
    std::array<int32_t,256> pcm{};double energy=0;
    for(unsigned i=0;i<frames;) {
        const auto count=std::min(128u,frames-i);fmer_dsp_render(pcm.data(),count,1024);now+=count;i+=count;
        for(unsigned n=0;n<count;++n){const auto v=pcm[n*2]/16384.f;energy+=v*v;if(samples)samples->push_back(v);}
    }
    return energy;
}
void midi_config(bool external=false) {
    fmer_midi_settings_t s{};fmer_midi_defaults(&s);s.value[FMER_MIDI_ROUTE]=2;s.value[FMER_MIDI_TX_CHANNEL]=10;
    s.value[FMER_MIDI_CLOCK_SOURCE]=external?1:0;s.value[FMER_MIDI_TRANSPORT_RX]=1;
    check(fmer_dsp_set_midi_settings(&s)!=0,"MIDI config accepted");
}
void reset() {fmer_dsp_panic();midi_config();restore(initial);midi_count=tap_count=0;}
fmer_native_state_t scene(unsigned length=4) {
    auto s=initial;s.controls.value[FMER_SEQ_MODE]=1;s.controls.value[FMER_SEQ_TRACK]=0;
    s.controls.value[FMER_SEQ_PATTERN]=0;s.controls.value[FMER_SEQ_STEP]=0;s.controls.value[FMER_SEQ_LENGTH]=static_cast<uint16_t>(length);
    s.controls.value[FMER_SEQ_PITCH]=60;s.controls.value[FMER_SEQ_VELOCITY]=100;s.controls.value[FMER_SEQ_GATE]=75;
    s.controls.value[FMER_TRACK_SOUND]=64;s.controls.value[FMER_TRACK_LEVEL]=100;s.controls.value[FMER_TRACK_MUTE]=0;
    s.controls.value[FMER_VOICE_BUDGET]=4;s.controls.value[FMER_RECORD_MODE]=0;
    s.controls.value[FMER_TEMPO]=120;s.controls.value[FMER_ARP_ENABLE]=0;
    for(unsigned bank=0;bank<FMER_PATTERN_BANKS;++bank) {
        auto* pitch=bank?s.patterns[bank-1].pitch:s.pitch;auto* velocity=bank?s.patterns[bank-1].velocity:s.velocity;auto* gate=bank?s.patterns[bank-1].gate:s.gate;
        if(bank)s.patterns[bank-1].length=static_cast<std::uint8_t>(length);else s.length=static_cast<std::uint8_t>(length);
        std::fill_n(pitch,64,FMER_REST);std::fill_n(velocity,64,100);std::fill_n(gate,64,75);
        for(unsigned step=0;step<length;++step)pitch[step]=static_cast<std::uint8_t>(60+step);
    }
    for(unsigned t=0;t<4;++t){s.tracks[t].pattern=static_cast<uint8_t>(t);s.tracks[t].chain_mask=0;
        s.tracks[t].sound=static_cast<uint8_t>(64+(t%2?8:0));s.tracks[t].level=100;s.tracks[t].mute=0;}
    return s;
}
std::size_t sent(unsigned kind,unsigned channel,unsigned pitch=255) {
    return std::count_if(midi.begin(),midi.begin()+midi_count,[=](auto e){return (e.status&0xf0)==kind && (e.status&15)==channel && (pitch==255 || e.a==pitch);});
}
void global_polyphony_escape() {
    reset();restore(scene());auto before=native();auto c=controls();fmer_panel_t panel{};fmer_panel_init(&panel);
    panel.family=FMER_PANEL_GLO;panel.page[panel.family]=FMER_GLO_VOICE;
    check(!fmer_panel_encoder(&panel,4,1,&c,100) && c.value[FMER_SEQ_MODE],"VOICES stays locked in four-track mode");
    panel.fine_adjust=1;fmer_panel_button(&panel,8,&c,101);panel.fine_adjust=0;apply(c);
    for(unsigned n: {60u,64u,67u,71u})fmer_dsp_midi(0x90,static_cast<uint8_t>(n),100,3);
    check(render(256)>.0001 && fmer_dsp_active()==4,"four held local keys sound simultaneously after SEL HOME mode shortcut");
    fmer_dsp_panic();auto after=native();check(std::memcmp(before.tracks,after.tracks,sizeof before.tracks)==0,"switching to polyphony preserves all track settings");
    c=controls();panel.fine_adjust=1;fmer_panel_button(&panel,8,&c,200);panel.fine_adjust=0;apply(c);
    fmer_dsp_transport(FMER_TRANSPORT_PLAY);check(render(256)>.0001 && fmer_dsp_active()==4,"return to four-track mode restores simultaneous parts");
}
void single_song_keys_and_arp() {
    reset();auto s=scene(4);s.controls.value[FMER_SEQ_MODE]=0;
    s.song.length[0]=2;s.song.enabled[0]=1;s.song.loop[0]=1;s.song.rows[0][0]={0,0,0};s.song.rows[0][1]={1,12,0};
    restore(s);const auto saved=native();const auto errors=performance().performance_errors;
    check(fmer_dsp_transport(fmer_song_command(0,0,2,1)),"single instrument accepts song edits");
    fmer_dsp_transport(FMER_TRANSPORT_PLAY);check(render(256)>.001,"one song lane sounds in single mode");
    check(fmer_dsp_active()==1,"one mono pattern reserves just one live voice");
    for(unsigned n:{80u,84u,87u})fmer_dsp_midi(0x90,n,100,3);
    check(render(256)>.001 && fmer_dsp_active()==4,"three live notes fill remaining polyphony over song");
    for(unsigned n:{80u,84u,87u})fmer_dsp_midi(0x80,n,0,3);
    set(FMER_ARP_ENABLE,1);fmer_dsp_midi(0x90,84,100,3);tap_count=0;
    check(render(88200)>.001 && performance().running,"arp joins song without stopping it");
    unsigned seq=0,arp=0;uint32_t previous=0;
    for(size_t i=0;i<tap_count;i++){check(tapped[i].frame>=previous,"combined events remain chronological");previous=tapped[i].frame;
        if((tapped[i].status&240)==144){seq+=tapped[i].source==4;arp+=tapped[i].source==5;}}
    check(seq>2 && arp>2,"both generators contribute actual notes");
    check(performance().performance_errors==errors,"combined playback has no scheduler errors");
    check(!std::memcmp(native().tracks,saved.tracks,sizeof saved.tracks),"single playback preserves four-part assignments");
    set(FMER_ARP_ENABLE,0);check(performance().running,"disabling arp preserves pattern transport");
}
void navigation_keeps_single_song_playable() {
    reset();auto s=scene(16);s.controls.value[FMER_SEQ_MODE]=0;s.song.length[0]=1;
    s.song.enabled[0]=1;s.song.loop[0]=1;s.song.rows[0][0]={0,0,0};restore(s);
    fmer_panel_t panel;fmer_panel_init(&panel);auto c=controls();fmer_panel_button(&panel,11,&c,0);apply(c);
    check(panel.page[FMER_PANEL_SEQ]==8 && !c.value[FMER_SEQ_MODE],"single instrument SEQ opens its own Song without allocation change");
    fmer_dsp_transport(FMER_TRANSPORT_PLAY);render(256);
    for(unsigned n:{80u,84u,87u})fmer_dsp_midi(0x90,n,100,3);
    for(unsigned page=0;page<8;page++) {
        const auto before=performance();c=controls();fmer_panel_button(&panel,11,&c,100+page);apply(c);
        check(performance().running && performance().seq_position==before.seq_position,"every page navigation retains playing transport and current step");
        check(render(128)>.001 && fmer_dsp_active()==4,"song plus three physical-source held keys remain audible on every V-mode page");
    }
    check(panel.page[FMER_PANEL_SEQ]==8 && !controls().value[FMER_SEQ_MODE],"full menu cycle returns to single-track Song");
    fmer_panel_section_home(&panel,11,&c);apply(c);
    check(performance().running && render(128)>.001 && fmer_dsp_active()==4,"section-home hold also preserves live polyphony and song audio");
    for(unsigned n:{80u,84u,87u})fmer_dsp_midi(0x80,n,0,3);
    panel.family=FMER_PANEL_PRESETS;const auto position=performance().seq_position;
    c=controls();fmer_panel_encoder(&panel,0,-1,&c,1000);apply(c);
    check(performance().running && performance().seq_position==position && controls().value[FMER_VOICE_BUDGET]==1,"4V to1V keeps the single-instrument song running at its current step");
    c=controls();fmer_panel_encoder(&panel,0,1,&c,1001);apply(c);
    check(performance().running && performance().seq_position==position && controls().value[FMER_VOICE_BUDGET]==6,"1V to6V preserves transport rather than restarting the song");
}
void explicit_mode_wheel_audio() {
    reset();restore(scene());const auto saved=native();fmer_panel_t panel;fmer_panel_init(&panel);panel.family=FMER_PANEL_PRESETS;
    auto c=controls();check(fmer_panel_encoder(&panel,0,-1,&c,1)!=0,"mode wheel exits4T");apply(c);
    check(!controls().value[FMER_SEQ_MODE] && controls().value[FMER_VOICE_BUDGET]==6,"mode wheel reconciles six-voice DSP allocator");
    for(unsigned n:{60u,64u,67u,71u,74u,77u})fmer_dsp_midi(0x90,n,100,3);
    check(render(256)>.001 && fmer_dsp_active()==6,"six-voice wheel choice plays physical-source chord");fmer_dsp_panic();
    c=controls();check(fmer_panel_encoder(&panel,0,-1,&c,2)!=0,"mode wheel enters1V");apply(c);
    check(!controls().value[FMER_SEQ_MODE] && controls().value[FMER_VOICE_BUDGET]==1 && controls().value[FMER_GLIDE_MODE]==1,"mono wheel choice is valid legato allocation");
    for(unsigned n:{60u,64u})fmer_dsp_midi(0x90,n,100,3);
    check(render(256)>.001 && fmer_dsp_active()==1,"mono wheel choice renders one glide voice");fmer_dsp_panic();
    c=controls();check(fmer_panel_encoder(&panel,0,1,&c,3)!=0,"mode wheel restores6V");apply(c);
    check(controls().value[FMER_VOICE_BUDGET]==6 && !controls().value[FMER_GLIDE_MODE],"leaving1V restores six voices despite automatic glide memory");
    c=controls();check(fmer_panel_encoder(&panel,0,1,&c,4)!=0,"mode wheel restores4T");apply(c);
    fmer_dsp_transport(FMER_TRANSPORT_PLAY);check(render(256)>.001 && fmer_dsp_active()==4,"return to4T plays every saved part");
    check(!std::memcmp(saved.tracks,native().tracks,sizeof saved.tracks),"mode round trip preserves saved track instruments, patterns and mixer state");
}
void explicit_poly_choice_overrides_glide_resume() {
    for(unsigned previous:{2u,3u})for(unsigned path=0;path<7;path++) {
        reset();auto s=scene();s.controls.value[FMER_SEQ_MODE]=0;s.controls.value[FMER_GLIDE_MODE]=0;
        s.controls.value[FMER_VOICE_BUDGET]=(uint16_t)previous;restore(s);set(FMER_GLIDE_MODE,1);
        check(controls().value[FMER_VOICE_BUDGET]==1,"normal glide toggle remembers prior polyphony and admits one voice");
        fmer_panel_t panel;fmer_panel_init(&panel);auto c=controls();unsigned expected=6;
        if(path==0){c.value[FMER_GLIDE_MODE]=0;expected=previous;}
        else if(path==1){panel.family=FMER_PANEL_PRESETS;check(fmer_panel_encoder(&panel,0,1,&c,0)!=0,"preset mode wheel explicitly requests6V");}
        else if(path==2){panel.family=FMER_PANEL_SEQ;panel.page[panel.family]=3;check(fmer_panel_encoder(&panel,2,1,&c,0)!=0,"sequencer mode wheel explicitly requests6V");}
        else if(path==3){panel.family=FMER_PANEL_GLO;panel.page[panel.family]=FMER_GLO_VOICE;check(fmer_panel_encoder(&panel,2,1,&c,0)!=0,"global mode wheel explicitly requests6V");}
        else if(path==4)fmer_panel_shortcut(&panel,&c,3);
        else if(path==5){panel.fine_adjust=1;fmer_panel_button(&panel,8,&c,0);apply(c);c=controls();fmer_panel_button(&panel,8,&c,1);}
        else {c.value[FMER_GLIDE_MODE]=0;c.value[FMER_VOICE_BUDGET]=(uint16_t)(previous==2?3:2);expected=c.value[FMER_VOICE_BUDGET];}
        apply(c);const auto actual=controls();
        check(!actual.value[FMER_SEQ_MODE] && !actual.value[FMER_GLIDE_MODE] && actual.value[FMER_VOICE_BUDGET]==expected,
            "explicit nonmono choice overrides glide resume; an ordinary off toggle alone restores previous budget");
        for(unsigned n:{60u,64u,67u,71u,74u,77u})fmer_dsp_midi(0x90,n,100,3);
        check(render(256)>.001 && fmer_dsp_active()==expected,"reconciled budget controls the actual audible allocator");
    }
}
void patch_browse_preserves_mode() {
    for(unsigned mode=0;mode<3;mode++){
        reset();auto s=scene();s.controls.value[FMER_SEQ_MODE]=mode==2;s.controls.value[FMER_GLIDE_MODE]=mode==1?1:0;
        s.controls.value[FMER_VOICE_BUDGET]=mode==1?1:4;restore(s);
        for(unsigned slot=64;slot<128;slot++){check(fmer_dsp_audition(slot),"factory audition works");auto c=controls();
            check(c.value[FMER_SEQ_MODE]==(mode==2) && c.value[FMER_VOICE_BUDGET]==(mode==1?1:4),"patch browse preserves playing allocation");
            if(mode!=2)check(c.value[FMER_GLIDE_MODE]==(mode==1),"patch browse preserves glide");}
    }
}
void modulation_recipes_persist() {
    reset();check(fmer_dsp_transport(0x60000003u) && fmer_dsp_transport(0x60000102u),"modulation recipes accepted");
    const auto saved=native();check(saved.modulation[0]==3 && saved.modulation[1]==2,"profiles enter exact native snapshot");
    check(!fmer_dsp_transport(0x60000004u),"unsupported recipe rejected");restore(initial);restore(saved);
    check(fmer_dsp_modulation()==0x203,"both recipes survive complete project recall");
    for(unsigned effect=0;effect<2;effect++){
        std::vector<float> previous;
        for(unsigned recipe=0;recipe<4;recipe++){
            reset();set(FMER_SEQ_MODE,0);set(FMER_ENGINE,1);set(FMER_VA_WAVE,1);
            set(effect?FMER_PHASER:FMER_CHORUS,100);check(fmer_dsp_transport(0x60000000u|(effect<<8)|recipe),"recipe accepted for audio");
            fmer_dsp_midi(0x90,60,100,3);std::vector<float> samples;check(render(88200,&samples)>.01,"every modulation recipe is audible");
            double difference=0;for(size_t i=0;i<samples.size();i++){check(std::isfinite(samples[i]) && std::abs(samples[i])<=.981f,"recipe output remains finite and bounded");if(!previous.empty())difference+=std::abs(samples[i]-previous[i]);}
            if(recipe)check(difference>1,"neighboring recipes produce measurably distinct audio");previous=std::move(samples);
        }
    }
}
void four_tracks_and_owner_release() {
    reset();restore(scene());const auto errors=performance().performance_errors;
    fmer_dsp_transport(FMER_TRANSPORT_PLAY);check(render(256)>.0001,"mixed FM/VA parts make actual audio");
    check(fmer_dsp_active()==4,"four simultaneous tracks use exactly four local voices");
    for(unsigned t=0;t<4;++t)check(sent(0x90,10+t,60)==1,"generated MIDI uses four consecutive channels");
    fmer_dsp_midi(0x80,60,0,1);check(fmer_dsp_active()==4,"unowned incoming off cannot terminate generated sequence voice");
    set(FMER_SEQ_TRACK,1);fmer_dsp_midi(0x90,75,100,3);check(fmer_dsp_active()==4,"live key replaces only its selected mono part");
    fmer_dsp_midi(0x80,60,0,3);check(fmer_dsp_active()==4,"stale physical noteoff does not release new ownership");
    fmer_dsp_transport(FMER_TRANSPORT_STOP);fmer_dsp_midi(0x80,75,0,3);render(44100*3);
    check(!fmer_dsp_active(),"Stop and physical release leave no stuck voices");
    check(performance().performance_errors==errors,"ordinary four-track workflow reports no rejected core events");
}
void queues_and_track_names() {
    reset();restore(scene());
    set(FMER_SEQ_TRACK,1);auto a=native();
    fmer::FactoryPreset va;fmer::load_factory_preset(8,va);
    check(std::equal(va.patch.vced.begin()+145,va.patch.vced.end(),a.vced+145),"selecting track restores its own full patch name");
    set(FMER_SEQ_TRACK,0);fmer_dsp_transport(FMER_TRANSPORT_PLAY);render(128);set(FMER_SEQ_PATTERN,4);
    auto p=pattern();check(p.track_queued[0]==4 && p.track_pattern[0]==0,"queue is attached to selected track only");
    set(FMER_SEQ_TRACK,1);check(pattern().track_queued[0]==4,"switching editor track preserves prior track queue");
    render(22050);p=pattern();check(p.track_pattern[0]==4 && p.track_pattern[1]==1,"one pattern boundary changes only queued track");
}
void mute_sends_immediate_off() {
    reset();auto s=scene();for(unsigned i=1;i<4;++i)s.pitch[i]=FMER_TIE;restore(s);
    fmer_dsp_transport(FMER_TRANSPORT_PLAY);render(256);const auto before=sent(0x80,10,60);
    set(FMER_TRACK_MUTE,1);
    check(sent(0x80,10,60)==before+1,"muting a tied track immediately releases external MIDI ownership");
    check(sent(0x80,11,60)==0,"muting one track preserves another channel's same pitch");
    render(256);set(FMER_TRACK_MUTE,0);
    check(sent(0x90,10,60)==1,"unmute cannot resurrect a MIDI onset from a past step");
}
void timed_record_and_native_roundtrip() {
    reset();restore(scene(8));set(FMER_RECORD_MODE,2);fmer_dsp_transport(FMER_TRANSPORT_RECORD);
    render(88199);check(performance().recording && pattern().count_in==1,"count-in shows final beat before recording starts");
    fmer_dsp_midi(0x90,48,100,3);render(2);render(11025);fmer_dsp_midi(0x80,48,0,3);render(5513);
    auto s=native();check(s.pitch[0]==48 && s.pitch[1]==FMER_TIE && s.pitch[2]==FMER_TIE && s.pitch[3]==FMER_REST,
        "adapter records held notes as ties and key release as rest");
    render(44100);check(!performance().recording && performance().running,"one take ends while transport continues");
    s=native();check(fmer_native_state_valid(&s)==FMER_NATIVE_OK,"recorded snapshot stays internally valid");
    std::array<uint8_t,FMER_NATIVE_BYTES> bytes{};fmer_native_state_t decoded{};
    check(fmer_native_encode(&s,bytes.data(),bytes.size())==FMER_NATIVE_OK &&
          fmer_native_decode(bytes.data(),bytes.size(),&decoded)==FMER_NATIVE_OK,"v5 scene serializes complete tie/rest data");
    check(!std::memcmp(s.tracks,decoded.tracks,sizeof s.tracks) && !std::memcmp(s.pitch,decoded.pitch,64),"roundtrip preserves mix, track references and notes");
    fmer_dsp_transport(FMER_TRANSPORT_STOP);restore(decoded);check(native().pitch[1]==FMER_TIE,"recalled scene retains recorded holds");
}
void exact_native_roundtrip(fmer_native_state_t expected,const char* message) {
    restore(expected);const auto observed=native();expected.source_generation=observed.source_generation;
    std::array<uint8_t,FMER_NATIVE_BYTES> wanted{},actual{};
    check(fmer_native_encode(&expected,wanted.data(),wanted.size())==FMER_NATIVE_OK &&
          fmer_native_encode(&observed,actual.data(),actual.size())==FMER_NATIVE_OK,"both complete snapshots encode");
    check(wanted==actual,message);
}
void independent_chain_metadata_restore() {
    // The legacy editor chain and dormant track assignments are independent
    // native fields. Import must not interpret the former as a live track edit.
    for(unsigned mode:{0u,1u})for(unsigned selected:{0u,2u}) {
        reset();auto s=scene();s.controls.value[FMER_SEQ_MODE]=static_cast<uint16_t>(mode);
        s.controls.value[FMER_SEQ_TRACK]=static_cast<uint16_t>(selected);
        s.controls.value[FMER_TRACK_SOUND]=s.tracks[selected].sound;
        s.controls.value[FMER_SEQ_CHAIN]=1;s.controls.value[FMER_SEQ_CHAIN_MASK]=3;
        for(unsigned t=0;t<4;++t)s.tracks[t].chain_mask=static_cast<uint16_t>(t?1u<<(t+12):0);
        exact_native_roundtrip(s,"v5 import preserves independent16-bit chains and all fields for any selected track/mode");
    }
}
void migrated_legacy_chain_restore() {
    reset();auto legacy=scene();legacy.controls.value[FMER_SEQ_MODE]=0;
    legacy.controls.value[FMER_SEQ_CHAIN]=1;legacy.controls.value[FMER_SEQ_CHAIN_MASK]=5;
    std::array<uint8_t,FMER_NATIVE_BYTES> current{};
    check(fmer_native_encode(&legacy,current.data(),current.size())==FMER_NATIVE_OK,"legacy fixture starts as valid snapshot");
    std::array<uint8_t,FMER_NATIVE_V4_BYTES> wire{};std::copy_n(current.begin(),wire.size(),wire.begin());
    std::memcpy(wire.data(),"FMERNAT3",8);fmer_native_wr16(wire.data()+8,3);
    fmer_native_wr16(wire.data()+12,FMER_NATIVE_V4_BYTES);wire[26]=8;
    std::fill_n(wire.data()+32+150*2,20,0);std::fill_n(wire.data()+FMER_NATIVE_V4_PADDING,49,0);
    fmer_native_wr32(wire.data()+28,fmer_native_crc_n(wire.data(),wire.size()));
    fmer_native_state_t migrated{};
    check(fmer_native_decode(wire.data(),wire.size(),&migrated)==FMER_NATIVE_OK,"genuine v3 chained snapshot migrates");
    check(migrated.controls.value[FMER_SEQ_CHAIN]==1 && migrated.controls.value[FMER_SEQ_CHAIN_MASK]==5 &&
          migrated.tracks[0].chain_mask==0,"migration preserves legacy chain and initializes dormant track chain separately");
    exact_native_roundtrip(migrated,"restoring migrated v3 chain preserves every migrated v5 field");
}
void external_record_mirrors_into_native() {
    reset();restore(scene(4));midi_config(true);set(FMER_RECORD_MODE,1);fmer_dsp_transport(FMER_TRANSPORT_RECORD);
    const auto before=native().pitch[0];render(22050);
    check(pattern().count_in==0 && pattern().count_in_active && native().pitch[0]==before,"external REC waits without premature visual beat");
    fmer_dsp_midi(0xfa,0,0,1);
    check(performance().recording,"external master Start preserves pending record arm");
    fmer_dsp_midi(0xf8,0,0,1);
    for(unsigned tick=1;tick<=96;++tick){render(919);if(tick==96)fmer_dsp_midi(0x90,55,100,3);fmer_dsp_midi(0xf8,0,0,1);}
    fmer_dsp_midi(0xfc,0,0,1);
    check(native().pitch[0]==55,"external-clock recorded step is mirrored to persisted/native pool");
}
void remote_part_edits_and_snapshots() {
    reset();restore(scene());auto patch=fmer::make_init_patch();
    for(unsigned op=0;op<6;++op)patch.vced[op*21+3]=99;
    check(fmer_dsp_patch(patch.vced.data(),155)!=0,"remote raw FM patch accepted in parts mode");
    fmer_dsp_midi(0x90,69,110,1);render(4096);
    check(fmer_dsp_parameter(105+18,4)!=0,"remote operator edit accepted in parts mode");
    std::vector<float> audio;render(22050,&audio);unsigned crossings=0;
    for(unsigned i=1;i<audio.size();++i)if(audio[i-1]<=0 && audio[i]>0)++crossings;
    check(crossings*2>435 && crossings*2<445,"remote edits preserve current immutable part note snapshot");
    fmer_dsp_midi(0x80,69,0,1);render(44100);fmer_dsp_midi(0x90,69,110,1);render(4096);
    audio.clear();render(22050,&audio);crossings=0;
    for(unsigned i=1;i<audio.size();++i)if(audio[i-1]<=0 && audio[i]>0)++crossings;
    check(crossings*2>1755 && crossings*2<1765,"next part note actually adopts remotely edited FM ratio");
    auto saved=native();fmer_dsp_panic();restore(saved);check(native().vced[105+18]==4,"selected part working patch survives native restore");
    fmer_dsp_midi(0x90,69,110,1);render(4096);audio.clear();render(22050,&audio);crossings=0;
    for(unsigned i=1;i<audio.size();++i)if(audio[i-1]<=0 && audio[i]>0)++crossings;
    check(crossings*2>1755 && crossings*2<1765,"recalled selected part uses saved working patch in DSP");
}
void unavailable_reference_is_atomic() {
    reset();restore(scene());fmer_dsp_midi(0x90,60,100,3);render(128);
    auto bad=native();bad.tracks[2].sound=5;const auto generation=fmer_dsp_state_generation(),voices=fmer_dsp_active();
    check(fmer_native_state_valid(&bad)==FMER_NATIVE_OK,"missing-bank reference is structurally valid");
    check(!fmer_dsp_set_native(&bad,generation),"missing USER instrument is refused instead of silently replaced");
    check(fmer_dsp_state_generation()==generation && fmer_dsp_active()==voices,"unresolvable scene refusal preserves working state and held voices");
}
void incoming_parts_and_record_ownership() {
    reset();auto s=scene();
    for(unsigned t=0;t<4;++t)s.tracks[t].sound=72;s.controls.value[FMER_TRACK_SOUND]=72;
    s.controls.value[FMER_ENGINE]=1;restore(s);
    for(unsigned channel=0;channel<4;++channel)fmer_dsp_midi(static_cast<uint8_t>(0x90|channel),60,100,1);
    check(fmer_dsp_active()==4,"four external MIDI channels drive independent parts without local sequencer");
    fmer_dsp_midi(0x80,60,0,2);render(128);check(fmer_dsp_active()==4,"other MIDI input source cannot release same-channel owner");
    fmer_dsp_midi(0x80,60,0,1);render(44100*3);
    check(fmer_dsp_active()==3,"one incoming channel note-off leaves other three parts active");
    reset();restore(scene());set(FMER_RECORD_MODE,1);fmer_dsp_transport(FMER_TRANSPORT_RECORD);render(88199);
    fmer_dsp_midi(0x90,48,100,1);fmer_dsp_midi(0x91,77,100,1);render(2);
    check(native().pitch[0]==48,"MIDI for another part cannot overwrite armed track's recording input");
    fmer_dsp_midi(0x80,48,0,2);render(5513);
    check(native().pitch[1]==FMER_TIE,"unowned source note-off cannot terminate held recording input");
    fmer_dsp_midi(0x90,48,100,2);render(5513);fmer_dsp_midi(0x80,48,0,1);render(5513);
    check(native().pitch[3]==FMER_TIE,"older same-pitch owner release cannot cut a second input's held recording note");
}
void single_mode_live_recording() {
    reset();auto s=scene();s.controls.value[FMER_SEQ_MODE]=0;s.controls.value[FMER_VOICE_BUDGET]=2;
    s.controls.value[FMER_SEQ_TRACK]=2;s.controls.value[FMER_SEQ_PATTERN]=3;restore(s);
    const auto refs=native();set(FMER_RECORD_MODE,2);const auto errors=performance().performance_errors;
    fmer_dsp_transport(FMER_TRANSPORT_RECORD);check(performance().recording && performance().running && !pattern().count_in && pattern().count_in_active,"single mode replace arms real count-in before first click");
    render(88199);fmer_dsp_midi(0x90,55,110,3);render(11027);fmer_dsp_midi(0x80,55,0,3);render(5513);
    auto recorded=native();
    check(recorded.patterns[2].pitch[0]==55 && recorded.patterns[2].pitch[1]==FMER_TIE &&
          recorded.patterns[2].pitch[2]==FMER_TIE && recorded.patterns[2].pitch[3]==FMER_REST,
          "single mode records into current edit bank with holds and rests");
    check(!performance().recording && performance().running && fmer_dsp_voice_limit()==2,"single take ends without forcing four-part voice reservation");
    for(unsigned t=1;t<4;++t)check(sent(0x90,10+t)==0,"single live recording never emits unwanted other-track channels");
    check(!std::memcmp(refs.tracks,recorded.tracks,sizeof refs.tracks),"single live take preserves saved four-part assignments");
    set(FMER_SEQ_PATTERN,4);check(pattern().queued_pattern==4,"single live playback retains queued pattern workflow");
    render(22051);check(pattern().playing_pattern==4,"single live queue changes on full-pattern boundary");
    fmer_dsp_transport(FMER_TRANSPORT_STOP);check(!performance().running,"single live transport stops");
    fmer_dsp_transport(FMER_TRANSPORT_PLAY);render(128);check(performance().running && pattern().playing_pattern==4,"normal single sequencer works again after live take stops");
    check(performance().performance_errors==errors,"single-mode live integration produces no rejected core events");
    fmer_dsp_transport(FMER_TRANSPORT_STOP);set(FMER_RECORD_MODE,0);fmer_dsp_transport(FMER_TRANSPORT_RECORD);
    fmer_dsp_midi(0x90,57,110,3);check(pattern().pitch[0]==57 && !performance().running,"legacy untimed step recording remains available");
}
void multitimbral_midi_routes() {
    reset();restore(scene());fmer_midi_settings_t settings{};fmer_midi_defaults(&settings);
    settings.value[FMER_MIDI_ROUTE]=3;settings.value[FMER_MIDI_TX_CHANNEL]=10;check(fmer_dsp_set_midi_settings(&settings)!=0,"all-route MIDI fixture accepted");
    set(FMER_SEQ_TRACK,2);midi_count=0;fmer_dsp_midi(0x90,70,100,3);
    check(sent(0x90,12,70)==1 && sent(0x90,10,70)==0,"physical keyboard sends selected part's MIDI channel");
    set(FMER_SEQ_TRACK,0);fmer_dsp_midi(0x80,70,0,3);
    check(sent(0x80,12,70)==1,"physical noteoff retains original part after editor selection changes");
    fmer_dsp_panic();const auto before=fmer_dsp_active();fmer_dsp_midi(0x94,69,100,1);
    check(fmer_dsp_active()==before,"unsupported MIDI channels do not alias a valid part");
    const auto selected_name=native();fmer_dsp_midi(0xc1,9,0,1);
    auto after=native();check(after.tracks[1].sound==73 && after.tracks[0].sound==selected_name.tracks[0].sound &&
        !std::memcmp(after.vced,selected_name.vced,155),"Program Change on unselected MIDI part leaves editor instrument intact");
    const auto cutoff=controls().value[FMER_VA_CUTOFF];fmer_dsp_midi(0xb1,74,30,1);
    check(controls().value[FMER_VA_CUTOFF]==cutoff,"unselected MIDI part CC does not move editor's cutoff");
    set(FMER_SEQ_TRACK,1);check(controls().value[FMER_VA_CUTOFF]<200 && controls().value[FMER_TRACK_SOUND]==73,
        "selecting MIDI-edited part exposes its own patch and cutoff");
}
void single_live_external_recording() {
    reset();auto s=scene(1);s.controls.value[FMER_SEQ_MODE]=0;restore(s);midi_config(true);
    set(FMER_RECORD_MODE,1);fmer_dsp_transport(FMER_TRANSPORT_RECORD);render(8192);
    check(!pattern().count_in && pattern().count_in_active,"single live external mode awaits Start and clock without a fake beat");
    fmer_dsp_midi(0xfa,0,0,1);fmer_dsp_midi(0xf8,0,0,1);
    for(unsigned tick=1;tick<=96;++tick){render(919);if(tick==96)fmer_dsp_midi(0x90,52,100,3);fmer_dsp_midi(0xf8,0,0,1);}
    fmer_dsp_midi(0xfc,0,0,1);
    check(native().pitch[0]==52 && !performance().running && !performance().recording,"single live master-clock take persists even when Stop immediately follows final clock");
}
void multitrack_adapter_allocates_nothing() {
    reset();auto s=scene(8);restore(s);const auto before=adapter_multitrack_allocations;
    set(FMER_RECORD_MODE,1);fmer_dsp_transport(FMER_TRANSPORT_RECORD);render(88199);
    fmer_dsp_midi(0x90,48,100,3);render(22050);fmer_dsp_midi(0x80,48,0,3);render(22050);
    set(FMER_SEQ_TRACK,1);set(FMER_TRACK_LEVEL,70);set(FMER_TRACK_MUTE,1);set(FMER_SEQ_PATTERN,4);
    render(44100);auto saved=native();fmer_dsp_transport(FMER_TRANSPORT_STOP);restore(saved);fmer_dsp_panic();
    check(adapter_multitrack_allocations==before,"adapter record/render/edit/queue/native snapshot/restore allocate nothing after init");
}
void arp_survives_parts_mode() {
    reset();restore(scene());set(FMER_SEQ_TRACK,1);set(FMER_ARP_ENABLE,1);fmer_dsp_midi(0x90,69,100,3);
    check(render(4096)>.01 && fmer_dsp_active()>0,"arpeggiator remains audible in four-part mode");
    set(FMER_ARP_ENABLE,0);check(fmer_dsp_active()>0,"disabling arp restores held owner to its part");
    fmer_dsp_midi(0x80,69,0,3);render(44100*3);check(!fmer_dsp_active(),"restored live key releases normally");
}
void automatic_glide_and_fx_order() {
    reset();set(FMER_SEQ_MODE,0);set(FMER_GLIDE_MODE,0);set(FMER_VOICE_BUDGET,2);
    set(FMER_GLIDE_MODE,1);check(controls().value[FMER_VOICE_BUDGET]==1 && fmer_dsp_voice_limit()==1,"glide enters actual mono allocation");
    set(FMER_GLIDE_MODE,2);check(fmer_dsp_voice_limit()==1,"glide contour/mode change stays mono");
    set(FMER_GLIDE_MODE,0);check(fmer_dsp_voice_limit()==2,"glide off restores prior two-voice limit");
    set(FMER_GLIDE_MODE,1);auto voice=controls();voice.value[FMER_VOICE_BUDGET]=4;apply(voice);
    check(fmer_dsp_voice_limit()==1,"direct control request cannot defeat glide mono");
    set(FMER_GLIDE_MODE,0);set(FMER_SEQ_MODE,1);set(FMER_GLIDE_MODE,1);
    check(fmer_dsp_voice_limit()==4,"part glide cannot collapse four-track budget");
    set(FMER_SEQ_MODE,0);check(fmer_dsp_voice_limit()==1,"single mode adopts active glide");
    set(FMER_GLIDE_MODE,0);auto original=native();
    check(fmer_dsp_transport(fmer_fx_command(3,-6))!=0,"move distortion before filter accepted");
    uint8_t order[6];auto reordered=native();fmer_fx_unrank(reordered.fx_order,order);
    check(order[0]==3 && reordered.fx_order!=original.fx_order,"audio-owner FX order changes");
    check(fmer_dsp_set_fx_default(reordered.fx_order,0)!=0,"stopped owner installs personal reset target");
    check(fmer_dsp_transport(fmer_fx_command(0,1))!=0,"alter route after saving default");
    check(fmer_dsp_transport(fmer_fx_command(6,1))!=0 && native().fx_order==reordered.fx_order,"reset uses saved personal default");
    check(fmer_dsp_set_fx_default(720,1)==0 && native().fx_order==reordered.fx_order,"invalid default cannot alter live route");
    check(fmer_dsp_set_fx_default(0,0)!=0,"restore original reset target");
    restore(reordered);check(native().fx_order==reordered.fx_order,"FX order survives native snapshot restore");
    check(fmer_dsp_transport(fmer_fx_command(6,1))!=0 && native().fx_order==0,"default-chain reset is explicit");
    restore(original);
}
void fx_survive_all_bank_auditions() {
    reset();auto c=controls();
    const unsigned ids[]={FMER_FILTER_TYPE,FMER_FX_RESONANCE,FMER_REVERB_MODEL,FMER_DELAY_MODEL,FMER_CUTOFF,
        FMER_DRIVE,FMER_CHORUS,FMER_DELAY,FMER_DELAY_MS,FMER_FEEDBACK,FMER_REVERB,FMER_PHASER,FMER_REVERB_DECAY};
    const unsigned values[]={2,73,1,1,3210,15,22,46,470,62,54,19,67};
    for(unsigned i=0;i<std::size(ids);++i)c.value[ids[i]]=static_cast<uint16_t>(values[i]);apply(c);
    for(unsigned slot:{64u,72u,0u}) {
        check(fmer_dsp_audition(slot)!=0,"FM, VA and USER audition succeeds");const auto current=controls();
        for(unsigned id:ids)check(current.value[id]==c.value[id],"changing sound bank preserves all live shared FX parameters");
    }
}
struct FxTrace {std::vector<float> audio;std::vector<Midi> messages;fmer_native_state_t state;};
FxTrace fx_edit_trace(bool reference,unsigned mode,unsigned engine) {
    reset();auto s=scene();s.controls.value[FMER_SEQ_MODE]=static_cast<uint16_t>(mode);
    s.controls.value[FMER_ENGINE]=static_cast<uint16_t>(engine);s.controls.value[FMER_LFO_ENABLE]=0;
    s.controls.value[FMER_SEQ_CHAIN]=0;s.controls.value[FMER_SEQ_CHAIN_MASK]=1;restore(s);
    fmer_midi_settings_t settings{};fmer_dsp_get_midi_settings(&settings);settings.value[FMER_MIDI_CC_SEND]=1;
    check(fmer_dsp_set_midi_settings(&settings)!=0,"FX trace enables canonical CC feedback");
    for(unsigned note=0;note<4;++note)fmer_dsp_midi(static_cast<uint8_t>(0x90|(mode?note:0)),60+note*3,90,1);
    render(4096);midi_count=0;
    const unsigned edits[][2]={{FMER_FILTER_TYPE,2},{FMER_FX_RESONANCE,75},{FMER_REVERB_MODEL,1},{FMER_DELAY_MODEL,1},
        {FMER_CUTOFF,744},{FMER_DRIVE,20},{FMER_CHORUS,25},{FMER_DELAY,60},{FMER_DELAY_MS,1000},
        {FMER_FEEDBACK,70},{FMER_REVERB,80},{FMER_PHASER,30},{FMER_REVERB_DECAY,75},{FMER_DELAY_MS,20},
        {FMER_CUTOFF,12000},{FMER_DELAY,0},{FMER_REVERB,0},{FMER_CHORUS,0},{FMER_PHASER,0},
        {FMER_FILTER_TYPE,0},{FMER_FX_RESONANCE,0},{FMER_CUTOFF,20000}};
    FxTrace trace{};trace.audio.reserve(std::size(edits)*256);const auto allocations=adapter_multitrack_allocations;
    for(const auto& edit:edits) {
        auto c=controls();c.value[edit[0]]=static_cast<uint16_t>(edit[1]);
        // Changing the disabled legacy chain mask forces the reference through
        // the full instrument path without changing held-note audio or FX.
        if(reference)c.value[FMER_SEQ_CHAIN_MASK]=c.value[FMER_SEQ_CHAIN_MASK]==1?2:1;
        const auto generation=fmer_dsp_state_generation();apply(c);
        check(fmer_dsp_state_generation()==generation+1,"FX edit advances the same canonical revision once");
        render(256,&trace.audio);check(fmer_dsp_active()==4,"FX editing preserves four held owners");
    }
    check(adapter_multitrack_allocations==allocations,"FX edits and audio render allocate nothing");
    trace.state=native();trace.state.controls.value[FMER_SEQ_CHAIN_MASK]=1;
    trace.messages.assign(midi.begin(),midi.begin()+midi_count);return trace;
}
void fx_fast_path_matches_full_apply() {
    for(unsigned mode:{0u,1u})for(unsigned engine:{0u,1u}) {
        const auto fast=fx_edit_trace(false,mode,engine),full=fx_edit_trace(true,mode,engine);
        check(fast.audio==full.audio,"FX-only and full applies produce identical PCM through edits, readhead changes and tail clearing");
        check(fast.messages.size()==full.messages.size() && fast.messages.size()==(mode?8u:11u),"both FX paths send eight shared-send CCs plus single-mode cutoff changes");
        for(unsigned i=0;i<fast.messages.size();++i)check(fast.messages[i].status==full.messages[i].status &&
            fast.messages[i].a==full.messages[i].a && fast.messages[i].b==full.messages[i].b,"FX paths preserve exact MIDI CC values");
        auto expected=fast.state;expected.source_generation=full.state.source_generation;
        std::array<uint8_t,FMER_NATIVE_BYTES> a{},b{};
        check(fmer_native_encode(&expected,a.data(),a.size())==FMER_NATIVE_OK &&
              fmer_native_encode(&full.state,b.data(),b.size())==FMER_NATIVE_OK && a==b,"FX paths retain identical complete native state");
    }
}
void fx_fast_path_rejects_invalid_batches() {
    reset();auto c=controls();c.value[FMER_CUTOFF]=744;
    const auto generation=fmer_dsp_state_generation();const auto before=native();
    const unsigned invalid_ids[]={0,159,FMER_CUTOFF,FMER_GLIDE_MODE,FMER_SEQ_TRACK,FMER_SEQ_CHAIN_MASK};
    for(unsigned id:invalid_ids) {
        auto bad=c;bad.value[id]=id==FMER_SEQ_CHAIN_MASK?0:65535;
        check(!fmer_dsp_apply_controls(&bad),"FX edit cannot bypass malformed FM, reserved, FX, glide, track or chain validation");
        const auto after=native();check(fmer_dsp_state_generation()==generation &&
            !std::memcmp(&before.controls,&after.controls,sizeof before.controls),"invalid FX batch leaves complete controls and revision untouched");
    }
    // A restore also contains patch/name/part state outside the controls array,
    // so it must always take the full path despite an FX-only control delta.
    auto imported=before;imported.controls.value[FMER_CUTOFF]=744;
    std::copy_n("FX IMPORT ",10,imported.vced+145);
    exact_native_roundtrip(imported,"FX-only native import still adopts exact patch name and snapshot");
    set(FMER_SEQ_TRACK,1);set(FMER_SEQ_TRACK,0);
    check(!std::memcmp(native().vced+145,imported.vced+145,10),"native FX-only import updates dormant selected-part snapshot");
    reset();check(fmer_dsp_parameter(134,19)!=0,"direct FM edit accepted before FX-only batch");set(FMER_CUTOFF,744);
    set(FMER_SEQ_TRACK,1);set(FMER_SEQ_TRACK,0);
    check(controls().value[134]==19,"FX-only batch retains full-path dormant-part synchronization after direct FM parameter edit");
    auto named=fmer::make_init_patch();std::copy_n("RAW FX    ",10,named.vced.begin()+145);
    check(fmer_dsp_patch(named.vced.data(),155)!=0,"direct FM snapshot accepted before FX-only batch");set(FMER_CUTOFF,12000);
    set(FMER_SEQ_TRACK,1);set(FMER_SEQ_TRACK,0);
    check(!std::memcmp(native().vced+145,named.vced.data()+145,10),"FX-only batch retains full-path dormant-part synchronization after raw patch edit");
    reset();fmer_midi_settings_t settings{};fmer_dsp_get_midi_settings(&settings);settings.value[FMER_MIDI_CC_SEND]=1;
    check(fmer_dsp_set_midi_settings(&settings)!=0,"CC loop test settings accepted");midi_count=0;
    fmer_dsp_midi(0xb0,74,40,1);
    check(controls().value[FMER_CUTOFF]!=before.controls.value[FMER_CUTOFF] && !midi_count,"incoming cutoff CC uses FX path without echo");
}
void standalone_glide_audio() {
    reset();auto c=controls();c.value[FMER_ENGINE]=1;c.value[FMER_VA_WAVE]=0;c.value[FMER_VA_CUTOFF]=18000;
    c.value[FMER_RESONANCE]=0;c.value[FMER_ATTACK]=0;c.value[FMER_DECAY]=0;c.value[FMER_SUSTAIN]=100;
    c.value[FMER_RELEASE]=5;c.value[FMER_VOICE_BUDGET]=1;c.value[FMER_GLIDE_MODE]=1;c.value[FMER_GLIDE_MS]=1000;
    c.value[FMER_GLIDE_CURVE]=0;c.value[FMER_LFO_ENABLE]=0;apply(c);
    fmer_dsp_midi(0x90,69,110,3);render(4096);fmer_dsp_midi(0x90,81,110,3);render(19845);
    std::vector<float> window;render(4410,&window);unsigned crossings=0;
    for(unsigned i=1;i<window.size();++i)if(window[i-1]<=0 && window[i]>0)++crossings;
    check(crossings*10>590 && crossings*10<660 && fmer_dsp_active()==1,"canonical glide controls yield audible midpoint glide with one voice");
    auto s=native();check(s.controls.value[FMER_GLIDE_MS]==1000,"glide settings enter native save state");
}
void panel_turn(fmer_panel_t& panel,unsigned encoder,int delta) {
    auto c=controls();const auto changed=fmer_panel_encoder(&panel,encoder,delta,&c,1000u+panel.edit_ms);
    check(changed || panel.performance_request,"gesture publishes control or explicit performance command");
    if(changed)apply(c);
    if(panel.performance_request){check(fmer_dsp_transport(panel.performance_request)!=0,"performance command accepted");panel.performance_request=0;}
}
void panel_mixer_audio_levels() {
    for(unsigned mode:{0u,1u})for(unsigned engine:{0u,1u}) {
        reset();auto s=scene();s.controls.value[FMER_SEQ_MODE]=static_cast<uint16_t>(mode);
        s.controls.value[FMER_ENGINE]=static_cast<uint16_t>(engine);s.controls.value[FMER_LFO_ENABLE]=0;
        s.controls.value[FMER_CUTOFF]=20000;s.controls.value[FMER_FX_RESONANCE]=0;
        s.controls.value[FMER_ATTACK]=0;s.controls.value[FMER_DECAY]=0;s.controls.value[FMER_SUSTAIN]=100;
        auto sustained=fmer::make_init_patch();for(unsigned op=0;op<6;++op)sustained.vced[op*21+3]=99;
        std::copy_n(sustained.vced.begin(),155,s.vced);for(unsigned id=0;id<145;++id)s.controls.value[id]=s.vced[id];
        restore(s);fmer_panel_t panel;fmer_panel_init(&panel);panel.family=FMER_PANEL_SEQ;panel.page[FMER_PANEL_SEQ]=4;
        fmer_dsp_midi(0x90,69,100,1);render(4096);const auto full=render(22050);check(full>.01,"mixer fixture has sustained audible signal");
        if(!mode) {
            auto c=controls();const auto before=c;
            check(!fmer_panel_encoder(&panel,2,-50,&c,1000) && !fmer_panel_encoder(&panel,4,1,&c,2000) &&
                  !std::memcmp(&before,&c,sizeof c),"SINGLE mixer rejects ineffective level/mute gestures without changing state");
            check(render(22050)/full>.98,"opening inactive SINGLE mixer leaves ongoing sound intact");continue;
        }
        panel_turn(panel,2,-25);render(4096);const auto half=render(22050);
        panel.mixer_layer=FMER_MIX_MUTE;panel_turn(panel,2,1);render(4096);const auto muted=render(22050);
        std::cout<<"MIXER audio mode="<<mode<<" engine="<<engine<<" level50_energy_ratio="<<half/full<<" muted_energy_ratio="<<muted/full<<'\n';
        if(mode) {
            check(half/full>.245 && half/full<.255,"panel mixer50 produces half amplitude/quarter energy");
            check(muted==0,"panel mixer mute reaches exact silence after bounded smoothing");
            panel_turn(panel,2,-1);panel.mixer_layer=FMER_MIX_LEVEL;panel_turn(panel,2,25);render(4096);
            check(render(22050)/full>.98,"panel unmute/level restore resumes existing held owner");
        }
    }
}
void panel_parts_entry_tracks_editor() {
    reset();auto s=scene();s.controls.value[FMER_SEQ_MODE]=0;restore(s);
    fmer_panel_t panel;fmer_panel_init(&panel);panel.family=FMER_PANEL_SEQ;panel.page[FMER_PANEL_SEQ]=3;
    panel.page[FMER_PANEL_SEQ]=1;panel_turn(panel,2,4);check(controls().value[FMER_SEQ_PATTERN]==4 && native().tracks[0].pattern==0,"single editor can differ from dormant track assignment");
    panel.page[FMER_PANEL_SEQ]=3;
    panel_turn(panel,2,1);
    const auto c=controls();const auto p=pattern();
    std::cout<<"4TRK mode-entry editor="<<c.value[FMER_SEQ_PATTERN]<<" selected_track_pattern="<<unsigned(p.track_pattern[c.value[FMER_SEQ_TRACK]])<<'\n';
    check(c.value[FMER_SEQ_PATTERN]==p.track_pattern[c.value[FMER_SEQ_TRACK]],"entering four tracks synchronizes editor to selected track assignment");
    fmer_dsp_transport(FMER_TRANSPORT_PLAY);render(256);
    check(fmer_dsp_active()==4,"panel-enabled four-track playback admits all four populated tracks");
}
FxTrace control_edit_trace(bool reference,unsigned mode,unsigned engine) {
    reset();auto s=scene();s.controls.value[FMER_SEQ_MODE]=static_cast<uint16_t>(mode);
    s.controls.value[FMER_ENGINE]=static_cast<uint16_t>(engine);s.controls.value[FMER_DELAY]=25;s.controls.value[FMER_REVERB]=35;
    restore(s);check(fmer_dsp_patch(s.vced,155)!=0,"reference fixture installs canonical raw snapshot");apply(controls());
    fmer_midi_settings_t settings{};fmer_dsp_get_midi_settings(&settings);settings.value[FMER_MIDI_CC_SEND]=1;
    check(fmer_dsp_set_midi_settings(&settings)!=0,"instrument trace enables canonical CC feedback");
    for(unsigned voice=0;voice<4;++voice)fmer_dsp_midi(static_cast<uint8_t>(0x90|(mode?voice:0)),60+voice*3,90,1);
    render(4096);midi_count=0;
    const unsigned edits[][2]={{FMER_SEQ_STEP,1},{FMER_SEQ_STEP,2},{FMER_SEQ_PITCH,72},{FMER_SEQ_VELOCITY,64},
        {FMER_SEQ_GATE,50},{FMER_TEMPO,130},{142,4},{FMER_LFO_RATE,850},{FMER_LFO_ENABLE,0},{FMER_LFO_ENABLE,1},
        {FMER_ENGINE,1},{FMER_ATTACK,70},{FMER_RELEASE,400},{FMER_VA_CUTOFF,5000},{FMER_GLIDE_MODE,1},
        {FMER_GLIDE_MS,120},{FMER_TRACK_LEVEL,75},{FMER_TRACK_MUTE,1},{FMER_TRACK_MUTE,0},{134,9},
        {FMER_RESONANCE,75},{FMER_VA_WAVE,3},{FMER_ENGINE,0},{FMER_VOICE_BUDGET,2},{FMER_VOICE_BUDGET,4}};
    FxTrace trace{};trace.audio.reserve(std::size(edits)*512);const auto allocations=adapter_multitrack_allocations;unsigned live_note=60;
    for(const auto& edit:edits) {
        // Reinstalling the identical raw patch forces the retained complete
        // synchronization path without resetting voices, phases or FX tails.
        if(reference){const auto raw=native();check(fmer_dsp_patch(raw.vced,155)!=0,"force complete instrument synchronization");}
        auto c=controls();c.value[edit[0]]=static_cast<uint16_t>(edit[1]);apply(c);render(256,&trace.audio);
        fmer_dsp_midi(0x80,static_cast<uint8_t>(live_note),0,1);live_note=live_note==60?72:60;
        fmer_dsp_midi(0x90,static_cast<uint8_t>(live_note),90,1);render(256,&trace.audio);
    }
    check(adapter_multitrack_allocations==allocations,"selective and full instrument edits/render allocate nothing");
    trace.state=native();trace.messages.assign(midi.begin(),midi.begin()+midi_count);return trace;
}
void selective_instrument_apply_matches_full_sync() {
    for(unsigned mode:{0u,1u})for(unsigned engine:{0u,1u}) {
        const auto selective=control_edit_trace(false,mode,engine),full=control_edit_trace(true,mode,engine);
        check(selective.audio==full.audio,"selective setters retain exact PCM for cursor/LFO/engine/envelope/glide/mixer/voice-budget edits and subsequent notes");
        check(selective.messages.size()==full.messages.size(),"selective instrument setters preserve MIDI message count");
        for(unsigned i=0;i<selective.messages.size();++i)check(selective.messages[i].status==full.messages[i].status &&
            selective.messages[i].a==full.messages[i].a && selective.messages[i].b==full.messages[i].b,"selective instrument setters preserve exact MIDI feedback");
        auto expected=selective.state;expected.source_generation=full.state.source_generation;
        std::array<uint8_t,FMER_NATIVE_BYTES> a{},b{};
        check(fmer_native_encode(&expected,a.data(),a.size())==FMER_NATIVE_OK &&
              fmer_native_encode(&full.state,b.data(),b.size())==FMER_NATIVE_OK && a==b,"selective instrument setters preserve complete native scene");
    }
}
void algorithm_is_selected_instrument_state() {
    reset();restore(scene());auto c=controls();
    for(unsigned id:{FMER_DRIVE,FMER_CHORUS,FMER_DELAY,FMER_REVERB,FMER_PHASER,FMER_FX_RESONANCE})c.value[id]=0;
    c.value[FMER_CUTOFF]=20000;c.value[FMER_LFO_ENABLE]=0;apply(c);
    set(FMER_SEQ_TRACK,2);set(134,31);set(FMER_LFO_ENABLE,0);
    fmer_dsp_midi(0x92,69,100,1);std::vector<float> original;render(8192,&original);fmer_dsp_panic();
    set(FMER_SEQ_TRACK,0);set(134,17);set(FMER_SEQ_TRACK,2);
    check(controls().value[134]==31,"algorithm edit on part0 does not change FM instrument on part2");
    fmer_dsp_midi(0x92,69,100,1);std::vector<float> after;render(8192,&after);fmer_dsp_panic();
    check(original==after,"unselected FM part produces exact unchanged PCM after another part's algorithm edit");
    set(FMER_SEQ_TRACK,0);check(controls().value[134]==17,"returning to edited part restores its own algorithm");
    auto sound=native();std::array<uint8_t,FMER_NATIVE_BYTES> wire{};
    check(fmer_native_encode(&sound,wire.data(),wire.size())==FMER_NATIVE_OK,"edited instrument serializes algorithm");
    fmer_dsp_cache_sound(1,wire.data());set(FMER_TRACK_SOUND,1);set(FMER_SEQ_TRACK,2);
    const auto project=native();restore(project);set(FMER_SEQ_TRACK,0);
    check(controls().value[134]==17 && controls().value[FMER_TRACK_SOUND]==1,
          "project restore resolves edited algorithm from saved instrument slot independently");
    set(FMER_SEQ_TRACK,2);check(controls().value[134]==31,"project restore preserves selected working FM algorithm too");
}
void upper_pattern_queue_and_overdub_preservation() {
    reset();auto s=scene(4);s.tracks[0].pattern=15;s.tracks[0].chain_mask=0x8100;
    s.controls.value[FMER_SEQ_PATTERN]=15;s.controls.value[FMER_SEQ_CHAIN]=1;s.controls.value[FMER_SEQ_CHAIN_MASK]=0x8100;
    s.patterns[14].pitch[0]=79;s.controls.value[FMER_SEQ_PITCH]=79;restore(s);
    fmer_dsp_transport(FMER_TRANSPORT_PLAY);render(128);
    check(sent(0x90,10,79)==1 && pattern().track_pattern[0]==15,"pattern16 plays from native project assignment");
    set(FMER_SEQ_PATTERN,14);check(pattern().track_queued[0]==14,"pattern15 queues independently for track1");
    render(22050);check(pattern().track_pattern[0]==14 && pattern().track_pattern[1]==1,"upper-pattern queue applies only to its track");
    fmer_dsp_transport(FMER_TRANSPORT_STOP);
    reset();s=scene(4);s.tracks[0].pattern=15;s.controls.value[FMER_SEQ_PATTERN]=15;restore(s);
    const auto before=native();set(FMER_RECORD_MODE,1);fmer_dsp_transport(FMER_TRANSPORT_RECORD);render(88201);
    fmer_dsp_midi(0x90,77,83,3);fmer_dsp_midi(0x80,77,0,3);render(5513);
    auto during=native();check(during.patterns[14].pitch[0]==60 && during.patterns[14].pitch[1]==77 &&
        during.patterns[14].velocity[1]==83 && during.patterns[14].pitch[2]==62,"overdub edits one upper-bank cell and keeps surrounding notes");
    for(unsigned bank=0;bank<15;++bank) {
        const auto* expected=bank?before.patterns[bank-1].pitch:before.pitch;
        const auto* actual=bank?during.patterns[bank-1].pitch:during.pitch;
        check(!std::memcmp(expected,actual,64),"recording mirror preserves every other shared pattern");
    }
    render(22050);check(performance().recording,"overdub remains armed for additional passes");
    fmer_dsp_transport(FMER_TRANSPORT_RECORD);check(!performance().recording && performance().running,"REC finishes overdub without stopping performance");
    const auto completed=native();render(44100);const auto played=native();
    check(!std::memcmp(completed.patterns,played.patterns,sizeof completed.patterns),"completed overdub cannot write during later playback");
}
void mono_adapter_returns_to_held_pitch() {
    for(unsigned mode:{0u,1u}) {
        reset();auto s=scene();s.controls.value[FMER_SEQ_MODE]=static_cast<uint16_t>(mode);
        s.controls.value[FMER_VOICE_BUDGET]=mode?4:1;restore(s);set(FMER_GLIDE_MODE,1);set(FMER_GLIDE_MS,150);
        fmer_dsp_midi(0x90,60,90,3);render(128);fmer_dsp_midi(0x90,72,110,3);render(8192);
        fmer_dsp_midi(0x80,72,0,3);render(128);fmer_activity_state_t state{};fmer_dsp_get_activity(&state);
        check(state.active_voices==1 && (state.gated_notes[1]&(1u<<28)) && !(state.gated_notes[2]&(1u<<8)),
              "physical adapter release returns standalone/part mono voice to actual still-held owner");
        fmer_dsp_midi(0x80,60,0,3);render(44100*3);check(!fmer_dsp_active(),"final held key releases through adapter without stuck fallback");
    }
}
void repeat_reports_mono_admission() {
    reset();auto s=scene();s.controls.value[FMER_SEQ_MODE]=0;s.controls.value[FMER_VOICE_BUDGET]=1;
    s.controls.value[FMER_TEMPO]=100;s.controls.value[FMER_ARP_RATE]=16;s.controls.value[FMER_ARP_GATE]=70;
    s.controls.value[FMER_ARP_OCTAVES]=4;s.controls.value[FMER_ARP_ORDER]=6;s.controls.value[FMER_ARP_TRIPLET]=0;
    s.controls.value[FMER_ARP_SWING]=50;restore(s);set(FMER_ARP_ENABLE,1);
    const auto drops=performance().generated_drops;
    fmer_dsp_midi(0x90,62,100,3);fmer_dsp_midi(0x90,69,100,3);render(8*6615);
    const auto attacks=std::count_if(tapped.begin(),tapped.begin()+tap_count,[](auto e){return e.status==0x90;});
    check(attacks==8 && performance().generated_drops-drops==56,
          "eight Repeat pulses with eight expanded pitches and mono budget report exactly56 denied local attacks");
    check(sent(0x90,10)==64,"all expanded Repeat pitches still reach generated MIDI beyond local mono admission");
    check(fmer_dsp_active()<=1,"Repeat admission never silently exceeds selected local voice budget");
}
void single_live_external_restart_keeps_upper_chain() {
    reset();auto s=scene(1);s.controls.value[FMER_SEQ_MODE]=0;
    s.controls.value[FMER_SEQ_CHAIN]=1;s.controls.value[FMER_SEQ_CHAIN_MASK]=0x8001;
    s.patterns[14].pitch[0]=75;restore(s);midi_config(true);set(FMER_RECORD_MODE,1);
    fmer_dsp_transport(FMER_TRANSPORT_RECORD);fmer_dsp_transport(FMER_TRANSPORT_RECORD);
    fmer_dsp_midi(0xfc,0,0,1);set(FMER_SEQ_PATTERN,15);fmer_dsp_midi(0xfa,0,0,1);
    for(unsigned tick=0;tick<=12;++tick){if(tick)render(919);fmer_dsp_midi(0xf8,0,0,1);}
    check(pattern().playing_pattern==15 && sent(0x90,10,75)==2 && sent(0x90,10,60)==1,
          "stopped external single-live pattern selection retains bit15 chain after master restart");
}
void performance_solo_fx_and_persistence() {
    reset();restore(scene());fmer_dsp_transport(FMER_TRANSPORT_PLAY);render(256);
    check(fmer_dsp_transport(fmer_mix_command(1,FMER_MIX_SOLO,1)),"solo command accepted");
    for(unsigned t=0;t<4;t++)if(t!=1)check(sent(0x80,10+t,60)==1,"solo releases every excluded MIDI owner");
    const auto phase=pattern().track_step[2];render(6000);
    check(pattern().track_step[2]!=phase,"solo-excluded track retains timeline");
    check(fmer_dsp_transport(fmer_mix_command(2,FMER_MIX_FX,-1)),"dry send command accepted");
    auto saved=native();check(saved.tracks[1].solo && saved.tracks[2].fx_bypass,"project snapshot owns solo and FX route");
    std::array<uint8_t,FMER_NATIVE_BYTES> bytes{};fmer_native_state_t decoded{};
    check(fmer_native_encode(&saved,bytes.data(),bytes.size())==0 && fmer_native_decode(bytes.data(),bytes.size(),&decoded)==0,"mixer flags encode and decode");
    check(decoded.tracks[1].solo && decoded.tracks[2].fx_bypass,"flags survive compact native representation");
    restore(decoded);check(pattern().track_solo[1] && !pattern().track_fx[2],"restored screen agrees with saved mixer");
}
void merged_channel_balances_same_pitch() {
    reset();restore(scene());fmer_midi_settings_t settings{};fmer_dsp_get_midi_settings(&settings);settings.value[7]=1;
    check(fmer_dsp_set_midi_settings(&settings),"merged routing accepted");
    midi_count=0;fmer_dsp_transport(FMER_TRANSPORT_PLAY);render(256);
    check(sent(0x90,10,60)==4 && sent(0x80,10,60)==3,"merged same-pitch onsets retrigger one balanced channel voice");
    for(unsigned t=1;t<4;t++)check(!sent(0x90,10+t),"merged mode does not duplicate split-channel notes");
    fmer_dsp_transport(fmer_mix_command(0,FMER_MIX_MUTE,1));
    check(sent(0x80,10,60)==3,"muting one shared-pitch owner cannot cut remaining owners");
    fmer_dsp_transport(FMER_TRANSPORT_STOP);check(sent(0x80,10,60)==4,"last shared-pitch owner releases exactly once");
    settings.value[7]=0;check(fmer_dsp_set_midi_settings(&settings),"split restored after balanced old-channel release");
}
void fx_bypass_is_actual_audio_routing() {
    const auto pcm=[&](bool bypass,bool effect){
        reset();auto state=scene(8);state.tracks[0].solo=1;state.tracks[0].fx_bypass=bypass;
        state.controls.value[FMER_FILTER_TYPE]=0;state.controls.value[FMER_CUTOFF]=effect?100:20000;
        state.controls.value[FMER_REVERB]=state.controls.value[FMER_DELAY]=0;
        restore(state);fmer_dsp_transport(FMER_TRANSPORT_PLAY);std::vector<float> result;render(8192,&result);return result;
    };
    const auto bypass_filtered=pcm(true,true),bypass_open=pcm(true,false),filtered=pcm(false,true);
    check(bypass_filtered==bypass_open,"FX bypass PCM does not depend on global filter settings");
    check(bypass_filtered!=filtered,"FX send actually processes the track through the filter");
}
void direct_edit_workflow_and_undo() {
    reset();auto s=scene(16);
    for(unsigned i=1;i<64;i++)s.pitch[i]=FMER_REST;
    restore(s);
    check(fmer_dsp_transport(fmer_note_command(0,0,FMER_NOTE_LENGTH,3)),"extend note command");
    auto p=pattern();check(p.pitch[0]==60 && p.pitch[1]==FMER_TIE && p.pitch[3]==FMER_TIE,"held duration writes ties");
    fmer_dsp_transport(fmer_note_command(0,2,FMER_NOTE_MOVE,3));p=pattern();
    check(p.pitch[0]==FMER_REST && p.pitch[3]==60 && p.pitch[6]==FMER_TIE && controls().value[FMER_SEQ_STEP]==3,"moving from a tie retains whole note and editor cursor");
    fmer_dsp_transport(fmer_block_command(0,3,4,0,FMER_BLOCK_COPY));check(pattern().clipboard_length==4,"copy captures selected range");
    fmer_dsp_transport(fmer_block_command(0,0,1,8,FMER_BLOCK_PASTE));p=pattern();check(p.pitch[8]==60 && p.pitch[11]==FMER_TIE,"paste reproduces held phrase");
    fmer_dsp_transport(fmer_block_command(0,0,1,0,FMER_BLOCK_UNDO));check(pattern().pitch[8]==FMER_REST,"undo restores overwritten destination");
    fmer_dsp_transport(fmer_note_command(0,5,FMER_NOTE_DELETE,0));check(pattern().pitch[3]==FMER_REST && pattern().pitch[6]==FMER_REST,"delete from tied cell removes logical note");
    fmer_dsp_transport(fmer_block_command(0,0,1,14,FMER_BLOCK_PASTE));check(pattern().edit_result && pattern().pitch[14]==FMER_REST,"out-of-range paste reports failure and preserves target");
}
void silent_countin_shared_downbeat() {
    reset();auto s=scene(8);s.controls.value[FMER_RECORD_MODE]=1;s.controls.value[FMER_REVERB]=70;s.controls.value[FMER_DELAY]=50;
    restore(s);fmer_dsp_transport(FMER_TRANSPORT_PLAY);render(1000);fmer_dsp_transport(FMER_TRANSPORT_RECORD);
    check(render(2000)==0,"armed count-in silences old voices and FX tails before the first click");
    const auto start=tap_count;render(120000);
    std::array<uint32_t,4> onset{};for(std::size_t i=start;i<tap_count;++i)if((tapped[i].status&0xf0)==0x90){
        auto t=tapped[i].status&15;if(t<4 && !onset[t]){onset[t]=tapped[i].frame;check(tapped[i].note==60,"all tracks restart at first note after lead-in");}}
    check(onset[0] && onset[0]==onset[1] && onset[0]==onset[2] && onset[0]==onset[3],"all four tracks share exact first frame after count-in");
}

void arp_capture_records_generated_notes() {
    for(bool external:{false,true}){
        reset();restore(scene(16));midi_config(external);set(FMER_RECORD_MODE,1);set(FMER_ARP_ENABLE,1);
        fmer_midi_settings_t ms{};fmer_dsp_get_midi_settings(&ms);ms.value[FMER_MIDI_CLOCK_SEND]=1;
        check(fmer_dsp_set_midi_settings(&ms),"clock send enabled for capture transport check");
        set(FMER_ARP_LATCH,1);set(FMER_ARP_RATE,16);
        fmer_dsp_midi(0x90,60,90,3);fmer_dsp_midi(0x90,64,91,3);fmer_dsp_midi(0x90,67,92,3);
        fmer_dsp_midi(0x80,60,0,3);fmer_dsp_midi(0x80,64,0,3);fmer_dsp_midi(0x80,67,0,3);
        const auto errors=performance().performance_errors;
        check(fmer_dsp_transport(FMER_TRANSPORT_ARP_RECORD),"arp capture arms");
        if(external){fmer_dsp_midi(0xfa,0,0,1);for(unsigned i=0;i<120;i++){fmer_dsp_midi(0xf8,0,0,1);render(919);}}
        else render(88200+22050);
        const auto n=native();
        check(n.pitch[0]==60 && n.pitch[1]==64 && n.pitch[2]==67 && n.pitch[3]==60,"recorded cells contain generated arp order, not raw chord or one-step delayed notes");
        check(performance().performance_errors==errors,"merged capture scheduler preserves chronology");
        midi_count=0;
        check(fmer_dsp_transport(FMER_TRANSPORT_ARP_RECORD),"REC again finishes capture");
        if(!external){render(22050);bool clock=false,stop=false;for(std::size_t i=0;i<midi_count;++i){clock|=midi[i].status==0xf8;stop|=midi[i].status==0xfc;}
            check(clock && !stop,"finishing arp capture preserves running master MIDI clock");}
        check(controls().value[FMER_ARP_ENABLE] && !performance().recording,"capture stop leaves arp enabled and recording off");
    }
}
void one_step_launch_refreshes_display(){
 reset();restore(scene(1));midi_config(true);fmer_dsp_midi(0xfa,0,0,1);fmer_dsp_midi(0xf8,0,0,1);render(919);
 check(fmer_dsp_transport(FMER_TRANSPORT_LAUNCH_ALL),"queue one-step tracks");render(128);
 for(unsigned tick=1;tick<96;++tick){fmer_dsp_midi(0xf8,0,0,1);render(919);}
 const auto pending=pattern();check(pending.track_launch[0],"one-step launch remains pending before bar");
 fmer_dsp_midi(0xf8,0,0,1);render(128);const auto launched=pattern();
 check(!launched.track_launch[0] && launched.revision!=pending.revision,"one-step launch indicator refreshes even when cursor/pattern unchanged");
}
void tempo_delay_and_repeat_capture(){
    reset();set(FMER_DELAY_MS,327);set(FMER_TEMPO,120);set(FMER_DELAY_SYNC,1);render(128);
    check(pattern().delay_ms==500,"quarter delay follows internal120 BPM");
    set(FMER_DELAY_SYNC,2);render(128);check(pattern().delay_ms==375,"dotted eighth delay follows internal tempo");
    set(FMER_TEMPO,60);render(128);check(pattern().delay_ms==750,"tempo edits update delay without rewriting free time");
    set(FMER_DELAY_SYNC,0);render(128);check(pattern().delay_ms==327,"Free restores exact independent millisecond setting");
    set(FMER_DELAY_SYNC,7);render(128);check(pattern().delay_ms==1000,"long synced delay explicitly reaches buffer capacity");
    midi_config(true);fmer_dsp_midi(0xfa,0,0,1);
    for(unsigned i=0;i<48;++i){fmer_dsp_midi(0xf8,0,0,1);render(919);}
    set(FMER_DELAY_SYNC,1);render(4410);check(pattern().delay_ms>=499 && pattern().delay_ms<=501,"external MIDI pulse period drives delay timing");
    reset();restore(scene(16));set(FMER_RECORD_MODE,1);set(FMER_ARP_ENABLE,1);set(FMER_ARP_ORDER,6);set(FMER_ARP_OCTAVES,4);
    for(unsigned note=48;note<64;++note)fmer_dsp_midi(0x90,static_cast<uint8_t>(note),32,3);
    const auto errors=performance().performance_errors;
    check(fmer_dsp_transport(FMER_TRANSPORT_ARP_RECORD),"expanded Repeat capture arms");render(110250);
    check(performance().performance_errors==errors,"expanded Repeat cannot exhaust mono recording held-note capacity");
    check(native().pitch[0]<128,"Repeat records one generated mono onset");
}
void stopped_live_preview_preserves_mixer(){
    for(unsigned engine:{0u,1u}){
        reset();auto s=scene();s.controls.value[FMER_ENGINE]=engine;
        s.controls.value[FMER_TRACK_MUTE]=1;s.tracks[0].mute=1;
        for(auto& track:s.tracks)track.mute=1;
        restore(s);fmer_midi_settings_t settings{};fmer_midi_defaults(&settings);settings.value[FMER_MIDI_ROUTE]=3;
        check(fmer_dsp_set_midi_settings(&settings)!=0,"live MIDI setup");
        midi_count=0;
        fmer_dsp_midi(0x90,69,100,3);check(render(4096)>.001,"stopped physical keys sound on muted selected track");
        check(native().tracks[0].mute && controls().value[FMER_TRACK_MUTE],"audition never clears saved mute");
        check(sent(0x90,0,69)==1,"stopped keys also audition over routed MIDI");
        fmer_dsp_transport(FMER_TRANSPORT_PLAY);render(4096);
        check(render(4096)==0,"playback restores all track mutes including live monitor");
        check(sent(0x80,0,69)>=1,"starting muted playback releases external preview");
        fmer_dsp_transport(FMER_TRANSPORT_STOP);fmer_dsp_midi(0x80,69,0,3);render(4096);
        fmer_dsp_midi(0x90,72,100,3);check(render(4096)>.001,"new key auditions again after Stop");
        fmer_dsp_midi(0x80,72,0,3);render(44100*3);check(!fmer_dsp_active(),"preview release has no stuck voice");
        settings.value[FMER_MIDI_LOCAL]=0;check(fmer_dsp_set_midi_settings(&settings),"local off accepted");
        fmer_dsp_midi(0x90,74,100,3);check(render(4096)==0,"preview never overrides Local Off");
    }
    reset();auto solo_scene=scene();solo_scene.tracks[1].solo=1;restore(solo_scene);
    fmer_dsp_midi(0x90,67,100,3);check(render(4096)>.001,"stopped keys audition a track excluded by another solo");
    check(native().tracks[1].solo && !native().tracks[0].solo,"audition preserves solo ownership");
    set(FMER_TRACK_LEVEL,0);render(8192);check(render(4096)==0,"preview still honors zero track level");

}
void arp_respects_split_midi_mute(){
    reset();restore(scene());set(FMER_SEQ_TRACK,2);set(FMER_ARP_ENABLE,1);midi_count=0;
    fmer_dsp_midi(0x90,72,100,3);render(256);
    check(sent(0x90,12,72)==1 && sent(0x90,10,72)==0,"arp follows selected part MIDI channel");
    set(FMER_TRACK_MUTE,1);render(22050);
    check(sent(0x90,12,72)>1,"stopped arp auditions through stored mute");
    check(native().tracks[2].mute,"arp preview preserves mute");
    fmer_dsp_transport(FMER_TRANSPORT_PLAY);render(256);const auto attacks=sent(0x90,12,72);render(22050);
    check(sent(0x80,12,72)>=1 && sent(0x90,12,72)==attacks,"running mixer mute gates arp MIDI");
}

}
int main() {
    try {
        check(fmer_dsp_init()!=0,"adapter initializes");fmer_dsp_set_midi_output(midi_output);fmer_dsp_set_event_tap(tap);
        const auto boot=native();
        check(fmer_native_state_valid(&boot)==FMER_NATIVE_OK,"fresh boot is a valid full native project before any restore");
        for(unsigned t=0;t<4;++t)check(boot.tracks[t].pattern==t && boot.tracks[t].chain_mask==0 &&
            boot.tracks[t].sound==64 && boot.tracks[t].level==100 && !boot.tracks[t].mute,
            "fresh boot assigns four distinct first patterns and no accidental chains");
        std::array<uint8_t,FMER_NATIVE_BYTES> wire{};check(fmer_dsp_original_default(8,wire.data())!=0,"USER fixture original available");fmer_dsp_cache_sound(0,wire.data());
        initial=native();unsigned failures=0;
        const auto run=[&](const char* name,void(*test)()) {try{test();std::cout<<"PASS "<<name<<'\n';}catch(const std::exception& e){++failures;std::cout<<"FAIL "<<name<<": "<<e.what()<<'\n';}};
        run("single_song_keys_and_arp",single_song_keys_and_arp);run("patch_browse_preserves_mode",patch_browse_preserves_mode);run("modulation_recipes_persist",modulation_recipes_persist);
        run("navigation_keeps_single_song_playable",navigation_keeps_single_song_playable);run("explicit_mode_wheel_audio",explicit_mode_wheel_audio);
        run("explicit_poly_choice_overrides_glide_resume",explicit_poly_choice_overrides_glide_resume);
        run("stopped_live_preview_preserves_mixer",stopped_live_preview_preserves_mixer);run("one_step_launch_refreshes_display",one_step_launch_refreshes_display);run("tempo_delay_and_repeat_capture",tempo_delay_and_repeat_capture);run("arp_capture_records_generated_notes",arp_capture_records_generated_notes);run("arp_respects_split_midi_mute",arp_respects_split_midi_mute);
        run("global_polyphony_escape",global_polyphony_escape);run("four_tracks_and_owner_release",four_tracks_and_owner_release);run("queues_and_track_names",queues_and_track_names);
        run("mute_sends_immediate_off",mute_sends_immediate_off);run("timed_record_and_native_roundtrip",timed_record_and_native_roundtrip);
        run("independent_chain_metadata_restore",independent_chain_metadata_restore);run("migrated_legacy_chain_restore",migrated_legacy_chain_restore);
        run("external_record_mirrors_into_native",external_record_mirrors_into_native);run("arp_survives_parts_mode",arp_survives_parts_mode);
        run("remote_part_edits_and_snapshots",remote_part_edits_and_snapshots);run("unavailable_reference_is_atomic",unavailable_reference_is_atomic);
        run("incoming_parts_and_record_ownership",incoming_parts_and_record_ownership);run("multitrack_adapter_allocates_nothing",multitrack_adapter_allocates_nothing);
        run("single_mode_live_recording",single_mode_live_recording);run("multitimbral_midi_routes",multitimbral_midi_routes);
        run("single_live_external_recording",single_live_external_recording);
        run("automatic_glide_and_fx_order",automatic_glide_and_fx_order);run("fx_survive_all_bank_auditions",fx_survive_all_bank_auditions);run("standalone_glide_audio",standalone_glide_audio);
        run("fx_fast_path_matches_full_apply",fx_fast_path_matches_full_apply);run("fx_fast_path_rejects_invalid_batches",fx_fast_path_rejects_invalid_batches);
        run("panel_mixer_audio_levels",panel_mixer_audio_levels);run("panel_parts_entry_tracks_editor",panel_parts_entry_tracks_editor);
        run("selective_instrument_apply_matches_full_sync",selective_instrument_apply_matches_full_sync);
        run("algorithm_is_selected_instrument_state",algorithm_is_selected_instrument_state);
        run("upper_pattern_queue_and_overdub_preservation",upper_pattern_queue_and_overdub_preservation);
        run("mono_adapter_returns_to_held_pitch",mono_adapter_returns_to_held_pitch);
        run("repeat_reports_mono_admission",repeat_reports_mono_admission);
        run("single_live_external_restart_keeps_upper_chain",single_live_external_restart_keeps_upper_chain);
        run("performance_solo_fx_and_persistence",performance_solo_fx_and_persistence);
        run("merged_channel_balances_same_pitch",merged_channel_balances_same_pitch);
        run("fx_bypass_is_actual_audio_routing",fx_bypass_is_actual_audio_routing);
        run("direct_edit_workflow_and_undo",direct_edit_workflow_and_undo);
        run("silent_countin_shared_downbeat",silent_countin_shared_downbeat);
        std::cout<<"multitrack adapter failures="<<failures<<'\n';return failures?1:0;
    }catch(const std::exception& e){std::cerr<<"multitrack adapter setup failure: "<<e.what()<<'\n';return 1;}
}

