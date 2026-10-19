/* SPDX-License-Identifier: GPL-3.0-only
 * Copyright (C) 2026 Leo Kuroshita (@kurogedelic), Hügelton Instruments */
/* Host test of the Felucca update loader (firmware/loader/ldr_core.c): a fake
 * host serves a package over the SysEx protocol, the "device" flash starts as
 * another package's flash.bin (as if that firmware were installed).
 *   ldr_test OLD.fwsc NEW.fwsc */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../write_policy.h"
/* Independent profile constants exercise both real staging layouts. */
#ifdef FMER_CITRINE_STOCK
#define TEST_RECORD_OFFSET 0xE7F00u
#define OTHER_RECORD_OFFSET 0xE4F00u
#else
#define TEST_RECORD_OFFSET 0xE4F00u
#define OTHER_RECORD_OFFSET 0xE7F00u
#endif

#define FELUCCA_ID "ota-FM-1_900"
#define FELUCCA_OTA_DRYRUN 0

static uint8_t nor[0x100000], *logical;
static size_t logical_len;
static uint8_t rx[1024];
static uint32_t rx_len, rx_full, now_ms, requests, erases, bad_range, record_cleared, f0_asked;
static uint32_t corrupt_at, corrupt_once, no_finish, bad_finish, fail_program, programs;   /* the host serves a damaged byte / never says "success" */

static uint32_t pack7(const uint8_t *in, uint32_t n, uint8_t *out)
{
    uint32_t acc = 0, nb = 0, o = 0;
    while (n--) {
        acc |= (uint32_t)*in++ << nb;
        nb += 8;
        while (nb >= 7) { out[o++] = acc & 0x7F; acc >>= 7; nb -= 7; }
    }
    if (nb) out[o++] = acc & 0x7F;
    return o;
}
static uint32_t unpack7h(const uint8_t *in, uint32_t n, uint8_t *out)
{
    uint32_t acc = 0, nb = 0, o = 0;
    while (n--) {
        acc |= (uint32_t)*in++ << nb;
        nb += 7;
        if (nb >= 8) { out[o++] = (uint8_t)acc; acc >>= 8; nb -= 8; }
    }
    return o;
}

static int ota_wire_send(const uint8_t *p, uint32_t n)
{
    uint8_t u[64], m[600];
    uint32_t addr, len, i, s = 0;
    unpack7h(p + 1, n - 2, u);
    if (u[2] == 0x11) return 0;
    addr = u[7] | u[8] << 8 | u[9] << 16 | (uint32_t)u[10] << 24;
    len = u[11] | u[12] << 8 | u[13] << 16;
    requests++;
    memcpy(m, "\x00\x59\x30", 3);
    m[3] = (uint8_t)(len + 8); m[4] = (uint8_t)((len + 8) >> 8); m[5] = 0; m[6] = 0;
    memcpy(m + 7, &addr, 4);
    m[11] = (uint8_t)len; m[12] = (uint8_t)(len >> 8); m[13] = 0;
    if (addr == 0xF0000000u && no_finish) {
        f0_asked++;
        return 0;                                    /* no reply */
    }
    if (addr >= 0xE0000000u) {
        f0_asked += addr == 0xF0000000u;
        memset(m + 14, 0, len);
        memcpy(m + 14, bad_finish ? "failure" : "success", 8);
    } else {
        if (addr > logical_len || len > logical_len - addr) return 0;
        memcpy(m + 14, logical + addr, len);
        if (corrupt_at && addr <= corrupt_at && corrupt_at < addr + len) {
            m[14 + corrupt_at - addr] ^= 0x08;       /* (the frame's own checksum is fine: only the CRC sees it) */
            if (corrupt_once)
                corrupt_at = 0;
        }
    }
    for (i = 6; i < 14 + len; i++) s += m[i];
    m[14 + len] = (uint8_t)~s;
    rx_len = pack7(m, 15 + len, rx);
    rx_full = 1;
    return 0;
}
static int ota_frame_get(const uint8_t **p, uint32_t *n) { if (!rx_full) return 0; *p = rx; *n = rx_len; return 1; }
static void ota_frame_done(void) { rx_full = 0; }
static uint32_t ota_now_ms(void) { return now_ms; }
static void ota_idle(void) { now_ms++; }
static int ota_erase(uint32_t off) { (void)off; return -1; }
static int ota_prog(uint32_t off, const void *p, uint32_t n) { (void)off; (void)p; (void)n; return -1; }
static int ota_fread(uint32_t off, void *p, uint32_t n) { memcpy(p, nor + off, n); return 0; }
static void ota_show(uint32_t step, int32_t code) { (void)step; (void)code; }
static void ota_commit(const uint8_t *parm) { (void)parm; }
#include "../src/ota.c"

