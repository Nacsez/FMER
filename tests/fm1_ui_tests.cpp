// Offline LCD/DMA mock: no target headers, OS handles or hardware accesses.
#include <array>
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>

static bool ready=true;
static const uint16_t* pending=nullptr;
static size_t pending_count=0;
static std::array<uint16_t,240*24> pending_copy{};
static std::array<uint16_t,240*240> display{};
static std::vector<unsigned> drawn;
static uint64_t transfer_hash=14695981039346656037ull;
static void hash_byte(uint8_t byte) { transfer_hash=(transfer_hash^byte)*1099511628211ull; }
static void require(bool condition,const char* message) {
    if(!condition) { std::fprintf(stderr,"FAIL: %s\n",message); std::exit(1); }
}
static bool mock_ready() { return ready; }
static void mock_sync() {
    require(ready,"sync never blocks on an unfinished DMA");
    if(pending) require(!std::memcmp(pending,pending_copy.data(),pending_count*sizeof(uint16_t)),"pending DMA buffer remains immutable");
    pending=nullptr;
}
static void mock_blit(unsigned x,unsigned y,unsigned w,unsigned h,const uint16_t* pixels) {
    require(!pending,"old DMA synchronized before new submission");
    require(w && h && x+w<=240 && h<=24 && y+h<=240 && y/24==(y+h-1)/24,"one bounded rectangle within a row, never a full-screen clear");
    pending=pixels;pending_count=w*h;std::memcpy(pending_copy.data(),pixels,pending_count*sizeof(uint16_t));
    hash_byte(static_cast<uint8_t>(x));hash_byte(static_cast<uint8_t>(y));
    hash_byte(static_cast<uint8_t>(w));hash_byte(static_cast<uint8_t>(h));
    for(unsigned i=0;i<w*h;i++) { hash_byte(static_cast<uint8_t>(pixels[i]));hash_byte(static_cast<uint8_t>(pixels[i]>>8)); }
    for(unsigned row=0;row<h;row++)std::memcpy(display.data()+(y+row)*240+x,pixels+row*w,w*sizeof(uint16_t));
    drawn.push_back(y/24);
}
#define FMER_UI_CAN_DRAW() mock_ready()
#define FMER_UI_SYNC() mock_sync()
#define FMER_UI_BLIT(x,y,w,h,p) mock_blit(x,y,w,h,p)
#ifdef FMER_UI_REFERENCE_HEADER
#include FMER_UI_REFERENCE_HEADER
#else
#include "../firmware/fm1/ui.h"
#endif

static uint32_t now=0;
static void call(const fmer_ui_state_t& state) {
    const auto before=drawn.size();
    const int result=fmer_ui_service(&state,now);
    require(drawn.size()-before<=1,"service submits at most one row");
    require(static_cast<size_t>(result)==drawn.size()-before,"return reports the actual row submission");
    now+=8;
}
static void settle(const fmer_ui_state_t& state) { for(unsigned i=0;i<32;i++) call(state); }
static std::string text(unsigned row,const fmer_ui_state_t& state) {
    fmer_ui_row_t value{}; fmer_ui_describe(row,&state,&value);return value.first;
}
static void image(const char* name) {
    std::ofstream stream(name,std::ios::binary); stream<<"P6\n240 240\n255\n";
    for(uint16_t pixel:display) {
        pixel=fmer_ui_wire(pixel);
        const unsigned char rgb[]={static_cast<unsigned char>(((pixel>>11)&31)*255/31),
            static_cast<unsigned char>(((pixel>>5)&63)*255/63),static_cast<unsigned char>((pixel&31)*255/31)};
        stream.write(reinterpret_cast<const char*>(rgb),3);
    }
}

static void require_exact_frame(const fmer_ui_state_t& state) {
    mock_sync();
    for(unsigned row=0;row<10;row++) {
        fmer_ui_row_t descriptor{};fmer_ui_describe(row,&state,&descriptor);fmer_ui_render(&descriptor);
        require(!std::memcmp(display.data()+row*24*240,fmer_ui.pixels,sizeof fmer_ui.pixels),
                "cropped DMA display equals complete reference raster, without old trace ghosts");
    }
}

