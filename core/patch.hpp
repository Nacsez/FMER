#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace fmer {

inline constexpr std::size_t kVcedSize = 155;
inline constexpr std::size_t kVmemSize = 128;
inline constexpr std::size_t kParameterCount = 145;
inline constexpr std::size_t kBankSize = 32;

// Compatibility byte order is OP6, OP5, ... OP1, followed by globals/name.
// This bounded value type owns its complete voice; it contains no pointers.
struct Patch {
    std::array<std::uint8_t, kVcedSize> vced{};
};

struct PatchValidation {
    bool valid;
    std::size_t index;
    std::uint8_t value;
    std::uint8_t maximum;
};

Patch make_init_patch() noexcept;
PatchValidation validate_patch(const Patch& patch) noexcept;
bool validate_patch(const Patch& patch, std::string& error);

// Offline codecs: error reporting and returned vectors may allocate.
// Decode/pack/unpack preserve outputs (including count) on every failure.
bool pack_vmem(const Patch& patch,
               std::array<std::uint8_t, kVmemSize>& output,
               std::string& error);
bool unpack_vmem(const std::uint8_t* input, std::size_t size,
                 Patch& output, std::string& error);
inline bool unpack_vmem(const std::array<std::uint8_t, kVmemSize>& input,
                        Patch& output, std::string& error) {
    return unpack_vmem(input.data(), input.size(), output, error);
}
bool decode_sysex(const std::uint8_t* input, std::size_t size,
                  std::array<Patch, kBankSize>& output,
                  std::size_t& count, std::string& error);

// Throws std::invalid_argument for an invalid patch or channel > 15.
std::vector<std::uint8_t> encode_single(const Patch& patch,
                                       std::uint8_t channel = 0);
std::vector<std::uint8_t> encode_bank(
    const std::array<Patch, kBankSize>& patches, std::uint8_t channel = 0);

}  // namespace fmer
