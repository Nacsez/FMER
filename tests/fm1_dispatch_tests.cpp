#include <cstdint>
#include <cstdio>
#include <cstdlib>
static const uint8_t custom[]={0x7d,'F','M','E','R',2};
static const uint8_t vendor[]={0,0x32,0x45};
static const uint8_t yamaha[]={0x43,0,0};
static const uint8_t *pending;
static uint32_t pending_length;
static bool arrive_after_empty;
static unsigned companion_calls, vendor_calls;
static void require(bool ok,const char *why) { if(!ok) { std::fprintf(stderr,"FAIL: %s\n",why); std::exit(1); } }
static int ota_frame_get(const uint8_t **p,uint32_t *n) {
    if(!pending) {
        // Reproduce an interrupt delivering a complete frame immediately after
        // the first consumer observed an empty mailbox.
        if(arrive_after_empty) { pending=custom; pending_length=sizeof custom; arrive_after_empty=false; }
        return 0;
    }
    *p=pending; *n=pending_length; return 1;
}
static void companion_service(const uint8_t *p,uint32_t n) {
    require(p==pending && n==pending_length,"dispatch retains the exact observed frame");
    companion_calls++; pending=nullptr;
}
static void ota_service() {
    require(pending==vendor,"vendor parser never consumes a newly arriving custom frame");
    vendor_calls++; pending=nullptr;
}
#include "../firmware/fm1/frame_dispatch.h"
int main() {
    arrive_after_empty=true;
    fmer_frame_dispatch();
    require(pending==custom && !companion_calls && !vendor_calls,"arrival after empty peek survives this pass");
    fmer_frame_dispatch();
    require(companion_calls==1 && !pending,"custom diagnostics delivered on next pass");
    pending=vendor; pending_length=sizeof vendor; fmer_frame_dispatch();
    require(vendor_calls==1 && !pending,"vendor identity reaches updater parser");
    pending=yamaha; pending_length=sizeof yamaha; fmer_frame_dispatch();
    require(companion_calls==2 && !pending,"Yamaha frames retain companion ownership");
    for(unsigned i=0;i<10000;i++) { arrive_after_empty=true; fmer_frame_dispatch(); fmer_frame_dispatch(); }
    require(companion_calls==10002 && vendor_calls==1,"repeated interrupt-boundary arrivals are never lost or misrouted");
    std::puts("FMER single-consumer frame dispatch passed");
}
