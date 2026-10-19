#include "../firmware/fm1/encoder_model.h"
#include <cstdio>
#include <cstdlib>
#include <initializer_list>
static void check(bool b,const char* s){if(!b){std::fprintf(stderr,"FAIL: %s\n",s);std::exit(1);}}
struct Decoder{uint8_t prev=255,rest=0;uint16_t still=0;int8_t sub=0;uint32_t moves=0,lost=0;int sum=0;
 void feed(int v){sum+=fmer_encoder_sample(v,&prev,&rest,&still,&sub,&moves,&lost);}};
int main(){
 for(int repeats: {1,2,8,50}){Decoder d;d.feed(0);for(int n=0;n<80;n++)for(int s:{1,3,2,0})for(int j=0;j<repeats;j++)d.feed(s);check(d.sum==80,"80 clockwise detents at fast/slow sample dwell");for(int n=0;n<80;n++)for(int s:{2,3,1,0})for(int j=0;j<repeats;j++)d.feed(s);check(d.sum==0,"reverse count cancels");}
 Decoder b;b.feed(0);for(int n=0;n<100;n++){b.feed(1);b.feed(0);}check(b.sum==0,"contact bounce does not turn");
 for(int s:{1,0,1,3,1,3,2,3,2,0})b.feed(s);check(b.sum==1,"bounce around full clockwise detent counts once");
 Decoder j;j.feed(0);j.feed(3);j.feed(0);check(j.sum==0 && j.lost==2,"ambiguous jumps do not invent direction");
 Decoder boot;boot.feed(1);for(int k=0;k<901;k++)boot.feed(0);check(boot.rest==0 && boot.sum==0,"rest relearn cannot generate a turn");
 std::puts("FMER encoder PASS: fast/slow, reversal, bounce, ambiguity, rest relearn");
}
