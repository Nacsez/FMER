#pragma once

#include "patch.hpp"
#include <cstddef>
#include <cstdint>
#include <memory>

namespace fmer {

enum class SynthEngine : std::uint8_t { fm, va };
enum class VaWaveform : std::uint8_t { sine, saw, square, triangle, noise };

// Original FMER preview engine; these settings are not Baud's native format.
struct VaParameters {
    VaWaveform waveform{VaWaveform::saw};
    float cutoff_hz{6000.0f};
    float resonance{0.2f};
    float attack_ms{5.0f};
    float decay_ms{150.0f};
    float sustain{0.7f};
    float release_ms{200.0f};
    // Note-snapshot vibrato. A fixed-point sine phase and a bounded cubic
    // exponential avoid libm calls in the sample loop; zero depth is bypass.
    float lfo_rate_hz{5.0f};
    float lfo_depth_cents{0.0f};
};

enum class GlideMode : std::uint8_t { off, legato, always };
enum class GlideContour : std::uint8_t { linear, ease_in, ease_out };

// Constant-time portamento in musical pitch (semitones), 0..5000 ms.
// Legato only glides overlapping notes; always also glides separate notes.
// An overlapping glide preserves oscillator/envelope state. A detached note
// retriggers its envelope. Off preserves the original retrigger behavior.
struct GlideParameters {
    GlideMode mode{GlideMode::off};
    float time_ms{150.0f};
    GlideContour contour{GlideContour::linear};
};

// Small immutable-on-note-start instrument snapshot; effects are deliberately
// absent because all parts feed one shared effects chain in the adapter.
struct PartParameters {
    Patch patch{make_init_patch()};
    SynthEngine engine{SynthEngine::fm};
    VaParameters va{};
    GlideParameters glide{};
    bool lfo_enabled{true};
};

struct SynthStats {
    std::uint64_t rendered_frames{};
    std::uint64_t note_ons{};
    std::uint64_t note_offs{};
    std::uint64_t stolen_voices{};
    std::uint64_t retriggers{};
    std::uint64_t clipped_samples{};
    std::uint64_t rejected_events{};
    std::uint32_t active_voices{};
    std::uint32_t released_voices{};
    std::uint32_t peak_voices{};
};

// Input MIDI ownership pitches, before patch transpose or pitch bend. Masks
// collapse overlapping voices of the same pitch; active_voices counts slots.
// Active includes release tails and silent patches. Gated includes only active
// held/pedal-sustained slots; finished or stolen voices appear in neither mask.
struct SynthActivity {
    std::uint32_t active_notes[4]{}, gated_notes[4]{};
    std::uint32_t active_voices{};
};

// Single audio-thread ownership: enqueue events outside this class if needed.
// Construction allocates the bounded implementation once. No allocation or I/O
// occurs in set_patch, MIDI handlers, render, panic, or stats.
class Synth {
public:
    static constexpr std::size_t voice_limit = 12;
    static constexpr std::size_t part_limit = 4;
    // Per mono lane, keyed by (source, channel, pitch). Overflow refuses the
    // new key and increments rejected_events; existing held keys are retained.
    static constexpr std::size_t mono_held_limit = 32;
    static constexpr std::uint32_t native_sample_rate = 44100;
    static constexpr std::size_t control_block_size = 64;

    Synth();
    ~Synth();
    Synth(const Synth&) = delete;
    Synth& operator=(const Synth&) = delete;

    // Original MSFA amplitude-envelope timing is calibrated for 44.1 kHz.
    // Unsupported rates are rejected without changing the running state.
    bool init(std::uint32_t sample_rate = native_sample_rate) noexcept;
    bool set_patch(const Patch& patch) noexcept;
    bool set_engine(SynthEngine engine) noexcept;
    bool set_va_parameters(const VaParameters& parameters) noexcept;
    // Live program-LFO gate; preserves patch depths, phase and held voices.
    // MIDI mod-wheel expression is independent of this program modulation gate.
    void set_lfo_enabled(bool enabled) noexcept;
    // Adapter budget within the fixed pool; default12 preserves host behavior.
    // Reducing it immediately retires released/sustained/oldest voices, counting
    // each retirement as a steal. No allocation or global silence is required.
    bool set_voice_budget(std::uint32_t voices) noexcept;
    std::uint32_t voice_budget() const noexcept;
    // Mode transitions silence existing ownership. Mono shares one bounded
    // voice with last-held-note priority, while parts mode reserves one voice
    // per part and requires budget4. Releasing the newest key returns to the
    // previous physically held key using the same configured glide contour.
    // Standalone note handlers reject note-ons during parts mode: the adapter
    // must explicitly route incoming notes to the selected part.
    bool set_mono(bool enabled) noexcept;
    bool set_glide(const GlideParameters& parameters) noexcept;
    bool configure_part(std::uint8_t part, const PartParameters& parameters) noexcept;
    bool set_parts_enabled(bool enabled) noexcept;
    bool set_part_mix(std::uint8_t part, float level, bool muted) noexcept;
    void part_note_on(std::uint8_t part, std::uint8_t channel, std::uint8_t note,
                      std::uint8_t velocity, std::uint8_t source = 0,
                      bool honor_sustain = false) noexcept;
    void part_note_off(std::uint8_t part, std::uint8_t channel, std::uint8_t note,
                       std::uint8_t source = 0) noexcept;
    void panic_part(std::uint8_t part) noexcept;
    SynthActivity part_activity(std::uint8_t part) const noexcept;
    void note_on(std::uint8_t channel, std::uint8_t note, std::uint8_t velocity,
                 std::uint8_t source = 0, bool honor_sustain = true) noexcept;
    void note_off(std::uint8_t channel, std::uint8_t note,
                  std::uint8_t source = 0) noexcept;
    void control_change(std::uint8_t channel, std::uint8_t cc,
                        std::uint8_t value) noexcept;
    void pitch_bend(std::uint8_t channel, std::uint16_t value14) noexcept;
    // Optional dry bus: bits0..3 route those parts around shared external FX.
    // Both buses share the same voice pool and render each voice exactly once.
    void render(float* mono, std::size_t frames, float* dry=nullptr,
                std::uint8_t bypass_mask=0, std::uint8_t preview_sources=0) noexcept;
    // Pre-fader/pre-FX PCM monitors; bounded and owned by the audio thread.
    void part_scopes(std::int16_t out[4][32]) const noexcept;
    void panic() noexcept;
    void panic_source(std::uint8_t source) noexcept;
    SynthStats stats() const noexcept;
    // Audio-owner-only bounded fixed-slot inspection, with no allocation,
    // timeline advance, changes to voices/counters, or envelope estimation.
    SynthActivity activity() const noexcept;

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace fmer
