// Retained by a separate OFFLINE link only. Never included in board startup.
// Exercises every public path so --gc-sections cannot hide the transport cost.
#include "ble_midi.hpp"
#include <new>
using namespace fmer::ble;
alignas(Group) static unsigned char group_memory[sizeof(Group)];
static Transmission output;
static Delivery delivery;
static Decoded decoded;
extern "C" unsigned fmer_ble_offline_probe(unsigned command, unsigned peer,
    unsigned epoch, unsigned time, unsigned value, unsigned char* packet) {
    auto& group = *reinterpret_cast<Group*>(group_memory);
    switch (command) {
    case 0: new(group_memory) Group; return sizeof(Group);
    case 1: return group.connect(peer, value ? RadioRole::central : RadioRole::peripheral);
    case 2: return group.ready(peer, epoch, value);
    case 3: group.disconnect(peer, epoch); return 0;
    case 4: return group.follow(static_cast<int>(peer));
    case 5: return group.receive(peer, epoch, packet, value, time);
    case 6: return group.send_local({packet[0],packet[1],packet[2]}, time);
    case 7: return group.peek(peer, output);
    case 8: return group.commit(peer, output);
    case 9: return group.pop(time, delivery);
    case 10: group.poll(time); return group.counters().clock_lost;
    case 11: return static_cast<unsigned>(group.state(peer));
    case 12: return static_cast<unsigned>(decode(packet, value, decoded));
    case 13: return encode(decoded.events, decoded.count, packet, value, output.size);
    case 14: return static_cast<unsigned>(group.clock_owner());
    default: return 0;
    }
}
