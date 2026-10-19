#pragma once
#include "patch.hpp"
#include <array>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace fmer {
// Musical preset data only. This deliberately has no addresses or device writes.
class PresetStore {
public:
    static constexpr std::size_t slots = 128;
    PresetStore();
    const Patch& audition() const noexcept { return audition_; }
    const Patch* saved(std::size_t slot) const noexcept;
    bool edit(const Patch& patch) noexcept;
    bool undo() noexcept;
    bool load(std::size_t slot) noexcept;
    bool commit(std::size_t slot) noexcept;
    std::uint32_t generation() const noexcept { return generation_; }
    std::vector<std::uint8_t> backup() const;
    // Validate the entire incoming record before publishing any state.
    bool restore(const std::uint8_t* bytes, std::size_t size, std::string& error);
private:
    std::array<Patch, slots> presets_{};
    Patch audition_{};
    Patch previous_{};
    bool has_undo_{false};
    std::uint32_t generation_{0};
};
} // namespace fmer
