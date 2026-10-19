/* SPDX-License-Identifier: GPL-3.0-only
 * Main-loop only. Retain raw evidence across USB detach, never write flash.
 * USB enumeration is not a charger-current measurement or state of charge.
 */
#ifndef FMER_BATTERY_HISTORY_H
#define FMER_BATTERY_HISTORY_H
#include <stdint.h>
enum {FMER_BATTERY_HISTORY_CAPACITY=128};
typedef struct {uint32_t seconds_usb;uint16_t raw,filtered;} fmer_battery_sample_t;
typedef struct {
 fmer_battery_sample_t samples[FMER_BATTERY_HISTORY_CAPACITY];
 uint32_t total,last_ms,last_usb;
} fmer_battery_history_t;
static void fmer_battery_history_add(fmer_battery_history_t *h,uint32_t ms,uint32_t raw,uint32_t filtered,uint32_t usb)
{
 fmer_battery_sample_t *s;
 if(raw>1023u || filtered>1023u || usb>1u)return;
 if(h->total && ms-h->last_ms<300000u && usb==h->last_usb)return;
 s=&h->samples[h->total%FMER_BATTERY_HISTORY_CAPACITY];
 s->seconds_usb=(ms/1000u)|(usb<<31);s->raw=(uint16_t)raw;s->filtered=(uint16_t)filtered;
 h->total++;h->last_ms=ms;h->last_usb=usb;
}
static uint32_t fmer_battery_history_count(const fmer_battery_history_t *h)
{return h->total<FMER_BATTERY_HISTORY_CAPACITY?h->total:FMER_BATTERY_HISTORY_CAPACITY;}
static const fmer_battery_sample_t *fmer_battery_history_get(const fmer_battery_history_t *h,uint32_t index)
{
 uint32_t n=fmer_battery_history_count(h);
 if(index>=n)return 0;
 return &h->samples[(h->total-n+index)%FMER_BATTERY_HISTORY_CAPACITY];
}
#endif
