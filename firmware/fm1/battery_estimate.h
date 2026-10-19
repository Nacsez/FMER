/* SPDX-License-Identifier: GPL-3.0-only
 * FMER provisional ADC estimate, curve revision 4 (2026-10-15).
 * NOT a calibrated fuel gauge or remaining-hours prediction. No voltage,
 * charger current, capacity or chemistry measurement is implied.
 * 632: observed charge plateau. 591/561/531: upstream stock bar thresholds.
 * Percentages and the 520 usable-empty endpoint are provisional priors.
 * Owner reports load instability near old14%; after reboot ADC522..525.
 * This is a conservative usable-charge estimate, not a measured cutoff.
 * Malachite's retained 9.5-hour unplugged segment: 613 -> 537 filtered ADC.
 * Midrange anchors follow elapsed-use shape with an assumed remaining tail;
 * they are NOT coulomb/voltage measurements or a completed discharge cycle.
 * See docs/USB_DIRECT_LINK.md for exact evidence and remaining uncertainty.
 */
#ifndef FMER_BATTERY_ESTIMATE_H
#define FMER_BATTERY_ESTIMATE_H
#include <stdint.h>
static uint32_t fmer_battery_estimate(uint32_t adc)
{
    static const uint16_t raw[]={520,531,537,545,560,582,600,610,632};
    static const uint8_t percent[]={0,5,12,26,50,67,91,95,100};
    uint32_t i;
    if(adc<400u || adc>750u)return 101u; /* disconnected/implausible ADC */
    if(adc<=raw[0])return 0;
    for(i=1;i<sizeof raw/sizeof raw[0];i++)if(adc<=raw[i])
        return percent[i-1]+((adc-raw[i-1])*(percent[i]-percent[i-1])+(raw[i]-raw[i-1])/2u)/(raw[i]-raw[i-1]);
    return 100;
}
/* Main-owned, filtered ADC input. A sustained change of one percentage point
 * takes thirty seconds; larger load/charge changes settle one point per thirty sec.
 * Invalid/stale UI input remains unknown; this does not synthesize samples. */
typedef struct {uint32_t initialized,percent,last_ms;} fmer_battery_estimator_t;
static uint32_t fmer_battery_update(fmer_battery_estimator_t *s,uint32_t adc,uint32_t now)
{
    uint32_t target=fmer_battery_estimate(adc);
    if(target>100u){s->initialized=0;return 101u;}
    if(!s->initialized){s->initialized=1;s->percent=target;s->last_ms=now;}
    else if(target==s->percent)s->last_ms=now;
    else if(target<=10u && target<s->percent && (uint32_t)(now-s->last_ms)>=5000u) {
        /* Do not hide sustained low readings behind minutes of display lag. */
        uint32_t drop=s->percent-target;s->percent-=drop>5u?5u:drop;s->last_ms=now;
    }
    else if((uint32_t)(now-s->last_ms)>=30000u){s->percent+=target>s->percent?1u:(uint32_t)-1;s->last_ms=now;}
    return s->percent;
}
#endif
