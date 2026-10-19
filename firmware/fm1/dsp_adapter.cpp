// FMER's shared musical core behind the board's single-owner C boundary.
#include "dsp_adapter.h"
#include "synth.hpp"
#include "effects.hpp"
#include "delay_timing.h"
#include "finite_float.hpp"
#include "parameters.hpp"
#include "performance.hpp"
#include "multitrack.hpp"
#include "pattern_edit.hpp"
#include "performance_commands.h"
#include "modulation_profiles.h"
#include "factory_presets.hpp"
#include "memory_layout.h"
#include <algorithm>
#include <cmath>

namespace {
constexpr uint8_t seq_source = 4, arp_source = 5;
constexpr uint32_t block_capacity = 128, owner_capacity = 96;
fmer::Synth* synth;
fmer::Effects* effects;
fmer::Sequencer* sequencer;
fmer::MultitrackSequencer* multi;
fmer_native_track_t tracks[4]{};
fmer::PartParameters* parts; // Explicit boot construction; board has no C++ init-array runner.
uint8_t track_midi_owned[4][128]{};
uint32_t click_remaining{},click_phase{};
uint32_t mirrored_multi_revision{},multi_view_signature{};
uint8_t arp_part{};
fmer::Arpeggiator* arpeggiator;
fmer::Patch patch;
fmer::VaParameters va;
fmer::Pattern pattern;
fmer_controls_t controls{};
uint16_t fx_order{},fx_default{};
uint8_t modulation[2]{};
// Bank Select is scoped to transport and channel; USB and TRS cannot steal banks.
uint8_t midi_bank[2][16][2]{};
uint16_t poly_resume{4};
float scratch[block_capacity],dry_bus[block_capacity];
uint8_t quiet_frame[block_capacity];
bool countin_quiet{},arp_capture{},preview_previous{};
uint8_t arp_capture_note{128};
uint32_t synced_delay_ms{};
uint64_t synced_delay_refresh{};
fmer::MonoPattern edit_clipboard,edit_undo,edit_after;
uint8_t clipboard_length{},undo_pattern{16},edit_result{};
bool same_pattern(const fmer::MonoPattern& a,const fmer::MonoPattern& b){
    if(a.length!=b.length)return false;
    for(unsigned i=0;i<64;++i)if(a.steps[i].pitch!=b.steps[i].pitch || a.steps[i].velocity!=b.steps[i].velocity || a.steps[i].gate_percent!=b.steps[i].gate_percent)return false;
    return true;
}
struct InputOwner {
    uint8_t source{}, channel{}, pitch{}, velocity{};
    bool active{}, held{};
    uint8_t part{};
};
InputOwner owners[owner_capacity];
bool pedal[16]{};
bool recording{}, rendering{}, single_live{}, single_sequence_requested{};
uint64_t frame{}, rendered_to{}, render_end{};
uint32_t attacks_this_block{}, generated_drops{}, emitted_notes{}, performance_errors{}, revision{};
uint32_t pattern_revision{1};
uint32_t current_preset{FMER_NATIVE_CUSTOM_PRESET};
bool sound_dirty{};
bool instrument_controls_synced{};
fmer_dsp_event_tap_t event_tap{};
bool generated_notes[2][128]{};
struct DefaultSound { uint8_t vced[155]; uint16_t extended[19]; uint16_t fx[5],glide[3]; char name[11]; bool edited; };
DefaultSound default_sounds[128] FMER_WORKSPACE {}; // Boot/storage owner; unchanged hot RAM access.
fmer_midi_settings_t midi_settings{{0,0,1,0,0,1,0,0}};
fmer_midi_metrics_t midi_metrics{};
fmer_dsp_midi_output_t midi_output{};
uint8_t midi_owned[128]{}; // Physical/sequence/arp ownership on one explicit TX channel.
bool midi_clock_running{}, external_running{}, have_clock{}, midi_from_input{};
uint64_t midi_next_clock{}, midi_clock_remainder{}, last_clock{};
uint32_t clock_period{919};
uint64_t sensing_frame[2]{}; bool sensing[2]{};

void increment(uint32_t& value) { if (value != UINT32_MAX) ++value; }
void state_modified() { if (++revision == 0) revision = 1; }
void pattern_modified() { if (++pattern_revision == 0) pattern_revision = 1; }
void checked(bool success) { if (!success) increment(performance_errors); }
bool midi_send(uint8_t status,uint8_t a=0,uint8_t b=0) {
    if (!midi_output) return false;
    const int accepted=midi_output(status,a,b);
    if(accepted==2)return false;
    if (!accepted) { increment(midi_metrics.output_refused); return false; }
    if (status==0xf8) increment(midi_metrics.sent_clock);
    if ((status&0xf0)==0x90 && b) increment(midi_metrics.sent_notes);
    return true;
}
uint8_t track_channel(uint8_t t);
bool part_owner_on_channel(uint8_t channel,uint8_t pitch,uint8_t except=4){
    for(uint8_t t=0;t<4;++t)if(t!=except && track_channel(t)==channel && track_midi_owned[t][pitch])return true;
    return false;
}
void midi_note(uint8_t source,uint8_t pitch,uint8_t velocity) {
    if (source<3 || source>5) return;
    const auto bit=static_cast<uint8_t>(1u<<(source-3));
    auto& owned=midi_owned[pitch]; const auto channel=midi_settings.value[FMER_MIDI_TX_CHANNEL];
    const auto route=midi_settings.value[FMER_MIDI_ROUTE];
    if (velocity) {
        const bool allowed=source==3 ? route==1 || (route==3 && !controls.value[FMER_ARP_ENABLE]) : route>=2;
        if (!allowed) return;
        if (owned || part_owner_on_channel(channel,pitch)) midi_send(static_cast<uint8_t>(0x80|channel),pitch);
        if (midi_send(static_cast<uint8_t>(0x90|channel),pitch,velocity)) owned|=bit;
    } else if (owned&bit) {
        owned=static_cast<uint8_t>(owned&~bit);
        if (!owned && !part_owner_on_channel(channel,pitch)) midi_send(static_cast<uint8_t>(0x80|channel),pitch);
    }
}
uint8_t track_channel(uint8_t t){return static_cast<uint8_t>((midi_settings.value[FMER_MIDI_TX_CHANNEL]+(midi_settings.value[7]?0:t))&15u);}
bool track_quiet(uint8_t t){
    bool solo=false;for(const auto& track:tracks)solo=solo||track.solo;
    return tracks[t].mute || (solo&&!tracks[t].solo);
}
bool live_preview(){return !recording && !sequencer->running() && !multi->running() && !multi->record_armed();}
bool other_midi_owner(uint8_t t,uint8_t pitch){
    const auto channel=track_channel(t);
    return (channel==midi_settings.value[FMER_MIDI_TX_CHANNEL] && midi_owned[pitch]) || part_owner_on_channel(channel,pitch,t);
}
void release_track_midi(uint8_t t,uint8_t mask=7){
    for(uint32_t n=0;n<128;++n)if(track_midi_owned[t][n]){
        const auto before=track_midi_owned[t][n];
        track_midi_owned[t][n]&=static_cast<uint8_t>(~mask);
        if(before!=track_midi_owned[t][n] && !track_midi_owned[t][n] && !other_midi_owner(t,static_cast<uint8_t>(n)))midi_send(static_cast<uint8_t>(0x80|track_channel(t)),static_cast<uint8_t>(n));
    }
}
void update_mix(){
    for(uint8_t t=0;t<4;++t){const bool quiet=track_quiet(t);if(quiet)release_track_midi(t,live_preview()?1:7);
        checked(synth->set_part_mix(t,tracks[t].level*.01f,quiet));}
}
void midi_release_all() {
    for(uint8_t t=0;t<4;++t)release_track_midi(t);
    bool any=false;
    for (uint32_t n=0;n<128;++n) if(midi_owned[n]) {
        any=true;midi_send(static_cast<uint8_t>(0x80|midi_settings.value[FMER_MIDI_TX_CHANNEL]),static_cast<uint8_t>(n));midi_owned[n]=0;
    }
    if(any) {midi_send(static_cast<uint8_t>(0xb0|midi_settings.value[FMER_MIDI_TX_CHANNEL]),64,0);
             midi_send(static_cast<uint8_t>(0xb0|midi_settings.value[FMER_MIDI_TX_CHANNEL]),123,0);}
}
void render_to(uint64_t at) {
    if (!rendering || at < rendered_to || at > render_end) { increment(performance_errors); return; }
    const auto offset=static_cast<uint32_t>(rendered_to-frame),count=static_cast<uint32_t>(at-rendered_to);
    uint8_t bypass=0;for(unsigned t=0;t<4;++t)if(tracks[t].fx_bypass)bypass|=1u<<t;
    synth->render(scratch+offset,count,dry_bus+offset,bypass,live_preview()?((1u<<3)|(1u<<arp_source)):0);
    for(uint32_t i=offset;i<offset+count;++i){quiet_frame[i]=countin_quiet;if(countin_quiet)scratch[i]=dry_bus[i]=0.f;}
    for(uint32_t i=static_cast<uint32_t>(rendered_to-frame);i<at-frame && click_remaining;++i){
        dry_bus[i]+=(click_phase++%32u<16u?.10f:-.10f)*(float(click_remaining)/441.f);--click_remaining;
    }
    rendered_to = at;
}
void part_midi_note(uint8_t,uint8_t,uint8_t,uint8_t,bool);
bool generated(void*, const fmer::Event& event) {
    if (rendering) render_to(event.frame);
    else if (event.frame != frame) { increment(performance_errors); return false; }
    if (event.type==fmer::EventType::Start || event.type==fmer::EventType::Continue || event.type==fmer::EventType::Stop) {
        if(arp_capture && event.source==fmer::EventSource::Arpeggiator)return true;
        const bool stopped=event.type==fmer::EventType::Stop;
        if(stopped && arp_capture && arpeggiator->running())return true;
        // Independent generators share one transport. Joining or leaving an
        // already-running clock must not restart/stop the external follower.
        const bool other=event.source==fmer::EventSource::Arpeggiator?
            (multi->running() || sequencer->running()):arpeggiator->running();
        if(other && midi_clock_running)return true;
        midi_clock_running=!stopped;
        if(!stopped){midi_next_clock=event.frame;midi_clock_remainder=0;}
        if(midi_settings.value[FMER_MIDI_CLOCK_SEND] && !midi_settings.value[FMER_MIDI_CLOCK_SOURCE])
            midi_send(stopped?0xfc:event.type==fmer::EventType::Start?0xfa:0xfb);
        return true;
    }
    if(event.type!=fmer::EventType::NoteOn && event.type!=fmer::EventType::NoteOff)return true;
    const auto source = event.source == fmer::EventSource::Sequencer ? seq_source : arp_source;
    const auto velocity=event.type==fmer::EventType::NoteOn?event.data2:0;
    if(arp_capture && source==arp_source){
        // The destination is monophonic. Repeat chords keep their final onset,
        // without filling the physical-key recording history with expanded notes.
        if(velocity){
            if(arp_capture_note<128)checked(multi->record_note_off(arp_capture_note));
            arp_capture_note=event.data1;checked(multi->record_note_on(event.data1,event.data2));
        }else if(event.data1==arp_capture_note){
            checked(multi->record_note_off(event.data1));arp_capture_note=128;
        }
    }
    if(controls.value[FMER_SEQ_MODE])part_midi_note(arp_part,event.data1,velocity,4,midi_settings.value[FMER_MIDI_ROUTE]>=2);
    else midi_note(source,event.data1,velocity);
    auto& admitted = generated_notes[source == seq_source ? 0 : 1][event.data1];
    if (event.type == fmer::EventType::NoteOn) {
        // Repeat expands at most128 notes. Advertise skipped attacks, rather
        // than initializing128 voices only to steal124 in one audio half.
        if (attacks_this_block >= synth->voice_budget()) { increment(generated_drops); return true; }
        ++attacks_this_block;
        if(midi_settings.value[FMER_MIDI_LOCAL]){
            if(controls.value[FMER_SEQ_MODE])synth->part_note_on(arp_part,event.channel,event.data1,event.data2,source,false);
            else synth->note_on(event.channel, event.data1, event.data2, source, false);
        }
        admitted = true;
        if (event_tap) event_tap(static_cast<uint32_t>(event.frame), static_cast<uint8_t>(0x90 | event.channel), event.data1, event.data2, source);
        increment(emitted_notes);
    } else if (event.type == fmer::EventType::NoteOff && admitted) {
        if(controls.value[FMER_SEQ_MODE])synth->part_note_off(arp_part,event.channel,event.data1,source);
        else synth->note_off(event.channel, event.data1, source);
        admitted = false;
        if (event_tap) event_tap(static_cast<uint32_t>(event.frame), static_cast<uint8_t>(0x80 | event.channel), event.data1, 0, source);
    }
    return true;
}
fmer::EventSink sink() { return {nullptr, generated}; }
bool parts_mode(){return controls.value[FMER_SEQ_MODE]!=0;}
uint8_t selected_track(){return static_cast<uint8_t>(controls.value[FMER_SEQ_TRACK]);}
bool multi_playback(){return parts_mode() || single_live;}
uint8_t playback_track(){return parts_mode()?selected_track():0;}
void part_midi_note(uint8_t t,uint8_t pitch,uint8_t velocity,uint8_t bit,bool allowed){
    auto& owned=track_midi_owned[t][pitch];const auto ch=track_channel(t);
    if(velocity){if(!allowed || (track_quiet(t) && !(bit!=1 && live_preview())))return;if(owned || other_midi_owner(t,pitch))midi_send(static_cast<uint8_t>(0x80|ch),pitch);
        if(midi_send(static_cast<uint8_t>(0x90|ch),pitch,velocity))owned|=bit;
    }else if(owned&bit){owned=static_cast<uint8_t>(owned&~bit);if(!owned && !other_midi_owner(t,pitch))midi_send(static_cast<uint8_t>(0x80|ch),pitch);}
}
bool track_generated(void*,uint8_t t,const fmer::Event& e){
    if(arp_capture && t==multi->record_track())return true; // Monitor the arp once, never its captured copy.
    if(t>=4 || !parts_mode())return generated(nullptr,e);
    if(rendering)render_to(e.frame);
    else if(e.frame!=frame){increment(performance_errors);return false;}
    const bool on=e.type==fmer::EventType::NoteOn;
    if(!on && e.type!=fmer::EventType::NoteOff)return true;
    part_midi_note(t,e.data1,on?e.data2:0,1,midi_settings.value[FMER_MIDI_ROUTE]>=2);
    if(on){
        if(midi_settings.value[FMER_MIDI_LOCAL] && !track_quiet(t))synth->part_note_on(t,e.channel,e.data1,e.data2,seq_source,false);
        increment(emitted_notes);
    }else synth->part_note_off(t,e.channel,e.data1,seq_source);
    if(event_tap)event_tap(static_cast<uint32_t>(e.frame),static_cast<uint8_t>((on?0x90:0x80)|e.channel),e.data1,on?e.data2:0,seq_source);
    return true;
}
bool count_click(void*,uint64_t at,uint8_t remaining){
    if(rendering)render_to(at);
    countin_quiet=remaining!=0;
    click_remaining=remaining?441:0;click_phase=0;
    if(!remaining && arp_capture){
        checked(arpeggiator->start(at,sink()));
        if(midi_settings.value[FMER_MIDI_CLOCK_SOURCE])checked(arpeggiator->clock(at,clock_period,sink()));
    }
    return true;
}
bool capture_boundary(void*,uint64_t at){
    return !arp_capture || arpeggiator->advance(at+1,sink());
}
fmer::TrackSink track_sink(){return {nullptr,track_generated,count_click,capture_boundary};}
fmer::MonoPattern compact(const fmer::Pattern& p){
    fmer::MonoPattern m;m.length=p.length;
    for(unsigned i=0;i<64;++i)m.steps[i]={static_cast<uint8_t>(p.steps[i].tie?FMER_TIE:p.steps[i].note_count?p.steps[i].notes[0].pitch:FMER_REST),p.steps[i].notes[0].velocity,p.steps[i].gate_percent};
    return m;
}
fmer::Pattern expanded(const fmer::MonoPattern& m){
    fmer::Pattern p;p.length=m.length;
    for(unsigned i=0;i<64;++i){const auto& a=m.steps[i];auto& b=p.steps[i];b.tie=a.pitch==FMER_TIE;b.note_count=a.pitch<FMER_REST?1:0;b.notes[0]={static_cast<uint8_t>(a.pitch<FMER_REST?a.pitch:60),a.velocity};b.gate_percent=a.gate_percent;}
    return p;
}
fmer::GlideParameters glide_for(const fmer_controls_t& c){return {static_cast<fmer::GlideMode>(c.value[FMER_GLIDE_MODE]),float(c.value[FMER_GLIDE_MS]),static_cast<fmer::GlideContour>(c.value[FMER_GLIDE_CURVE])};}
void part_controls(const fmer::PartParameters& p,fmer_controls_t& c){
    for(unsigned i=0;i<145;++i)c.value[i]=p.patch.vced[i];
    const auto& v=p.va;c.value[FMER_ENGINE]=p.engine==fmer::SynthEngine::va;
    c.value[FMER_LFO_ENABLE]=p.lfo_enabled;c.value[FMER_VA_WAVE]=static_cast<uint16_t>(v.waveform);
    c.value[FMER_VA_CUTOFF]=static_cast<uint16_t>(v.cutoff_hz);c.value[FMER_RESONANCE]=static_cast<uint16_t>(v.resonance*100.f+.5f);
    c.value[FMER_ATTACK]=static_cast<uint16_t>(v.attack_ms);c.value[FMER_DECAY]=static_cast<uint16_t>(v.decay_ms);
    c.value[FMER_SUSTAIN]=static_cast<uint16_t>(v.sustain*100.f+.5f);c.value[FMER_RELEASE]=static_cast<uint16_t>(v.release_ms);
    c.value[FMER_LFO_RATE]=static_cast<uint16_t>(v.lfo_rate_hz*100.f+.5f);c.value[FMER_LFO_DEPTH]=static_cast<uint16_t>(v.lfo_depth_cents);
    c.value[FMER_GLIDE_MODE]=static_cast<uint16_t>(p.glide.mode);c.value[FMER_GLIDE_MS]=static_cast<uint16_t>(p.glide.time_ms);c.value[FMER_GLIDE_CURVE]=static_cast<uint16_t>(p.glide.contour);
}
bool sound_part(uint32_t slot,fmer::PartParameters& p){
    if(slot>=128)return false;
    fmer::FactoryPreset recipe;
    const auto& saved=default_sounds[slot];
    if(!saved.edited){if(slot<64 || !fmer::load_factory_preset(slot-64,recipe))return false;p.patch=recipe.patch;p.engine=recipe.engine;p.va=recipe.va;p.glide={};p.lfo_enabled=recipe.lfo_enabled;return true;}
    std::copy_n(saved.vced,155,p.patch.vced.begin());const auto* v=saved.extended;
    p.engine=v[0]?fmer::SynthEngine::va:fmer::SynthEngine::fm;
    p.va.waveform=static_cast<fmer::VaWaveform>(v[1]);p.va.cutoff_hz=v[17];p.va.resonance=v[3]*.01f;
    p.va.attack_ms=v[4];p.va.decay_ms=v[5];p.va.sustain=v[6]*.01f;p.va.release_ms=v[7];p.va.lfo_rate_hz=v[15]*.01f;p.va.lfo_depth_cents=v[16];
    p.lfo_enabled=saved.fx[2]!=0;p.glide={static_cast<fmer::GlideMode>(saved.glide[0]),float(saved.glide[1]),static_cast<fmer::GlideContour>(saved.glide[2])};return true;
}
void configure_single(){
    single_live=true;
    for(uint8_t t=0;t<4;++t)checked(multi->configure_track(t,
        {static_cast<uint8_t>(t?tracks[t].pattern:controls.value[FMER_SEQ_PATTERN]),
         static_cast<uint16_t>(!t && controls.value[FMER_SEQ_CHAIN]?controls.value[FMER_SEQ_CHAIN_MASK]:0),0,t==0},frame,track_sink()));
}
void configure_tracks(){
    if(!parts_mode()){configure_single();return;}
    for(uint8_t t=0;t<4;++t){checked(synth->configure_part(t,parts[t]));checked(synth->set_part_mix(t,tracks[t].level*.01f,track_quiet(t)));
        checked(multi->configure_track(t,{tracks[t].pattern,tracks[t].chain_mask,t,true},frame,track_sink(),true));}
}

uint32_t edit_pattern() { return controls.value[FMER_SEQ_PATTERN]; }
void publish_pattern() { checked(sequencer->set_pattern(edit_pattern(), pattern, true));checked(multi->set_pattern(edit_pattern(),compact(pattern),true)); }
void refresh_step() {
    const auto& step = pattern.steps[controls.value[FMER_SEQ_STEP]];
    controls.value[FMER_SEQ_PITCH] = step.tie ? FMER_TIE : step.note_count ? step.notes[0].pitch : FMER_REST;
    controls.value[FMER_SEQ_VELOCITY] = step.notes[0].velocity;
    controls.value[FMER_SEQ_GATE] = step.gate_percent;
}
void mirror_recorded_patterns() {
    if(mirrored_multi_revision==multi->pattern_revision())return;
    // Recording mutates one shared pattern. Do not expand/copy the entire
    // pool inside the audio callback on every performed step.
    const auto bank=multi->record_pattern();
    if(bank<FMER_PATTERN_BANKS) {
        checked(sequencer->set_pattern(bank,expanded(*multi->pattern(bank)),true));
        if(bank==edit_pattern()){pattern=*sequencer->pattern(bank);refresh_step();}
    }
    state_modified();
    mirrored_multi_revision=multi->pattern_revision();pattern_modified();
}
bool pitch_owned(uint8_t pitch) {
    for (const auto& owner : owners) if (owner.active && owner.pitch == pitch) return true;
    return false;
}
InputOwner* find_owner(uint8_t source, uint8_t channel, uint8_t pitch) {
    for (auto& owner : owners)
        if (owner.active && owner.source == source && owner.channel == channel && owner.pitch == pitch) return &owner;
    return nullptr;
}
void stop_sequence() {
    arp_capture=false;
    if(multi && multi->running())checked(multi->stop(frame,track_sink()));
    click_remaining=0;countin_quiet=false;
    const bool queued = sequencer->queued_pattern() < FMER_PATTERN_BANKS;
    if (sequencer->running()) checked(sequencer->stop(frame, sink()));
    if (queued && sequencer->queued_pattern() >= FMER_PATTERN_BANKS) pattern_modified();
    synth->panic_source(seq_source);
}
void stop_arp() {
    if (arpeggiator->running()) checked(arpeggiator->stop(frame, sink()));
    checked(arpeggiator->clear(frame, sink()));
    synth->panic_source(arp_source);
}
void restore_live_owners() {
    uint32_t admitted = 0;
    for (const auto& owner : owners) if (owner.active) {
        if(owner.source==3 && owner.held){if(parts_mode())part_midi_note(owner.part,owner.pitch,owner.velocity,2,midi_settings.value[FMER_MIDI_ROUTE]==1||midi_settings.value[FMER_MIDI_ROUTE]==3);else midi_note(3,owner.pitch,owner.velocity);}
        if(owner.source==3 && !midi_settings.value[FMER_MIDI_LOCAL])continue;
        if (admitted++ >= synth->voice_budget()) { increment(generated_drops); continue; }
        if(parts_mode()){
            synth->part_note_on(owner.part,owner.channel,owner.pitch,owner.velocity,owner.source,true);
            if(!owner.held)synth->part_note_off(owner.part,owner.channel,owner.pitch,owner.source);
        }else{
            synth->note_on(owner.channel, owner.pitch, owner.velocity, owner.source);
            if (!owner.held) synth->note_off(owner.channel, owner.pitch, owner.source);
        }
    }
}
void rebuild_arp() {
    stop_arp();
    for (const auto& owner : owners) if (owner.active && !arpeggiator->note_on(owner.pitch, owner.velocity))
        increment(generated_drops);
    if (controls.value[FMER_ARP_ENABLE] && (!midi_settings.value[FMER_MIDI_CLOCK_SOURCE] || external_running)) checked(arpeggiator->start(frame, sink()));
}
void set_arp_enabled(bool enabled) {
    if (enabled) {
        arp_part=selected_track();
        if(midi_settings.value[FMER_MIDI_CLOCK_SOURCE] && !midi_settings.value[FMER_MIDI_TRANSPORT_RX])external_running=true;
        if(midi_settings.value[FMER_MIDI_ROUTE]==3)for(uint32_t n=0;n<128;++n)midi_note(3,static_cast<uint8_t>(n),0);
        if(parts_mode())stop_sequence();
        recording = false;
        for (uint8_t source = 1; source <= 3; ++source) synth->panic_source(source);
        controls.value[FMER_ARP_ENABLE] = 1;
        rebuild_arp();
    } else {
        if(arp_capture)stop_sequence();
        stop_arp();
        controls.value[FMER_ARP_ENABLE] = 0;
        restore_live_owners();
    }
}
fmer::ArpSettings arp_settings(const fmer_controls_t& c) {
    fmer::ArpSettings result;
    result.order = static_cast<fmer::ArpOrder>(c.value[FMER_ARP_ORDER]);
    result.rate = static_cast<uint8_t>(c.value[FMER_ARP_RATE]);
    result.octaves = static_cast<uint8_t>(c.value[FMER_ARP_OCTAVES]);
    result.gate_percent = static_cast<uint8_t>(c.value[FMER_ARP_GATE]);
    result.latch = c.value[FMER_ARP_LATCH] != 0;
    result.swing = static_cast<uint8_t>(c.value[FMER_ARP_SWING]);
    result.triplet = c.value[FMER_ARP_TRIPLET] != 0;
    return result;
}
void record_note(uint8_t pitch, uint8_t velocity) {
    if(arp_capture)return;
    if(multi_playback() && controls.value[FMER_RECORD_MODE]){checked(multi->record_note_on(pitch,velocity));return;}
    if (!recording) return;
    auto& step = pattern.steps[controls.value[FMER_SEQ_STEP]];
    const bool changed = step.note_count != 1 || step.tie ||
        step.notes[0].pitch != pitch || step.notes[0].velocity != velocity;
    step.note_count = 1; step.tie = false; step.notes[0] = {pitch, velocity};
    publish_pattern();
    if (changed) pattern_modified();
    controls.value[FMER_SEQ_STEP] = static_cast<uint16_t>((controls.value[FMER_SEQ_STEP] + 1) % pattern.length);
    refresh_step(); state_modified();
}
void note_on(uint8_t channel, uint8_t pitch, uint8_t velocity, uint8_t source) {
    auto* owner = find_owner(source, channel, pitch);
    if (!owner) for (auto& candidate : owners) if (!candidate.active) { owner = &candidate; break; }
    if (!owner) { increment(generated_drops); return; }
    const bool first_arp_note = arpeggiator->held_count() == 0;
    if (controls.value[FMER_ARP_ENABLE] && !arpeggiator->note_on(pitch, velocity)) {
        increment(generated_drops); return;
    }
    *owner = {source, channel, pitch, velocity, true, true,static_cast<uint8_t>(source==3?selected_track():channel%4u)};
    if(source==3){if(parts_mode())part_midi_note(owner->part,pitch,velocity,2,midi_settings.value[FMER_MIDI_ROUTE]==1||(midi_settings.value[FMER_MIDI_ROUTE]==3&&!controls.value[FMER_ARP_ENABLE]));else midi_note(source,pitch,velocity);}
    if (controls.value[FMER_ARP_ENABLE]) {
        if (!arp_capture && ((!midi_settings.value[FMER_MIDI_CLOCK_SOURCE] && first_arp_note) ||
            (!arpeggiator->running() && (!midi_settings.value[FMER_MIDI_CLOCK_SOURCE] || external_running)))) {
            if (arpeggiator->running()) checked(arpeggiator->stop(frame, sink()));
            checked(arpeggiator->start(frame, sink()));
        }
    } else if(source!=3 || midi_settings.value[FMER_MIDI_LOCAL]){
        if(parts_mode())synth->part_note_on(owner->part,channel,pitch,velocity,source,true);
        else synth->note_on(channel,pitch,velocity,source);
    }
    if(!parts_mode() || owner->part==multi->record_track())record_note(pitch, velocity);
}
void note_off(uint8_t channel, uint8_t pitch, uint8_t source) {
    auto* owner = find_owner(source, channel, pitch);
    if(source==3){if(parts_mode()){if(owner)part_midi_note(owner->part,pitch,0,2,true);}else midi_note(source,pitch,0);}
    if (owner) {
        owner->held = false;
        if (!pedal[channel]) owner->active = false;
    }
    if (controls.value[FMER_ARP_ENABLE]) {
        if (!pitch_owned(pitch)) checked(arpeggiator->note_off(pitch));
    } else if(parts_mode()){
        if(owner)synth->part_note_off(owner->part,channel,pitch,source);
    }else synth->note_off(channel, pitch, source);
    if(!arp_capture && owner && multi_playback() && (!parts_mode() || owner->part==multi->record_track())) {
        // Releasing an older same-pitch owner must not cut another input's
        // held recording note. Synth voice ownership follows the same rule.
        bool held_elsewhere=false;
        for(const auto& other:owners)if(other.active && other.held && other.pitch==pitch &&
            (!parts_mode() || other.part==multi->record_track()))held_elsewhere=true;
        if(!held_elsewhere)checked(multi->record_note_off(pitch));
    }
}
void release_pedal(uint8_t channel) {
    for (auto& owner : owners) if (owner.active && owner.channel == channel && !owner.held) {
        const auto pitch = owner.pitch;
        owner.active = false;
        if (controls.value[FMER_ARP_ENABLE] && !pitch_owned(pitch)) checked(arpeggiator->note_off(pitch));
    }
}
}

