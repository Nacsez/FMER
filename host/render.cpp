#include "render.hpp"
#include "parameters.hpp"
#include "performance.hpp"
#include "synth.hpp"
#include "effects.hpp"
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
constexpr std::uint32_t rate = 44100;
std::string quote(const std::string& input) {
    std::ostringstream out; out << '"';
    for (const unsigned char c : input) {
        if (c == '"' || c == '\\') out << '\\' << static_cast<char>(c);
        else if (c < 0x20) out << "\\u" << std::hex << std::setfill('0') << std::setw(4) << static_cast<unsigned>(c);
        else out << static_cast<char>(c);
    }
    out << '"'; return out.str();
}
void ensure(bool okay,const char* message) { if(!okay)throw std::runtime_error(message); }
int number(const std::string& text,int low,int high) {
    std::size_t consumed=0;const int value=std::stoi(text,&consumed);
    if(consumed!=text.size()||value<low||value>high)throw std::invalid_argument("Value outside range "+std::to_string(low)+".."+std::to_string(high)+": "+text);
    return value;
}
float real_number(const std::string& text) {
    std::size_t consumed=0;const float value=std::stof(text,&consumed);
    if(consumed!=text.size()||!std::isfinite(value))throw std::invalid_argument("Expected finite number");
    return value;
}
fmer::EffectKind effect_kind(const std::string& name) {
    using fmer::EffectKind;
    if(name=="filter")return EffectKind::filter;if(name=="reverb")return EffectKind::reverb;
    if(name=="delay")return EffectKind::delay;if(name=="drive")return EffectKind::drive;
    if(name=="chorus")return EffectKind::chorus;if(name=="phaser")return EffectKind::phaser;
    throw std::invalid_argument("Unknown effect stage");
}
void effect_setting(fmer::EffectParameters& p,const std::string& assignment) {
    const auto eq=assignment.find('=');ensure(eq!=std::string::npos,"Use --fx NAME=VALUE");
    const auto key=assignment.substr(0,eq);const auto value=real_number(assignment.substr(eq+1));
    if(key=="drive")p.drive=value;else if(key=="chorus")p.chorus=value;
    else if(key=="delay")p.delay=value;else if(key=="delay_ms")p.delay_ms=value;
    else if(key=="feedback")p.feedback=value;else if(key=="reverb")p.reverb=value;
    else if(key=="cutoff_hz")p.cutoff_hz=value;else if(key=="phaser")p.phaser=value;
    else if(key=="chorus_rate_hz")p.chorus_rate_hz=value;else if(key=="chorus_depth")p.chorus_depth=value;
    else if(key=="phaser_rate_hz")p.phaser_rate_hz=value;else if(key=="phaser_depth")p.phaser_depth=value;
    else if(key=="resonance")p.resonance=value;
    else if(key=="filter_mode"){ensure(value>=0 && value<=2 && value==std::floor(value),"Filter mode0..2");p.filter_mode=static_cast<fmer::FilterMode>(static_cast<unsigned>(value));}
    else if(key=="reverb_model"){ensure(value>=0 && value<=3 && value==std::floor(value),"Reverb model0..3");p.reverb_model=static_cast<fmer::ReverbModel>(static_cast<unsigned>(value));}
    else if(key=="delay_model"){ensure(value>=0 && value<=1 && value==std::floor(value),"Delay model0..1");p.delay_model=static_cast<fmer::DelayModel>(static_cast<unsigned>(value));}
    else if(key=="reverb_decay")p.reverb_decay=value;else throw std::invalid_argument("Unknown effect parameter");
}
fmer::ArpOrder arp_order(const std::string& name) {
    using fmer::ArpOrder;
    if(name=="up")return ArpOrder::Up;if(name=="down")return ArpOrder::Down;
    if(name=="up_down"||name=="exclusive")return ArpOrder::UpDown;
    if(name=="played")return ArpOrder::Played;if(name=="inclusive")return ArpOrder::Inclusive;
    if(name=="random")return ArpOrder::Random;if(name=="repeat")return ArpOrder::Repeat;
    if(name=="down_exclusive")return ArpOrder::DownUp;
    if(name=="down_inclusive")return ArpOrder::DownInclusive;
    if(name=="strum")return ArpOrder::Strum;
    if(name=="outside_in")return ArpOrder::OutsideIn;
    throw std::invalid_argument("Unknown arpeggio order");
}
struct Options {
    std::string scenario,out,report,patch,pattern,engine="fm",wave="saw";
    int note=60,velocity=100,bpm=120,duration=3,voice=1,cutoff=6000,tail=1;
    fmer::EffectParameters effects;
    fmer::ArpSettings arp;
    bool held_release=false, lfo_enabled=true, mono=false;
    fmer::VaParameters va;
    fmer::GlideParameters glide;
    int budget=12;
    std::vector<std::pair<int,int>> edits;
};
Options options(int argc,char**argv) {
    Options o;
    o.arp.octaves=2;o.arp.order=fmer::ArpOrder::UpDown;
    for(int i=1;i<argc;++i) {
        const std::string key=argv[i];if(++i>=argc)throw std::invalid_argument("Missing value for "+key);
        const std::string v=argv[i];
        if(key=="--render")o.scenario=v;else if(key=="--out")o.out=v;else if(key=="--report")o.report=v;
        else if(key=="--patch")o.patch=v;else if(key=="--note")o.note=number(v,0,127);
        else if(key=="--velocity")o.velocity=number(v,1,127);else if(key=="--bpm")o.bpm=number(v,20,300);
        else if(key=="--duration")o.duration=number(v,1,20);else if(key=="--voice")o.voice=number(v,1,32);
        else if(key=="--engine")o.engine=v;else if(key=="--wave")o.wave=v;else if(key=="--cutoff")o.cutoff=number(v,20,18000);
        else if(key=="--tail")o.tail=number(v,1,10);else if(key=="--pattern")o.pattern=v;
        else if(key=="--lfo-enabled")o.lfo_enabled=number(v,0,1)!=0;
        else if(key=="--mono")o.mono=number(v,0,1)!=0;
        else if(key=="--glide-mode")o.glide.mode=static_cast<fmer::GlideMode>(number(v,0,2));
        else if(key=="--glide-ms")o.glide.time_ms=static_cast<float>(number(v,0,2000));
        else if(key=="--glide-curve")o.glide.contour=static_cast<fmer::GlideContour>(number(v,0,2));
        else if(key=="--budget")o.budget=number(v,1,12);
        else if(key=="--va") {
            const auto eq=v.find('=');ensure(eq!=std::string::npos,"Use --va NAME=VALUE");
            const auto name=v.substr(0,eq);const auto value=real_number(v.substr(eq+1));
            if(name=="resonance")o.va.resonance=value;
            else if(name=="attack_ms")o.va.attack_ms=value;
            else if(name=="decay_ms")o.va.decay_ms=value;
            else if(name=="sustain")o.va.sustain=value;
            else if(name=="release_ms")o.va.release_ms=value;
            else if(name=="lfo_rate_hz")o.va.lfo_rate_hz=value;
            else if(name=="lfo_depth_cents")o.va.lfo_depth_cents=value;
            else throw std::invalid_argument("Unknown VA parameter");
        }
        else if(key=="--fx")effect_setting(o.effects,v);
        else if(key=="--fx-order") {
            std::istringstream names(v);std::string name;std::size_t index=0;
            while(std::getline(names,name,',')){ensure(index<6,"Exactly six effect stages required");o.effects.order[index++]=effect_kind(name);}
            ensure(index==6,"Exactly six effect stages required");
        }
        else if(key=="--arp-order")o.arp.order=arp_order(v);
        else if(key=="--arp-octaves")o.arp.octaves=static_cast<std::uint8_t>(number(v,1,4));
        else if(key=="--arp-gate")o.arp.gate_percent=static_cast<std::uint8_t>(number(v,0,100));
        else if(key=="--arp-rate")o.arp.rate=static_cast<std::uint8_t>(number(v,1,32));
        else if(key=="--arp-swing")o.arp.swing=static_cast<std::uint8_t>(number(v,50,75));
        else if(key=="--arp-seed")o.arp.seed=static_cast<std::uint32_t>(number(v,1,2147483647));
        else if(key=="--arp-latch")o.arp.latch=number(v,0,1)!=0;
        else if(key=="--arp-triplet")o.arp.triplet=number(v,0,1)!=0;
        else if(key=="--arp-held-release")o.held_release=number(v,0,1)!=0;
        else if(key=="--set") {
            const auto eq=v.find('=');if(eq==std::string::npos||o.edits.size()>=145)throw std::invalid_argument("Use --set ID=VALUE; at most145 edits");
            o.edits.emplace_back(number(v.substr(0,eq),0,144),number(v.substr(eq+1),0,127));
        } else throw std::invalid_argument("Unknown option "+key);
    }
    ensure(!o.out.empty()&&!o.report.empty(),"Render needs --out WAV and --report JSON");
    ensure(o.engine=="fm"||o.engine=="va","Engine must be fm or va");
    ensure(o.wave=="sine"||o.wave=="saw"||o.wave=="square"||o.wave=="triangle"||o.wave=="noise","Unknown VA waveform");
    ensure(std::filesystem::absolute(o.out).lexically_normal()!=std::filesystem::absolute(o.report).lexically_normal(),"Audio/report paths must differ");
    ensure(!std::filesystem::exists(o.out)&&!std::filesystem::exists(o.report),"Output already exists; choose new filenames");
    return o;
}
fmer::Pattern read_pattern(const std::string& path) {
    ensure(std::filesystem::file_size(path)<=16384,"Pattern file exceeds bound");
    std::ifstream input(path);std::string magic;input>>magic;
    ensure(magic=="FMER_PATTERN_1","Unknown pattern format");
    auto field=[&](int low,int high){std::string token;ensure(bool(input>>token),"Truncated pattern");return number(token,low,high);};
    fmer::Pattern p;p.length=static_cast<std::uint8_t>(field(1,64));p.channel=static_cast<std::uint8_t>(field(0,15));
    const auto count=field(p.length,64);
    for(int i=0;i<count;++i) {
        auto& step=p.steps[static_cast<std::size_t>(i)];step.gate_percent=static_cast<std::uint8_t>(field(1,100));
        step.tie=field(0,1)!=0;step.note_count=static_cast<std::uint8_t>(field(0,9));
        for(std::size_t n=0;n<step.note_count;++n)step.notes[n]={static_cast<std::uint8_t>(field(0,127)),static_cast<std::uint8_t>(field(1,127))};
    }
    std::string extra;ensure(!(input>>extra),"Trailing pattern fields");return p;
}
bool collect(void* context,const fmer::Event& event) {
    // The largest exposed score is 20 seconds at 300 BPM, 1/32 triplet,
    // four-octave triad Repeat: 28,802 owned events including transport.
    auto& events=*static_cast<std::vector<fmer::Event>*>(context);if(events.size()>=32768)return false;
    events.push_back(event);return true;
}
std::vector<fmer::Event> scenario(const Options& o,std::uint64_t end) {
    using namespace fmer;std::vector<Event> events;events.reserve(2048);EventSink sink{&events,collect};
    const auto note=static_cast<std::uint8_t>(o.note),vel=static_cast<std::uint8_t>(o.velocity);
    auto on=[&](std::uint64_t frame,int pitch){ensure(pitch<=127,"Phrase exceeds MIDI pitch range; choose a lower root");sink.emit({frame,EventType::NoteOn,0,static_cast<std::uint8_t>(pitch),vel,EventSource::Midi});};
    auto off=[&](std::uint64_t frame,int pitch){sink.emit({frame,EventType::NoteOff,0,static_cast<std::uint8_t>(pitch),0,EventSource::Midi});};
    if(o.scenario=="note"||o.scenario=="chord") {
        on(0,note);off(end*2/3,note);if(o.scenario=="chord")for(int d:{4,7}){on(0,o.note+d);off(end*2/3,o.note+d);}
    } else if(o.scenario=="sequence") {
        Sequencer seq(rate);Pattern p;
        if(!o.pattern.empty())p=read_pattern(o.pattern);
        else {
            ensure(o.note<=118,"Sequence needs root <=118");p.length=8;
            const std::array<int,8> offsets{{0,2,4,7,9,7,4,2}};
            for(std::size_t i=0;i<offsets.size();++i){p.steps[i].note_count=1;p.steps[i].notes[0]={static_cast<std::uint8_t>(o.note+offsets[i]),vel};}
        }
        ensure(seq.set_tempo(static_cast<std::uint16_t>(o.bpm))&&seq.set_pattern(0,p),"Invalid sequence settings");
        ensure(seq.start(0,sink)&&seq.advance(end,sink)&&seq.stop(end,sink),"Sequence output refused");
    } else if(o.scenario=="arp") {
        ensure(o.note<=120,"Arp triad needs root <=120; octave expansion above127 is omitted");Arpeggiator arp(rate);
        ensure(arp.set_tempo(static_cast<std::uint16_t>(o.bpm))&&arp.configure(o.arp,0,sink),"Invalid arp settings");
        for(int d:{0,4,7})ensure(arp.note_on(static_cast<std::uint8_t>(o.note+d),vel),"Held note limit");
        ensure(arp.start(0,sink),"Arp start refused");
        if(o.held_release){ensure(arp.advance(end/2,sink),"Arp output refused");for(int d:{0,4,7})ensure(arp.note_off(static_cast<std::uint8_t>(o.note+d)),"Held release refused");}
        ensure(arp.advance(end,sink)&&arp.stop(end,sink),"Arp output refused");
    } else if(o.scenario=="midi") {
        ensure(o.note<=123,"MIDI fixture needs root <=123");MidiParser parser;
        for(auto b:std::array<std::uint8_t,7>{{0x90,note,vel,0xf8,static_cast<std::uint8_t>(note+4),vel,0xf8}})ensure(parser.feed(b,0,sink),"MIDI fixture failed");
        for(auto b:std::array<std::uint8_t,4>{{note,0,static_cast<std::uint8_t>(note+4),0}})ensure(parser.feed(b,end*2/3,sink),"MIDI zero-velocity release failed");
    } else if(o.scenario=="stress") {
        for(int i=0;i<24;++i){on(static_cast<std::uint64_t>(i)*64,48+i);off(end*2/3,48+i);}
    } else throw std::invalid_argument("Unknown scenario: "+o.scenario);
    std::stable_sort(events.begin(),events.end(),[](const Event&a,const Event&b){return a.frame<b.frame;});return events;
}
void apply(fmer::Synth&s,const fmer::Event&e) {
    using fmer::EventType;const auto source=static_cast<std::uint8_t>(e.source);
    switch(e.type) {
    case EventType::NoteOn:s.note_on(e.channel,e.data1,e.data2,source);break;
    case EventType::NoteOff:s.note_off(e.channel,e.data1,source);break;
    case EventType::ControlChange:s.control_change(e.channel,e.data1,e.data2);break;
    case EventType::PitchBend:s.pitch_bend(e.channel,static_cast<std::uint16_t>(e.data1|(e.data2<<7)));break;
    case EventType::AllNotesOff:if(e.channel==255)s.panic();else s.panic_source(source);break;
    case EventType::Reset:s.panic();break;
    default:break; // Transport retained in trace; generators emit their owned releases.
    }
}
void put16(std::ostream&o,std::uint16_t n){o.put(static_cast<char>(n));o.put(static_cast<char>(n>>8));}
void put32(std::ostream&o,std::uint32_t n){put16(o,static_cast<std::uint16_t>(n));put16(o,static_cast<std::uint16_t>(n>>16));}
void write_wav(const std::string&path,const std::vector<float>&audio) {
    std::ofstream o(path,std::ios::binary);ensure(bool(o),"Cannot create audio output");const auto bytes=static_cast<std::uint32_t>(audio.size()*2);
    o.write("RIFF",4);put32(o,36+bytes);o.write("WAVEfmt ",8);put32(o,16);put16(o,1);put16(o,1);put32(o,rate);put32(o,rate*2);put16(o,2);put16(o,16);o.write("data",4);put32(o,bytes);
    for(float sample:audio)put16(o,static_cast<std::uint16_t>(static_cast<std::int16_t>(std::lround(std::clamp(sample,-1.f,1.f)*32767.f))));
    o.flush();ensure(bool(o),"Audio output write failed");
}
fmer::Patch patch_for(const Options&o) {
    auto patch=fmer::make_init_patch();
    if(!o.patch.empty()) {
        std::ifstream in(o.patch,std::ios::binary);ensure(bool(in),"Cannot read patch");std::array<std::uint8_t,4105>bytes{};
        in.read(reinterpret_cast<char*>(bytes.data()),bytes.size());ensure(in.gcount()<=4104,"Patch exceeds one standard bank");
        std::array<fmer::Patch,32>bank{};std::size_t count=0;std::string error;
        if(!fmer::decode_sysex(bytes.data(),static_cast<std::size_t>(in.gcount()),bank,count,error))throw std::invalid_argument(error);
        ensure(static_cast<std::size_t>(o.voice)<=count,"Selected voice exceeds imported patch count");patch=bank[static_cast<std::size_t>(o.voice-1)];
    }
    for(const auto&edit:o.edits){std::string error;if(!fmer::edit_parameter(patch,static_cast<std::uint16_t>(edit.first),edit.second,error))throw std::invalid_argument(error);}
    return patch;
}
}
void print_parameters() {
    std::cout<<"{\"schema_version\":1,\"parameters\":[";bool first=true;
    for(const auto&p:fmer::parameter_registry()) {
        if(!first)std::cout<<',';first=false;
        std::cout<<"{\"id\":"<<p.id<<",\"name\":"<<quote(p.name)<<",\"operator_number\":"<<unsigned(p.operator_number)<<",\"minimum\":"<<unsigned(p.minimum)<<",\"maximum\":"<<unsigned(p.maximum)<<",\"default_value\":"<<unsigned(p.default_value)<<'}';
    }
    std::cout<<"]}\n";
}
int run_render(int argc,char**argv) {
    try {
        const auto o=options(argc,argv);const auto patch=patch_for(o);const auto score=static_cast<std::uint64_t>(o.duration)*rate;
        const auto tail=static_cast<std::uint64_t>(o.tail)*rate;
        const auto frames=score+tail;const auto events=scenario(o,score);fmer::Synth synth;fmer::Effects effects;
        ensure(effects.init(rate)&&effects.set_parameters(o.effects),"Effect parameters rejected");
        ensure(synth.init(rate)&&synth.set_patch(patch),"Synth initialization rejected");
        synth.set_lfo_enabled(o.lfo_enabled);
        ensure(synth.set_voice_budget(static_cast<unsigned>(o.budget)),"Voice budget rejected");
        ensure(synth.set_glide(o.glide)&&synth.set_mono(o.mono),"Mono/glide settings rejected");
        if(o.engine=="va") {
            fmer::VaParameters va=o.va;va.cutoff_hz=static_cast<float>(o.cutoff);
            va.waveform=o.wave=="noise"?fmer::VaWaveform::noise:o.wave=="sine"?fmer::VaWaveform::sine:o.wave=="square"?fmer::VaWaveform::square:o.wave=="triangle"?fmer::VaWaveform::triangle:fmer::VaWaveform::saw;
            ensure(synth.set_va_parameters(va)&&synth.set_engine(fmer::SynthEngine::va),"VA settings rejected");
        }
        std::vector<float>audio(static_cast<std::size_t>(frames),0.f);
        std::size_t cursor=0,index=0;const auto start=std::chrono::steady_clock::now();
        while(cursor<audio.size()) {
            while(index<events.size()&&events[index].frame<=cursor)apply(synth,events[index++]);
            auto count=std::min(std::size_t(64),audio.size()-cursor);if(index<events.size())count=std::min(count,static_cast<std::size_t>(events[index].frame-cursor));
            ensure(count!=0,"Renderer made no progress");synth.render(audio.data()+cursor,count);effects.process(audio.data()+cursor,count);cursor+=count;
        }
        const double elapsed=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();double peak=0,energy=0;std::array<double,256>wave{};
        for(std::size_t i=0;i<audio.size();++i){ensure(std::isfinite(audio[i]),"Non-finite audio sample");const double s=audio[i];peak=std::max(peak,std::abs(s));energy+=s*s;auto&bin=wave[std::min(wave.size()-1,i*wave.size()/audio.size())];bin=std::max(bin,std::abs(s));}
        const auto stats=synth.stats();const auto fx=effects.stats();std::ostringstream report;report<<std::setprecision(12)
            <<"{\"schema_version\":1,\"scenario\":"<<quote(o.scenario)<<",\"engine\":"<<quote(o.engine=="fm"?"MSFA":"FMER-VA")<<",\"hardware_access\":false,\"device_fidelity\":\"unmeasured\","
            <<"\"sample_rate\":"<<rate<<",\"frames\":"<<frames<<",\"score_frames\":"<<score<<",\"peak\":"<<peak<<",\"rms\":"<<std::sqrt(energy/audio.size())
            <<",\"render_seconds\":"<<elapsed<<",\"build_id\":"<<quote(FMER_BUILD_ID)<<",\"compiler\":"<<quote(FMER_COMPILER_ID)
            <<",\"voice_limit\":"<<o.budget<<",\"control_block_frames\":64,\"peak_voices\":"<<stats.peak_voices<<",\"active_voices_end\":"<<stats.active_voices
            <<",\"mono\":"<<(o.mono?"true":"false")<<",\"glide\":{\"mode\":"<<unsigned(o.glide.mode)<<",\"time_ms\":"<<o.glide.time_ms<<",\"curve\":"<<unsigned(o.glide.contour)<<'}'
            <<",\"stolen_voices\":"<<stats.stolen_voices<<",\"clipped_samples\":"<<stats.clipped_samples<<",\"rejected_events\":"<<stats.rejected_events<<",\"patch_vced\":[";
        for(std::size_t i=0;i<patch.vced.size();++i){if(i)report<<',';report<<unsigned(patch.vced[i]);}report<<"],\"events\":[";
        for(std::size_t i=0;i<events.size();++i){const auto&e=events[i];if(i)report<<',';report<<"{\"frame\":"<<e.frame<<",\"type\":"<<quote(fmer::event_type_name(e.type))<<",\"source\":"<<quote(fmer::event_source_name(e.source))<<",\"channel\":"<<unsigned(e.channel)<<",\"data1\":"<<unsigned(e.data1)<<",\"data2\":"<<unsigned(e.data2)<<'}';}
        report<<"],\"waveform\":[";for(std::size_t i=0;i<wave.size();++i){if(i)report<<',';report<<wave[i];}
        report<<"],\"tail_frames\":"<<tail<<",\"fx_clipped_samples\":"<<fx.clipped_samples
            <<",\"fx_sanitized_samples\":"<<fx.sanitized_samples<<",\"fx_tail_peak\":"<<fx.tail_peak
            <<",\"fx_storage_bytes\":"<<fmer::Effects::storage_bytes()
            <<",\"tail_truncated\":"<<(stats.active_voices||fx.tail_peak>0.00001f?"true":"false")<<"}\n";
        write_wav(o.out,audio);std::ofstream file(o.report,std::ios::binary);file<<report.str();file.flush();ensure(bool(file),"Report write failed");
        std::cout<<"Rendered "<<o.scenario<<": "<<frames<<" frames; peak="<<peak<<"; voices="<<stats.peak_voices<<"; report="<<o.report<<'\n';return 0;
    }catch(const std::exception&e){std::cerr<<"Render error: "<<e.what()<<'\n';return 2;}
}
