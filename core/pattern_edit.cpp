#include "pattern_edit.hpp"

namespace fmer {
unsigned note_start(const MonoPattern& p,unsigned step) noexcept {
    if(step>=p.length)return p.length;
    while(step && p.steps[step].pitch==MonoStep::tie)--step;
    return p.steps[step].pitch<128?step:p.length;
}
unsigned note_length(const MonoPattern& p,unsigned step) noexcept {
    const auto start=note_start(p,step);if(start>=p.length)return 0;
    auto end=start+1;while(end<p.length && p.steps[end].pitch==MonoStep::tie)++end;
    return end-start;
}
bool erase_note(MonoPattern& p,unsigned step) noexcept {
    const auto start=note_start(p,step),length=note_length(p,step);
    if(!length)return false;
    for(auto i=start;i<start+length;++i)p.steps[i].pitch=MonoStep::rest;
    return true;
}
bool move_note(MonoPattern& p,unsigned step,int distance) noexcept {
    const auto start=note_start(p,step),length=note_length(p,step);
    const auto target=static_cast<int>(start)+distance;
    if(!length || !distance || target<0 || target+length>p.length)return false;
    for(unsigned i=target;i<target+length;++i)
        if((i<start || i>=start+length) && p.steps[i].pitch!=MonoStep::rest)return false;
    auto copy=p;
    erase_note(p,start);
    for(unsigned i=0;i<length;++i)p.steps[target+i]=copy.steps[start+i];
    return true;
}
bool resize_note(MonoPattern& p,unsigned step,unsigned length) noexcept {
    const auto start=note_start(p,step),old=note_length(p,step);
    if(!old || !length || start+length>p.length)return false;
    for(auto i=start+old;i<start+length;++i)if(p.steps[i].pitch!=MonoStep::rest)return false;
    for(auto i=start+length;i<start+old;++i)p.steps[i].pitch=MonoStep::rest;
    const auto ending=p.steps[start+old-1].gate_percent;
    for(auto i=start;i<start+length;++i){
        if(i>start){p.steps[i]=p.steps[start];p.steps[i].pitch=MonoStep::tie;}
        p.steps[i].gate_percent=i+1==start+length?ending:100;
    }
    return true;
}
bool copy_steps(const MonoPattern& p,unsigned start,unsigned count,MonoPattern& out) noexcept {
    if(!count || start>=p.length || count>p.length-start)return false;
    out={};out.length=static_cast<std::uint8_t>(count);
    for(unsigned i=0;i<count;++i)out.steps[i]=p.steps[start+i];
    if(out.steps[0].pitch==MonoStep::tie)out.steps[0].pitch=MonoStep::rest;
    return true;
}
bool paste_steps(MonoPattern& p,unsigned start,const MonoPattern& copy) noexcept {
    if(!copy.length || copy.length>64 || start>=p.length || copy.length>p.length-start)return false;
    for(unsigned i=0;i<copy.length;++i)p.steps[start+i]=copy.steps[i];
    // Do not accidentally extend the last pasted note into the replaced phrase.
    if(start+copy.length<p.length && p.steps[start+copy.length].pitch==MonoStep::tie)
        p.steps[start+copy.length].pitch=MonoStep::rest;
    return true;
}
}
