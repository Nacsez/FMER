/* SPDX-License-Identifier: GPL-3.0-only
 * Octave brightness at matrix-frame rate, never UI-frame rate. */
#ifndef FMER_LED_PWM_H
#define FMER_LED_PWM_H
#include <stdint.h>
static uint8_t fmer_led_scan_mask(uint8_t full,uint8_t half,uint8_t three_quarter,uint8_t phase)
{
    uint8_t suppressed=(uint8_t)(((phase&1u)?half:0u)|((phase&3u)==3u?three_quarter:0u));
    return (uint8_t)(full & ~suppressed);
}
#endif
