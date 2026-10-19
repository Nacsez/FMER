#pragma once

#include "patch.hpp"

namespace fmer {

// IDs 0..144 are permanently assigned to their numeric VCED byte offsets.
// Names (145..154) are archival bytes, not numeric synthesizer parameters.
struct Parameter {
    std::uint16_t id;
    const char* name;
    std::uint8_t operator_number;  // 6..1 for operator fields, 0 for globals.
    std::uint8_t minimum;
    std::uint8_t maximum;
    std::uint8_t default_value;
};

const std::array<Parameter, kParameterCount>& parameter_registry() noexcept;
const Parameter* find_parameter(std::uint16_t id) noexcept;

// Validates the complete candidate voice. Rejection leaves it unchanged.
// No allocation, locks, logging or exceptions; suitable for a bounded command
// application step, with synchronization/voice snapshots owned by the caller.
bool set_parameter(Patch& patch, std::uint16_t id, int value) noexcept;

// Offline counterpart with an explanatory error; may allocate.
bool edit_parameter(Patch& patch, std::uint16_t id, int value,
                    std::string& error);

}  // namespace fmer
