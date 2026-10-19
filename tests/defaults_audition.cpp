// Offline bank audition/measurement harness, shared by frozen708 and current recipes.
// Same dry six-second score and gain for both banks; no loudness normalization.
#include "factory_presets.hpp"
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>
void u16(std::ofstream& s,std::uint16_t v){s.put(char(v&255));s.put(char(v>>8));}
void u32(std::ofstream& s,std::uint32_t v){u16(s,std::uint16_t(v));u16(s,std::uint16_t(v>>16));}
double energy(const std::vector<float>& a){double sum=0;for(auto v:a)sum+=v*v;return std::sqrt(sum/a.size());}
int main(int argc,char** argv){
    if(argc!=2)return 2;
    std::cout<<"[";
    for(unsigned id=0;id<64;++id){
        fmer::FactoryPreset p;fmer::Synth synth;
        if(!fmer::load_factory_preset(id,p)||!synth.set_patch(p.patch)||!synth.set_engine(p.engine)||!synth.set_va_parameters(p.va))return 3;
        synth.set_lfo_enabled(p.lfo_enabled);synth.set_voice_budget(4);std::vector<float> samples(44100*6);
        synth.note_on(0,60,100);synth.render(samples.data(),44100);synth.note_off(0,60);synth.render(samples.data()+44100,44100);synth.panic();
        for(auto note:{48,55,60,64})synth.note_on(0,std::uint8_t(note),110);
        synth.render(samples.data()+88200,66150);
        for(auto note:{48,55,60,64})synth.note_off(0,std::uint8_t(note));
        synth.render(samples.data()+154350,110250);
        if(synth.stats().clipped_samples)return 4;
        std::ofstream out(std::string(argv[1])+"/preset-"+std::to_string(id)+".wav",std::ios::binary|std::ios::trunc);
        if(!out)return 5;
        out.write("RIFF",4);u32(out,36+std::uint32_t(samples.size()*2));out.write("WAVEfmt ",8);u32(out,16);u16(out,1);u16(out,1);u32(out,44100);u32(out,88200);u16(out,2);u16(out,16);out.write("data",4);u32(out,std::uint32_t(samples.size()*2));
        double peak=0;for(auto v:samples){if(!std::isfinite(v)||std::abs(v)>1)return 6;peak=std::max(peak,std::abs(double(v)));u16(out,std::uint16_t(std::int16_t(std::lround(v*32767))));}if(!out)return 7;
        if(id)std::cout<<',';
        std::cout<<"{\"id\":"<<id<<",\"name\":\""<<p.name<<"\",\"engine\":"<<unsigned(p.engine)<<",\"peak\":"<<peak<<",\"rms\":"<<energy(samples)<<",\"matrix\":[";
        bool comma=false;
        for(int note:{36,60,84})for(int velocity:{40,100,127}){
            synth.panic();std::vector<float> a(44100);synth.note_on(0,std::uint8_t(note),std::uint8_t(velocity));synth.render(a.data(),a.size());
            if(synth.stats().clipped_samples)return 8;
            synth.note_off(0,std::uint8_t(note));std::vector<float> release(441000);synth.render(release.data(),release.size());
            if(synth.stats().active_voices)return 9;
            double pk=0;for(auto v:a){if(!std::isfinite(v))return 10;pk=std::max(pk,std::abs(double(v)));}
            if(comma)std::cout<<',';comma=true;
            std::cout<<"{\"note\":"<<note<<",\"velocity\":"<<velocity<<",\"peak\":"<<pk<<",\"rms\":"<<energy(a)<<"}";
        }
        std::cout<<"]}";
    }
    std::cout<<"]\n";
}
