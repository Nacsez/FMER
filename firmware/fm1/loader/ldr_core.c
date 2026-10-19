/* SPDX-License-Identifier: GPL-3.0-only
 * Copyright (C) 2026 Leo Kuroshita (@kurogedelic), Hügelton Instruments */
/* Felucca update loader, the portable part (step 2 of the M-UPGRADE update
 * protocol).
 *
 * The host serves the package ("logical image") with cmd 0x30 reads (ota.c).
 * The loader:
 *   1. reads the UFW header and finds flash.bin;
 *   2. checks that the package's app area decrypts with THIS chip's key
 *      (taken from isd_config.ini in the device's own flash head), so a
 *      package for another key is refused before anything is erased;
 *   3. writes ONLY the app area [0x4000, 0x93000), sector by sector, skipping
 *      sectors that are already equal, and verifies each one; the flash head
 *      (SPL, isd_config) is never written;
 *   4. checks the CRC16 the package stores for flash.bin against everything it
 *      was served (the head too, which it never writes; a mismatch: up to two
 *      more passes, rewriting what differs), asks 0xF0000000 ("success"), then
 *      invalidates the update record (RAM and flash) so the SPL boots the new
 *      app, and resets. A damaged package or no "success" leaves the record:
 *      the loader stays (also after a power cycle) and the host can resume.
 * Power loss during 3: the record is still there, the SPL runs the loader
 * again on the next power-on and the host can resume.
 *
 * Hooks from the platform (loader.c, tests/ldr_test.c):
 *   ldr_fread(off, p, n)  ldr_erase(off)  ldr_prog(off, p, n)   flash, 0 = ok
 *   ldr_record_clear()    forget the RAM update record
 *   ldr_flash_known()     the flash chip is the expected 1 MiB part; otherwise no writes
 *   ldr_image_bytes/size() startup snapshot, for exact staged-loader comparison
 *   ldr_stock_app_matches() fresh full published-stock SHA-256 for reversible abort
 *   ldr_progress(done, total)
 * plus the ota.c hooks (frames, time, idle). */
#define LDR_APP_LO 0x4000u
#define LDR_APP_HI 0x93000u
#define LDR_REC_LO 0x93000u                     /* update records live above the app ... */
#define LDR_REC_HI 0xE9000u                     /* FMER: stock V15 VM only; exclude BTIF/USR/key_mac */
#include "write_policy.h"

static int ldr_fread(uint32_t off, void *p, uint32_t n);
static int ldr_erase(uint32_t off);
static int ldr_prog(uint32_t off, const void *p, uint32_t n);
static void ldr_record_clear(void);
static int ldr_flash_known(void);
static void ldr_progress(uint32_t done, uint32_t total);
static uint32_t ldr_image_size(void);
static const uint8_t *ldr_image_bytes(void);    /* immutable snapshot taken before USB/HAL init */
static int ldr_stock_app_matches(void);         /* full raw app SHA-256; read error is a mismatch */

#ifdef FMER_PORTABLE_INSTALL
#include "compatibility.h"
#endif

/* SFC cipher: per 32-byte block, key ^ (block offset >> 2) */
static void ldr_sfc(uint8_t *p, uint32_t n, uint32_t base_off, uint32_t key)
{
    uint32_t i, j;
    for (i = 0; i < n; i += 32u) {
        uint32_t k = key ^ ((base_off + i) >> 2);
        for (j = 0; j < 32u && i + j < n; j++) {
            p[i + j] ^= (uint8_t)k;
            k = ((k << 1) ^ (k & 0x8000u ? 0x1021u : 0u)) & 0xFFFFu;
        }
    }
}

