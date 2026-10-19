/* SPDX-License-Identifier: GPL-3.0-only
 * One main-loop consumer owns each complete SysEx mailbox. A frame arriving
 * after an empty peek is left for the next pass; a different parser must not
 * opportunistically consume it in the same pass. */
#ifndef FMER_FRAME_DISPATCH_H
#define FMER_FRAME_DISPATCH_H
static void fmer_frame_dispatch(void)
{
    const uint8_t *frame;
    uint32_t length;
    if (!ota_frame_get(&frame, &length)) return;
    if (length && (frame[0] == 0x43u || frame[0] == 0x7Du))
        companion_service(frame, length);
    else
        ota_service();
}
#endif
