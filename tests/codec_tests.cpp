#include "patch.hpp"
#include "parameters.hpp"

#include <algorithm>
#include <array>
#include <cstdint>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <utility>
#include <vector>

#if defined(FMER_CODEC_MSFA_REFERENCE)
// Link the independently acquired upstream patch.cc, without copying its logic.
void UnpackPatch(const char bulk[128], char patch[156]);
#endif

namespace {
using fmer::Patch;
using Bank = std::array<Patch, fmer::kBankSize>;
using Packed = std::array<std::uint8_t, fmer::kVmemSize>;

#define REQUIRE(expression) do { \
    if (!(expression)) throw std::runtime_error( \
        std::string(#expression) + " (line " + std::to_string(__LINE__) + ")"); \
} while (false)

std::size_t reference_comparisons = 0;

bool same(const Bank& a, const Bank& b) {
    for (std::size_t i = 0; i < a.size(); ++i) {
        if (a[i].vced != b[i].vced) return false;
    }
    return true;
}

Bank sentinel_bank() {
    Bank result{};
    for (std::size_t i = 0; i < result.size(); ++i) {
        result[i] = fmer::make_init_patch();
        result[i].vced[145] = static_cast<std::uint8_t>(32 + i);
    }
    return result;
}

void reference_compare(const Packed& packed, const Patch& expected) {
#if defined(FMER_CODEC_MSFA_REFERENCE)
    std::array<char, 128> input{};
    std::array<char, 156> output{};
    for (std::size_t i = 0; i < input.size(); ++i) input[i] = static_cast<char>(packed[i]);
    UnpackPatch(input.data(), output.data());
    for (std::size_t i = 0; i < expected.vced.size(); ++i) {
        REQUIRE(static_cast<std::uint8_t>(output[i]) == expected.vced[i]);
    }
    REQUIRE(output[155] == 0x3f);
    ++reference_comparisons;
#else
    (void)packed;
    (void)expected;
#endif
}

void roundtrip(const Patch& patch) {
    std::string error = "previous error";
    Packed packed{};
    REQUIRE(fmer::pack_vmem(patch, packed, error));
    REQUIRE(error.empty());
    Patch decoded{};
    REQUIRE(fmer::unpack_vmem(packed, decoded, error));
    REQUIRE(decoded.vced == patch.vced);
    Packed repacked{};
    REQUIRE(fmer::pack_vmem(decoded, repacked, error));
    REQUIRE(repacked == packed);
    reference_compare(packed, patch);
}

void repair_checksum(std::vector<std::uint8_t>& message) {
    unsigned sum = 0;
    for (std::size_t i = 6; i + 2 < message.size(); ++i) sum += message[i];
    message[message.size() - 2] = static_cast<std::uint8_t>((0U - sum) & 127U);
}

void reject(const std::uint8_t* data, std::size_t size) {
    Bank output = sentinel_bank();
    const auto before = output;
    std::size_t count = 17;
    std::string error;
    REQUIRE(!fmer::decode_sysex(data, size, output, count, error));
    REQUIRE(!error.empty());
    REQUIRE(count == 17);
    REQUIRE(same(output, before));
}

void reject(const std::vector<std::uint8_t>& message) { reject(message.data(), message.size()); }

void test_init() {
    static_assert(sizeof(Patch) == 155, "Patch must own only bounded VCED bytes");
    static_assert(std::is_trivially_copyable<Patch>::value, "Voice snapshots must be values");
    const auto patch = fmer::make_init_patch();
    REQUIRE(fmer::validate_patch(patch).valid);
    REQUIRE(patch.vced[134] == 0);
    unsigned audible = 0;
    for (std::size_t op = 0; op < 6; ++op) {
        if (patch.vced[op * 21 + 16] != 0) ++audible;
        REQUIRE(patch.vced[op * 21 + 18] == 1);
        REQUIRE(patch.vced[op * 21 + 20] == 7);
    }
    REQUIRE(audible == 1);
    REQUIRE(patch.vced[121] == 80);  // OP1, not OP6.
    REQUIRE(patch.vced[108] == 70);
    REQUIRE(patch.vced[112] == 0);
    REQUIRE(patch.vced[144] == 24);
    REQUIRE(std::string(patch.vced.begin() + 145, patch.vced.end()) == "FMER INIT ");
    roundtrip(patch);
}

void test_registry_and_edits() {
    REQUIRE(fmer::parameter_registry().size() == 145);
    const auto initial = fmer::make_init_patch();
    for (const auto& parameter : fmer::parameter_registry()) {
        const auto id = parameter.id;
        REQUIRE(fmer::find_parameter(id) == &parameter);
        REQUIRE(parameter.minimum == 0);
        REQUIRE(parameter.name != nullptr && parameter.name[0] != '\0');
        REQUIRE(parameter.operator_number == (id < 126 ? 6 - id / 21 : 0));
        REQUIRE(parameter.default_value == initial.vced[id]);
        auto patch = initial;
        REQUIRE(fmer::set_parameter(patch, id, parameter.minimum));
        REQUIRE(patch.vced[id] == parameter.minimum);
        REQUIRE(fmer::set_parameter(patch, id, parameter.maximum));
        REQUIRE(patch.vced[id] == parameter.maximum);
        auto expected = initial;
        expected.vced[id] = parameter.maximum;
        REQUIRE(patch.vced == expected.vced);
        const auto before = patch;
        REQUIRE(!fmer::set_parameter(patch, id, -1));
        REQUIRE(patch.vced == before.vced);
        REQUIRE(!fmer::set_parameter(patch, id, parameter.maximum + 1));
        REQUIRE(patch.vced == before.vced);
        std::string error;
        REQUIRE(!fmer::edit_parameter(patch, id, 9999, error));
        REQUIRE(!error.empty());
        REQUIRE(patch.vced == before.vced);
    }
    auto patch = initial;
    REQUIRE(fmer::find_parameter(145) == nullptr);
    REQUIRE(fmer::find_parameter(65535) == nullptr);
    REQUIRE(!fmer::set_parameter(patch, 145, 32));
    REQUIRE(!fmer::set_parameter(patch, 65535, 0));
    REQUIRE(patch.vced == initial.vced);
    std::string error = "old";
    REQUIRE(fmer::edit_parameter(patch, 134, 31, error));
    REQUIRE(error.empty());
    REQUIRE(patch.vced[134] == 31);
    patch.vced[0] = 100;
    const auto corrupt = patch;
    REQUIRE(!fmer::set_parameter(patch, 134, 0));
    REQUIRE(patch.vced == corrupt.vced);
    REQUIRE(!fmer::edit_parameter(patch, 134, 0, error));
    REQUIRE(patch.vced == corrupt.vced);
}

void test_golden_bitfields_and_operator_order() {
    Patch patch{};
    // Explicit independent sentinels distinguish the six serialized operators.
    for (std::size_t op = 0; op < 6; ++op) {
        patch.vced[op * 21] = static_cast<std::uint8_t>(91 - op);
        patch.vced[op * 21 + 16] = static_cast<std::uint8_t>(31 + op);
    }
    const std::array<std::uint8_t, 10> operator_fields{2, 3, 5, 2, 6, 99, 1, 17, 42, 9};
    std::copy(operator_fields.begin(), operator_fields.end(), patch.vced.begin() + 11);
    const std::array<std::uint8_t, 11> globals{31, 7, 1, 11, 22, 33, 44, 1, 5, 7, 48};
    std::copy(globals.begin(), globals.end(), patch.vced.begin() + 134);
    Packed packed{};
    std::string error;
    REQUIRE(fmer::pack_vmem(patch, packed, error));
    const std::array<std::uint8_t, 6> expected_op{14, 77, 26, 99, 35, 42};
    REQUIRE(std::equal(expected_op.begin(), expected_op.end(), packed.begin() + 11));
    const std::array<std::uint8_t, 8> expected_globals{31, 15, 11, 22, 33, 44, 123, 48};
    REQUIRE(std::equal(expected_globals.begin(), expected_globals.end(), packed.begin() + 110));
    for (std::size_t op = 0; op < 6; ++op) REQUIRE(packed[op * 17] == 91 - op);
    REQUIRE(packed[5 * 17 + 14] == 36);
    roundtrip(patch);
}

void test_extrema_and_deterministic_voices() {
    Patch low{};
    Patch high{};
    for (const auto& parameter : fmer::parameter_registry()) high.vced[parameter.id] = parameter.maximum;
    std::fill(high.vced.begin() + 145, high.vced.end(), static_cast<std::uint8_t>(127));
    roundtrip(low);
    roundtrip(high);
    std::uint32_t state = 0x46a1c09dU;
    for (unsigned voice = 0; voice < 256; ++voice) {
        Patch patch{};
        for (std::size_t i = 0; i < patch.vced.size(); ++i) {
            state = state * 1664525U + 1013904223U;
            const unsigned range = i < 145 ? fmer::parameter_registry()[i].maximum + 1U : 128U;
            patch.vced[i] = static_cast<std::uint8_t>((state >> 16) % range);
        }
        roundtrip(patch);
    }
}

void test_all_algorithms() {
    for (std::uint8_t algorithm = 0; algorithm < 32; ++algorithm) {
        auto patch = fmer::make_init_patch();
        REQUIRE(fmer::set_parameter(patch, 134, algorithm));
        roundtrip(patch);
        const auto message = fmer::encode_single(patch);
        Bank output{};
        std::size_t count = 0;
        std::string error;
        REQUIRE(fmer::decode_sysex(message.data(), message.size(), output, count, error));
        REQUIRE(count == 1);
        REQUIRE(output[0].vced[134] == algorithm);
    }
}

void test_single_envelope_channels() {
    const auto patch = fmer::make_init_patch();
    for (std::uint8_t channel = 0; channel < 16; ++channel) {
        const auto message = fmer::encode_single(patch, channel);
        REQUIRE(message.size() == 163);
        const std::array<std::uint8_t, 6> header{0xf0, 0x43, channel, 0, 1, 27};
        REQUIRE(std::equal(header.begin(), header.end(), message.begin()));
        REQUIRE(message.back() == 0xf7);
        unsigned sum = message[161];
        for (const auto value : patch.vced) sum += value;
        REQUIRE((sum & 127U) == 0);
        Bank output = sentinel_bank();
        const auto untouched_tail = output[1];
        std::size_t count = 32;
        std::string error = "old failure";
        REQUIRE(fmer::decode_sysex(message.data(), message.size(), output, count, error));
        REQUIRE(count == 1 && error.empty());
        REQUIRE(output[0].vced == patch.vced);
        REQUIRE(output[1].vced == untouched_tail.vced);
    }
}

void test_bank_envelope_and_order() {
    auto bank = sentinel_bank();
    for (std::size_t i = 0; i < bank.size(); ++i) bank[i].vced[134] = static_cast<std::uint8_t>(i);
    const auto message = fmer::encode_bank(bank, 15);
    REQUIRE(message.size() == 4104);
    const std::array<std::uint8_t, 6> header{0xf0, 0x43, 15, 9, 32, 0};
    REQUIRE(std::equal(header.begin(), header.end(), message.begin()));
    REQUIRE(message.back() == 0xf7);
    for (std::size_t i = 0; i < bank.size(); ++i) {
        REQUIRE(message[6 + i * 128 + 110] == i);
        REQUIRE(message[6 + i * 128 + 118] == 32 + i);
        roundtrip(bank[i]);
    }
    Bank output{};
    std::size_t count = 0;
    std::string error;
    REQUIRE(fmer::decode_sysex(message.data(), message.size(), output, count, error));
    REQUIRE(count == 32);
    REQUIRE(same(output, bank));
    REQUIRE(fmer::encode_bank(output, 15) == message);
}

void test_names_archive_all_seven_bit_values() {
    for (unsigned value = 0; value < 128; ++value) {
        auto patch = fmer::make_init_patch();
        std::fill(patch.vced.begin() + 145, patch.vced.end(), static_cast<std::uint8_t>(value));
        roundtrip(patch);
    }
}

void test_null_and_bad_lengths() {
    reject(nullptr, 0);
    reject(nullptr, 163);
    reject(nullptr, 4104);
    reject(nullptr, std::numeric_limits<std::size_t>::max());
    const auto original = fmer::encode_single(fmer::make_init_patch());
    for (std::size_t length = 0; length < original.size(); ++length) reject(original.data(), length);
    auto trailing = original;
    trailing.push_back(0);
    reject(trailing);
    auto concatenated = original;
    concatenated.insert(concatenated.end(), original.begin(), original.end());
    reject(concatenated);
    auto bank = fmer::encode_bank(sentinel_bank());
    bank.pop_back();
    reject(bank);
    auto output = fmer::make_init_patch();
    const auto before = output;
    std::string error;
    REQUIRE(!fmer::unpack_vmem(nullptr, 128, output, error));
    REQUIRE(output.vced == before.vced);
    REQUIRE(!fmer::unpack_vmem(nullptr, std::numeric_limits<std::size_t>::max(), output, error));
    REQUIRE(output.vced == before.vced);
}

void test_bad_headers_and_checksum() {
    const auto original = fmer::encode_single(fmer::make_init_patch());
    for (const auto offset : {0U, 1U, 3U, 4U, 5U, 161U, 162U}) {
        auto corrupt = original;
        corrupt[offset] ^= 1U;
        reject(corrupt);
    }
    for (const auto substatus : {16U, 32U, 127U, 128U, 255U}) {
        auto corrupt = original;
        corrupt[2] = static_cast<std::uint8_t>(substatus);
        reject(corrupt);
    }
    auto high_bit = original;
    high_bit[6 + 145] = 128;
    repair_checksum(high_bit);
    reject(high_bit);
    // A file codec rejects realtime interleaving; a streaming MIDI parser
    // removes/dispatches realtime events before calling this API.
    auto interleaved = original;
    interleaved.insert(interleaved.begin() + 10, 0xf8);
    reject(interleaved);
}

void test_every_parameter_rejection_is_atomic() {
    const auto initial = fmer::make_init_patch();
    for (const auto& parameter : fmer::parameter_registry()) {
        auto patch = initial;
        patch.vced[parameter.id] = static_cast<std::uint8_t>(parameter.maximum + 1);
        const auto validation = fmer::validate_patch(patch);
        REQUIRE(!validation.valid);
        REQUIRE(validation.index == parameter.id);
        Packed packed{};
        packed.fill(0x55);
        const auto before = packed;
        std::string error;
        REQUIRE(!fmer::pack_vmem(patch, packed, error));
        REQUIRE(packed == before);
        auto message = fmer::encode_single(initial);
        message[6 + parameter.id] = patch.vced[parameter.id];
        repair_checksum(message);
        reject(message);
    }
}

void test_reserved_bits_and_packed_ranges() {
    Packed original{};
    std::string error;
    REQUIRE(fmer::pack_vmem(fmer::make_init_patch(), original, error));
    const auto reject_packed = [&](const Packed& packed) {
        auto output = fmer::make_init_patch();
        const auto before = output;
        REQUIRE(!fmer::unpack_vmem(packed, output, error));
        REQUIRE(!error.empty());
        REQUIRE(output.vced == before.vced);
    };
    for (std::size_t op = 0; op < 6; ++op) {
        for (unsigned bit : {16U, 32U, 64U}) {
            auto corrupt = original;
            corrupt[op * 17 + 11] |= static_cast<std::uint8_t>(bit);
            reject_packed(corrupt);
        }
        for (unsigned bit : {32U, 64U}) {
            auto corrupt = original;
            corrupt[op * 17 + 13] |= static_cast<std::uint8_t>(bit);
            reject_packed(corrupt);
        }
        auto corrupt = original;
        corrupt[op * 17 + 15] |= 64;
        reject_packed(corrupt);
        corrupt = original;
        corrupt[op * 17 + 12] = 15U << 3;  // Detune 15 is not legal.
        reject_packed(corrupt);
    }
    for (const auto offset : {110U, 111U}) {
        auto corrupt = original;
        corrupt[offset] |= 64;
        reject_packed(corrupt);
    }
    auto corrupt = original;
    corrupt[116] = 6U << 1;  // Only LFO waveform 0..5 is legal.
    reject_packed(corrupt);
    corrupt = original;
    corrupt[127] = 128;
    reject_packed(corrupt);
}

void test_late_bank_failure_publishes_nothing() {
    auto message = fmer::encode_bank(sentinel_bank());
    message[6 + 31 * 128 + 11] |= 16;
    repair_checksum(message);
    reject(message);
}

void test_encoders_reject_invalid_input() {
    const auto throws_invalid = [](const auto& action) {
        bool caught = false;
        try { action(); } catch (const std::invalid_argument&) { caught = true; }
        REQUIRE(caught);
    };
    auto patch = fmer::make_init_patch();
    throws_invalid([&] { (void)fmer::encode_single(patch, 16); });
    throws_invalid([&] { (void)fmer::encode_bank(sentinel_bank(), 255); });
    patch.vced[134] = 32;
    throws_invalid([&] { (void)fmer::encode_single(patch); });
    auto bank = sentinel_bank();
    bank.back().vced[145] = 128;
    throws_invalid([&] { (void)fmer::encode_bank(bank); });
}

}  // namespace

int main() {
    const std::array<std::pair<const char*, void (*)()>, 14> tests{{
        {"original bounded INIT voice", test_init},
        {"145 stable parameters and atomic edits", test_registry_and_edits},
        {"golden bitfields and serialized operator order", test_golden_bitfields_and_operator_order},
        {"extrema and 256 deterministic synthetic voices", test_extrema_and_deterministic_voices},
        {"all 32 algorithm values roundtrip", test_all_algorithms},
        {"single envelope and all channel nibbles", test_single_envelope_channels},
        {"32-voice bank envelope and voice order", test_bank_envelope_and_order},
        {"all archival seven-bit name values", test_names_archive_all_seven_bit_values},
        {"null pointers and malformed lengths", test_null_and_bad_lengths},
        {"framing substatus checksum and seven-bit errors", test_bad_headers_and_checksum},
        {"all numeric fields reject overflow atomically", test_every_parameter_rejection_is_atomic},
        {"reserved packed bits and semantic packed ranges", test_reserved_bits_and_packed_ranges},
        {"late bank failure publishes nothing", test_late_bank_failure_publishes_nothing},
        {"encoders reject invalid channel and voice", test_encoders_reject_invalid_input}
    }};
    std::size_t passed = 0;
    for (const auto& test : tests) {
        try {
            test.second();
            ++passed;
            std::cout << "PASS codec: " << test.first << '\n';
        } catch (const std::exception& error) {
            std::cerr << "FAIL codec: " << test.first << ": " << error.what() << '\n';
        }
    }
    std::cout << "Codec groups passed " << passed << '/' << tests.size() << '\n';
#if defined(FMER_CODEC_MSFA_REFERENCE)
    std::cout << "Independent upstream MSFA unpack comparisons: " << reference_comparisons << '\n';
#else
    std::cout << "Independent upstream MSFA comparison: disabled in this build\n";
#endif
    return passed == tests.size() ? 0 : 1;
}
