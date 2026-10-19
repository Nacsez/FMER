/* SPDX-License-Identifier: GPL-3.0-only
 * Delay subdivisions in quarter-note twelfths. Zero preserves free milliseconds.
 * The one-second delay buffer is a hard capacity, not a claimed long-note sync.
 */
#ifndef FMER_DELAY_TIMING_H
#define FMER_DELAY_TIMING_H
#include <stdint.h>
static uint32_t fmer_delay_time(uint32_t division,uint32_t free_ms,uint32_t quarter_us)
{
 static const uint8_t units[]={0,12,9,6,4,3,2,18};
 uint32_t ms;
 if(!division || division>7)return free_ms;
 ms=(uint32_t)(((uint64_t)quarter_us*units[division]+6000u)/12000u);
 return ms<20?20:ms>1000?1000:ms;
}
static const char *fmer_delay_division_name(uint32_t division)
{
 static const char *const names[]={"FREE MS","1/4","1/8 DOT","1/8","1/8 TRI","1/16","1/16 TRI","1/4 DOT"};
 return division<8?names[division]:"?";
}
#endif
