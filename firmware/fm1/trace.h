/* SPDX-License-Identifier: GPL-3.0-only
 * Fixed recent-event history. No I/O, allocation or string formatting in IRQs.
 * Snapshot reads are non-consuming, so reconnects can detect and report gaps.
 */
#ifndef FMER_TRACE_H
#define FMER_TRACE_H
#include <stdint.h>
#ifndef FMER_TRACE_LOCK
#define FMER_TRACE_LOCK() 0u
#define FMER_TRACE_UNLOCK(f) ((void)(f))
#endif
enum { FMER_TRACE_CAPACITY=256, FMER_TRACE_BATCH=6 };
enum { FMER_TRACE_ENCODER=1, FMER_TRACE_BUTTON, FMER_TRACE_CONTROL,
 FMER_TRACE_NOTE, FMER_TRACE_TRANSPORT, FMER_TRACE_FAULT, FMER_TRACE_PAGE,
 FMER_TRACE_BOOT, FMER_TRACE_APPLIED, FMER_TRACE_GENERATED, FMER_TRACE_STORAGE,
 FMER_TRACE_NATIVE_LOAD };
typedef struct {
 uint32_t sequence, ms;
 uint16_t kind,id;
 int32_t value;
 uint32_t aux;
} fmer_trace_event_t;
typedef struct {
 fmer_trace_event_t events[FMER_TRACE_CAPACITY];
 uint32_t newest,count;
} fmer_trace_t;
/* Caller already owns the critical section, or interrupts have not yet been
 * enabled during startup. Never invoke a lock/unlock pair inside this path. */
static void fmer_trace_push_locked(fmer_trace_t *t,uint32_t ms,uint32_t kind,
                                  uint32_t id,int32_t value,uint32_t aux) {
 uint32_t seq=t->newest+1u;
 fmer_trace_event_t *e;
 if(!seq) { seq=1; t->count=0; } /* explicit sequence restart after wrap */
 e=&t->events[(seq-1u)%FMER_TRACE_CAPACITY];
 e->sequence=seq; e->ms=ms; e->kind=(uint16_t)kind; e->id=(uint16_t)id;
 e->value=value; e->aux=aux;
 if(t->count<FMER_TRACE_CAPACITY) t->count++;
 t->newest=seq;
}
static void fmer_trace_push(fmer_trace_t *t,uint32_t ms,uint32_t kind,
                           uint32_t id,int32_t value,uint32_t aux) {
 uint32_t f=FMER_TRACE_LOCK();
 fmer_trace_push_locked(t,ms,kind,id,value,aux);
 FMER_TRACE_UNLOCK(f);
}
static uint32_t fmer_trace_snapshot(const fmer_trace_t *t,uint32_t cursor,
 fmer_trace_event_t *events,uint32_t *newest,uint32_t *oldest) {
 uint32_t f=FMER_TRACE_LOCK(),first,n=0,seq;
 *newest=t->newest; *oldest=t->count?t->newest-t->count+1u:1u;
 if(cursor>t->newest) first=*oldest;
 else first=cursor+1u;
 if(first<*oldest) first=*oldest;
 for(seq=first;seq && seq<=*newest && n<FMER_TRACE_BATCH;seq++)
   events[n++]=t->events[(seq-1u)%FMER_TRACE_CAPACITY];
 FMER_TRACE_UNLOCK(f); return n;
}
#endif