/* chip key from the device's flash head: JLFS top entries (ENC 0xFFFF) -> isd_config.ini blob */
static int ldr_chip_key(uint32_t *key)
{
    uint8_t e[32], blob[34];
    uint32_t off, i, sum, k;
    for (off = 32; off < 0x400u; off += 32u) {
        if (ldr_fread(off, e, 32))
            return -1;
        ota_jl_enc(e, 32);
        if (ota_crc16(e + 2, 30, 0) != ota_rd16(e))
            return -2;
        if (!ota_memeq(e + 16, (const uint8_t *)"isd_config.ini", 15)) {
            if (ota_rd16(e + 14))
                return -3;                               /* last entry, not found */
            continue;
        }
        if (ldr_fread(ota_rd32(e + 4), blob, 34) || ota_crc16(blob, 32, 0) != ota_rd16(blob + 32))
            return -4;
        for (i = 0, sum = 0; i < 16u; i++)
            sum += blob[i];
        sum &= 0xFFu;
        sum = sum >= 0xE0u ? 0xAAu : sum <= 0x10u ? 0x55u : sum;
        for (i = 0, k = 0; i < 16u; i++)
            if ((uint32_t)(blob[16 + i] ^ blob[15 - i]) < sum)
                k |= 1u << i;
        *key = k;
        return 0;
    }
    return -3;
}

#define LDR_EBADPKG (-12)                       /* flash.bin as served does not match the package's CRC16 */
#define LDR_ENOFIN (-13)                        /* no "success" from the host */
#define LDR_EFLASH (-14)                        /* another flash chip: no writes of any kind */
#define LDR_ERECORD (-15)                       /* active record cannot be proven / invalidation failed */

/* FMER preservation policy: never erase a record's containing sector. Exactly
 * one valid VM record must refer to a staged loader whose complete decompressed
 * bytes equal our startup image snapshot. RAM/flash record equality is NOT
 * assumed. Another valid record is ambiguous and refuses before app writes. */
static uint32_t ldr_record_offset;
static uint8_t ldr_active_record[80];
static uint32_t ldr_app_dirty;                  /* set before first erase attempt; never reset on retry */
static uint32_t ldr_record_matches;
static int ldr_last_error;
static uint32_t ldr_state;                     /* v1 diagnostics: idle/preflight/updating/complete/refused/aborted */

static int ldr_record_valid(const uint8_t *r)
{
    return ota_rd16(r) && ota_rd16(r) == ota_crc16(r + 2, 78, 0) &&
           ota_rd16(r + 2) == 0x5A0Du && ota_rd16(r + 4) == 0x5A01u &&
           ota_rd16(r + 6) == 0x5441u;
}

static int ldr_block_matches(const uint8_t *b, uint32_t n, uint32_t base, uint32_t total)
{
    const uint8_t *self = ldr_image_bytes() + base;
    uint32_t p = 0, out = 0, token, count, off, extra, i;
    while (p < n) {
        token = b[p++]; count = token >> 4;
        if (count == 15u) do {
            if (p >= n) return -1;
            extra = b[p++]; count += extra;
            if (count > total) return -1;
        } while (extra == 255u);
        if (count > n - p || count > total - out) return -1;
        for (i = 0; i < count; i++) if (b[p++] != self[out++]) return -1;
        if (p == n) return out == total && !(token & 15u) ? 0 : -1;
        if (n - p < 2u) return -1;
        off = ota_rd16(b + p); p += 2;
        if (!off || off > out) return -1;
        count = token & 15u;
        if (count == 15u) do {
            if (p >= n) return -1;
            extra = b[p++]; count += extra;
            if (count > total) return -1;
        } while (extra == 255u);
        count += 4u;
        if (count > total - out) return -1;
        for (i = 0; i < count; i++, out++) if (self[out] != self[out - off]) return -1;
    }
    return -1;
}

