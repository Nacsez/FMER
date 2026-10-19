#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <memory>

namespace fmer {

enum class EffectKind : std::uint8_t { filter, reverb, delay, drive, chorus, phaser };
enum class FilterMode : std::uint8_t { low_pass, high_pass, band_pass };
enum class ReverbModel : std::uint8_t { room, plate, hall, cloud };
enum class DelayModel : std::uint8_t { clean, warm };

// Original FMER effects, not a stock/Baud preset or DSP compatibility format.
// Zero amounts bypass a stage exactly. Filter bypass is LP at20000Hz and Q0.
struct EffectParameters {
    float drive{0.0f};                 // 0..1, soft clipping amount/gain
    float chorus{0.0f};                // 0..1 intensity, dry/wet mix0..50%
    float delay{0.0f};                 // 0..1 send return; preserves dry, adds up to .68 wet
    float delay_ms{250.0f};            // 20..1000
    float feedback{0.35f};             // 0..0.85
    float reverb{0.0f};                // 0..1 send return; preserves dry, adds up to .68 wet
    float cutoff_hz{20000.0f};         // 20..20000; bypass only LP with zero resonance
    float phaser{0.0f};                // 0..1 intensity, dry/wet mix0..50%
    float chorus_rate_hz{0.35f};       // 0.1..1
    float chorus_depth{0.5f};          // 0..1
    float phaser_rate_hz{0.7f};        // 0.5..6
    float phaser_depth{0.5f};          // 0..1
    float reverb_decay{0.5f};          // 0..1, nominal low-frequency T60 .3..8 seconds
    float resonance{0.0f};            // 0..1, Q .707..10; independent of VA voice filter
    FilterMode filter_mode{FilterMode::low_pass};
    ReverbModel reverb_model{ReverbModel::room};
    DelayModel delay_model{DelayModel::clean};
    std::array<EffectKind, 6> order{{EffectKind::filter, EffectKind::reverb,
        EffectKind::delay, EffectKind::drive, EffectKind::chorus, EffectKind::phaser}};
};

struct EffectStats {
    std::uint64_t processed_frames{};
    std::uint64_t rejected_parameters{};
    std::uint64_t rejected_buffers{};
    std::uint64_t sanitized_samples{};
    std::uint64_t clipped_samples{};
    std::uint64_t limited_samples{}; // transparent below .9, soft output knee above
    std::uint64_t guarded_samples{}; // hard final ceiling, including bypass
    float peak_input{};
    float peak_output{};
    // Largest absolute active delay/filter state, not a prediction of audibility.
    // Computed by bounded inspection when stats() is called, outside rendering.
    float tail_peak{};
};

// Single-thread ownership, just like Synth. Construction allocates fixed storage
// once; process/set_parameters/reset do not allocate, block, log, or perform I/O.
// Parameter acceptance is all-or-nothing, not concurrent-thread synchronization.
// The 20..1000 ms delay uses compact 16-bit floating storage on host and target;
// normal writes round to nearest/even, subnormal writes truncate to end tails.
// Reverb/filter/modulation state and all processing arithmetic remain float32.
class Effects {
public:
    static constexpr std::uint32_t native_sample_rate = 44100;
    Effects();
    ~Effects();
    Effects(const Effects&) = delete;
    Effects& operator=(const Effects&) = delete;

    bool init(std::uint32_t sample_rate = native_sample_rate) noexcept;
    bool set_parameters(const EffectParameters& parameters) noexcept;
    EffectParameters parameters() const noexcept;
    void process(float* mono, std::size_t frames) noexcept;
    // Clear tails/oscillator phases/counters while preserving parameter values.
    void reset() noexcept;
    EffectStats stats() const noexcept;
    EffectStats meters() const noexcept; // cached counters only; no tail scan
    // Decimated peak of each stage's output-minus-input, with ~150ms release.
    // Activity, not feedback coefficient or calibrated loudness. Audio owner.
    const std::array<float,6>& activity() const noexcept;
    static constexpr float output_ceiling = .98f;
    static std::size_t storage_bytes() noexcept;

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace fmer
