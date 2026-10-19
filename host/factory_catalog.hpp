#pragma once
#include "factory_presets.hpp"
#include <iostream>

inline void print_factory_catalog() {
    std::cout << "{\"profile\":\"FMER Default 726.1\",\"sounds\":[";
    for (unsigned i=0;i<fmer::factory_preset_count;++i) {
        fmer::FactoryPreset p; fmer::load_factory_preset(i,p);
        if(i)std::cout<<',';
        std::cout<<"{\"id\":"<<i<<",\"name\":\""<<p.name<<"\",\"engine\":"<<unsigned(p.engine)<<",\"lfo_enabled\":"<<(p.lfo_enabled?1:0)<<",\"vced\":[";
        for(unsigned j=0;j<155;++j){if(j)std::cout<<',';std::cout<<unsigned(p.patch.vced[j]);}
        const auto& v=p.va;
        std::cout<<"],\"va\":["<<unsigned(v.waveform)<<','<<v.cutoff_hz<<','<<v.resonance<<','<<v.attack_ms<<','
          <<v.decay_ms<<','<<v.sustain<<','<<v.release_ms<<','<<v.lfo_rate_hz<<','<<v.lfo_depth_cents<<"]}";
    }
    std::cout<<"]}\n";
}
