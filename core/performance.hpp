#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace fmer {

enum class EventType : std::uint8_t {
    NoteOn, NoteOff, ControlChange, ProgramChange, PitchBend, PolyPressure,
    ChannelPressure, Clock, Start, Continue, Stop, SongPosition, ActiveSensing,
    Reset, SysExComplete, AllNotesOff
};
enum class EventSource : std::uint8_t { Midi, Sequencer, Arpeggiator, System };
struct Event {
    std::uint64_t frame = 0;
    EventType type = EventType::NoteOff;
    std::uint8_t channel = 0;
    std::uint8_t data1 = 0;
    std::uint8_t data2 = 0;
    EventSource source = EventSource::Midi;
};
using EventCallback = bool (*)(void*, const Event&);
struct EventSink {
    void* context = nullptr;
    EventCallback callback = nullptr;
    bool emit(const Event& event) const { return callback && callback(context, event); }
};
const char* event_type_name(EventType type);
const char* event_source_name(EventSource source);

// A bounded FIFO reserves space for termination. If even that reserve is full,
// pending events are replaced with a global AllNotesOff (channel 255, System).
class EventQueue {
public:
    static constexpr std::size_t capacity = 256;
    static constexpr std::size_t release_reserve = 16;
    bool push(const Event& event);
    bool pop(Event& event);
    std::size_t size() const { return size_; }
    std::uint64_t overflow_count() const { return overflows_; }
    std::uint64_t panic_count() const { return panics_; }
    EventSink sink();
private:
    std::array<Event, capacity> events_{};
    std::size_t head_ = 0, size_ = 0;
    std::uint64_t overflows_ = 0, panics_ = 0;
    bool panic_pending_ = false;
};

struct MidiParserStats {
    std::uint64_t bytes = 0, events = 0, stray_data = 0, malformed = 0;
    std::uint64_t sysex_completed = 0, sysex_overflow = 0, output_rejected = 0;
};
class MidiParser {
public:
    static constexpr std::size_t sysex_capacity = 4104; // Complete standard DX7 bank.
    bool feed(std::uint8_t byte, std::uint64_t frame, EventSink sink);
    void reset();
    const MidiParserStats& stats() const { return stats_; }
    const std::uint8_t* sysex_data() const { return sysex_.data(); }
    std::size_t sysex_size() const { return sysex_size_; }
private:
    bool emit(Event event, EventSink sink);
    std::array<std::uint8_t, sysex_capacity> sysex_{};
    std::array<std::uint8_t, 2> data_{};
    std::size_t sysex_size_ = 0;
    std::uint8_t status_ = 0, running_status_ = 0, needed_ = 0, received_ = 0;
    bool in_sysex_ = false, sysex_dropped_ = false;
    MidiParserStats stats_{};
};

struct Note { std::uint8_t pitch = 60, velocity = 100; };
struct Step {
    std::array<Note, 9> notes{};
    std::uint8_t note_count = 0;
    std::uint8_t gate_percent = 75;
    bool tie = false; // Sustain preceding chord; tie steps contain no new notes.
};
struct Pattern {
    std::array<Step, 64> steps{};
    std::uint8_t length = 16;
    std::uint8_t channel = 0;
};
enum class PerformanceError : std::uint8_t {
    None, InvalidTempo, InvalidPattern, InvalidNote, PatternIndex,
    RunningEdit, OutputRejected, TimeOrder, HeldNoteCapacity
};
const char* performance_error_name(PerformanceError error);

