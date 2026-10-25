#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include "synth.h"
#include "controllers.h"
#include "dx7note.h"

extern int32_t osc_freq(int,int,int,int,int);

int main() {
    // Capture the uninitialized upstream calculation, then compare the cached
    // path over every supported note, coarse/fine setting, detune and mode.
    int32_t original[2][32][100];
    for(int mode=0;mode<2;++mode)for(int coarse=0;coarse<32;++coarse)for(int fine=0;fine<100;++fine)
        original[mode][coarse][fine]=osc_freq(0,mode,coarse,fine,7);
    const auto fallback=osc_freq(0,0,1,137,7);
    Dx7Note::init_tuning();Dx7Note::init_tuning();
    unsigned comparisons=0;
    for(int mode=0;mode<2;++mode)for(int note=0;note<128;++note)
    for(int coarse=0;coarse<32;++coarse)for(int fine=0;fine<100;++fine)for(int detune=0;detune<15;++detune) {
        const auto offset=mode==0?((1<<24)/12)*note+12606*(detune-7):detune>7?13457*(detune-7):0;
        if(osc_freq(note,mode,coarse,fine,detune)!=original[mode][coarse][fine]+offset) {
            std::fprintf(stderr,"tuning mismatch: %d %d %d %d %d\n",mode,note,coarse,fine,detune);return 1;
        }
        ++comparisons;
    }
    if(osc_freq(0,0,1,137,7)!=fallback)return 2;
    std::printf("%u exact before/after tuning comparisons; fallback and repeated initialization preserved\n",comparisons);
    return 0;
}
