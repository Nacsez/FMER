#pragma once

#include "performance.hpp"
#include "song.h"

namespace fmer {

struct MonoStep {
    static constexpr std::uint8_t rest = 128, tie = 129;
    std::uint8_t pitch{rest}, velocity{100}, gate_percent{75};
};
struct MonoPattern {
    std::array<MonoStep,64> steps{};
    std::uint8_t length{16};
};
struct TrackSettings {
    std::uint8_t pattern{};
    std::uint16_t chain_mask{};
    std::uint8_t channel{};
    bool enabled{true};
};
enum class RecordMode : std::uint8_t { overdub, replace };
struct TrackSink {
    void* context{};
    // Track255 marks one shared Start/Continue/Stop/Clock event. Note events
    // retain their independent track ID and configured MIDI channel.
    bool (*callback)(void*,std::uint8_t,const Event&){};
    // Remaining0 marks the exact shared recording downbeat, without a click.
    bool (*count_in_callback)(void*,std::uint64_t,std::uint8_t){};
    bool (*before_record_callback)(void*,std::uint64_t){};
    bool emit(std::uint8_t track,const Event& event) const {
        return callback && callback(context,track,event);
    }
};

// Four mono cursors over a single sixteen-pattern pool. No allocation, callbacks
// to storage or independent synth instances. All events are chronological; at
// a shared frame, scheduled gates release before clocks; steps run in track
// order, with a track's old note released before its replacement note.
class MultitrackSequencer {
public:
    static constexpr std::size_t pattern_count=16,track_count=4;
    explicit MultitrackSequencer(std::uint32_t sample_rate=44100) noexcept;
    bool set_tempo(std::uint16_t bpm,bool live=false) noexcept;
    bool set_pattern(std::size_t index,const MonoPattern& pattern,bool live=false) noexcept;
    const MonoPattern* pattern(std::size_t index) const noexcept;
    bool configure_track(std::uint8_t track,const TrackSettings&,std::uint64_t frame,
                         TrackSink sink,bool live=true) noexcept;
    const fmer_song_t& song() const noexcept { return song_; }
    bool set_song(const fmer_song_t&) noexcept;
    // Lane edits publish at the next entry boundary. Explicit Live bypasses the
    // arrangement; a Start/retrigger restarts enabled lanes from entry zero.
    bool edit_song(std::uint8_t track,std::uint8_t row,std::uint8_t action,int delta) noexcept;
    std::uint8_t song_row(std::uint8_t t) const noexcept {return t<4?song_cursor_[t].row:32;}
    std::uint8_t song_repeat(std::uint8_t t) const noexcept {return t<4?song_cursor_[t].repeat:0;}
    bool song_live(std::uint8_t t) const noexcept {return t>=4 || song_cursor_[t].live;}
    bool queue_pattern(std::uint8_t track,std::uint8_t pattern) noexcept;
    // Queued launch consumes any pending pattern and starts at zero on the next global bar.
    bool launch_at_bar(std::uint8_t track) noexcept; // track_count means all
    bool stop_track(std::uint8_t track,std::uint64_t frame,TrackSink sink) noexcept;
    bool track_stopped(std::uint8_t track) const noexcept {return track<track_count && tracks_[track].stopped;}
    bool launch_pending(std::uint8_t track) const noexcept {return track<track_count && tracks_[track].launch;}
    std::uint64_t next_event_frame() const noexcept;
    bool start(std::uint64_t frame,TrackSink sink) noexcept;
    bool stop(std::uint64_t frame,TrackSink sink) noexcept;
    bool resume(std::uint64_t frame,TrackSink sink) noexcept;
    bool advance(std::uint64_t end_frame_exclusive,TrackSink sink) noexcept;
    void external_clock(bool enabled) noexcept { external_=enabled; }
    bool clock(std::uint64_t frame,std::uint32_t period_frames,TrackSink sink) noexcept;
    bool song_position(std::uint16_t sixteenths,std::uint64_t frame,TrackSink sink) noexcept;

