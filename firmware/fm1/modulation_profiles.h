/* SPDX-License-Identifier: GPL-3.0-only
 * Original FMER modulation recipes. Amount stays independent of the recipe.
 * Values fit the existing DSP's validated frequency and depth ranges. */
#ifndef FMER_MODULATION_PROFILES_H
#define FMER_MODULATION_PROFILES_H
static const char *fmer_modulation_name(unsigned phaser,unsigned profile)
{
    static const char *const names[2][4]={{"DREAM","WIDE","SHIMMER","RUSH"},{"DRIFT","SWEEP","PULSE","STORM"}};
    return names[phaser?1:0][profile&3u];
}
static float fmer_modulation_rate(unsigned phaser,unsigned profile)
{
    static const float rate[2][4]={{.12f,.28f,.65f,1.f},{.5f,1.1f,2.6f,5.2f}};
    return rate[phaser?1:0][profile&3u];
}
static float fmer_modulation_depth(unsigned phaser,unsigned profile)
{
    static const float depth[2][4]={{.35f,.70f,.85f,1.f},{.55f,.80f,.90f,1.f}};
    return depth[phaser?1:0][profile&3u];
}
#endif
