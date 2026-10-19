/* SPDX-License-Identifier: GPL-3.0-only
 * Copyright (C) 2026 Leo Kuroshita (@kurogedelic), Hügelton Instruments */
/* FMER derivative update loader (device side). Runs from RAM, started by the SPL from
 * an update record, with interrupts off: USB is polled from the main loop.
 * It is a USB-MIDI device "FMER Update" (1209:0002) that answers the
 * M-UPGRADE update protocol as "ota-FM-1_708" (hosts look for "ota-"), and
 * writes the app area plus two proven update-record CRC bytes (ldr_core.c).
 * Guarded abort requires a fresh full pinned-original-app SHA-256 match.
 * The deliberate UBOOT soft key works here too.
 * Single compilation unit. */
#include <stdint.h>
#define FELUCCA_LOADER 1
#define FELUCCA_CDC 0
#define FELUCCA_OTA 1
#define FELUCCA_OTA_DRYRUN 0
#define FELUCCA_USB_PID 0x0002
#ifdef FMER_PORTABLE_INSTALL
#define FELUCCA_ID "ota-FM-1_935"
#else
#define FELUCCA_ID "ota-FM-1_733"
#endif
#define RING_PUBLISH() __asm__ volatile("" ::: "memory")
#include "fm1_time.h"
#include "fm1_sys.h"
/* FMER708: the native journal is protected independently of record contents.
 * The only non-application write is our exact staged record's two CRC bytes. */
#include "write_policy.h"
#define FL_RANGE_OK(off, n) fmer_loader_write_allowed((off),(n))
#include "fm1_flash.h"
#include "src/libc.c"
#include "src/usb.c"

static uint32_t ldr_ms(void)   /* monotonic ms; survives the TIMER4 wrap (178.9 s) */
{
    static uint32_t last, acc, ms;
    uint32_t now = fm1_ticks();
    acc += now - last;
    last = now;
    ms += acc / (1000u * FM1_TICKS_PER_US);
    acc %= 1000u * FM1_TICKS_PER_US;
    return ms;
}

static void ldr_poll(void)                          /* USB at ~2 kHz, watchdog */
{
    static uint32_t last;
    uint32_t now = fm1_ticks();
    fm1_wdt_feed();
    if (now - last >= 500u * FM1_TICKS_PER_US) {
        last = now;
        usb_poll();
    }
}

/* ---- ota.c hooks (the SysEx frame hooks are in usb.c) ---- */
static uint32_t ota_now_ms(void) { return ldr_ms(); }
static void ota_idle(void) { ldr_poll(); }
/* step-1 hooks of ota.c: not used by the loader */
static int ota_erase(uint32_t off) { (void)off; return -1; }
static int ota_prog(uint32_t off, const void *p, uint32_t n) { (void)off; (void)p; (void)n; return -1; }
static int ota_fread(uint32_t off, void *p, uint32_t n) { return fl_read_ram(off, p, n); }
static void ota_show(uint32_t step, int32_t code) { (void)step; (void)code; }
static void ota_commit(const uint8_t *parm) { (void)parm; }
#define FMER_LOADER_DIAGNOSTICS 1
static int ldr_diagnostic(const uint8_t *p, uint32_t n);
#include "src/ota.c"

/* ---- ldr_core.c hooks: interrupts are off for the whole loader ---- */
static int ldr_fread(uint32_t off, void *p, uint32_t n) { return fl_read_ram(off, p, n); }
static int ldr_erase(uint32_t off)
{
    uint32_t took;
    return fl_erase4k_ram(off, &took);
}
static int ldr_prog(uint32_t off, const void *p, uint32_t n)
{
    uint32_t took;
    return fl_prog_ram(off, p, n, &took);
}
static void ldr_record_clear(void)
{
    fm1_updata_parm_clear();                        /* CRC 0: the SPL ignores it on a warm reset */
}
static int ldr_flash_known(void) { return fl_jedec_ram() == 0x856014u; }   /* as the app (project.c) */
static void ldr_progress(uint32_t done, uint32_t total) { (void)done; (void)total; ldr_poll(); }
/* Copy once, before any USB/HAL init can modify initialized data that shares
 * the RAM image. Full decompression equality, not a CRC collision, qualifies
 * a flash update record as pointing to this loader. */
static uint8_t ldr_self_image[0x8000];
static uint32_t ldr_self_len;
static uint32_t ldr_image_size(void) { return ldr_self_len; }
static const uint8_t *ldr_image_bytes(void) { return ldr_self_image; }
#include "sha256.h"
#include "stock_reference.h"
static int ldr_stock_app_matches(void)
{
    fmer_sha256 hash;
    uint8_t block[512], digest[32];
    uint32_t off;
    if (!FMER_STOCK_REFERENCE_READY) return 0;
    fmer_sha256_init(&hash);
    for (off = 0x4000u; off < 0x93000u; off += sizeof block) {
        if (ldr_fread(off, block, sizeof block)) return 0;
        fmer_sha256_update(&hash, block, sizeof block);
        ldr_poll();
    }
    fmer_sha256_final(&hash, digest);
    return ota_memeq(digest, fmer_stock_app_sha256, sizeof digest);
}
#include "ldr_core.c"

