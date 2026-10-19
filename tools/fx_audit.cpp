// Offline measurements of the existing FX mix law. No device access or DSP edits.
// Build with the host CMake project; stdout is CSV suitable for comparisons.
#include "../core/effects.hpp"
#include <algorithm>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <vector>

namespace {
constexpr unsigned rate = 44100;
constexpr double pi = 3.14159265358979323846;
double rms(const std::vector<float>& samples, unsigned begin, unsigned end) {
    double sum = 0;
    for (unsigned i = begin; i < end; ++i) sum += double(samples[i]) * samples[i];
    return std::sqrt(sum / (end - begin));
}
}

int main() {
    std::cout << "model,signal,stage,mix,feedback_or_decay,input_rms,onset_20ms_rms,first_250ms_rms,steady_1to2s_rms,tail_2to3s_rms,peak,clipped,sanitized,limited\n";
    std::cout << std::setprecision(9);
    for (unsigned signal = 0; signal < 3; ++signal) {
        std::vector<float> dry(rate * 4);
        for (unsigned i = 0; i < rate * 2; ++i) {
            const double t = double(i) / rate;
            if (signal == 0 || (signal == 1 && i < rate / 20))
                dry[i] = float(0.25 * std::sin(2 * pi * 220 * t) +
                    0.125 * std::sin(2 * pi * 331 * t) + 0.0625 * std::sin(2 * pi * 733 * t));
        }
        if (signal == 2) dry[0] = 0.5f;
        for(unsigned model=0;model<2;++model) for (unsigned stage = 0; stage < 3; ++stage) {
            for (float amount : {0.0f, 0.25f, 0.5f, 0.75f, 1.0f}) {
                for (float setting : {0.0f, 0.5f, 1.0f}) {
                    fmer::Effects fx;
                    if (!fx.init()) return 1;
                    fmer::EffectParameters parameters;
                    parameters.reverb_model=static_cast<fmer::ReverbModel>(model);
                    parameters.delay_model=static_cast<fmer::DelayModel>(model);
                    parameters.delay = stage == 1 ? 0 : amount;
                    parameters.reverb = stage == 0 ? 0 : amount;
                    parameters.feedback = setting * 0.85f;
                    parameters.reverb_decay = setting;
                    if (!fx.set_parameters(parameters)) return 2;
                    auto output = dry;
                    for (std::size_t at = 0; at < output.size(); at += 128)
                        fx.process(output.data() + at, std::min<std::size_t>(128, output.size() - at));
                    const auto stats = fx.stats();
                    if (stats.sanitized_samples || stats.rejected_parameters || stats.rejected_buffers) return 3;
                    std::cout << model << ',' << (signal == 0 ? "multitone" : signal == 1 ? "burst" : "impulse") << ','
                        << (stage == 0 ? "delay" : stage == 1 ? "reverb" : "reverb_then_delay") << ','
                        << amount << ',' << (stage == 0 ? parameters.feedback : setting) << ','
                        << rms(dry, 0, rate * 2) << ',' << rms(output, 0, rate / 50) << ','
                        << rms(output, 0, rate / 4) << ',' << rms(output, rate, rate * 2) << ','
                        << rms(output, rate * 2, rate * 3) << ',' << stats.peak_output << ','
                        << stats.clipped_samples << ',' << stats.sanitized_samples << ',' << stats.limited_samples << '\n';
                }
            }
        }
    }
}
