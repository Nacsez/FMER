/* SPDX-License-Identifier: GPL-3.0-only
 * Original bounded USB 1.1 MIDI host for a single, self-powered FMER peer.
 * Register facts: pinned AC79 SDK, see docs/USB_DIRECT_LINK.md. No SDK runtime.
 * One timer owner; no allocation, sleep, flash, printf or unbounded USB wait.
 * Platform supplies ul_read/write, ul_attach/off, DMA and MIDI ring callbacks.
 */
#ifndef FMER_USB_LINK_H
#define FMER_USB_LINK_H
#include <stdint.h>
#include <string.h>
#ifdef _MSC_VER
#define UL_ALIGN __declspec(align(4))
#else
#define UL_ALIGN __attribute__((aligned(4)))
#endif
enum {UL_OFF,UL_ATTACH,UL_WAIT,UL_RESET,UL_SETTLE,UL_CONTROL,UL_READY,UL_FAILED};
enum {UL_OK,UL_IO,UL_NO_HOST,UL_LOW_SPEED,UL_CONTROL_TIMEOUT,UL_STALL,
      UL_BAD_DEVICE,UL_BAD_CONFIG,UL_DISCONNECTED,UL_BULK_ERROR,UL_TX_TIMEOUT};
typedef struct {
    uint32_t state,error,started,phase,stage,expected,received,ep0_size,total;
    uint32_t tx_pending,tx_started,rx_events,tx_events,connects,disconnects,failures;
    uint32_t devctl,csr,io_failures,ignored,rx_packets,tx_packets;
    uint8_t config,ep_in,ep_out,max_in,max_out;
    uint8_t descriptor[512];
    UL_ALIGN uint8_t control[68];
    UL_ALIGN uint8_t rx[68];
    UL_ALIGN uint8_t tx[64];
} fmer_usb_link_t;
static fmer_usb_link_t ul;
static void ul_fail(uint32_t error,uint32_t now)
{
    ul_off();ul.state=UL_FAILED;ul.error=error;ul.started=now;
    ul.failures++;ul.tx_pending=0;ul_disconnect();
}
/* Reject malformed descriptors, unsupported alternates and ambiguous MIDI
 * interfaces. Never select the audio streaming endpoint or a hub. */
