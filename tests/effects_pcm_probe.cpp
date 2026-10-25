#include "effects.hpp"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>

// Optional before/after optimization probe. Compare complete output files
// using one compiler/arithmetic profile; never infer host/board PCM identity.
int main(int argc,char** argv) {
    if(argc!=2)return 2;
    try {
        std::ofstream out(argv[1],std::ios::binary);
        if(!out)throw std::runtime_error("output unavailable");
        fmer::EffectParameters p;
        std::array<float,257> audio{};
        constexpr unsigned chunks[]{1,17,63,64,65,127,128,257};
        unsigned scenario=0;std::uint64_t frames=0;
        do {
            fmer::Effects fx;
            p.cutoff_hz=1700;p.resonance=.82f;p.filter_mode=static_cast<fmer::FilterMode>(scenario%3);
            p.reverb_model=static_cast<fmer::ReverbModel>(scenario%4);p.reverb_decay=.8f;
            p.delay_model=static_cast<fmer::DelayModel>(scenario%2);p.delay_ms=20;
            p.drive=.4f;p.delay=.7f;p.reverb=.8f;p.chorus=.75f;p.phaser=.65f;
            if(!fx.set_parameters(p))throw std::runtime_error("invalid fixture");
            std::uint32_t noise=719;unsigned absolute=0;
            for(unsigned block=0;block<128;++block) {
                if(block==37){p.cutoff_hz=8000;p.resonance=.15f;p.delay_ms=47;if(!fx.set_parameters(p))return 3;}
                if(block==71){p.reverb=0;p.chorus=0;if(!fx.set_parameters(p))return 3;}
                if(block==79){p.reverb=.9f;p.chorus=.7f;if(!fx.set_parameters(p))return 3;}
                if(block==95)fx.reset();
                const auto count=chunks[block%8];
                for(unsigned i=0;i<count;++i) {
                    noise=noise*1664525u+1013904223u;
                    audio[i]=block>111?0.f:(static_cast<float>(noise>>8)/16777216.f-.5f)*.2f;
                    if(absolute++%2003==0)audio[i]+=.4f;
                }
                // Input fault sanitation stays observable, including its counters.
                if(block==105)audio[0]=std::numeric_limits<float>::quiet_NaN();
                fx.process(audio.data(),count);
                for(unsigned i=0;i<count;++i)if(!std::isfinite(audio[i]))return 4;
                out.write(reinterpret_cast<const char*>(audio.data()),count*sizeof(float));
                const auto m=fx.meters();const std::uint64_t stats[]{m.processed_frames,m.rejected_parameters,m.rejected_buffers,m.sanitized_samples,m.clipped_samples,m.limited_samples,m.guarded_samples};
                out.write(reinterpret_cast<const char*>(stats),sizeof(stats));
                const float peaks[]{m.peak_input,m.peak_output};out.write(reinterpret_cast<const char*>(peaks),sizeof(peaks));
                out.write(reinterpret_cast<const char*>(fx.activity().data()),6*sizeof(float));frames+=count;
            }
            ++scenario;
        }while(std::next_permutation(p.order.begin(),p.order.end()));
        out.close();if(!out)return 5;
        std::cout<<scenario<<" FX orders; "<<frames<<" exact samples plus counters/activity\n";
        return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