static int ldr_fread(uint32_t off, void *p, uint32_t n) { memcpy(p, nor + off, n); return 0; }
static int ldr_erase(uint32_t off)
{
    if (!fmer_loader_write_allowed(off,4096u) || (off & 0xFFFu)) {bad_range++;return -1;}
    if (off < 0x4000u) { printf("ERASE IN THE HEAD %#x\n", off); exit(1); }
    erases++;
    memset(nor + off, 0xFF, 0x1000);
    return 0;
}
static int ldr_prog(uint32_t off, const void *p, uint32_t n)
{
    const uint8_t *s = p;
    uint32_t i;
    if (!fmer_loader_write_allowed(off,n)) {bad_range++;return -1;}
    if (fail_program) return -1;
    programs++;
    for (i = 0; i < n; i++) nor[off + i] &= s[i];
    return 0;
}
static void ldr_record_clear(void) { record_cleared++; }
static uint32_t flash_unknown;
static int ldr_flash_known(void) { return !flash_unknown; }
static void ldr_progress(uint32_t done, uint32_t total) { (void)done; (void)total; }
static const uint8_t *self_image;
static uint32_t self_len;
static uint32_t ldr_image_size(void) { return self_len; }
static const uint8_t *ldr_image_bytes(void) { return self_image; }
#include "../sha256.h"
static uint8_t stock_digest[32];
static int hash_read_failure;
static int ldr_stock_app_matches(void)
{
    fmer_sha256 hash; uint8_t digest[32]; uint32_t off;
    if(hash_read_failure) return 0;
    fmer_sha256_init(&hash);
    for(off=0x4000;off<0x93000;off+=512) fmer_sha256_update(&hash,nor+off,512);
    fmer_sha256_final(&hash,digest);
    return !memcmp(digest,stock_digest,32);
}
#include "../ldr_core.c"

static uint8_t *load_logical(const char *path, size_t *len)
{
    FILE *f = fopen(path, "rb");
    uint8_t *raw = malloc(0x200000), *lg;
    size_t n, i;
    if (!f) { perror(path); exit(2); }
    n = fread(raw, 1, 0x200000, f);
    fclose(f);
    lg = malloc(n);
    for (i = 0; i < 20; i++) memcpy(lg + i * 47, raw + i * 48, 47);
    memcpy(lg + 20 * 47, raw + 20 * 48, n - 20 * 48);
    *len = n - 20;
    free(raw);
    return lg;
}

static uint32_t flash_off(const uint8_t *lg)        /* flash.bin offset in the logical image */
{
    uint8_t h[0x400];
    uint32_t i, n;
    memcpy(h, lg, sizeof h);
    ota_jl_enc(h, 0x40);
    n = ota_rd16(h + 8);
    for (i = 0; i < n; i++) {
        uint8_t *e = h + 0x40 + i * 0x50u;
        ota_jl_enc(e, 0x50);
        if (ota_rd16(e) == 0) return ota_rd32(e + 8);
    }
    return 0;
}

static int check(const char *what, int ok) { printf("%-56s %s\n", what, ok ? "ok" : "FAIL"); return ok ? 0 : 1; }

static uint8_t original[0x100000];
static uint8_t protected_head[0x4000];
static int separate_head;
static uint32_t file_off, ota_off, ota_size;

