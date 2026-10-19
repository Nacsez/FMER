#pragma once
#include <stdint.h>
#include "control_model.h"
#include "native_state.h"
#include "midi_settings.h"
/* Main/boot only. Cache publication requires stopped audio; original generation
 * is pure and matches the companion profile, including empty retained patterns. */
#ifdef __cplusplus
extern "C" {
#endif
int fmer_dsp_init(void);
void fmer_dsp_midi(uint8_t status, uint8_t data1, uint8_t data2, uint8_t source);
void fmer_dsp_panic(void);
int fmer_dsp_patch(const uint8_t *vced, uint32_t length);
int fmer_dsp_parameter(uint32_t id, uint32_t value);
/* Factory presets replace sound parameters only; tempo, channel, pattern and
 * voice admission survive. Existing notes retain their immutable sound. */
int fmer_dsp_factory_preset(uint32_t index);
const char *fmer_dsp_factory_name(uint32_t index);
int fmer_dsp_original_default(uint32_t index,uint8_t *wire);
void fmer_dsp_cache_default(uint32_t index,const uint8_t *wire);
void fmer_dsp_cache_sound(uint32_t slot,const uint8_t *wire);
int fmer_dsp_audition(uint32_t slot);
uint32_t fmer_dsp_preset_id(void);
uint32_t fmer_dsp_sound_dirty(void);
void fmer_dsp_patch_name(char out[11]);
uint32_t fmer_dsp_state_generation(void);
/* Audio-owner copies, no wire encoding or CRC here. Import requires a validated
 * complete record, a matching generation and stops/releases runtime voices. */
uint32_t fmer_dsp_fx_order(void);
uint32_t fmer_dsp_modulation(void);
int fmer_dsp_set_fx_default(uint32_t rank,int apply);
void fmer_dsp_get_native(fmer_native_state_t *out);
int fmer_dsp_set_native(const fmer_native_state_t *state, uint32_t expected_generation);
int fmer_dsp_controls(uint32_t engine, uint32_t cutoff, uint32_t delay_percent);
/* VA snapshots apply on the next note. waveform0..3, attack/release0..10000ms. */
int fmer_dsp_voice_controls(uint32_t waveform, uint32_t attack_ms, uint32_t release_ms);
/* All calls share the audio owner. Batches are validated before mutation.
 * Changing SEQ_STEP selects the stored step; edit its fields in a following
 * batch. Recording can advance selection; merge only explicitly edited IDs
 * into a fresh get_controls snapshot. No allocation after init.
 * Changing SEQ_PATTERN selects its retained length and step0, ignoring step
 * fields from the previous bank in that batch. While playing, this also queues
 * the bank for the next full-pattern boundary. Edit/playing banks are separate.
 * VA ADSR/filter/vibrato and FM edits affect future note snapshots. */
void fmer_dsp_get_controls(fmer_controls_t *out);
int fmer_dsp_apply_controls(const fmer_controls_t *controls);
int fmer_dsp_transport(uint32_t command);
void fmer_dsp_performance(fmer_performance_state_t *out);
enum { FMER_PATTERN_STEPS=64, FMER_PATTERN_BANKS=16 };
typedef struct {
    fmer_song_t song;
    uint8_t song_row[4],song_repeat[4],song_live[4],pattern_length[16];
    uint32_t revision, length, delay_ms;
    uint8_t pitch[FMER_PATTERN_STEPS], velocity[FMER_PATTERN_STEPS], gate[FMER_PATTERN_STEPS];
    uint32_t selected_pattern, playing_pattern, queued_pattern, chain_mask, chain_enabled;
    uint32_t mode,track,count_in,count_in_active;
    uint8_t track_stopped[4],track_launch[4],track_solo[4],track_fx[4],track_length[4],edit_result,clipboard_length,undo_available;
    uint8_t track_pattern[4],track_queued[4],track_step[4],track_level[4],track_mute[4],track_sound[4];
} fmer_pattern_state_t;
/* Audio-owner-only readback of all stored steps, including inactive trailing
 * steps. Pitch128 is REST. Revision0/length0 means not initialized; after init
 * revision changes on stored content/length edits, bank selection and the
 * appended bank/queue/chain metadata, not ordinary steps or sound controls.
 * Revisions wrap UINT32_MAX->1. Compare for inequality. queued_pattern16 means
 * no pending switch. The step arrays always describe selected_pattern.
 * Check revision before copying; publish an immutable copy to the UI outside
 * this API. Neither call allocates, advances playback, or emits notes. */
uint32_t fmer_dsp_pattern_revision(void);
void fmer_dsp_get_pattern(fmer_pattern_state_t *out);
typedef struct {
    uint32_t active_notes[4], gated_notes[4];
    uint32_t active_voices, beat_on;
} fmer_activity_state_t;
/* Audio-owner-only fixed12-slot snapshot. Bit(note%32) of word(note/32)
 * represents the input MIDI pitch before patch transpose/bend. Active includes
 * release tails and silent voices; gated means active held or sustained slots.
 * Steals/finished envelopes disappear; overlapping owners share a pitch bit.
 * beat_on is sequencer-only: first4 of24 PPQ ticks per quarter, including
 * rests; starts bright at PLAY and is false when stopped or arp-only.
 * Before init returns allzero. Null is ignored. No allocation or DSP mutation.
 * Publish an immutable copy for the main/UI owner. */
void fmer_dsp_get_activity(fmer_activity_state_t *out);
/* Optional startup-installed observer for admitted generated note edges only.
 * Called by the audio owner: callback must be bounded, nonblocking and do no
 * allocation/I/O. Frame low wraps naturally; source is4(seq) or5(arp). */
typedef void (*fmer_dsp_event_tap_t)(uint32_t frame_low, uint8_t status,
                                   uint8_t note, uint8_t velocity, uint8_t source);
void fmer_dsp_set_event_tap(fmer_dsp_event_tap_t tap);
/* Separate bounded MIDI output observer. Return0 if the board queue refuses;
 * audio code records the refusal and never waits for USB. No MIDI input echo. */
typedef int (*fmer_dsp_midi_output_t)(uint8_t status,uint8_t a,uint8_t b);
void fmer_dsp_set_midi_output(fmer_dsp_midi_output_t output);
int fmer_dsp_set_midi_settings(const fmer_midi_settings_t *settings);
void fmer_dsp_get_midi_settings(fmer_midi_settings_t *settings);
void fmer_dsp_midi_metrics(fmer_midi_metrics_t *metrics);
void fmer_dsp_midi_disconnected(void);
/* Board admission1..4 within the shared12-voice pool; board default4.
 * Budget reductions/new notes steal tails, sustained, then oldest held notes.
 * Stolen counter saturates at UINT32_MAX for this diagnostic C boundary. */
int fmer_dsp_voice_budget(uint32_t limit);
uint32_t fmer_dsp_voice_limit(void);
uint32_t fmer_dsp_stolen(void);
void fmer_dsp_render(int32_t *stereo_q15, uint32_t frames, uint32_t gain_q10);
uint32_t fmer_dsp_active(void);
/* Audio-owner lifetime since boot, saturating counters; peak values Q15 before master. */
void fmer_dsp_output_metrics(uint32_t out[7]);
/* Main may copy with IRQ masked; six bounded Q15 effect-difference peaks. */
void fmer_dsp_fx_activity(uint16_t out[6]);
void fmer_dsp_part_scopes(int16_t out[4][32]);
uint32_t fmer_heap_used(void);
#ifdef __cplusplus
}
#endif
