#include "../firmware/fm1/battery_estimate.h"
#include "../firmware/fm1/battery_history.h"
#include <cstdlib>
#include <cstdio>
static void check(bool ok,const char *why){if(!ok){std::fprintf(stderr,"FAIL: %s\n",why);std::exit(1);}}
int main(){
 check(fmer_battery_estimate(633)==100 && fmer_battery_estimate(590)==78,"measured top/discharge readings have explicit provisional mapping");
 check(fmer_battery_estimate(531)==5 && fmer_battery_estimate(520)==0,"provisional low anchors");
 check(fmer_battery_estimate(0)==101 && fmer_battery_estimate(1023)==101,"implausible ADC remains unknown");
 unsigned prev=0;for(unsigned x=400;x<=750;x++){auto v=fmer_battery_estimate(x);check(v<=100 && v>=prev,"bounded monotonic full ADC sweep");prev=v;}
 fmer_battery_estimator_t s{};check(fmer_battery_update(&s,633,0)==100,"boot uses actual measured level");
 check(fmer_battery_update(&s,590,29999)==100,"load change does not cause immediate jump");
 check(fmer_battery_update(&s,590,30000)==99,"bounded downward display update");
 check(fmer_battery_update(&s,633,60000)==100,"charging recovery can rise");
 check(fmer_battery_update(&s,0,61000)==101 && fmer_battery_update(&s,590,62000)==78,"invalid sample recovery reseeds without invented value");
 s.last_ms=0xfffffff0u;s.percent=79;s.initialized=1;check(fmer_battery_update(&s,590,30000)==78,"uptime wrap preserves cadence");
 s={};fmer_battery_update(&s,561,0);check(fmer_battery_update(&s,523,4999)==51,"low readings require sustained five second interval");
 check(fmer_battery_update(&s,523,5000)==46,"low-charge fall bypasses thirty-second smoothing");
 for(unsigned t=10000;t<=60000;t+=5000)fmer_battery_update(&s,523,t);
 check(s.percent==fmer_battery_estimate(523),"low charge catches up without undershoot");
 fmer_battery_history_t h{};fmer_battery_history_add(&h,0,633,633,1);fmer_battery_history_add(&h,1000,620,620,0);
 check(h.total==2,"bus transition captured immediately");
 fmer_battery_history_add(&h,300000,610,610,0);check(h.total==2,"five minute cadence after transition");
 fmer_battery_history_add(&h,301000,607,607,0);check(h.total==3,"five minute sample retained");
 for(unsigned i=2;i<=130;i++)fmer_battery_history_add(&h,1000+i*300000,590,590,0);
 check(fmer_battery_history_count(&h)==128 && fmer_battery_history_get(&h,127)->raw==590,"bounded ring keeps latest samples");
 check(!fmer_battery_history_get(&h,128),"out-of-range history rejected");
 std::puts("Battery provisional curve, smoothing, invalid input and long history passed.");
}