/* FMER private development protocol, manufacturer 0x7D. Commands are literal;
 * reply payload is continuous LSB-first pack7 of 16 checksum-protected bytes.
 * No reply claims recovery beyond the uniquely proven staging record. */
static int ldr_diagnostic(const uint8_t *p, uint32_t n)
{
    static const uint8_t prefix[6] = {0x7D, 'F', 'M', 'E', 'R', 1};
    uint8_t payload[16], wire[28];
    uint32_t i, sum = 0;
    int aborted = 0;
#ifdef FMER_PORTABLE_INSTALL
    if(n==9u && ota_memeq(p,prefix,6) && p[6]==3u && p[7]<20u && p[8]==(0x7fu-p[7])) {
        uint8_t data[259], reply[305];uint32_t j, checksum=0;
        data[0]=p[7];data[1]=0;
        for(j=2;j<258;j++)data[j]=0;
        if(ldr_metadata_page(p[7],data+2))data[1]=1;
        for(j=0;j<258;j++)checksum+=data[j];data[258]=(uint8_t)~checksum;
        reply[0]=0xf0;for(j=0;j<6;j++)reply[j+1]=prefix[j];reply[7]=0x43;
        j=8+ota_pack7(data,259,reply+8);reply[j++]=0xf7;
        ota_wire_send(reply,j);return 1;
    }
#endif
    if (n != 7u || !ota_memeq(p, prefix, 6) || (p[6] != 1u && p[6] != 2u))
        return 0;
    if (p[6] == 2u)
        aborted = ldr_abort() == 0;
    payload[0] = (uint8_t)ldr_state;
    ota_wr32(payload + 1, (uint32_t)ldr_last_error);
    payload[5] = (uint8_t)(ldr_app_dirty != 0);
    payload[6] = (uint8_t)ldr_record_matches;
    ota_wr32(payload + 7, ldr_record_offset);
    ota_wr32(payload + 11, ldr_image_size());
    for (i = 0; i < 15u; i++) sum += payload[i];
    payload[15] = (uint8_t)~sum;
    wire[0] = 0xF0;
    for (i = 0; i < 6u; i++) wire[i + 1] = prefix[i];
    wire[7] = p[6] | 0x40u;
    i = 8u + ota_pack7(payload, 16, wire + 8);
    wire[i++] = 0xF7;
    ota_wire_send(wire, i);
    if (aborted) {
        uint32_t begin = ldr_ms();
        while (ldr_ms() - begin < 200u) ldr_poll();
        usb_detach();
        fm1_delay_ms(30);
        fm1_core_reset();
    }
    return 1;
}

extern uint32_t _bss_start[], _bss_end[];
extern uint8_t _start[], _image_end[];

void ldr_main(void)
{
    fm1_wdt_arm(0x0D);                              /* ~8 s, fed by ldr_poll */
    fm1_time_init();
    usb_start();
    ldr_state = 1;
    ldr_last_error = ldr_flash_known() ? ldr_records_preflight() : LDR_EFLASH;
    ldr_state = ldr_last_error ? 4u : 0u;
#ifdef FMER_PORTABLE_INSTALL
    /* Dirty here means incompatible layout, not different application code. */
    ldr_app_dirty = !ldr_layout_compatible();
#else
    ldr_app_dirty = !ldr_stock_app_matches();
#endif
    for (;;) {
        ldr_poll();
        usb_retry(ldr_ms());
        if (usb.uboot_req) {                        /* soft key: mask-ROM UBOOT, as in Felucca */
            usb_detach();
            fm1_delay_ms(30);
            fm1_enter_uboot();
        }
        ota_service();                              /* handshake */
        if (usb.ota_req) {
            int rc;
            usb.ota_req = 0;
            rc = ldr_session();
            if (rc == 0) {                         /* errors retain the records and remain in loader */
                fm1_delay_ms(200);                  /* the "success" reply leaves */
                usb_detach();
                fm1_delay_ms(30);
                fm1_core_reset();                   /* the SPL boots the new app */
            }
        }
    }
}

void ldr_cstart(void)
{
    uint32_t *p;
    uint32_t i, size = (uint32_t)(_image_end - _start);
    /* Retain the active RAM update record until verified flash-record cleanup.
     * It lives outside this image/BSS; no RAM/flash equivalence is assumed. */
    for (p = _bss_start; p < _bss_end; p++)
        *p = 0;
    if (size <= sizeof ldr_self_image) {
        for (i = 0; i < size; i++) ldr_self_image[i] = _start[i];
        ldr_self_len = size;
    }
    ldr_main();
}
