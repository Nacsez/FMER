/* SPDX-License-Identifier: GPL-3.0-only
 * Portable installer: application code and its four CRC bytes may differ.
 * The final 32 opaque bytes may differ; their entire sector is never written.
 * All other encrypted layout/configuration/calibration bytes must match the
 * replacement, so writing it preserves them exactly. This is not a bootability
 * test and MUST NOT replace the exact-origin check used by guarded abort.
 */
static int ldr_layout_compatible(void) {
    static const uint8_t expected[32] = {
0x3c,0x96,0xf7,0x91,0x07,0x6c,0xb5,0x29,0xd4,0x2b,0xe1,0x22,0x5d,0x42,0xe4,0xe5,0xc8,0x20,0x72,0x8e,0x91,0xc1,0x87,0xe5,0x86,0x82,0xe3,0xd7,0x70,0x8a,0xcd,0x88};
    static const uint32_t spans[3][2]={{4,32},{36,0x120},{0x8de3c,0x8efe0}};
    fmer_sha256 hash; uint8_t block[512], digest[32]; uint32_t i,off,n;
    fmer_sha256_init(&hash);
    for(i=0;i<3;i++) for(off=spans[i][0];off<spans[i][1];off+=n) {
        n=spans[i][1]-off; if(n>sizeof block)n=sizeof block;
        if(ldr_fread(0x4000u+off,block,n))return 0;
        fmer_sha256_update(&hash,block,n); ldr_progress(0,0);
    }
    fmer_sha256_final(&hash,digest);
    return ota_memeq(digest,expected,32);
}

/* Read-only, fixed diagnostic windows. No addresses supplied by the host;
 * exclude boot identity/key and all user/storage partitions. */
static int ldr_metadata_page(uint32_t page, uint8_t *data) {
    uint32_t off;
    if(page>=20u)return -1;
    off=page<2u?0x4000u+page*256u:0x91e00u+(page-2u)*256u;
    return ldr_fread(off,data,256u);
}
