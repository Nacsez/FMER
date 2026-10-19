#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <string_view>
#include "render.hpp"
#include "patch_tool.hpp"
#include "factory_catalog.hpp"

namespace {
std::string json_string(std::string_view input) {
    std::ostringstream output;
    output << '"';
    for (const unsigned char value : input) {
        if (value == '"' || value == '\\') {
            output << '\\' << static_cast<char>(value);
        } else if (value < 0x20) {
            output << "\\u" << std::hex << std::setfill('0') << std::setw(4)
                   << static_cast<unsigned int>(value);
        } else {
            output << static_cast<char>(value);
        }
    }
    output << '"';
    return output.str();
}
} // namespace

int main(int argc, char** argv) {
    if (argc == 2 && std::string_view(argv[1]) == "--factory") { print_factory_catalog(); return 0; }
    if (argc > 1 && std::string_view(argv[1]) == "--patch-tool") return run_patch_tool(argc, argv);
    if (argc > 1 && std::string_view(argv[1]) == "--render") return run_render(argc, argv);
    if (argc == 2 && std::string_view(argv[1]) == "--parameters") { print_parameters(); return 0; }
    if (argc > 2 || (argc == 2 && std::string_view(argv[1]) != "--diagnostics")) {
        std::cerr << "Usage: fmer_host --diagnostics | --parameters | --render note|chord|sequence|arp|midi|stress --out FILE.wav --report FILE.json [--note N --bpm N --duration SECONDS --tail SECONDS --patch FILE.syx --voice N --set ID=VALUE --pattern FILE --fx NAME=VALUE --arp-order NAME] | --patch-tool decode|validate|encode-single|encode-bank --in FILE [--out FILE]\n";
        return 2;
    }

    // Host evidence only: the shared musical core has no device adapter yet.
    std::cout << "{\n"
              << "  \"schema_version\": 1,\n"
              << "  \"project\": \"FMER\",\n"
              << "  \"component\": \"fmer_host\",\n"
              << "  \"implementation\": \"host-musical-prototype\",\n"
              << "  \"project_version\": " << json_string(FMER_VERSION) << ",\n"
              << "  \"build_id\": " << json_string(FMER_BUILD_ID) << ",\n"
              << "  \"compiler_id\": " << json_string(FMER_COMPILER_ID) << ",\n"
              << "  \"compiler_version\": " << json_string(FMER_COMPILER_VERSION) << ",\n"
              << "  \"build_configuration\": " << json_string(FMER_BUILD_CONFIG) << ",\n"
              << "  \"cpp_standard\": 17,\n"
              << "  \"pointer_bits\": " << sizeof(void*) * 8 << ",\n"
              << "  \"hardware_access\": false,\n"
              << "  \"audio_engine\": true,\n"
              << "  \"engine\": \"MSFA\",\n"
              << "  \"sample_rate\": 44100,\n"
              << "  \"voice_limit\": 12,\n"
              << "  \"device_fidelity\": \"unmeasured\"\n"
              << "}\n";
    return std::cout.good() ? 0 : 1;
}