    // Record after four quarter-note clicks. Overdub loops until explicitly
    // stopped and preserves unperformed cells; replace writes one complete pass.
    // The first click aligns to the next quarter boundary. All tracks pause
    // during the lead-in and restart at step zero on its shared downbeat.
    // Notes quantize forward to the next 16th; a short tap is retained
    // until that boundary, held notes write ties. Replace silence writes rests;
    // overdub silence preserves old notes/rests and cuts inherited tie tails.
    // Last note wins within an interval. Stop leaves unvisited steps intact.
    bool arm_record(std::uint8_t track,std::uint64_t frame,TrackSink sink,
                    RecordMode mode=RecordMode::overdub) noexcept;
    void stop_record() noexcept;
    bool record_note_on(std::uint8_t note,std::uint8_t velocity) noexcept;
    bool record_note_off(std::uint8_t note) noexcept;

    bool running() const noexcept { return running_; }
    std::uint64_t clock_ticks() const noexcept { return ticks_; }
    std::uint8_t selected_pattern(std::uint8_t track) const noexcept;
    std::uint8_t queued_pattern(std::uint8_t track) const noexcept;
    std::uint8_t playing_step(std::uint8_t track) const noexcept;
    std::uint16_t chain_mask(std::uint8_t track) const noexcept;
    std::uint8_t track_channel(std::uint8_t track) const noexcept;
    bool track_enabled(std::uint8_t track) const noexcept;
    bool recording() const noexcept { return recording_; }
    bool record_armed() const noexcept { return record_armed_; }
    std::uint8_t record_track() const noexcept { return record_track_; }
    // Retained after a completed/stopped take for bounded adapter mirroring.
    std::uint8_t record_pattern() const noexcept { return record_pattern_; }
    std::uint8_t count_in_remaining() const noexcept { return count_in_remaining_; }
    // Same audio-clock pulse as the click, never a separate UI timer. Zero
    // countdown while armed means awaiting the first actual quarter boundary.
    bool count_in_pulse(std::uint64_t frame) const noexcept;
    std::uint32_t pattern_revision() const noexcept { return pattern_revision_; }
    PerformanceError last_error() const noexcept { return error_; }

private:
    struct SongCursor {fmer_song_row_t entry{};std::uint8_t row{},repeat{};bool live{},done{},override_pending{};};
    void song_restart(std::uint8_t) noexcept;
    bool song_boundary(std::uint8_t,std::uint64_t,TrackSink) noexcept;
    fmer_song_t song_{};
    std::array<SongCursor,4> song_cursor_{};
    struct Track {
        TrackSettings settings{};
        std::uint64_t release_frame{UINT64_MAX};
        std::uint8_t position{},played{},queued{pattern_count};
        std::uint8_t active_pitch{MonoStep::rest},active_channel{};
        bool started{},stopped{},launch{};
    };
    bool release(std::uint8_t track,std::uint64_t frame,TrackSink) noexcept;
    bool release_all(std::uint64_t frame,TrackSink) noexcept;
    bool play_step(std::uint8_t track,std::uint64_t frame,TrackSink) noexcept;
    bool tick(std::uint64_t frame,TrackSink) noexcept;
    bool recording_step(std::uint64_t frame,TrackSink) noexcept;
    void write_record_step() noexcept;
    void move_clock() noexcept;
    bool fail(std::uint64_t frame,TrackSink) noexcept;
    std::array<MonoPattern,pattern_count> patterns_{};
    std::array<Track,track_count> tracks_{};
    std::uint32_t sample_rate_{};
    std::uint16_t bpm_{120};
    std::uint64_t next_clock_{},clock_remainder_{},ticks_{},cursor_{},paused_clock_distance_{};
    std::uint32_t external_period_{919},pattern_revision_{};
    std::uint8_t record_track_{track_count},record_pattern_{},record_steps_{},count_in_steps_{},count_in_remaining_{};
    std::uint8_t input_note_{MonoStep::rest},input_velocity_{100},pending_note_{MonoStep::rest},pending_velocity_{100};
    std::uint8_t last_recorded_note_{MonoStep::rest};
    std::array<Note,32> record_held_{};
    std::uint8_t record_held_count_{};
    RecordMode record_mode_{RecordMode::overdub};
    std::uint64_t count_in_frame_{UINT64_MAX};
    bool running_{},external_{},record_armed_{},recording_{},count_in_started_{},input_held_{};
    PerformanceError error_{PerformanceError::None};
};

} // namespace fmer