class Sequencer {
public:
    // Shared capacity across the portable engine and target project format.
    static constexpr std::size_t pattern_count = 16;
    explicit Sequencer(std::uint32_t sample_rate = 44100);
    bool set_tempo(std::uint16_t bpm, bool live = false); // live preserves phase at the last advance.
    bool set_pattern(std::size_t index, const Pattern& pattern, bool live = false);
    const Pattern* pattern(std::size_t index) const;
    bool select_pattern(std::size_t index, std::uint64_t frame, EventSink sink);
    // While running, queue a single switch at the next full-pattern boundary.
    // Explicit queue wins once, then ascending chain traversal resumes. Zero
    // chain mask loops the current pattern. Stop/Start cancels pending queues.
    bool queue_pattern(std::size_t index);
    void set_chain_mask(std::uint16_t mask) { chain_mask_ = mask; }
    bool start(std::uint64_t frame, EventSink sink);
    bool stop(std::uint64_t frame, EventSink sink);
    bool resume(std::uint64_t frame, EventSink sink);
    bool advance(std::uint64_t end_frame_exclusive, EventSink sink);
    // External clock advances only on received24PPQN pulses. advance() still
    // services gate releases between pulses; it never free-runs the next step.
    void external_clock(bool enabled) { external_ = enabled; }
    bool clock(std::uint64_t frame, std::uint32_t period_frames, EventSink sink);
    bool song_position(std::uint16_t sixteenths, std::uint64_t frame, EventSink sink);
    bool running() const { return running_; }
    std::size_t selected_pattern() const { return selected_; }
    std::size_t queued_pattern() const { return queued_; } // pattern_count = none
    std::size_t playing_step() const { return played_position_; }
    std::uint16_t chain_mask() const { return chain_mask_; }
    std::uint64_t clock_ticks() const { return ticks_; }
    PerformanceError last_error() const { return error_; }
private:
    bool release(std::uint64_t frame, EventSink sink);
    bool play_step(std::uint64_t frame, EventSink sink);
    void move_clock();
    std::array<Pattern, pattern_count> patterns_{};
    std::array<Note, 9> active_{};
    std::size_t active_count_ = 0, selected_ = 0, position_ = 0;
    std::size_t queued_ = pattern_count, played_position_ = 0;
    std::uint32_t sample_rate_;
    std::uint16_t bpm_ = 120;
    std::uint16_t chain_mask_ = 0;
    std::uint64_t next_clock_ = 0, clock_remainder_ = 0, ticks_ = 0;
    std::uint64_t release_frame_ = UINT64_MAX, cursor_ = 0, paused_clock_distance_ = 0;
    bool running_ = false;
    bool external_ = false;
    std::uint32_t external_period_ = 919;
    PerformanceError error_ = PerformanceError::None;
};

enum class ArpOrder : std::uint8_t {
    Up, Down, UpDown, Played, Inclusive, Random, Repeat,
    DownUp, DownInclusive, OutsideIn, Strum,
    Exclusive = UpDown // Same stable raw2; no duplicate setting.
};
struct ArpSettings {
    ArpOrder order = ArpOrder::Up;
    std::uint8_t octaves = 1, gate_percent = 75, channel = 0;
    bool latch = false;
    std::uint8_t rate = 16, swing = 50; // Note denominator, paired swing 50..75%.
    bool triplet = false;
    std::uint32_t seed = 1; // Reinitialized at Start; zero is refused.
};
class Arpeggiator {
public:
    static constexpr std::size_t held_capacity = 32;
    explicit Arpeggiator(std::uint32_t sample_rate = 44100);
    bool set_tempo(std::uint16_t bpm, bool live = false);
    bool configure(const ArpSettings& settings, std::uint64_t frame, EventSink sink, bool live = false);
    bool note_on(std::uint8_t pitch, std::uint8_t velocity);
    bool note_off(std::uint8_t pitch);
    bool clear(std::uint64_t frame, EventSink sink);
    bool start(std::uint64_t frame, EventSink sink);
    bool stop(std::uint64_t frame, EventSink sink);
    bool advance(std::uint64_t end_frame_exclusive, EventSink sink);
    void external_clock(bool enabled) { external_ = enabled; }
    bool clock(std::uint64_t frame, std::uint32_t period_frames, EventSink sink);
    bool resume(std::uint64_t frame, EventSink sink);
    std::uint64_t next_event_frame() const {return !running_?UINT64_MAX:next_step_<release_frame_?next_step_:release_frame_;}
    std::size_t held_count() const { return held_count_; }
    bool running() const { return running_; }
    PerformanceError last_error() const { return error_; }
private:
    struct Held { Note note{}; bool physical = false; };
    bool release(std::uint64_t frame, EventSink sink);
    std::size_t candidates(std::array<Note, held_capacity * 4>& result) const;
    std::array<Held, held_capacity> held_{};
    std::size_t held_count_ = 0;
    ArpSettings settings_{};
    std::array<Note, held_capacity * 4> active_{};
    std::size_t active_count_ = 0;
    bool running_ = false;
    std::uint32_t random_state_ = 1;
    std::uint32_t sample_rate_;
    std::uint16_t bpm_ = 120;
    std::uint64_t next_step_ = 0, remainder_ = 0, index_ = 0, cursor_ = 0;
    std::uint64_t release_frame_ = UINT64_MAX;
    bool external_ = false;
    std::uint64_t external_ticks_ = 0, external_next_ = 0, external_anchor_ = 0;
    std::uint32_t external_period_ = 919;
    void schedule_external(std::uint64_t frame);
    PerformanceError error_ = PerformanceError::None;
};

} // namespace fmer
