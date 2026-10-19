#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <vector>
extern "C" {
void* fmer_test_memcpy(void*,const void*,size_t);
void* fmer_test_memmove(void*,const void*,size_t);
void* fmer_test_memset(void*,int,size_t);
int fmer_test_memcmp(const void*,const void*,size_t);
double __adddf3(double,double),__subdf3(double,double),__muldf3(double,double),__divdf3(double,double);
int __fixdfsi(double);
double __floatsidf(int);
uint64_t __udivdi3(uint64_t,uint64_t),__umoddi3(uint64_t,uint64_t);
uint64_t __udivmoddi4(uint64_t,uint64_t,uint64_t*);
int __ieee754_rem_pio2(double,double*);
int __ieee754_rem_pio2f(float,float*);
}
static unsigned long long checks=0;
static void require(bool okay,const char* what) {
    ++checks;
    if(!okay){std::fprintf(stderr,"runtime check failed: %s (%llu)\n",what,checks);std::exit(1);}
}
static uint64_t bits(double x){uint64_t u;std::memcpy(&u,&x,8);return u;}
static uint64_t random_word() {
    static uint64_t x=0x9e3779b97f4a7c15ULL;
    x^=x<<13;x^=x>>7;x^=x<<17;return x;
}
static void same(double actual,double expected,const char* what,uint64_t ulps=0) {
    if(std::isnan(expected)){require(std::isnan(actual),what);return;}
    auto a=bits(actual),b=bits(expected);
    require((a==b)||((a>>63)==(b>>63)&&std::isfinite(actual)&&std::isfinite(expected)&&
        (a>b?a-b:b-a)<=ulps),what);
}
static void memory() {
    std::vector<unsigned char> source(8192),a(8192),b(8192);
    for(auto& x:source)x=static_cast<unsigned char>(random_word());
    for(size_t n=0;n<=4096;n+=n<64?1:37)for(size_t offset=0;offset<8;++offset){
        a=source;b=source;
        require(fmer_test_memset(a.data()+offset,0xa5,n)==a.data()+offset,"memset return");
        std::memset(b.data()+offset,0xa5,n);require(a==b,"memset guards and alignment");
        for(size_t from=0;from<8;++from){
            a=source;b=source;
            require(fmer_test_memcpy(a.data()+offset,source.data()+from,n)==a.data()+offset,"memcpy return");
            std::memcpy(b.data()+offset,source.data()+from,n);require(a==b,"memcpy guards and alignment");
            for(int direction: {-1,1}){
                a=source;b=source;size_t dst=64+offset,src=static_cast<size_t>(64+offset+direction*int(from));
                require(fmer_test_memmove(a.data()+dst,a.data()+src,n)==a.data()+dst,"memmove return");
                std::memmove(b.data()+dst,b.data()+src,n);require(a==b,"memmove overlap");
            }
        }
        require(fmer_test_memcmp(a.data()+offset,b.data()+offset,n)==0,"memcmp equal");
        if(n){b[offset+n-1]^=0xff;int x=fmer_test_memcmp(a.data()+offset,b.data()+offset,n),y=std::memcmp(a.data()+offset,b.data()+offset,n);
            require((x>0)==(y>0)&&(x<0)==(y<0),"memcmp unsigned order");}
    }
}
static void arithmetic() {
    for(unsigned i=0;i<100000;++i){
        double a=std::ldexp(static_cast<double>(int32_t(random_word()))/2147483648.0,int(random_word()%601)-300);
        double b=std::ldexp(static_cast<double>(int32_t(random_word()))/2147483648.0,int(random_word()%601)-300);
        if(!b)b=1;
        same(__adddf3(a,b),a+b,"soft add");same(__subdf3(a,b),a-b,"soft subtract");
        same(__muldf3(a,b),a*b,"soft multiply");same(__divdf3(a,b),a/b,"soft divide",1);
        int32_t v=int32_t(random_word());same(__floatsidf(v),double(v),"int to double");
        require(__fixdfsi(double(v))==v,"double to int");
        uint64_t x=random_word(),y=random_word()|1,r=0;
        require(__udivdi3(x,y)==x/y,"uint64 divide");require(__umoddi3(x,y)==x%y,"uint64 remainder");
        require(__udivmoddi4(x,y,&r)==x/y&&r==x%y,"uint64 quotient and remainder");
    }
    const double inf=std::numeric_limits<double>::infinity(),nan=std::numeric_limits<double>::quiet_NaN();
    const double values[]={0.0,-0.0,1,-1,inf,-inf,nan,1e300,1e-300};
    for(double a:values)for(double b:values){
        same(__adddf3(a,b),a+b,"add exceptional");same(__muldf3(a,b),a*b,"multiply exceptional");
        // LLVM4's documented gradual-underflow limitation is checked explicitly
        // below, never mistaken for full IEEE conformance or new DSP behavior.
        double expected=a/b;
        if(std::fpclassify(expected)!=FP_SUBNORMAL)same(__divdf3(a,b),expected,"divide exceptional",1);
    }
    require(__divdf3(std::numeric_limits<double>::min(),2.0)==0.0,"documented division underflow flush");
}
static double reconstructed_sin(double y,int quadrant){
    switch(quadrant&3){case 0:return std::sin(y);case 1:return std::cos(y);case 2:return -std::sin(y);default:return -std::cos(y);}
}
static void reduction() {
    for(unsigned i=0;i<50000;++i){
        double x=std::ldexp(double(int32_t(random_word()))/2147483648.0,int(random_word()%1001)-30),y[2];
        int q=__ieee754_rem_pio2(x,y);double z=y[0]+y[1];
        require(std::abs(z)<=0.785398163397449,"double reduction interval");
        require(std::abs(reconstructed_sin(z,q)-std::sin(x))<2e-15,"double reduction phase");
        // FMER keeps float oscillator/modulation phases bounded. Exercise a
        // much wider +/-4096-radian domain; do not claim full-range libm proof.
        float xf=std::ldexp(float(int32_t(random_word()))/2147483648.0f,int(random_word()%43)-30),yf[2];
        q=__ieee754_rem_pio2f(xf,yf);z=double(yf[0])+yf[1];
        require(std::abs(z)<=0.785399,"float reduction interval");
        require(std::abs(reconstructed_sin(z,q)-std::sin(double(xf)))<1e-6,"float reduction phase");
    }
}
int main(){memory();arithmetic();reduction();std::printf("%llu runtime checks passed; host only, target timing separate\n",checks);}
