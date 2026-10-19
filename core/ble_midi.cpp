// SPDX-License-Identifier: GPL-3.0-only
#include "ble_midi.hpp"

namespace fmer { namespace ble {
namespace {
bool realtime(std::uint8_t s) noexcept { return s == 0xf8 || s == 0xfa || s == 0xfb || s == 0xfc || s == 0xfe || s == 0xff; }
bool transport(std::uint8_t s) noexcept { return s == 0xf8 || s == 0xfa || s == 0xfb || s == 0xfc || s == 0xf2; }
unsigned length(std::uint8_t s) noexcept {
    if (s >= 0x80 && s < 0xf0) return (s & 0xe0) == 0xc0 ? 2 : 3;
    if (s == 0xf1 || s == 0xf3) return 2;
    if (s == 0xf2) return 3;
    return s == 0xf6 || realtime(s) ? 1 : 0;
}
bool due(std::uint32_t a, std::uint32_t b) noexcept { return static_cast<std::int32_t>(a - b) <= 0; }
}
unsigned message_size(Message m) noexcept {
    const unsigned n = length(m.status);
    return (n > 1 && m.a > 127) || (n > 2 && m.b > 127) ? 0 : n;
}
DecodeResult decode(const std::uint8_t* bytes, unsigned size, Decoded& out) noexcept {
    out.count = 0;
    if (!bytes || size < 2 || size > max_packet || (bytes[0] & 0xc0) != 0x80) return DecodeResult::malformed;
    // Work in a scratch result so malformed tails cannot partially trigger notes.
    Decoded tmp{};
    unsigned high = (bytes[0] & 63) << 7, low = 0, stamp = 0, i = 1;
    std::uint8_t running = 0;
    bool have_stamp = false;
    auto timestamp = [&](std::uint8_t b) {
        const unsigned next = b & 127;
        if (have_stamp && next < low) high = (high + 128) & 8191;
        low = next; stamp = high | low; have_stamp = true;
    };
    auto emit = [&](Message m) {
        if (tmp.count == max_events) return false;
        tmp.events[tmp.count++] = {stamp, m}; return true;
    };
    while (i < size) {
        bool stamped = false;
        if (bytes[i] & 128) { timestamp(bytes[i++]); stamped = true; }
        if (i == size || !have_stamp) return DecodeResult::malformed;
        std::uint8_t status = running;
        if (bytes[i] & 128) {
            if (!stamped) return DecodeResult::malformed;
            status = bytes[i++];
            if (status == 0xf0 || status == 0xf7) return DecodeResult::unsupported_sysex;
            if (!realtime(status)) running = status < 0xf0 ? status : 0;
        }
        const unsigned n = length(status);
        if (!n) return DecodeResult::malformed;
        Message m{status, 0, 0};
        unsigned data = 1;
        const unsigned message_stamp = stamp;
        while (data < n) {
            if (i == size) return DecodeResult::malformed;
            if (bytes[i] & 128) {
                timestamp(bytes[i++]);
                if (i == size || !realtime(bytes[i])) return DecodeResult::malformed;
                if (!emit({bytes[i++], 0, 0})) return DecodeResult::capacity;
            } else {
                if (data == 1) m.a = bytes[i++]; else m.b = bytes[i++];
                ++data;
            }
        }
        // Interleaved realtime is delivered first, preserving MIDI byte-stream
        // completion order; clamp the completed message to that event's time.
        if (tmp.count == max_events) return DecodeResult::capacity;
        tmp.events[tmp.count++] = {stamp == message_stamp ? message_stamp : stamp, m};
    }
    out = tmp;
    return DecodeResult::ok;
}
unsigned encode(const TimedMessage* events, unsigned count, std::uint8_t* bytes,
                unsigned capacity, unsigned& written) noexcept {
    written = 0;
    if (!events || !bytes || !count || capacity < 3) return 0;
    if (capacity > max_packet) capacity = max_packet;
    const unsigned high = (events[0].time_ms >> 7) & 63;
    unsigned n = 0, at = 1;
    while (n < count) {
        const auto& e = events[n]; const unsigned len = message_size(e.midi);
        if (!len || ((e.time_ms >> 7) & 63) != high || at + 1 + len > capacity) break;
        bytes[at++] = 0x80 | (e.time_ms & 127); bytes[at++] = e.midi.status;
        if (len > 1) bytes[at++] = e.midi.a;
        if (len > 2) bytes[at++] = e.midi.b;
        ++n;
    }
    if (n) { bytes[0] = static_cast<std::uint8_t>(0x80 | high); written = at; }
    return n;
}
bool Group::current(unsigned p, std::uint32_t epoch) noexcept {
    if (p >= max_peers || !epoch || peers_[p].epoch != epoch || peers_[p].state == PeerState::disconnected) {
        ++stats_.stale; return false;
    }
    return true;
}
void Group::recover(unsigned p) noexcept {
    peers_[p].rx.clear(); peers_[p].tx.clear(); ++peers_[p].serial;
    peers_[p].timestamp_valid = false;
    release_mask_ |= 1u << p;
    if (clock_peer_ == static_cast<int>(p) && clock_running_) { clock_running_ = false; stop_pending_ = true; }
}
std::uint32_t Group::connect(unsigned p, RadioRole role) noexcept {
    if (p >= max_peers) return 0;
    recover(p);
    auto& peer = peers_[p];
    if (++peer.epoch == 0) ++peer.epoch;
    peer.role = role; peer.state = PeerState::discovering; peer.payload = 20;
    return peer.epoch;
}
bool Group::ready(unsigned p, std::uint32_t epoch, unsigned mtu) noexcept {
    if (!current(p, epoch) || peers_[p].state != PeerState::discovering || mtu < 23 || mtu > 517) return false;
    peers_[p].payload = mtu - 3 < max_packet ? mtu - 3 : max_packet;
    peers_[p].state = PeerState::ready; return true;
}
void Group::disconnect(unsigned p, std::uint32_t epoch) noexcept {
    if (!current(p, epoch)) return;
    recover(p); peers_[p].state = PeerState::disconnected; ++stats_.disconnects;
}
bool Group::follow(int p) noexcept {
    if (p < -1 || p >= static_cast<int>(max_peers)) return false;
    if (p != clock_peer_) {
        if (clock_running_) stop_pending_ = true;
        clock_running_ = false;
        // Remove queued transport from the old authority. Keep its notes.
        for (auto& peer : peers_) {
            const unsigned n = peer.rx.count;
            for (unsigned i = 0; i < n; ++i) { const auto e = peer.rx.front(); peer.rx.drop(); if (!transport(e.midi.status)) peer.rx.push(e); }
        }
        clock_peer_ = p;
    }
    return true;
}
std::uint32_t Group::map_time(Peer& p, std::uint32_t remote, std::uint32_t arrival) noexcept {
    const unsigned delta = (remote - p.remote) & 8191;
    std::uint32_t mapped = p.mapped + delta;
    const auto drift = static_cast<std::int32_t>(mapped - arrival);
    if (!p.timestamp_valid || arrival - p.arrival >= 8192 || delta > 4096 || drift < -50 || drift > 50) {
        mapped = arrival + 3; ++stats_.timestamp_reanchors;
    }
    // A reanchor must never make this peer's already queued events go backward.
    if (p.timestamp_valid && !due(p.mapped, mapped)) mapped = p.mapped;
    p.timestamp_valid = true; p.arrival = arrival; p.remote = remote; p.mapped = mapped;
    return mapped;
}
bool Group::receive(unsigned p, std::uint32_t epoch, const std::uint8_t* bytes,
                    unsigned size, std::uint32_t arrival) noexcept {
    if (!current(p, epoch) || peers_[p].state != PeerState::ready) return false;
    auto& peer = peers_[p]; Decoded decoded{};
    const auto result = size <= peer.payload ? decode(bytes, size, decoded) : DecodeResult::malformed;
    if (result != DecodeResult::ok) {
        if (result == DecodeResult::unsupported_sysex) ++stats_.unsupported; else ++stats_.malformed;
        // Invalid packets may contain a lost note-off. Retire only this source.
        recover(p); peer.state = PeerState::fault; return false;
    }
    unsigned accepted = 0;
    for (unsigned i = 0; i < decoded.count; ++i) if (!transport(decoded.events[i].midi.status) || clock_peer_ == static_cast<int>(p)) ++accepted;
    if (accepted > queue_size - peer.rx.count) { ++stats_.rx_overflow; recover(p); peer.state = PeerState::fault; return false; }
    ++stats_.rx_packets;
    for (unsigned i = 0; i < decoded.count; ++i) {
        auto e = decoded.events[i];
        if (transport(e.midi.status) && clock_peer_ != static_cast<int>(p)) { ++stats_.clock_rejected; continue; }
        e.time_ms = map_time(peer, e.time_ms, arrival); peer.rx.push(e); ++stats_.rx_events;
        if (peer.rx.count > stats_.rx_high_water) stats_.rx_high_water = peer.rx.count;
        if (e.midi.status == 0xfa || e.midi.status == 0xfb) { clock_running_ = true; last_clock_ = arrival; }
        if (e.midi.status == 0xf8) last_clock_ = arrival;
        if (e.midi.status == 0xfc) clock_running_ = false;
    }
    return true;
}
unsigned Group::send_local(Message m, std::uint32_t now) noexcept {
    if (!message_size(m) || (transport(m.status) && clock_peer_ != -1)) return 0;
    unsigned sent = 0;
    for (unsigned p = 0; p < max_peers; ++p) {
        auto& peer = peers_[p]; if (peer.state != PeerState::ready) continue;
        if (peer.tx.count == queue_size) {
            ++stats_.tx_overflow; recover(p); peer.state = PeerState::fault;
            // Backend must disconnect a faulted peer. Dropping its note-offs
            // silently would strand notes on the remote instrument.
        } else {
            peer.tx.push({now, m}); ++sent;
            if (peer.tx.count > stats_.tx_high_water) stats_.tx_high_water = peer.tx.count;
        }
    }
    return sent;
}
bool Group::peek(unsigned p, Transmission& packet) const noexcept {
    packet = {};
    if (p >= max_peers || peers_[p].state != PeerState::ready) return false;
    const auto& peer = peers_[p]; TimedMessage events[queue_size]{};
    for (unsigned i = 0; i < peer.tx.count; ++i) events[i] = peer.tx.events[(peer.tx.head + i) % queue_size];
    packet.count = encode(events, peer.tx.count, packet.bytes, peer.payload, packet.size);
    packet.epoch = peer.epoch; packet.serial = peer.serial; packet.peer = p;
    return packet.count != 0;
}
bool Group::commit(unsigned p, const Transmission& packet) noexcept {
    if (packet.peer != p) { ++stats_.stale; return false; }
    if (!current(p, packet.epoch) || peers_[p].state != PeerState::ready) return false;
    auto& peer = peers_[p];
    if (packet.serial != peer.serial || !packet.count || packet.count > peer.tx.count) { ++stats_.stale; return false; }
    for (unsigned i = 0; i < packet.count; ++i) peer.tx.drop();
    ++peer.serial; stats_.tx_events += packet.count; return true;
}
bool Group::pop(std::uint32_t now, Delivery& d) noexcept {
    d = {};
    if (stop_pending_) { stop_pending_ = false; d.stop_clock = true; return true; }
    for (unsigned p = 0; p < max_peers; ++p) if (release_mask_ & (1u << p)) {
        release_mask_ &= ~(1u << p); d.source = static_cast<std::uint8_t>(first_peer_source + p); d.release_source = true; return true;
    }
    unsigned chosen = max_peers; std::uint32_t earliest = now;
    for (unsigned p = 0; p < max_peers; ++p) if (peers_[p].rx.count && due(peers_[p].rx.front().time_ms, earliest)) {
        earliest = peers_[p].rx.front().time_ms; chosen = p;
    }
    if (chosen == max_peers) return false;
    d.event = peers_[chosen].rx.front(); peers_[chosen].rx.drop();
    const unsigned late = now - d.event.time_ms;
    if (late) ++stats_.late_events;
    if (late > stats_.max_lateness_ms) stats_.max_lateness_ms = late;
    d.source = static_cast<std::uint8_t>(first_peer_source + chosen); return true;
}
void Group::poll(std::uint32_t now) noexcept {
    if (clock_peer_ >= 0 && clock_running_ && now - last_clock_ > 500) {
        ++stats_.clock_lost; clock_running_ = false; stop_pending_ = true;
        // A stale queued Start/Continue must not restart after timeout.
        auto& rx = peers_[clock_peer_].rx; const unsigned n = rx.count;
        for (unsigned i = 0; i < n; ++i) { auto e = rx.front(); rx.drop(); if (!transport(e.midi.status)) rx.push(e); }
    }
}
PeerState Group::state(unsigned p) const noexcept { return p < max_peers ? peers_[p].state : PeerState::disconnected; }
}} // namespace fmer::ble
