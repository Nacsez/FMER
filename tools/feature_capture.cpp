// SPDX-License-Identifier: GPL-3.0-only
// Exact production renderer poses for documentation. No instrument access.
// Reuse the tested LCD/DMA mock; the regression entrypoint is never called here.
#define main fmer_ui_regression_main
#include "../tests/fm1_ui_tests.cpp"
#undef main
#include <cmath>

int main(int argc,char** argv) {
    if(argc!=2)return 2;
    const std::string prefix=argv[1];
    fmer_controls_t c{};for(unsigned i=0;i<FMER_PARAM_COUNT;i++)c.value[i]=fmer_control_min(i);
    for(unsigned op=0;op<6;op++){unsigned b=op*21;c.value[b]=85;c.value[b+1]=55;c.value[b+2]=40;c.value[b+3]=60;c.value[b+4]=99;c.value[b+5]=75;c.value[b+6]=60;c.value[b+16]=80;c.value[b+18]=1;c.value[b+20]=7;}
    c.value[FMER_VOICE_BUDGET]=4;c.value[FMER_TEMPO]=120;c.value[FMER_CUTOFF]=2400;c.value[FMER_VA_CUTOFF]=8000;
    c.value[FMER_FX_RESONANCE]=45;c.value[FMER_RESONANCE]=25;c.value[FMER_ATTACK]=10;c.value[FMER_DECAY]=350;c.value[FMER_SUSTAIN]=65;c.value[FMER_RELEASE]=500;
    c.value[FMER_REVERB]=30;c.value[FMER_REVERB_MODEL]=2;c.value[FMER_REVERB_DECAY]=60;c.value[FMER_DELAY]=25;c.value[FMER_DELAY_MS]=375;c.value[FMER_FEEDBACK]=35;
    c.value[FMER_CHORUS]=40;c.value[FMER_PHASER]=35;c.value[FMER_DRIVE]=15;c.value[FMER_LFO_RATE]=240;c.value[FMER_LFO_DEPTH]=15;c.value[FMER_LFO_ENABLE]=1;
    c.value[FMER_ARP_OCTAVES]=2;c.value[FMER_ARP_RATE]=16;c.value[FMER_ARP_GATE]=75;c.value[FMER_ARP_SWING]=55;c.value[FMER_ARP_ENABLE]=1;c.value[FMER_ARP_LATCH]=1;c.value[FMER_ARP_ORDER]=10;
    c.value[FMER_SEQ_LENGTH]=16;c.value[FMER_SEQ_GATE]=75;c.value[FMER_SEQ_VELOCITY]=100;c.value[FMER_SEQ_PITCH]=60;c.value[FMER_TRACK_LEVEL]=80;c.value[FMER_RECORD_MODE]=1;
    fmer_panel_t p{};fmer_panel_init(&p);p.modulation=1u|(2u<<8);
    fmer_pattern_state_t pattern{};pattern.length=16;pattern.revision=1;pattern.clipboard_length=4;pattern.undo_available=1;
    for(unsigned i=0;i<64;i++){pattern.pitch[i]=i%4==1?129:i%4==3?128:60+(i%8);pattern.velocity[i]=100;pattern.gate[i]=75;}
    for(auto& l:pattern.pattern_length)l=16;
    for(unsigned t=0;t<4;t++){
        pattern.track_pattern[t]=t;pattern.track_queued[t]=16;pattern.track_step[t]=4;pattern.track_level[t]=100-t*15;pattern.track_length[t]=16;pattern.track_fx[t]=1;pattern.track_sound[t]=64+t;
        pattern.song.length[t]=3;pattern.song.enabled[t]=1;pattern.song.loop[t]=1;
        for(unsigned e=0;e<3;e++)pattern.song.rows[t][e]={static_cast<uint8_t>(t+e),static_cast<int8_t>(e*5),static_cast<uint8_t>(e==0?1:0)};
    }
    std::array<int16_t,128> scope{};std::array<int16_t,128> parts{};
    for(unsigned i=0;i<128;i++){scope[i]=static_cast<int16_t>(9000*std::sin(i*.18)+2500*std::sin(i*.54));parts[i]=static_cast<int16_t>(7000*std::sin(i*.42));}
    fmer_ui_state_t s{};s.build=734;s.controls=&c;s.panel=&p;s.pattern=&pattern;s.scope=scope.data();s.part_scopes=parts.data();s.scope_generation=1;
    s.voice_limit=4;s.battery_valid=1;s.battery_percent=76;s.storage_ready=1;s.storage_valid_slots=128;s.patch_name="FM KEYS";s.candidate_name="FM KEYS";s.user_slot_name="MY INSTRUMENT";s.user_slot_present=1;
    s.performance.queued_pattern=16;s.performance.seq_position=4;s.performance.arp_held=3;
    auto shot=[&](const std::string& name,unsigned family,unsigned page){p.family=family;p.page[family]=page;p.focus_active=0;mock_sync();fmer_ui_reset();settle(s);require_exact_frame(s);image((prefix+name+".ppm").c_str());};
    shot("home",FMER_PANEL_HOME,0);
    for(unsigned i=0;i<8;i++)shot("fm-edit-"+std::to_string(i),FMER_PANEL_EDIT,i);
    shot("fm-env",FMER_PANEL_ENV,0);for(unsigned i=0;i<2;i++)shot("fm-lfo-"+std::to_string(i),FMER_PANEL_LFO,i);
    c.value[FMER_ENGINE]=1;s.engine=1;s.patch_name="VA SAW";c.value[FMER_VA_WAVE]=1;s.va_wave=1;
    shot("va-edit",FMER_PANEL_EDIT,0);shot("va-env",FMER_PANEL_ENV,0);shot("va-lfo",FMER_PANEL_LFO,0);
    c.value[FMER_ENGINE]=0;s.engine=0;s.patch_name="FM KEYS";
    for(unsigned i=0;i<4;i++)shot("fx-"+std::to_string(i),FMER_PANEL_FX,i);
    p.focused_id=FMER_PHASER;shot("phaser",FMER_PANEL_FX,1);p.focused_id=FMER_PANEL_INVALID;
    for(unsigned i=0;i<3;i++){c.value[FMER_FILTER_TYPE]=i;shot("filter-"+std::to_string(i),FMER_PANEL_FX,0);}c.value[FMER_FILTER_TYPE]=0;
    c.value[FMER_DELAY_SYNC]=3;pattern.delay_ms=fmer_delay_time(3,375,500000);shot("delay-sync",FMER_PANEL_FX,2);c.value[FMER_DELAY_SYNC]=0;
    for(unsigned i=0;i<2;i++)shot("arp-"+std::to_string(i),FMER_PANEL_ARP,i);
    for(unsigned i=0;i<10;i++)shot("glo-"+std::to_string(i),FMER_PANEL_GLO,i);
    shot("presets",FMER_PANEL_PRESETS,0);shot("save-instrument",FMER_PANEL_SAVE,0);p.save_scope=1;shot("save-project",FMER_PANEL_SAVE,0);p.save_scope=0;
    c.value[FMER_GLIDE_MODE]=1;c.value[FMER_GLIDE_MS]=180;c.value[FMER_VOICE_BUDGET]=1;s.voice_limit=1;shot("mono-glide",FMER_PANEL_GLO,FMER_GLO_GLIDE);
    c.value[FMER_GLIDE_MODE]=0;c.value[FMER_VOICE_BUDGET]=4;s.voice_limit=4;
    shot("single-song",FMER_PANEL_SEQ,8);p.scope_only=1;shot("scope",FMER_PANEL_HOME,0);p.scope_only=0;
    c.value[FMER_SEQ_MODE]=1;pattern.mode=1;s.performance.running=1;
    for(unsigned i=0;i<9;i++)shot("seq-"+std::to_string(i),FMER_PANEL_SEQ,i);
    p.song_layer=1;shot("song-setup",FMER_PANEL_SEQ,8);p.song_layer=0;
    shot("home-4t",FMER_PANEL_HOME,0);p.scope_only=1;shot("scope-4t",FMER_PANEL_HOME,0);
    std::puts("Production734 renderer captures complete; no hardware access.");return 0;
}