static void prepare(void)
{
    fmer_sha256 hash;
    uint8_t r[112] = {0}, h[32] = {0};
    memset(nor, 0xA5, sizeof nor);
    memcpy(nor, logical + file_off, 0x93000);
    if (separate_head) memcpy(nor, protected_head, sizeof protected_head);
    nor[0x5010] ^= 1;                          /* one old-app sector differs */
    memset(nor + 0xE0000, 0xFF, 0x5000);
    memcpy(nor + 0xE0020, logical + ota_off + 32, ota_size - 32);
    ota_wr16(h + 2, 0xFFFF); ota_wr32(h + 4, 0xE0000); ota_wr32(h + 8, ota_size);
    h[12] = 0x41; h[13] = 0xFF; ota_wr16(h + 14, 0xFFFF);
    memcpy(h + 16, "LOADER.BIN", 10); ota_wr16(h, ota_crc16(h + 2, 30, 0));
    memcpy(nor + 0xE0000, h, 32);
    ota_wr16(r + 2, 0x5A0D); ota_wr16(r + 4, 0x5A01); ota_wr16(r + 6, 0x5441);
    memcpy(r + 8, "ota-FM-1_015", 12); ota_wr32(r + 72, 0xE0000);
    ota_wr16(r, ota_crc16(r + 2, 78, 0)); memcpy(nor + TEST_RECORD_OFFSET, r, sizeof r);
    memcpy(original, nor, sizeof nor);
    fmer_sha256_init(&hash); fmer_sha256_update(&hash,nor+0x4000,0x8F000); fmer_sha256_final(&hash,stock_digest);
    requests = erases = programs = bad_range = record_cleared = f0_asked = 0;
    corrupt_at = corrupt_once = no_finish = bad_finish = fail_program = flash_unknown = 0;
    rx_full = now_ms = 0; ota_deadline = 0;
    hash_read_failure=0;
    ldr_app_dirty = ldr_record_offset = ldr_record_matches = ldr_state = 0;
}

static int preserved(void)
{
    return !memcmp(nor, original, 0x4000) &&
           !memcmp(nor + 0x93000, original + 0x93000, TEST_RECORD_OFFSET - 0x93000) &&
           !memcmp(nor + (TEST_RECORD_OFFSET+2), original + (TEST_RECORD_OFFSET+2), sizeof nor - (TEST_RECORD_OFFSET+2));
}

