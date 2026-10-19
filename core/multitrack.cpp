#include "multitrack.hpp"

#include <algorithm>

namespace fmer {
namespace {
constexpr auto never=UINT64_MAX;
std::uint64_t later(std::uint64_t frame,std::uint64_t distance) noexcept {
    return distance>never-frame?never:frame+distance;
}
Event event(std::uint64_t frame,EventType type,std::uint8_t channel=0,std::uint8_t note=0,std::uint8_t velocity=0) noexcept {
    return {frame,type,channel,note,velocity,EventSource::Sequencer};
}
bool valid(const MonoPattern& pattern) noexcept {
    if(!pattern.length || pattern.length>64)return false;
    for(const auto& s:pattern.steps)
        if(s.pitch>MonoStep::tie || !s.velocity || s.velocity>127 || !s.gate_percent || s.gate_percent>100)return false;
    return true;
}
}

MultitrackSequencer::MultitrackSequencer(std::uint32_t rate) noexcept : sample_rate_(rate) {
    for(std::uint8_t i=0;i<track_count;++i)tracks_[i].settings={i,0,i,i==0};
}

bool MultitrackSequencer::set_tempo(std::uint16_t bpm,bool live) noexcept {
    if(running_ && !live){error_=PerformanceError::RunningEdit;return false;}
    if(sample_rate_<8000 || sample_rate_>384000 || bpm<20 || bpm>300){error_=PerformanceError::InvalidTempo;return false;}
    if(running_ && !external_) {
        next_clock_=later(cursor_,(next_clock_>cursor_?next_clock_-cursor_:0)*bpm_/bpm);
        for(auto& track:tracks_)if(track.release_frame!=never)
            track.release_frame=later(cursor_,(track.release_frame>cursor_?track.release_frame-cursor_:0)*bpm_/bpm);
    }
    bpm_=bpm;clock_remainder_=0;error_=PerformanceError::None;return true;
}

const MonoPattern* MultitrackSequencer::pattern(std::size_t index) const noexcept {
    return index<pattern_count?&patterns_[index]:nullptr;
}
bool MultitrackSequencer::set_pattern(std::size_t index,const MonoPattern& pattern,bool live) noexcept {
    if(index>=pattern_count){error_=PerformanceError::PatternIndex;return false;}
    if(!valid(pattern)){error_=PerformanceError::InvalidPattern;return false;}
    if(!live && running_)for(const auto& track:tracks_)if(track.settings.pattern==index){error_=PerformanceError::RunningEdit;return false;}
    bool changed=patterns_[index].length!=pattern.length;
    for(std::size_t i=0;i<pattern.steps.size() && !changed;++i) {
        const auto& a=patterns_[index].steps[i];const auto& b=pattern.steps[i];
        changed=a.pitch!=b.pitch || a.velocity!=b.velocity || a.gate_percent!=b.gate_percent;
    }
    patterns_[index]=pattern;
    for(auto& track:tracks_)if(track.settings.pattern==index && track.position>=pattern.length)track.position=0;
    if(changed)++pattern_revision_;
    error_=PerformanceError::None;return true;
}

bool MultitrackSequencer::release(std::uint8_t index,std::uint64_t frame,TrackSink sink) noexcept {
    auto& track=tracks_[index];
    if(track.active_pitch<128 && !sink.emit(index,event(frame,EventType::NoteOff,track.active_channel,track.active_pitch))) {
        track.release_frame=frame;error_=PerformanceError::OutputRejected;return false;
    }
    track.active_pitch=MonoStep::rest;track.release_frame=never;return true;
}
bool MultitrackSequencer::release_all(std::uint64_t frame,TrackSink sink) noexcept {
    bool okay=true;
    for(std::uint8_t i=0;i<track_count;++i)okay=release(i,frame,sink)&&okay;
    return okay;
}
bool MultitrackSequencer::fail(std::uint64_t frame,TrackSink sink) noexcept {
    running_=false;stop_record();release_all(frame,sink);cursor_=frame;
    error_=PerformanceError::OutputRejected;return false;
}

bool MultitrackSequencer::configure_track(std::uint8_t index,const TrackSettings& settings,
                                        std::uint64_t frame,TrackSink sink,bool live) noexcept {
    if(index>=track_count || settings.pattern>=pattern_count){error_=PerformanceError::PatternIndex;return false;}
    if(settings.channel>15){error_=PerformanceError::InvalidPattern;return false;}
    if(frame<cursor_){error_=PerformanceError::TimeOrder;return false;}
    if(running_ && !live){error_=PerformanceError::RunningEdit;return false;}
    if(running_ && !advance(frame,sink))return false;
    auto& track=tracks_[index];
    const bool different=settings.pattern!=track.settings.pattern;
    if((different || settings.channel!=track.settings.channel || !settings.enabled) && !release(index,frame,sink))return false;
    track.settings=settings;
    if(different){track.position=track.played=0;track.queued=pattern_count;track.started=false;}
    if(index==record_track_ && (different || !settings.enabled))stop_record();
    cursor_=frame;error_=PerformanceError::None;return true;
}
bool MultitrackSequencer::set_song(const fmer_song_t& song) noexcept {
    if(running_ || !fmer_song_valid(&song))return false;
    song_=song;for(std::uint8_t t=0;t<4;t++)song_restart(t);return true;
}
bool MultitrackSequencer::edit_song(std::uint8_t t,std::uint8_t row,std::uint8_t action,int delta) noexcept {
    if(t>=4 || row>=32 || !delta || action>6 || record_armed_ || recording_)return false;
    auto& v=song_.rows[t][row];
    if(action==0)v.pattern=static_cast<std::uint8_t>(std::clamp(int(v.pattern)+delta,0,16));
    if(action==1)v.transpose=static_cast<std::int8_t>(std::clamp(int(v.transpose)+delta,-24,24));
    if(action==2)v.repeats=static_cast<std::uint8_t>(std::clamp(int(v.repeats)+delta,0,31));
    if(action<=2 && row>=song_.length[t])song_.length[t]=row+1;
    if(action==3) {song_.enabled[t]=delta>0;if(song_.enabled[t]&&!song_.length[t])song_.length[t]=1;
        if(running_) {song_cursor_[t].live=delta<0;if(delta>0)tracks_[t].launch=true;}}
    if(action==4)song_.loop[t]=delta>0;
    if(action==5) { // Remove selected entry, retain bounded trailing defaults.
        if(row>=song_.length[t])return false;
        for(unsigned r=row;r+1<song_.length[t];r++)song_.rows[t][r]=song_.rows[t][r+1];
        song_.rows[t][--song_.length[t]]={};if(!song_.length[t])song_.enabled[t]=0;
    }
    if(action==6) { // Insert a copy before selected entry (or append at end).
        if(song_.length[t]>=32 || row>song_.length[t])return false;
        for(unsigned r=song_.length[t];r>row;r--)song_.rows[t][r]=song_.rows[t][r-1];
        ++song_.length[t];
    }
    if(!running_)song_restart(t);return true;
}
void MultitrackSequencer::song_restart(std::uint8_t t) noexcept {
    song_cursor_[t]={};auto& c=song_cursor_[t];c.live=!song_.enabled[t] || !song_.length[t];
    if(!c.live)c.entry=song_.rows[t][0];
}
bool MultitrackSequencer::song_boundary(std::uint8_t t,std::uint64_t frame,TrackSink sink) noexcept {
    auto& c=song_cursor_[t];auto& track=tracks_[t];
    if(c.override_pending){c.live=true;c.override_pending=false;}
    if(c.live)return true;
    if(!song_.enabled[t] || !song_.length[t]) {c.live=true;return release(t,frame,sink);}
    if(track.started) {
        if(++c.repeat>c.entry.repeats) {
            c.repeat=0;++c.row;
            if(c.row>=song_.length[t]) {
                if(song_.loop[t])c.row=0;else {c.done=true;track.stopped=true;return release(t,frame,sink);}
            }
            c.entry=song_.rows[t][c.row];
        }
        // Do not carry a tie or old transposition into a new pattern/repeat.
        if(!release(t,frame,sink))return false;
    }
    if(c.entry.pattern<16)track.settings.pattern=c.entry.pattern;
    return true;
}

bool MultitrackSequencer::queue_pattern(std::uint8_t track,std::uint8_t pattern) noexcept {
    if(track>=track_count || pattern>=pattern_count){error_=PerformanceError::PatternIndex;return false;}
    if(!running_ || ((record_armed_ || recording_) && track==record_track_)){error_=PerformanceError::RunningEdit;return false;}
    song_cursor_[track].override_pending=true;tracks_[track].queued=pattern;error_=PerformanceError::None;return true;
}

bool MultitrackSequencer::launch_at_bar(std::uint8_t index) noexcept {
    if(index>track_count){error_=PerformanceError::PatternIndex;return false;}
    if(!running_ || recording_ || record_armed_){error_=PerformanceError::RunningEdit;return false;}
    for(std::uint8_t t=0;t<track_count;++t)if(index==track_count || index==t)tracks_[t].launch=true;
    error_=PerformanceError::None;return true;
}
bool MultitrackSequencer::stop_track(std::uint8_t index,std::uint64_t frame,TrackSink sink) noexcept {
    if(index>=track_count){error_=PerformanceError::PatternIndex;return false;}
    if(!advance(frame,sink) || !release(index,frame,sink))return false;
    auto& t=tracks_[index];t.stopped=true;t.launch=false;t.queued=pattern_count;
    if(index==record_track_)stop_record();
    error_=PerformanceError::None;return true;
}
std::uint64_t MultitrackSequencer::next_event_frame() const noexcept {
    auto at=running_&&!external_?next_clock_:never;
    for(const auto& t:tracks_)at=std::min(at,t.release_frame);
    return at;
}
bool MultitrackSequencer::start(std::uint64_t frame,TrackSink sink) noexcept {
    if(sample_rate_<8000 || sample_rate_>384000){error_=PerformanceError::InvalidTempo;return false;}
    if(frame<cursor_){error_=PerformanceError::TimeOrder;return false;}
    if(!release_all(frame,sink))return false;
    for(auto& track:tracks_){track.position=track.played=0;track.queued=pattern_count;track.started=track.stopped=track.launch=false;}
    for(std::uint8_t t=0;t<4;t++)song_restart(t);
    stop_record();ticks_=clock_remainder_=paused_clock_distance_=0;
    next_clock_=cursor_=frame;
    running_=sink.emit(255,event(frame,EventType::Start));
    error_=running_?PerformanceError::None:PerformanceError::OutputRejected;return running_;
}
bool MultitrackSequencer::stop(std::uint64_t frame,TrackSink sink) noexcept {
    if(frame<cursor_){error_=PerformanceError::TimeOrder;return false;}
    bool okay=!running_ || advance(frame,sink);
    paused_clock_distance_=next_clock_>frame?next_clock_-frame:0;running_=false;stop_record();
    for(auto& track:tracks_){track.queued=pattern_count;track.launch=false;}
    okay=release_all(frame,sink)&&okay;
    okay=sink.emit(255,event(frame,EventType::Stop))&&okay;
    cursor_=frame;error_=okay?PerformanceError::None:PerformanceError::OutputRejected;return okay;
}
bool MultitrackSequencer::resume(std::uint64_t frame,TrackSink sink) noexcept {
    if(frame<cursor_){error_=PerformanceError::TimeOrder;return false;}
    if(sample_rate_<8000 || sample_rate_>384000){error_=PerformanceError::InvalidTempo;return false;}
    if(running_){error_=PerformanceError::RunningEdit;return false;}
    for(const auto& track:tracks_)if(track.active_pitch<128){error_=PerformanceError::RunningEdit;return false;}
    next_clock_=later(frame,paused_clock_distance_);cursor_=frame;
    running_=sink.emit(255,event(frame,EventType::Continue));
    error_=running_?PerformanceError::None:PerformanceError::OutputRejected;return running_;
}
void MultitrackSequencer::move_clock() noexcept {
    const auto sum=clock_remainder_+static_cast<std::uint64_t>(sample_rate_)*60;
    const auto denominator=static_cast<std::uint64_t>(bpm_)*24;
    next_clock_=later(next_clock_,sum/denominator);clock_remainder_=sum%denominator;++ticks_;
}

bool MultitrackSequencer::play_step(std::uint8_t index,std::uint64_t frame,TrackSink sink) noexcept {
    auto& track=tracks_[index];
    if(track.stopped)return true;
    if(!track.position && !song_boundary(index,frame,sink))return false;
    if(track.stopped)return true;
    if(song_cursor_[index].live && !track.position && track.started && !(recording_ && index==record_track_)) {
        auto next=track.settings.pattern;
        if(track.queued<pattern_count)next=track.queued;
        else if(track.settings.chain_mask)for(std::uint8_t distance=1;distance<=pattern_count;++distance) {
            const auto candidate=static_cast<std::uint8_t>((track.settings.pattern+distance)%pattern_count);
            if(track.settings.chain_mask&(1u<<candidate)){next=candidate;break;}
        }
        if(next!=track.settings.pattern && !release(index,frame,sink))return false;
        track.settings.pattern=next;track.queued=pattern_count;
    }
    const auto& sc=song_cursor_[index];
    if(!sc.live && sc.entry.pattern==FMER_SONG_REST) {
        if(!release(index,frame,sink))return false;
        track.played=track.position;track.started=true;track.position=(track.position+1)%16;return true;
    }
    const auto& pattern=patterns_[track.settings.pattern];
    if(track.position>=pattern.length)track.position=0;
    const auto& step=pattern.steps[track.position];
    track.played=track.position;track.started=true;
    const auto next_position=static_cast<std::uint8_t>((track.position+1)%pattern.length);
    if(!track.settings.enabled || step.pitch!=MonoStep::tie) {
        if(!release(index,frame,sink))return false;
        if(track.settings.enabled && step.pitch<128) {
            const int pitch=int(step.pitch)+(sc.live?0:sc.entry.transpose);
            // Out-of-range notes are rests; wrapping or clamping changes the phrase.
            if(pitch<0 || pitch>127){track.position=next_position;return true;}
            if(!sink.emit(index,event(frame,EventType::NoteOn,track.settings.channel,static_cast<std::uint8_t>(pitch),step.velocity)))return false;
            track.active_pitch=static_cast<std::uint8_t>(pitch);track.active_channel=track.settings.channel;
        }
    }
    const bool recording_hold=recording_ && index==record_track_ && input_held_;
    // A short newly recorded tap owns its gate; an inherited future tie will
    // be cut by the next overdub write and must not lengthen the tap now.
    const bool recorded_tap=recording_ && index==record_track_ && last_recorded_note_<128 && !input_held_;
    if(track.active_pitch<128 && !recording_hold && (recorded_tap || pattern.steps[next_position].pitch!=MonoStep::tie)) {
        const auto duration=external_?static_cast<std::uint64_t>(external_period_)*6:
            (clock_remainder_+static_cast<std::uint64_t>(sample_rate_)*360)/(static_cast<std::uint64_t>(bpm_)*24);
        track.release_frame=later(frame,duration*step.gate_percent/100);
    } else track.release_frame=never;
    track.position=next_position;return true;
}

bool MultitrackSequencer::tick(std::uint64_t frame,TrackSink sink) noexcept {
    if(!sink.emit(255,event(frame,EventType::Clock)))return false;
    if(ticks_%6==0) {
        if(!recording_step(frame,sink))return false;
        // The count-in owns the timeline: no track advances or launches notes
        // until the shared recording downbeat, even with unequal lengths.
        if(record_armed_)return true;
        if(ticks_%96==0)for(std::uint8_t i=0;i<track_count;++i)if(tracks_[i].launch){
            auto& t=tracks_[i];if(!release(i,frame,sink))return false;
            if(t.queued<pattern_count){t.settings.pattern=t.queued;song_cursor_[i].live=true;}
            else song_restart(i);
            t.queued=pattern_count;t.position=t.played=0;t.started=t.stopped=t.launch=false;
        }
        for(std::uint8_t i=0;i<track_count;++i)if(!play_step(i,frame,sink))return false;
    }
    return true;
}
bool MultitrackSequencer::advance(std::uint64_t end,TrackSink sink) noexcept {
    if(end<cursor_){error_=PerformanceError::TimeOrder;return false;}
    // Even after an output rejection, retry retained offs on the next call.
    for(;;) {
        auto next=(running_ && !external_)?next_clock_:never;
        for(const auto& track:tracks_)next=std::min(next,track.release_frame);
        if(next>=end)break;
        for(std::uint8_t i=0;i<track_count;++i)if(tracks_[i].release_frame<=next && !release(i,next,sink))return fail(next,sink);
        if(running_ && !external_ && next_clock_==next) {
            if(!tick(next,sink))return fail(next,sink);
            move_clock();
        }
    }
    cursor_=end;error_=PerformanceError::None;return true;
}
bool MultitrackSequencer::clock(std::uint64_t frame,std::uint32_t period,TrackSink sink) noexcept {
    if(!external_ || !period || frame<cursor_){error_=PerformanceError::TimeOrder;return false;}
    if(!advance(frame,sink))return false;
    external_period_=period;
    if(!running_)return true;
    for(std::uint8_t i=0;i<track_count;++i)if(tracks_[i].release_frame<=frame && !release(i,frame,sink))return fail(frame,sink);
    if(!tick(frame,sink))return fail(frame,sink);
    ++ticks_;next_clock_=later(frame,period);cursor_=frame;error_=PerformanceError::None;return true;
}
bool MultitrackSequencer::song_position(std::uint16_t sixteenths,std::uint64_t frame,TrackSink sink) noexcept {
    if(frame<cursor_){error_=PerformanceError::TimeOrder;return false;}
    if(!release_all(frame,sink))return false;
    stop_record();ticks_=static_cast<std::uint64_t>(sixteenths)*6;
    for(std::uint8_t i=0;i<4;i++) {
        auto& track=tracks_[i];song_restart(i);auto& c=song_cursor_[i];unsigned remaining=sixteenths;
        track.queued=pattern_count;track.started=track.stopped=track.launch=false;
        if(!c.live) {
            unsigned total=0;for(unsigned r=0;r<song_.length[i];r++){const auto& v=song_.rows[i][r];total+=(v.pattern<16?patterns_[v.pattern].length:16)*(v.repeats+1);}
            if(song_.loop[i])remaining%=total;
            else if(remaining>=total){c.done=true;track.stopped=true;continue;}
            for(unsigned r=0;r<song_.length[i];r++) {const auto& v=song_.rows[i][r];unsigned len=v.pattern<16?patterns_[v.pattern].length:16,n=len*(v.repeats+1);
                if(remaining<n){c.row=r;c.entry=v;c.repeat=remaining/len;remaining%=len;if(v.pattern<16)track.settings.pattern=v.pattern;break;}remaining-=n;}
        } else remaining%=patterns_[track.settings.pattern].length;
        track.position=track.played=static_cast<std::uint8_t>(remaining);
        track.queued=pattern_count;track.started=track.stopped=track.launch=false;
    }
    clock_remainder_=0;next_clock_=cursor_=frame;paused_clock_distance_=0;error_=PerformanceError::None;return true;
}

bool MultitrackSequencer::arm_record(std::uint8_t index,std::uint64_t frame,TrackSink sink,RecordMode mode) noexcept {
    if(index>=track_count){error_=PerformanceError::PatternIndex;return false;}
    if(mode!=RecordMode::overdub && mode!=RecordMode::replace){error_=PerformanceError::InvalidPattern;return false;}
    if(frame<cursor_){error_=PerformanceError::TimeOrder;return false;}
    if(running_){if(!advance(frame,sink))return false;}else if(!start(frame,sink))return false;
    if(!release_all(frame,sink))return fail(frame,sink);
    stop_record();record_track_=index;record_pattern_=tracks_[index].settings.pattern;
    song_cursor_[index].live=true;tracks_[index].queued=pattern_count;record_armed_=true;count_in_remaining_=0;record_mode_=mode;
    count_in_steps_=record_steps_=0;count_in_started_=false;
    tracks_[index].stopped=false;tracks_[index].launch=false;
    tracks_[index].settings.enabled=true;error_=PerformanceError::None;return true;
}
void MultitrackSequencer::stop_record() noexcept {
    recording_=record_armed_=count_in_started_=false;count_in_remaining_=0;
    count_in_frame_=never;
    input_held_=false;input_note_=pending_note_=last_recorded_note_=MonoStep::rest;
    record_held_count_=0;
}
bool MultitrackSequencer::count_in_pulse(std::uint64_t frame) const noexcept {
    const auto quarter=external_?static_cast<std::uint64_t>(external_period_)*24:
        static_cast<std::uint64_t>(sample_rate_)*60/bpm_;
    return record_armed_ && count_in_remaining_ && frame>=count_in_frame_ && frame-count_in_frame_<quarter/4;
}
bool MultitrackSequencer::record_note_on(std::uint8_t note,std::uint8_t velocity) noexcept {
    if(note>127 || velocity>127){error_=PerformanceError::InvalidNote;return false;}
    if(!velocity)return record_note_off(note);
    if(record_armed_ || recording_) {
        // Same last-held-note order as mono performance. The adapter collapses
        // same-pitch owners before NoteOff; note-on moves a repeated key newest.
        for(std::uint8_t i=0;i<record_held_count_;++i)if(record_held_[i].pitch==note) {
            for(;i+1<record_held_count_;++i)record_held_[i]=record_held_[i+1];
            --record_held_count_;break;
        }
        if(record_held_count_==record_held_.size()){error_=PerformanceError::HeldNoteCapacity;return false;}
        record_held_[record_held_count_++]={note,velocity};
        input_note_=pending_note_=note;input_velocity_=pending_velocity_=velocity;input_held_=true;
    }
    error_=PerformanceError::None;return true;
}
bool MultitrackSequencer::record_note_off(std::uint8_t note) noexcept {
    if(note>127){error_=PerformanceError::InvalidNote;return false;}
    for(std::uint8_t i=0;i<record_held_count_;++i)if(record_held_[i].pitch==note) {
        for(;i+1<record_held_count_;++i)record_held_[i]=record_held_[i+1];
        --record_held_count_;break;
    }
    if(input_note_==note) {
        input_held_=record_held_count_!=0;
        if(input_held_) {
            const auto& held=record_held_[record_held_count_-1];
            input_note_=pending_note_=held.pitch;input_velocity_=pending_velocity_=held.velocity;
        }
    }
    error_=PerformanceError::None;return true;
}
bool MultitrackSequencer::recording_step(std::uint64_t frame,TrackSink sink) noexcept {
    if(record_armed_) {
        if(!count_in_started_) {
            if(ticks_%24)return true;
            count_in_started_=true;count_in_steps_=0;
        }
        if(count_in_steps_<16) {
            if(count_in_steps_%4==0) {
                count_in_remaining_=static_cast<std::uint8_t>(4-count_in_steps_/4);
                count_in_frame_=frame;
                if(sink.count_in_callback && !sink.count_in_callback(sink.context,frame,count_in_remaining_))return false;
            }
            ++count_in_steps_;return true;
        }
        if(!release_all(frame,sink))return false;
        tracks_[record_track_].settings.pattern=record_pattern_;
        for(auto& track:tracks_) {
            track.position=track.played=0;track.started=false;track.queued=pattern_count;
        }
        if(sink.count_in_callback && !sink.count_in_callback(sink.context,frame,0))return false;
        record_armed_=false;recording_=true;count_in_remaining_=0;count_in_frame_=never;record_steps_=0;
        // A tap during the lead-in is not part of the take; a held note is.
        pending_note_=input_held_?input_note_:MonoStep::rest;
        pending_velocity_=input_velocity_;last_recorded_note_=MonoStep::rest;
    }
    if(recording_){
        if(sink.before_record_callback && !sink.before_record_callback(sink.context,frame))return false;
        write_record_step();
    }
    return true;
}
void MultitrackSequencer::write_record_step() noexcept {
    auto& pattern=patterns_[record_pattern_];
    auto& track=tracks_[record_track_];
    MonoStep step{};
    auto& destination=pattern.steps[track.position];
    bool write=record_mode_==RecordMode::replace;
    if(pending_note_<128) {
        write=true;
        step.pitch=pending_note_;step.velocity=pending_velocity_;step.gate_percent=input_held_?100:75;
        last_recorded_note_=pending_note_;
    } else if(input_held_) {
        write=true;
        // Keep a self-contained onset at the pattern start on later overdub
        // loops, otherwise holding through a complete loop erases every onset.
        step.pitch=last_recorded_note_==input_note_ && track.position!=0?MonoStep::tie:input_note_;
        step.velocity=input_velocity_;step.gate_percent=100;last_recorded_note_=input_note_;
    } else {
        // An existing tie belongs to the overwritten phrase, not the new key.
        // Cut it at release; ordinary existing onsets and rests remain intact.
        if(last_recorded_note_<128 && destination.pitch==MonoStep::tie)write=true;
        last_recorded_note_=MonoStep::rest;
    }
    if(write && (destination.pitch!=step.pitch || destination.velocity!=step.velocity || destination.gate_percent!=step.gate_percent)) {
        destination=step;++pattern_revision_;
    }
    pending_note_=MonoStep::rest;
    if(++record_steps_>=pattern.length) {
        record_steps_=0;
        // Overdub can keep layering later passes; replace is an explicit take.
        if(record_mode_==RecordMode::replace){recording_=false;input_held_=false;}
    }
}

std::uint8_t MultitrackSequencer::selected_pattern(std::uint8_t t) const noexcept {return t<track_count?tracks_[t].settings.pattern:pattern_count;}
std::uint8_t MultitrackSequencer::queued_pattern(std::uint8_t t) const noexcept {return t<track_count?tracks_[t].queued:pattern_count;}
std::uint8_t MultitrackSequencer::playing_step(std::uint8_t t) const noexcept {return t<track_count?tracks_[t].played:0;}
std::uint16_t MultitrackSequencer::chain_mask(std::uint8_t t) const noexcept {return t<track_count?tracks_[t].settings.chain_mask:0;}
std::uint8_t MultitrackSequencer::track_channel(std::uint8_t t) const noexcept {return t<track_count?tracks_[t].settings.channel:0;}
bool MultitrackSequencer::track_enabled(std::uint8_t t) const noexcept {return t<track_count && tracks_[t].settings.enabled;}

} // namespace fmer
