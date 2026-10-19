#include "patch.hpp"
#include "parameters.hpp"

#include <algorithm>
#include <stdexcept>

namespace fmer {
namespace {

// DX7 compatibility field layout. The corpus dx7_bank.py is the initial
// specification seed; see docs/CODEC.md for the independent MSFA comparison.
constexpr std::array<std::uint8_t, 21> kOperatorMax{
    99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99,
    3, 3, 7, 3, 7, 99, 1, 31, 99, 14};
constexpr std::array<std::uint8_t, 19> kGlobalMax{
    99, 99, 99, 99, 99, 99, 99, 99, 31, 7, 1,
    99, 99, 99, 99, 1, 5, 7, 48};
constexpr std::array<const char*, 21> kOperatorNames{
    "EG rate 1", "EG rate 2", "EG rate 3", "EG rate 4",
    "EG level 1", "EG level 2", "EG level 3", "EG level 4",
    "Keyboard breakpoint", "Keyboard left depth", "Keyboard right depth",
    "Keyboard left curve", "Keyboard right curve", "EG rate scaling",
    "Amplitude modulation sensitivity", "Key velocity sensitivity",
    "Output level", "Oscillator mode", "Frequency coarse", "Frequency fine",
    "Detune"};
constexpr std::array<const char*, 19> kGlobalNames{
    "Pitch EG rate 1", "Pitch EG rate 2", "Pitch EG rate 3", "Pitch EG rate 4",
    "Pitch EG level 1", "Pitch EG level 2", "Pitch EG level 3", "Pitch EG level 4",
    "Algorithm", "Feedback", "Oscillator key sync", "LFO speed", "LFO delay",
    "LFO pitch modulation depth", "LFO amplitude modulation depth", "LFO key sync",
    "LFO waveform", "Pitch modulation sensitivity", "Transpose"};

constexpr Patch init_patch_value() {
    Patch patch{};
    for (std::size_t op = 0; op < 6; ++op) {
        const auto base = op * 21;
        patch.vced[base] = 99;
        patch.vced[base + 1] = 99;
        patch.vced[base + 2] = 99;
        patch.vced[base + 3] = 70;
        patch.vced[base + 4] = 99;
        patch.vced[base + 5] = 99;
        patch.vced[base + 6] = 99;
        patch.vced[base + 7] = 0;
        patch.vced[base + 8] = 39;
        patch.vced[base + 18] = 1;
        patch.vced[base + 20] = 7;
    }
    patch.vced[5 * 21 + 16] = 80;  // OP1 is the sole audible carrier.
    for (std::size_t i = 126; i < 130; ++i) patch.vced[i] = 99;
    for (std::size_t i = 130; i < 134; ++i) patch.vced[i] = 50;
    patch.vced[136] = 1;
    patch.vced[137] = 35;
    patch.vced[141] = 1;
    patch.vced[144] = 24;
    constexpr char name[] = "FMER INIT ";
    for (std::size_t i = 0; i < 10; ++i) {
        patch.vced[145 + i] = static_cast<std::uint8_t>(name[i]);
    }
    return patch;
}

constexpr Patch kInitPatch = init_patch_value();

constexpr std::array<Parameter, kParameterCount> make_registry() {
    std::array<Parameter, kParameterCount> result{};
    for (std::size_t id = 0; id < kParameterCount; ++id) {
        const bool is_operator = id < 126;
        result[id] = Parameter{
            static_cast<std::uint16_t>(id),
            is_operator ? kOperatorNames[id % 21] : kGlobalNames[id - 126],
            static_cast<std::uint8_t>(is_operator ? 6 - id / 21 : 0),
            0,
            is_operator ? kOperatorMax[id % 21] : kGlobalMax[id - 126],
            kInitPatch.vced[id]};
    }
    return result;
}

constexpr auto kRegistry = make_registry();

std::uint8_t checksum(const std::uint8_t* data, std::size_t size) noexcept {
    std::uint32_t sum = 0;
    for (std::size_t i = 0; i < size; ++i) sum += data[i];
    return static_cast<std::uint8_t>((128U - (sum & 127U)) & 127U);
}

bool fail(std::string& error, const std::string& reason) {
    error = reason;
    return false;
}

void validate_channel(std::uint8_t channel) {
    if (channel > 15) {
        throw std::invalid_argument("SysEx channel nibble must be 0..15");
    }
}

}  // namespace

Patch make_init_patch() noexcept { return kInitPatch; }

PatchValidation validate_patch(const Patch& patch) noexcept {
    for (std::size_t i = 0; i < kVcedSize; ++i) {
        const std::uint8_t maximum = i < kParameterCount ? kRegistry[i].maximum : 127;
        if (patch.vced[i] > maximum) return {false, i, patch.vced[i], maximum};
    }
    return {true, kVcedSize, 0, 0};
}

bool validate_patch(const Patch& patch, std::string& error) {
    const auto result = validate_patch(patch);
    if (!result.valid) {
        return fail(error, "VCED byte " + std::to_string(result.index) +
                           ": value " + std::to_string(result.value) +
                           " exceeds " + std::to_string(result.maximum));
    }
    error.clear();
    return true;
}

const std::array<Parameter, kParameterCount>& parameter_registry() noexcept {
    return kRegistry;
}

const Parameter* find_parameter(std::uint16_t id) noexcept {
    return id < kParameterCount ? &kRegistry[id] : nullptr;
}

bool set_parameter(Patch& patch, std::uint16_t id, int value) noexcept {
    const auto* parameter = find_parameter(id);
    if (parameter == nullptr || value < parameter->minimum || value > parameter->maximum) {
        return false;
    }
    Patch candidate = patch;
    candidate.vced[id] = static_cast<std::uint8_t>(value);
    if (!validate_patch(candidate).valid) return false;
    patch = candidate;
    return true;
}

bool edit_parameter(Patch& patch, std::uint16_t id, int value, std::string& error) {
    const auto* parameter = find_parameter(id);
    if (parameter == nullptr) return fail(error, "Unknown parameter ID " + std::to_string(id));
    if (value < parameter->minimum || value > parameter->maximum) {
        return fail(error, "Parameter " + std::to_string(id) + " (" + parameter->name +
                           "): value " + std::to_string(value) + " outside " +
                           std::to_string(parameter->minimum) + ".." +
                           std::to_string(parameter->maximum));
    }
    Patch candidate = patch;
    candidate.vced[id] = static_cast<std::uint8_t>(value);
    if (!validate_patch(candidate, error)) return false;
    patch = candidate;
    return true;
}

bool pack_vmem(const Patch& patch, std::array<std::uint8_t, kVmemSize>& output,
               std::string& error) {
    if (!validate_patch(patch, error)) return false;
    const auto& v = patch.vced;
    std::array<std::uint8_t, kVmemSize> packed{};
    for (std::size_t op = 0; op < 6; ++op) {
        const auto src = op * 21;
        const auto dst = op * 17;
        std::copy_n(v.begin() + src, 11, packed.begin() + dst);
        packed[dst + 11] = static_cast<std::uint8_t>(v[src + 11] | (v[src + 12] << 2));
        packed[dst + 12] = static_cast<std::uint8_t>(v[src + 13] | (v[src + 20] << 3));
        packed[dst + 13] = static_cast<std::uint8_t>(v[src + 14] | (v[src + 15] << 2));
        packed[dst + 14] = v[src + 16];
        packed[dst + 15] = static_cast<std::uint8_t>(v[src + 17] | (v[src + 18] << 1));
        packed[dst + 16] = v[src + 19];
    }
    std::copy_n(v.begin() + 126, 8, packed.begin() + 102);
    packed[110] = v[134];
    packed[111] = static_cast<std::uint8_t>(v[135] | (v[136] << 3));
    std::copy_n(v.begin() + 137, 4, packed.begin() + 112);
    packed[116] = static_cast<std::uint8_t>(v[141] | (v[142] << 1) | (v[143] << 4));
    packed[117] = v[144];
    std::copy_n(v.begin() + 145, 10, packed.begin() + 118);
    output = packed;
    error.clear();
    return true;
}

bool unpack_vmem(const std::uint8_t* input, std::size_t size,
                 Patch& output, std::string& error) {
    if (size != kVmemSize) return fail(error, "VMEM payload must contain exactly 128 bytes");
    if (input == nullptr) return fail(error, "VMEM input is null");
    for (std::size_t i = 0; i < size; ++i) {
        if (input[i] > 127) return fail(error, "VMEM contains a non-seven-bit byte at " + std::to_string(i));
    }
    Patch candidate{};
    auto& v = candidate.vced;
    for (std::size_t op = 0; op < 6; ++op) {
        const auto src = op * 17;
        const auto dst = op * 21;
        if ((input[src + 11] & 0x70U) != 0 ||
            (input[src + 13] & 0x60U) != 0 ||
            (input[src + 15] & 0x40U) != 0) {
            return fail(error, "VMEM reserved bits set in operator " + std::to_string(6 - op));
        }
        std::copy_n(input + src, 11, v.begin() + dst);
        v[dst + 11] = input[src + 11] & 3U;
        v[dst + 12] = (input[src + 11] >> 2) & 3U;
        v[dst + 13] = input[src + 12] & 7U;
        v[dst + 14] = input[src + 13] & 3U;
        v[dst + 15] = (input[src + 13] >> 2) & 7U;
        v[dst + 16] = input[src + 14];
        v[dst + 17] = input[src + 15] & 1U;
        v[dst + 18] = (input[src + 15] >> 1) & 31U;
        v[dst + 19] = input[src + 16];
        v[dst + 20] = (input[src + 12] >> 3) & 15U;
    }
    if (input[110] > 31 || (input[111] & 0x70U) != 0) {
        return fail(error, "VMEM reserved global bits are set");
    }
    std::copy_n(input + 102, 8, v.begin() + 126);
    v[134] = input[110];
    v[135] = input[111] & 7U;
    v[136] = (input[111] >> 3) & 1U;
    std::copy_n(input + 112, 4, v.begin() + 137);
    v[141] = input[116] & 1U;
    v[142] = (input[116] >> 1) & 7U;
    v[143] = (input[116] >> 4) & 7U;
    v[144] = input[117];
    std::copy_n(input + 118, 10, v.begin() + 145);
    if (!validate_patch(candidate, error)) return false;
    output = candidate;
    error.clear();
    return true;
}

bool decode_sysex(const std::uint8_t* input, std::size_t size,
                  std::array<Patch, kBankSize>& output,
                  std::size_t& count, std::string& error) {
    if (size != 163 && size != 4104) {
        return fail(error, "Expected exactly one 163-byte single or 4104-byte bank SysEx message");
    }
    if (input == nullptr) return fail(error, "SysEx input is null");
    if (input[0] != 0xf0 || input[1] != 0x43 || input[size - 1] != 0xf7) {
        return fail(error, "Invalid Yamaha SysEx framing or manufacturer");
    }
    if (input[2] > 15) return fail(error, "Unsupported SysEx substatus/channel; expected 0..15");
    for (std::size_t i = 1; i + 1 < size; ++i) {
        if (input[i] > 127) return fail(error, "Non-seven-bit SysEx byte at " + std::to_string(i));
    }
    const bool single = size == 163;
    if ((single && (input[3] != 0 || input[4] != 1 || input[5] != 27)) ||
        (!single && (input[3] != 9 || input[4] != 32 || input[5] != 0))) {
        return fail(error, "Unsupported SysEx format or declared payload length");
    }
    if (checksum(input + 6, size - 8) != input[size - 2]) {
        return fail(error, "SysEx payload checksum mismatch");
    }
    std::array<Patch, kBankSize> candidates{};
    const std::size_t decoded_count = single ? 1 : kBankSize;
    if (single) {
        std::copy_n(input + 6, kVcedSize, candidates[0].vced.begin());
        if (!validate_patch(candidates[0], error)) return false;
    } else {
        for (std::size_t i = 0; i < kBankSize; ++i) {
            if (!unpack_vmem(input + 6 + i * kVmemSize, kVmemSize, candidates[i], error)) {
                error = "Bank voice " + std::to_string(i + 1) + ": " + error;
                return false;
            }
        }
    }
    // Publish only after the whole message has passed validation.
    std::copy_n(candidates.begin(), decoded_count, output.begin());
    count = decoded_count;
    error.clear();
    return true;
}

std::vector<std::uint8_t> encode_single(const Patch& patch, std::uint8_t channel) {
    validate_channel(channel);
    std::string error;
    if (!validate_patch(patch, error)) throw std::invalid_argument(error);
    std::vector<std::uint8_t> result;
    result.reserve(163);
    result.insert(result.end(), {0xf0, 0x43, channel, 0, 1, 27});
    result.insert(result.end(), patch.vced.begin(), patch.vced.end());
    result.push_back(checksum(patch.vced.data(), patch.vced.size()));
    result.push_back(0xf7);
    return result;
}

std::vector<std::uint8_t> encode_bank(const std::array<Patch, kBankSize>& patches,
                                    std::uint8_t channel) {
    validate_channel(channel);
    std::vector<std::uint8_t> result;
    result.reserve(4104);
    result.insert(result.end(), {0xf0, 0x43, channel, 9, 32, 0});
    std::array<std::uint8_t, kVmemSize> packed{};
    std::string error;
    for (std::size_t i = 0; i < patches.size(); ++i) {
        if (!pack_vmem(patches[i], packed, error)) {
            throw std::invalid_argument("Bank voice " + std::to_string(i + 1) + ": " + error);
        }
        result.insert(result.end(), packed.begin(), packed.end());
    }
    result.push_back(checksum(result.data() + 6, 4096));
    result.push_back(0xf7);
    return result;
}

}  // namespace fmer
