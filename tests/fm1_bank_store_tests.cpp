// Reuse the NOR fault simulator; no device or flash access.
#include "../firmware/fm1/bank_store.h"
#include "../firmware/fm1/dsp_adapter.h"
#define main legacy_journal_main
#include "fm1_preset_store_tests.cpp"
#undef main
using Wire=std::array<uint8_t,FMER_NATIVE_BYTES>;
static Wire original(unsigned slot){Wire w{};check(fmer_dsp_original_default(slot,w.data()),"original profile encodes");return w;}
static void bank_mount(fmer_bank_t& b,fmer_store_t& s,Nor& nor){auto r=mount(s,nor);check(r==0||r==FMER_STORE_FOREIGN,"journal mounts");check(fmer_bank_mount(&b,&s)==0,"bank mounts");}
static Wire load(fmer_bank_t& b,fmer_store_t& s,unsigned slot){Wire w{};check(!fmer_bank_load(&b,&s,slot,w.data(),fmer_dsp_original_default),"sound load");return w;}
static Wire project(fmer_bank_t& b,fmer_store_t& s,unsigned slot){Wire w{};check(!fmer_bank_project_load(&b,&s,slot,w.data()),"project load");return w;}
static Wire sound(const Wire& w){std::array<uint8_t,FMER_BANK_SOUND> p{};Wire out{};fmer_bank_sound_pack(w.data(),p.data());check(fmer_bank_sound_unpack(p.data(),out.data()),"sound projection valid");return out;}
static std::array<uint8_t,FMER_BANK_PAIR_V3> legacy_pair(const Wire& a,const Wire& b,unsigned group){
 std::array<uint8_t,FMER_BANK_PAIR_V3> p{};std::memcpy(p.data(),"FMERPAIR",8);p[8]=3;p[9]=(uint8_t)group;p[10]=3;p[11]=1;
 const Wire* words[]={&a,&b};
 for(unsigned side=0;side<2;side++){
  std::array<uint8_t,2176> old{};std::copy_n(words[side]->begin(),2127,old.begin());std::memcpy(old.data(),"FMERNAT4",8);
  fmer_native_wr16(old.data()+32+FMER_VA_WAVE*2,std::min<uint16_t>(3,fmer_native_rd16(old.data()+32+FMER_VA_WAVE*2)));
  fmer_native_wr16(old.data()+32+FMER_ARP_ORDER*2,std::min<uint16_t>(9,fmer_native_rd16(old.data()+32+FMER_ARP_ORDER*2)));
  fmer_native_wr16(old.data()+32+FMER_VOICE_BUDGET*2,4);
  fmer_native_wr16(old.data()+32+FMER_DELAY_SYNC*2,0);
  fmer_native_wr16(old.data()+32+FMER_REVERB_MODEL*2,std::min<uint16_t>(1,fmer_native_rd16(old.data()+32+FMER_REVERB_MODEL*2)));
  fmer_native_wr16(old.data()+8,4);fmer_native_wr16(old.data()+12,2176);old[26]=8;std::memcpy(old.data()+2127,"TRK1",4);
  for(unsigned t=0;t<4;t++){auto src=words[side]->data()+FMER_NATIVE_PADDING+4+6*t;auto dst=old.data()+2131+5*t;dst[0]=src[0];dst[1]=src[1];dst[2]=src[3];dst[3]=src[4];dst[4]=src[5];}
  fmer_native_wr32(old.data()+28,fmer_native_crc_n(old.data(),old.size()));check(!fmer_native_validate(old.data(),old.size()),"genuine719 legacy fixture");
  auto out=p.data()+32+side*1758;std::memcpy(out,old.data(),32);std::memcpy(out+32,old.data()+428,155);std::memcpy(out+187,old.data()+352,76);
  std::memcpy(out+1679,old.data()+322,30);std::memcpy(out+1709,old.data()+2127,49);
  for(unsigned k=0;k<8;k++){auto src=old.data()+583+k*193;auto dst=out+263+k*177;*dst++=*src++;unsigned bit=0;
   for(unsigned i=0;i<192;i++){auto width=i%3?7u:8u;for(unsigned j=0;j<width;j++,bit++)dst[bit/8]|=((src[i]>>j)&1)<<(bit%8);}}
 }
 return p;
}
static void relocate_current_to_last(Nor& nor,fmer_bank_t& b,fmer_store_t& s,unsigned id){
 const auto from=fmer_store_address(s.slot[id].cell),to=fmer_store_address(FMER_STORE_CELLS-1);
 std::copy_n(nor.bytes.begin()+from,4096,nor.bytes.begin()+to);fmer_store_owner(FMER_STORE_CELLS-1,nor.bytes.data()+to);
 std::fill_n(nor.bytes.begin()+from,4096,255);bank_mount(b,s,nor);check(s.cursor==0,"fault cursor targets obsolete sector");
}
int main(int argc,char** argv){
 {auto w=original(0);w[FMER_NATIVE_PADDING+38]=3;w[FMER_NATIVE_PADDING+39]=2;fmer_native_wr32(w.data()+28,fmer_native_crc(w.data()));
  auto recalled=sound(w);check(recalled[FMER_NATIVE_PADDING+38]==3 && recalled[FMER_NATIVE_PADDING+39]==2,"compact instrument preserves modulation recipes");}
 if(argc==4 && !std::strcmp(argv[1],"--migrate")){
  Wire input{},output{};std::array<uint8_t,FMER_BANK_COMPACT> packed{};
  FILE* file=std::fopen(argv[2],"rb");check(file!=nullptr,"open legacy project");auto bytes=std::fread(input.data(),1,input.size(),file);check(bytes==FMER_NATIVE_BYTES || bytes==FMER_NATIVE_V9_BYTES,"read complete legacy project");std::fclose(file);
  check(!fmer_native_validate(input.data(),bytes),"validate legacy project before compacting");
  fmer_bank_pack(input.data(),packed.data());check(fmer_bank_unpack(packed.data(),output.data()),"compact migration valid");
  file=std::fopen(argv[3],"wb");check(file&&std::fwrite(output.data(),1,output.size(),file)==output.size(),"write complete migrated project");std::fclose(file);return 0;
 }
 Nor nor;fmer_store_t s{};fmer_bank_t b{};std::array<Wire,64> originals{};
 for(unsigned i=0;i<64;i++){originals[i]=original(i);std::array<uint8_t,FMER_BANK_COMPACT> p{};Wire out{};fmer_bank_pack(originals[i].data(),p.data());check(fmer_bank_unpack(p.data(),out.data())&&out==originals[i],"all64 complete originals compact exactly");}
 if(argc==2){FILE* f=std::fopen(argv[1],"wb");check(f!=nullptr,"open cross-language fixture");for(const auto& w:originals)check(std::fwrite(w.data(),1,w.size(),f)==w.size(),"write fixture");check(!std::fclose(f),"close fixture");}
 auto st=fmer_native_state_t{};check(!fmer_native_decode(originals[0].data(),FMER_NATIVE_BYTES,&st),"decode working fixture");
 for(unsigned k=0;k<15;k++){auto& p=st.patterns[k];p.length=(uint8_t)(64-k);for(unsigned i=0;i<64;i++){p.pitch[i]=(uint8_t)((i+k)%3==0?129:(i+k)%3==1?128:i*2);p.velocity[i]=(uint8_t)(i%2?127:1);p.gate[i]=(uint8_t)(i%2?100:1);}}
 st.tracks[0].chain_mask=0xa581;st.tracks[0].pattern=15;st.controls.value[FMER_SEQ_CHAIN_MASK]=65535;st.controls.value[134]=st.vced[134]=7;
 for(unsigned t=0;t<4;t++){st.song.length[t]=32;st.song.enabled[t]=1;st.song.loop[t]=t%2;
  for(unsigned row=0;row<32;row++)st.song.rows[t][row]={static_cast<uint8_t>(row%17),static_cast<int8_t>(int(row%49)-24),static_cast<uint8_t>(row)};}
 Wire varied{};check(!fmer_native_encode(&st,varied.data(),varied.size()),"all16 varied patterns and full mask encode");
 std::array<uint8_t,FMER_BANK_COMPACT> compact{};Wire out{};fmer_bank_pack(varied.data(),compact.data());check(fmer_bank_unpack(compact.data(),out.data())&&out==varied,"all inactive bits and16bit masks survive");compact[32]^=1;check(!fmer_bank_unpack(compact.data(),out.data()),"inner CRC rejects corrupted project");
 const auto varied_sound=sound(varied);check(fmer_bank_sound_equal(varied.data(),varied_sound.data()),"instrument projection preserves every sound control incl algorithm");
 for(unsigned i=0;i<6;i++)nor.bytes[fmer_store_address(i)]=0;bank_mount(b,s,nor);check(b.layout==3&&s.foreign_cells==6,"blank usable layout keeps six foreign sectors");
 fmer_midi_settings_t midi{{3,9,1,2,0,1,1,0}};check(!fmer_bank_save_midi(&b,&s,&midi),"global MIDI persists");
 for(unsigned i=0;i<128;i++)check(!fmer_bank_save(&b,&s,i,varied.data()),"128 sound destinations fit");
 for(unsigned i=0;i<16;i++)check(!fmer_bank_project_save(&b,&s,i,varied.data()),"16 independent complete projects fit");
 check(s.valid_slots==33,"only33 current sectors needed for full catalog");bank_mount(b,s,nor);
 check(s.valid_slots==33&&b.latest_project==15&&b.latest_slot==127,"full reboot inventory");
 for(unsigned i=0;i<128;i++)check(load(b,s,i)==varied_sound,"all sounds retain only declared instrument scope");
 for(unsigned i=0;i<16;i++)check(project(b,s,i)==varied,"all projects retain every full snapshot byte");
 check(!fmer_bank_reset(&b,&s,3),"reset only default bank");for(unsigned i=0;i<64;i++){check(load(b,s,i)==varied_sound,"default reset keeps USER");check(load(b,s,i+64)==originals[i],"default reset restores originals");}
 check(project(b,s,15)==varied,"default reset retains project");check(!fmer_bank_save(&b,&s,64,varied.data()),"edited DEFAULT saves");check(!fmer_bank_reset(&b,&s,4),"USER copies reset");check(load(b,s,0)==originals[0]&&load(b,s,64)==varied_sound,"USER fallback independent of edited DEFAULT");
 check(!fmer_bank_reset(&b,&s,5),"clear USER");check(fmer_bank_load(&b,&s,0,out.data(),fmer_dsp_original_default)==FMER_STORE_EMPTY,"clear leaves empty");check(!fmer_bank_save(&b,&s,7,varied.data()),"save into final peer");check(fmer_bank_load(&b,&s,0,out.data(),fmer_dsp_original_default)==FMER_STORE_EMPTY,"empty peer stays empty");
 check(!fmer_bank_reset_projects(&b,&s),"clear projects separately");check(fmer_bank_project_load(&b,&s,15,out.data())==FMER_STORE_EMPTY&&load(b,s,7)==varied_sound&&load(b,s,64)==varied_sound,"project clear preserves both sound banks");check(!std::memcmp(&b.midi,&midi,sizeof midi),"all resets retain MIDI");
 for(unsigned i=0;i<180;i++){check(!fmer_bank_save(&b,&s,i%128,varied.data()),"sound sector rotation");check(!fmer_bank_project_save(&b,&s,i%16,varied.data()),"project sector rotation");}
 protected_unchanged(nor);
 // Atomic failure matrix includes blank and reclaimed targets, all8 sound peers,
 // a sixteen-pattern project, independent reset scopes and saved MIDI.
 Nor seed;bank_mount(b,s,seed);check(!fmer_bank_save(&b,&s,0,varied.data()),"fault baseline");check(!fmer_bank_save(&b,&s,7,originals[7].data()),"fault last peer");check(!fmer_bank_project_save(&b,&s,0,varied.data()),"fault project baseline");
 for(unsigned reclaim:{0u,1u}){
  if(reclaim){bank_mount(b,s,seed);check(!fmer_bank_project_save(&b,&s,0,varied.data()),"prime reclaim");relocate_current_to_last(seed,b,s,16);}
  for(unsigned action:{1u,4u,5u,6u,8u,10u}){
   auto mutate=[&](fmer_bank_t& bank,fmer_store_t& store){return action==1?fmer_bank_save(&bank,&store,0,originals[2].data()):action==6?fmer_bank_save_midi(&bank,&store,&midi):action==8?fmer_bank_project_save(&bank,&store,0,originals[2].data()):action==10?fmer_bank_reset_projects(&bank,&store):fmer_bank_reset(&bank,&store,action);};
   Nor probe=seed;bank_mount(b,s,probe);probe.mutations=0;check(!mutate(b,s),"fault length probe");
   for(unsigned cut=0;cut<=probe.mutations;cut++){
    Nor trial=seed;bank_mount(b,s,trial);trial.remaining=cut;auto result=mutate(b,s);trial.remaining=-1;bank_mount(b,s,trial);++interruptions;
    auto lr=fmer_bank_load(&b,&s,0,out.data(),fmer_dsp_original_default);
    if(action==1){check(!lr&&(out==varied_sound||out==sound(originals[2])),"sound old or new");check(load(b,s,7)==sound(originals[7]),"eighth peer never lost");if(!result)check(out==sound(originals[2]),"acknowledged sound is new");}
    else if(action==4)check(!lr&&(out==varied_sound||out==originals[0]),"USER reset complete old/new");
    else if(action==5)check(lr==FMER_STORE_EMPTY||(!lr&&out==varied_sound),"USER clear complete old/empty");
    else check(!lr&&out==varied_sound,"project/MIDI mutation preserves sound");
    auto pr=fmer_bank_project_load(&b,&s,0,out.data());
    if(action==8){check(!pr&&(out==varied||out==originals[2]),"project old/new all16 patterns");if(!result)check(out==originals[2],"acknowledged project durable");}
    else if(action==10)check(pr==FMER_STORE_EMPTY||(!pr&&out==varied),"project reset all-old/all-empty");
    else check(!pr&&out==varied,"sound/MIDI resets preserve project");
    check(load(b,s,64)==originals[0],"USER/project/MIDI never changes DEFAULT");
    if(action==6){fmer_midi_settings_t defaults;fmer_midi_defaults(&defaults);check(!std::memcmp(&b.midi,&defaults,sizeof defaults)||!std::memcmp(&b.midi,&midi,sizeof midi),"MIDI old/new atomic");}
   }
  }
 }
 // Legacy v4 remains readable with no implicit writes. One atomic metadata barrier
 // switches to defaults+empty projects; all65old records can then be reclaimed.
 Nor old;for(unsigned cell=67;cell<73;cell++)old.bytes[fmer_store_address(cell)]=0;bank_mount(b,s,old);for(unsigned g=0;g<64;g++){auto p=legacy_pair(originals[(2*g)%64],originals[(2*g+1)%64],g);check(!fmer_store_save(&s,g,p.data(),p.size()),"seed full719 catalog");}
 uint8_t meta[32]={0};std::memcpy(meta,"FMERBNK2",8);meta[17]=1;std::memcpy(meta+18,midi.value,8);check(!fmer_store_save(&s,64,meta,32),"legacy MIDI metadata");
 auto legacy_expected=originals[63];fmer_native_wr16(legacy_expected.data()+32+FMER_VOICE_BUDGET*2,4);fmer_native_wr16(legacy_expected.data()+32+FMER_DELAY_SYNC*2,0);fmer_native_wr16(legacy_expected.data()+32+FMER_REVERB_MODEL*2,std::min<uint16_t>(1,fmer_native_rd16(legacy_expected.data()+32+FMER_REVERB_MODEL*2)));legacy_expected[FMER_NATIVE_PADDING+38]=legacy_expected[FMER_NATIVE_PADDING+39]=0;fmer_native_wr16(legacy_expected.data()+32+FMER_RECORD_MODE*2,2);fmer_native_wr32(legacy_expected.data()+28,fmer_native_crc(legacy_expected.data()));
 bank_mount(b,s,old);const auto before=old.bytes;check(b.layout==2&&load(b,s,127)==legacy_expected,"legacy entire snapshot decoded to16patterns");check(fmer_bank_save(&b,&s,0,varied.data())==FMER_STORE_NOT_READY&&old.bytes==before,"legacy remains read-only until explicit initialization");
 Nor probe=old;bank_mount(b,s,probe);probe.mutations=0;check(!fmer_bank_initialize(&b,&s),"layout initialization probe");
 for(unsigned cut=0;cut<=probe.mutations;cut++){
  Nor trial=old;bank_mount(b,s,trial);trial.remaining=cut;auto result=fmer_bank_initialize(&b,&s);trial.remaining=-1;bank_mount(b,s,trial);++interruptions;
  check(b.layout==2||b.layout==3,"layout old/new");check(!result?b.layout==3:true,"successful layout durable");check(load(b,s,127)==(b.layout==2?legacy_expected:originals[63]),"legacy exact state or new original available according to layout");check(!std::memcmp(&b.midi,&midi,sizeof midi),"initialization preserves MIDI");
  if(b.layout==3){check(s.valid_slots==1,"old65 record heads released only after barrier");check(fmer_bank_project_load(&b,&s,0,out.data())==FMER_STORE_EMPTY,"new layout has empty projects");}
 }
 bank_mount(b,s,old);check(!fmer_bank_initialize(&b,&s),"initialize actual model");for(unsigned i=0;i<128;i++)check(!fmer_bank_save(&b,&s,i,varied.data()),"repopulate128 after reset");for(unsigned i=0;i<16;i++)check(!fmer_bank_project_save(&b,&s,i,varied.data()),"repopulate16projects after reset");bank_mount(b,s,old);check(s.valid_slots==33&&project(b,s,15)==varied,"new records survive old-record reclamation");protected_unchanged(old);
 // v2/v3 stored pairs retain exact audible fields and append empty patterns.
 for(unsigned version:{2u,3u}){
  Nor historical;bank_mount(b,s,historical);auto pair=legacy_pair(originals[0],originals[1],0);
  const unsigned width=version==2?1679:1709;std::vector<uint8_t> bytes(32+2*width,0);
  std::copy_n(pair.begin(),32,bytes.begin());bytes[8]=(uint8_t)(version-1);
  for(unsigned side=0;side<2;side++){
   auto *in=pair.data()+32+side*1758;Wire oldwire{};check(fmer_bank_legacy_unpack(in,oldwire.data()),"v4 legacy compaction reference");
   std::array<uint8_t,2176> oldraw{};std::copy_n(oldwire.begin(),2127,oldraw.begin());std::memcpy(oldraw.data(),version==2?"FMERNAT2":"FMERNAT3",8);fmer_native_wr16(oldraw.data()+8,(uint16_t)version);fmer_native_wr16(oldraw.data()+12,2176);oldraw[26]=8;
   std::memset(oldraw.data()+32+(version==2?145:150)*2,0,version==2?30:20);fmer_native_wr32(oldraw.data()+28,fmer_native_crc_n(oldraw.data(),2176));
   std::copy_n(in,width,bytes.data()+32+side*width);auto *dst=bytes.data()+32+side*width;std::copy_n(oldraw.begin(),32,dst);if(version==3)std::copy_n(oldraw.begin()+322,30,dst+1679);
   check(!fmer_native_decode(oldraw.data(),2176,&st),"strict historical file decodes");Wire expected{};check(!fmer_native_encode(&st,expected.data(),expected.size()),"historical expected v5 encodes");
   Wire actual{};check(fmer_bank_legacy_unpack(dst,actual.data())&&actual==expected,"small-stack in-place v2/v3 migration equals full decoder");
  }
  check(!fmer_store_save(&s,0,bytes.data(),(uint32_t)bytes.size()),"historical pair seeds");bank_mount(b,s,historical);const auto before_read=historical.bytes;check(b.layout==2,"historical layout remains read-only");(void)load(b,s,0);(void)load(b,s,1);check(before_read==historical.bytes,"historical migration has no flash side effects");
 }
 // Personal FX default survives remount and every interrupted metadata write.
 Nor defaults_nor;bank_mount(b,s,defaults_nor);
 check(!fmer_bank_save_midi(&b,&s,&midi),"seed independent MIDI settings");
 check(!fmer_bank_save(&b,&s,7,varied.data()),"seed sound before FX default");
 check(!fmer_bank_project_save(&b,&s,3,varied.data()),"seed project before FX default");
 const auto saved_sound=load(b,s,7);const auto saved_project=project(b,s,3);
 const auto pristine_defaults=defaults_nor;
 for(int cut=0;cut<4400;cut++) {
  Nor trial=pristine_defaults;bank_mount(b,s,trial);trial.remaining=cut;
  fmer_bank_save_fx_default(&b,&s,719);trial.remaining=-1;bank_mount(b,s,trial);++interruptions;
  check(b.fx_default==0 || b.fx_default==719,"interrupted default is wholly old or new");
  check(!std::memcmp(&b.midi,&midi,sizeof midi),"default transaction preserves MIDI");
  check(load(b,s,7)==saved_sound && project(b,s,3)==saved_project,"default transaction preserves all owner records");
 }
 bank_mount(b,s,defaults_nor);check(!fmer_bank_save_fx_default(&b,&s,719),"personal default commits");bank_mount(b,s,defaults_nor);
 check(b.fx_default==719,"personal default survives boot mount");
 check(!fmer_bank_save_midi(&b,&s,&midi) && b.fx_default==719,"MIDI save preserves personal default");
 check(fmer_bank_save_fx_default(&b,&s,720)==FMER_STORE_ARGUMENT,"invalid default rejected");
 check(!fmer_bank_save_fx_default(&b,&s,0) && b.fx_default==0,"original routing restore commits");
 check(load(b,s,7)==saved_sound && project(b,s,3)==saved_project,"original routing reset leaves music intact");
 // The FX permutation belongs to the sound and the project, without growth.
 auto fxwire=originals[2];fmer_native_wr16(fxwire.data()+FMER_NATIVE_PADDING+32,719);fmer_native_wr32(fxwire.data()+28,fmer_native_crc(fxwire.data()));
 check(!fmer_native_validate(fxwire.data(),fxwire.size()),"nondefault FX chain validates");
 auto fxsound=sound(fxwire);check(fmer_native_rd16(fxsound.data()+FMER_NATIVE_PADDING+32)==719,"compact instrument retains FX permutation");
 std::array<uint8_t,FMER_BANK_COMPACT> fxpacked{};Wire fxround{};fmer_bank_pack(fxwire.data(),fxpacked.data());
 check(fmer_bank_unpack(fxpacked.data(),fxround.data()) && fxround==fxwire,"compact project retains exact FX permutation and CRC");
 check(fmer_native_merge_sound(fxsound.data(),varied.data()) && fmer_native_rd16(fxsound.data()+FMER_NATIVE_PADDING+32)==719,"sound recall preserves its chain while merging arrangement");
 // Explicit load merges current project rather than erasing the arrangement.
 auto merged=sound(originals[2]);check(fmer_native_merge_sound(merged.data(),varied.data()),"sound/project merge");check(!std::memcmp(merged.data()+583,varied.data()+583,FMER_NATIVE_BYTES-583),"merge keeps every pattern/track bit");check(merged[428+134]==originals[2][428+134],"algorithm stays with loaded instrument");
 // Sound-only startup merges the initialized project, preserving the new
 // OVERDUB default instead of treating a canonical empty export as a saved song.
 check(fmer_dsp_init()!=0,"real adapter fresh boot initialization");fmer_native_state_t boot_state{};fmer_dsp_get_native(&boot_state);
 check(boot_state.controls.value[FMER_RECORD_MODE]==1,"fresh standalone record default is overdub");
 Wire fresh_project{};check(!fmer_native_encode(&boot_state,fresh_project.data(),fresh_project.size()),"fresh boot project encodes");
 auto boot_sound=sound(varied);check(fmer_native_rd16(boot_sound.data()+32+FMER_RECORD_MODE*2)==0,"sound interchange empty project is canonical STEP");
 check(fmer_native_merge_sound_slot(boot_sound.data(),fresh_project.data(),31),"sound boot merge assigns selected slot");
 check(fmer_native_rd16(boot_sound.data()+32+FMER_RECORD_MODE*2)==1,"sound-only boot keeps OVERDUB");
 check(boot_sound[FMER_NATIVE_VCED+134]==varied[FMER_NATIVE_VCED+134],"sound boot retains saved per-instrument algorithm");
 check(fmer_native_rd16(boot_sound.data()+32+FMER_TRACK_SOUND*2)==31&&boot_sound[FMER_NATIVE_PADDING+7]==31,"sound boot mirrors assigned slot");
 check(!std::memcmp(boot_sound.data()+FMER_NATIVE_STEPS,fresh_project.data()+FMER_NATIVE_STEPS,16*193),"sound boot keeps initialized sixteen-pattern pool");
 std::printf("PASS %u bank checks, %u byte interruption points;128 sounds+16 projects,16 patterns, scoped epochs, atomic layout reset, protected sectors\n",checks,interruptions);
}
