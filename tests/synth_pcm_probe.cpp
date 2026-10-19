#include "synth.hpp"
#include "factory_presets.hpp"
#include <array>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>

// Optional binary equivalence probe. Capture before and after an optimization
// with the same host compiler; compare the entire files, not an audio metric.
// Floating-point host/target identity is deliberately not assumed.
int main(int argc, char** argv) {
    if(argc!=2) {std::cerr<<"usage: synth_pcm_probe OUTPUT.bin\n";return 2;}
    try {
        std::ofstream out(argv[1],std::ios::binary);
        if(!out)throw std::runtime_error("cannot open output");
        std::array<float,257> audio{};
        constexpr std::size_t chunks[]{1,17,63,64,65,127,128,257};
        std::uint64_t frames=0;
        for(unsigned scenario=0;scenario<104;++scenario) {
            fmer::Synth s;
            std::array<fmer::PartParameters,4> p{};
            s.set_voice_budget(4);
            const bool parts=scenario%2==0;
            s.set_parts_enabled(parts);s.set_mono(!parts);
            for(unsigned t=0;t<4;++t) {
                auto& q=p[t];
                if(scenario>=40) {
                    fmer::FactoryPreset preset;
                    if(!fmer::load_factory_preset(scenario-40,preset))throw std::runtime_error("factory fixture");
                    q.patch=preset.patch;q.va=preset.va;q.engine=preset.engine;q.lfo_enabled=preset.lfo_enabled;
                } else {
                    q.engine=scenario<32?fmer::SynthEngine::fm:scenario<36?fmer::SynthEngine::va:
                        (t%2?fmer::SynthEngine::va:fmer::SynthEngine::fm);
                    q.patch.vced[134]=scenario%32;q.patch.vced[135]=scenario%8;
                    q.patch.vced[137]=63;q.patch.vced[138]=17;q.patch.vced[139]=20;
                    q.patch.vced[140]=51;q.patch.vced[141]=scenario%2;q.patch.vced[142]=scenario%6;
                    q.patch.vced[143]=4;q.patch.vced[144]=24;
                    for(unsigned op=0;op<6;++op) {
                        const auto at=op*21;
                        q.patch.vced[at]=83;q.patch.vced[at+1]=67;q.patch.vced[at+2]=49;q.patch.vced[at+3]=95;
                        q.patch.vced[at+4]=99;q.patch.vced[at+5]=79;q.patch.vced[at+6]=61;q.patch.vced[at+7]=0;
                        q.patch.vced[at+8]=36;q.patch.vced[at+9]=13;q.patch.vced[at+10]=23;
                        q.patch.vced[at+11]=op%4;q.patch.vced[at+12]=(op+1)%4;
                        q.patch.vced[at+13]=op%8;q.patch.vced[at+14]=op%4;q.patch.vced[at+15]=op%8;
                        q.patch.vced[at+16]=70+op*4;q.patch.vced[at+17]=(scenario+t+op)%7==0;
                        q.patch.vced[at+18]=1+op;q.patch.vced[at+19]=(scenario*17+op*13)%100;
                        q.patch.vced[at+20]=3+op;
                    }
                    q.va.waveform=static_cast<fmer::VaWaveform>(scenario%4);
                    q.va.cutoff_hz=3500;q.va.resonance=.6f;q.va.attack_ms=3;
                    q.va.decay_ms=19;q.va.sustain=.71f;q.va.release_ms=29;
                    q.va.lfo_depth_cents=19;q.va.lfo_rate_hz=3.7f;
                }
                q.glide.mode=static_cast<fmer::GlideMode>(scenario%3);
                q.glide.contour=static_cast<fmer::GlideContour>((scenario/3)%3);q.glide.time_ms=37;
                if(!s.configure_part(static_cast<std::uint8_t>(t),q))throw std::runtime_error("part fixture");
            }
            auto set_single=[&](unsigned t){
                s.set_patch(p[t].patch);s.set_engine(p[t].engine);s.set_va_parameters(p[t].va);
                s.set_glide(p[t].glide);s.set_lfo_enabled(p[t].lfo_enabled);
            };
            set_single(0);
            std::array<std::uint8_t,4> notes{48,53,60,67};
            for(unsigned block=0;block<160;++block) {
                if(block%17==0)for(unsigned t=0;t<(parts?4u:1u);++t) {
                    notes[t]=static_cast<std::uint8_t>(36+((scenario+block+t*11)%60));
                    const auto velocity=static_cast<std::uint8_t>(1+(scenario*7+block*3+t*17)%127);
                    if(parts)s.part_note_on(t,t,notes[t],velocity,4);else s.note_on(0,notes[t],velocity,1);
                }
                if(block==15||block==52||block==101)for(unsigned t=0;t<4;++t)
                    s.set_part_mix(t,block==15?.37f:block==52?0.f:1.f,block==52&&t%2);
                if(block==35||block==80)for(unsigned t=0;t<4;++t) {
                    s.control_change(t,7,block==35?87:127);s.control_change(t,11,block==35?59:127);
                    s.pitch_bend(t,block==35?10231:8192);s.control_change(t,1,block==35?47:0);
                }
                if(block==64)for(unsigned t=0;t<4;++t) {
                    p[t].engine=p[t].engine==fmer::SynthEngine::fm?fmer::SynthEngine::va:fmer::SynthEngine::fm;
                    s.configure_part(t,p[t]);
                }
                if(block==64&&!parts)set_single(0);
                if(block==93)s.panic();
                if(block%23==22)for(unsigned t=0;t<(parts?4u:1u);++t) {
                    if(parts)s.part_note_off(t,t,notes[t],4);else s.note_off(0,notes[t],1);
                }
                const auto count=chunks[block%8];s.render(audio.data(),count);
                for(std::size_t i=0;i<count;++i)if(!std::isfinite(audio[i]))throw std::runtime_error("nonfinite PCM");
                out.write(reinterpret_cast<const char*>(audio.data()),static_cast<std::streamsize>(count*sizeof(float)));
                const auto stats=s.stats();
                const std::uint64_t values[]{stats.rendered_frames,stats.note_ons,stats.note_offs,stats.stolen_voices,
                    stats.retriggers,stats.clipped_samples,stats.rejected_events,stats.active_voices,
                    stats.released_voices,stats.peak_voices};
                out.write(reinterpret_cast<const char*>(values),sizeof(values));frames+=count;
            }
        }
        out.close();if(!out)throw std::runtime_error("capture write failed");
        std::cout<<"104 cases; "<<frames<<" exact float samples plus ownership/statistics captured\n";
        return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
