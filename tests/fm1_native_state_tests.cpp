// Exact portable native wire/transaction model; no HAL, allocation or device I/O.
#include "../firmware/fm1/native_state.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
static void check(bool ok,const char *why)
{ if(!ok){std::fprintf(stderr,"FAIL: %s\n",why);std::exit(1);} }
static fmer_native_state_t fixture()
{
 fmer_native_state_t s{};
 for(unsigned i=0;i<FMER_PARAM_COUNT;i++)s.controls.value[i]=(uint16_t)fmer_control_min(i);
 s.controls.value[134]=31;s.controls.value[FMER_SEQ_LENGTH]=64;s.controls.value[FMER_SEQ_STEP]=63;
 s.controls.value[FMER_MIDI_CHANNEL]=16;s.controls.value[FMER_REVERB_DECAY]=100;
 for(unsigned i=0;i<145;i++)s.vced[i]=(uint8_t)s.controls.value[i];
 const uint8_t name[10]={0,127,32,65,66,67,68,69,70,71};std::memcpy(s.vced+145,name,10);
 for(unsigned i=0;i<64;i++){s.pitch[i]=(uint8_t)(i*2);s.velocity[i]=(uint8_t)(i+1);s.gate[i]=(uint8_t)(i%100+1);}
 s.pitch[62]=128;s.controls.value[FMER_SEQ_PITCH]=s.pitch[63];
 s.controls.value[FMER_SEQ_VELOCITY]=s.velocity[63];s.controls.value[FMER_SEQ_GATE]=s.gate[63];
 for(unsigned b=0;b<15;b++){s.patterns[b].length=(uint8_t)(b+1);for(unsigned j=0;j<64;j++){
  s.patterns[b].pitch[j]=(uint8_t)((b*17+j)%129);s.patterns[b].velocity[j]=(uint8_t)(j+1);s.patterns[b].gate[j]=75;}}
 s.source_generation=0xffffffffu;s.preset_id=63;s.length=64;return s;
}
static void fix_crc(uint8_t *bytes)
{ fmer_native_wr32(bytes+28,fmer_native_crc(bytes)); }
int main(int argc,char **argv)
{
 static_assert(FMER_PARAM_COUNT==198,"708 native v2 has exactly198 controls");
 static_assert(FMER_NATIVE_BYTES==4000 && FMER_NATIVE_VCED==428 && FMER_NATIVE_STEPS==583,"708 native v2 offsets");
 auto original=fixture();uint8_t raw[FMER_NATIVE_BYTES],changed[FMER_NATIVE_BYTES],again[FMER_NATIVE_BYTES];
 check(fmer_native_encode(&original,raw,sizeof raw)==FMER_NATIVE_OK,"valid complete record encodes");
 // Independent Python roundtrip validates this fixture, including CRC and all banks.
 if(argc==3 && !std::strcmp(argv[1],"--emit")) {
  auto file=std::fopen(argv[2],"wb");check(file!=nullptr,"open fixture output");
  check(std::fwrite(raw,1,sizeof raw,file)==sizeof raw,"write fixture");std::fclose(file);return 0;
 }
 if(argc==4 && !std::strcmp(argv[1],"--roundtrip")) {
  uint8_t input[FMER_NATIVE_BYTES+1];auto file=std::fopen(argv[2],"rb");check(file!=nullptr,"open fixture input");
  const auto n=std::fread(input,1,sizeof input,file);std::fclose(file);fmer_native_state_t decoded;
  check(fmer_native_decode(input,n,&decoded)==FMER_NATIVE_OK,"cross-language import");
  check(fmer_native_encode(&decoded,raw,sizeof raw)==FMER_NATIVE_OK,"cross-language export");
  file=std::fopen(argv[3],"wb");check(file!=nullptr,"open roundtrip output");
  check(std::fwrite(raw,1,sizeof raw,file)==sizeof raw,"write roundtrip");std::fclose(file);return 0;
 }
 fmer_native_state_t decoded{};
 check(fmer_native_decode(raw,sizeof raw,&decoded)==FMER_NATIVE_OK,"complete record decodes");
 check(!std::memcmp(&decoded,&original,sizeof original),"all controls/name/inactive steps/metadata retained");
 check(fmer_native_encode(&decoded,again,sizeof again)==FMER_NATIVE_OK && !std::memcmp(raw,again,sizeof raw),"exact byte roundtrip");
 for(unsigned i=0;i<sizeof raw;i++)for(unsigned bit=0;bit<8;bit++) {
  std::memcpy(changed,raw,sizeof raw);changed[i]^=(uint8_t)(1u<<bit);
  check(fmer_native_decode(changed,sizeof changed,&decoded)!=FMER_NATIVE_OK,"every single-bit corruption refused");
  check(!std::memcmp(&decoded,&original,sizeof original),"failed decode never partially publishes");
 }
 check(fmer_native_decode(raw,sizeof raw-1,&decoded)==FMER_NATIVE_SIZE,"truncation refused");
 check(fmer_native_decode(raw,sizeof raw+1,&decoded)==FMER_NATIVE_SIZE,"extra bytes refused before read");
 for(unsigned id=159;id<160;id++) {
  std::memcpy(changed,raw,sizeof raw);fmer_native_wr16(changed+32+id*2,8);fix_crc(changed);
  check(fmer_native_validate(changed,sizeof changed)==FMER_NATIVE_CONTROL,"out-of-range delay division with valid CRC refused");
 }
 std::memcpy(changed,raw,sizeof raw);changed[FMER_NATIVE_VCED]=1;fix_crc(changed);
 check(fmer_native_validate(changed,sizeof changed)==FMER_NATIVE_VOICE,"controls/VCED consistency required");
 for(unsigned n=0;n<128;n++) {
  auto named=original;std::memset(named.vced+145,(int)n,10);
  check(fmer_native_encode(&named,changed,sizeof changed)==FMER_NATIVE_OK,"all seven-bit names accepted exactly");
  check(fmer_native_decode(changed,sizeof changed,&decoded)==FMER_NATIVE_OK && decoded.vced[154]==n,"name bytes roundtrip");
 }
 std::memcpy(changed,raw,sizeof raw);changed[FMER_NATIVE_VCED+145]=128;fix_crc(changed);
 check(fmer_native_validate(changed,sizeof changed)==FMER_NATIVE_VOICE,"eight-bit name refused");
 for(unsigned i=40;i<FMER_NATIVE_SONG-FMER_NATIVE_PADDING;i++) {
  std::memcpy(changed,raw,sizeof raw);changed[FMER_NATIVE_PADDING+i]=1;fix_crc(changed);
  check(fmer_native_validate(changed,sizeof changed)==FMER_NATIVE_FORMAT,"all reserved tail bytes checked");
 }
 auto shortened=original;shortened.length=1;shortened.controls.value[FMER_SEQ_LENGTH]=1;
 shortened.controls.value[FMER_SEQ_STEP]=0;shortened.controls.value[FMER_SEQ_PITCH]=shortened.pitch[0];
 shortened.controls.value[FMER_SEQ_VELOCITY]=shortened.velocity[0];shortened.controls.value[FMER_SEQ_GATE]=shortened.gate[0];
 check(fmer_native_encode(&shortened,changed,sizeof changed)==FMER_NATIVE_OK,"inactive trailing steps remain serializable");
 check(fmer_native_decode(changed,sizeof changed,&decoded)==FMER_NATIVE_OK && decoded.pitch[62]==128 && decoded.pitch[63]==126,"short pattern preserves trailing steps");
 for(unsigned field=0;field<3;field++) {
  auto invalid=shortened;if(field==0)invalid.pitch[63]=130;if(field==1)invalid.velocity[63]=0;if(field==2)invalid.gate[63]=101;
  std::memset(changed,0xa5,sizeof changed);
  check(fmer_native_encode(&invalid,changed,sizeof changed)==FMER_NATIVE_PATTERN,"invalid inactive step refused");
  for(auto byte:changed)check(byte==0xa5,"failed encode does not partially replace output");
 }
 for(unsigned id=0;id<FMER_PARAM_COUNT;id++) {
  auto invalid=original;invalid.controls.value[id]=(uint16_t)(fmer_control_max(id)+1);
  if(id<145)invalid.vced[id]=(uint8_t)invalid.controls.value[id];
  check(fmer_native_state_valid(&invalid)!=FMER_NATIVE_OK,"all upper boundaries reject successor");
 }
 for(unsigned id=0;id<64;id++){auto s=original;s.preset_id=(uint16_t)id;check(fmer_native_state_valid(&s)==FMER_NATIVE_OK,"all factory IDs");}
 auto metadata=original;metadata.preset_id=FMER_NATIVE_CUSTOM_PRESET;
 check(fmer_native_state_valid(&metadata)==FMER_NATIVE_OK,"custom preset allowed");metadata.preset_id=64;
 check(fmer_native_state_valid(&metadata)==FMER_NATIVE_METADATA,"undefined preset metadata refused");
 fmer_native_transfer_t tx{};
 check(fmer_native_transfer_begin(&tx,0,9,FMER_NATIVE_BYTES)==FMER_NATIVE_ARGUMENT,"transaction ID zero refused");
 check(fmer_native_transfer_begin(&tx,42,9,FMER_NATIVE_BYTES-1)==FMER_NATIVE_SIZE,"wrong transfer size refused");
 check(fmer_native_transfer_begin(&tx,42,9,FMER_NATIVE_BYTES)==FMER_NATIVE_OK,"transaction begins");
 check(fmer_native_transfer_begin(&tx,43,9,FMER_NATIVE_BYTES)==FMER_NATIVE_BUSY,"unrelated transaction cannot discard inflight bytes");
 check(fmer_native_transfer_ready(&tx,42,9)==FMER_NATIVE_INCOMPLETE,"partial transaction cannot commit");
 check(fmer_native_transfer_chunk(&tx,43,0,raw,64)==FMER_NATIVE_TRANSACTION,"wrong owner refused");
 check(fmer_native_transfer_chunk(&tx,42,1,raw,64)==FMER_NATIVE_ORDER,"out of order chunk refused");
 check(fmer_native_transfer_chunk(&tx,42,0,raw,65)==FMER_NATIVE_SIZE,"oversized chunk refused");
 check(fmer_native_transfer_chunk(&tx,42,0,raw,0)==FMER_NATIVE_SIZE,"empty chunk refused");
 check(fmer_native_transfer_chunk(&tx,42,(size_t)-1,raw,64)==FMER_NATIVE_SIZE,"wrapped offset refused before read");
 check(fmer_native_transfer_chunk(&tx,42,0,raw,64)==FMER_NATIVE_OK,"first chunk accepted");
 check(fmer_native_transfer_chunk(&tx,42,0,raw,64)==FMER_NATIVE_OK && tx.received==64,"duplicate retry idempotent");
 check(fmer_native_transfer_begin(&tx,42,9,FMER_NATIVE_BYTES)==FMER_NATIVE_OK && tx.received==64,"begin retry idempotent");
 std::memcpy(changed,raw,sizeof raw);changed[10]^=1;
 check(fmer_native_transfer_chunk(&tx,42,0,changed,64)==FMER_NATIVE_CONFLICT && tx.received==64,"conflicting retry cannot modify staged bytes");
 check(fmer_native_transfer_chunk(&tx,42,63,raw,2)==FMER_NATIVE_ORDER,"partially overlapping chunk refused");
 for(unsigned offset=64;offset<sizeof raw;offset+=64) {
  const auto count=(sizeof raw-offset)<64?(sizeof raw-offset):64;
  check(fmer_native_transfer_chunk(&tx,42,offset,raw+offset,count)==FMER_NATIVE_OK,"ordered remainder accepted");
 }
 check(fmer_native_transfer_ready(&tx,42,10)==FMER_NATIVE_STALE,"intervening live edit refuses commit");
 check(fmer_native_transfer_ready(&tx,42,9)==FMER_NATIVE_OK,"validated full transaction ready");
 check(!std::memcmp(tx.bytes,raw,sizeof raw),"transaction retains exact file");
 tx.bytes[100]^=1;check(fmer_native_transfer_ready(&tx,42,9)==FMER_NATIVE_CRC,"commit revalidates stored checksum");
 fmer_native_transfer_reset(&tx);
 check(!tx.active && !tx.received && !tx.id && !tx.bytes[100],"abort clears ownership and staged bytes");
 check(fmer_native_transfer_ready(&tx,42,9)==FMER_NATIVE_TRANSACTION,"reset transaction cannot commit");
 for(unsigned rank=0;rank<720;rank++){uint8_t order[6];fmer_fx_unrank((uint16_t)rank,order);
  check(fmer_fx_rank(order)==rank,"all720 unique permutations round trip");
  for(unsigned effect=0;effect<6;effect++){auto moved=fmer_fx_move((uint16_t)rank,effect,-6);fmer_fx_unrank(moved,order);check(order[0]==effect,"every effect can move to input");
   moved=fmer_fx_move((uint16_t)rank,effect,6);fmer_fx_unrank(moved,order);check(order[5]==effect,"every effect can move to output");}}
 std::puts("FMER native state PASS: exact4000B roundtrip,32000 bit corruptions, ranges/names/inactive steps, atomic refusal, bounded transactional assembly");
 return 0;
}
