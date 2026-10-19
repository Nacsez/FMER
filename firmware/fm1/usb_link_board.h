/* SPDX-License-Identifier: GPL-3.0-only
 * USB0 adapter. Included after the existing MIDI ring and board state.
 * Only TIMER5 owns SIE while link_host is set. Main switches owners with IRQs
 * masked briefly; attach/reset settling is timed in usb_link.h, never slept.
 */
static volatile uint32_t link_host,link_io_error;
static uint32_t link_role,link_saved,link_saved_channel;
static fmer_midi_settings_t link_saved_midi;
static uint32_t ul_read(uint32_t reg)
{
    uint32_t i;
    if(link_io_error || !fm1_usb_sie_on()) {link_io_error=1;return 0;}
    fm1_usb_sie_rd_start(reg);
    for(i=0;i<128u;i++)if(fm1_usb_sie_done())return fm1_usb_sie_data();
    link_io_error=1;return 0;
}
static void ul_write(uint32_t reg,uint32_t value)
{
    uint32_t i;
    if(link_io_error || !fm1_usb_sie_on()){link_io_error=1;return;}
    fm1_usb_sie_wr_start(reg,value);
    for(i=0;i<128u;i++)if(fm1_usb_sie_done())return;
    link_io_error=1;
}
static void ul_off(void){fm1_usb_off();}
static void ul_attach(void *control)
{
    FM1_CLK_CON1 &= ~3u;
    FM1_USB_EP0_ADR=(uint32_t)(uintptr_t)control;
    FM1_USB_CON1=0;
    /* SDK USB0 host: input pads, D+/D- pulldowns, CID=0, PHY/NRST/VBUS=1.
     * VBUS here is the controller sense override, NOT a board 5V supply.
     * No charger, boost, GPIO power or Type-C CC register is touched. */
    FM1_USB_IO_CON0=(1u<<9)|(1u<<10)|0x3cu;
    FM1_USB_CON0=0x25u;
    fm1_usb_ep_enable(3u);
}
static void ul_dma_control(void *p,uint32_t n){fm1_usb_ep0_send(p,n);}
static void ul_dma_bulk(void *rx,void *tx){fm1_usb_ep_rxbuf(1,rx);fm1_usb_ep_txbuf(1,tx);}
static void ul_dma_send(void *p,uint32_t n){fm1_usb_ep_send(1,p,n);}
static void ul_rx_sync(void){fm1_usb_rx_sync();}
static void ul_disconnect(void)
{
    usb.config=0;usb.suspended=1;mo_r=mo_w;
    midi_tx_recovery=midi_tx_stop_pending=0;
    /* Existing audio-owner USB disconnect detection releases USB-owned notes.
     * Do not manufacture an overflow or clear unrelated TRS/physical notes. */
}
static void ul_connected(void){usb.config=1;usb.suspended=0;midi_tx_recovery=0xffffu;}
static int ul_midi_receive(uint32_t p)
{
    uint32_t cin=p&15u,st=(p>>8)&255u;
    if(p&0xf0u)return 0; /* cable 0 only */
    if(cin>=8 && cin<=14 && (st>>4)==cin && !(p&0x80800000u))return midi_enqueue(p,1);
    if(cin==3 && st==0xf2 && !(p&0x80800000u))return midi_enqueue(p,1);
    if(cin==15 && (st==0xf8 || st==0xfa || st==0xfb || st==0xfc || st==0xfe || st==0xff))return midi_enqueue(p,1);
    return 0;
}
static uint32_t ul_midi_peek(uint8_t *out,uint32_t limit)
{
    uint32_t i,n=mo_w-mo_r,p;
    if(n>limit/4u)n=limit/4u;
    for(i=0;i<n;i++) {p=midi_out_q[(mo_r+i)%MQ];out[4*i]=(uint8_t)p;out[4*i+1]=(uint8_t)(p>>8);out[4*i+2]=(uint8_t)(p>>16);out[4*i+3]=(uint8_t)(p>>24);}
    return n*4u;
}
static void ul_midi_commit(uint32_t n){mo_r+=n;}
#include "usb_link.h"
static void usb_link_poll(void)
{
    if(!link_host)return;
    ul_poll(fm1_ms);
    if(link_io_error && ul.state!=UL_FAILED){ul.io_failures++;ul_fail(UL_IO,fm1_ms);}
}
static void usb_link_apply(void)
{
    uint32_t role=panel_state.usb_role,f;
    if(!panel_state.usb_apply)return;
    panel_state.usb_apply=0;
    /* Never seize a live PC bus. Explicit retry after unplugging is required. */
    if(role==1u && !link_host && usb.config && !usb.suspended){ul.error=12;return;}
    if(storage_busy || updating || native_import_ready){ul.error=13;return;}
    if(!link_saved && role) {link_saved_midi=panel_state.midi;link_saved_channel=controls.value[FMER_MIDI_CHANNEL];link_saved=1;}
    f=irq_save();
    if(role==1u) {
        link_host=1;usb.up=0;usb.detached=1;uac.alt=uac.go=uac.flowing=0;
        link_io_error=0;ul_start(fm1_ms);
    } else if(link_host) {ul_disconnect();ul_off();ul.state=UL_OFF;link_host=0;usb.up=0;usb.detached=0;}
    link_role=role;
    irq_restore(f);
    if(!role && link_saved) {
        panel_state.midi=link_saved_midi;controls.value[FMER_MIDI_CHANNEL]=(uint16_t)link_saved_channel;link_saved=0;
    } else if(role) {
        panel_state.midi.value[FMER_MIDI_LOCAL]=1;
        panel_state.midi.value[FMER_MIDI_CHANNEL_MODE]=0; /* track channels 1..4 */
        panel_state.midi.value[FMER_MIDI_CLOCK_SOURCE]=role==1u?0u:1u;
        panel_state.midi.value[FMER_MIDI_CLOCK_SEND]=role==1u && panel_state.usb_send!=1u;
        panel_state.midi.value[FMER_MIDI_TRANSPORT_RX]=role==2u;
        panel_state.midi.value[FMER_MIDI_ROUTE]=role==1u && panel_state.usb_send?3u:0u;
        controls.value[FMER_MIDI_CHANNEL]=0; /* ALL; per-track allocator still isolates channels */
    }
    panel_state.midi_revision++;
    control_dirty[FMER_MIDI_CHANNEL/32]|=1u<<(FMER_MIDI_CHANNEL%32);controls_generation++;
    trace_event(FMER_TRACE_BUTTON,0x731u,(int32_t)role,panel_state.usb_send);
}
