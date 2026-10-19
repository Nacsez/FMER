/* Original FMER710 global MIDI settings, independent of native patch bytes.
 * Persist in the existing bank metadata record; resets retain these values. */
#ifndef FMER_MIDI_SETTINGS_H
#define FMER_MIDI_SETTINGS_H
#include <stdint.h>
enum {FMER_MIDI_ROUTE,FMER_MIDI_TX_CHANNEL,FMER_MIDI_LOCAL,FMER_MIDI_CLOCK_SOURCE,
      FMER_MIDI_CLOCK_SEND,FMER_MIDI_TRANSPORT_RX,FMER_MIDI_CC_SEND,FMER_MIDI_CHANNEL_MODE,FMER_MIDI_SETTINGS_COUNT};
typedef struct {uint8_t value[8];} fmer_midi_settings_t;
static void fmer_midi_defaults(fmer_midi_settings_t *s)
{uint32_t i;for(i=0;i<8u;i++)s->value[i]=0;s->value[FMER_MIDI_LOCAL]=1;s->value[FMER_MIDI_TRANSPORT_RX]=1;}
static uint32_t fmer_midi_setting_max(uint32_t id)
{return id==0?3u:id==1?15u:id==3?2u:id<8?1u:0u;}
static int fmer_midi_settings_valid(const fmer_midi_settings_t *s)
{uint32_t i;if(!s)return 0;for(i=0;i<8u;i++)if(s->value[i]>fmer_midi_setting_max(i))return 0;return 1;}
typedef struct {uint32_t received_clock,received_start,received_stop,sent_notes,sent_clock,
    output_refused,clock_timeouts,clock_period_frames,external_running,received_song_position;} fmer_midi_metrics_t;
#endif
