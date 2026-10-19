#include "../core/performance.hpp"

#include <algorithm>
#include <array>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

using namespace fmer;
namespace {
void check(bool okay, const char* message) {
    if (!okay) throw std::runtime_error(message);
}
struct Trace {
    std::vector<Event> events;
    bool reject_release = false;
    EventSink sink() {
        return {this, [](void* self, const Event& value) {
            auto& trace = *static_cast<Trace*>(self);
            if (trace.reject_release && value.type == EventType::NoteOff) return false;
            trace.events.push_back(value);
            return true;
        }};
    }
    std::vector<Event> only(EventType type) const {
        std::vector<Event> result;
        for (auto value : events) if (value.type == type) result.push_back(value);
        return result;
    }
};
Pattern one_note(std::uint8_t pitch = 60) {
    Pattern result;
    result.length = 1;
    result.steps[0].note_count = 1;
    result.steps[0].notes[0] = {pitch, 100};
    return result;
}
bool equal(Event a, Event b) {
    return a.frame == b.frame && a.type == b.type && a.channel == b.channel &&
           a.data1 == b.data1 && a.data2 == b.data2 && a.source == b.source;
}
struct Ownership {
    std::array<std::array<bool, 128>, 3> notes{};
    void apply(Event value) {
        if (value.type == EventType::AllNotesOff || value.type == EventType::Reset) {
            for (auto& source : notes) source.fill(false);
        } else if (value.type == EventType::NoteOn || value.type == EventType::NoteOff) {
            notes[static_cast<std::size_t>(value.source)][value.data1] = value.type == EventType::NoteOn;
        }
    }
    bool any() const {
        for (const auto& source : notes) for (bool note : source) if (note) return true;
        return false;
    }
};

void midi_streaming() {
    MidiParser parser;
    Trace trace;
    const std::array<std::uint8_t, 23> bytes{
        0x92, 60, 0xf8, 100, 64, 0, 0xc2, 7, 8, 0xb2, 64, 127,
        0xe2, 0, 64, 0xf2, 1, 2, 60, 0x92, 65, 0x80, 65};
    for (std::size_t i = 0; i < bytes.size(); ++i) check(parser.feed(bytes[i], i, trace.sink()), "MIDI feed");
    check(parser.feed(0, 23, trace.sink()), "truncated message recovers");
    check(trace.events.size() == 9, "running status and realtime event count");
    check(trace.events[0].type == EventType::Clock && trace.events[0].frame == 2, "interleaved clock timestamp");
    check(trace.events[1].type == EventType::NoteOn && trace.events[1].channel == 2 &&
          trace.events[1].data1 == 60 && trace.events[1].frame == 3, "completed note timestamp");
    check(trace.events[2].type == EventType::NoteOff && trace.events[2].data1 == 64, "zero velocity converts to off");
    check(trace.events[3].type == EventType::ProgramChange && trace.events[4].data1 == 8, "one-byte running status");
    check(trace.events[5].type == EventType::ControlChange && trace.events[5].data2 == 127, "CC data");
    check(trace.events[6].type == EventType::PitchBend && trace.events[6].data2 == 64, "14-bit pitch bytes");
    check(trace.events[7].type == EventType::SongPosition && trace.events[7].data1 == 1, "song position framing");
    check(parser.stats().stray_data == 1 && parser.stats().malformed == 1, "system common clears running status; interrupted message counted");
}
void midi_sysex_bounds() {
    MidiParser parser;
    Trace trace;
    for (auto byte : {0xf0, 0x43, 0xfa, 1, 0xf7}) check(parser.feed(static_cast<std::uint8_t>(byte), 0, trace.sink()), "SysEx feed");
    check(trace.events.size() == 2 && trace.events[0].type == EventType::Start &&
          trace.events[1].type == EventType::SysExComplete, "realtime inside SysEx");
    check(parser.sysex_size() == 4 && parser.sysex_data()[2] == 1, "realtime excluded from SysEx bytes");
    check(parser.feed(0xf0, 1, trace.sink()), "large SysEx start");
    for (std::size_t i = 0; i < MidiParser::sysex_capacity; ++i) check(parser.feed(0, 1, trace.sink()), "large SysEx body");
    check(parser.feed(0xf7, 1, trace.sink()), "large SysEx end");
    check(parser.stats().sysex_overflow == 1 && parser.stats().sysex_completed == 1 && parser.sysex_size() == 0,
          "oversized SysEx rejected atomically");
    for (auto byte : {0x90, 60, 100}) check(parser.feed(static_cast<std::uint8_t>(byte), 2, trace.sink()), "post-SysEx recovery");
    check(trace.events.back().type == EventType::NoteOn, "parser recovers after overflow");
}
void sequence_chord_rest_tie() {
    Sequencer sequence;
    Pattern pattern;
    pattern.length = 4;
    pattern.steps[0].note_count = 2;
    pattern.steps[0].notes[0] = {60, 100};
    pattern.steps[0].notes[1] = {64, 90};
    pattern.steps[0].gate_percent = 25;
    pattern.steps[1].tie = true;
    pattern.steps[1].gate_percent = 50;
    pattern.steps[3].note_count = 1;
    pattern.steps[3].notes[0] = {67, 110};
    pattern.steps[3].gate_percent = 100;
    Trace trace;
    check(sequence.set_pattern(0, pattern) && sequence.start(0, trace.sink()) &&
          sequence.advance(22050, trace.sink()) && sequence.stop(22050, trace.sink()), "sequence playback");
    const auto ons = trace.only(EventType::NoteOn), offs = trace.only(EventType::NoteOff);
    check(ons.size() == 3 && offs.size() == 3, "tie does not retrigger chord; rest emits no attack");
    check(ons[0].frame == 0 && ons[1].frame == 0 && ons[2].frame == 16537, "exact chord/rest onset frames");
    check(offs[0].frame == 8268 && offs[1].frame == 8268 && offs[2].frame == 22050,
          "tie overrides prior short gate; final 100 percent gate closes on Stop");
}
void rational_clock_long_run() {
    Sequencer sequence;
    Trace trace;
    check(sequence.set_tempo(137) && sequence.start(0, trace.sink()) &&
          sequence.advance(44100ULL * 600, trace.sink()), "ten-minute clock schedule");
    auto clocks = trace.only(EventType::Clock);
    check(clocks.size() == 137 * 24 * 10, "24 MIDI clocks per quarter");
    for (std::size_t i = 0; i < clocks.size(); ++i) {
        check(clocks[i].frame == i * 44100ULL * 60 / (137 * 24), "clock has no cumulative rounding drift");
    }
}
void chunk_independence() {
    Sequencer whole, chunks;
    Trace a, b;
    check(whole.set_pattern(0, one_note()) && chunks.set_pattern(0, one_note()), "chunk fixture");
    check(whole.set_tempo(137) && chunks.set_tempo(137), "chunk tempo");
    check(whole.start(0, a.sink()) && chunks.start(0, b.sink()), "chunk start");
    constexpr std::uint64_t end = 441000;
    check(whole.advance(end, a.sink()), "whole schedule");
    for (std::uint64_t frame = 113; frame < end; frame += 113) check(chunks.advance(frame, b.sink()), "chunk schedule");
    check(chunks.advance(end, b.sink()), "final chunk");
    check(a.events.size() == b.events.size(), "chunk event count");
    for (std::size_t i = 0; i < a.events.size(); ++i) check(equal(a.events[i], b.events[i]), "block boundaries cannot alter event timing/order");
}
void transport_continue() {
    Sequencer sequence;
    Trace trace;
    check(sequence.set_pattern(0, one_note()) && sequence.start(0, trace.sink()) &&
          sequence.stop(1000, trace.sink()) && sequence.resume(5000, trace.sink()) &&
          sequence.advance(10000, trace.sink()) && sequence.stop(10000, trace.sink()), "stop/continue flow");
    auto ons = trace.only(EventType::NoteOn), offs = trace.only(EventType::NoteOff);
    check(ons.size() == 2 && ons[0].frame == 0 && ons[1].frame == 9512, "Continue preserves paused fractional clock position");
    check(offs[0].frame == 1000 && offs[1].frame == 10000, "Stop releases all owned notes");
    check(!sequence.advance(9999, trace.sink()) && sequence.last_error() == PerformanceError::TimeOrder, "backward time rejected");
}
void validation_and_pattern_switch() {
    Sequencer sequence;
    auto original = one_note();
    check(sequence.set_pattern(0, original), "valid pattern");
    auto invalid = original;
    invalid.steps[0].note_count = 10;
    check(!sequence.set_pattern(0, invalid) && sequence.pattern(0)->steps[0].note_count == 1, "bad capacity leaves prior pattern unchanged");
    invalid = original;
    invalid.steps[0].tie = true;
    check(!sequence.set_pattern(0, invalid), "tie and notes are mutually exclusive");
    check(!sequence.set_pattern(Sequencer::pattern_count, original) && sequence.pattern(Sequencer::pattern_count) == nullptr, "pattern bounds");
    check(!sequence.set_tempo(0), "zero tempo refused");
    Trace trace;
    check(sequence.set_pattern(Sequencer::pattern_count-1, one_note(72)) && sequence.start(0, trace.sink()) && sequence.advance(1, trace.sink()), "first pattern");
    check(!sequence.set_pattern(0, one_note(55)), "active pattern edits require explicit boundary");
    check(sequence.select_pattern(Sequencer::pattern_count-1, 100, trace.sink()) && sequence.advance(101, trace.sink()), "pattern switch");
    auto ons = trace.only(EventType::NoteOn), offs = trace.only(EventType::NoteOff);
    check(ons.size() == 2 && ons[1].data1 == 72 && ons[1].frame == 100 && offs[0].data1 == 60 && offs[0].frame == 100,
          "switch releases prior pattern before new attack");
}
void overlap_ownership() {
    Sequencer sequence;
    Trace trace;
    trace.events.push_back({0, EventType::NoteOn, 0, 60, 100, EventSource::Midi});
    check(sequence.set_pattern(0, one_note()) && sequence.start(0, trace.sink()) && sequence.stop(100, trace.sink()), "overlap sequence");
    Ownership ownership;
    for (auto value : trace.events) ownership.apply(value);
    check(ownership.notes[0][60] && !ownership.notes[1][60], "sequencer Stop does not release a live MIDI owner of same pitch");
    ownership.apply({100, EventType::NoteOff, 0, 60, 0, EventSource::Midi});
    check(!ownership.any(), "each owner releases its own note");
}
void rejected_release_retry() {
    Sequencer sequence;
    Trace trace;
    check(sequence.set_pattern(0, one_note()) && sequence.start(0, trace.sink()) && sequence.advance(1, trace.sink()), "release retry fixture");
    trace.reject_release = true;
    check(!sequence.stop(100, trace.sink()) && sequence.last_error() == PerformanceError::OutputRejected, "failed release reported");
    trace.reject_release = false;
    check(sequence.stop(200, trace.sink()), "retained ownership can be retried");
    auto offs = trace.only(EventType::NoteOff);
    check(offs.size() == 1 && offs[0].frame == 200 && offs[0].data1 == 60, "rejected note-off is not silently forgotten");
}
void queue_overflow_safety() {
    EventQueue queue;
    for (std::size_t i = 0; i < EventQueue::capacity - EventQueue::release_reserve; ++i)
        check(queue.push({0, EventType::NoteOn, 0, 60, 100, EventSource::Midi}), "normal queue fill");
    check(!queue.push({0, EventType::NoteOn, 0, 61, 100, EventSource::Midi}), "normal capacity refused");
    check(queue.push({1, EventType::ControlChange, 0, 64, 0, EventSource::Midi}), "sustain release has reserve");
    for (std::size_t i = 1; i < EventQueue::release_reserve; ++i)
        check(queue.push({1, EventType::NoteOff, 0, 60, 0, EventSource::Midi}), "release reserve accepted");
    check(!queue.push({2, EventType::NoteOff, 0, 60, 0, EventSource::Midi}), "exhausted reserve escalates visibly");
    check(queue.panic_count() == 1 && queue.size() == 1 && queue.overflow_count() == 2, "panic replaces unsafe pending queue");
    check(!queue.push({2, EventType::NoteOn, 0, 61, 100, EventSource::Midi}), "no new attacks until panic consumed");
    Ownership ownership;
    ownership.apply({0, EventType::NoteOn, 0, 60, 100, EventSource::Midi});
    Event value;
    check(queue.pop(value) && value.type == EventType::AllNotesOff && value.channel == 255 && value.source == EventSource::System,
          "explicit global panic contract");
    ownership.apply(value);
    check(!ownership.any() && !queue.pop(value), "overflow cannot leave a held owner after panic consumed");
}
void dense_schedule_overflow() {
    Sequencer sequence;
    EventQueue queue;
    Pattern pattern = one_note();
    pattern.steps[0].note_count = 9;
    for (std::uint8_t i = 0; i < 9; ++i) pattern.steps[0].notes[i] = {static_cast<std::uint8_t>(60 + i), 100};
    check(sequence.set_pattern(0, pattern) && sequence.start(0, queue.sink()), "dense schedule fixture");
    check(!sequence.advance(44100 * 10, queue.sink()) && !sequence.running() && queue.overflow_count() > 0, "dense overflow stops producer and reports failure");
    Ownership ownership;
    Event value;
    while (queue.pop(value)) ownership.apply(value);
    check(!ownership.any(), "reserved releases terminate all accepted dense attacks");
}
std::vector<std::uint8_t> arp_notes(ArpOrder order, std::uint8_t octaves = 1) {
    Arpeggiator arp;
    Trace trace;
    ArpSettings settings;
    settings.order = order;
    settings.octaves = octaves;
    check(arp.configure(settings, 0, trace.sink()), "arp configure");
    for (auto pitch : {67, 60, 64}) check(arp.note_on(static_cast<std::uint8_t>(pitch), 100), "arp held note");
    check(arp.start(0, trace.sink()) && arp.advance(44100, trace.sink()) && arp.stop(44100, trace.sink()), "arp playback");
    std::vector<std::uint8_t> result;
    for (auto value : trace.only(EventType::NoteOn)) result.push_back(value.data1);
    Ownership ownership;
    for (auto value : trace.events) ownership.apply(value);
    check(!ownership.any(), "arp stop leaves no generated owner");
    return result;
}
void arp_orders() {
    check(arp_notes(ArpOrder::Up) == std::vector<std::uint8_t>({60, 64, 67, 60, 64, 67, 60, 64}), "arp up order");
    check(arp_notes(ArpOrder::Down) == std::vector<std::uint8_t>({67, 64, 60, 67, 64, 60, 67, 64}), "arp down order");
    check(arp_notes(ArpOrder::UpDown) == std::vector<std::uint8_t>({60, 64, 67, 64, 60, 64, 67, 64}), "arp up/down without repeated endpoints");
    check(arp_notes(ArpOrder::Played) == std::vector<std::uint8_t>({67, 60, 64, 67, 60, 64, 67, 60}), "arp played order");
    check(arp_notes(ArpOrder::Up, 2) == std::vector<std::uint8_t>({60, 64, 67, 72, 76, 79, 60, 64}), "arp octave expansion");
}
void arp_latch_and_capacity() {
    Arpeggiator arp;
    Trace trace;
    ArpSettings settings;
    settings.latch = true;
    check(arp.configure(settings, 0, trace.sink()) && arp.note_on(60, 100) && arp.note_on(64, 100) &&
          arp.note_off(60) && arp.note_off(64), "latch chord");
    check(arp.held_count() == 2 && arp.start(0, trace.sink()) && arp.advance(6000, trace.sink()), "latched chord continues after physical release");
    check(arp.note_on(67, 100) && arp.held_count() == 1 && arp.note_off(67), "new chord replaces fully released latch");
    settings.latch = false;
    check(arp.configure(settings, 6000, trace.sink()) && arp.held_count() == 0, "disabling latch clears released held notes and active output");
    check(arp.stop(6000, trace.sink()), "latch stop");
    for (std::uint8_t i = 0; i < Arpeggiator::held_capacity; ++i) check(arp.note_on(i, 100), "held capacity fill");
    check(!arp.note_on(100, 100) && arp.last_error() == PerformanceError::HeldNoteCapacity &&
          arp.held_count() == Arpeggiator::held_capacity, "held capacity refusal preserves prior set");
    check(arp.note_off(0) && arp.note_on(100, 100), "released held capacity reused");
}
void arp_clips_octaves_and_releases() {
    Arpeggiator arp;
    Trace trace;
    ArpSettings settings;
    settings.octaves = 4;
    check(arp.configure(settings, 0, trace.sink()) && arp.note_on(127, 100) &&
          arp.start(0, trace.sink()) && arp.advance(12000, trace.sink()), "top-octave fixture");
    auto ons = trace.only(EventType::NoteOn);
    check(ons.size() == 3, "top note still cycles");
    for (auto value : ons) check(value.data1 == 127, "octave expansion omits out-of-range notes without wraparound");
    check(arp.clear(12000, trace.sink()) && arp.held_count() == 0 && arp.advance(22050, trace.sink()), "clear releases active and cancels held set");
    check(trace.only(EventType::NoteOn).size() == 3, "cleared arp produces no further attack");
}
void arp_extended_orders_and_seed() {
    auto play = [](ArpOrder order, std::uint32_t seed) {
        Trace trace; Arpeggiator arp; ArpSettings settings;
        settings.order = order; settings.seed = seed;
        check(arp.configure(settings, 0, trace.sink()), "extended arp configure");
        for (std::uint8_t pitch : {60, 64, 67}) check(arp.note_on(pitch, 100), "held notes");
        check(arp.start(0, trace.sink()) && arp.advance(44100, trace.sink()) &&
              arp.stop(44100, trace.sink()), "extended arp run");
        return trace;
    };
    const auto inclusive = play(ArpOrder::Inclusive, 1).only(EventType::NoteOn);
    const std::array<int,8> expected{60,64,67,67,64,60,60,64};
    check(inclusive.size() == expected.size(), "inclusive attacks");
    for (std::size_t i=0; i<expected.size(); ++i) check(inclusive[i].data1 == expected[i], "inclusive endpoints repeat");
    const auto random_a = play(ArpOrder::Random, 42).only(EventType::NoteOn);
    const auto random_b = play(ArpOrder::Random, 42).only(EventType::NoteOn);
    const auto random_c = play(ArpOrder::Random, 43).only(EventType::NoteOn);
    bool changed = false;
    for (std::size_t i=0; i<random_a.size(); ++i) {
        check(equal(random_a[i],random_b[i]), "same seed reproduces random order");
        changed = changed || random_a[i].data1 != random_c[i].data1;
    }
    check(changed, "different seed changes order");
    const auto chord = play(ArpOrder::Repeat, 1);
    check(chord.only(EventType::NoteOn).size() == 24 && chord.only(EventType::NoteOff).size() == 24,
          "Repeat emits and releases every chord owner");
    Ownership owners; for(auto event:chord.events) owners.apply(event);
    check(!owners.any(), "Repeat stops cleanly");
}
void arp_rate_swing_triplet_and_release_retry() {
    Trace trace; Arpeggiator arp; ArpSettings settings;
    settings.rate=8; settings.swing=75; settings.triplet=true; settings.order=ArpOrder::Repeat;
    check(arp.configure(settings,0,trace.sink()) && arp.note_on(60,100) && arp.note_on(64,100), "rate fixture");
    check(arp.start(0,trace.sink()) && arp.advance(27000,trace.sink()), "triplet swing advance");
    const auto ons=trace.only(EventType::NoteOn);
    check(ons.size()==8, "four triplet eighth chords in two thirds second");
    check(ons[0].frame==0 && ons[2].frame==11025 && ons[4].frame==14700 && ons[6].frame==25725,
          "75 percent paired swing has exact boundaries and no drift");
    trace.reject_release=true;
    check(!arp.stop(27000,trace.sink()), "release refusal surfaced");
    trace.reject_release=false;
    check(arp.stop(27000,trace.sink()), "retained chord releases retry");
    Ownership owners; for(auto event:trace.events) owners.apply(event);
    check(!owners.any(), "retry cannot strand any chord pitch");
    settings.rate=3; check(!arp.configure(settings,29400,trace.sink()), "unsupported rate refused");
    settings.rate=16; settings.seed=0; check(!arp.configure(settings,29400,trace.sink()), "zero seed refused");
}
void inactive_steps_are_validated() {
    Sequencer seq; Pattern invalid=one_note(); invalid.steps[63].note_count=10;
    check(!seq.set_pattern(0,invalid), "hidden invalid step must not enter project");
    check(seq.pattern(0)->length==16, "refusal preserves saved pattern");
}
void pattern_boundary_queue_and_chain() {
    Sequencer sequence;Trace trace;
    auto first=one_note(60);first.length=2;first.steps[1]=first.steps[0];first.steps[1].notes[0].pitch=61;
    auto second=one_note(64);second.channel=3;
    auto last=one_note(67);last.channel=5;
    check(sequence.set_pattern(0,first)&&sequence.set_pattern(1,second)&&sequence.set_pattern(7,last),"chain fixtures");
    sequence.set_chain_mask((1u<<0)|(1u<<1)|(1u<<7));
    check(!sequence.queue_pattern(1),"queue requires running transport");
    check(sequence.start(0,trace.sink())&&sequence.advance(1000,trace.sink())&&sequence.queue_pattern(7),"queue on active first pattern");
    check(sequence.selected_pattern()==0&&sequence.queued_pattern()==7,"queue leaves sounding pattern unchanged");
    check(!sequence.queue_pattern(Sequencer::pattern_count)&&sequence.queued_pattern()==7,"invalid queue preserves pending switch");
    check(sequence.advance(11025,trace.sink())&&sequence.selected_pattern()==0,"queued switch waits for full two-step pattern boundary");
    check(sequence.advance(11026,trace.sink())&&sequence.selected_pattern()==7&&sequence.queued_pattern()==Sequencer::pattern_count&&sequence.playing_step()==0,"explicit queue wins next boundary and clears exactly once");
    check(sequence.advance(33076,trace.sink()),"ascending chain continues after explicit queue");
    const auto ons=trace.only(EventType::NoteOn);
    const std::array<int,7> expected{60,61,67,60,61,64,67};
    check(ons.size()==expected.size(),"chain follows lengths without extra attacks");
    for(std::size_t i=0;i<ons.size();++i)check(ons[i].data1==expected[i]&&ons[i].frame==(i*44100u/8u),"chain preserves exact rational sixteenth grid");
    check(ons[2].channel==5&&ons[5].channel==3,"pattern switches route new notes to intended channels");
    check(sequence.queue_pattern(1)&&sequence.stop(34000,trace.sink())&&sequence.queued_pattern()==Sequencer::pattern_count,"Stop cancels a queued pattern");
    Ownership ownership;for(auto e:trace.events)ownership.apply(e);check(!ownership.any(),"chain Stop releases all generated owners");
    for(const auto& off:trace.only(EventType::NoteOff)) {
        if(off.data1==67)check(off.channel==5,"queued and chained note offs use original pattern channel");
        if(off.data1==64)check(off.channel==3,"previous pattern release happens before changing channel");
    }
}
void chain_chunk_independence_and_release_failure() {
    auto run=[](std::uint64_t chunk){
        Sequencer sequence;Trace trace;
        for(unsigned i=0;i<8;++i)check(sequence.set_pattern(i,one_note(static_cast<std::uint8_t>(60+i))),"eight chain slots");
        sequence.set_chain_mask(255);check(sequence.start(0,trace.sink()),"chain starts");
        for(std::uint64_t end=0;end<100000;) {end=std::min(std::uint64_t(100000),end+chunk);check(sequence.advance(end,trace.sink()),"chain render chunk");}
        check(sequence.stop(100000,trace.sink()),"chain stops");return trace.events;
    };
    const auto a=run(37),b=run(128),c=run(100000);
    check(a.size()==b.size()&&a.size()==c.size(),"chain event count independent of render chunk");
    for(std::size_t i=0;i<a.size();++i)check(equal(a[i],b[i])&&equal(a[i],c[i]),"exact chain timing and ownership independent of chunking");
    Sequencer sequence;Trace trace;auto tied=one_note(60);tied.length=2;tied.steps[1].tie=true;tied.steps[0].gate_percent=tied.steps[1].gate_percent=100;
    check(sequence.set_pattern(0,tied)&&sequence.set_pattern(1,one_note(72))&&sequence.start(0,trace.sink())&&sequence.advance(10000,trace.sink()),"tied boundary fixture");
    check(sequence.queue_pattern(1),"queue beyond sustained tie");trace.reject_release=true;
    check(!sequence.advance(12000,trace.sink())&&!sequence.running()&&sequence.selected_pattern()==0,"failed boundary release cannot switch channel or launch next pattern");
    trace.reject_release=false;check(sequence.stop(12000,trace.sink()),"failed boundary retains releasable owner");
    Ownership ownership;for(auto e:trace.events)ownership.apply(e);check(!ownership.any(),"boundary retry releases prior tied note");
}
void arp_new_orders_and_endpoints() {
    check(static_cast<unsigned>(ArpOrder::Exclusive)==2&&arp_notes(ArpOrder::Exclusive)==arp_notes(ArpOrder::UpDown),"Exclusive names the existing stable raw2 behavior");
    check(arp_notes(ArpOrder::DownUp)==std::vector<std::uint8_t>({67,64,60,64,67,64,60,64}),"descending Exclusive does not repeat endpoints");
    check(arp_notes(ArpOrder::DownInclusive)==std::vector<std::uint8_t>({67,64,60,60,64,67,67,64}),"descending Inclusive repeats endpoints");
    check(arp_notes(ArpOrder::OutsideIn)==std::vector<std::uint8_t>({60,67,64,60,67,64,60,67}),"outside-in alternates lowest and highest remaining candidates");
    check(arp_notes(ArpOrder::OutsideIn,2)==std::vector<std::uint8_t>({60,79,64,76,67,72,60,79}),"outside-in covers even octave-expanded set without duplicates");
    for(unsigned order=0;order<10;++order){
        Arpeggiator arp;Trace trace;ArpSettings settings;settings.order=static_cast<ArpOrder>(order);settings.octaves=4;
        check(arp.configure(settings,0,trace.sink())&&arp.note_on(127,100)&&arp.start(0,trace.sink())&&arp.advance(44100,trace.sink())&&arp.stop(44100,trace.sink()),"all ten orders handle singleton clipped candidate safely");
        const auto notes=trace.only(EventType::NoteOn);check(notes.size()==8,"singleton cycles at every pulse");
        for(auto e:notes)check(e.data1==127,"new orders preserve MIDI pitch bound");
    }
}
}

