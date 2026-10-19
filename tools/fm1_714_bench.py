#!/usr/bin/env python3
"""Bounded FMER714 RAM feature bench; exact identity, no onboard slot writes.

Root bench operator only: close the recorder and leave physical keys released.
A complete durable pre-test snapshot is required before musical commands. The
finally path attempts all releases and restores all198 controls/eight patterns.
Diagnostics/trace establish state and timing, not analog audio or visual quality.
Onboard save/load qualification is deliberately a separate explicit bridge run.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import uuid
import fm1_bench as legacy
import fm1_704_bench as feature
import fm1_flash_transport as transport
import fm1_native_bridge_v8 as bridge
import fm1_native_state_v3 as native
import fm1_session as telemetry
import hardware_bridge as hardware

NAMES = ('FM KEYS','FM BELL','FM BASS','FM BRASS','FM ORGAN','FM PLUCK','FM REED','FM MOTION',
         'VA ROUND','VA SAW','VA PULSE','VA TRI','VA BASS','VA PLUCK','VA SOFT','VA VIBRA',
         'FM TINE','FM REEDKEY','FM CLAV','FM TOYKEY','FM VIBES','FM MARIMBA','FM CHIME','FM GLOCK',
         'FM FINGER','FM PICKBS','FM SUBBASS','FM SLAP','FM TRUMPET','FM HORN','FM TROMB','FM FLUTE',
         'FM CLARIN','FM STRINGS','FM BOWED','FM CHOIR','FM WARMPAD','FM GLASS','FM LEAD','FM PERC',
         'VA SUB','VA ACID','VA ROUND B','VA PULSE B','VA SNAP B','VA DEEP B','VA LEAD','VA HOLLOW',
         'VA REED','VA FLUTE','VA BRIGHT','VA SING','VA WARM','VA STRINGS','VA SWELL','VA SHIMMER',
         'VA SHORT','VA MALLET','VA ORGAN','VA BRASS','VA SOFTKEY','VA CLAV','VA ARP','VA LONG')


def short_message(session, journal, status, data1, data2=0):
    if getattr(session,'verified_identity',None)!=bridge.IDENTITY:
        raise ValueError('Exact714 identity is required before musical bench messages')
    if any(type(n) is not int for n in (status,data1,data2)):
        raise ValueError('Integer MIDI bytes required')
    allowed=(status in (0xc0,0xcf) and 0<=data1<64 and data2==0 or
             status in (0x90,0x9f) and data1 in feature.NOTES and data2==32 or
             status in (0x80,0x8f) and data1 in feature.NOTES and data2==0 or
             status in (0xb0,0xbf) and data1 in (64,120,123) and data2==0 or
             status in (0xb0,0xbf) and data1 in (71,72,73,74) and data2 in (0,64,127))
    if not allowed:raise ValueError('Outside bounded714 MIDI allowlist')
    cleanup=status&0xf0==0x80 or status&0xf0==0xb0 and data1 in (64,120,123)
    logging_error=None
    try:journal.record('714_short_message_intent',status=status,data1=data1,data2=data2)
    except Exception as error:
        if not cleanup:raise
        logging_error=error
    function=session.api.dll.midiOutShortMsg
    function.argtypes,function.restype=[hardware.HANDLE,hardware.DWORD],hardware.UINT
    session.api.checked('midiOutShortMsg',session.output,status|data1<<8|data2<<16)
    if logging_error:raise RuntimeError('Cleanup sent but logging failed') from logging_error


def wait_for(call,predicate,label):
    last=None
    for _ in range(100):
        last=call()
        if predicate(last):return last
        time.sleep(.01)
    raise RuntimeError(label+': '+repr(last))


def musical(raw):
    value=native.decode(raw);value.pop('source_generation');return value


def program_engine(program):
    if type(program) is not int or not 0<=program<64:raise ValueError('Invalid factory program')
    return 0 if program<8 or 16<=program<40 else 1


def expected_arp(order,steps):
    if type(order) is not int or not 0<=order<10 or not 0<=steps<=128:raise ValueError('Invalid bounded arp oracle')
    cycles={0:(60,64,67),1:(67,64,60),2:(60,64,67,64),3:(67,60,64),
            4:(60,64,67,67,64,60),7:(67,64,60,64),8:(67,64,60,60,64,67),9:(60,67,64)}
    result=[];random=1
    for index in range(steps):
        if order==6:result.append([60,64,67])
        elif order==5:
            random=(random^(random<<13))&0xffffffff;random^=random>>17;random=(random^(random<<5))&0xffffffff
            result.append([(60,64,67)[random%3]])
        else:result.append([cycles[order][index%len(cycles[order])]])
    return result


def generated_groups(events,source):
    groups=[]
    for event in events:
        if event.get('kind')!=10 or event.get('source')!=source or not event['value']:continue
        frame=event['audio_frame_low32']
        if not groups or groups[-1]['frame']!=frame:groups.append(dict(frame=frame,notes=[]))
        groups[-1]['notes'].append(event['pitch'])
    return groups


def verify_groups(groups,expected,label,*,minimum=6):
    if not minimum<=len(groups)<=128:raise RuntimeError(label+' insufficient/excess generated steps')
    if len(expected)<len(groups):raise RuntimeError(label+' oracle shorter than trace')
    origin=groups[0]['frame']
    for index,group in enumerate(groups):
        #120BPM straight sixteenths: alternating5512/5513 frames, no host-time approximation.
        if group['notes']!=expected[index] or ((group['frame']-origin)&0xffffffff)!=index*44100//8:
            raise RuntimeError(label+' generated pitch/frame differs at step'+str(index)+': '+repr(group))
    return dict(steps=len(groups),first_frame=origin,notes=[g['notes'] for g in groups],sample_grid='44100/8 rational frames')


def pattern_probe(raw,*,chain_mask=3):
    state=native.decode(raw)
    state['preset_id']=native.CUSTOM_PRESET;state['vced'][145:]=list(b'BENCH714  ')
    for bank,pattern in enumerate(state['patterns']):
        pattern['length']=4 if bank==0 else 2 if bank==1 else bank+1
        for step in range(64):pattern['steps'][step]=[128,32,75]
        pattern['steps'][63]=[min(127,90+bank),70+bank,80+bank]
    for i,pitch in enumerate((60,64,60,64)):state['patterns'][0]['steps'][i]=[pitch,32,75]
    state['patterns'][1]['steps'][0]=[67,32,75];state['patterns'][1]['steps'][1]=[71,32,75]
    controls=state['controls']
    for identifier,value in ((160,1),(161,0),(162,20000),(163,0),(164,0),(165,0),(166,100),(167,0),
                             (168,0),(169,0),(170,0),(173,0),(174,0),(177,18000),(178,120),(179,0),
                             (180,0),(181,16),(182,1),(183,75),(184,0),(185,50),(191,4),(192,0),(193,0),
                             (195,0),(196,1),(197,chain_mask)):
        controls[identifier]=value
    controls[186]=4;controls[187]=0;controls[188:191]=state['patterns'][0]['steps'][0][:]
    return native.encode(state)


def run_presets(bench,nb,result,before):
    cases=result['cases']
    for identifier,value in ((193,0),(179,0),(191,4),(168,0),(169,0),(170,0),(173,0),(174,0),(162,20000)):
        bench.set(identifier,value)
    for program in range(64):
        short_message(bench.session,bench.journal,0xcf,program)
        wait_for(nb.status,lambda status:status['preset_id']==program and not status['sound_dirty'],'factory program adoption')
        raw,_=nb.snapshot();state=native.decode(raw)
        name=bytes(state['vced'][145:]).decode('ascii').rstrip()
        if state['preset_id']!=program or name!=NAMES[program] or state['controls'][160]!=program_engine(program):
            raise RuntimeError('Factory program/name/engine mismatch: '+str(program))
        legacy.reset_peaks(bench.session)
        for note in feature.NOTES:short_message(bench.session,bench.journal,0x9f,note,32)
        time.sleep(.045)
        diag=bench.check(before)
        # maximum_render_voices describes the voices during the slowest half,
        # not the largest chord. An attack/setup half can cost more than the
        # subsequent four-voice sustain. Check the actual held chord instead.
        if diag['active_voices']!=4:
            raise RuntimeError('Factory chord did not admit all four notes: '+str(program))
        for note in feature.NOTES:short_message(bench.session,bench.journal,0x8f,note)
        bench.transport(5)
        if legacy.query(bench.session,bench.journal,2)['active_voices']:
            raise RuntimeError('Factory cleanup left a sounding owner')
        cases.append(dict(case='factory quiet chord',program=program,name=name,engine=state['controls'][160],
                          diagnostics=diag,audio_recorded=False))


def run_arps(bench,nb,result,before,directory):
    record=pattern_probe(nb.snapshot()[0]);nb.restore(record,directory)
    bench.set(196,0)
    for order in range(10):
        bench.transport(5);bench.set(180,order)
        for note in (67,60,64):short_message(bench.session,bench.journal,0x9f,note,32)
        bench.trace();start=len(bench.events)
        bench.set(179,1)
        time.sleep(1.02)
        bench.check(before)
        groups=generated_groups(bench.events[start:],5)
        verified=verify_groups(groups,expected_arp(order,len(groups)),'arp'+str(order),minimum=8)
        for note in (67,60,64):short_message(bench.session,bench.journal,0x8f,note)
        bench.transport(5);bench.set(179,0);bench.trace()
        result['cases'].append(dict(case='arpeggiator exact order and grid',order=order,**verified))


def run_patterns(bench,nb,result,before,directory):
    record=pattern_probe(nb.snapshot()[0],chain_mask=1)
    restored=nb.restore(record,directory)
    if musical(nb.snapshot()[0])!=musical(record):raise RuntimeError('Complete eight-bank native roundtrip differs')
    result['cases'].append(dict(case='eight-bank512-step native roundtrip',**restored))
    bench.trace();start=len(bench.events)
    bench.transport(1);bench.set(195,1)
    perf=bench.performance()
    if perf['selected_pattern']!=1 or perf['playing_pattern']!=0 or perf['queued_pattern']!=1:
        raise RuntimeError('Pattern edit/play/queue state was not distinct before boundary')
    time.sleep(1.42);bench.check(before)
    groups=generated_groups(bench.events[start:],4)
    expected=[[60],[64],[60],[64],[67],[71]]+[[60],[64],[60],[64]]*32
    verified=verify_groups(groups,expected,'queued pattern override',minimum=10)
    if bench.performance()['selected_pattern']!=1:raise RuntimeError('Playing chain moved editor selection')
    bench.transport(3);bench.trace()
    result['cases'].append(dict(case='queued pattern takes one boundary then loop resumes',**verified))
    bench.set(195,0);bench.set(197,3)
    bench.trace();start=len(bench.events)
    bench.transport(1);time.sleep(1.42);bench.check(before)
    groups=generated_groups(bench.events[start:],4)
    verified=verify_groups(groups,[[60],[64],[60],[64],[67],[71]]*22,'ascending linked patterns',minimum=10)
    bench.transport(3);bench.trace()
    result['cases'].append(dict(case='two-pattern chain preserves lengths and exact clock',**verified))


def run_native_refusals(bench,nb,result):
    raw,status=nb.snapshot();tx=0x71401
    def response(packet,op):
        return native.parse_result(nb.request(packet,'714_native_refusal_test'),opcode=op,transaction=tx)['result']
    nb.abort_staging()
    if response(native.begin_request(tx,status['live_generation']),16) or response(native.commit_request(tx),18)!=13:
        raise RuntimeError('Incomplete valid native transaction was not refused')
    nb.abort_staging(tx)
    bench.set(162,19998);edited=nb.snapshot()[0]
    if response(native.begin_request(tx,status['live_generation']),16):raise RuntimeError('Stale test begin refused unexpectedly')
    for offset in range(0,native.SIZE,64):
        if response(native.write_chunk_request(tx,offset,raw[offset:offset+64]),17):raise RuntimeError('Stale test chunk failed')
    if response(native.commit_request(tx),18)!=14:raise RuntimeError('Stale complete transaction not refused')
    nb.abort_staging(tx)
    if musical(nb.snapshot()[0])!=musical(edited):raise RuntimeError('Refused native transaction changed live data')
    result['cases'].append(dict(case='incomplete and stale native imports preserve complete state'))


def run_panel(bench,nb,result,before):
    bench.transport(5);bench.set(179,0);bench.button(8)
    for fine,wanted in ((False,6357),(True,6044)):
        bench.set(162,6000);bench.button(8)
        if fine:bench.panel(2,3,1)
        try:bench.panel(1,2,1)
        finally:
            if fine:bench.panel(2,3,0)
        wait_for(lambda:bench.controls()[162],lambda value:value==wanted,'logarithmic cutoff detent')
        diag=bench.check(before)
        if diag['cutoff_hz']!=wanted:raise RuntimeError('Display/canonical cutoff and actual effect readback disagree')
        result['cases'].append(dict(case='virtual logarithmic cutoff coarse/fine',fine=fine,initial=6000,value=wanted))
    bench.button(10)
    page=bench.performance()['page_index']
    if page:bench.panel(1,0,-page)
    bench.set(180,0);bench.panel(1,2,1)
    wait_for(lambda:bench.controls()[180],lambda value:value==1,'ARP order knob on first page')
    bench.panel(1,0,1);bench.set(181,8);bench.set(178,120)
    bench.panel(1,2,1);bench.panel(1,3,1)
    controls=bench.controls()
    if controls[181]!=16 or controls[178]!=121 or bench.performance()['page_index']!=1:
        raise RuntimeError('ARP timing page knob positions differ from canonical control mapping')
    bench.panel(1,0,1)
    if bench.performance()['page_index']!=0:raise RuntimeError('ARP page traversal did not wrap through exactly two pages')
    bench.check(before)
    result['cases'].append(dict(case='two ARP pages with one stable location per control'))
    bench.button(8)


def run_live_edits(bench,nb,result,before,directory):
    state=native.decode(pattern_probe(nb.snapshot()[0],chain_mask=1))
    state['patterns'][0]['length']=8;state['controls'][186]=8
    for step in range(8):state['patterns'][0]['steps'][step]=[60+step,32,75]
    state['controls'][188:191]=state['patterns'][0]['steps'][0]
    nb.restore(native.encode(state),directory);bench.trace();start=len(bench.events)
    bench.transport(1);time.sleep(.29);bench.trace()
    prior=bench.performance();bench.set(189,31);edited=bench.performance()
    if edited['seq_position']<prior['seq_position']:raise RuntimeError('Step edit restarted playback')
    time.sleep(.3);bench.check(before)
    groups=generated_groups(bench.events[start:],4)
    verify_groups(groups,[[60+i%8] for i in range(128)],'live step edit retains clock',minimum=4)
    prior=bench.performance();bench.set(178,150);edited=bench.performance()
    if edited['seq_position']<prior['seq_position']:raise RuntimeError('Tempo edit restarted playback')
    time.sleep(.38);bench.check(before);bench.transport(5)
    groups=generated_groups(bench.events[start:],4)
    if len(groups)<8 or any(g['notes']!=[60+i%8] for i,g in enumerate(groups)):raise RuntimeError('Live edit lost sequence note position')
    result['cases'].append(dict(case='live velocity and tempo changes retain sequence step',generated=groups))

def run_essentials(bench,nb,result,directory):
    result['cases']=[];before=result['before']=legacy.query(bench.session,bench.journal,2)
    bench.performance_baseline=bench.performance()
    if any(before[key] for key in feature.FAILURES) or bench.performance_baseline['performance_errors']:
        raise RuntimeError('714 bench requires fault-free initial DSP counters')
    run_presets(bench,nb,result,before)
    run_arps(bench,nb,result,before,directory)
    run_patterns(bench,nb,result,before,directory)
    run_live_edits(bench,nb,result,before,directory)
    run_native_refusals(bench,nb,result)
    run_panel(bench,nb,result,before)
    result['after']=bench.check(before)
    result['maximum_render_us']=bench.peak_render
    if bench.peak_render>=2032:raise RuntimeError('714 essential cases exceeded70percent nominal audio-half budget')


def cleanup_and_restore(session,bench,nb,original,directory,result):
    errors=[]
    for status in (0x80,0x8f):
        for note in feature.NOTES:
            try:short_message(session,bench.journal,status,note)
            except Exception as error:errors.append(dict(action='note release',status=status,note=note,error=repr(error)))
    try:bench.cleanup()
    except Exception as error:errors.append(dict(action='panic and pedal cleanup',error=repr(error)))
    try:result['final_restore']=nb.restore(original,directory)
    except Exception as error:result.update(success=False,restoration_error=repr(error))
    try:bench.button(8)
    except Exception as error:errors.append(dict(action='return HOME',error=repr(error)))
    if errors:result.update(success=False,final_cleanup_errors=errors)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('essentials','matrix','releases'),default='essentials')
    args=parser.parse_args(argv)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')+'-'+uuid.uuid4().hex[:8]
    journal=transport.Journal(transport.ROOT/'artifacts/fm1-714-bench'/stamp);directory=journal.directory/'backups'
    result=dict(success=False,identity=bridge.IDENTITY,mode=args.mode,flash_writes=False,audio_recorded=False,
                tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    session=bench=nb=None;original=None
    try:
        session=transport.find_session(hardware.WinMM(),bridge.IDENTITY,journal,wait=2)
        bench=feature.Bench(session,journal,identity=bridge.IDENTITY);nb=bridge.NativeBridge(session,journal)
        perf=bench.performance();led=telemetry.led_state(session,journal,identity=bridge.IDENTITY)
        if perf['seq_running'] or perf['seq_recording'] or perf['arp_held'] or led['physical_keys'] or led['held_buttons'] or led['active_voices']:
            raise RuntimeError('Bench requires released keys and stopped transport')
        store=nb.store_status()
        if not store['ready'] or store['busy']:raise RuntimeError('Bench requires settled714 storage status')
        pending=nb.status()
        if pending['save_token'] and pending['save_token']!=pending['save_acked_token']:
            raw=nb.read_token(pending['save_token'])
            result['prior_save_mirror']=native.save_backup(raw,directory,device_identity=bridge.IDENTITY,source='pending onboard SAVE mirror before714bench')
            nb.acknowledge_save(pending['save_token'],raw)
        captured,_=nb.snapshot()
        result['pre_test_backup']=native.save_backup(captured,directory,device_identity=bridge.IDENTITY,source='complete pre714bench backup')
        bench.trace(initial=True)
        original=captured
        if args.mode=='essentials':run_essentials(bench,nb,result,directory)
        else:
            bench.set(193,0);bench.set(179,0)
            (legacy.run_matrix if args.mode=='matrix' else legacy.run_releases)(session,journal,result)
        result['success']=True
    except Exception as error:result.update(success=False,error=repr(error))
    finally:
        if original is not None:cleanup_and_restore(session,bench,nb,original,directory,result)
        if session is not None:
            try:
                failures=session.close()
                if failures:result.update(success=False,close_errors=failures)
            except Exception as error:result.update(success=False,close_errors=[repr(error)])
        try:journal.record('714_bench_finished',**result)
        except Exception as error:result.update(success=False,final_logging_error=repr(error))
        try:journal.close()
        except Exception as error:result.update(success=False,journal_close_error=repr(error))
        try:native._write_new(journal.directory/'report.json',(json.dumps(result,indent=2)+'\n').encode())
        except Exception as error:result.update(success=False,report_write_error=repr(error))
    print(json.dumps(dict(success=result['success'],error=result.get('error'),restoration_error=result.get('restoration_error'),
                         close_errors=result.get('close_errors'),final_logging_error=result.get('final_logging_error'),
                         report_write_error=result.get('report_write_error'),artifacts=str(journal.directory))))
    return 0 if result['success'] else 1


if __name__=='__main__':raise SystemExit(main())