static int ldr_stage_matches(uint32_t stage)
{
    static uint8_t block[4096];
    uint8_t h[64], lengths[8];
    uint32_t end, at, out = 0, compressed, unpacked, self_len = ldr_image_size();
    if (!self_len || stage < LDR_REC_LO || stage > LDR_REC_HI - sizeof h || (stage & 0xFFFu))
        return -1;
    if (ldr_fread(stage, h, sizeof h) || ota_crc16(h + 2, 30, 0) != ota_rd16(h) ||
        ota_rd32(h + 4) != stage || h[12] != 0x41u ||
        !ota_memeq(h + 16, (const uint8_t *)"LOADER.BIN", 10) ||
        ota_rd32(h + 8) < 72u || ota_rd32(h + 8) > LDR_REC_HI - stage ||
        ota_crc16(h + 34, 30, 0) != ota_rd16(h + 32) ||
        ota_rd32(h + 40) != 0x01C0A800u || ota_rd32(h + 36) != self_len ||
        ota_rd16(h + 34) != ota_crc16(ldr_image_bytes(), self_len, 0))
        return -1;
    at = stage + 64u; end = stage + ota_rd32(h + 8);
    while (at < end) {
        if (end - at < 8u || ldr_fread(at, lengths, 8)) return -1;
        at += 8; compressed = ota_rd32(lengths); unpacked = ota_rd32(lengths + 4);
        if (!compressed || compressed > sizeof block || compressed > end - at || out >= self_len ||
            unpacked != (self_len - out < 4096u ? self_len - out : 4096u) ||
            ldr_fread(at, block, compressed) || ldr_block_matches(block, compressed, out, unpacked))
            return -1;
        at += compressed; out += unpacked;
        ldr_progress(0, 0);                          /* keep USB and watchdog alive during proof */
    }
    return out == self_len ? 0 : -1;
}

static int ldr_records_preflight(void)
{
    uint32_t s, valid = 0;
    uint8_t r[80];
    ldr_record_offset = ldr_record_matches = 0;
    for (s = LDR_REC_LO + 0x1000u; s <= LDR_REC_HI; s += 0x1000u) {
        if (ldr_fread(s - 0x100u, r, sizeof r))
            return LDR_ERECORD;
        if (ota_rd16(r + 6) != 0x5441u || !ota_rd16(r) || ota_rd16(r) != ota_crc16(r + 2, 78, 0))
            continue;
        valid++;
        if (ldr_record_valid(r) && !ldr_stage_matches(ota_rd32(r + 72))) {
            ldr_record_matches++;
            ldr_record_offset = s - 0x100u;
            for (uint32_t i = 0; i < sizeof r; i++) ldr_active_record[i] = r[i];
        }
    }
    if (valid != 1u || ldr_record_matches != 1u || !fmer_loader_record_allowed(ldr_record_offset)) {
        ldr_record_offset = 0;
        return LDR_ERECORD;
    }
    return 0;
}

/* NOR permits 1->0 programming without erase. Zero only the matched record CRC,
 * verify both zero bytes and all remaining bytes, then clear RAM. */
static int ldr_records_drop(void)
{
    uint8_t r[80], zero[2] = {0, 0};
    if (!fmer_loader_record_allowed(ldr_record_offset) || ldr_fread(ldr_record_offset, r, sizeof r) ||
        !ota_memeq(r, ldr_active_record, sizeof r) ||
        ldr_prog(ldr_record_offset, zero, 2) ||
        ldr_fread(ldr_record_offset, r, sizeof r) || ota_rd16(r) ||
        !ota_memeq(r + 2, ldr_active_record + 2, sizeof r - 2))
        return LDR_ERECORD;
    ldr_record_clear();
    return 0;
}