extern "C" int fmer_dsp_init(void) {
    if (synth && effects && sequencer && arpeggiator) return 1;
    synth = new fmer::Synth;
    effects = new fmer::Effects;
    sequencer = new fmer::Sequencer;
    multi = new fmer::MultitrackSequencer;
    parts = new fmer::PartParameters[4];
    arpeggiator = new fmer::Arpeggiator;
    patch = fmer::make_init_patch();
    va = fmer::VaParameters{};
    va.cutoff_hz = 18000.f;
    if (!synth->init() || !synth->set_voice_budget(4) || !synth->set_patch(patch) ||
        !synth->set_va_parameters(va) || !effects->init()) return 0;
    for (uint32_t id = 0; id < fmer::kParameterCount; ++id) controls.value[id] = patch.vced[id];
    controls.value[FMER_GLIDE_MS]=150;controls.value[FMER_TRACK_SOUND]=64;controls.value[FMER_TRACK_LEVEL]=100;
    controls.value[FMER_RECORD_MODE]=1; // Live overdub is the normal recording workflow.
    for(uint8_t t=0;t<4;++t){
        tracks[t].pattern=t;tracks[t].chain_mask=0;tracks[t].sound=64;
        tracks[t].level=100;tracks[t].mute=0;sound_part(64,parts[t]);
    }
    controls.value[FMER_VA_WAVE] = 1;
    controls.value[FMER_CUTOFF] = 20000;
    controls.value[FMER_VA_CUTOFF] = 18000;
    controls.value[FMER_RESONANCE] = 20;
    controls.value[FMER_ATTACK] = 5; controls.value[FMER_DECAY] = 150;
    controls.value[FMER_SUSTAIN] = 70; controls.value[FMER_RELEASE] = 200;
    controls.value[FMER_DELAY_MS] = 250; controls.value[FMER_FEEDBACK] = 35;
    controls.value[FMER_LFO_ENABLE] = 1;
    controls.value[FMER_LFO_RATE] = 500;
    controls.value[FMER_TEMPO] = 120;
    controls.value[FMER_ARP_RATE] = 16; controls.value[FMER_ARP_OCTAVES] = 1;
    controls.value[FMER_ARP_GATE] = 75; controls.value[FMER_ARP_SWING] = 50;
    controls.value[FMER_SEQ_LENGTH] = 16; controls.value[FMER_VOICE_BUDGET] = 4;
    controls.value[FMER_REVERB_DECAY] = 50;
    controls.value[FMER_SEQ_CHAIN_MASK] = 1;
    // Original FMER demonstration; user step edits remain RAM-only.
    const uint8_t notes[] = {60,67,64,67,62,69,65,67};
    for (uint32_t step = 0; step < 16; ++step) if (!(step & 1)) {
        pattern.steps[step].note_count = 1;
        pattern.steps[step].notes[0] = {notes[step / 2], 100};
    }
    refresh_step();checked(multi->set_pattern(0,compact(pattern)));configure_tracks();
    return sequencer->set_pattern(0, pattern) && arpeggiator->configure(arp_settings(controls), 0, sink()) &&
        fmer_dsp_factory_preset(0);
}
extern "C" void fmer_dsp_panic(void) {
    if (!synth) return;
    stop_sequence(); stop_arp(); recording = false;external_running=false;midi_release_all();
    single_live=false;single_sequence_requested=false;
    for (auto& owner : owners) owner.active = false;
    std::fill_n(pedal, 16, false);
    synth->panic(); effects->reset(); state_modified();
}
extern "C" void fmer_dsp_midi(uint8_t status, uint8_t a, uint8_t b, uint8_t source) {
    if (!synth || a > 127 || b > 127 || source < 1 || source > 3) return;
    if(source<3) {sensing_frame[source-1]=frame;if(status==0xfe)sensing[source-1]=true;}
    if(status>=0xf0) {
        if(status==0xff){fmer_dsp_panic();return;}
        if(source==3 || source!=midi_settings.value[FMER_MIDI_CLOCK_SOURCE])return;
        if(status==0xf8) {
            increment(midi_metrics.received_clock);
            if(have_clock && frame>last_clock) {
                const auto elapsed=frame-last_clock;
                if(elapsed>=128 && elapsed<=11025)clock_period=(clock_period*3u+static_cast<uint32_t>(elapsed))/4u;
            }
            have_clock=true;last_clock=frame;
            if(external_running) {
                if(multi_playback() && multi->running()){
                    if(arpeggiator->running())checked(arpeggiator->clock(frame,clock_period,sink()));
                    checked(multi->clock(frame,clock_period,track_sink()));mirror_recorded_patterns();
                }
                else if(sequencer->running())checked(sequencer->clock(frame,clock_period,sink()));
                else if(arpeggiator->running())checked(arpeggiator->clock(frame,clock_period,sink()));
            }
        } else if(midi_settings.value[FMER_MIDI_TRANSPORT_RX]) {
            if(status==0xfa || status==0xfb) {
                external_running=true;have_clock=false;recording=false;increment(midi_metrics.received_start);
                const bool run_sequence=!controls.value[FMER_ARP_ENABLE] || arp_capture || (!parts_mode() && single_sequence_requested);
                if(controls.value[FMER_ARP_ENABLE] && !arp_capture) {
                    if(arpeggiator->running())checked(arpeggiator->stop(frame,sink()));
                    checked(status==0xfa?arpeggiator->start(frame,sink()):arpeggiator->resume(frame,sink()));
                }
                if(run_sequence && multi_playback()){
                    const bool armed=multi->record_armed();const auto record_track=multi->record_track();
                    if(multi->running())checked(multi->stop(frame,track_sink()));
                    checked(status==0xfa?multi->start(frame,track_sink()):multi->resume(frame,track_sink()));
                    if(armed)checked(multi->arm_record(record_track,frame,track_sink(),controls.value[FMER_RECORD_MODE]==2?fmer::RecordMode::replace:fmer::RecordMode::overdub));
                } else if(run_sequence) {
                    if(multi->running())checked(multi->stop(frame,track_sink()));
                if(sequencer->running())checked(sequencer->stop(frame,sink()));
                    if(status==0xfa) {checked(sequencer->select_pattern(edit_pattern(),frame,sink()));checked(sequencer->start(frame,sink()));}
                    else checked(sequencer->resume(frame,sink()));
                }
                state_modified();
            } else if(status==0xfc) {
                external_running=false;increment(midi_metrics.received_stop);
                if(multi->running())checked(multi->stop(frame,track_sink()));
                if(sequencer->running())checked(sequencer->stop(frame,sink()));
                if(arpeggiator->running())checked(arpeggiator->stop(frame,sink()));
                recording=false;state_modified();
            } else if(status==0xf2) {
                if(multi_playback())checked(multi->song_position(static_cast<uint16_t>(a|(b<<7)),frame,track_sink()));
                checked(sequencer->song_position(static_cast<uint16_t>(a|(b<<7)),frame,sink()));
                increment(midi_metrics.received_song_position);state_modified();
            }
        }
        return;
    }
    struct InputScope {bool previous;InputScope(bool value):previous(midi_from_input){midi_from_input=value;}~InputScope(){midi_from_input=previous;}} input_scope(source!=3);
    const auto channel = static_cast<uint8_t>(status & 15);
    if (source != 3 && controls.value[FMER_MIDI_CHANNEL] &&
        controls.value[FMER_MIDI_CHANNEL] != static_cast<uint32_t>(channel)+1u) return;
    if(source!=3 && (!parts_mode() || channel<4u) && (status&0xf0)==0xb0 && (a==0 || a==32)) {
        midi_bank[source-1][channel][a==32]=b;return;
    }
    const auto bank=source<3?midi_bank[source-1][channel][0]:0;
    const auto bank_lsb=source<3?midi_bank[source-1][channel][1]:0;
    const auto program_slot=static_cast<uint32_t>(a)+(bank==0?64u:0u);
    const bool program_valid=a<64u && bank<2u && bank_lsb==0;
    if(parts_mode() && source!=3){
        if(channel>=4u)return; // Four explicit receive channels1..4; no modulo aliases.
        if((status&0xf0)==0xc0){
            if(program_valid){fmer::PartParameters candidate;if(sound_part(program_slot,candidate)){
                if(channel==selected_track())checked(fmer_dsp_audition(program_slot)!=0);
                else {parts[channel]=candidate;tracks[channel].sound=static_cast<uint16_t>(program_slot);checked(synth->configure_part(channel,candidate));state_modified();pattern_modified();}
            }}return;
        }
        if((status&0xf0)==0xb0 && (a==71 || a==72 || a==73 || a==74)){
            auto& p=parts[channel];
            if(a==74)p.va.cutoff_hz=b==127?18000.f:20.f*std::exp2(b*(9.813781f/127.f));
            if(a==71)p.va.resonance=b*(.95f/127.f);
            if(a==73)p.va.attack_ms=b*(10000.f/127.f);
            if(a==72)p.va.release_ms=b*(10000.f/127.f);
            checked(synth->configure_part(channel,p));
            if(channel==selected_track()){auto next=controls;part_controls(p,next);checked(fmer_dsp_apply_controls(&next)!=0);}
            state_modified();return;
        }
    }
    switch (status & 0xf0) {
    case 0x80: note_off(channel, a, source); break;
    case 0x90: if (b) note_on(channel, a, b, source); else note_off(channel, a, source); break;
    case 0xb0:
        if(a==91 || a==93 || a==95 || a==12) {
            auto next=controls;const auto id=a==91?FMER_REVERB:a==93?FMER_CHORUS:a==95?FMER_PHASER:FMER_DELAY;
            next.value[id]=static_cast<uint16_t>(b*100u/127u);checked(fmer_dsp_apply_controls(&next)!=0);break;
        }
        // Common performance CCs use canonical controls and the same ownership
        // policy as the panel. Filter cutoff is live; VA voice edits retrigger.
        if (a == 74 || a == 71 || a == 73 || a == 72) {
            auto next = controls;
            if (a == 74) next.value[FMER_CUTOFF] = static_cast<uint16_t>(b == 127 ? 20000 :
                20.f * std::exp2(static_cast<float>(b) * (9.965784285f / 127.f)));
            if (a == 71) next.value[FMER_RESONANCE] = static_cast<uint16_t>(b * 95u / 127u);
            if (a == 73) next.value[FMER_ATTACK] = static_cast<uint16_t>(b * 10000u / 127u);
            if (a == 72) next.value[FMER_RELEASE] = static_cast<uint16_t>(b * 10000u / 127u);
            checked(fmer_dsp_apply_controls(&next) != 0);
            break;
        }
        if (a == 64) {
            pedal[channel] = b >= 64;
            if (!pedal[channel]) release_pedal(channel);
        } else if (a == 121) {
            pedal[channel] = false; release_pedal(channel);
        } else if (a == 120 || a == 123) {
            for (auto& owner : owners) if (owner.active && owner.channel == channel) {
                owner.held = false;
                if (a == 120 || !pedal[channel]) owner.active = false;
            }
            // Explicit MIDI termination also clears latched generated notes.
            // Other channels' physical owners survive a bounded rebuild.
            if (controls.value[FMER_ARP_ENABLE]) rebuild_arp();
        }
        synth->control_change(channel,a,b); break;
    case 0xc0: if(program_valid) {fmer::PartParameters candidate;if(sound_part(program_slot,candidate))checked(fmer_dsp_audition(program_slot)!=0);} break;
    case 0xe0: synth->pitch_bend(channel, static_cast<uint16_t>(a | (b << 7))); break;
    }
}
extern "C" int fmer_dsp_patch(const uint8_t* bytes, uint32_t length) {
    if (!synth || !bytes || length != fmer::kVcedSize) return 0;
    auto next = patch;
    std::copy_n(bytes, length, next.vced.begin());
    if (!synth->set_patch(next)) return 0;
    patch = next;
    instrument_controls_synced=false;
    if(parts_mode()){parts[selected_track()].patch=next;checked(synth->configure_part(selected_track(),parts[selected_track()]));}
    current_preset = FMER_NATIVE_CUSTOM_PRESET; sound_dirty = true;
    for (uint32_t id = 0; id < fmer::kParameterCount; ++id) controls.value[id] = patch.vced[id];
    state_modified(); return 1;
}
extern "C" int fmer_dsp_parameter(uint32_t id, uint32_t value) {
    if (!synth || id >= fmer::kParameterCount || value > 127) return 0;
    auto next = patch;
    if (!fmer::set_parameter(next, static_cast<uint16_t>(id), static_cast<int>(value)) || !synth->set_patch(next)) return 0;
    patch = next; controls.value[id] = static_cast<uint16_t>(value);instrument_controls_synced=false;
    if(parts_mode()){parts[selected_track()].patch=next;checked(synth->configure_part(selected_track(),parts[selected_track()]));}
    sound_dirty = true; state_modified(); return 1;
}
extern "C" void fmer_dsp_get_controls(fmer_controls_t* out) { if (out) *out = controls; }
extern "C" void fmer_dsp_set_event_tap(fmer_dsp_event_tap_t tap) { event_tap = tap; }
static bool shared_fx_control(uint32_t id) {
    switch(id) {
    case FMER_DELAY_SYNC:case FMER_FILTER_TYPE:case FMER_FX_RESONANCE:case FMER_REVERB_MODEL:case FMER_DELAY_MODEL:
    case FMER_CUTOFF:case FMER_DRIVE:case FMER_CHORUS:case FMER_DELAY:case FMER_DELAY_MS:
    case FMER_FEEDBACK:case FMER_REVERB:case FMER_PHASER:case FMER_REVERB_DECAY:return true;
    default:return false;
    }
}
static fmer::EffectParameters effects_for(const fmer_controls_t& requested) {
    auto next=effects->parameters();
    uint8_t order[6];fmer_fx_unrank(fx_order,order);
    for(unsigned i=0;i<6;++i)next.order[i]=static_cast<fmer::EffectKind>(order[i]);
    next.filter_mode=static_cast<fmer::FilterMode>(requested.value[FMER_FILTER_TYPE]);
    next.resonance=requested.value[FMER_FX_RESONANCE]*.01f;
    next.reverb_model=static_cast<fmer::ReverbModel>(requested.value[FMER_REVERB_MODEL]);
    next.delay_model=static_cast<fmer::DelayModel>(requested.value[FMER_DELAY_MODEL]);
    next.cutoff_hz=static_cast<float>(requested.value[FMER_CUTOFF]);
    next.drive=requested.value[FMER_DRIVE]*.01f;next.chorus=requested.value[FMER_CHORUS]*.01f;
    next.delay=requested.value[FMER_DELAY]*.01f;next.delay_ms=static_cast<float>(fmer_delay_time(requested.value[FMER_DELAY_SYNC],requested.value[FMER_DELAY_MS],
        midi_settings.value[FMER_MIDI_CLOCK_SOURCE] && have_clock ? uint32_t(uint64_t(clock_period)*24000000u/44100u) : 60000000u/requested.value[FMER_TEMPO]));
    next.feedback=requested.value[FMER_FEEDBACK]*.01f;next.reverb=requested.value[FMER_REVERB]*.01f;
    next.phaser=requested.value[FMER_PHASER]*.01f;next.reverb_decay=requested.value[FMER_REVERB_DECAY]*.01f;
    next.chorus_rate_hz=fmer_modulation_rate(0,modulation[0]);next.chorus_depth=fmer_modulation_depth(0,modulation[0]);
    next.phaser_rate_hz=fmer_modulation_rate(1,modulation[1]);next.phaser_depth=fmer_modulation_depth(1,modulation[1]);
    return next;
}
static void send_control_ccs(const fmer_controls_t& requested) {
    if(!midi_settings.value[FMER_MIDI_CC_SEND] || midi_from_input)return;
    const uint32_t ids[]={parts_mode()?FMER_VA_CUTOFF:FMER_CUTOFF,FMER_RESONANCE,FMER_ATTACK,FMER_RELEASE,FMER_DELAY,FMER_REVERB,FMER_CHORUS,FMER_PHASER};
    const uint8_t ccs[]={74,71,73,72,12,91,93,95};
    for(uint32_t i=0;i<8;++i)if(requested.value[ids[i]]!=controls.value[ids[i]]) {
        const float v=requested.value[ids[i]];
        const auto scaled=i==0?std::log2(v/20.f)*(127.f/(parts_mode()?9.813781f:9.965784285f)):i==1?v*(127.f/95.f):i<4?v*(127.f/10000.f):v*(127.f/100.f);
        midi_send(static_cast<uint8_t>(0xb0|(parts_mode() && i<4?track_channel(selected_track()):midi_settings.value[FMER_MIDI_TX_CHANNEL])),ccs[i],static_cast<uint8_t>(std::clamp(scaled+0.5f,0.f,127.f)));
    }
}
static int apply_controls(const fmer_controls_t* requested,bool allow_fx_fast_path) {
    if (!synth || !requested) return 0;
    const bool resync=!allow_fx_fast_path || !instrument_controls_synced;
    bool patch_changed=resync,va_changed=resync,glide_changed=resync,fx_changed=false;
    bool engine_changed=resync,lfo_changed=resync;
    bool fx_only=allow_fx_fast_path && instrument_controls_synced && !parts_mode();
    for (uint32_t id = 0; id < FMER_PARAM_COUNT; ++id) {
        if (!fmer_control_valid(id, requested->value[id])) return 0;
        if(requested->value[id]!=controls.value[id]) {
            const bool is_fx=shared_fx_control(id);fx_changed=fx_changed||is_fx;
            if(!is_fx)fx_only=false;
            if(id<145u)patch_changed=true;
            if(id==FMER_VA_WAVE || (id>=FMER_RESONANCE && id<=FMER_RELEASE) ||
               (id>=FMER_LFO_RATE && id<=FMER_VA_CUTOFF))va_changed=true;
            if(id>=FMER_GLIDE_MODE && id<=FMER_GLIDE_CURVE)glide_changed=true;
            if(id==FMER_ENGINE)engine_changed=true;
            if(id==FMER_LFO_ENABLE)lfo_changed=true;
        }
    }
    if (requested->value[FMER_SEQ_STEP] >= requested->value[FMER_SEQ_LENGTH]) return 0;
    // A pure shared-FX edit cannot change note snapshots, instrument settings or
    // sequencer ownership. Keep their validated state intact while using the
    // identical FX setter/CC conversion as the full path. Imports opt out.
    if(fx_only && fx_changed) {
        const auto next_fx=effects_for(*requested);send_control_ccs(*requested);
        checked(effects->set_parameters(next_fx));controls=*requested;
        sound_dirty=true;state_modified();return 1;
    }
    auto adjusted=*requested;
    const bool mode_changed=adjusted.value[FMER_SEQ_MODE]!=controls.value[FMER_SEQ_MODE];
    const bool track_changed=adjusted.value[FMER_SEQ_TRACK]!=controls.value[FMER_SEQ_TRACK];
    if(track_changed && arp_capture && (multi->recording() || multi->record_armed()))return 0;
    const auto tr=static_cast<uint8_t>(adjusted.value[FMER_SEQ_TRACK]);
    const bool sound_selected=!track_changed && adjusted.value[FMER_TRACK_SOUND]!=controls.value[FMER_TRACK_SOUND];
    if(sound_selected){if(!sound_part(adjusted.value[FMER_TRACK_SOUND],parts[tr]))return 0;part_controls(parts[tr],adjusted);
        if(!adjusted.value[FMER_SEQ_MODE])for(unsigned id=FMER_GLIDE_MODE;id<=FMER_GLIDE_CURVE;id++)adjusted.value[id]=controls.value[id];}
    if(track_changed){part_controls(parts[tr],adjusted);adjusted.value[FMER_TRACK_SOUND]=tracks[tr].sound;adjusted.value[FMER_TRACK_LEVEL]=tracks[tr].level;adjusted.value[FMER_TRACK_MUTE]=tracks[tr].mute;adjusted.value[FMER_SEQ_PATTERN]=multi->selected_pattern(tr);adjusted.value[FMER_SEQ_CHAIN]=tracks[tr].chain_mask!=0;adjusted.value[FMER_SEQ_CHAIN_MASK]=tracks[tr].chain_mask?tracks[tr].chain_mask:1;}
    if(track_changed || sound_selected)patch_changed=va_changed=glide_changed=engine_changed=lfo_changed=true;
    // An explicit mode change opens the selected track's saved assignment.
    // Native import already supplies an exact independent editor snapshot.
    if(allow_fx_fast_path && mode_changed && adjusted.value[FMER_SEQ_MODE]) {
        adjusted.value[FMER_SEQ_PATTERN]=tracks[tr].pattern;
        adjusted.value[FMER_SEQ_CHAIN]=tracks[tr].chain_mask!=0;
        adjusted.value[FMER_SEQ_CHAIN_MASK]=tracks[tr].chain_mask?tracks[tr].chain_mask:1;
        const auto& assigned=*sequencer->pattern(tracks[tr].pattern);const auto& first=assigned.steps[0];
        adjusted.value[FMER_SEQ_LENGTH]=assigned.length;adjusted.value[FMER_SEQ_STEP]=0;
        adjusted.value[FMER_SEQ_PITCH]=first.tie?FMER_TIE:first.note_count?first.notes[0].pitch:FMER_REST;
        adjusted.value[FMER_SEQ_VELOCITY]=first.notes[0].velocity;adjusted.value[FMER_SEQ_GATE]=first.gate_percent;
    }
    if(adjusted.value[FMER_SEQ_MODE])adjusted.value[FMER_VOICE_BUDGET]=4;
    else if(adjusted.value[FMER_GLIDE_MODE]) {
        if(resync || mode_changed || !controls.value[FMER_GLIDE_MODE])
            poly_resume=adjusted.value[FMER_VOICE_BUDGET]>1?adjusted.value[FMER_VOICE_BUDGET]:4;
        adjusted.value[FMER_VOICE_BUDGET]=1;
    } else if(!resync && controls.value[FMER_GLIDE_MODE] && !controls.value[FMER_SEQ_MODE] &&
              adjusted.value[FMER_VOICE_BUDGET]<=1u)
        // An ordinary Glide Off retains the current mono budget in its request,
        // so restore remembered polyphony. An explicit nonmono budget in the
        // same transaction (4V mode wheel/hotkey/companion) takes precedence.
        adjusted.value[FMER_VOICE_BUDGET]=poly_resume;
    requested=&adjusted;
    if(mode_changed){fmer_dsp_panic();checked(synth->set_parts_enabled(false));}
    for (uint32_t id=0; id<178u; ++id)
        if (requested->value[id] != controls.value[id]) sound_dirty = true;
    if (requested->value[FMER_REVERB_DECAY] != controls.value[FMER_REVERB_DECAY]) sound_dirty = true;
    if (requested->value[FMER_MIDI_CHANNEL] != controls.value[FMER_MIDI_CHANNEL]) fmer_dsp_panic();
    const bool bank_selected = requested->value[FMER_SEQ_PATTERN] != controls.value[FMER_SEQ_PATTERN];
    const bool selected = bank_selected || requested->value[FMER_SEQ_STEP] != controls.value[FMER_SEQ_STEP];
    const bool pattern_changed = !bank_selected && (requested->value[FMER_SEQ_LENGTH] != controls.value[FMER_SEQ_LENGTH] ||
        (!selected && (requested->value[FMER_SEQ_PITCH] != controls.value[FMER_SEQ_PITCH] ||
        requested->value[FMER_SEQ_VELOCITY] != controls.value[FMER_SEQ_VELOCITY] ||
        requested->value[FMER_SEQ_GATE] != controls.value[FMER_SEQ_GATE])));
    const auto old_tempo=controls.value[FMER_TEMPO];
    const bool tempo_changed = requested->value[FMER_TEMPO] != old_tempo;
    send_control_ccs(*requested);
    bool arp_changed = tempo_changed;
    for (uint32_t id = FMER_ARP_ORDER; id <= FMER_ARP_SWING; ++id)
        arp_changed = arp_changed || requested->value[id] != controls.value[id];
    arp_changed = arp_changed || requested->value[FMER_ARP_TRIPLET] != controls.value[FMER_ARP_TRIPLET];
    const bool enable_changed = requested->value[FMER_ARP_ENABLE] != controls.value[FMER_ARP_ENABLE];
    const bool chain_changed = requested->value[FMER_SEQ_CHAIN] != controls.value[FMER_SEQ_CHAIN] ||
        requested->value[FMER_SEQ_CHAIN_MASK] != controls.value[FMER_SEQ_CHAIN_MASK];
    // Every prospective value above has been validated. These core setters
    // cannot refuse a value in the shared control model's narrower ranges.
    // Only changed instrument groups need conversion, validation and snapshot
    // copies. The complete control batch was validated before any mutation;
    // patch names originate from validated native/cache/patch entry points.
    if(patch_changed) {
        if(track_changed || sound_selected)std::copy_n(parts[tr].patch.vced.begin()+145,10,patch.vced.begin()+145);
        for(uint32_t id=0;id<fmer::kParameterCount;++id)patch.vced[id]=static_cast<uint8_t>(requested->value[id]);
        checked(synth->set_patch(patch));parts[tr].patch=patch;
    }
    if(va_changed) {
        va.waveform=static_cast<fmer::VaWaveform>(requested->value[FMER_VA_WAVE]);
        va.cutoff_hz=static_cast<float>(requested->value[FMER_VA_CUTOFF]);va.resonance=requested->value[FMER_RESONANCE]*.01f;
        va.attack_ms=static_cast<float>(requested->value[FMER_ATTACK]);va.decay_ms=static_cast<float>(requested->value[FMER_DECAY]);
        va.sustain=requested->value[FMER_SUSTAIN]*.01f;va.release_ms=static_cast<float>(requested->value[FMER_RELEASE]);
        va.lfo_rate_hz=static_cast<float>(requested->value[FMER_LFO_RATE])/100.f;va.lfo_depth_cents=static_cast<float>(requested->value[FMER_LFO_DEPTH]);
        checked(synth->set_va_parameters(va));parts[tr].va=va;
    }
    if(resync || fx_changed || requested->value[FMER_TEMPO]!=controls.value[FMER_TEMPO])checked(effects->set_parameters(effects_for(*requested)));
    if(lfo_changed){synth->set_lfo_enabled(requested->value[FMER_LFO_ENABLE]!=0);parts[tr].lfo_enabled=requested->value[FMER_LFO_ENABLE]!=0;}
    if(engine_changed){parts[tr].engine=requested->value[FMER_ENGINE]?fmer::SynthEngine::va:fmer::SynthEngine::fm;checked(synth->set_engine(parts[tr].engine));}
    if(resync || mode_changed || requested->value[FMER_VOICE_BUDGET]!=controls.value[FMER_VOICE_BUDGET]) {
        checked(synth->set_voice_budget(requested->value[FMER_VOICE_BUDGET]));
        checked(synth->set_mono(!requested->value[FMER_SEQ_MODE] && requested->value[FMER_VOICE_BUDGET]==1));
    }
    if(glide_changed){parts[tr].glide=glide_for(*requested);checked(synth->set_glide(parts[tr].glide));}
    if(requested->value[FMER_TRACK_MUTE] && !tracks[tr].mute){
        release_track_midi(tr);
    }
    tracks[tr].sound=static_cast<uint8_t>(requested->value[FMER_TRACK_SOUND]);tracks[tr].level=static_cast<uint8_t>(requested->value[FMER_TRACK_LEVEL]);tracks[tr].mute=static_cast<uint8_t>(requested->value[FMER_TRACK_MUTE]);
    if(mode_changed && requested->value[FMER_SEQ_MODE]){for(uint8_t t=0;t<4;++t)if(t!=tr)checked(sound_part(tracks[t].sound,parts[t]));checked(synth->set_parts_enabled(true));}
    if(requested->value[FMER_SEQ_MODE]) {
        if(mode_changed || track_changed || patch_changed || va_changed || glide_changed || engine_changed || lfo_changed)checked(synth->configure_part(tr,parts[tr]));
        if(resync || mode_changed || track_changed || requested->value[FMER_TRACK_LEVEL]!=controls.value[FMER_TRACK_LEVEL] ||
           requested->value[FMER_TRACK_MUTE]!=controls.value[FMER_TRACK_MUTE])checked(synth->set_part_mix(tr,tracks[tr].level*.01f,track_quiet(tr)));
    }
    const bool old_enabled = controls.value[FMER_ARP_ENABLE] != 0;
    for(uint32_t i=FMER_SEQ_MODE;i<=FMER_RECORD_MODE;++i)if(controls.value[i]!=requested->value[i]){pattern_modified();break;}
    controls = *requested;
    if(track_changed && controls.value[FMER_ARP_ENABLE]){
        const bool running=arpeggiator->running();
        if(running)checked(arpeggiator->stop(frame,sink()));
        arp_part=tr;
        if(running)checked(arpeggiator->resume(frame,sink()));
    }
    if (bank_selected) {
        pattern = *sequencer->pattern(edit_pattern());
        controls.value[FMER_SEQ_LENGTH] = pattern.length;
        controls.value[FMER_SEQ_STEP] = 0;
        if(single_live){
            if(multi->running())checked(multi->queue_pattern(0,static_cast<uint8_t>(edit_pattern())));
            else checked(multi->configure_track(0,{static_cast<uint8_t>(edit_pattern()),static_cast<uint16_t>(controls.value[FMER_SEQ_CHAIN]?controls.value[FMER_SEQ_CHAIN_MASK]:0),0,true},frame,track_sink()));
        }else if(parts_mode()){
            if(!track_changed){if(multi->running())checked(multi->queue_pattern(tr,static_cast<uint8_t>(edit_pattern())));else {tracks[tr].pattern=static_cast<uint8_t>(edit_pattern());checked(multi->configure_track(tr,{tracks[tr].pattern,tracks[tr].chain_mask,tr,true},frame,track_sink()));}}
        }
        else if (sequencer->running()) checked(sequencer->queue_pattern(edit_pattern()));
        else checked(sequencer->select_pattern(edit_pattern(), frame, sink()));
        pattern_modified();
    }
    if (pattern_changed) {
        pattern.length = static_cast<uint8_t>(controls.value[FMER_SEQ_LENGTH]);
        if (!selected) {
            auto& step = pattern.steps[controls.value[FMER_SEQ_STEP]];
            step.note_count = controls.value[FMER_SEQ_PITCH] < FMER_REST ? 1 : 0;
            step.tie = controls.value[FMER_SEQ_PITCH] == FMER_TIE;
            if (step.note_count) step.notes[0].pitch = static_cast<uint8_t>(controls.value[FMER_SEQ_PITCH]);
            step.notes[0].velocity = static_cast<uint8_t>(controls.value[FMER_SEQ_VELOCITY]);
            step.gate_percent = static_cast<uint8_t>(controls.value[FMER_SEQ_GATE]);
        }
        publish_pattern();
        pattern_modified();
    }
    refresh_step();
    sequencer->set_chain_mask(controls.value[FMER_SEQ_CHAIN] ? controls.value[FMER_SEQ_CHAIN_MASK] : 0);
    if (chain_changed){
        const uint16_t chain=controls.value[FMER_SEQ_CHAIN]?controls.value[FMER_SEQ_CHAIN_MASK]:0;
        if(parts_mode())tracks[tr].chain_mask=chain;
        const auto playback=parts_mode()?tr:uint8_t{0};
        checked(multi->configure_track(playback,{multi->selected_pattern(playback),chain,playback,true},frame,track_sink()));pattern_modified();
    }
    if(mode_changed)configure_tracks();
    if (tempo_changed) {
        if(midi_clock_running && midi_next_clock>frame)midi_next_clock=frame+(midi_next_clock-frame)*old_tempo/requested->value[FMER_TEMPO];
        checked(sequencer->set_tempo(controls.value[FMER_TEMPO], true));
        checked(multi->set_tempo(controls.value[FMER_TEMPO],true));
        checked(arpeggiator->set_tempo(controls.value[FMER_TEMPO], true));
    }
    if (arp_changed) checked(arpeggiator->configure(arp_settings(controls), frame, sink(), true));
    if (enable_changed) set_arp_enabled(!old_enabled);
    instrument_controls_synced=true;
    state_modified(); return 1;
}
extern "C" int fmer_dsp_apply_controls(const fmer_controls_t* requested) {return apply_controls(requested,true);}
extern "C" int fmer_dsp_audition(uint32_t slot) {
    if(!synth)return 0;fmer::PartParameters sound;if(!sound_part(slot,sound))return 0;
    auto next=controls;part_controls(sound,next);
    if(!parts_mode())for(unsigned id=FMER_GLIDE_MODE;id<=FMER_GLIDE_CURVE;id++)next.value[id]=controls.value[id];
    next.value[FMER_TRACK_SOUND]=static_cast<uint16_t>(slot);
    if(!fmer_dsp_apply_controls(&next))return 0;
    std::copy_n(sound.patch.vced.begin()+145,10,patch.vced.begin()+145);parts[selected_track()].patch=patch;
    current_preset=slot>=64?slot-64:FMER_NATIVE_CUSTOM_PRESET;sound_dirty=false;state_modified();return 1;
}
extern "C" int fmer_dsp_factory_preset(uint32_t index) {return index<64?fmer_dsp_audition(index+64):0;}
extern "C" uint32_t fmer_dsp_preset_id(void) { return current_preset; }
extern "C" const char* fmer_dsp_factory_name(uint32_t index) {
    return index<64 && default_sounds[index+64].edited?default_sounds[index+64].name:fmer::factory_preset_name(index);
}
extern "C" void fmer_dsp_cache_default(uint32_t index,const uint8_t* wire) {if(index<64)fmer_dsp_cache_sound(index+64,wire);}
extern "C" void fmer_dsp_cache_sound(uint32_t index,const uint8_t* wire) {
    if(index>=128)return;
    auto& saved=default_sounds[index];
    if(!wire){saved.edited=false;return;}
    std::copy_n(wire+FMER_NATIVE_VCED,155,saved.vced);
    for(uint32_t i=0;i<18;++i)saved.extended[i]=fmer_native_rd16(wire+32+(160+i)*2);
    for(uint32_t i=0;i<5;++i)saved.fx[i]=fmer_native_rd16(wire+32+(145+i)*2);
    if(fmer_native_rd16(wire+8)<3u)saved.fx[2]=1;
    saved.extended[18]=fmer_native_rd16(wire+32+FMER_REVERB_DECAY*2);
    for(uint32_t i=0;i<10;++i)saved.name[i]=static_cast<char>(saved.vced[145+i]);
    for(uint32_t i=0;i<3;++i)saved.glide[i]=fmer_native_rd16(wire+32+2*(150+i));
    if(fmer_native_rd16(wire+8)<4)saved.glide[1]=150;
    saved.name[10]=0;saved.edited=true;
}
extern "C" int fmer_dsp_original_default(uint32_t index,uint8_t* wire) {
    fmer::FactoryPreset recipe;
    if(!wire || !fmer::load_factory_preset(index,recipe))return 0;
    fmer_native_state_t state{};
    const uint16_t defaults[38]={0,1,20000,20,5,150,70,200,0,0,0,250,35,0,0,500,0,18000,
        120,0,0,16,1,75,0,50,16,0,128,100,75,4,0,0,50,0,0,1};
    std::copy_n(defaults,38,state.controls.value+160);
    state.controls.value[FMER_LFO_ENABLE]=recipe.lfo_enabled?1:0;
    std::copy_n(recipe.patch.vced.begin(),155,state.vced);
    for(uint32_t i=0;i<145;++i)state.controls.value[i]=state.vced[i];
    auto* c=state.controls.value;const auto& p=recipe.va;
    c[FMER_ENGINE]=recipe.engine==fmer::SynthEngine::va?1:0;
    c[FMER_VA_WAVE]=static_cast<uint16_t>(p.waveform);c[FMER_VA_CUTOFF]=static_cast<uint16_t>(p.cutoff_hz);
    c[FMER_RESONANCE]=static_cast<uint16_t>(p.resonance*100.f+.5f);
    c[FMER_ATTACK]=static_cast<uint16_t>(p.attack_ms);c[FMER_DECAY]=static_cast<uint16_t>(p.decay_ms);
    c[FMER_SUSTAIN]=static_cast<uint16_t>(p.sustain*100.f+.5f);c[FMER_RELEASE]=static_cast<uint16_t>(p.release_ms);
    c[FMER_LFO_RATE]=static_cast<uint16_t>(p.lfo_rate_hz*100.f+.5f);c[FMER_LFO_DEPTH]=static_cast<uint16_t>(p.lfo_depth_cents);
    state.preset_id=static_cast<uint16_t>(index);state.length=16;fmer_native_track_defaults(&state);
    std::fill_n(state.pitch,64,128);std::fill_n(state.velocity,64,100);std::fill_n(state.gate,64,75);
    for(auto& pat:state.patterns){pat.length=16;std::fill_n(pat.pitch,64,128);std::fill_n(pat.velocity,64,100);std::fill_n(pat.gate,64,75);}
    return fmer_native_encode(&state,wire,FMER_NATIVE_BYTES)==FMER_NATIVE_OK;
}
extern "C" uint32_t fmer_dsp_sound_dirty(void) { return sound_dirty?1u:0u; }
extern "C" uint32_t fmer_dsp_state_generation(void) { return revision; }
extern "C" void fmer_dsp_patch_name(char out[11]) {
    if (!out) return;
    for (uint32_t i=0;i<10;++i) {
        const auto ch=patch.vced[145+i];
        out[i]=ch>='a' && ch<='z'?static_cast<char>(ch-'a'+'A'):
            ch>=32 && ch<127?static_cast<char>(ch):' ';
    }
    out[10]=0;
}
extern "C" void fmer_dsp_get_native(fmer_native_state_t* out) {
    if (!out || !synth) return;
    *out={}; out->controls=controls;out->fx_order=fx_order;std::copy_n(modulation,2,out->modulation);out->song=multi->song();
    std::copy_n(tracks,4,out->tracks);
    for(uint8_t t=0;t<4;++t)if(parts_mode())out->tracks[t].pattern=multi->selected_pattern(t);
    std::copy_n(patch.vced.begin(),155,out->vced);
    out->source_generation=revision;
    out->preset_id=static_cast<uint16_t>(sound_dirty?FMER_NATIVE_CUSTOM_PRESET:current_preset);
    for (uint32_t bank=0;bank<FMER_PATTERN_BANKS;++bank) {
        const auto& saved=*sequencer->pattern(bank);
        auto* pitch=bank?out->patterns[bank-1].pitch:out->pitch;
        auto* velocity=bank?out->patterns[bank-1].velocity:out->velocity;
        auto* gate=bank?out->patterns[bank-1].gate:out->gate;
        if(bank)out->patterns[bank-1].length=saved.length;else out->length=saved.length;
        for (uint32_t i=0;i<64;++i) {
            const auto& step=saved.steps[i];
            pitch[i]=step.tie?FMER_TIE:step.note_count?step.notes[0].pitch:FMER_REST;
            velocity[i]=step.notes[0].velocity;gate[i]=step.gate_percent;
        }
    }
}
extern "C" int fmer_dsp_set_native(const fmer_native_state_t* state,uint32_t expected_generation) {
    if (!synth || !state || revision!=expected_generation ||
        fmer_native_state_valid(state)!=FMER_NATIVE_OK) return 0;
    if(state->controls.value[FMER_SEQ_MODE]){fmer::PartParameters candidate;for(uint8_t t=0;t<4;++t)if(!sound_part(state->tracks[t].sound,candidate))return 0;}
    // Validation is complete before the first mutation. No flash, wire CRC or
    // allocation occurs here; runtime owners/tails are deliberately discarded.
    fmer_dsp_panic();undo_pattern=16;edit_result=0;
    for (uint32_t bank=0;bank<FMER_PATTERN_BANKS;++bank) {
        const auto* pitch=bank?state->patterns[bank-1].pitch:state->pitch;
        const auto* velocity=bank?state->patterns[bank-1].velocity:state->velocity;
        const auto* gate=bank?state->patterns[bank-1].gate:state->gate;
        pattern.length=bank?state->patterns[bank-1].length:state->length;
        pattern.channel=0;
        for (uint32_t i=0;i<64;++i) {
            auto& step=pattern.steps[i];step={};step.tie=pitch[i]==FMER_TIE;
            step.note_count=pitch[i]<FMER_REST?1:0;
            step.notes[0]={static_cast<uint8_t>(pitch[i]>=FMER_REST?60:pitch[i]),velocity[i]};
            step.gate_percent=gate[i];
        }
        checked(sequencer->set_pattern(bank,pattern));checked(multi->set_pattern(bank,compact(pattern)));
    }
    std::copy_n(state->tracks,4,tracks);
    for(uint8_t t=0;t<4;++t){if(!sound_part(tracks[t].sound,parts[t])){sound_part(64,parts[t]);} }
    controls.value[FMER_SEQ_TRACK]=state->controls.value[FMER_SEQ_TRACK];
    controls.value[FMER_TRACK_SOUND]=state->controls.value[FMER_TRACK_SOUND];
    // Synchronize the selected bank's edit cursor before applying sound/clock
    // controls, so a restore cannot reinterpret the prior cursor as a step edit.
    for(uint32_t id=FMER_SEQ_LENGTH;id<=FMER_SEQ_GATE;++id)controls.value[id]=state->controls.value[id];
    controls.value[FMER_SEQ_PATTERN]=state->controls.value[FMER_SEQ_PATTERN];
    // Import is a complete snapshot, not a live chain edit. Preserve the saved
    // track assignments even when the legacy editor has a different chain.
    controls.value[FMER_SEQ_CHAIN]=state->controls.value[FMER_SEQ_CHAIN];
    controls.value[FMER_SEQ_CHAIN_MASK]=state->controls.value[FMER_SEQ_CHAIN_MASK];
    pattern=*sequencer->pattern(edit_pattern());
    checked(sequencer->select_pattern(edit_pattern(),frame,sink()));
    std::copy_n(state->vced,155,patch.vced.begin());
    fx_order=state->fx_order;std::copy_n(state->modulation,2,modulation);
    checked(apply_controls(&state->controls,false)!=0);
    configure_tracks();checked(multi->set_song(state->song));refresh_step();pattern_modified();
    current_preset=state->preset_id;sound_dirty=current_preset==FMER_NATIVE_CUSTOM_PRESET;
    state_modified();return 1;
}
extern "C" int fmer_dsp_controls(uint32_t engine, uint32_t cutoff, uint32_t delay_percent) {
    if (engine > 1 || cutoff < 20 || cutoff > 20000 || delay_percent > 100) return 0;
    auto next = controls;
    next.value[FMER_ENGINE] = static_cast<uint16_t>(engine);
    next.value[FMER_CUTOFF] = static_cast<uint16_t>(cutoff);
    next.value[FMER_DELAY] = static_cast<uint16_t>(delay_percent);
    return fmer_dsp_apply_controls(&next);
}
extern "C" int fmer_dsp_voice_controls(uint32_t wave, uint32_t attack_ms, uint32_t release_ms) {
    if (wave > 4 || attack_ms > 10000 || release_ms > 10000) return 0;
    auto next = controls;
    next.value[FMER_VA_WAVE] = static_cast<uint16_t>(wave);
    next.value[FMER_ATTACK] = static_cast<uint16_t>(attack_ms);
    next.value[FMER_RELEASE] = static_cast<uint16_t>(release_ms);
    return fmer_dsp_apply_controls(&next);
}
static int performance_command(uint32_t command) {
    const auto kind=command>>28;
    if(kind==6){
        if(command&0x0ffffefcu)return 0;
        modulation[(command>>8)&1u]=static_cast<uint8_t>(command&3u);
        checked(effects->set_parameters(effects_for(controls)));sound_dirty=true;state_modified();return 1;
    }
    if(kind==5){
        const auto action=(command>>20)&15u,t=(command>>18)&3u,row=(command>>8)&31u;
        int delta=command&255u;if(delta&128)delta-=256;
        if((!parts_mode() && t!=0u) || (command&0x0f030000u) || (command&0xe000u))return 0;
        if(!multi->edit_song(t,row,action,delta)){edit_result=1;pattern_modified();return 0;}
        edit_result=0;state_modified();pattern_modified();return 1;
    }
    if(kind==4){
        const auto effect=(command>>8)&255u;int delta=command&255u;if(delta&128)delta-=256;
        if(command&0x0fff0000u || effect>6u || delta< -6 || delta>6)return 0;
        const auto rank=effect==6u?fx_default:fmer_fx_move(fx_order,effect,delta);
        if(rank!=fx_order){fx_order=static_cast<uint16_t>(rank);checked(effects->set_parameters(effects_for(controls)));sound_dirty=true;state_modified();}
        return 1;
    }
    if(kind==1){
        const auto layer=(command>>20)&15u,t=(command>>18)&3u;
        int delta=command&1023u;if(delta&512)delta-=1024;
        if(!parts_mode() || layer>=FMER_MIX_LAYERS || !delta)return 0;
        if(t!=selected_track()){auto next=controls;next.value[FMER_SEQ_TRACK]=static_cast<uint16_t>(t);if(!apply_controls(&next,true))return 0;}
        auto& track=tracks[t];
        if(layer==FMER_MIX_LEVEL)track.level=static_cast<uint8_t>(std::clamp(int(track.level)+delta,0,100));
        else if(layer==FMER_MIX_MUTE)track.mute=delta>0;
        else if(layer==FMER_MIX_SOLO)track.solo=delta>0;
        else if(layer==FMER_MIX_FX)track.fx_bypass=delta<0;
        else if(layer==FMER_MIX_RUN){
            const bool okay=delta<0?multi->stop_track(static_cast<uint8_t>(t),frame,track_sink()):multi->launch_at_bar(static_cast<uint8_t>(t));
            pattern_modified();return okay;
        }
        else {
            auto c=controls;c.value[FMER_SEQ_TRACK]=static_cast<uint16_t>(t);
            if(!apply_controls(&c,true))return 0;
            c=controls;
            if(layer==FMER_MIX_PATTERN){
                const auto queued=multi->queued_pattern(static_cast<uint8_t>(t));
                c.value[FMER_SEQ_PATTERN]=static_cast<uint16_t>(std::clamp(int(queued<16?queued:multi->selected_pattern(static_cast<uint8_t>(t)))+delta,0,15));
            }else c.value[FMER_TRACK_SOUND]=static_cast<uint16_t>(std::clamp(int(track.sound)+delta,0,127));
            return apply_controls(&c,true);
        }
        if(t==selected_track()){controls.value[FMER_TRACK_LEVEL]=track.level;controls.value[FMER_TRACK_MUTE]=track.mute;}
        update_mix();state_modified();pattern_modified();return 1;
    }
    if(kind!=2 && kind!=3)return 0;
    const auto bank=(command>>20)&15u,start=(command>>14)&63u,action=(command>>24)&15u;
    const auto* source=multi->pattern(bank);if(!source)return 0;
    edit_result=0;
    if(multi->record_armed() || multi->recording()){edit_result=4;pattern_modified();return 1;}
    auto edited=*source;bool okay=false,write=true;
    if(kind==2){
        int value=command&16383u;if(value&8192)value-=16384;
        if(action==FMER_NOTE_MOVE)okay=fmer::move_note(edited,start,value);
        else if(action==FMER_NOTE_LENGTH){const int length=int(fmer::note_length(edited,start))+value;
            okay=length>0 && fmer::resize_note(edited,start,static_cast<unsigned>(length));}
        else if(action==FMER_NOTE_DELETE)okay=fmer::erase_note(edited,start);
        else if(action==FMER_NOTE_REST && start<edited.length){edited.steps[start].pitch=fmer::MonoStep::rest;okay=true;}
    }else {
        const auto count=((command>>8)&63u)+1u,destination=command&63u;
        if(action==FMER_BLOCK_COPY || action==FMER_BLOCK_CUT){
            okay=fmer::copy_steps(edited,start,count,edit_clipboard);
            if(okay)clipboard_length=edit_clipboard.length;
            write=action==FMER_BLOCK_CUT;
        }
        if(action==FMER_BLOCK_CLEAR || (action==FMER_BLOCK_CUT && okay)){
            okay=start<edited.length && count<=edited.length-start;
            if(okay){for(unsigned i=start;i<start+count;++i)edited.steps[i].pitch=fmer::MonoStep::rest;
                if(start+count<edited.length && edited.steps[start+count].pitch==fmer::MonoStep::tie)edited.steps[start+count].pitch=fmer::MonoStep::rest;}
        }
        if(action==FMER_BLOCK_PASTE)okay=clipboard_length && fmer::paste_steps(edited,destination,edit_clipboard);
        if(action==FMER_BLOCK_UNDO){okay=undo_pattern==bank && same_pattern(edited,edit_after);if(okay)edited=edit_undo;}
    }
    if(!okay){edit_result=1;pattern_modified();return 1;}
    if(write){
        edit_undo=*source;edit_after=edited;undo_pattern=static_cast<uint8_t>(bank);
        checked(multi->set_pattern(bank,edited,true));checked(sequencer->set_pattern(bank,expanded(edited),true));
        if(bank==edit_pattern()){
            pattern=expanded(edited);
            if(kind==2 && action==FMER_NOTE_MOVE){int value=command&16383u;if(value&8192)value-=16384;controls.value[FMER_SEQ_STEP]=static_cast<uint16_t>(int(fmer::note_start(edit_undo,start))+value);}
            refresh_step();
        }
        state_modified();
    }
    pattern_modified();return 1;
}
extern "C" int fmer_dsp_transport(uint32_t command) {
    if (!synth) return 0;
    if(command>>28)return performance_command(command);
    if(command==FMER_TRANSPORT_LAUNCH_TRACK || command==FMER_TRANSPORT_LAUNCH_ALL){
        if(!multi_playback() || !multi->running())return 0;
        const bool okay=multi->launch_at_bar(command==FMER_TRANSPORT_LAUNCH_ALL?4:playback_track());
        pattern_modified();return okay;
    }
    if(command==FMER_TRANSPORT_ARP_RECORD){
        if(arp_capture){
            multi->stop_record();mirror_recorded_patterns();
            // Leave the arp performing; stop the recorder and backing patterns.
            checked(multi->stop(frame,track_sink()));arp_capture=false;
            state_modified();pattern_modified();return 1;
        }
        if(!controls.value[FMER_ARP_ENABLE])set_arp_enabled(true);
        stop_sequence();
        if(arpeggiator->running())checked(arpeggiator->stop(frame,sink())); // Retain latched notes.
        if(!parts_mode()){
            single_live=true;
            for(uint8_t t=0;t<4;++t)checked(multi->configure_track(t,{static_cast<uint8_t>(t?tracks[t].pattern:edit_pattern()),0,0,t==0},frame,track_sink()));
        }
        arp_part=playback_track();arp_capture=true;arp_capture_note=128;recording=false;
        if(!controls.value[FMER_RECORD_MODE])controls.value[FMER_RECORD_MODE]=1;
        const bool okay=multi->arm_record(playback_track(),frame,track_sink(),controls.value[FMER_RECORD_MODE]==2?fmer::RecordMode::replace:fmer::RecordMode::overdub);
        if(!okay)arp_capture=false;
        state_modified();pattern_modified();return okay;
    }
    if (command>=FMER_TRANSPORT_PRESET_BASE && command<FMER_TRANSPORT_PRESET_BASE+fmer::factory_preset_count)
        return fmer_dsp_factory_preset(command-FMER_TRANSPORT_PRESET_BASE);
    if(!parts_mode() && command==FMER_TRANSPORT_RECORD && controls.value[FMER_RECORD_MODE]) {
        if(controls.value[FMER_ARP_ENABLE])set_arp_enabled(false);
        if(!single_live) {
            stop_sequence();single_live=true;
            // Reuse the same shared pool, with one cursor feeding the original
            // standalone voice/MIDI path. Four-part project refs remain intact.
            for(uint8_t t=0;t<4;++t)checked(multi->configure_track(t,
                {static_cast<uint8_t>(t?tracks[t].pattern:edit_pattern()),
                 static_cast<uint16_t>(!t && controls.value[FMER_SEQ_CHAIN]?controls.value[FMER_SEQ_CHAIN_MASK]:0),0,t==0},frame,track_sink()));
        }
        recording=false;
        if(multi->record_armed()||multi->recording())multi->stop_record();
        else checked(multi->arm_record(0,frame,track_sink(),controls.value[FMER_RECORD_MODE]==2?fmer::RecordMode::replace:fmer::RecordMode::overdub));
        state_modified();pattern_modified();return 1;
    }
    if(!parts_mode() && command==FMER_TRANSPORT_PLAY){
        recording=false;
        if(multi->running() || sequencer->running()){stop_sequence();single_sequence_requested=false;}
        else {configure_single();single_sequence_requested=true;if(midi_settings.value[FMER_MIDI_CLOCK_SOURCE])external_running=true;
            checked(multi->start(frame,track_sink()));}
        state_modified();pattern_modified();return 1;
    }
    if(!parts_mode() && single_live && (command==FMER_TRANSPORT_STOP || command==FMER_TRANSPORT_RECORD)) {
        const bool was_running=multi->running();stop_sequence();single_live=false;
        if(command==FMER_TRANSPORT_PLAY && was_running){recording=false;state_modified();pattern_modified();return 1;}
    }
    if(parts_mode() && (command==FMER_TRANSPORT_PLAY || command==FMER_TRANSPORT_RECORD)){
        if(controls.value[FMER_ARP_ENABLE])set_arp_enabled(false);
        if(command==FMER_TRANSPORT_RECORD && !controls.value[FMER_RECORD_MODE]){stop_sequence();recording=!recording;}
        else if(command==FMER_TRANSPORT_RECORD){if(multi->record_armed()||multi->recording())multi->stop_record();else checked(multi->arm_record(selected_track(),frame,track_sink(),controls.value[FMER_RECORD_MODE]==2?fmer::RecordMode::replace:fmer::RecordMode::overdub));}
        else {recording=false;if(multi->running())stop_sequence();else {
            if(midi_settings.value[FMER_MIDI_CLOCK_SOURCE])external_running=true;
            checked(multi->start(frame,track_sink()));}}
        state_modified();pattern_modified();return 1;
    }
    switch (command) {
    case FMER_TRANSPORT_PLAY:
        recording = false;
        if (sequencer->running()) stop_sequence();
        else {
            if(midi_settings.value[FMER_MIDI_CLOCK_SOURCE])external_running=true;
            if (controls.value[FMER_ARP_ENABLE]) set_arp_enabled(false);
            if (sequencer->selected_pattern() != edit_pattern()) pattern_modified();
            checked(sequencer->select_pattern(edit_pattern(), frame, sink()));
            checked(sequencer->start(frame, sink()));
        }
        break;
    case FMER_TRANSPORT_RECORD:
        stop_sequence();
        if (controls.value[FMER_ARP_ENABLE]) set_arp_enabled(false);
        recording = !recording; break;
    case FMER_TRANSPORT_STOP:
        stop_sequence(); stop_arp(); recording = false;
        controls.value[FMER_ARP_ENABLE] = 0; break;
    case FMER_TRANSPORT_CLEAR_STEP: {
        const bool changed = pattern.steps[controls.value[FMER_SEQ_STEP]].note_count != 0 ||
            pattern.steps[controls.value[FMER_SEQ_STEP]].tie;
        pattern.steps[controls.value[FMER_SEQ_STEP]].note_count = 0;
        pattern.steps[controls.value[FMER_SEQ_STEP]].tie = false;
        publish_pattern(); refresh_step();
        if (changed) pattern_modified();
        break;
    }
    case FMER_TRANSPORT_PANIC: fmer_dsp_panic(); return 1;
    default: return 0;
    }
    state_modified(); return 1;
}
extern "C" void fmer_dsp_performance(fmer_performance_state_t* out) {
    if (!out) return;
    *out = {};
    if (!sequencer) return;
    out->running = sequencer->running(); out->recording = recording;
    out->seq_position = static_cast<uint32_t>(sequencer->playing_step());
    if(multi_playback()){out->running=multi->running();out->recording=recording||multi->recording()||multi->record_armed();out->seq_position=multi->playing_step(playback_track());}
    out->edit_step = controls.value[FMER_SEQ_STEP];
    out->arp_held = static_cast<uint32_t>(arpeggiator->held_count());
    out->generated_drops = generated_drops; out->emitted_notes = emitted_notes;
    out->performance_errors = performance_errors; out->revision = revision;
    out->step_pitch = controls.value[FMER_SEQ_PITCH];
    out->step_velocity = controls.value[FMER_SEQ_VELOCITY]; out->step_gate = controls.value[FMER_SEQ_GATE];
    out->selected_pattern = edit_pattern(); out->playing_pattern = static_cast<uint32_t>(sequencer->selected_pattern());
    out->queued_pattern = sequencer->queued_pattern() < FMER_PATTERN_BANKS ? static_cast<uint32_t>(sequencer->queued_pattern()) : FMER_PATTERN_BANKS;
    out->chain_mask = controls.value[FMER_SEQ_CHAIN_MASK]; out->chain_enabled = controls.value[FMER_SEQ_CHAIN];
    if(multi_playback()){out->playing_pattern=multi->selected_pattern(playback_track());out->queued_pattern=multi->queued_pattern(playback_track());}
}
extern "C" uint32_t fmer_dsp_pattern_revision(void) { return sequencer ? pattern_revision : 0; }
extern "C" void fmer_dsp_get_pattern(fmer_pattern_state_t* out) {
    if (!out) return;
    *out = {};
    if (!sequencer) return;
    out->song=multi->song();
    for(uint8_t t=0;t<4;t++){out->song_row[t]=multi->song_row(t);out->song_repeat[t]=multi->song_repeat(t);out->song_live[t]=multi->song_live(t);}
    for(uint8_t p=0;p<16;p++)out->pattern_length[p]=multi->pattern(p)->length;
    out->edit_result=edit_result;out->clipboard_length=clipboard_length;out->undo_available=undo_pattern==edit_pattern() && same_pattern(*multi->pattern(edit_pattern()),edit_after);
    out->revision = pattern_revision;out->mode=parts_mode();out->track=selected_track();out->count_in=multi->count_in_remaining();out->count_in_active=multi->record_armed();
    for(uint8_t t=0;t<4;++t){out->delay_ms=static_cast<uint32_t>(effects->parameters().delay_ms);out->track_pattern[t]=multi->selected_pattern(t);out->track_queued[t]=multi->queued_pattern(t);out->track_step[t]=multi->playing_step(t);out->track_level[t]=tracks[t].level;out->track_mute[t]=tracks[t].mute;out->track_solo[t]=tracks[t].solo;out->track_fx[t]=!tracks[t].fx_bypass;out->track_length[t]=multi->pattern(multi->selected_pattern(t))->length;out->track_sound[t]=tracks[t].sound;out->track_stopped[t]=multi->track_stopped(t);out->track_launch[t]=multi->launch_pending(t);}
    out->length = pattern.length;
    out->selected_pattern = edit_pattern(); out->playing_pattern = static_cast<uint32_t>(sequencer->selected_pattern());
    out->queued_pattern = sequencer->queued_pattern() < FMER_PATTERN_BANKS ? static_cast<uint32_t>(sequencer->queued_pattern()) : FMER_PATTERN_BANKS;
    out->chain_mask = controls.value[FMER_SEQ_CHAIN_MASK]; out->chain_enabled = controls.value[FMER_SEQ_CHAIN];
    if(multi_playback()){out->playing_pattern=multi->selected_pattern(playback_track());out->queued_pattern=multi->queued_pattern(playback_track());}
    for (uint32_t index = 0; index < FMER_PATTERN_STEPS; ++index) {
        const auto& step = pattern.steps[index];
        out->pitch[index] = step.tie ? FMER_TIE : step.note_count ? step.notes[0].pitch : FMER_REST;
        out->velocity[index] = step.notes[0].velocity;
        out->gate[index] = step.gate_percent;
    }
}
extern "C" void fmer_dsp_get_activity(fmer_activity_state_t* out) {
    if (!out) return;
    *out = {};
    if (!synth) return;
    const auto state = synth->activity();
    std::copy_n(state.active_notes, 4, out->active_notes);
    std::copy_n(state.gated_notes, 4, out->gated_notes);
    out->active_voices = state.active_voices;
    // advance() emits tick0 at Start and then increments the tick counter.
    // Before its first rendered sample, running with ticks0 is the same phase.
    const auto ticks = multi_playback()?multi->clock_ticks():sequencer->clock_ticks();
    out->beat_on = multi_playback() && multi->record_armed()?multi->count_in_pulse(frame):
        (multi_playback()?multi->running():sequencer->running()) && ((ticks ? ticks - 1 : 0) % 24u) < 4u;
}
extern "C" int fmer_dsp_voice_budget(uint32_t limit) {
    if (!synth || limit < 1 || limit > 4) return 0;
    if(!parts_mode() && controls.value[FMER_GLIDE_MODE])limit=1;
    if(!synth->set_voice_budget(limit))return 0;
    if (controls.value[FMER_VOICE_BUDGET] != limit) {instrument_controls_synced=false;state_modified();}
    controls.value[FMER_VOICE_BUDGET] = static_cast<uint16_t>(limit); return 1;
}
extern "C" void fmer_dsp_part_scopes(int16_t out[4][32]) {if(synth)synth->part_scopes(out);}
extern "C" uint32_t fmer_dsp_modulation(void) {return modulation[0]|(modulation[1]<<8);}
extern "C" uint32_t fmer_dsp_fx_order(void) {return fx_order;}
// Boot or stopped-DMA storage owner only; no flash access in the audio path.
extern "C" int fmer_dsp_set_fx_default(uint32_t rank,int apply) {
    if(rank>=720u)return 0;fx_default=static_cast<uint16_t>(rank);
    return !apply || fmer_dsp_transport(fmer_fx_command(6,1));
}
extern "C" uint32_t fmer_dsp_voice_limit(void) { return synth ? synth->voice_budget() : 0; }
extern "C" uint32_t fmer_dsp_stolen(void) {
    if (!synth) return 0;
    return static_cast<uint32_t>(std::min(synth->stats().stolen_voices, uint64_t{0xFFFFFFFFu}));
}
static uint32_t output_metrics[7]={1,0,0,0,0,0,0};
extern "C" void fmer_dsp_output_metrics(uint32_t out[7]) { if(out)std::copy_n(output_metrics,7,out); }
extern "C" void fmer_dsp_render(int32_t* stereo, uint32_t frames, uint32_t gain) {
    if (!synth || !stereo || frames > block_capacity || !frames) return;
    const bool preview=live_preview();
    if(controls.value[FMER_SEQ_MODE] && preview!=preview_previous){
        preview_previous=preview;
        if(!preview){for(uint8_t t=0;t<4;++t)if(track_quiet(t))release_track_midi(t);}
        else if(!controls.value[FMER_ARP_ENABLE]){
            for(const auto& owner:owners)if(owner.active && owner.held && owner.source==3 && track_quiet(owner.part) && !(track_midi_owned[owner.part][owner.pitch]&2u))
                part_midi_note(owner.part,owner.pitch,owner.velocity,2,midi_settings.value[FMER_MIDI_ROUTE]==1 || midi_settings.value[FMER_MIDI_ROUTE]==3);
        }
    }
    countin_quiet=multi->record_armed();
    rendered_to = frame; render_end = frame + frames; rendering = true; attacks_this_block = 0;
    const auto old_playing = sequencer->selected_pattern(), old_queued = sequencer->queued_pattern();
    for(uint32_t i=0;i<2;++i)if(sensing[i] && frame-sensing_frame[i]>13230u){sensing[i]=false;fmer_dsp_panic();}
    if(midi_settings.value[FMER_MIDI_CLOCK_SOURCE] && external_running && have_clock && frame-last_clock>std::max(22050u,clock_period*8u)) {
        external_running=false;increment(midi_metrics.clock_timeouts);
        if(multi->running())checked(multi->stop(frame,track_sink()));
                if(sequencer->running())checked(sequencer->stop(frame,sink()));
        if(arpeggiator->running())checked(arpeggiator->stop(frame,sink()));
    }
    if(!midi_settings.value[FMER_MIDI_CLOCK_SOURCE] && midi_settings.value[FMER_MIDI_CLOCK_SEND] && midi_clock_running)
        while(midi_next_clock<render_end){
            midi_send(0xf8);const auto n=midi_clock_remainder+44100u*60u;
            const auto den=controls.value[FMER_TEMPO]*24u;midi_next_clock+=n/den;midi_clock_remainder=n%den;
        }
    if(multi_playback() && multi->running()){
        if(arpeggiator->running() || arp_capture){
            // Merge the two bounded schedulers. At a shared recording tick the
            // recorder's hook generates the arp onset before writing that cell.
            while(true){
                const auto at=std::min(multi->next_event_frame(),arpeggiator->next_event_frame());
                if(at>=render_end)break;
                if(!multi->advance(at+1,track_sink()) || !arpeggiator->advance(at+1,sink())){increment(performance_errors);break;}
            }
            checked(arpeggiator->advance(render_end,sink()));
        }
        checked(multi->advance(render_end,track_sink()));
        mirror_recorded_patterns();
        if(parts_mode())for(uint8_t t=0;t<4;++t)tracks[t].pattern=multi->selected_pattern(t);
        uint32_t signature=multi->count_in_remaining()+8u*multi->record_armed();
        for(uint8_t t=0;t<4;++t)signature=signature*131u+multi->playing_step(t)+64u*multi->selected_pattern(t)+512u*multi->queued_pattern(t)+16384u*multi->launch_pending(t)+32768u*multi->track_stopped(t)+65536u*multi->song_row(t)+2097152u*multi->song_repeat(t)+67108864u*multi->song_live(t);
        if(signature!=multi_view_signature){multi_view_signature=signature;pattern_modified();}
    }else if (sequencer->running()) checked(sequencer->advance(render_end, sink()));
    else if (arpeggiator->running()) checked(arpeggiator->advance(render_end, sink()));
    if (old_playing != sequencer->selected_pattern() || old_queued != sequencer->queued_pattern()) pattern_modified();
    render_to(render_end); rendering = false;
    frame = render_end;
    if(controls.value[FMER_DELAY_SYNC] && frame>=synced_delay_refresh){
        synced_delay_refresh=frame+4410u;
        const auto next=effects_for(controls);const auto ms=static_cast<uint32_t>(next.delay_ms);
        if(ms!=synced_delay_ms){checked(effects->set_parameters(next));synced_delay_ms=ms;pattern_modified();}
    }else if(!controls.value[FMER_DELAY_SYNC])synced_delay_ms=0;
    const auto before=effects->meters();
    effects->process(scratch,frames);
    const auto after=effects->meters();
    const uint64_t delta[4]={after.guarded_samples-before.guarded_samples,
        after.sanitized_samples-before.sanitized_samples,after.clipped_samples-before.clipped_samples,
        after.limited_samples-before.limited_samples};
    for(unsigned i=0;i<4;++i)output_metrics[i+1]=static_cast<uint32_t>(std::min(uint64_t{0xffffffffu},uint64_t{output_metrics[i+1]}+delta[i]));
    output_metrics[5]=std::max(output_metrics[5],static_cast<uint32_t>(std::min(65535.f,after.peak_input*32767.f)));
    output_metrics[6]=std::max(output_metrics[6],static_cast<uint32_t>(after.peak_output*32767.f));
    const float scale = static_cast<float>(gain > 1024 ? 1024 : gain) * 16.0f;
    for (uint32_t i=0;i<frames;++i) {
        const float mixed=(quiet_frame[i]?0.f:scratch[i])+dry_bus[i];
        const float sample = fmer::finite_float(mixed) ? std::clamp(mixed,-.98f,.98f) : 0.f;
        output_metrics[6]=std::max(output_metrics[6],static_cast<uint32_t>(std::abs(sample)*32767.f));
        if(mixed>.98f || mixed<-.98f)increment(output_metrics[1]);
        const auto value = static_cast<int32_t>(sample * scale);
        stereo[2*i] = stereo[2*i+1] = value;
    }
}
extern "C" uint32_t fmer_dsp_active(void) { return synth ? synth->stats().active_voices : 0; }
extern "C" void fmer_dsp_fx_activity(uint16_t out[6]) {
    for(unsigned i=0;i<6;++i)out[i]=effects?static_cast<uint16_t>(std::min(1.f,effects->activity()[i])*32767.f):0;
}
extern "C" void fmer_dsp_set_midi_output(fmer_dsp_midi_output_t output) {midi_output=output;}
extern "C" int fmer_dsp_set_midi_settings(const fmer_midi_settings_t* requested) {
    if(!fmer_midi_settings_valid(requested))return 0;
    if(!std::equal(requested->value,requested->value+8,midi_settings.value)) {
        fmer_dsp_panic();midi_settings=*requested;have_clock=false;
        sequencer->external_clock(requested->value[FMER_MIDI_CLOCK_SOURCE]!=0);
        multi->external_clock(requested->value[FMER_MIDI_CLOCK_SOURCE]!=0);
        arpeggiator->external_clock(requested->value[FMER_MIDI_CLOCK_SOURCE]!=0);
    }
    return 1;
}
extern "C" void fmer_dsp_get_midi_settings(fmer_midi_settings_t* out) {if(out)*out=midi_settings;}
extern "C" void fmer_dsp_midi_metrics(fmer_midi_metrics_t* out) {
    if(out){*out=midi_metrics;out->clock_period_frames=clock_period;out->external_running=external_running;}
}
extern "C" void fmer_dsp_midi_disconnected(void) {
    // USB removal must not stop an independently powered instrument.
    for(auto& owner:owners)if(owner.active && owner.source==1)owner.active=false;
    synth->panic_source(1);sensing[0]=false;
    if(controls.value[FMER_ARP_ENABLE]) {
        for(uint32_t n=0;n<128;++n)if(!pitch_owned(static_cast<uint8_t>(n)))
            checked(arpeggiator->note_off(static_cast<uint8_t>(n)));
    }
    std::fill_n(midi_owned,128,0);
    if(midi_settings.value[FMER_MIDI_CLOCK_SOURCE]==1) {
        external_running=false;have_clock=false;
        if(multi->running())checked(multi->stop(frame,track_sink()));
                if(sequencer->running())checked(sequencer->stop(frame,sink()));
        if(arpeggiator->running())checked(arpeggiator->stop(frame,sink()));
    }
}