int main(int argc, char **argv)
{
    FILE *f; long bytes; uint8_t header[1024]; uint32_t unused, flsize, checksum;
    int bad = 0, rc;
    if (argc != 3 && argc != 4) { puts("usage: fmer_loader_test CANDIDATE.fwsc loader.bin [device-head-fixture.bin]"); return 2; }
    if (argc == 4) {
        f = fopen(argv[3], "rb"); if (!f) return 2;
        if (fread(protected_head,1,sizeof protected_head,f)!=sizeof protected_head || fgetc(f)!=EOF) { fclose(f); return 2; }
        fclose(f); separate_head=1;
    }
    logical = load_logical(argv[1], &logical_len);
    f = fopen(argv[2], "rb"); if (!f) return 2;
    fseek(f, 0, SEEK_END); bytes = ftell(f); rewind(f);
    if (bytes <= 0 || bytes > 0x8000) return 2;
    self_image = malloc((size_t)bytes); self_len = (uint32_t)bytes;
    if (fread((void *)self_image, 1, self_len, f) != self_len) return 2; fclose(f);
    rc = ota_ufw(header, &file_off, &flsize, &ota_off, &ota_size, &checksum);
    if (rc || flsize != 0x93000) return 2;

    {
        static const char *messages[]={"", "abc", "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq"};
        static const char *expected[]={"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"};
        uint32_t i,j; uint8_t digest[32]; char hex[65]; fmer_sha256 hash;
        for(i=0;i<3;i++) {
            fmer_sha256_init(&hash);
            for(j=0;messages[i][j];j++)fmer_sha256_update(&hash,(const uint8_t *)messages[i]+j,1);
            fmer_sha256_final(&hash,digest);
            for(j=0;j<32;j++)sprintf(hex+j*2,"%02x",digest[j]);
            bad+=check("SHA256 published vector (empty/abc/multiblock)",!strcmp(hex,expected[i]));
        }
        fmer_sha256_init(&hash);
        for(i=0;i<1000000;i++)fmer_sha256_update(&hash,(const uint8_t *)"a",1);
        fmer_sha256_final(&hash,digest);
        for(j=0;j<32;j++)sprintf(hex+j*2,"%02x",digest[j]);
        bad+=check("SHA256 published million-a vector",!strcmp(hex,"cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0"));
    }

    bad += check("708 write barrier permits app and exact staged record only",
                 fmer_loader_write_allowed(0x4000,256) && fmer_loader_write_allowed(0x91F00,256) &&
                 fmer_loader_write_allowed(TEST_RECORD_OFFSET,2) && !fmer_loader_write_allowed(TEST_RECORD_OFFSET,3) &&
                 !fmer_loader_write_allowed((TEST_RECORD_OFFSET-1),2) && !fmer_loader_write_allowed((TEST_RECORD_OFFSET+1),2));
    bad += check("708 write barrier rejects head, tail and integer-overflow ranges",
                 !fmer_loader_write_allowed(0x3FFF,2) && !fmer_loader_write_allowed(0x92FFF,2) &&
                 !fmer_loader_write_allowed(0x93000,2) && !fmer_loader_write_allowed(0xFFFFFFFFu,2) &&
                 !fmer_loader_write_allowed(0x4000,0xFFFFFFFFu));
    {
        uint32_t off,violations=0;
        for(off=0x97000;off<0xE0000;off++)
            if(fmer_loader_write_allowed(off,1) || fmer_loader_write_allowed(off,2) ||
               fmer_loader_write_allowed(off,256) || fmer_loader_write_allowed(off,4096))violations++;
        bad += check("708 journal every address97000-DFFFF rejects byte, CRC, page and sector writes",violations==0);
    }
#ifdef FMER_PORTABLE_INSTALL
    { uint8_t page[256];uint32_t i;int ok=1;prepare();
      for(i=0;i<20;i++) {uint32_t off=i<2?0x4000+i*256:0x91e00+(i-2)*256;
        if(ldr_metadata_page(i,page)||memcmp(page,nor+off,256))ok=0;}
      bad+=check("bounded metadata readback is exact and read-only",ok&&!erases&&!programs);
      bad+=check("metadata readback rejects every out-of-range page",ldr_metadata_page(20,page)<0&&ldr_metadata_page(0xffffffffu,page)<0&&!erases&&!programs);
    }
    prepare(); nor[0x88000]^=0x80;
    bad += check("different application code is compatible",ldr_layout_compatible());
    prepare(); nor[0x4004]^=1;
    bad += check("changed layout rejected before writes",!ldr_layout_compatible() && ldr_session()==-19 && !erases && !programs);
    prepare(); nor[0x92f00]^=1;
    bad += check("changed calibration/padding rejected before writes",!ldr_layout_compatible() && ldr_session()==-19 && !erases && !programs);
    { uint8_t tail[4096];prepare();nor[0x92ff2]^=0x39;nor[0x92ff5]^=4;
      memcpy(tail,nor+0x92000,4096);
      bad+=check("opaque trailer differences admitted",ldr_layout_compatible());
      rc=ldr_session();
      bad+=check("Amethyst trailer retained and application installed",rc==0&&!memcmp(tail,nor+0x92000,4096)&&!memcmp(nor+0x4000,logical+file_off+0x4000,0x8e000)&&!bad_range);
      bad+=check("final sector write barrier",!fmer_loader_write_allowed(0x92000,1)&&!fmer_loader_write_allowed(0x91fff,2));
    }
    prepare(); memcpy(nor+OTHER_RECORD_OFFSET,nor+TEST_RECORD_OFFSET,80);memset(nor+TEST_RECORD_OFFSET,0,80);
    rc=ldr_session();bad += check("FMER record also proven and completed",rc==0 && record_cleared && !bad_range);
#else
    bad += check("other staging profile is never writable", !fmer_loader_write_allowed(OTHER_RECORD_OFFSET,2));
    prepare(); memcpy(nor+OTHER_RECORD_OFFSET,nor+TEST_RECORD_OFFSET,80);memset(nor+TEST_RECORD_OFFSET,0,80);
    rc=ldr_session();bad += check("other staging profile record refuses before any write",rc==-15 && !erases && !programs);
#endif
    prepare(); rc = ldr_records_preflight();
    bad += check("complete staged image proof recognizes one own record", rc == 0 && ldr_record_matches == 1);
    bad += check("preflight is read-only", !memcmp(nor, original, sizeof nor) && !erases && !programs);
    rc = ldr_session();
    bad += check("install completes and exactly writes changed app sectors", rc == 0 && erases == 1 && !bad_range);
    bad += check("entire app matches package", !memcmp(nor + 0x4000, logical + file_off + 0x4000, 0x8F000));
    bad += check("boot, VM, BTIF, USR, identity unchanged except record CRC", preserved());
    bad += check("record invalidated only after success; RAM cleared", !ota_rd16(nor + TEST_RECORD_OFFSET) && record_cleared && f0_asked);
    bad += check("abort forbidden after any app erase", ldr_abort() == -17);

    prepare(); rc = ldr_abort();
    bad += check("fresh proven abort returns old app unchanged", rc == 0 && ldr_state == 5 && !erases && preserved() &&
                 !memcmp(nor + 0x4000, original + 0x4000, 0x8F000));

    prepare(); nor[TEST_RECORD_OFFSET] ^= 1; rc = ldr_session();
    bad += check("invalid record refuses without any write", rc == -15 && !erases && !programs);
    prepare(); memcpy(nor + 0xDFF00, nor + TEST_RECORD_OFFSET, 80); rc = ldr_session();
    bad += check("ambiguous valid records refuse without any write", rc == -15 && !erases && !programs);
    prepare(); memcpy(nor + 0xDFF00, nor + TEST_RECORD_OFFSET, 80); memset(nor + TEST_RECORD_OFFSET,0,80); rc = ldr_session();
    bad += check("708 sole valid record inside native journal refuses before app write",rc==-15 && !erases && !programs);
    prepare(); memcpy(nor + 0x97F00, nor + TEST_RECORD_OFFSET, 80); memset(nor + TEST_RECORD_OFFSET,0,80); rc = ldr_abort();
    bad += check("708 journal low-bound record refuses abort without writes",rc==-15 && !erases && !programs);
    prepare(); ldr_record_offset=0xDFF00;memcpy(ldr_active_record,nor+TEST_RECORD_OFFSET,80);memcpy(nor+0xDFF00,ldr_active_record,80);
    rc=ldr_records_drop();bad += check("708 cleanup rejects journal record even after metadata corruption",rc==-15 && !programs && !record_cleared);
    prepare(); nor[0xE0100] ^= 1; rc = ldr_session();
    bad += check("staged loader mismatch refuses without any write", rc == -15 && !erases && !programs);
    prepare(); flash_unknown = 1; rc = ldr_session();
    bad += check("unknown JEDEC refuses and keeps every record byte", rc == -14 && !erases && !programs && !record_cleared);

    prepare(); bad_finish = 1; rc = ldr_session();
    bad += check("incorrect finish payload retains recovery records", rc == -13 && !record_cleared && ota_rd16(nor + TEST_RECORD_OFFSET));
    bad_finish = 0; rc = ldr_session();
    bad += check("retry after missing finish completes", rc == 0 && record_cleared);
    prepare(); no_finish = 1; rc = ldr_session();
    bad += check("missing finish retains recovery records", rc == -13 && !record_cleared);
    ldr_app_dirty=ldr_state=0; rc=ldr_abort();
    bad += check("cold restart cannot abort a rewritten app",rc == -17 && !record_cleared && ota_rd16(nor+TEST_RECORD_OFFSET));

    prepare(); nor[0x80000]^=1; ldr_app_dirty=0; rc=ldr_abort();
    bad += check("full app hash catches changes beyond first sectors",rc == -17 && !record_cleared && !erases);
    prepare(); hash_read_failure=1; rc=ldr_abort();
    bad += check("app hash read failure refuses abort",rc == -17 && !record_cleared && !erases);
    prepare(); fail_program=1; rc=ldr_session(); fail_program=0; ldr_app_dirty=ldr_state=0;
    bad += check("power loss after erase cannot abort partial sector",rc != 0 && ldr_abort() == -17 && !record_cleared);

    prepare(); corrupt_at = file_off + 0x30123; corrupt_once = 1; rc = ldr_session();
    bad += check("one transport corruption is repaired by CRC retry", rc == 0 && record_cleared);
    prepare(); corrupt_at = file_off + 0x30123; rc = ldr_session();
    bad += check("persistent corruption keeps record after three passes", rc == -12 && !record_cleared);
    prepare(); fail_program = 1; rc = ldr_abort();
    bad += check("failed record invalidation never clears RAM", rc == -15 && !record_cleared && !erases);
    prepare(); unused = (uint32_t)logical_len; logical_len = 100; rc = ldr_session(); logical_len = unused;
    bad += check("truncated host package cannot start app writes", rc != 0 && !erases && !programs);

    puts(bad ? "FMER LOADER TEST FAILED" : "FMER loader regression passed");
    return bad != 0;
}

