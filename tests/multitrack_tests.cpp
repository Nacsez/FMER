#include "multitrack.hpp"

#include <algorithm>
#include <array>
#include <cstdlib>
#include <iostream>
#include <new>
#include <stdexcept>
#include <vector>

std::size_t multitrack_allocations{};
void* operator new(std::size_t n) {++multitrack_allocations;if(auto* p=std::malloc(n?n:1))return p;throw std::bad_alloc();}
void* operator new[](std::size_t n){return ::operator new(n);}
void operator delete(void* p) noexcept {std::free(p);}
void operator delete[](void* p) noexcept {std::free(p);}
void operator delete(void* p,std::size_t) noexcept {std::free(p);}
void operator delete[](void* p,std::size_t) noexcept {std::free(p);}

using namespace fmer;
namespace {
void check(bool okay,const char* message){if(!okay)throw std::runtime_error(message);}
struct Entry {std::uint8_t track;Event event;};
bool equal(const Entry& a,const Entry& b) {
    return a.track==b.track && a.event.frame==b.event.frame && a.event.type==b.event.type &&
        a.event.channel==b.event.channel && a.event.data1==b.event.data1 && a.event.data2==b.event.data2;
}
struct Trace {
    std::vector<Entry> events;
    std::vector<std::pair<std::uint64_t,std::uint8_t>> clicks;
    bool reject_off{},reject_on{},reject_click{};
    TrackSink sink() {
        return {this,[](void* context,std::uint8_t track,const Event& event) {
            auto& self=*static_cast<Trace*>(context);
            if((self.reject_off && event.type==EventType::NoteOff) || (self.reject_on && event.type==EventType::NoteOn))return false;
            self.events.push_back({track,event});return true;
        },[](void* context,std::uint64_t frame,std::uint8_t remaining) {
            auto& self=*static_cast<Trace*>(context);if(self.reject_click)return false;
            if(remaining)self.clicks.emplace_back(frame,remaining);return true;
        }};
    }
    std::vector<Entry> notes(std::uint8_t track,EventType type) const {
        std::vector<Entry> result;
        for(auto e:events)if(e.track==track && e.event.type==type)result.push_back(e);
        return result;
    }
    bool ordered() const {
        for(std::size_t i=1;i<events.size();++i)if(events[i].event.frame<events[i-1].event.frame)return false;
        return true;
    }
};
MonoPattern phrase(std::uint8_t base=60,std::uint8_t length=4,std::uint8_t gate=75) {
    MonoPattern p;p.length=length;
    for(std::uint8_t i=0;i<length;++i)p.steps[i]={static_cast<std::uint8_t>(base+i),100,gate};
    return p;
}
void setup(MultitrackSequencer& seq,Trace& trace) {
    for(std::uint8_t i=0;i<4;++i) {
        check(seq.set_pattern(i,phrase(48+i*8,i+1)) ,"pattern fixture accepted");
        check(seq.configure_track(i,{i,0,i,true},0,trace.sink()),"independent track settings accepted");
    }
}
void scheduling_and_chunking() {
    MultitrackSequencer a(48000),b(48000);Trace ta,tb;setup(a,ta);setup(b,tb);
    check(a.start(0,ta.sink()) && b.start(0,tb.sink()),"start emits shared transport");
    check(a.advance(48000,ta.sink()),"all four tracks advance");
    for(std::uint64_t end=127;end<48000;end+=127)check(b.advance(end,tb.sink()),"chunk advance");
    check(b.advance(48000,tb.sink()),"final chunk");
    check(ta.events.size()==tb.events.size() && std::equal(ta.events.begin(),ta.events.end(),tb.events.begin(),equal),"event streams are independent of render chunking");
    check(ta.ordered(),"all four tracks emit chronologically");
    for(std::uint8_t track=0;track<4;++track) {
        const auto ons=ta.notes(track,EventType::NoteOn),offs=ta.notes(track,EventType::NoteOff);
        check(ons.size()==8 && offs.size()==8,"each enabled mono track sounds every sixteenth");
        for(unsigned i=0;i<8;++i)check(ons[i].event.frame==i*6000 && offs[i].event.frame==i*6000+4500 &&
            ons[i].event.data1==48+track*8+i%(track+1) && ons[i].event.channel==track,"independent lengths, channels and exact gate timing");
    }
    check(a.clock_ticks()==48,"one shared24PPQN timeline, not four clocks");
}
void queues_chains_and_live_edit() {
    MultitrackSequencer seq(48000);Trace trace;setup(seq,trace);
    seq.set_pattern(4,phrase(84,2));seq.set_pattern(5,phrase(90,1));
    check(seq.configure_track(1,{1,static_cast<std::uint8_t>((1u<<1)|(1u<<5)),1,true},0,trace.sink()),"track-local chain enabled");
    seq.start(0,trace.sink());seq.advance(7001,trace.sink());
    check(seq.queue_pattern(0,4) && seq.queue_pattern(3,4),"independent boundary queues");
    auto p=*seq.pattern(2);p.steps[2].pitch=99;
    check(seq.set_pattern(2,p,true),"live edits preserve cursors");
    check(seq.playing_step(2)==1,"editing did not rewind playback");
    seq.advance(12001,trace.sink());
    check(seq.selected_pattern(0)==4 && seq.selected_pattern(3)==3 && seq.queued_pattern(3)==4,"short track switches without moving long-track queue");
    check(seq.selected_pattern(1)==5,"independent chain switches at its own boundary");
    check(trace.notes(2,EventType::NoteOn).back().event.data1==99,"live value takes effect on next visited step");
    seq.advance(24001,trace.sink());
    check(seq.selected_pattern(3)==4 && seq.queued_pattern(3)==MultitrackSequencer::pattern_count,"long track switches only after its full pattern");
    check(seq.playing_step(2)==1,"another track remains in its independent three-step phase");
    const auto before=seq.playing_step(2);check(seq.set_tempo(90,true),"live tempo accepted");
    check(seq.playing_step(2)==before,"live tempo does not reset any cursor");
    p.length=1;check(seq.set_pattern(2,p,true),"shortening playing pattern accepted");
    const auto revision=seq.pattern_revision();seq.set_pattern(2,p,true);
    check(seq.pattern_revision()==revision,"reapplying identical pattern does not create spurious dirty state");
    seq.advance(40001,trace.sink());check(seq.playing_step(2)==0,"shortening wraps safely at next visit");
    check(trace.ordered(),"queues, chains and tempo edits remain chronological");
}
void rests_ties_mute_and_channels() {
    MultitrackSequencer seq(48000);Trace trace;
    auto p=phrase();p.steps[1].pitch=MonoStep::tie;p.steps[2].pitch=MonoStep::rest;
    seq.set_pattern(0,p);seq.set_pattern(1,phrase(60,4));
    seq.configure_track(1,{1,0,0,true},0,trace.sink());seq.start(0,trace.sink());seq.advance(11001,trace.sink());
    const auto ons=trace.notes(0,EventType::NoteOn),offs=trace.notes(0,EventType::NoteOff);
    check(ons.size()==1 && offs.size()==1 && offs[0].event.frame==10500,"tie extends preceding note through its own gate");
    seq.advance(18001,trace.sink());check(trace.notes(0,EventType::NoteOn).size()==2,"rest emits no new note");
    check(seq.configure_track(1,{1,0,0,false},18500,trace.sink()),"mute disables track and releases its voice");
    const auto off=trace.notes(1,EventType::NoteOff).back();
    check(off.event.frame==18500 && off.track==1 && off.event.data1==63,"mute release retains exact track ownership despite shared channel");
    seq.advance(30001,trace.sink());check(seq.playing_step(1)==1,"muted track keeps phase");
    check(seq.configure_track(1,{1,0,7,true},31000,trace.sink()),"unmute/new channel accepted");
    seq.advance(36001,trace.sink());check(trace.notes(1,EventType::NoteOn).back().event.channel==7,"new channel applies only to subsequent notes");
    check(trace.ordered(),"rest/tie/mute operations retain ordered output");
}
void external_transport() {
    MultitrackSequencer seq(48000);Trace trace;setup(seq,trace);seq.external_clock(true);
    seq.start(0,trace.sink());seq.advance(100000,trace.sink());
    check(trace.notes(0,EventType::NoteOn).empty(),"external Start waits for first MIDI clock");
    for(unsigned tick=0;tick<12;++tick)check(seq.clock(100000+tick*1000,1000,trace.sink()),"external pulse accepted");
    seq.advance(112000,trace.sink());check(trace.notes(3,EventType::NoteOn).size()==2 && seq.playing_step(3)==1,"exactly six24PPQN pulses per sixteenth");
    seq.stop(112000,trace.sink());const auto prior=trace.notes(3,EventType::NoteOn).size();
    for(unsigned tick=0;tick<20;++tick)seq.clock(120000+tick*1000,1000,trace.sink());
    check(trace.notes(3,EventType::NoteOn).size()==prior,"clock pulses while stopped cannot trigger notes");
    seq.resume(140000,trace.sink());seq.clock(140000,1000,trace.sink());
    check(seq.playing_step(3)==2,"Continue retains next step instead of returning to first");
    seq.stop(141000,trace.sink());check(seq.song_position(11,142000,trace.sink()),"SPP accepted while stopped");
    check(seq.playing_step(1)==1 && seq.playing_step(2)==2 && seq.playing_step(3)==3,"SPP maps independently into each pattern length");
    seq.resume(143000,trace.sink());seq.clock(143000,1000,trace.sink());
    check(trace.notes(3,EventType::NoteOn).back().event.data1==75,"SPP+Continue starts requested sixteenth");
    check(trace.ordered(),"external clock and transport retain chronological output");
}
void one_take_recording() {
    MultitrackSequencer seq(48000);Trace trace;
    auto original=phrase(70,8);seq.set_pattern(0,original);seq.set_pattern(1,phrase(50,3));
    seq.configure_track(1,{1,0,1,true},0,trace.sink());
    check(seq.arm_record(0,0,trace.sink(),RecordMode::replace),"arming stopped transport starts explicit replace count-in");
    seq.record_note_on(77,90);seq.record_note_off(77);seq.advance(95999,trace.sink());
    check(!seq.recording() && seq.record_armed() && seq.count_in_remaining()==1,"four-beat lead-in precedes writing");
    check(seq.pattern(0)->steps[0].pitch==70,"count-in preserves existing pattern");
    check(trace.clicks.size()==4,"exactly four count-in clicks");
    check(trace.notes(0,EventType::NoteOn).empty() && trace.notes(1,EventType::NoteOn).empty(),
          "count-in silences every track without advancing its cursor");
    for(unsigned beat=0;beat<4;++beat)check(trace.clicks[beat].first==beat*24000 && trace.clicks[beat].second==4-beat,"count-in click spacing and display count");
    seq.record_note_on(60,110);seq.advance(96001,trace.sink());
    check(seq.recording() && !seq.record_armed() && !seq.count_in_remaining(),"recording begins after full fourth beat");
    seq.advance(108001,trace.sink());seq.record_note_off(60);seq.advance(114001,trace.sink());
    seq.record_note_on(64,84);seq.record_note_off(64);seq.advance(120001,trace.sink());seq.advance(126001,trace.sink());
    seq.record_note_on(67,120);seq.advance(138001,trace.sink());
    check(!seq.recording() && seq.running(),"one complete take ends recording while playback continues");
    const auto& steps=seq.pattern(0)->steps;
    check(steps[0].pitch==60 && steps[0].velocity==110 && steps[1].pitch==129 && steps[2].pitch==129,
          "held notes record one onset and explicit ties");
    check(steps[3].pitch==128 && steps[4].pitch==64 && steps[4].velocity==84 && steps[4].gate_percent==75 && steps[5].pitch==128,
          "silence records rests and a short between-boundary tap survives quantization");
    check(steps[6].pitch==67 && steps[7].pitch==129,"last held note is tied through end of take");
    check(seq.pattern(0)->steps[8].pitch==original.steps[8].pitch,"hidden steps survive short-pattern take");
    const auto first=trace.notes(0,EventType::NoteOn),off=trace.notes(0,EventType::NoteOff);
    check(std::count_if(first.begin(),first.end(),[](auto e){return e.event.frame>=96000 && e.event.frame<114000;})==1,
          "recorded tied notes play without boundary retrigger");
    check(std::none_of(off.begin(),off.end(),[](auto e){return e.event.frame>=96000 && e.event.frame<114000;}),"live held recording does not cut the note before its following tie is written");
    check(trace.notes(1,EventType::NoteOn).size()==8 && seq.playing_step(1)==1 &&
          trace.notes(1,EventType::NoteOn).front().event.frame==96000 &&
          trace.notes(1,EventType::NoteOn).front().event.data1==50,
          "other track restarts at its first note on the recording downbeat");
    const auto revision=seq.pattern_revision();seq.advance(192001,trace.sink());
    check(seq.pattern_revision()==revision && seq.pattern(0)->steps[0].pitch==60,"next playback loop cannot overwrite completed take");
}
void recording_alignment_cancel_and_external() {
    MultitrackSequencer seq(48000);Trace trace;seq.set_pattern(0,phrase(60,4));
    seq.start(0,trace.sink());seq.advance(7001,trace.sink());seq.arm_record(0,7001,trace.sink());seq.advance(24001,trace.sink());
    check(trace.clicks.size()==1 && trace.clicks[0].first==24000,"arming during playback aligns first click to next quarter");
    const auto rev=seq.pattern_revision();seq.stop_record();seq.advance(200000,trace.sink());
    check(seq.pattern_revision()==rev && !seq.record_armed(),"cancelled lead-in does not erase notes");
    MultitrackSequencer ext(48000);Trace tx;ext.external_clock(true);ext.set_pattern(0,phrase(70,1));
    ext.arm_record(0,0,tx.sink(),RecordMode::replace);ext.advance(100000,tx.sink());
    check(tx.clicks.empty() && ext.record_armed(),"external count-in never free runs while awaiting clock");
    for(unsigned tick=0;tick<=96;++tick)ext.clock(100000+tick*1000,1000,tx.sink());
    check(tx.clicks.size()==4 && !ext.recording() && ext.pattern(0)->steps[0].pitch==128,"external24PPQN clock drives four clicks then one-step rest take");
}
void validation_rejection_and_bounded_state() {
    MultitrackSequencer seq(48000);Trace trace;
    check(sizeof(seq)<3900 && sizeof(MonoPattern)==193,"compact sixteen-pattern pool and bounded scheduler state");
    auto p=phrase();p.steps[63].pitch=130;
    check(!seq.set_pattern(0,p) && !seq.set_pattern(16,phrase()) && seq.pattern(16)==nullptr,"invalid and hidden pattern data rejected");
    check(!seq.configure_track(4,{0,0,0,true},0,trace.sink()) && !seq.configure_track(0,{0,0,16,true},0,trace.sink()),"invalid track/channel rejected");
    check(!seq.set_tempo(19) && !seq.set_tempo(301),"tempo bounds enforced");
    check(!seq.queue_pattern(0,1),"stopped queue rejected");
    seq.set_pattern(0,phrase());seq.start(0,trace.sink());seq.advance(1,trace.sink());
    check(!seq.set_pattern(0,phrase()) && !seq.set_tempo(100),"nonlive edits refuse running state");
    trace.reject_off=true;
    check(!seq.stop(100,trace.sink()) && !seq.running(),"rejected release stops transport and retains note obligation");
    trace.reject_off=false;check(seq.advance(101,trace.sink()),"retained release can retry while stopped");
    check(trace.notes(0,EventType::NoteOff).size()==1,"retry emits exactly retained ownership once");
    check(!seq.advance(99,trace.sink()) && seq.last_error()==PerformanceError::TimeOrder,"backward time rejected");
    seq.start(101,trace.sink());trace.reject_on=true;
    check(!seq.advance(102,trace.sink()) && !seq.running(),"note rejection halts bounded scheduler instead of claiming playback");
    trace.reject_on=false;seq.start(102,trace.sink());seq.stop(103,trace.sink());trace.reject_click=true;seq.arm_record(0,104,trace.sink());
    check(!seq.advance(105,trace.sink()) && !seq.record_armed(),"failed count-in callback cancels take");
    std::size_t emitted=0;
    TrackSink sink{&emitted,[](void* count,std::uint8_t,const Event&){++*static_cast<std::size_t*>(count);return true;},nullptr};
    MultitrackSequencer fixed(48000);p=phrase(48,64);const auto allocations=multitrack_allocations;
    for(std::uint8_t track=0;track<4;++track){fixed.set_pattern(track,p);fixed.configure_track(track,{track,0,track,true},0,sink);}
    fixed.arm_record(0,0,sink);fixed.record_note_on(60,100);fixed.advance(600000,sink);fixed.stop(600000,sink);
    check(multitrack_allocations==allocations && emitted>500,"configuration, four-track playback, recording and stop allocate nothing");
}
void overdub_preserves_and_layers() {
    MultitrackSequencer seq(48000);Trace trace;
    auto original=phrase(48,8);original.steps[5].pitch=MonoStep::tie;original.steps[6].pitch=MonoStep::tie;
    seq.set_pattern(0,original);seq.arm_record(0,0,trace.sink());
    check(!seq.count_in_remaining() && !seq.count_in_pulse(0),"armed wait has no premature visual click");
    seq.advance(1,trace.sink());
    check(seq.count_in_remaining()==4 && seq.count_in_pulse(0) && seq.count_in_pulse(5999) && !seq.count_in_pulse(6000),
          "first displayed countdown/pulse uses exactly the emitted audio beat");
    seq.advance(108001,trace.sink()); // steps0,1,2 untouched
    check(seq.pattern(0)->steps[0].pitch==48 && seq.pattern(0)->steps[2].pitch==50,"overdub silence preserves prior onsets");
    seq.record_note_on(72,90);seq.advance(114001,trace.sink()); // onset3
    seq.advance(120001,trace.sink()); // tie4
    seq.record_note_off(72);seq.advance(126001,trace.sink()); // cuts inherited tie5
    seq.advance(138001,trace.sink());
    check(seq.recording() && seq.pattern(0)->steps[3].pitch==72 && seq.pattern(0)->steps[4].pitch==MonoStep::tie &&
          seq.pattern(0)->steps[5].pitch==MonoStep::rest && seq.pattern(0)->steps[6].pitch==MonoStep::tie && seq.pattern(0)->steps[7].pitch==55,
          "performed mono span replaces only its cells, cuts old held tail and keeps later unrelated notes");
    seq.advance(144001,trace.sink());seq.record_note_on(65,99);seq.record_note_off(65);seq.advance(150001,trace.sink());
    seq.stop_record();
    check(!seq.recording() && seq.pattern(0)->steps[0].pitch==48 && seq.pattern(0)->steps[1].pitch==65 &&
          seq.pattern(0)->steps[3].pitch==72 && seq.pattern(0)->steps[1].velocity==99,
          "a later overdub loop adds another tap without replacing the preceding take");
    const auto revision=seq.pattern_revision();seq.advance(250000,trace.sink());
    check(seq.pattern_revision()==revision,"stopping overdub resumes ordinary playback with no further writes");
    check(seq.record_pattern()==0,"recorded-pattern identity survives stop for bounded mirroring");
}
void sixteen_patterns_and_countdown_clock() {
    MultitrackSequencer seq(48000);Trace trace;
    seq.set_pattern(8,phrase(80,1));seq.set_pattern(15,phrase(95,1));
    seq.configure_track(0,{8,static_cast<std::uint16_t>((1u<<8)|(1u<<15)),0,true},0,trace.sink());
    seq.start(0,trace.sink());seq.advance(6001,trace.sink());
    check(seq.selected_pattern(0)==15 && seq.chain_mask(0)==0x8100 && trace.notes(0,EventType::NoteOn).back().event.data1==95,
          "upper-half chain mask and final pattern retain all sixteen bits");
    seq.queue_pattern(0,14);seq.advance(12001,trace.sink());
    check(seq.selected_pattern(0)==14,"upper-half queued patterns use normal independent boundaries");
    MultitrackSequencer ext(48000);Trace tx;ext.external_clock(true);ext.arm_record(0,0,tx.sink());
    check(!ext.count_in_remaining() && !ext.count_in_pulse(100000),"external armed state has no fake countdown before master clock");
    for(unsigned tick=0;tick<=96;++tick) {
        const auto frame=100000+tick*700;ext.clock(frame,700,tx.sink());
        if(tick<96)check(ext.count_in_remaining()==4-tick/24 && ext.count_in_pulse(frame)==(tick%24<6),
                        "external click pulse and displayed number share actual24PPQN beat phase");
    }
    check(ext.recording() && !ext.count_in_remaining() && !ext.count_in_pulse(167200),"first recording step ends lead-in visuals");
    check(tx.clicks.size()==4 && tx.clicks[3].first==150400,"external lead-in clicks use received clock timestamps");
}
void overdub_held_priority_and_wrap() {
    MultitrackSequencer seq(48000);Trace trace;MonoPattern p;p.length=4;
    seq.set_pattern(0,p);seq.arm_record(0,0,trace.sink());seq.record_note_on(60,90);seq.advance(96001,trace.sink());
    seq.record_note_on(67,100);seq.advance(102001,trace.sink());seq.record_note_off(67);seq.advance(108001,trace.sink());
    check(seq.pattern(0)->steps[0].pitch==60 && seq.pattern(0)->steps[1].pitch==67 && seq.pattern(0)->steps[2].pitch==60 &&
          seq.pattern(0)->steps[2].velocity==90,"recording follows mono return to still-held earlier key and its velocity");
    seq.advance(162001,trace.sink());
    check(seq.recording() && seq.pattern(0)->steps[0].pitch==60 && seq.pattern(0)->steps[1].pitch==MonoStep::tie &&
          seq.pattern(0)->steps[2].pitch==MonoStep::tie && seq.pattern(0)->steps[3].pitch==MonoStep::tie,
          "holding across repeated overdub loops retains a self-contained first onset");
    seq.record_note_off(60);seq.advance(168001,trace.sink());seq.stop_record();
    check(seq.pattern(0)->steps[0].pitch==60,"release on next loop preserves existing independent first onset");
    MultitrackSequencer tap(48000);Trace tx;tap.set_pattern(0,p);tap.arm_record(0,0,tx.sink());tap.advance(96001,tx.sink());
    tap.record_note_on(64,91);tap.record_note_off(64);tap.advance(102001,tx.sink());tap.advance(120001,tx.sink());
    check(tap.pattern(0)->steps[0].pitch==MonoStep::rest && tap.pattern(0)->steps[1].pitch==64 &&
          tap.pattern(0)->steps[2].pitch==MonoStep::rest,"blank-pattern overdub captures rests and between-boundary short taps");
    MultitrackSequencer tied(48000);Trace tt;p=phrase(48,4);p.steps[2].pitch=MonoStep::tie;
    tied.set_pattern(0,p);tied.arm_record(0,0,tt.sink());tied.advance(96001,tt.sink());
    tied.record_note_on(70,110);tied.record_note_off(70);tied.advance(107000,tt.sink());
    const auto releases=tt.notes(0,EventType::NoteOff);
    check(std::any_of(releases.begin(),releases.end(),[](const Entry& e){return e.event.data1==70 && e.event.frame==106500;}),
          "short overdub tap retains its75percent gate instead of inheriting old phrase tie duration");
}
void bar_launch_and_stop() {
    MultitrackSequencer seq(48000);Trace trace;
    seq.set_pattern(0,phrase(48,64));seq.set_pattern(1,phrase(72,32));
    seq.configure_track(1,{1,0,1,true},0,trace.sink());seq.start(0,trace.sink());seq.advance(30001,trace.sink());
    check(seq.queue_pattern(0,1) && seq.launch_at_bar(0),"independent bar launch accepts a queued pattern");
    seq.advance(95999,trace.sink());check(seq.selected_pattern(0)==0,"launch waits for bar, not just next step");
    seq.advance(96001,trace.sink());check(seq.selected_pattern(0)==1 && seq.playing_step(0)==0 && seq.playing_step(1)==16,"selected launch preserves the other cursor");
    check(seq.stop_track(0,96001,trace.sink()),"individual stop releases ownership");auto n=trace.notes(0,EventType::NoteOn).size();
    seq.advance(150001,trace.sink());check(trace.notes(0,EventType::NoteOn).size()==n && seq.track_stopped(0),"stopped track emits no further notes");
    check(seq.launch_at_bar(4),"all-track launch queued");seq.advance(192001,trace.sink());
    check(!seq.track_stopped(0) && seq.playing_step(0)==0 && seq.playing_step(1)==0 && seq.clock_ticks()==193,"all launch restarts cursors without resetting master clock");
    check(trace.ordered(),"launch and stop event timestamps remain chronological");
    seq.stop(192001,trace.sink());check(!seq.launch_at_bar(4),"stopped master refuses a hidden launch");
}

void song_arrangement() {
    MultitrackSequencer q(48000);Trace tr;setup(q,tr);
    fmer_song_t song{};song.length[0]=2;song.enabled[0]=1;
    song.rows[0][0]={0,5,1};song.rows[0][1]={1,-12,0}; // P0 length1 twice, P1 length2 once.
    song.length[1]=1;song.enabled[1]=1;song.loop[1]=1;song.rows[1][0]={2,7,0};
    check(q.set_song(song),"valid song accepted while stopped");
    check(q.start(0,tr.sink()) && q.advance(30001,tr.sink()),"song advances independent lanes");
    auto n=tr.notes(0,EventType::NoteOn);check(n.size()==4,"repeats and end stop produce exact note count");
    check(n[0].event.data1==53 && n[1].event.data1==53 && n[2].event.data1==44 && n[3].event.data1==45,"transpose applies per entry without changing stored notes");
    check(n[0].event.frame==0 && n[1].event.frame==6000 && n[2].event.frame==12000 && n[3].event.frame==18000,"song boundaries use shared exact step clock");
    check(q.track_stopped(0) && !q.track_stopped(1) && q.pattern(0)->steps[0].pitch==48,"end stop independent; source patterns immutable");
    auto off=tr.notes(0,EventType::NoteOff);check(off.size()==4 && off[2].event.data1==44,"offs own transposed pitches");
    check(q.queue_pattern(1,3) && !q.song_live(1),"manual pattern launch preserves song until boundary");
    q.advance(36001,tr.sink());check(q.song_live(1),"queued pattern enters Live at the pattern boundary");
    check(q.launch_at_bar(0) && q.advance(96001,tr.sink()) && !q.track_stopped(0) && q.song_row(0)==0,"bar retrigger restarts enabled song lane");
    check(q.stop(96001,tr.sink()) && q.song_position(2,96002,tr.sink()),"SPP seeks stopped arrangement");
    check(q.song_row(0)==1 && q.selected_pattern(0)==1 && q.playing_step(0)==0,"SPP accounts for repeats and unequal lengths");
    check(q.resume(96002,tr.sink()) && q.advance(96003,tr.sink()),"Continue resumes sought entry");
    check(tr.notes(0,EventType::NoteOn).back().event.data1==44,"Continue retains entry transposition");
    q.stop(96003,tr.sink());song.rows[0][0]={16,0,0};song.length[0]=1;song.loop[0]=0;
    check(q.set_song(song) && q.start(100000,tr.sink()),"explicit16-step rest accepted");auto before=tr.notes(0,EventType::NoteOn).size();
    q.advance(196001,tr.sink());check(tr.notes(0,EventType::NoteOn).size()==before && q.track_stopped(0),"rest consumes clock without notes");
    q.stop(196001,tr.sink());song.rows[0][0]={0,-24,31};song.length[0]=32;check(q.set_song(song),"full capacity accepted");
    check(!q.edit_song(0,0,6,1),"full lane refuses insertion without overwrite");
    check(q.edit_song(0,0,5,1) && q.song().length[0]==31,"delete compacts only one lane");
    song.rows[0][0].transpose=25;check(!q.set_song(song),"invalid transpose refuses atomic replacement");
}

}
int main() {
    try {
        song_arrangement();bar_launch_and_stop();scheduling_and_chunking();queues_chains_and_live_edit();rests_ties_mute_and_channels();external_transport();
        one_take_recording();recording_alignment_cancel_and_external();validation_rejection_and_bounded_state();
        overdub_preserves_and_layers();sixteen_patterns_and_countdown_clock();overdub_held_priority_and_wrap();
        std::cout<<"multitrack: four tracks, shared sixteen-pattern pool, ownership, queues/chains, live edits, external transport, aligned count-in, rests/ties, looping overdub/one-pass replace, bounded state and zero allocations passed; scheduler_bytes="<<sizeof(MultitrackSequencer)<<"; pattern_bytes="<<sizeof(MonoPattern)<<"\n";
        return EXIT_SUCCESS;
    }catch(const std::exception& e){std::cerr<<"multitrack failure: "<<e.what()<<'\n';return EXIT_FAILURE;}
}