int main(int argc,char** argv) {
    fmer_controls_t controls{}; fmer_panel_t panel;fmer_panel_init(&panel);
    for(unsigned id=0;id<FMER_PARAM_COUNT;id++)controls.value[id]=(uint16_t)fmer_control_min(id);
    controls.value[FMER_CUTOFF]=20000;controls.value[FMER_VA_CUTOFF]=18000;
    controls.value[FMER_VA_WAVE]=1;controls.value[FMER_ATTACK]=5;controls.value[FMER_RELEASE]=200;
    std::array<int16_t,FMER_SCOPE_SAMPLES> scope{};
    fmer_pattern_state_t pattern{};pattern.revision=1;pattern.length=16;
    for(unsigned i=0;i<64;i++){pattern.pitch[i]=i%2?128:static_cast<uint8_t>(60+i%16);pattern.velocity[i]=100;pattern.gate[i]=75;}
    fmer_ui_state_t state{};state.controls=&controls;state.panel=&panel;state.scope=scope.data();
    state.pattern=&pattern;state.build=734;state.gain=256;state.voice_limit=4;state.usb_ready=1;state.render_us=650;
    state.battery_percent=101;
    state.performance.queued_pattern=16;
    state.patch_name="FM KEYS";state.preset_id=0;
    fmer_ui_reset();settle(state);
    require(drawn.size()==10 && fmer_ui.valid==1023,"initial image sends exactly ten strips");
    require(fmer_ui.bytes_sent==115200,"one image worth of initial transfers");
    require(sizeof fmer_ui<15500,"UI and one-bit waveform damage map still use less than15.5KiB");
    const auto initial=drawn.size();settle(state);require(drawn.size()==initial,"unchanged snapshot never redraws");
    require(text(6,state)=="1 FREQ 20000HZ","home macro mapping exact cutoff");
    require(text(7,state)=="2 RESON 0%","HOME uses shared FX resonance");
    require(text(1,state)=="FM KEYS" && text(5,state).empty(),"home shows actual named sound and musical algorithm/voice status without engineering gain data");
    {fmer_ui_row_t header{};fmer_ui_describe(0,&state,&header);
     require(!header.scope[2],"unknown or uncalibrated ADC never becomes a numeric percentage");
     state.battery_valid=1;state.battery_raw=561;fmer_ui_describe(0,&state,&header);
     require(!header.scope[2],"valid raw ADC is distinct from a calibrated percentage model");
     state.battery_percent=73;fmer_ui_describe(0,&state,&header);
     require(header.scope[2]==74,"estimated percentage retains the actual integer value inside the battery icon");
     state.battery_percent=101;state.battery_valid=0;}
    if(argc>1)image((std::string(argv[1])+"-home.ppm").c_str());

    fmer_panel_encoder(&panel,2,-1,&controls,now);drawn.clear();call(state);
    require(drawn.size()==1 && drawn[0]==3,"next service prioritizes edited numeric value");
    require(text(3,state)=="18878 HZ","popup retains actual proportional frequency and units");
    panel.fine_adjust=1;require(text(5,state)=="FINE 1/8 SEMITONE","fine cutoff labels its actual musical step");panel.fine_adjust=0;
    require(fmer_ui_log_position(20)<fmer_ui_log_position(200) && fmer_ui_log_position(200)<fmer_ui_log_position(2000),"logarithmic positions are ordered");
    require(std::abs(static_cast<int>(fmer_ui_log_position(200)-fmer_ui_log_position(20))-
                     static_cast<int>(fmer_ui_log_position(2000)-fmer_ui_log_position(200)))<=1,"decades receive equal visual cutoff travel withinQ10 rounding");
    {fmer_ui_row_t lower{},middle{},upper{};
     controls.value[FMER_CUTOFF]=20;fmer_ui_describe(4,&state,&lower);
     controls.value[FMER_CUTOFF]=632;fmer_ui_describe(4,&state,&middle);
     controls.value[FMER_CUTOFF]=20000;fmer_ui_describe(4,&state,&upper);
     require(lower.amount==0 && upper.amount==upper.maximum,"log cutoff bar retains both exact endpoints");
     require(middle.amount*100/middle.maximum>=49 && middle.amount*100/middle.maximum<=50,"geometric midpoint lies at visual half travel");
     controls.value[FMER_CUTOFF]=18878;}
    settle(state);if(argc>1)image((std::string(argv[1])+"-focus.ppm").c_str());
    const auto prior=display;
    controls.value[FMER_CUTOFF]=20;panel.edited_ms=now;drawn.clear();settle(state);
    require(drawn.size()==3,"one parameter edits value bar and mapped footer only");
    require(std::memcmp(prior.data(),display.data(),240*3*24*2)==0,"other heading pixels preserved");
    for(unsigned y=72;y<96;y++)for(unsigned x=8+5*18;x<232;x++)
        require(display[y*240+x]==fmer_ui_wire(FMER_UI_BG),"shorter value clears only its strip without stale glyphs");

    ready=false;controls.value[FMER_CUTOFF]=20000;panel.edited_ms=now;drawn.clear();
    for(unsigned i=0;i<32;i++)call(state);
    require(drawn.empty(),"busy pixel DMA does not block or submit");
    require(!std::memcmp(pending,pending_copy.data(),sizeof pending_copy),"in-flight buffer unchanged");
    fmer_ui_reset();require(!std::memcmp(pending,pending_copy.data(),sizeof pending_copy),"reset preserves DMA memory");
    ready=true;settle(state);require(drawn.size()==10,"reset progressively redraws after DMA readiness");

    panel.focus_active=0;settle(state);scope.fill(12000);state.scope_generation++;
    now=fmer_ui.last_scope+8;drawn.clear();call(state);require(drawn.empty(),"scope is rate-limited between complete frames");
    now=fmer_ui.last_scope+100;settle(state);
    require(drawn.size()==2,"flat trace updates only old/new ink strips without engineering gain text churn");
    auto audible=display;scope.fill(0);state.scope_generation++;now=fmer_ui.last_scope+100;settle(state);
    require(audible!=display,"oscilloscope pixels are driven by real sample values");
    // Continuous scope updates cannot outrank current control feedback.
    scope.fill(-20000);state.scope_generation++;now=fmer_ui.last_scope+100;
    fmer_panel_encoder(&panel,2,-1,&controls,now);drawn.clear();call(state);
    require(drawn.size()==1 && drawn[0]==3,"edited value outranks simultaneous audio snapshot");

    // Quiet residue stays flat; a real low-level alternating signal becomes
    // visible by a declared display multiplier, without touching the PCM.
    panel.focus_active=0;scope.fill(0);for(unsigned i=0;i<scope.size();i++)scope[i]=i%2?128:-128;
    auto original_pcm=scope;state.scope_generation++;fmer_ui_reset();settle(state);
    require(scope==original_pcm,"scope gain never mutatesaudio samples");
    panel.scope_only=1;state.overruns=7;settle(state);
    for(unsigned row=0;row<10;++row){fmer_ui_row_t r{};fmer_ui_describe(row,&state,&r);
        require(r.bar==2 && r.maximum==240 && !r.first[0],"scope-only covers ten strips with no text");}
    if(argc>1)image((std::string(argv[1])+"-scope-only.ppm").c_str());
    panel.scope_only=0;state.overruns=0;settle(state);
    {fmer_ui_row_t r{};fmer_ui_describe(2,&state,&r);require(r.maximum==96,"normal HOME restores the four-strip scope with mode in the header");}
    require(fmer_ui.scope_gain==256 && text(5,state).empty(),"low level trace uses bounded display gain without crowding artist status");
    require(fmer_ui.scope[0]>180 && fmer_ui.scope[1]<80,"quiet musical waveform spans meaningful screenheight");
    if(argc>1) {
      state.voices=1;
      for(int amplitude:{128,8000,30000}) {
        for(unsigned i=0;i<scope.size();i++){int phase=static_cast<int>(i%32);scope[i]=static_cast<int16_t>((phase<16?phase-8:24-phase)*amplitude/8);}
        state.scope_generation++;fmer_ui_reset();settle(state);
        if(amplitude==8000){panel.scope_only=1;settle(state);image((std::string(argv[1])+"-scope-only.ppm").c_str());panel.scope_only=0;settle(state);}
        image((std::string(argv[1])+(amplitude==128?"-scope-quiet-signal.ppm":amplitude==8000?"-scope-normal.ppm":"-scope-loud.ppm")).c_str());
      }
      state.voices=0;
    }
    scope.fill(32);state.scope_generation++;now=fmer_ui.last_scope+100;settle(state);
    require(fmer_ui.scope_quiet && fmer_ui.scope_gain==1,"noise floor cannot fabricate a largewave");
    for(auto y:fmer_ui.scope)require(y==128,"quiet samples draw a flat centerline");
    for(unsigned i=0;i<scope.size();i++)scope[i]=i%2?32767:-32768;
    state.scope_generation++;now=fmer_ui.last_scope+100;settle(state);
    require(fmer_ui.scope_gain==1 && !fmer_ui.scope_quiet,"large signal immediately removes displayboost");
    for(auto y:fmer_ui.scope)require(y<=2 || y==255,"full signed PCM approaches both full resolution scope bounds");

    // Actual stored pattern, separate selection/playhead, rest and 64-step
    // banks remain visible even while the exact selected value is edited.
    panel.family=FMER_PANEL_SEQ;panel.page[panel.family]=0;panel.focus_active=0;
    controls.value[FMER_SEQ_LENGTH]=16;controls.value[FMER_SEQ_STEP]=2;controls.value[FMER_SEQ_PITCH]=62;
    controls.value[FMER_SEQ_VELOCITY]=100;controls.value[FMER_SEQ_GATE]=75;
    state.performance.running=1;state.performance.seq_position=4;settle(state);
    for(unsigned row=3;row<=5;row++){fmer_ui_row_t r{};fmer_ui_describe(row,&state,&r);
      require(r.bar==3 && r.scope[FMER_GRID_SELECTED]==2 && r.scope[FMER_GRID_PLAYHEAD]==4,"grid separates selectedstep andmovingplayhead");
      require(r.scope[1]==128 && r.scope[2]==62,"grid represents actualrest andpitch fromsnapshot");}
    require(display[73*240+8+2*14+1]==fmer_ui_wire(FMER_UI_PINK),"selectedstep haspinkoutline");
    require(display[74*240+8+4*14+3]==fmer_ui_wire(FMER_UI_GREEN),"playingstep hasgreenmarker");
    const auto grid_before=display;
    fmer_panel_encoder(&panel,3,1,&controls,now);drawn.clear();call(state);
    require(drawn.size()==1 && drawn[0]==2 && text(2,state)=="PITCH 63","sequenceeditvalue is21px andprioritized");
    settle(state);require(!std::memcmp(display.data()+72*240,grid_before.data()+72*240,72*240*2),"focusededit leaves sequencergrid visible");
    if(argc>1){pattern.pitch[2]=63;pattern.revision++;settle(state);image((std::string(argv[1])+"-sequence.ppm").c_str());}
    pattern.length=64;pattern.revision++;controls.value[FMER_SEQ_LENGTH]=64;controls.value[FMER_SEQ_STEP]=63;
    controls.value[FMER_SEQ_PITCH]=FMER_REST;
    panel.focus_active=0;state.performance.seq_position=1;settle(state);
    require(text(1,state).find("P0 48-63 ")==0,"lastbank keeps pattern ID and zero-based step range explicit");
    fmer_ui_row_t lastbank{};fmer_ui_describe(3,&state,&lastbank);
    require(lastbank.scope[FMER_GRID_SELECTED]==15 && lastbank.scope[FMER_GRID_PLAYHEAD]==255 && lastbank.scope[15]==128,"64-step snapshot andoff-bank playhead staybounded");
    require(text(2,state)=="REST","selectedrest keeps exactcanonical readout");
    if(argc>1)image((std::string(argv[1])+"-sequence-bank4.ppm").c_str());
    panel.fine_adjust=1;settle(state);require(text(1,state)=="P0 48-63 FINE","fine gesture staysvisiblymarked withgrid");panel.fine_adjust=0;
    controls.value[FMER_SEQ_PATTERN]=2;state.performance.playing_pattern=1;state.performance.seq_position=63;settle(state);
    fmer_ui_describe(3,&state,&lastbank);require(lastbank.scope[FMER_GRID_PLAYHEAD]==255,"grid never shows another pattern's playback position");
    panel.page[FMER_PANEL_SEQ]=1;controls.value[FMER_SEQ_CHAIN]=1;controls.value[FMER_SEQ_CHAIN_MASK]=0x89;
    state.performance.queued_pattern=2;settle(state);
    require(text(1,state)=="PATTERNS" && text(3,state).empty() && text(5,state)=="E2 PLAY1 NEXT2","pattern overview shows actual chain order and separate edit/play/queued IDs");
    fmer_ui_row_t overview{};fmer_ui_describe(3,&state,&overview);
    require(overview.bar==4 && overview.scope[0]==2 && overview.scope[1]==1 && overview.scope[2]==2 && overview.amount==0x89 && overview.scope_row==0,"overview tiles derive from actual selected, playing, queued and member state");
    require(display[(72+1)*240+8+2*28]==fmer_ui_wire(FMER_UI_PINK),"pattern edit tile has a pink boundary");
    require(display[(72+2)*240+8+1*28+2]==fmer_ui_wire(FMER_UI_GREEN),"playing pattern has a separate green marker");
    require(display[(72+19)*240+8+2*28+2]==fmer_ui_wire(FMER_UI_PURPLE),"queued pattern has a purple marker");
    if(argc>1)image((std::string(argv[1])+"-patterns.ppm").c_str());
    panel.page[FMER_PANEL_SEQ]=2;panel.chain_cursor=7;settle(state);
    require(text(2,state)=="P7 ON" && text(6,state)=="1 PATTERN 7" && text(7,state)=="2 INCLUDE ON" && text(9,state)=="MASK 137 ON","chain editing exposes membership and exact canonical mask");
    if(argc>1)image((std::string(argv[1])+"-chain.ppm").c_str());
    controls.value[FMER_SEQ_PATTERN]=15;controls.value[FMER_SEQ_CHAIN_MASK]=0x9001;
    panel.chain_cursor=15;state.performance.playing_pattern=12;state.performance.queued_pattern=15;settle(state);
    fmer_ui_row_t upper{};fmer_ui_describe(4,&state,&upper);
    require(upper.bar==4 && upper.scope_row==8 && upper.amount==0x9001 && upper.scope[0]==15 && upper.scope[1]==12 && upper.scope[2]==15,
            "upper eight tiles retain all sixteen pattern selection, queue and chain bits");
    require(display[(96+1)*240+8+7*28]==fmer_ui_wire(FMER_UI_PINK) &&
            display[(96+2)*240+8+4*28+2]==fmer_ui_wire(FMER_UI_GREEN) &&
            display[(96+19)*240+8+7*28+2]==fmer_ui_wire(FMER_UI_PURPLE),
            "upper pattern IDs have distinct actual rendered edit, playing and queued markers");
    require(text(5,state)=="E15 PLAY12 NEXT15" && text(9,state)=="MASK 36865 ON","sixteenth pattern and full mask remain exact and legible");
    if(argc>1)image((std::string(argv[1])+"-patterns16.ppm").c_str());
    panel.page[FMER_PANEL_SEQ]=0;controls.value[FMER_SEQ_PATTERN]=0;state.performance.playing_pattern=0;state.performance.queued_pattern=16;
    state.pattern=nullptr;settle(state);require(text(4,state)=="PATTERN PENDING","missingpattern neverinvents notes");state.pattern=&pattern;
    panel.family=FMER_PANEL_ARP;panel.focus_active=0;controls.value[FMER_ARP_ENABLE]=0;state.performance.running=0;settle(state);
    require(text(1,state)=="ARP OFF 1/2" && text(5,state)=="PRESS ARP FOR ON","disabledarp and directenable action stayexplicit");
    fmer_panel_button(&panel,10,&controls,now);settle(state);
    require(text(1,state)=="ARP ON 1/2" && text(5,state)=="ON - HOLD KEYS","enabledemptyarp promptsactualkeys and shows current page");
    if(argc>1)image((std::string(argv[1])+"-arp.ppm").c_str());
    controls.value[FMER_ARP_ORDER]=6;controls.value[FMER_ARP_OCTAVES]=4;state.performance.arp_held=2;
    panel.focus_active=0;settle(state);require(text(5,state)=="MAX 4 VOICES","Repeat exposes the true admission limit without claiming all expanded notes sound");
    if(argc>1)image((std::string(argv[1])+"-arp-capacity.ppm").c_str());
    controls.value[FMER_ARP_ORDER]=0;state.performance.arp_held=0;

    // Exercise actual mapped pages, every min/max, all names and numeric units.
    for(unsigned engine=0;engine<2;engine++)for(unsigned family=0;family<FMER_PANEL_FAMILIES;family++) {
        controls.value[FMER_ENGINE]=(uint16_t)engine;panel.family=family;
        for(unsigned page=0;page<fmer_panel_pages(family,engine);page++) {
            panel.page[family]=page;
            for(unsigned bound=0;bound<2;bound++) {
                for(unsigned id=0;id<FMER_PARAM_COUNT;id++)if(id!=FMER_ENGINE)
                    controls.value[id]=(uint16_t)(bound?fmer_control_max(id):fmer_control_min(id));
                for(unsigned knob=0;knob<4;knob++) {
                    panel.focused_knob=knob;panel.focused_id=fmer_panel_knob_id(&panel,knob,&controls);
                    panel.focus_active=panel.focused_id!=FMER_PANEL_INVALID;panel.edited_ms=now;
                    settle(state);
                    for(unsigned row=0;row<FMER_UI_ROWS;row++) {
                        fmer_ui_row_t value{};fmer_ui_describe(row,&state,&value);
                        require(value.scale>=2 && value.scale<=3,"normal interface never falls back to tiny type");
                        if(std::strlen(value.first)*6*value.scale>224) {
                            std::fprintf(stderr,"overflow: engine%u family%u page%u row%u '%s'\n",engine,family,page,row,value.first);
                            require(false,"mapped readout fits its strip");
                        }
                        require(!value.second[0],"no crowded secondary line");
                        if(std::strstr(value.first,"UNASSIGNED"))std::fprintf(stderr,"UNASSIGNED family%u page%u row%u id%u\n",family,page,row,panel.focused_id);
                        require(std::strstr(value.first,"UNASSIGNED")==nullptr,"inactive controls never masquerade as assignable slots");
                        if(row>=6 && !(family==FMER_PANEL_FX && page==3) && family!=FMER_PANEL_PRESETS && family!=FMER_PANEL_SAVE && !(family==FMER_PANEL_SEQ && (page==2 || page>=6 || (page==4 && controls.value[FMER_SEQ_MODE]))) && !(family==FMER_PANEL_GLO && page>=FMER_GLO_OUTPUT && page<=FMER_GLO_HOTKEYS) &&
                           fmer_panel_knob_id(&panel,row-6,&controls)==FMER_PANEL_INVALID) {
                            if(family==FMER_PANEL_SEQ && page==4 && !controls.value[FMER_SEQ_MODE])
                                require(std::strstr(value.first," LOCK") && !value.bar && value.color==FMER_UI_MUTED,"inactive mixer controls expose stored values with a clear lock instead of false live sliders");
                            else require(!value.first[0],"unassigned contextual control rows remain blank");
                        }
                    }
                }
            }
        }
    }
    panel.family=FMER_PANEL_PRESETS;panel.focus_active=0;panel.preset_bank=1;panel.preset_candidate=15;
    state.candidate_name="VA VIBRA";state.sound_dirty=0;settle(state);
    require(text(2,state)=="VA VIBRA" && text(3,state)=="VA SLOT 15" &&
            text(4,state)=="PRESETS: BROWSE" && text(5,state)=="PLAY KEYS TO HEAR",
            "default browser has named exact ID and instant sound-only scope");
    require(text(6,state)=="1 BANK VA" && text(7,state)==std::string("SELECT MODE ")+fmer_panel_mode_name(&controls) && text(8,state)=="SAVE TO KEEP EDITS" && text(9,state)=="HOME: PLAY / EDIT",
            "instant preset browser labels independent preset/bank and playing mode controls");
    if(argc>1)image((std::string(argv[1])+"-presets.ppm").c_str());
    state.sound_dirty=1;settle(state);
    require(text(5,state)=="PLAY KEYS TO HEAR","instant sound recall keeps its scope explicit even after further sound edits");
    require(text(5,state).size()*12<=224,"dirty sound replacement warning remains fully readable");
    controls.value[FMER_SEQ_MODE]=0;panel.family=FMER_PANEL_HOME;state.preset_id=FMER_NATIVE_CUSTOM_PRESET;state.patch_name="0123456789";settle(state);
    require(text(1,state).find("0123456789")!=std::string::npos && text(1,state).find('+')!=std::string::npos &&
            text(1,state).size()*12<=224,"long custom sound name and edited marker fit without clipping");
    state.patch_name="FM KEYS";state.preset_id=0;state.sound_dirty=0;
    panel.family=FMER_PANEL_SAVE;panel.focus_active=0;panel.save_slot=63;settle(state);
    require(text(2,state)=="USER 63" && text(3,state)=="EMPTY SLOT" && text(5,state)=="STORE NOT READY",
            "SAVE cannot claim persistence before storage mount");
    state.storage_ready=1;state.storage_valid_slots=64;settle(state);
    require(text(5,state)=="SEL CONFIRM SAVE" && text(6,state)=="1 SLOT 63 2 USER" && text(7,state)=="SEL SAVE + STOP",
            "SAVE requires explicit destination confirmation and warns that performance stops");
    state.user_slot_present=1;state.user_slot_name="FM BELL";settle(state);
    require(text(3,state)=="FM BELL" && text(7,state)=="SEL REPLACE + STOP","occupied destination has exact name and replace warning");
    state.storage_action=1;state.storage_slot=63;state.store_busy=1;settle(state);
    require(text(5,state)=="SAVING WAIT","pending flash write never claims saved");
    state.store_busy=0;state.storage_result=0;state.live_generation=state.saved_generation=42;settle(state);
    require(text(5,state)=="SAVED ON DEVICE","successful verified write names actual persistence destination");
    if(argc>1)image((std::string(argv[1])+"-onboard-saved.ppm").c_str());
    state.live_generation=43;settle(state);require(text(5,state)=="SAVED THEN EDITED","post-save edits do not appear captured");
    for(unsigned result=1;result<=12;result++){
        state.storage_result=result;settle(state);
        require(text(5,state).find("SAVED")==std::string::npos,"every error remains distinguishable from save success");
        require(text(5,state).size()*12<=224,"all numeric storage failures fit the status strip");
    }
    state.storage_result=0;state.storage_action=2;settle(state);
    require(text(5,state)=="SEL CONFIRM SAVE","successful load cannot masquerade as a save");
    panel.family=FMER_PANEL_PRESETS;panel.preset_bank=2;panel.preset_candidate=63;state.user_slot_present=0;settle(state);
    require(text(2,state)=="EMPTY" && text(3,state)=="USER SLOT 63" && text(5,state)=="EMPTY - SKIPPED","empty user destination leaves current sound unchanged");
    state.user_slot_present=1;state.candidate_name="FM BELL";settle(state);
    require(text(2,state)=="FM BELL" && text(5,state)=="PLAY KEYS TO HEAR" && text(8,state)=="SAVE TO KEEP EDITS","USER browser is sound-only like DEFAULT; full restore is separate");
    if(argc>1)image((std::string(argv[1])+"-user-presets.ppm").c_str());
    state.storage_action=0;state.user_slot_present=0;state.live_generation=state.saved_generation=0;
    panel.family=FMER_PANEL_GLO;panel.page[panel.family]=2;panel.focus_active=0;panel.focused_knob=0;
    controls.value[FMER_MIDI_CHANNEL]=0;settle(state);
    require(text(3,state)=="OMNI","receive channel zero retains meaningful omni label");
    controls.value[FMER_MIDI_CHANNEL]=16;settle(state);
    require(text(3,state)=="16","last receive channel is exact visible canonical value");
    controls.value[FMER_ENGINE]=0;
    for(unsigned family=0;family<FMER_PANEL_FAMILIES;family++) {
        controls.value[FMER_SEQ_MODE]=family==FMER_PANEL_FX;panel.family=family;if(family==FMER_PANEL_SEQ)panel.page[family]=0;panel.focus_active=0;settle(state);controls.value[134]=0;
        if(family==FMER_PANEL_FX) {
            panel.page[family]=0;controls.value[FMER_FILTER_TYPE]=0;
            fmer_panel_encoder(&panel,1,1,&controls,now);settle(state);
            require(text(1,state).find("FX HP T") == 0,"FX algorithm encoder shows actual filter mode and code");
            require(controls.value[134]==0,"FX mode selection preserves synth algorithm");
            continue;
        }
        fmer_panel_encoder(&panel,1,1,&controls,now);drawn.clear();call(state);
        require(drawn.size()==1,"algorithm overlay retains one strip per service");
        require(text(1,state)=="ALG 2/32 RAW 1","algorithm shows human and exact stored number");
        fmer_ui_row_t diagram{};fmer_ui_describe(3,&state,&diagram);
        require(diagram.bar==7,"every family shows actual routing graph on algorithm change");
        settle(state);
    }
    for(unsigned a=0;a<32;a++) {
        controls.value[134]=a;panel.focused_id=134;panel.focus_active=1;panel.edited_ms=now;
        settle(state);if(argc>1)image((std::string(argv[1])+"-algorithm-"+std::to_string(a+1)+".ppm").c_str());
        const auto prior=drawn.size();settle(state);require(drawn.size()==prior,"unchanged routing doesn't redraw");
    }
    panel.family=FMER_PANEL_GLO;panel.page[panel.family]=FMER_GLO_INFO;
    panel.focus_active=0;
    state.render_us=state.overruns=state.shed=0xffffffffu;now=fmer_ui.last_stats+250;settle(state);
    for(unsigned row=2;row<5;row++)require(text(row,state).size()*12<=224,"saturated diagnostics remain legible");
    panel.family=FMER_PANEL_EDIT;controls.value[FMER_ENGINE]=0;panel.page[panel.family]=3;
    panel.focused_id=136;panel.focus_active=1;panel.edited_ms=now;settle(state);
    require(text(5,state)=="STORED ONLY NO DSP","known unsupported FM field explicitly marked");
    for(unsigned id:{14u,140u}){panel.focused_id=id;panel.edited_ms=now;settle(state);
      require(text(5,state)!="STORED ONLY NO DSP","implemented amplitude modulation is not mislabeled inactive");}
    panel.focused_id=141;panel.edited_ms=now;settle(state);
    require(text(5,state)=="PER NOTE LFO","partial LFO sync phase behavior is not mislabeled stored only");
    state.audio_paused=1;settle(state);require(text(2,state)=="AUDIO PAUSED","pause visibly explained");
    fmer_ui.last_service=0xFFFFFFFCu;fmer_ui.last_stats=0xFFFFFF00u;now=4;
    call(state);require(fmer_ui.last_service==4,"unsigned wraparound scheduling");
    if(argc>1){
        state.audio_paused=0;state.performance.running=0;panel.focus_active=0;panel.focused_knob=0;
        panel.family=FMER_PANEL_FX;panel.page[panel.family]=0;controls.value[FMER_CUTOFF]=1234;
        controls.value[FMER_REVERB]=30;controls.value[FMER_REVERB_DECAY]=50;settle(state);
        state.fx_activity[1]=8000;state.fx_activity[2]=16000;now+=100;settle(state);
        {fmer_ui_row_t r{};fmer_ui_describe(5,&state,&r);require(r.bar==8 && r.scope[1] && r.scope[2] && !r.scope[0],"activity shows measured stages, not knob amounts");}
        image((std::string(argv[1])+"-effects-clean.ppm").c_str());
        panel.fine_adjust=1;settle(state);image((std::string(argv[1])+"-cutoff-fine.ppm").c_str());panel.fine_adjust=0;
        panel.family=FMER_PANEL_ARP;panel.page[panel.family]=0;controls.value[FMER_ARP_ORDER]=2;
        controls.value[FMER_ARP_ENABLE]=1;settle(state);image((std::string(argv[1])+"-arp-exclusive.ppm").c_str());
    }
    panel.family=FMER_PANEL_GLO;panel.page[panel.family]=FMER_GLO_RESET;panel.focus_active=0;
    for(unsigned choice=0;choice<4;choice++)for(unsigned armed=0;armed<2;armed++) {
        panel.reset_choice=choice;panel.reset_armed=armed;settle(state);
        for(unsigned row=0;row<FMER_UI_ROWS;row++){fmer_ui_row_t r{};fmer_ui_describe(row,&state,&r);require(std::strlen(r.first)*6*r.scale<=224,"every reset choice fits readable type");}
    }
    mock_sync();fmer_ui_reset();drawn.clear();fmer_ui_show_splash();
    require(drawn.size()==10 && !pending,"boot splash completes exactly ten bounded DMA strips");
    for(unsigned i=0;i<240*240;i++){
      const unsigned code=(fmer_splash_pixels[i/4]>>(6-2*(i%4)))&3;
      require(display[i]==fmer_ui_wire(fmer_splash_palette[code]),"splash pixel matches packed owner image");
    }
    if(argc>1)image((std::string(argv[1])+"-splash.ppm").c_str());
    now=100;panel.navigation_revision=0;panel.focus_active=0;panel.family=FMER_PANEL_HOME;state.voices=0;
    require(fmer_ui_service(&state,now)==0,"boot logo holds without blocking service");
    now=1200;call(state);require(!fmer_ui.splash,"logo yields to normal UI after1200ms");
    state.audio_paused=state.init_failed=state.overruns=0;panel.family=FMER_PANEL_HOME;panel.scope_only=1;panel.focus_active=0;fmer_ui_reset();
    // A whole coherent frame can progress as fast as completed DMA permits.
    // No elapsed wall time is required between its rows; busy hardware still
    // preserves the in-flight buffer, and each service submits only one row.
    for(unsigned i=0;i<scope.size();i++)scope[i]=i%2?32767:-32768;
    state.scope_generation++;drawn.clear();const auto frame_time=now+100;
    for(unsigned row=0;row<10;row++){
        const auto accepted_generation=fmer_ui.scope_generation;
        require(fmer_ui_service(&state,frame_time)==1 && drawn.back()==row,"full-screen frame drains in top-to-bottom order without per-row software delay");
        if(row)require(fmer_ui.scope_generation==accepted_generation,"all ready-only rows keep the same accepted PCM generation");
        ready=false;state.scope_generation++;
        require(!fmer_ui_service(&state,frame_time),"busy DMA always gates even unthrottled scope service");
        require(!std::memcmp(pending,pending_copy.data(),pending_count*sizeof(uint16_t)),"unthrottled scope never rewrites an in-flight buffer");
        ready=true;
    }
    require(!fmer_ui.scope_rows && !fmer_ui_service(&state,frame_time),"completed full-screen frame returns to paced capture rather than spinning a redraw");
    now=frame_time+8;fmer_ui_reset();
    unsigned complete=0;
    for(unsigned tick=0;tick<160;tick++){
        const auto pending_rows=fmer_ui.scope_rows,view=fmer_ui.scope_view;
        const auto generation=fmer_ui.scope_generation;
        for(unsigned n=0;n<scope.size();n++)scope[n]=static_cast<int16_t>(((n+tick)%32-16)*700);
        state.scope_generation++;call(state);
        if(pending_rows && view==1023)require(fmer_ui.scope_generation==generation,"all strips of a waveform use one immutable generation under continuous input");
        if(!fmer_ui.scope_rows)complete++;
    }
    std::printf("SCOPE_COMPLETIONS %u MASK %u\n",complete,fmer_ui.scope_rows);require(complete>=12,"continuous new audio cannot starve completion of scope frames");
    settle(state);require_exact_frame(state);
    // Controlled small movements cover old/new trace erasure and damage
    // rectangles crossing strip edges. Reference pixels must match exactly.
    uint32_t cropped_bytes=0;
    for(unsigned iteration=0;iteration<12;iteration++) {
        for(unsigned n=0;n<scope.size();n++) {
            int phase=static_cast<int>(n%32);
            scope[n]=static_cast<int16_t>((phase<16?phase-8:24-phase)*2800+static_cast<int>(iteration)*17);
        }
        state.scope_generation++;now=fmer_ui.last_scope+100;
        const auto bytes=fmer_ui.bytes_sent;settle(state);require_exact_frame(state);
        if(iteration)cropped_bytes+=fmer_ui.bytes_sent-bytes;
    }
    require(cropped_bytes<11u*115200u*3u/4u,"small waveform motion transmits under75percent of full frames without a second framebuffer");
    std::printf("SCOPE_DAMAGE_BYTES %u FULL_BYTES %u UI_BYTES %zu\n",cropped_bytes,11u*115200u,sizeof fmer_ui);
    // A 128-point ramp through near-full audio amplitude must not collapse to
    // the old72 vertical positions before being enlarged to240 pixels.
    for(unsigned n=0;n<scope.size();n++)scope[n]=static_cast<int16_t>(-32000+64000*n/(scope.size()-1));
    state.scope_generation++;now=fmer_ui.last_scope+100;settle(state);
    unsigned distinct=1;for(unsigned n=1;n<scope.size();n++)distinct+=fmer_ui.scope[n]!=fmer_ui.scope[n-1];
    std::printf("SCOPE_RAMP_DISTINCT %u GAIN %u FIRST %u LAST %u\n",distinct,fmer_ui.scope_gain,fmer_ui.scope[0],fmer_ui.scope[127]);
    require(distinct==128,"full-screen amplitude keeps all128 distinct ramp samples instead of72 levels");
    require_exact_frame(state);
    uint32_t random=0x719u;
    for(unsigned iteration=0;iteration<32;iteration++) {
        for(auto& sample:scope) {
            random=random*1664525u+1013904223u;
            sample=iteration%8==0?0:static_cast<int16_t>(random>>16);
        }
        state.scope_generation++;now=fmer_ui.last_scope+100;settle(state);require_exact_frame(state);
    }
    panel.scope_only=0;panel.family=FMER_PANEL_ENV;
    for(unsigned engine=0;engine<2;engine++){
        controls.value[FMER_ENGINE]=engine;controls.value[FMER_ATTACK]=1000;for(unsigned op=0;op<6;op++)controls.value[op*21]=80;settle(state);
        for(unsigned row=6;row<10;row++){fmer_ui_row_t r{};fmer_ui_describe(row,&state,&r);require(r.bar==10,"ENV retains four numeric sliders");}
        fmer_ui_row_t before{},after{};fmer_ui_describe(2,&state,&before);
        fmer_panel_encoder(&panel,2,-8,&controls,now);fmer_ui_describe(2,&state,&after);
        require(after.bar==9 && std::memcmp(before.scope,after.scope,10),"envelope graph changes immediately while knob focus is active");
        if(argc>1){settle(state);image((std::string(argv[1])+(engine?"-va-envelope.ppm":"-fm-envelope.ppm")).c_str());}
    }
    panel.family=FMER_PANEL_SEQ;panel.focus_active=0;panel.page[panel.family]=3;
    controls.value[FMER_SEQ_TRACK]=2;controls.value[FMER_SEQ_MODE]=1;controls.value[FMER_TRACK_SOUND]=88;
    controls.value[FMER_TRACK_LEVEL]=60;controls.value[FMER_TRACK_MUTE]=0;
    pattern.mode=1;pattern.track=2;pattern.revision++;state.performance.running=1;
    for(unsigned track=0;track<4;track++) {
        pattern.track_pattern[track]=track;pattern.track_queued[track]=track==2?7:16;
        pattern.track_step[track]=track*17;pattern.track_level[track]=100-track*20;
        pattern.track_length[track]=64;pattern.track_fx[track]=track!=2;pattern.track_mute[track]=track==3;pattern.track_sound[track]=track==1?7:64+track*8;
    }
    pattern.track_sound[2]=88;
    settle(state);
    require(text(1,state)=="PLAY MODE" && text(2,state)=="4T" && text(3,state)=="4 MONO PARTS / T3" && text(6,state)=="1 MODE 4T","mode has its own clear selector and selected track context");
    require(text(5,state)=="4T CHANGE STOPS","mode hint limits transport-stop claim to four-track transitions");
    state.init_failed=1;require(text(2,state)=="DSP FAILED" && text(3,state)=="HOLD PLAY TO RESET","mode screen cannot obscure a DSP initialization failure");state.init_failed=0;
    state.audio_paused=1;require(text(2,state)=="AUDIO PAUSED" && text(3,state)=="HOLD PLAY TO RESET","mode screen preserves protective audio pause feedback");state.audio_paused=0;
    for(unsigned row=7;row<10;row++)require(text(row,state).find(" LOCK")!=std::string::npos,"four-track mode marks mono-only glide settings unavailable");
    if(argc>1)image((std::string(argv[1])+"-tracks.ppm").c_str());
    pattern.track_step[0]=51;
    panel.page[panel.family]=4;settle(state);
    require(text(1,state)=="MIX VOLUME" && text(9,state)=="SEL PLAY: NEXT BAR","performance screen labels its active control layer and direct four-track mapping");
    for(unsigned row=2;row<9;++row){fmer_ui_row_t strip{};fmer_ui_describe(row,&state,&strip);
        require(strip.bar==13 && strip.scope[16]==60 && strip.scope[24]==40 && strip.scope[28]==1,"vertical strips retain actual levels and mute values across immutable render rows");}
    if(argc>1)image((std::string(argv[1])+"-mixer.ppm").c_str());
    // Default SINGLE is a polyphonic sound, outside the four-part mixer. It
    // must never animate dormant lanes or present inactive sliders as live.
    controls.value[FMER_SEQ_MODE]=0;controls.value[FMER_GLIDE_MODE]=0;settle(state);require_exact_frame(state);
    require(text(1,state)=="PERFORM SINGLE" && text(2,state)=="SINGLE: MIXER OFF" &&
            text(3,state)=="K4 MODE -> 4TRK" && text(4,state)=="MODE CHANGE STOPS" && text(5,state)=="THEN PRESS PLAY",
            "default mixer clearly explains explicit activation and stopped transport transition");
    require(text(6,state)=="1 LEVEL 60% LOCK" && text(7,state)=="2 TRACK T3 LOCK" && text(8,state)=="3 MUTE OFF LOCK" && text(9,state)==std::string("4 MODE ")+fmer_panel_mode_name(&controls),
            "inactive controls preserve exact stored values while saying they are locked");
    for(unsigned row=2;row<9;row++){fmer_ui_row_t inactive{};fmer_ui_describe(row,&state,&inactive);
        require(inactive.bar==0,"SINGLE hides all dormant track meters and ineffective sliders despite running transport");
        if(row>=6)require(inactive.color==FMER_UI_MUTED,"locked mixer controls use inactive visual state");}
    if(argc>1)image((std::string(argv[1])+"-mixer-single.ppm").c_str());
    panel.page[panel.family]=3;settle(state);
    require(text(1,state)=="PLAY MODE" && text(2,state)==fmer_panel_mode_name(&controls) && text(6,state)==std::string("1 MODE ")+fmer_panel_mode_name(&controls),
            "mode screen labels actual single-instrument allocation without duplicated patch controls");
    if(argc>1)image((std::string(argv[1])+"-tracks-single.ppm").c_str());
    panel.page[panel.family]=4;require(fmer_panel_encoder(&panel,5,1,&controls,now),"explicit mixer mode turn emits a real canonical edit");
    state.performance.running=0;settle(state);require_exact_frame(state);
    for(unsigned row=2;row<=5;row++){fmer_ui_row_t active{};fmer_ui_describe(row,&state,&active);
        require(active.bar==13 && !active.scope[36],"enabled stopped tracks appear without inventing playback");}
    require(text(9,state)=="SEL PLAY: NEXT BAR","mode edit remains visible without hiding the useful overview behind a popup");
    if(argc>1)image((std::string(argv[1])+"-mixer-ready.ppm").c_str());
    panel.page[panel.family]=5;controls.value[FMER_RECORD_MODE]=1;pattern.count_in=4;pattern.count_in_active=1;state.beat_on=1;settle(state);
    require(text(3,state)=="BEAT 1 / 4" && text(5,state)=="OVERDUB UNTIL REC" && text(6,state)=="1 RECORD OVERDUB","record mode exposes live count-in and quantized one-pass scope");
    if(argc>1)image((std::string(argv[1])+"-record.ppm").c_str());
    for(unsigned seqpage=0;seqpage<6;seqpage++){
        panel.page[panel.family]=seqpage;
        for(unsigned remaining=0;remaining<=4;remaining++){
            pattern.count_in=remaining;state.beat_on=0;settle(state);
            fmer_ui_row_t beat{};fmer_ui_describe(4,&state,&beat);
            require(beat.bar==12 && beat.amount==(remaining?5-remaining:0) && !beat.maximum,
                    "every sequencer page maps audio-owned count-in to the same beat boxes including armed wait");
            require(text(2,state)==(remaining?"COUNT IN":"WAIT FOR CLOCK"),"no first count-in beat appears before its audio event");
            state.beat_on=1;fmer_ui_describe(4,&state,&beat);require(beat.maximum==1,"beat pulse follows audio-owned click state without independent UI timing");
        }
    }
    panel.page[panel.family]=5;pattern.count_in_active=0;pattern.count_in=0;state.beat_on=0;settle(state);
    require(text(4,state)=="OVERDUB LOOPS" && text(5,state)=="REC TO END RECORD","looped overdub tells the performer how to finish");
    controls.value[FMER_RECORD_MODE]=2;settle(state);
    require(text(4,state)=="REPLACE ONE PASS" && text(6,state)=="1 RECORD REPLACE","optional one-pass destructive recording remains named and distinct");
    controls.value[FMER_RECORD_MODE]=1;
    pattern.count_in=pattern.count_in_active=0;
    controls.value[FMER_SEQ_STEP]=0;controls.value[FMER_SEQ_PITCH]=FMER_TIE;panel.page[panel.family]=0;panel.focused_id=FMER_SEQ_PITCH;panel.focus_active=1;panel.edited_ms=now;
    pattern.pitch[0]=60;pattern.pitch[1]=FMER_TIE;settle(state);require(text(2,state)=="TIE","tie editing shows its canonical distinct event code");
    panel.family=FMER_PANEL_GLO;panel.page[panel.family]=FMER_GLO_GLIDE;panel.focus_active=0;controls.value[FMER_GLIDE_MODE]=1;
    controls.value[FMER_GLIDE_MS]=350;controls.value[FMER_GLIDE_CURVE]=2;
    controls.value[FMER_SEQ_MODE]=1;controls.value[FMER_VOICE_BUDGET]=4;settle(state);require_exact_frame(state);
    require(text(3,state)=="4 MONO PARTS" && text(6,state)=="1 GLIDE LEGATO" && text(7,state)=="2 TIME 350MS" && text(9,state)=="4 VOICES 4 LOCK",
            "four-track glide describes mono parts while retaining exact mode, duration and total voice budget");
    require(controls.value[FMER_SEQ_MODE]==1 && controls.value[FMER_VOICE_BUDGET]==4 && controls.value[FMER_GLIDE_CURVE]==2,
            "glide rendering never changes track mode, voice budget or contour");
    if(argc>1)image((std::string(argv[1])+"-glide-four-parts.ppm").c_str());
    controls.value[FMER_SEQ_MODE]=0;settle(state);require_exact_frame(state);
    require(text(3,state)=="GLIDE: AUTO MONO" && text(9,state)=="4 VOICES 4 LOCK",
            "glide explains automatic mono and locks the allocator control");
    if(argc>1)image((std::string(argv[1])+"-glide-single-poly.ppm").c_str());
    controls.value[FMER_VOICE_BUDGET]=1;settle(state);require_exact_frame(state);
    require(text(3,state)=="GLIDE: AUTO MONO" && text(6,state)=="1 GLIDE LEGATO" && text(7,state)=="2 TIME 350MS" && text(9,state)=="4 VOICES 1 LOCK",
            "single mono sound shows glide readiness, semantic mode and exact duration");
    if(argc>1)image((std::string(argv[1])+"-glide.ppm").c_str());
    panel.family=FMER_PANEL_SAVE;panel.save_action=1;state.user_slot_present=1;settle(state);
    require(text(5,state)=="SEL LOAD SOUND" && text(7,state)=="SEL LOAD + STOP" && text(8,state)=="3 ACTION LOAD","explicit full restore is separate from instant sound-only browser");
    if(argc>1)image((std::string(argv[1])+"-restore.ppm").c_str());
    panel.save_scope=1;panel.save_slot=15;panel.save_action=0;state.storage_action=8;state.storage_slot=15;
    state.live_generation=state.saved_generation=300;state.user_slot_name="LIVE SET";settle(state);
    require(text(2,state)=="PROJECT 15" && text(4,state)=="SOUND / SEQ / SONG" && text(5,state)=="SAVED ON DEVICE" && text(6,state)=="1 SLOT 15" && text(9,state)=="4 SCOPE PROJECT",
            "project save clearly separates sixteen-pattern scope and destination from instrument banks");
    for(unsigned row=0;row<10;row++){fmer_ui_row_t r{};fmer_ui_describe(row,&state,&r);require(std::strlen(r.first)*6*r.scale<=224,"project scope fits readable screen rows");}
    if(argc>1)image((std::string(argv[1])+"-project-save.ppm").c_str());
    panel.save_action=1;settle(state);require(text(5,state)=="SEL LOAD PROJECT","project recall remains an explicit scoped action");
    panel.family=FMER_PANEL_GLO;panel.page[panel.family]=FMER_GLO_GLIDE;settle(state);
    require(text(1,state)=="MONO GLIDE 2/10","global heading names its actual musical purpose before its page count");
    panel.page[panel.family]=FMER_GLO_USB_LINK;panel.usb_role=1;state.usb_link_role=1;state.usb_link_state=6;
    settle(state);require_exact_frame(state);require(text(2,state)=="LINK CONNECTED" && text(6,state)=="1 LINK MASTER","USB role and actual connection are separate visible states");
    if(argc>1)image((std::string(argv[1])+"-usb-link.ppm").c_str());
    for(unsigned role=0;role<3;role++)for(unsigned send=0;send<3;send++) {
        panel.usb_role=role;panel.usb_send=send;
        for(unsigned row=0;row<10;row++){fmer_ui_row_t r{};fmer_ui_describe(row,&state,&r);require(std::strlen(r.first)*6*r.scale<=224,"all USB link instructions fit");}
    }
    state.usb_link_role=0;state.usb_link_state=0;
    panel.page[panel.family]=FMER_GLO_INFO;settle(state);require(text(1,state)=="INFO 9/10","information moves behind musical controls");
    panel.page[panel.family]=FMER_GLO_RESET;panel.reset_choice=3;panel.reset_armed=0;settle(state);
    require(text(1,state)=="RESET/CLEAR 10/10" && text(2,state)=="CLEAR PROJECTS" && text(3,state)=="16 EMPTY PROJECTS" && text(4,state)=="SOUNDS UNCHANGED",
            "destructive project clear is last with independent bank preservation visible");
    require(text(5,state)=="1 ACTION  SEL ARM","an earlier project Save never masquerades as successful project Clear");
    state.storage_action=10;settle(state);require(text(5,state)=="RESET COMPLETE","only the matching project clear action reports its completion");
    panel.reset_choice=0;settle(state);require(text(5,state)=="1 ACTION  SEL ARM","project clear completion does not masquerade as default-bank reset completion");
    panel.family=FMER_PANEL_FX;panel.page[panel.family]=3;panel.fx_selected=3;
    state.fx_order=fmer_fx_move(0,3,-6);settle(state);require_exact_frame(state);
    require(text(2,state)=="1 > DISTORTION" && text(3,state)=="2 > FILTER","chain displays actual reordered stages");
    if(argc>1)image((std::string(argv[1])+"-fx-chain.ppm").c_str());
    panel.family=FMER_PANEL_GLO;panel.page[panel.family]=FMER_GLO_LEGEND;settle(state);require_exact_frame(state);
    for(unsigned row=2;row<10;row++){
        unsigned ink=0;for(unsigned y=row*24;y<row*24+24;y++)for(unsigned x=8;x<72;x++)
            ink+=display[y*240+x]!=fmer_ui_wire(FMER_UI_BG);
        require(ink>4,"every legend row draws its symbol beside its label");
    }
    if(argc>1)image((std::string(argv[1])+"-legend.ppm").c_str());

    {auto prior=state;auto oldpanel=panel;auto oldcontrols=controls;auto oldpattern=pattern;
     controls.value[FMER_SEQ_MODE]=1;panel.family=FMER_PANEL_HOME;panel.scope_only=0;panel.focus_active=0;panel.home_layer=FMER_MIX_LEVEL;
     int16_t taps[4][32];for(unsigned t=0;t<4;t++)for(unsigned i=0;i<32;i++)taps[t][i]=static_cast<int16_t>((int(i%8)-4)*500*(t+1));
     state.part_scopes=&taps[0][0];state.scope_generation++;state.pattern=&pattern;pattern.revision++;settle(state);
       require(text(7,state)=="MIX VOLUME","four-track HOME labels layer below five scopes");
       panel.scope_only=1;settle(state);require_exact_frame(state);
       for(unsigned row=0;row<10;row++){fmer_ui_row_t r{};fmer_ui_describe(row,&state,&r);
           require(r.bar==2 && r.maximum==48 && r.scope_row==row%2 && !r.first[0],"four-track fullscreen retains four part traces and master without labels");}
       if(argc>1)image((std::string(argv[1])+"-four-track-fullscreen.ppm").c_str());
       panel.scope_only=0;settle(state);
     fmer_ui_row_t r{};fmer_ui_describe(1,&state,&r);require(r.bar==16 && r.scope[64]==1 && r.scope[65]==2,"HOME first pair belongs to tracks1/2");
     fmer_ui_describe(3,&state,&r);require(r.bar==16 && r.scope[64]==3 && r.scope[65]==4,"HOME second pair belongs to tracks3/4");
     fmer_ui_describe(5,&state,&r);require(r.bar==2 && r.maximum==48,"master scope remains actual mix");
     if(argc>1)image((std::string(argv[1])+"-home-four-tracks.ppm").c_str());
     panel.family=FMER_PANEL_SEQ;panel.page[panel.family]=8;panel.song_row=1;panel.song_track=0;panel.song_layer=0;
     for(unsigned t=0;t<4;t++){pattern.song.length[t]=3;pattern.song.enabled[t]=1;pattern.song_live[t]=0;pattern.song_row[t]=0;
       for(unsigned e=0;e<3;e++)pattern.song.rows[t][e]={static_cast<uint8_t>(t+e),static_cast<int8_t>(e*5),static_cast<uint8_t>(e==0?1:0)};}
     for(auto& length:pattern.pattern_length)length=16;settle(state);
     require(text(7,state)=="2 PATTERN P1" && text(8,state)=="3 TRANSPOSE +5" && text(9,state)=="4 REPEATS 1","song controls reflect selected entry exactly");
     fmer_ui_describe(2,&state,&r);require(r.bar==15 && r.scope[98]==4 && r.scope[0]==0 && r.scope[3]==26,"repeat blocks share actual time scale");
     if(argc>1)image((std::string(argv[1])+"-song.ppm").c_str());
     panel.song_layer=1;settle(state);if(argc>1)image((std::string(argv[1])+"-song-setup.ppm").c_str());
     panel.family=FMER_PANEL_GLO;panel.page[panel.family]=FMER_GLO_HOTKEYS;settle(state);if(argc>1)image((std::string(argv[1])+"-shortcuts.ppm").c_str());
     panel.family=FMER_PANEL_HOME;panel.scope_only=0;state.scope_generation++;settle(state);require(fmer_ui.scope_rows==0,"four-track wave frame drains all six strips");
     auto oldwaves=display;for(unsigned t=0;t<4;t++)for(unsigned i=0;i<32;i++)taps[t][i]=-taps[t][i];state.scope_generation++;settle(state);
     require(fmer_ui.scope_rows==0 && display!=oldwaves,"subsequent PCM generation redraws mini scopes without frozen master mask");
     for(unsigned type=0;type<3;type++){controls.value[FMER_SEQ_MODE]=0;controls.value[FMER_FILTER_TYPE]=type;controls.value[FMER_CUTOFF]=1000;
       panel.family=FMER_PANEL_HOME;panel.focused_id=FMER_CUTOFF;panel.focused_knob=0;panel.focus_active=1;panel.edited_ms=now;settle(state);
       require_exact_frame(state);fmer_ui_describe(6,&state,&r);require(r.scope[60]==type+1,"lower filter shares popup mode");
       fmer_ui_describe(4,&state,&r);require(r.bar==1 && r.scope[60]==type+1,"HOME popup uses identical LP HP BP fill mode");
       if(argc>1)image((std::string(argv[1])+"-home-filter-"+std::to_string(type)+".ppm").c_str());}
     state=prior;panel=oldpanel;controls=oldcontrols;pattern=oldpattern;
    }
    std::printf("UI_TRANSFER_HASH %016llx\n",static_cast<unsigned long long>(transfer_hash));
#ifndef FMER_UI_REFERENCE_HEADER
    // Reviewed734 render stream: all bytes and rectangle positions, including
    // readiness, focus changes, scope damage, menus, grids, bank resets and
    // explicit inactive/active mixer transitions from the SINGLE default,
    // and four-part versus single/poly/mono glide instructions.
    // Screenshot mode additionally exercises poses; its transfer stream differs
    // from the standard no-argument regression run.
    require(transfer_hash==(argc==1?0x0315d77b8cd1b902ull:0x7199bfab3d6d1361ull),"734 reviewed mode navigation, power indication, menus and waveform rendering");
#endif
    // Observable selection borders cover every track, including inactive switches.
    for(unsigned layer : {FMER_MIX_SOUND,FMER_MIX_PATTERN,FMER_MIX_RUN,FMER_MIX_LEVEL,FMER_MIX_MUTE,FMER_MIX_SOLO,FMER_MIX_FX}){
        fmer_ui_row_t selected{};selected.bar=13;selected.amount=layer;
        unsigned y=layer==FMER_MIX_SOUND?21:layer==FMER_MIX_PATTERN?41:layer==FMER_MIX_RUN?59:layer==FMER_MIX_LEVEL?80:121;
        unsigned dx=layer==FMER_MIX_SOLO?17:layer==FMER_MIX_FX?34:0;
        selected.scope_row=(uint8_t)(y/24);mock_sync();fmer_ui_render(&selected);
        for(unsigned t=0;t<4;t++)require(fmer_ui.pixels[(y%24)*240+8+57*t+dx]==fmer_ui_wire(FMER_UI_PINK),"active mixer cell outlined on all four tracks");
    }
    {fmer_ui_row_t focused{};focused.highlight=1;focused.scale=2;fmer_ui_text(focused.first,"FOCUSED");mock_sync();fmer_ui_render(&focused);
     require(fmer_ui.pixels[6]==fmer_ui_wire(FMER_UI_PINK)&&fmer_ui.pixels[23*240+233]==fmer_ui_wire(FMER_UI_PINK),"menu focus has full width outline");}
    panel.family=FMER_PANEL_GLO;panel.page[panel.family]=FMER_GLO_VOICE;panel.focus_active=0;
    controls.value[FMER_SEQ_MODE]=1;controls.value[FMER_VOICE_BUDGET]=4;panel.focused_knob=0;settle(state);require_exact_frame(state);
    require(text(5,state)=="1 VOICE PER TRACK" && text(6,state)=="1 MODE 4T", "Global explains total-versus-per-track budget and exposes mode");
    if(argc>1)image((std::string(argv[1])+"-global-mode.ppm").c_str());

    panel.family=FMER_PANEL_GLO;panel.focus_active=0;state.storage_action=0;state.battery_valid=1;state.battery_percent=64;
    for(unsigned page=FMER_GLO_OUTPUT;page<=FMER_GLO_CLOCK;page++){
        panel.page[panel.family]=page;
        for(unsigned id=0;id<8;id++)for(unsigned value=0;value<=fmer_midi_setting_max(id);value++){
            panel.midi.value[id]=(uint8_t)value;
            for(unsigned row=0;row<10;row++){fmer_ui_row_t r{};fmer_ui_describe(row,&state,&r);if(std::strlen(r.first)*6*r.scale>224)std::fprintf(stderr,"MIDI overflow page%u id%u value%u row%u scale%u text=%s\n",page,id,value,row,r.scale,r.first);require(std::strlen(r.first)*6*r.scale<=224,"all MIDI routing and channel values fit");}
        }
        settle(state);if(argc>1)image((std::string(argv[1])+(page==FMER_GLO_OUTPUT?"-midi-output.ppm":"-midi-clock.ppm")).c_str());
    }
    for(unsigned plugged:{0u,1u})for(unsigned percent:{0u,9u,10u,64u,100u,101u}){
        fmer_ui_row_t header{};header.bar=6;header.scope[2]=percent<=100?percent+1:0;
        header.scope[3]=(uint8_t)plugged;const auto expected=fmer_ui_wire(percent<10?FMER_UI_PINK:plugged?FMER_UI_GREEN:FMER_UI_INK);
        mock_sync();fmer_ui_render(&header);
        require(fmer_ui.pixels[2*240+(percent==100?180:percent<10?204:192)]==expected &&
                fmer_ui.pixels[10*240+235]==expected,"battery fits percentage width with green USB, pink below10%, white detached and low-power priority");
        unsigned ink=0;for(unsigned y=4;y<18;y++)for(unsigned x=180;x<230;x++)
            ink+=fmer_ui.pixels[y*240+x]==expected;
        require(ink>20,"large percentage glyphs remain visible inside outline");
    }
    panel.family=FMER_PANEL_HOME;settle(state);if(argc>1)image((std::string(argv[1])+"-estimated-battery.ppm").c_str());
    std::puts("FMER UI PASS: readable controls, both banks, all reset confirmations, scope, grid, bounds and DMA");
    return 0;
}