static void live_edits_keep_phase() {
    using namespace fmer;
    Sequencer seq;Trace trace;Pattern pat;pat.length=8;
    for(unsigned i=0;i<8;i++){pat.steps[i].note_count=1;pat.steps[i].notes[0]={static_cast<uint8_t>(60+i),100};}
    check(seq.set_pattern(0,pat)&&seq.set_pattern(1,pat)&&seq.start(0,trace.sink())&&seq.advance(17000,trace.sink()),"live sequence reaches step3");
    const auto step=seq.playing_step(),ticks=seq.clock_ticks(),attacks=trace.only(EventType::NoteOn).size();
    check(step==3&&seq.queue_pattern(1),"boundary queue before edit");
    pat.steps[4].notes[0].pitch=88;
    check(seq.set_pattern(0,pat,true)&&seq.set_tempo(150,true),"live step and tempo accepted");
    check(seq.running()&&seq.playing_step()==step&&seq.clock_ticks()==ticks&&seq.queued_pattern()==1,"live edit preserves step, tick, queue");
    check(trace.only(EventType::Start).size()==1&&trace.only(EventType::NoteOn).size()==attacks,"no restart or premature attack");
    check(seq.advance(23000,trace.sink()),"edited step reached");
    auto notes=trace.only(EventType::NoteOn);check(notes[attacks].data1==88,"next step uses edited data without replaying first step");
    check(seq.advance(50000,trace.sink())&&seq.selected_pattern()==1,"queued boundary survives live edit");
    check(seq.stop(50000,trace.sink()),"live sequence releases");
    check(trace.only(EventType::NoteOn).size()==trace.only(EventType::NoteOff).size(),"all live sequence attacks released");
    Arpeggiator arp;Trace ar;ArpSettings settings;
    check(arp.configure(settings,0,ar.sink())&&arp.note_on(60,100)&&arp.note_on(64,100)&&arp.note_on(67,100)&&arp.start(0,ar.sink())&&arp.advance(7000,ar.sink()),"arp reaches second note");
    auto prior=ar.only(EventType::NoteOn);check(prior.size()==2,"arp prior phase");
    settings.gate_percent=40;settings.rate=8;
    check(arp.configure(settings,7000,ar.sink(),true)&&arp.set_tempo(150,true),"live arp settings accepted");
    check(arp.advance(7001,ar.sink())&&ar.only(EventType::NoteOn).size()==prior.size(),"no immediate retrigger from settings");
    check(arp.advance(20000,ar.sink()),"arp advances after edit");
    check(ar.only(EventType::NoteOn)[2].data1==67,"arp order phase retained");
    check(arp.stop(20000,ar.sink()),"arp stop after live settings");
    check(ar.only(EventType::NoteOn).size()==ar.only(EventType::NoteOff).size(),"all live arp notes released");
}
static void external_clock_grid() {
    using namespace fmer;
    for(unsigned rate:{1u,2u,4u,8u,16u,32u})for(bool triplet:{false,true})for(unsigned swing:{50u,61u,75u}) {
        Arpeggiator a,b;Trace x,y;ArpSettings s;s.rate=rate;s.triplet=triplet;s.swing=swing;
        for(auto* p:{&a,&b}){p->external_clock(true);check(p->configure(s,0,x.sink())&&p->note_on(60,100),"external arp config");}
        check(a.start(0,x.sink())&&b.start(0,y.sink()),"external arp start");
        for(uint64_t clock=0;clock<192;++clock){
            const auto at=clock*1000;
            check(a.clock(at,1000,x.sink())&&b.clock(at,1000,y.sink()),"external pulse accepted");
            check(a.advance(at+1000,x.sink()),"external wide chunk");
            for(uint64_t pos=at;pos<at+1000;pos+=17)check(b.advance(std::min(at+1000,pos+17),y.sink()),"external narrow chunk");
        }
        auto nx=x.only(EventType::NoteOn),ny=y.only(EventType::NoteOn);
        check(nx.size()==rate*2*(triplet?3:2)/2,"two bars external rate count including triplets and swing");
        check(nx.size()==ny.size(),"external chunk count invariant");
        for(size_t i=0;i<nx.size();++i)check(nx[i].frame==ny[i].frame,"external chunk timing invariant");
        auto count=nx.size();check(a.advance(250000,x.sink())&&x.only(EventType::NoteOn).size()==count,"clock loss cannot schedule later attacks");
        check(a.stop(250000,x.sink()),"external arp stop");
        check(x.only(EventType::NoteOn).size()==x.only(EventType::NoteOff).size(),"all externally generated notes release");
    }
}
void strum_once_and_rearm() {
    for(bool external:{false,true}) {
        Arpeggiator arp;Trace trace;ArpSettings settings;settings.order=ArpOrder::Strum;settings.rate=16;
        check(arp.configure(settings,0,trace.sink()),"strum setting accepted");
        arp.note_on(67,100);arp.note_on(60,100);arp.note_on(64,100);arp.external_clock(external);arp.start(0,trace.sink());
        if(external)for(unsigned i=0;i<48;i++)check(arp.clock(i*919,919,trace.sink()),"strum follows external pulses");
        check(arp.advance(44100,trace.sink()),"strum advance");
        auto on=trace.only(EventType::NoteOn),off=trace.only(EventType::NoteOff);
        check(on.size()==3 && off.size()==3,"strum plays exactly once with balanced releases");
        check(on[0].data1==60 && on[1].data1==64 && on[2].data1==67,"strum ascends the held chord");
        arp.note_on(60,100);
        if(external)for(unsigned i=48;i<96;i++)arp.clock(i*919,919,trace.sink());
        arp.advance(88200,trace.sink());arp.stop(88200,trace.sink());
        check(trace.only(EventType::NoteOn).size()==6 && trace.only(EventType::NoteOff).size()==6,"fresh key rearms one rake with no stuck notes");
    }
}
int main() {
    const std::array<std::pair<const char*, void (*)()>, 23> tests{{
        {"strum_once_and_rearm",strum_once_and_rearm}, {"midi_streaming", midi_streaming}, {"midi_sysex_bounds", midi_sysex_bounds},
        {"sequence_chord_rest_tie", sequence_chord_rest_tie}, {"rational_clock_long_run", rational_clock_long_run},
        {"chunk_independence", chunk_independence}, {"transport_continue", transport_continue},
        {"validation_and_pattern_switch", validation_and_pattern_switch}, {"overlap_ownership", overlap_ownership},
        {"rejected_release_retry", rejected_release_retry}, {"queue_overflow_safety", queue_overflow_safety},
        {"dense_schedule_overflow", dense_schedule_overflow}, {"arp_orders", arp_orders},
        {"arp_latch_and_capacity", arp_latch_and_capacity}, {"arp_clips_octaves_and_releases", arp_clips_octaves_and_releases},
        {"arp_extended_orders_and_seed", arp_extended_orders_and_seed},
        {"arp_rate_swing_triplet_and_release_retry", arp_rate_swing_triplet_and_release_retry},
        {"inactive_steps_are_validated", inactive_steps_are_validated},
        {"pattern_boundary_queue_and_chain",pattern_boundary_queue_and_chain},
        {"chain_chunk_independence_and_release_failure",chain_chunk_independence_and_release_failure},
        {"arp_new_orders_and_endpoints",arp_new_orders_and_endpoints},
        {"live_edits_keep_phase",live_edits_keep_phase}, {"external_clock_grid",external_clock_grid}
    }};
    std::size_t failures = 0;
    for (const auto& test : tests) {
        try { test.second(); std::cout << "PASS " << test.first << '\n'; }
        catch (const std::exception& error) { ++failures; std::cerr << "FAIL " << test.first << ": " << error.what() << '\n'; }
    }
    std::cout << tests.size() << " performance tests; " << failures << " failures\n";
    return failures ? 1 : 0;
}
