#include "ble_midi.hpp"
#include "synth.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <new>
#include <initializer_list>

static unsigned allocations;
void* operator new(std::size_t n) { ++allocations; if (auto p = std::malloc(n ? n : 1)) return p; throw std::bad_alloc(); }
void* operator new[](std::size_t n) { return ::operator new(n); }
void operator delete(void* p) noexcept { std::free(p); }
void operator delete[](void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }
void operator delete[](void* p, std::size_t) noexcept { std::free(p); }
using namespace fmer::ble;
static void check(bool b, const char* what) { if (!b) { std::fprintf(stderr, "FAIL: %s\n", what); std::exit(1); } }
static unsigned packet(Message m, unsigned t, std::uint8_t* bytes) {
    TimedMessage e{t, m}; unsigned n = 0;
    check(encode(&e, 1, bytes, max_packet, n) == 1, "encode message"); return n;
}
static void input(Group& g, unsigned p, unsigned epoch, Message m, unsigned t, unsigned arrival) {
    std::uint8_t bytes[max_packet]; const auto n = packet(m, t, bytes);
    check(g.receive(p, epoch, bytes, n, arrival), "receive valid message");
}
static void drain(Group& g, unsigned now) { Delivery d; while (g.pop(now, d)) {} }
static void codec() {
    Decoded d;
    const std::uint8_t notes[] = {0x80, 0x80, 0x90, 60, 100, 62, 90, 0x85, 64, 80, 0x86, 0xf8, 65, 70};
    check(decode(notes, sizeof notes, d) == DecodeResult::ok && d.count == 5, "running status and realtime");
    check(d.events[2].time_ms == 5 && d.events[3].midi.status == 0xf8 && d.events[4].midi.status == 0x90, "running status survives realtime");
    const std::uint8_t interleave[] = {0x80, 0x81, 0x90, 60, 0x82, 0xf8, 100};
    check(decode(interleave, sizeof interleave, d) == DecodeResult::ok && d.count == 2, "realtime within message");
    check(d.events[0].midi.status == 0xf8 && d.events[1].midi.b == 100 && d.events[1].time_ms == 2, "completion order maintained");
    const std::uint8_t wrap[] = {0xbf, 0xff, 0xf8, 0x80, 0xf8};
    check(decode(wrap, sizeof wrap, d) == DecodeResult::ok && d.events[0].time_ms == 8191 && d.events[1].time_ms == 0, "13-bit wrap within notification");
    const std::uint8_t malformed[][6] = {{0xc0,0x80,0x90,60,90,0x80}, {0x80,0x80,0x90,60,90,0x80}, {0x80,0x80,60,90,0,0}, {0x80,0x80,0xf4,0,0,0}};
    for (const auto& p : malformed) check(decode(p, sizeof p, d) == DecodeResult::malformed && !d.count, "malformed packet is atomic");
    const std::uint8_t sysex[] = {0x80,0x80,0xf0,1,2,0x80,0xf7};
    check(decode(sysex, sizeof sysex, d) == DecodeResult::unsupported_sysex && !d.count, "unsupported SysEx reported");
    const std::uint8_t no_status[] = {0x80,0x80,60,90};
    check(decode(no_status, sizeof no_status, d) == DecodeResult::malformed, "running status never crosses packet boundary");
    check(decode(nullptr, 0, d) == DecodeResult::malformed, "null input bounded");
    for (unsigned status = 0x80; status <= 0xff; ++status) {
        Message m{static_cast<std::uint8_t>(status), 20, 100};
        if (!message_size(m)) continue;
        for (unsigned t : {0u,127u,128u,8191u,8192u,0xfffffff0u}) {
            std::uint8_t bytes[max_packet]; unsigned n = packet(m, t, bytes);
            check(decode(bytes, n, d) == DecodeResult::ok && d.count == 1, "all MIDI1 short statuses round trip");
            check(d.events[0].midi.status == status && d.events[0].time_ms == (t & 8191), "status/timestamp preserved");
            if (message_size(m) > 1) check(d.events[0].midi.a == 20, "first data preserved");
            if (message_size(m) > 2) check(d.events[0].midi.b == 100, "second data preserved");
        }
    }
    TimedMessage e[3]{{127,{0x90,60,100}}, {128,{0x80,60,0}}, {128,{0xf8,0,0}}};
    std::uint8_t bytes[64]; unsigned size;
    check(encode(e, 3, bytes, 20, size) == 1 && size == 5, "TX splits high timestamp changes");
    check(encode(e, 1, bytes, 4, size) == 0 && size == 0, "no fragmented note");
    // Deterministic hostile packets and round-trip all accepted decodes.
    unsigned random = 0x732;
    for (unsigned k = 0; k < 100000; ++k) {
        unsigned n = k % 65;
        for (unsigned i = 0; i < n; ++i) { random = random * 1664525u + 1013904223u; bytes[i] = random >> 24; }
        if (decode(bytes, n, d) == DecodeResult::ok) {
            check(d.count <= max_events, "fuzz output bounded");
            unsigned at = 0;
            while (at < d.count) {
                unsigned used = encode(d.events + at, d.count - at, bytes, 64, size); check(used != 0, "accepted event encodable");
                Decoded again; check(decode(bytes, size, again) == DecodeResult::ok && again.count == used, "fuzz round trip"); at += used;
            }
        } else check(d.count == 0, "fuzz failure publishes no events");
    }
}
static void sessions() {
    Group g; Delivery d; Transmission tx;
    auto a = g.connect(0, RadioRole::central), b = g.connect(1, RadioRole::central);
    std::uint8_t bytes[64]; unsigned n = packet({0x90,60,100}, 10, bytes);
    check(!g.receive(0, a, bytes, n, 10) && !g.peek(0, tx), "discovery cannot exchange MIDI");
    check(!g.ready(0, a, 22) && g.ready(0, a, 23) && g.ready(1, b, 67), "valid ATT MTU required"); drain(g,0);
    input(g,0,a,{0x90,60,100},8190,1000);
    check(!g.pop(1002,d) && g.pop(1003,d) && d.source == 6, "scheduled input uses sender offset");
    check(!g.peek(1,tx), "received notes never echo to another peer");
    input(g,0,a,{0x80,60,0},2,1004);
    check(g.pop(1007,d) && d.event.midi.status == 0x80, "timestamp wrap keeps four ms interval");
    input(g,0,a,{0x90,61,100},12,1020);
    check(g.pop(1020,d) && d.event.time_ms==1017 && g.counters().late_events==1 && g.counters().max_lateness_ms==3, "arrival jitter preserves sender spacing and counts lateness");
    input(g,0,a,{0x90,62,100},3,20000);
    check(g.pop(20003,d), "idle longer than timestamp wrap reanchors");
    check(g.follow(0), "clock authority explicit");
    input(g,1,b,{0xfa,0,0},10,20010); check(!g.pop(20014,d) && g.counters().clock_rejected == 1, "second clock cannot take control");
    input(g,0,a,{0xfa,0,0},10,20010); drain(g,20014);
    check(g.send_local({0xf8,0,0},20015) == 0, "follower cannot echo local clock");
    g.poll(20511); check(g.pop(20511,d) && d.stop_clock && g.counters().clock_lost == 1, "clock loss stops once");
    g.poll(21000); check(!g.pop(21000,d), "timeout is not repeated");
    input(g,0,a,{0xfa,0,0},100,21001);
    check(g.follow(1), "switch clock authority");
    check(g.pop(21002,d) && d.stop_clock && !g.pop(21100,d), "old queued start removed on owner change");
    check(g.send_local({0x90,67,100},22000) == 2 && g.peek(0,tx), "local messages broadcast separately");
    check(!g.commit(1,tx), "completion token cannot consume another peer's events");
    auto old = tx; check(g.commit(0,tx) && !g.commit(0,tx), "commit exactly once");
    a = g.connect(0,RadioRole::peripheral); check(g.ready(0,a,23) && !g.commit(0,old), "reconnect invalidates old completions"); drain(g,22000);
    check(!g.receive(0,a-1,bytes,n,22000), "stale RX ignored");
    input(g,0,a,{0x90,67,100},0,22000); input(g,1,b,{0x90,68,100},0,22000);
    g.disconnect(0,a);
    check(g.pop(22004,d) && d.release_source && d.source == 6, "disconnect releases only peer");
    check(g.pop(22004,d) && d.source == 7 && d.event.midi.a == 68, "other peer notes survive");
    // Paused output on peer1 cannot block peer2. Fault is explicit, requiring
    // backend disconnect/recovery rather than silently losing remote note-offs.
    auto c = g.connect(2,RadioRole::central); check(g.ready(2,c,23), "third simulated peer"); drain(g,22005);
    for (unsigned i=0;i<34;++i) {
        g.send_local({0x90,static_cast<std::uint8_t>(i),100},23000);
        check(g.peek(2,tx) && g.commit(2,tx), "unblocked peer sends while other stalls");
    }
    check(g.state(1) == PeerState::fault && g.state(2) == PeerState::ready && g.counters().tx_overflow == 1, "stalled peer isolated");
    drain(g,24000);
    for (unsigned i=0;i<32;++i) input(g,2,c,{0x90,60,100},0,24000);
    n=packet({0x80,60,0},0,bytes);
    check(!g.receive(2,c,bytes,n,24000) && g.counters().rx_overflow == 1, "RX overflow explicit");
    check(g.pop(24005,d) && d.release_source && d.source == 8 && !g.pop(24005,d), "overflow discards partial batch and releases source");
    check(g.state(2)==PeerState::fault && !g.ready(2,c,23), "RX overflow requires backend disconnect/reconnect");
    // 32-bit local uptime wrap.
    g.disconnect(2,c); c=g.connect(2,RadioRole::central); check(g.ready(2,c,23), "recovered peer can reconnect"); drain(g,24005);
    input(g,2,c,{0x90,60,100},100,0xfffffffdu);
    check(!g.pop(0xffffffffu,d) && g.pop(0,d), "local uptime wraps safely");
    // Malformed tails cannot retain the first note, or silently discard queued
    // remote note-offs while leaving the connection apparently healthy.
    const std::uint8_t bad_tail[] = {0x80,0x80,0x90,60,100,0x81};
    check(!g.receive(2,c,bad_tail,sizeof bad_tail,10), "invalid tail refused");
    check(g.state(2)==PeerState::fault && g.pop(10,d) && d.release_source && !g.pop(10,d), "invalid packet faults and releases, never partial note");
}
static void synth_ownership() {
    fmer::Synth synth; check(synth.init() && synth.set_voice_budget(4), "synth starts");
    Group g; auto a=g.connect(0,RadioRole::central), b=g.connect(1,RadioRole::central);
    check(g.ready(0,a,23) && g.ready(1,b,23), "two peer synth session"); drain(g,0);
    input(g,0,a,{0x90,60,100},0,0); input(g,1,b,{0x90,60,100},0,0);
    synth.note_on(0,64,100,3); Delivery d;
    while(g.pop(5,d)) synth.note_on(d.event.midi.status & 15,d.event.midi.a,d.event.midi.b,d.source);
    check(synth.stats().active_voices == 3, "same pitch from peers owns separate voices");
    g.disconnect(0,a); check(g.pop(5,d) && d.release_source, "recovery token"); synth.panic_source(d.source);
    check(synth.stats().active_voices == 2, "peer disconnect preserves physical and other peer voices");
    float pcm[256]; synth.render(pcm,256); double energy=0; for(float x:pcm)energy+=x*x;
    check(energy>0.00001, "remaining voices actually render PCM");
}
static void endurance() {
    Group leader, followers[3]; std::uint32_t epochs[3], remote[3]; Delivery d;
    for(unsigned p=0;p<3;++p) {
        epochs[p]=leader.connect(p,RadioRole::central); check(leader.ready(p,epochs[p],23),"leader ready");
        remote[p]=followers[p].connect(0,RadioRole::peripheral); check(followers[p].ready(0,remote[p],23) && followers[p].follow(0),"follower ready");
        drain(followers[p],0);
    }
    drain(leader,0); const unsigned before=allocations;
    unsigned clocks[3]{}, starts[3]{}, stops[3]{}, on[3]{}, off[3]{};
    // 30 simulated minutes at 120 BPM, 24 PPQN; no wall-clock sleep.
    for(unsigned tick=0;tick<86402;++tick) {
        unsigned t=tick*125/6;
        Message m = tick==0?Message{0xfa,0,0}:tick==86401?Message{0xfc,0,0}:Message{0xf8,0,0};
        check(leader.send_local(m,t)==3,"group transport broadcast");
        if(tick%24==1)check(leader.send_local({0x90,60,100},t)==3,"group note on");
        if(tick%24==13)check(leader.send_local({0x80,60,0},t)==3,"group note off");
        for(unsigned p=0;p<3;++p) {
            Transmission tx;
            while(leader.peek(p,tx)) {
                check(followers[p].receive(0,remote[p],tx.bytes,tx.size,t+p),"simulated radio delivery");
                check(leader.commit(p,tx),"simulated radio acceptance");
            }
            while(followers[p].pop(t+10,d)) {
                check(!d.release_source && !d.stop_clock,"steady group has no recoveries");
                auto s=d.event.midi.status;
                clocks[p]+=s==0xf8; starts[p]+=s==0xfa; stops[p]+=s==0xfc; on[p]+=s==0x90; off[p]+=s==0x80;
            }
            followers[p].poll(t+10);
        }
    }
    for(unsigned p=0;p<3;++p)check(clocks[p]==86400 && starts[p]==1 && stops[p]==1 && on[p]==3601 && off[p]==3600,"identical clock and event totals across group");
    // Repeated lifecycle stress: no heap growth and old event generations die.
    for(unsigned i=0;i<10000;++i) {
        auto epoch=leader.connect(0,RadioRole::central); check(leader.ready(0,epoch,23),"reconnect ready");
        leader.disconnect(0,epoch); drain(leader,2000000);
    }
    check(allocations==before,"transport and reconnect paths allocate nothing");
    std::printf("group simulation: 3 peers, 30 minutes, 86400 clocks each; 10000 reconnects; Group=%zu bytes, zero allocations\n",sizeof(Group));
}
int main() { codec(); sessions(); synth_ownership(); endurance(); std::puts("BLE MIDI offline codec, ownership, recovery and group tests passed; no radio or device tested."); }
