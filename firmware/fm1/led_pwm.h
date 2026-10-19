/* SPDX-License-Identifier: GPL-3.0-only
 * Half-bright octave feedback at matrix-frame rate, never UI-frame rate. */
#ifndef FMER_LED_PWM_H
#define FMER_LED_PWM_H
#include <stdint.h>
static uint8_t fmer_led_scan_mask(uint8_t full,uint8_t half,uint8_t phase)
{ return (uint8_t)(full & (phase?~half:255u)); }
#endif
