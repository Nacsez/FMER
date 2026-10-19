// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include <cstddef>
#include <cstdint>

// Original FMER BLE-MIDI short-message transport. This is an offline-tested
// protocol/session layer, NOT an AC79 radio driver. All calls belong to one
// non-audio transport pump; the eventual radio ISR must enqueue bounded work.
namespace fmer { namespace ble {
constexpr const char service_uuid[] = "03B80E5A-EDE8-4B33-A751-6CE34EC4C700";
constexpr const char characteristic_uuid[] = "7772E5DB-3868-4112-A1A9-F2669D106BF3";
constexpr unsigned max_packet = 64, max_events = 32, max_peers = 3, queue_size = 32;
constexpr unsigned first_peer_source = 6; // 1 USB, 2 TRS, 3 keys, 4 SEQ, 5 ARP.
struct Message { std::uint8_t status{}, a{}, b{}; };
struct TimedMessage { std::uint32_t time_ms{}; Message midi{}; };
enum class DecodeResult : std::uint8_t { ok, malformed, unsupported_sysex, capacity };
struct Decoded {
    TimedMessage events[max_events]{};
    unsigned count{};
};
// Invalid packets publish no events. SysEx is explicitly unsupported in this
// first transport profile, including continuations. No patch/flash commands.
DecodeResult decode(const std::uint8_t* bytes, unsigned size, Decoded& out) noexcept;
unsigned message_size(Message message) noexcept;
// Whole messages only, repeated status, split at timestamp-high boundaries.
// Returns consumed events; bytes_written=0 if the first event cannot fit.
unsigned encode(const TimedMessage* events, unsigned count, std::uint8_t* bytes,
                unsigned capacity, unsigned& bytes_written) noexcept;

enum class RadioRole : std::uint8_t { peripheral, central };
enum class PeerState : std::uint8_t { disconnected, discovering, ready, fault };
struct Counters {
    std::uint32_t rx_packets{}, rx_events{}, tx_events{}, malformed{}, unsupported{};
    std::uint32_t stale{}, rx_overflow{}, tx_overflow{}, clock_rejected{}, clock_lost{};
    std::uint32_t disconnects{}, timestamp_reanchors{};
    std::uint32_t rx_high_water{}, tx_high_water{}, late_events{}, max_lateness_ms{};
};
struct Delivery {
    TimedMessage event{};
    std::uint8_t source{};
    bool release_source{}; // Apply before any subsequent notes from this peer.
    bool stop_clock{};     // Transport stop; never a global synth panic.
};
struct Transmission {
    std::uint8_t bytes[max_packet]{};
    unsigned size{}, count{};
    std::uint32_t epoch{}, serial{};
    unsigned peer{max_peers};
};
class Group {
public:
    // Three peers is a SIMULATION bound, not a qualified physical group size.
    // Caller must perform actual discovery + characteristic subscription/read
    // handshake before ready(). Slots and clock owner are explicit, not paired
    // implicitly by display name. No automatic clock election or MIDI echo.
    // A fault state REQUIRES backend disconnect (and remote disconnect recovery)
    // before reconnect. Never keep an overflowed session silently connected.
    std::uint32_t connect(unsigned peer, RadioRole role) noexcept;
    bool ready(unsigned peer, std::uint32_t epoch, unsigned att_mtu) noexcept;
    void disconnect(unsigned peer, std::uint32_t epoch) noexcept;
    bool follow(int peer) noexcept; // -1 = internal leader, otherwise one peer.
    bool receive(unsigned peer, std::uint32_t epoch, const std::uint8_t* bytes,
                 unsigned size, std::uint32_t arrival_ms) noexcept;
    unsigned send_local(Message message, std::uint32_t now_ms) noexcept;
    bool peek(unsigned peer, Transmission& packet) const noexcept;
    bool commit(unsigned peer, const Transmission& packet) noexcept;
    bool pop(std::uint32_t now_ms, Delivery& delivery) noexcept;
    void poll(std::uint32_t now_ms) noexcept;
    PeerState state(unsigned peer) const noexcept;
    const Counters& counters() const noexcept { return stats_; }
    int clock_owner() const noexcept { return clock_peer_; }
private:
    struct Ring {
        TimedMessage events[queue_size]{};
        unsigned head{}, count{};
        void clear() noexcept { head = count = 0; }
        void push(TimedMessage e) noexcept { events[(head + count++) % queue_size] = e; }
        TimedMessage front() const noexcept { return events[head]; }
        void drop() noexcept { head = (head + 1) % queue_size; --count; }
    };
    struct Peer {
        Ring rx{}, tx{};
        std::uint32_t epoch{}, serial{}, arrival{}, remote{}, mapped{};
        unsigned payload{20};
        PeerState state{};
        RadioRole role{};
        bool timestamp_valid{};
    } peers_[max_peers]{};
    Counters stats_{};
    std::uint32_t last_clock_{};
    unsigned release_mask_{};
    int clock_peer_{-1};
    bool clock_running_{}, stop_pending_{};
    bool current(unsigned peer, std::uint32_t epoch) noexcept;
    void recover(unsigned peer) noexcept;
    std::uint32_t map_time(Peer& peer, std::uint32_t remote, std::uint32_t arrival) noexcept;
};
static_assert(sizeof(Group) <= 2048, "BLE peer state must stay within the 2 KiB software budget");
}} // namespace fmer::ble
