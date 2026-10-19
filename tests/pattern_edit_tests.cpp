#include "pattern_edit.hpp"
#include <cstdlib>
#include <iostream>
#include <stdexcept>
using namespace fmer;
void check(bool value,const char* text){if(!value)throw std::runtime_error(text);}
bool same(const MonoPattern& a,const MonoPattern& b){
    if(a.length!=b.length)return false;
    for(unsigned i=0;i<64;++i)if(a.steps[i].pitch!=b.steps[i].pitch || a.steps[i].velocity!=b.steps[i].velocity || a.steps[i].gate_percent!=b.steps[i].gate_percent)return false;
    return true;
}
int main(){try{
    MonoPattern p;p.length=16;p.steps[2]={60,83,67};p.steps[8]={72,99,75};
    check(resize_note(p,2,4),"extend onset through three ties");
    check(p.steps[2].gate_percent==100 && p.steps[5].pitch==MonoStep::tie && p.steps[5].gate_percent==67,"hold retains terminal gate and velocity");
    const auto before=p;
    check(!resize_note(p,2,8) && same(p,before),"extension collision refuses without changing any byte");
    check(move_note(p,4,2),"moving from middle tie selects whole logical note");
    check(p.steps[2].pitch==MonoStep::rest && p.steps[4].pitch==60 && p.steps[7].pitch==MonoStep::tie && p.steps[7].gate_percent==67,"overlapping move preserves note and ties");
    const auto moved=p;
    check(!move_note(p,4,1) && same(p,moved),"move refuses occupied destination");
    check(!move_note(p,4,-5) && same(p,moved),"negative destination is atomic");
    check(resize_note(p,6,2) && p.steps[6].pitch==MonoStep::rest && p.steps[5].gate_percent==67,"shrinking from tie clears old tail and retains final gate");
    MonoPattern clip;check(copy_steps(p,4,5,clip) && clip.length==5,"copy range includes rests and separate onsets");
    check(paste_steps(p,10,clip) && p.steps[10].pitch==60 && p.steps[14].pitch==72,"paste copies exact sequence");
    const auto pasted=p;check(!paste_steps(p,13,clip) && same(p,pasted),"paste cannot exceed pattern extent");
    check(copy_steps(p,11,2,clip) && clip.steps[0].pitch==MonoStep::rest,"leading copied tie cannot attach to unrelated note");
    check(erase_note(p,11) && p.steps[10].pitch==MonoStep::rest && p.steps[11].pitch==MonoStep::rest,"delete from tie removes entire logical note");
    p.steps[63]={99,127,100};check(!resize_note(p,63,1) && p.steps[63].pitch==99,"hidden trailing steps remain untouched");
    std::cout<<"Pattern edits: holds, overlap, collision, boundaries, ranges, ties and hidden-step preservation passed\n";return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
