#pragma once

#include "synth.hpp"
#include <cstddef>

namespace fmer {

inline constexpr std::size_t factory_fm_preset_count = 32;
inline constexpr std::size_t factory_va_preset_count = 32;
inline constexpr std::size_t factory_preset_count = 64;

// Original FMER recipes, not an imported DX7/vendor sound bank. These values
// describe a sound only: recall must not silently overwrite patterns, routing,
// clock, master volume, or effects. Names fit the ten-byte DX7 name field.
struct FactoryPreset {
    const char* name{};
    SynthEngine engine{SynthEngine::fm};
    Patch patch{};
    VaParameters va{};
    bool lfo_enabled{false}; // sound-owned gate; rates/depths remain ready when off
};

// Immutable name storage; nullptr denotes an invalid index. Loading constructs
// one bounded value without allocating. Failure preserves output byte values.
const char* factory_preset_name(std::size_t index) noexcept;
bool load_factory_preset(std::size_t index, FactoryPreset& output) noexcept;

// Stable program IDs preserve the original bank positions: FM0..7, VA8..15,
// additional FM16..39 and VA40..63. A browser can present two contiguous
// 32-sound banks using these helpers without renumbering saved/received IDs.
// Invalid IDs return engine255 / bank index32; invalid bank requests return64.
SynthEngine factory_preset_engine(std::size_t index) noexcept;
std::size_t factory_preset_bank_index(std::size_t index) noexcept;
std::size_t factory_preset_id(SynthEngine engine, std::size_t bank_index) noexcept;

} // namespace fmer
