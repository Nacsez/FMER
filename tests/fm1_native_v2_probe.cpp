// Cross-language file probe only. No HAL or device I/O.
#include "../firmware/fm1/native_state.h"
#include <cstdio>
#include <cstring>
int main(int argc,char **argv)
{
 if(argc!=3)return 10;
 FILE *input=std::fopen(argv[1],"rb");if(!input)return 11;
 unsigned char bytes[FMER_NATIVE_BYTES+1],out[FMER_NATIVE_BYTES];
 const size_t count=std::fread(bytes,1,sizeof bytes,input);std::fclose(input);
 fmer_native_state_t state,prior;std::memset(&state,0x5a,sizeof state);prior=state;
 const auto result=fmer_native_decode(bytes,count,&state);
 if(result!=FMER_NATIVE_OK){
  if(std::memcmp(&state,&prior,sizeof state))return 12;
  std::printf("REFUSED %u; destination unchanged\n",(unsigned)result);return 2;
 }
 if(fmer_native_encode(&state,out,sizeof out)!=FMER_NATIVE_OK)return 13;
 FILE *output=std::fopen(argv[2],"wb");if(!output)return 14;
 const size_t written=std::fwrite(out,1,sizeof out,output);const int closed=std::fclose(output);
 if(written!=sizeof out||closed)return 15;
 std::printf("OK %zu -> %zu\n",count,sizeof out);return 0;
}
