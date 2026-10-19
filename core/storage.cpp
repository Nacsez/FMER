#include "storage.hpp"
#include <algorithm>
#include <limits>

namespace fmer {
namespace {
constexpr std::size_t header_size = 16;
constexpr std::size_t payload_size = PresetStore::slots * 155;
std::uint32_t crc32(const std::uint8_t* data, std::size_t size) {
    std::uint32_t crc = 0xffffffffU;
    for (std::size_t i = 0; i < size; ++i) {
        crc ^= data[i];
        for (int bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ (0xedb88320U & (0U - (crc & 1U)));
    }
    return ~crc;
}
void put32(std::uint8_t* p, std::uint32_t n) {
    for (unsigned i = 0; i < 4; ++i) p[i] = static_cast<std::uint8_t>(n >> (i * 8));
}
std::uint32_t get32(const std::uint8_t* p) {
    std::uint32_t n = 0;
    for (unsigned i = 0; i < 4; ++i) n |= std::uint32_t(p[i]) << (i * 8);
    return n;
}
bool valid(const Patch& patch) noexcept {
    // Codec validation is shared with import and parameter editing.
    return validate_patch(patch).valid;
}
}
PresetStore::PresetStore() : audition_(make_init_patch()), previous_(audition_) {
    presets_.fill(audition_);
}
const Patch* PresetStore::saved(std::size_t slot) const noexcept {
    return slot < slots ? &presets_[slot] : nullptr;
}
bool PresetStore::edit(const Patch& patch) noexcept {
    if (!valid(patch)) return false;
    previous_ = audition_; has_undo_ = true; audition_ = patch;
    return true;
}
bool PresetStore::undo() noexcept {
    if (!has_undo_) return false;
    std::swap(audition_, previous_); has_undo_ = false;
    return true;
}
bool PresetStore::load(std::size_t slot) noexcept {
    return slot < slots && edit(presets_[slot]);
}
bool PresetStore::commit(std::size_t slot) noexcept {
    if (slot >= slots || generation_ == std::numeric_limits<std::uint32_t>::max()) return false;
    presets_[slot] = audition_; ++generation_;
    return true;
}
std::vector<std::uint8_t> PresetStore::backup() const {
    std::vector<std::uint8_t> bytes(header_size + payload_size + 4, 0);
    const std::array<std::uint8_t, 8> magic{{'F','M','E','R','P','S','T',1}};
    std::copy(magic.begin(), magic.end(), bytes.begin());
    put32(bytes.data() + 8, generation_); put32(bytes.data() + 12, payload_size);
    for (std::size_t slot = 0; slot < slots; ++slot)
        std::copy(presets_[slot].vced.begin(), presets_[slot].vced.end(), bytes.begin() + header_size + slot * 155);
    put32(bytes.data() + header_size + payload_size, crc32(bytes.data(), header_size + payload_size));
    return bytes;
}
bool PresetStore::restore(const std::uint8_t* bytes, std::size_t size, std::string& error) {
    const std::array<std::uint8_t, 8> magic{{'F','M','E','R','P','S','T',1}};
    if (!bytes || size != header_size + payload_size + 4) { error = "Wrong preset record length"; return false; }
    if (!std::equal(magic.begin(), magic.end(), bytes)) { error = "Unsupported preset record version/magic"; return false; }
    if (get32(bytes + 12) != payload_size) { error = "Wrong preset payload length"; return false; }
    if (get32(bytes + header_size + payload_size) != crc32(bytes, header_size + payload_size)) {
        error = "Preset record CRC mismatch"; return false;
    }
    std::array<Patch, slots> staged{};
    for (std::size_t slot = 0; slot < slots; ++slot) {
        std::copy_n(bytes + header_size + slot * 155, 155, staged[slot].vced.begin());
        if (!valid(staged[slot])) { error = "Invalid preset at slot " + std::to_string(slot); return false; }
    }
    presets_ = staged; generation_ = get32(bytes + 8);
    // An import changes saved data only; the player's temporary audition remains.
    error.clear(); return true;
}
} // namespace fmer
