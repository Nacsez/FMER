#include "patch_tool.hpp"
#include "patch.hpp"

#include <algorithm>
#include <array>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
std::string quoted(const std::string& input) {
    std::ostringstream out;
    out << '"';
    for (const unsigned char c : input) {
        if (c == '"' || c == '\\') out << '\\' << static_cast<char>(c);
        else if (c < 32 || c >= 127)
            out << "\\u" << std::hex << std::setfill('0') << std::setw(4) << unsigned(c);
        else out << static_cast<char>(c);
    }
    out << '"';
    return out.str();
}

std::vector<std::uint8_t> read_bounded(const std::filesystem::path& path) {
    std::ifstream stream(path, std::ios::binary | std::ios::ate);
    if (!stream) throw std::runtime_error("Cannot open patch input");
    const auto length = stream.tellg();
    if (length <= 0 || length > 128 * 155)
        throw std::runtime_error("Patch input must contain 1..19840 bytes");
    std::vector<std::uint8_t> bytes(static_cast<std::size_t>(length));
    stream.seekg(0);
    if (!stream.read(reinterpret_cast<char*>(bytes.data()), static_cast<std::streamsize>(bytes.size())))
        throw std::runtime_error("Cannot read complete patch input");
    return bytes;
}

void write_new(const std::filesystem::path& path, const std::vector<std::uint8_t>& bytes) {
    // C11 exclusive creation is supported by the host CRT; never truncate an
    // existing file, including an input/output alias or a concurrent creator.
    std::FILE* stream = nullptr;
#ifdef _WIN32
    if (_wfopen_s(&stream, path.c_str(), L"wbx") != 0) stream = nullptr;
#else
    stream = std::fopen(path.c_str(), "wbx");
#endif
    if (!stream) throw std::runtime_error("Cannot create output; existing files are preserved");
    const bool written = std::fwrite(bytes.data(), 1, bytes.size(), stream) == bytes.size();
    const bool closed = std::fclose(stream) == 0;
    if (!written || !closed) throw std::runtime_error("Patch output write failed");
}

void print_patch(const fmer::Patch& patch) {
    std::string name;
    for (std::size_t i = 145; i < 155; ++i) name += static_cast<char>(patch.vced[i]);
    std::cout << "{\"name\":" << quoted(name) << ",\"vced\":[";
    for (std::size_t i = 0; i < patch.vced.size(); ++i) {
        if (i) std::cout << ',';
        std::cout << unsigned(patch.vced[i]);
    }
    std::cout << "]}";
}
}  // namespace

int run_patch_tool(int argc, char** argv) {
    try {
        if (argc < 3) throw std::invalid_argument("Missing patch operation");
        const std::string operation = argv[2];
        std::filesystem::path input, output;
        for (int i = 3; i < argc; i += 2) {
            if (i + 1 == argc) throw std::invalid_argument("Missing patch option value");
            const std::string option = argv[i];
            if (option == "--in" && input.empty()) input = std::filesystem::u8path(argv[i + 1]);
            else if (option == "--out" && output.empty()) output = std::filesystem::u8path(argv[i + 1]);
            else throw std::invalid_argument("Unknown or duplicate patch option");
        }
        if (input.empty()) throw std::invalid_argument("--in is required");
        if (operation != "decode" && operation != "validate" && operation != "encode-single" && operation != "encode-bank")
            throw std::invalid_argument("Patch operation must be decode, validate, encode-single or encode-bank");
        const bool encode = operation == "encode-single" || operation == "encode-bank";
        if (encode == output.empty()) throw std::invalid_argument(encode ? "--out is required" : "--out is only valid for encoding");
        const auto bytes = read_bounded(input);
        std::array<fmer::Patch, 128> patches{};
        std::size_t count = 0;
        std::string error;
        if (operation == "decode") {
            std::array<fmer::Patch, fmer::kBankSize> decoded{};
            if (!fmer::decode_sysex(bytes.data(), bytes.size(), decoded, count, error))
                throw std::invalid_argument(error);
            std::copy_n(decoded.begin(), count, patches.begin());
        } else {
            if (bytes.size() % fmer::kVcedSize != 0)
                throw std::invalid_argument("Raw VCED input must contain complete 155-byte voices");
            count = bytes.size() / fmer::kVcedSize;
            if ((operation == "encode-single" && count != 1) || (operation == "encode-bank" && count != 32))
                throw std::invalid_argument("Encoding requires exactly 1 single or 32 bank voices");
            for (std::size_t i = 0; i < count; ++i) {
                std::copy_n(bytes.begin() + i * fmer::kVcedSize, fmer::kVcedSize, patches[i].vced.begin());
                if (!fmer::validate_patch(patches[i], error))
                    throw std::invalid_argument("Voice " + std::to_string(i + 1) + ": " + error);
            }
        }
        std::size_t output_size = 0;
        if (encode) {
            std::vector<std::uint8_t> encoded;
            if (count == 1) encoded = fmer::encode_single(patches[0]);
            else {
                std::array<fmer::Patch, fmer::kBankSize> bank{};
                std::copy_n(patches.begin(), bank.size(), bank.begin());
                encoded = fmer::encode_bank(bank);
            }
            write_new(output, encoded);
            output_size = encoded.size();
        }
        std::cout << "{\"operation\":" << quoted(operation) << ",\"count\":" << count
                  << ",\"output_bytes\":" << output_size << ",\"hardware_access\":false";
        if (operation == "decode") {
            std::cout << ",\"patches\":[";
            for (std::size_t i = 0; i < count; ++i) {
                if (i) std::cout << ',';
                print_patch(patches[i]);
            }
            std::cout << ']';
        }
        std::cout << "}\n";
        return std::cout.good() ? 0 : 1;
    } catch (const std::exception& error) {
        std::cerr << "Patch codec: " << error.what() << '\n';
        return 2;
    }
}
