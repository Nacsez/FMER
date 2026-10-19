/* SPDX-License-Identifier: GPL-3.0-only
 * Original FMER708 write barrier. Application sectors and exactly the CRC of
 * our known staged-loader record are writable. Native slots are never in range.
 */
#ifndef FMER_LOADER_WRITE_POLICY_H
#define FMER_LOADER_WRITE_POLICY_H
#include <stdint.h>
#ifdef FMER_CITRINE_STOCK
/* Stock V15 staging is separate from FMER's own staging layout. This build
 * admits only the stock record, never both locations or a dynamic address. */
#define FMER_LOADER_RECORD_OFFSET 0xE7F00u
#else
#define FMER_LOADER_RECORD_OFFSET 0xE4F00u
#endif
static int fmer_loader_record_allowed(uint32_t off) {
#ifdef FMER_PORTABLE_INSTALL
    return off==0xE7F00u || off==0xE4F00u;
#else
    return off==FMER_LOADER_RECORD_OFFSET;
#endif
}
static int fmer_loader_write_allowed(uint32_t off,uint32_t n)
{
#ifdef FMER_PORTABLE_INSTALL
    if(off>=0x92000u && off<0x93000u)return 0;
    if(off<0x92000u && n>0x92000u-off)return 0;
#endif
    return n && ((off>=0x4000u && off<=0x93000u && n<=0x93000u-off) ||
                 (fmer_loader_record_allowed(off) && n==2u));
}
#endif
