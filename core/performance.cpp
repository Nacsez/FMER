#include "performance.hpp"

#include <algorithm>
#include <limits>

namespace fmer {
namespace {
constexpr auto never = std::numeric_limits<std::uint64_t>::max();
bool terminal(const Event& value) {
    return value.type == EventType::NoteOff || value.type == EventType::Stop ||
           value.type == EventType::AllNotesOff || value.type == EventType::Reset ||
           (value.type == EventType::ControlChange &&
            (value.data1 == 120 || value.data1 == 121 || value.data1 == 123 ||
             (value.data1 == 64 && value.data2 < 64)));
}
std::uint64_t add_frame(std::uint64_t frame, std::uint64_t distance) {
    return distance > never - frame ? never : frame + distance;
}
bool valid_clock(std::uint32_t rate, std::uint16_t bpm) {
    return rate >= 8000 && rate <= 384000 && bpm >= 20 && bpm <= 300;
}
Event event(std::uint64_t frame, EventType type, EventSource source,
            std::uint8_t channel = 0, std::uint8_t first = 0, std::uint8_t second = 0) {
    return Event{frame, type, channel, first, second, source};
}
}

const char* event_type_name(EventType type) {
    switch (type) {
#define FMER_EVENT_NAME(name) case EventType::name: return #name
        FMER_EVENT_NAME(NoteOn); FMER_EVENT_NAME(NoteOff); FMER_EVENT_NAME(ControlChange);
        FMER_EVENT_NAME(ProgramChange); FMER_EVENT_NAME(PitchBend); FMER_EVENT_NAME(PolyPressure);
        FMER_EVENT_NAME(ChannelPressure); FMER_EVENT_NAME(Clock); FMER_EVENT_NAME(Start);
        FMER_EVENT_NAME(Continue); FMER_EVENT_NAME(Stop); FMER_EVENT_NAME(SongPosition);
        FMER_EVENT_NAME(ActiveSensing); FMER_EVENT_NAME(Reset); FMER_EVENT_NAME(SysExComplete);
        FMER_EVENT_NAME(AllNotesOff);
#undef FMER_EVENT_NAME
    }
    return "Unknown";
}
const char* event_source_name(EventSource source) {
    switch (source) {
        case EventSource::Midi: return "midi";
        case EventSource::Sequencer: return "sequencer";
        case EventSource::Arpeggiator: return "arpeggiator";
        case EventSource::System: return "system";
    }
    return "unknown";
}
const char* performance_error_name(PerformanceError error) {
    switch (error) {
#define FMER_ERROR_NAME(name) case PerformanceError::name: return #name
        FMER_ERROR_NAME(None); FMER_ERROR_NAME(InvalidTempo); FMER_ERROR_NAME(InvalidPattern);
        FMER_ERROR_NAME(InvalidNote); FMER_ERROR_NAME(PatternIndex); FMER_ERROR_NAME(RunningEdit);
        FMER_ERROR_NAME(OutputRejected); FMER_ERROR_NAME(TimeOrder); FMER_ERROR_NAME(HeldNoteCapacity);
#undef FMER_ERROR_NAME
    }
    return "Unknown";
}

bool EventQueue::push(const Event& value) {
    if (panic_pending_ || (!terminal(value) && size_ >= capacity - release_reserve)) {
        ++overflows_;
        return false;
    }
    if (size_ == capacity) {
        ++overflows_;
        ++panics_;
        head_ = 0;
        size_ = 1;
        panic_pending_ = true;
        events_[0] = event(value.frame, EventType::AllNotesOff, EventSource::System, 255);
        return false;
    }
    events_[(head_ + size_) % capacity] = value;
    ++size_;
    return true;
}
bool EventQueue::pop(Event& value) {
    if (!size_) return false;
    value = events_[head_];
    head_ = (head_ + 1) % capacity;
    --size_;
    if (panic_pending_) panic_pending_ = false;
    return true;
}
EventSink EventQueue::sink() {
    return {this, [](void* self, const Event& value) {
        return static_cast<EventQueue*>(self)->push(value);
    }};
}

void MidiParser::reset() {
    status_ = running_status_ = needed_ = received_ = 0;
    in_sysex_ = sysex_dropped_ = false;
    sysex_size_ = 0;
    stats_ = {};
}
bool MidiParser::emit(Event value, EventSink sink) {
    if (!sink.emit(value)) { ++stats_.output_rejected; return false; }
    ++stats_.events;
    return true;
}
bool MidiParser::feed(std::uint8_t byte, std::uint64_t frame, EventSink sink) {
    ++stats_.bytes;
    if (byte >= 0xf8) {
        EventType type;
        switch (byte) {
            case 0xf8: type = EventType::Clock; break;
            case 0xfa: type = EventType::Start; break;
            case 0xfb: type = EventType::Continue; break;
            case 0xfc: type = EventType::Stop; break;
            case 0xfe: type = EventType::ActiveSensing; break;
            case 0xff: type = EventType::Reset; break;
            default: return true; // Undefined real-time statuses preserve parser state.
        }
        return emit(event(frame, type, EventSource::Midi), sink);
    }
    if (in_sysex_) {
        if (byte < 0x80 || byte == 0xf7) {
            if (!sysex_dropped_) {
                if (sysex_size_ == sysex_capacity) {
                    sysex_dropped_ = true;
                    ++stats_.sysex_overflow;
                } else sysex_[sysex_size_++] = byte;
            }
            if (byte == 0xf7) {
                in_sysex_ = false;
                if (!sysex_dropped_) {
                    ++stats_.sysex_completed;
                    return emit(event(frame, EventType::SysExComplete, EventSource::Midi), sink);
                }
                sysex_size_ = 0;
            }
            return true;
        }
        ++stats_.malformed;
        in_sysex_ = false; // Abort interrupted SysEx, then process the new status.
        sysex_size_ = 0;
    }
    if (byte & 0x80) {
        if (received_) ++stats_.malformed;
        status_ = byte;
        received_ = 0;
        if (byte < 0xf0) {
            running_status_ = byte;
            needed_ = ((byte & 0xf0) == 0xc0 || (byte & 0xf0) == 0xd0) ? 1 : 2;
        } else {
            running_status_ = 0;
            if (byte == 0xf0) {
                in_sysex_ = true;
                sysex_dropped_ = false;
                sysex_size_ = 1;
                sysex_[0] = byte;
                needed_ = 0;
            } else if (byte == 0xf2) needed_ = 2;
            else if (byte == 0xf1 || byte == 0xf3) needed_ = 1;
            else { needed_ = 0; status_ = 0; }
        }
        return true;
    }
    if (!status_ || !needed_) { ++stats_.stray_data; return true; }
    data_[received_++] = byte;
    if (received_ < needed_) return true;
    const auto complete_status = status_;
    const auto first = data_[0];
    const auto second = needed_ == 2 ? data_[1] : std::uint8_t{0};
    received_ = 0;
    status_ = running_status_;
    if (!status_) needed_ = 0;
    EventType type;
    switch (complete_status & 0xf0) {
        case 0x80: type = EventType::NoteOff; break;
        case 0x90: type = second ? EventType::NoteOn : EventType::NoteOff; break;
        case 0xa0: type = EventType::PolyPressure; break;
        case 0xb0: type = EventType::ControlChange; break;
        case 0xc0: type = EventType::ProgramChange; break;
        case 0xd0: type = EventType::ChannelPressure; break;
        case 0xe0: type = EventType::PitchBend; break;
        default:
            if (complete_status != 0xf2) return true;
            type = EventType::SongPosition;
            break;
    }
    return emit(event(frame, type, EventSource::Midi,
                      static_cast<std::uint8_t>(complete_status < 0xf0 ? complete_status & 0x0f : 0),
                      first, second), sink);
}

Sequencer::Sequencer(std::uint32_t sample_rate) : sample_rate_(sample_rate) {}
bool Sequencer::set_tempo(std::uint16_t bpm, bool live) {
    if (running_ && !live) { error_ = PerformanceError::RunningEdit; return false; }
    if (!valid_clock(sample_rate_, bpm)) { error_ = PerformanceError::InvalidTempo; return false; }
    if (running_ && !external_) {
        next_clock_ = add_frame(cursor_, (next_clock_ - cursor_) * bpm_ / bpm);
        if (release_frame_ != never) release_frame_ = add_frame(cursor_, (release_frame_ - cursor_) * bpm_ / bpm);
    }
    bpm_ = bpm;
    clock_remainder_ = 0;
    error_ = PerformanceError::None;
    return true;
}
const Pattern* Sequencer::pattern(std::size_t index) const {
    return index < pattern_count ? &patterns_[index] : nullptr;
}
bool Sequencer::set_pattern(std::size_t index, const Pattern& value, bool live) {
    if (index >= pattern_count) { error_ = PerformanceError::PatternIndex; return false; }
    if (index == selected_ && (running_ || active_count_) && (!live || value.channel != patterns_[index].channel)) {
        error_ = PerformanceError::RunningEdit; return false;
    }
    if (value.length < 1 || value.length > 64 || value.channel > 15) {
        error_ = PerformanceError::InvalidPattern; return false;
    }
    // Hidden trailing positions are preserved and must be valid before expansion.
    for (std::size_t i = 0; i < value.steps.size(); ++i) {
        const auto& step = value.steps[i];
        if (step.note_count > 9 || step.gate_percent < 1 || step.gate_percent > 100 ||
            (step.tie && step.note_count)) {
            error_ = PerformanceError::InvalidPattern; return false;
        }
        for (std::size_t n = 0; n < step.note_count; ++n) {
            if (step.notes[n].pitch > 127 || !step.notes[n].velocity || step.notes[n].velocity > 127) {
                error_ = PerformanceError::InvalidNote; return false;
            }
            for (std::size_t previous = 0; previous < n; ++previous) {
                if (step.notes[n].pitch == step.notes[previous].pitch) {
                    error_ = PerformanceError::InvalidNote; return false;
                }
            }
        }
    }
    patterns_[index] = value;
    // Active notes retain their scheduled release. Edited steps take effect on
    // their next visit; shortening wraps only an out-of-range next position.
    if (index == selected_ && position_ >= value.length) position_ = 0;
    error_ = PerformanceError::None;
    return true;
}
bool Sequencer::release(std::uint64_t frame, EventSink sink) {
    std::size_t retained = 0;
    for (std::size_t i = 0; i < active_count_; ++i) {
        if (!sink.emit(event(frame, EventType::NoteOff, EventSource::Sequencer,
                             patterns_[selected_].channel, active_[i].pitch))) {
            active_[retained++] = active_[i];
        }
    }
    active_count_ = retained;
    release_frame_ = retained ? frame : never;
    if (retained) error_ = PerformanceError::OutputRejected;
    return !retained;
}
bool Sequencer::select_pattern(std::size_t index, std::uint64_t frame, EventSink sink) {
    if (index >= pattern_count) { error_ = PerformanceError::PatternIndex; return false; }
    if (frame < cursor_) { error_ = PerformanceError::TimeOrder; return false; }
    if (running_ && !advance(frame, sink)) return false;
    if (!release(frame, sink)) return false;
    selected_ = index;
    position_ = played_position_ = 0;
    queued_ = pattern_count;
    ticks_ = clock_remainder_ = 0;
    next_clock_ = cursor_ = frame;
    paused_clock_distance_ = 0;
    error_ = PerformanceError::None;
    return true;
}
bool Sequencer::queue_pattern(std::size_t index) {
    if (index >= pattern_count) { error_ = PerformanceError::PatternIndex; return false; }
    if (!running_) { error_ = PerformanceError::RunningEdit; return false; }
    queued_ = index;
    error_ = PerformanceError::None;
    return true;
}
bool Sequencer::start(std::uint64_t frame, EventSink sink) {
    if (!valid_clock(sample_rate_, bpm_)) { error_ = PerformanceError::InvalidTempo; return false; }
    if (frame < cursor_) { error_ = PerformanceError::TimeOrder; return false; }
    if (!release(frame, sink)) return false;
    position_ = played_position_ = 0;
    queued_ = pattern_count;
    ticks_ = clock_remainder_ = 0;
    next_clock_ = cursor_ = frame;
    paused_clock_distance_ = 0;
    running_ = sink.emit(event(frame, EventType::Start, EventSource::Sequencer));
    error_ = running_ ? PerformanceError::None : PerformanceError::OutputRejected;
    return running_;
}
bool Sequencer::stop(std::uint64_t frame, EventSink sink) {
    if (frame < cursor_) { error_ = PerformanceError::TimeOrder; return false; }
    bool okay = !running_ || advance(frame, sink);
    paused_clock_distance_ = next_clock_ > frame ? next_clock_ - frame : 0;
    running_ = false;
    queued_ = pattern_count;
    okay = release(frame, sink) && okay;
    okay = sink.emit(event(frame, EventType::Stop, EventSource::Sequencer)) && okay;
    cursor_ = frame;
    error_ = okay ? PerformanceError::None : PerformanceError::OutputRejected;
    return okay;
}
bool Sequencer::resume(std::uint64_t frame, EventSink sink) {
    if (frame < cursor_) { error_ = PerformanceError::TimeOrder; return false; }
    if (!valid_clock(sample_rate_, bpm_)) { error_ = PerformanceError::InvalidTempo; return false; }
    if (running_ || active_count_) { error_ = PerformanceError::RunningEdit; return false; }
    next_clock_ = add_frame(frame, paused_clock_distance_);
    cursor_ = frame;
    running_ = sink.emit(event(frame, EventType::Continue, EventSource::Sequencer));
    error_ = running_ ? PerformanceError::None : PerformanceError::OutputRejected;
    return running_;
}
void Sequencer::move_clock() {
    const auto sum = clock_remainder_ + static_cast<std::uint64_t>(sample_rate_) * 60;
    const auto denominator = static_cast<std::uint64_t>(bpm_) * 24;
    next_clock_ = add_frame(next_clock_, sum / denominator);
    clock_remainder_ = sum % denominator;
    ++ticks_;
}
bool Sequencer::play_step(std::uint64_t frame, EventSink sink) {
    if (!position_ && ticks_) {
        auto next = selected_;
        if (queued_ < pattern_count) next = queued_;
        else if (chain_mask_) {
            for (std::size_t distance = 1; distance <= pattern_count; ++distance) {
                const auto candidate = (selected_ + distance) % pattern_count;
                if (chain_mask_ & (std::uint16_t(1) << candidate)) { next = candidate; break; }
            }
        }
        if (next != selected_) {
            // Release using the previous pattern's channel before changing it;
            // ties never carry ownership into another pattern's channel.
            if (!release(frame, sink)) return false;
            selected_ = next;
        }
        queued_ = pattern_count;
    }
    const auto& current = patterns_[selected_];
    const auto& step = current.steps[position_];
    played_position_ = position_;
    const auto next_position = (position_ + 1) % current.length;
    if (!step.tie) {
        if (!release(frame, sink)) return false;
        for (std::size_t i = 0; i < step.note_count; ++i) {
            const auto note = step.notes[i];
            if (!sink.emit(event(frame, EventType::NoteOn, EventSource::Sequencer,
                                 current.channel, note.pitch, note.velocity))) {
                error_ = PerformanceError::OutputRejected;
                return false;
            }
            active_[active_count_++] = note;
        }
    }
    if (active_count_ && !current.steps[next_position].tie) {
        const auto duration = external_ ? static_cast<std::uint64_t>(external_period_) * 6 :
                             (clock_remainder_ + static_cast<std::uint64_t>(sample_rate_) * 360) /
                              (static_cast<std::uint64_t>(bpm_) * 24);
        release_frame_ = add_frame(frame, duration * step.gate_percent / 100);
    } else release_frame_ = never;
    position_ = next_position;
    return true;
}
bool Sequencer::advance(std::uint64_t end, EventSink sink) {
    if (end < cursor_) { error_ = PerformanceError::TimeOrder; return false; }
    if (!running_) { cursor_ = end; return true; }
    while (std::min(external_ ? never : next_clock_, release_frame_) < end) {
        const auto frame = std::min(external_ ? never : next_clock_, release_frame_);
        if (external_ || release_frame_ <= next_clock_) {
            if (!release(frame, sink)) { running_ = false; cursor_ = frame; return false; }
        } else {
            if (!sink.emit(event(frame, EventType::Clock, EventSource::Sequencer)) ||
                (ticks_ % 6 == 0 && !play_step(frame, sink))) {
                release(frame, sink);
                running_ = false;
                cursor_ = frame;
                error_ = PerformanceError::OutputRejected;
                return false;
            }
            move_clock();
        }
    }
    cursor_ = end;
    error_ = PerformanceError::None;
    return true;
}

bool Sequencer::clock(std::uint64_t frame, std::uint32_t period, EventSink sink) {
    if (!external_ || !period || frame < cursor_) { error_ = PerformanceError::TimeOrder; return false; }
    if (!advance(frame, sink)) return false;
    external_period_ = period;
    if (!running_) return true;
    if (release_frame_ <= frame && !release(frame, sink)) return false;
    if (!sink.emit(event(frame, EventType::Clock, EventSource::Sequencer)) ||
        (ticks_ % 6 == 0 && !play_step(frame, sink))) return false;
    ++ticks_; next_clock_ = add_frame(frame, period); cursor_ = frame;
    return true;
}
bool Sequencer::song_position(std::uint16_t sixteenths, std::uint64_t frame, EventSink sink) {
    if (frame < cursor_ || !release(frame, sink)) return false;
    ticks_ = static_cast<std::uint64_t>(sixteenths) * 6;
    position_ = played_position_ = sixteenths % patterns_[selected_].length;
    queued_ = pattern_count; next_clock_ = cursor_ = frame; paused_clock_distance_ = 0;
    return true;
}

Arpeggiator::Arpeggiator(std::uint32_t sample_rate) : sample_rate_(sample_rate) {}
bool Arpeggiator::set_tempo(std::uint16_t bpm, bool live) {
    if (running_ && !live) { error_ = PerformanceError::RunningEdit; return false; }
    if (!valid_clock(sample_rate_, bpm)) { error_ = PerformanceError::InvalidTempo; return false; }
    if (running_ && !external_) {
        next_step_ = add_frame(cursor_, (next_step_ - cursor_) * bpm_ / bpm);
        if (release_frame_ != never) release_frame_ = add_frame(cursor_, (release_frame_ - cursor_) * bpm_ / bpm);
    }
    bpm_ = bpm;
    remainder_ = 0;
    error_ = PerformanceError::None;
    return true;
}
bool Arpeggiator::release(std::uint64_t frame, EventSink sink) {
    std::size_t retained = 0;
    for (std::size_t i = 0; i < active_count_; ++i) {
        if (!sink.emit(event(frame, EventType::NoteOff, EventSource::Arpeggiator,
                            settings_.channel, active_[i].pitch))) active_[retained++] = active_[i];
    }
    active_count_ = retained;
    release_frame_ = retained ? frame : never;
    if (retained) error_ = PerformanceError::OutputRejected;
    return !retained;
}
bool Arpeggiator::configure(const ArpSettings& settings, std::uint64_t frame, EventSink sink, bool live) {
    if (settings.octaves < 1 || settings.octaves > 4 || settings.channel > 15 ||
        settings.gate_percent > 100 || settings.swing < 50 || settings.swing > 75 ||
        !(settings.rate == 1 || settings.rate == 2 || settings.rate == 4 ||
          settings.rate == 8 || settings.rate == 16 || settings.rate == 32) || !settings.seed ||
        static_cast<unsigned>(settings.order) > static_cast<unsigned>(ArpOrder::Strum)) {
        error_ = PerformanceError::InvalidPattern; return false;
    }
    if (frame < cursor_) { error_ = PerformanceError::TimeOrder; return false; }
    if (running_ && !advance(frame, sink)) return false;
    const bool preserve = live && running_;
    if ((!preserve || settings.channel != settings_.channel) && !release(frame, sink)) return false;
    if (preserve) {
        const auto old_rate = static_cast<std::uint64_t>(settings_.rate) * (settings_.triplet ? 3u : 2u);
        const auto new_rate = static_cast<std::uint64_t>(settings.rate) * (settings.triplet ? 3u : 2u);
        if (external_) {
            const auto phase = external_ticks_ ? (external_ticks_ - 1) * 100 : 0;
            if (external_next_ > phase) external_next_ = phase + (external_next_ - phase) * old_rate / new_rate;
            schedule_external(frame);
        } else next_step_ = add_frame(frame, (next_step_ - frame) * old_rate / new_rate);
    }
    if (!preserve || settings.seed != settings_.seed) random_state_ = settings.seed;
    settings_ = settings;
    if (!settings_.latch) {
        std::size_t count = 0;
        for (std::size_t i = 0; i < held_count_; ++i) if (held_[i].physical) held_[count++] = held_[i];
        held_count_ = count;
    }
    remainder_ = 0;
    if (!preserve) { index_ = 0; next_step_ = external_ ? never : frame; }
    cursor_ = frame;
    error_ = PerformanceError::None;
    return true;
}
bool Arpeggiator::note_on(std::uint8_t pitch, std::uint8_t velocity) {
    if (pitch > 127 || velocity > 127) { error_ = PerformanceError::InvalidNote; return false; }
    if (!velocity) return note_off(pitch);
    bool any_physical = false;
    for (std::size_t i = 0; i < held_count_; ++i) any_physical = any_physical || held_[i].physical;
    if (settings_.latch && !any_physical) { held_count_ = 0; index_ = 0; }
    for (std::size_t i = 0; i < held_count_; ++i) {
        if (held_[i].note.pitch == pitch) {
            held_[i].note.velocity = velocity;
            held_[i].physical = true;
            if (settings_.order == ArpOrder::Strum) index_ = 0;
            error_ = PerformanceError::None;
            return true;
        }
    }
    if (held_count_ == held_capacity) { error_ = PerformanceError::HeldNoteCapacity; return false; }
    held_[held_count_++] = Held{Note{pitch, velocity}, true};
    if (settings_.order == ArpOrder::Strum) index_ = 0;
    error_ = PerformanceError::None;
    return true;
}
bool Arpeggiator::note_off(std::uint8_t pitch) {
    if (pitch > 127) { error_ = PerformanceError::InvalidNote; return false; }
    for (std::size_t i = 0; i < held_count_; ++i) {
        if (held_[i].note.pitch == pitch) {
            if (settings_.latch) held_[i].physical = false;
            else {
                for (std::size_t n = i + 1; n < held_count_; ++n) held_[n - 1] = held_[n];
                --held_count_;
            }
            break;
        }
    }
    error_ = PerformanceError::None;
    return true;
}
bool Arpeggiator::clear(std::uint64_t frame, EventSink sink) {
    if (frame < cursor_) { error_ = PerformanceError::TimeOrder; return false; }
    if (running_ && !advance(frame, sink)) return false;
    if (!release(frame, sink)) return false;
    held_count_ = 0;
    index_ = 0;
    cursor_ = frame;
    error_ = PerformanceError::None;
    return true;
}
bool Arpeggiator::start(std::uint64_t frame, EventSink sink) {
    if (!valid_clock(sample_rate_, bpm_)) { error_ = PerformanceError::InvalidTempo; return false; }
    if (frame < cursor_) { error_ = PerformanceError::TimeOrder; return false; }
    if (!release(frame, sink)) return false;
    index_ = remainder_ = 0;
    external_ticks_ = external_next_ = external_anchor_ = 0;
    random_state_ = settings_.seed;
    next_step_ = cursor_ = frame;
    if (external_) next_step_ = never;
    running_ = sink.emit(event(frame, EventType::Start, EventSource::Arpeggiator));
    error_ = running_ ? PerformanceError::None : PerformanceError::OutputRejected;
    return running_;
}
bool Arpeggiator::stop(std::uint64_t frame, EventSink sink) {
    if (frame < cursor_) { error_ = PerformanceError::TimeOrder; return false; }
    bool okay = !running_ || advance(frame, sink);
    running_ = false;
    okay = release(frame, sink) && okay;
    okay = sink.emit(event(frame, EventType::Stop, EventSource::Arpeggiator)) && okay;
    cursor_ = frame;
    error_ = okay ? PerformanceError::None : PerformanceError::OutputRejected;
    return okay;
}
std::size_t Arpeggiator::candidates(std::array<Note, held_capacity * 4>& result) const {
    std::size_t count = 0;
    for (unsigned octave = 0; octave < settings_.octaves; ++octave) {
        for (std::size_t i = 0; i < held_count_; ++i) {
            const auto pitch = static_cast<unsigned>(held_[i].note.pitch) + octave * 12;
            if (pitch <= 127) result[count++] = Note{static_cast<std::uint8_t>(pitch), held_[i].note.velocity};
        }
    }
    if (settings_.order != ArpOrder::Played) {
        // Stable insertion sort has a fixed 128-note bound and never allocates.
        // Equal pitches from overlapping octave expansions retain held-note order.
        for (std::size_t i = 1; i < count; ++i) {
            const auto value = result[i];
            auto position = i;
            while (position && result[position - 1].pitch > value.pitch) {
                result[position] = result[position - 1];
                --position;
            }
            result[position] = value;
        }
    }
    return count;
}
bool Arpeggiator::advance(std::uint64_t end, EventSink sink) {
    if (end < cursor_) { error_ = PerformanceError::TimeOrder; return false; }
    if (!running_) { cursor_ = end; return true; }
    while (std::min(next_step_, release_frame_) < end) {
        const auto frame = std::min(next_step_, release_frame_);
        if (release_frame_ <= next_step_) {
            if (!release(frame, sink)) { running_ = false; cursor_ = frame; return false; }
            continue;
        }
        if (!release(frame, sink)) { running_ = false; cursor_ = frame; return false; }
        const auto swing_weight = index_ % 2 ? 100 - settings_.swing : settings_.swing;
        const auto sum = remainder_ + static_cast<std::uint64_t>(sample_rate_) * 60 * 4 *
            (settings_.triplet ? 2 : 1) * swing_weight * 2;
        const auto denominator = static_cast<std::uint64_t>(bpm_) * settings_.rate *
            (settings_.triplet ? 3 : 1) * 100;
        const auto units = 96u * 2u * (settings_.triplet ? 2u : 1u) * swing_weight /
            (settings_.rate * (settings_.triplet ? 3u : 1u)); // hundredths of a MIDI clock
        const auto duration = external_ ? static_cast<std::uint64_t>(external_period_) * units / 100u : sum / denominator;
        std::array<Note, held_capacity * 4> notes{};
        const auto count = candidates(notes);
        if (count && (settings_.order != ArpOrder::Strum || index_ < count)) {
            std::size_t position;
            if ((settings_.order == ArpOrder::UpDown || settings_.order == ArpOrder::DownUp) && count > 1) {
                const auto cycle = count * 2 - 2;
                position = static_cast<std::size_t>(index_ % cycle);
                if (position >= count) position = cycle - position;
                if (settings_.order == ArpOrder::DownUp) position = count - 1 - position;
            } else if (settings_.order == ArpOrder::Inclusive || settings_.order == ArpOrder::DownInclusive) {
                position = static_cast<std::size_t>(index_ % (count * 2));
                if (position >= count) position = count * 2 - 1 - position;
                if (settings_.order == ArpOrder::DownInclusive) position = count - 1 - position;
            } else if (settings_.order == ArpOrder::OutsideIn) {
                const auto stride = static_cast<std::size_t>(index_ % count);
                position = stride % 2 ? count - 1 - stride / 2 : stride / 2;
            } else if (settings_.order == ArpOrder::Random) {
                random_state_ ^= random_state_ << 13;
                random_state_ ^= random_state_ >> 17;
                random_state_ ^= random_state_ << 5;
                position = random_state_ % count;
            } else {
                position = static_cast<std::size_t>(index_ % count);
                if (settings_.order == ArpOrder::Down) position = count - 1 - position;
            }
            const auto attacks = settings_.order == ArpOrder::Repeat ? count : 1;
            for (std::size_t i = 0; i < attacks; ++i) {
                const auto next = notes[settings_.order == ArpOrder::Repeat ? i : position];
                // Expanded overlapping octaves must not duplicate one owner/pitch.
                bool duplicate = false;
                for (std::size_t n = 0; n < active_count_; ++n)
                    duplicate = duplicate || active_[n].pitch == next.pitch;
                if (duplicate) continue;
                if (!sink.emit(event(frame, EventType::NoteOn, EventSource::Arpeggiator,
                                     settings_.channel, next.pitch, next.velocity))) {
                    release(frame, sink);
                    running_ = false;
                    cursor_ = frame;
                    error_ = PerformanceError::OutputRejected;
                    return false;
                }
                active_[active_count_++] = next;
            }
            release_frame_ = add_frame(frame, duration * settings_.gate_percent / 100);
        }
        ++index_;
        if (external_) { external_next_ += units; schedule_external(frame); }
        else next_step_ = add_frame(next_step_, duration);
        remainder_ = sum % denominator;
    }
    cursor_ = end;
    error_ = PerformanceError::None;
    return true;
}
void Arpeggiator::schedule_external(std::uint64_t frame) {
    const auto phase = external_ticks_ ? (external_ticks_ - 1) * 100 : 0;
    // Never predict an attack on the next MIDI pulse. Only interpolate swing
    // inside the current received interval; absent clock cannot free-run notes.
    next_step_ = external_ticks_ && external_next_ < phase + 100 ?
        std::max(frame, add_frame(external_anchor_, external_next_ > phase ?
            (external_next_ - phase) * external_period_ / 100 : 0)) : never;
}
bool Arpeggiator::clock(std::uint64_t frame, std::uint32_t period, EventSink sink) {
    if (!external_ || !period || frame < cursor_) { error_ = PerformanceError::TimeOrder; return false; }
    if (!advance(frame, sink)) return false;
    external_period_ = period;
    if (!running_) return true;
    external_anchor_ = frame; ++external_ticks_; schedule_external(frame);
    return true;
}
bool Arpeggiator::resume(std::uint64_t frame, EventSink sink) {
    if (running_ || frame < cursor_) { error_ = PerformanceError::TimeOrder; return false; }
    cursor_ = frame; next_step_ = external_ ? never : frame;
    running_ = sink.emit(event(frame, EventType::Continue, EventSource::Arpeggiator));
    return running_;
}
} // namespace fmer
