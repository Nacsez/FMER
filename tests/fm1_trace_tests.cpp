#include <cstdio>
#include <cstdlib>
#include <cstring>
// Model the actual HAL's unconditional CLI/STI pair. A nested ordinary push
// would re-enable interrupts prematurely, so an owned-section push must use
// the explicit lock-owned API instead.
static bool irq_enabled=false;
static unsigned lock_calls=0,unlock_calls=0;
static unsigned trace_lock(){lock_calls++;irq_enabled=false;return 0;}
static void trace_unlock(unsigned){unlock_calls++;irq_enabled=true;}
#define FMER_TRACE_LOCK() trace_lock()
#define FMER_TRACE_UNLOCK(f) trace_unlock(f)
#include "../firmware/fm1/trace.h"
static void check(bool ok,const char* why) { if(!ok) { std::fprintf(stderr,"FAIL: %s\n",why); std::exit(1); } }
int main() {
 fmer_trace_t t{}; fmer_trace_event_t out[FMER_TRACE_BATCH]; uint32_t newest,oldest;
 fmer_trace_push_locked(&t,0,FMER_TRACE_BOOT,704,0,0);
 check(!irq_enabled && lock_calls==0 && unlock_calls==0,"startup event never enables IRQs before peripheral setup");
 t={};irq_enabled=true;
 const auto outer=trace_lock();
 fmer_trace_push_locked(&t,1,FMER_TRACE_CONTROL,162,1000,1);
 check(!irq_enabled && lock_calls==1 && unlock_calls==0,"trace inside control publication cannot reopen outer critical section");
 trace_unlock(outer);check(irq_enabled,"owner releases its critical section once");t={};
 check(fmer_trace_snapshot(&t,0,out,&newest,&oldest)==0 && newest==0 && oldest==1,"empty stream is unambiguous");
 for(uint32_t i=1;i<=300;i++) fmer_trace_push(&t,i*10,FMER_TRACE_ENCODER,6,-3,i);
 check(fmer_trace_snapshot(&t,0,out,&newest,&oldest)==6 && newest==300 && oldest==45,"bounded ring exposes overwritten interval");
 check(out[0].sequence==45 && out[0].ms==450 && out[0].value==-3 && out[0].aux==45,"signed deltas and timestamps survive wrap");
 uint32_t cursor=44,count=0;
 while(uint32_t n=fmer_trace_snapshot(&t,cursor,out,&newest,&oldest)) {
  for(uint32_t i=0;i<n;i++) check(out[i].sequence==++cursor,"ordered contiguous retained stream");
  count+=n;
 }
 check(count==256,"each retained record can be recovered");
 check(fmer_trace_snapshot(&t,299,out,&newest,&oldest)==1 && out[0].sequence==300,"reads never consume another reader's events");
 t.newest=0xFFFFFFFFu;fmer_trace_push(&t,4,FMER_TRACE_BOOT,704,0,0);
 check(fmer_trace_snapshot(&t,300,out,&newest,&oldest)==1 && newest==1 && oldest==1,"sequence restart exposes new epoch");
 std::puts("FMER trace: overwrite gaps, reconnect cursors, signed events and sequence restart passed");
}