static int ldr_pass(void)
{
    static uint8_t hdr[0x400], sec[0x1000], cur[0x1000];
    uint32_t i, k, fl_off, fl_size, ota_off, ota_len, key, s, n, want, crc = 0, done = 0;
    int rc;
    /* 1. UFW header + entry list (ota.c) */
    if ((rc = ota_ufw(hdr, &fl_off, &fl_size, &ota_off, &ota_len, &want)) != 0)
        return rc;
    if (!fl_off || fl_size != LDR_APP_HI)
        return -3;
    ldr_state = 1;
    if (!ldr_flash_known())
        return LDR_EFLASH;
    if ((rc = ldr_records_preflight()) != 0)
        return rc;
#ifdef FMER_PORTABLE_INSTALL
    if (!ldr_layout_compatible()) return -19;
#endif
    ldr_state = 2;
    /* 2. the package's app area must decrypt with this chip's key */
    if ((rc = ldr_chip_key(&key)) != 0)
        return -40 + rc;
    if (ota_read(fl_off + LDR_APP_LO, sec, 32))
        return -5;
    ldr_sfc(sec, 32, 0, key);
    if (ota_crc16(sec + 2, 30, 0) != ota_rd16(sec))
        return -6;                                       /* package for another chip key */
    /* the head of flash.bin is never written, but it is part of the package's CRC */
    for (s = 0; s < LDR_APP_LO; s += 512u) {
        if (ota_read(fl_off + s, sec, 512))
            return -7;
        crc = ota_crc16(sec, 512, crc);
    }
    /* 3. app area, sector by sector */
    for (s = LDR_APP_LO; s < LDR_APP_HI; s += 0x1000u) {
        for (k = 0; k < 0x1000u; k += 512u)
            if (ota_read(fl_off + s + k, sec + k, 512))
                return -7;
        crc = ota_crc16(sec, 0x1000u, crc);
        if (ldr_fread(s, cur, 0x1000u))
            return -8;
#ifdef FMER_PORTABLE_INSTALL
        /* The final sector contains immutable calibration and an opaque
         * per-unit trailer. Compare all but the final 32 bytes, then leave
         * the WHOLE sector untouched. CRC above still covers received bytes.
         * No erase/program means preservation also survives interruption. */
        if (s == 0x92000u) {
            if (!ota_memeq(sec, cur, 0xFE0u)) return -19;
            done += 0x1000u;
            ldr_progress(done, LDR_APP_HI - LDR_APP_LO);
            continue;
        }
#endif
        if (!ota_memeq(sec, cur, 0x1000u)) {
            uint32_t tries;
            for (tries = 0; tries < 2u; tries++) {
                ldr_app_dirty = 1;                       /* abort is forbidden even if erase reports failure */
                if (ldr_erase(s))
                    return -9;
                for (k = 0; k < 0x1000u; k += 256u)
                    if (ldr_prog(s + k, sec + k, 256))
                        return -10;
                if (ldr_fread(s, cur, 0x1000u))
                    return -8;
                if (ota_memeq(sec, cur, 0x1000u))
                    break;
            }
            if (tries == 2u)
                return -11;                              /* verify failed twice */
        }
        done += 0x1000u;
        ldr_progress(done, LDR_APP_HI - LDR_APP_LO);
    }
    for (s = LDR_APP_HI; s < fl_size; s += n) {          /* (a flash.bin longer than the app area) */
        n = fl_size - s < 512u ? fl_size - s : 512u;
        if (ota_read(fl_off + s, sec, n))
            return -7;
        crc = ota_crc16(sec, n, crc);
    }
    /* 4. finish: the whole package arrived as it was built, the host confirms, the record goes,
     *    the SPL boots the app */
    if (crc != want)
        return LDR_EBADPKG;
    for (i = 0; i < 4u; i++)
        if (!ota_read(0xF0000000u, sec, 8) && ota_memeq(sec, (const uint8_t *)"success", 8))
            break;
    if (i == 4u)
        return LDR_ENOFIN;
    return ldr_records_drop();
}

/* a pass that does not add up (a byte damaged on the way) is run again: the host answers any read, so it
 * just serves the image once more and the sectors that differ are rewritten; a package that is damaged
 * itself fails every pass and the record stays */
static int ldr_session(void)
{
    int rc = LDR_EBADPKG;
    uint32_t pass;
    for (pass = 0; pass < 3u && rc == LDR_EBADPKG; pass++)
        rc = ldr_pass();
    ldr_last_error = rc;
    ldr_state = rc ? 4u : 3u;
    return rc;
}

static int ldr_abort(void)
{
    int rc;
    if (ldr_state == 1u || ldr_state == 2u) return ldr_last_error = -18;
    if (ldr_app_dirty) return ldr_last_error = -17;
    if (!ldr_flash_known()) return ldr_last_error = LDR_EFLASH;
    if ((rc = ldr_records_preflight()) != 0) return ldr_last_error = rc;
    /* Recompute independently of volatile state: a cold reset cannot make a
     * partially programmed app eligible for abort. No flash journal needed. */
    if (!ldr_stock_app_matches()) { ldr_app_dirty = 1; return ldr_last_error = -17; }
    rc = ldr_records_drop();
    ldr_state = rc ? 4u : 5u;
    return ldr_last_error = rc;
}