static int ul_configuration(fmer_usb_link_t *s,const uint8_t *p,uint32_t n)
{
    uint32_t at=0,midi=0,interfaces=0,in=0,out=0,mi=0,mo=0;
    if(n<9 || p[0]!=9 || p[1]!=2 || (uint32_t)(p[2]|p[3]<<8)!=n || !p[5])return 0;
    while(at<n) {
        uint32_t len=p[at],type=at+1<n?p[at+1]:0;
        if(len<2 || len>n-at)return 0;
        if(type==4) {
            if(len<9)return 0;
            midi=p[at+5]==1 && p[at+6]==3 && p[at+7]==0 && p[at+3]==0;
            if(midi && ++interfaces>1)return 0;
        } else if(type==5 && midi) {
            uint32_t ep,size;
            if(len<7)return 0;
            ep=p[at+2];size=p[at+4]|p[at+5]<<8;
            if((p[at+3]&3)!=2 || !(ep&15) || (ep&0x70) || size<4 || size>64 || size%4)return 0;
            if(ep&0x80){if(in)return 0;in=ep&15;mi=size;}
            else {if(out)return 0;out=ep;mo=size;}
        }
        at+=len;
    }
    if(interfaces!=1 || !in || !out)return 0;
    s->config=p[5];s->ep_in=(uint8_t)in;s->ep_out=(uint8_t)out;
    s->max_in=(uint8_t)mi;s->max_out=(uint8_t)mo;return 1;
}
static void ul_setup(uint8_t type,uint8_t request,uint16_t value,uint16_t length,uint32_t now)
{
    ul.control[0]=type;ul.control[1]=request;ul.control[2]=(uint8_t)value;ul.control[3]=(uint8_t)(value>>8);
    ul.control[4]=ul.control[5]=0;ul.control[6]=(uint8_t)length;ul.control[7]=(uint8_t)(length>>8);
    ul.expected=length;ul.received=0;ul.stage=0;ul.started=now;ul.state=UL_CONTROL;
    ul_write(14,0);ul_dma_control(ul.control,8);ul_write(17,0x0a); /* SETUP | TX ready */
}
static void ul_request(uint32_t phase,uint32_t now)
{
    ul.phase=phase;
    switch(phase) {
    case 0:ul_setup(0x80,6,0x100,8,now);break;
    case 1:ul_setup(0,5,1,0,now);break;
    case 2:ul_setup(0x80,6,0x100,18,now);break;
    case 3:ul_setup(0x80,6,0x200,9,now);break;
    case 4:ul_setup(0x80,6,0x200,(uint16_t)ul.total,now);break;
    case 5:ul_setup(0,9,ul.config,0,now);break;
    }
}
static void ul_control_complete(uint32_t now)
{
    uint8_t *p=ul.descriptor;
    switch(ul.phase) {
    case 0:
        if(ul.received!=8 || p[0]!=18 || p[1]!=1 || (p[7]!=8 && p[7]!=16 && p[7]!=32 && p[7]!=64)) {ul_fail(UL_BAD_DEVICE,now);return;}
        ul.ep0_size=p[7];ul_request(1,now);return;
    case 1:ul_write(0,1);ul.state=UL_SETTLE;ul.started=now;return; /* address recovery >=2ms */
    case 2:
        /* Narrow bench host: the FMER pid.codes test identity, one configuration.
         * No firmware update, vendor or SysEx traffic is accepted over this link. */
        if(ul.received!=18 || p[0]!=18 || p[1]!=1 || p[8]!=9 || p[9]!=0x12 || p[10]!=1 || p[11]!=0 || p[17]!=1) {ul_fail(UL_BAD_DEVICE,now);return;}
        ul_request(3,now);return;
    case 3:
        ul.total=p[2]|p[3]<<8;
        if(ul.received!=9 || p[0]!=9 || p[1]!=2 || ul.total<9 || ul.total>sizeof ul.descriptor) {ul_fail(UL_BAD_CONFIG,now);return;}
        ul_request(4,now);return;
    case 4:
        if(!ul_configuration(&ul,p,ul.received)) {ul_fail(UL_BAD_CONFIG,now);return;}
        ul_request(5,now);return;
    case 5:
        ul_dma_bulk(ul.rx,ul.tx);
        ul_write(14,1);ul_write(16,0xff);ul_write(17,0x48);ul_write(18,0);
        ul_write(19,0xff);ul_write(20,0x90);ul_write(21,0);
        ul_write(24,0x20|ul.ep_out);ul_write(25,8);
        ul_write(26,0x20|ul.ep_in);ul_write(27,8);ul_write(20,0x20);
        ul.state=UL_READY;ul.error=0;ul.connects++;ul.started=now;ul_connected();return;
    }
}
static void ul_control_poll(uint32_t now)
{
    uint32_t csr,n;
    if(now-ul.started>1000u){ul_fail(UL_CONTROL_TIMEOUT,now);return;}
    ul_write(14,0);csr=ul_read(17);ul.csr=csr;
    if(csr&0x94u){ul_fail(UL_STALL,now);return;}
    if(ul.stage==0) {
        if(csr&2u)return;
        ul_dma_control(ul.control,0);
        if(ul.expected){ul.stage=1;ul_write(17,0x20);}
        else {ul.stage=3;ul_write(17,0x60);} /* IN status */
    } else if(ul.stage==1 && (csr&1u)) {
        n=ul_read(22);ul_rx_sync();
        if(n>ul.ep0_size || n>ul.expected-ul.received || ul.received+n>sizeof ul.descriptor) {ul_fail(UL_BAD_CONFIG,now);return;}
        memcpy(ul.descriptor+ul.received,ul.control,n);ul.received+=n;
        ul_write(17,0);
        if(n<ul.ep0_size || ul.received==ul.expected) {
            ul.stage=2;ul_dma_control(ul.control,0);ul_write(17,0x42); /* OUT status */
        } else ul_write(17,0x20);
    } else if(ul.stage==2 && !(csr&2u)) {ul_write(17,0);ul_control_complete(now);}
    else if(ul.stage==3 && (csr&1u)) {
        if(ul_read(22)!=0){ul_fail(UL_BAD_CONFIG,now);return;}
        ul_write(17,0);ul_control_complete(now);
    }
}
static void ul_bulk_poll(uint32_t now)
{
    uint32_t csr,n,i,pkt;
    ul_write(14,1);csr=ul_read(20);ul.csr=csr;
    if(csr&0x44u){ul_fail(UL_BULK_ERROR,now);return;}
    if(csr&1u) {
        n=ul_read(22)|(ul_read(23)<<8);
        if(n>ul.max_in || n%4u){ul_fail(UL_BULK_ERROR,now);return;}
        ul_rx_sync();
        for(i=0;i<n;i+=4) {
            pkt=(uint32_t)ul.rx[i]|((uint32_t)ul.rx[i+1]<<8)|((uint32_t)ul.rx[i+2]<<16)|((uint32_t)ul.rx[i+3]<<24);
            /* Short messages only. Never execute a peer's updater SysEx. */
            if(ul_midi_receive(pkt))ul.rx_events++;else ul.ignored++;
        }
        ul.rx_packets++;ul_write(20,0x10);ul_write(20,0x20);
    } else if(csr&8u) {ul_write(20,0);ul_write(20,0x20);} /* NAK: normal idle, preserve toggle */
    csr=ul_read(17);
    if(csr&0x24u){ul_fail(UL_BULK_ERROR,now);return;}
    if(ul.tx_pending) {
        if(now-ul.tx_started>1000u){ul_fail(UL_TX_TIMEOUT,now);return;}
        if(csr&0x80u){ul_write(17,1);return;} /* NAK retry; do not duplicate/dequeue */
        if(csr&1u){if(now-ul.tx_started>1000u)ul_fail(UL_TX_TIMEOUT,now);return;}
        ul_midi_commit(ul.tx_pending);ul.tx_events+=ul.tx_pending;ul.tx_packets++;ul.tx_pending=0;
    }
    n=ul_midi_peek(ul.tx,ul.max_out);
    if(n) {ul.tx_pending=n/4;ul.tx_started=now;ul_dma_send(ul.tx,n);ul_write(17,1);}
}
static void ul_start(uint32_t now)
{
    ul_disconnect();ul_off();ul.state=UL_ATTACH;ul.error=0;ul.started=now;ul.tx_pending=0;
}
static void ul_poll(uint32_t now)
{
    uint32_t dev;
    if(ul.state==UL_OFF || ul.state==UL_FAILED)return;
    if(ul.state==UL_ATTACH) {
        if(now-ul.started<25u)return;
        ul_attach(ul.control);ul_write(0,0);ul_write(1,0);ul_write(7,0);ul_write(8,0);
        ul_write(9,0);ul_write(10,0);ul_write(11,0);ul_write(15,3);
        ul.state=UL_WAIT;ul.started=now;return;
    }
    dev=ul_read(15);ul.devctl=dev;
    if(ul.state==UL_WAIT) {
        if(now-ul.started>30000u){ul_fail((dev&4)?UL_DISCONNECTED:UL_NO_HOST,now);return;}
        if(!(dev&4))return;
        if(dev&0x20){ul_fail(UL_LOW_SPEED,now);return;}
        if(!(dev&0x40))return;
        ul_write(1,8);ul.state=UL_RESET;ul.started=now;return;
    }
    if(ul.state==UL_RESET) {
        if(now-ul.started<50u)return;
        ul_write(1,0);ul.state=UL_SETTLE;ul.phase=0xffffffffu;ul.started=now;return;
    }
    if(!(dev&4u) || !(dev&0x40u)) {ul.disconnects++;ul_fail(UL_DISCONNECTED,now);return;}
    if(ul.state==UL_SETTLE) {
        if(now-ul.started<10u)return;
        ul.ep0_size=ul.phase==0xffffffffu?8u:ul.ep0_size;
        ul_request(ul.phase==0xffffffffu?0u:2u,now);return;
    }
    if(ul.state==UL_CONTROL)ul_control_poll(now);
    else if(ul.state==UL_READY)ul_bulk_poll(now);
}
#endif
