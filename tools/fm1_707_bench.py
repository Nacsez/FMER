#!/usr/bin/env python3
"""Bounded FMER707 preset/MIDI/native-state bench; exact identity, RAM only.

Quiet notes and complete pre-test/pre-restore PC backups are mandatory. This
does not establish analog sound quality or physical control/LED appearance.
Close the recorder while the bench owns MIDI. Importing performs no I/O.
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
import fm1_native_bridge as bridge
import fm1_native_state as native
import fm1_session as telemetry
import hardware_bridge as hardware

NAMES = ('FM KEYS','FM BELL','FM BASS','FM BRASS','FM ORGAN','FM PLUCK','FM REED','FM MOTION',
         'VA ROUND','VA SAW','VA PULSE','VA TRI','VA BASS','VA PLUCK','VA SOFT','VA VIBRA')


def short_message(session, journal, status, data1, data2=0):
    if getattr(session, 'verified_identity', None) != bridge.IDENTITY:
        raise ValueError('Exact707 identity is required before musical bench messages')
    if any(type(n) is not int for n in (status, data1, data2)):
        raise ValueError('Integer MIDI bytes required')
    kind = status & 0xf0
    allowed = (status in (0xc0, 0xcf) and 0 <= data1 < 16 and data2 == 0 or
               status in (0x90, 0x9f) and data1 in feature.NOTES and data2 == 32 or
               status in (0x80, 0x8f) and data1 in feature.NOTES and data2 == 0 or
               status in (0xb0, 0xbf) and data1 == 120 and data2 == 0 or
               status in (0xb0, 0xbf) and data1 in (71,72,73,74) and data2 in (0,64,127))
    if not allowed:
        raise ValueError('Outside bounded707 MIDI test allowlist')
    cleanup = kind == 0x80 or (kind == 0xb0 and data1 == 120)
    logging_error = None
    try:
        journal.record('707_short_message_intent', status=status, data1=data1, data2=data2)
    except Exception as error:
        if not cleanup: raise
        logging_error = error
    function = session.api.dll.midiOutShortMsg
    function.argtypes, function.restype = [hardware.HANDLE, hardware.DWORD], hardware.UINT
    session.api.checked('midiOutShortMsg', session.output, status | data1 << 8 | data2 << 16)
    if logging_error: raise RuntimeError('Cleanup sent but logging failed') from logging_error


def wait_for(call, predicate, label):
    last = None
    for _ in range(100):
        last = call()
        if predicate(last): return last
        time.sleep(.01)
    raise RuntimeError(label + ': ' + repr(last))


def musical(raw):
    value = native.decode(raw)
    value.pop('source_generation')
    return value


def pending_save(status):
    return bool(status['save_token'] and status['save_token'] != status['save_acked_token'])


def restore_probe_records(raw):
    """Exercise complete state, including a genuinely inactive pattern cell."""
    state = native.decode(raw)
    state['preset_id'] = native.CUSTOM_PRESET
    state['vced'][145:155] = list(b'TEST707 OK')
    state['length'] = min(state['length'], 63)
    state['controls'][186] = state['length']
    state['controls'][187] = min(state['controls'][187], state['length'] - 1)
    state['controls'][188:191] = state['steps'][state['controls'][187]][:]
    state['steps'][63] = [128, 77, 93]
    for budget in (1, 4):
        state['controls'][191] = budget
        yield budget, native.encode(state)


def run_native(bench, nb, result, directory):
    cases = result['cases'] = []
    before = legacy.query(bench.session, bench.journal, 2)
    bench.performance_baseline = bench.performance()
    if bench.performance_baseline['performance_errors'] or any(before[key] for key in feature.FAILURES):
        raise RuntimeError('Native bench requires fault-free initial DSP/performance counters')
    bench.set(193, 0)
    bench.set(179, 0)
    bench.set(191, 4)
    send = lambda s, a, b=0: short_message(bench.session, bench.journal, s, a, b)
    for index in range(16):
        send(0xcf, index)
        wait_for(nb.status, lambda x: x['preset_id'] == index and not x['sound_dirty'], 'factory recall')
        raw, _ = nb.snapshot(); state = native.decode(raw)
        name = bytes(state['vced'][145:155]).decode('ascii').rstrip()
        if state['preset_id'] != index or name != NAMES[index] or state['controls'][160] != (index >= 8):
            raise RuntimeError('Factory preset metadata/readback mismatch: ' + repr((index, name)))
        legacy.reset_peaks(bench.session)
        bench.notes(); time.sleep(.08)
        diag = bench.check(before)
        if diag['active_voices'] != 4: raise RuntimeError('Four quiet preset notes not owned')
        bench.notes(on=False); bench.transport(5)
        cases.append(dict(case='factory program', program=index, name=name, diagnostics=diag))

    # Browse is reversible; recall is deliberate, and the original sound stays
    # active while a candidate is displayed. Presets retain performance/FX.
    send(0xcf, 0); time.sleep(.03)
    prior, _ = nb.snapshot()
    bench.panel(1, 6, 1)
    wait_for(bench.performance,lambda x:x['page_family']==9,'preset browser opened')
    if musical(nb.snapshot()[0]) != musical(prior):
        raise RuntimeError('Preset browsing altered sound or did not open browser')
    bench.button(8)
    if musical(nb.snapshot()[0]) != musical(prior): raise RuntimeError('Preset cancel changed sound')
    bench.panel(1, 6, 1); bench.button(3)
    # The candidate survives prior browsing and is outside native state. Verify
    # the selected identity, then an observable adjacent recall instead of
    # assuming that a prior owner's candidate was always zero.
    recalled=wait_for(nb.status,lambda x:x['preset_id']<16 and not x['sound_dirty'] and
                     bench.performance()['page_family']==0,'SEL recalls candidate')
    recalled_state=native.decode(nb.snapshot()[0])
    if bytes(recalled_state['vced'][145:155]).decode('ascii').rstrip()!=NAMES[recalled['preset_id']]:
        raise RuntimeError('SEL recall factory metadata disagrees')
    bench.panel(1,6,1);bench.button(3)
    wait_for(nb.status,lambda x:x['preset_id']==(recalled['preset_id']+1)%16 and not x['sound_dirty'],
             'next candidate confirms adjacent factory slot')
    bench.set(170, 25); bench.set(194, 75); bench.set(178, 137)
    send(0xcf, 3); time.sleep(.03)
    controls = bench.controls()
    if (controls[170], controls[194], controls[178]) != (25,75,137):
        raise RuntimeError('Factory recall replaced FX or tempo')
    cases.append(dict(case='preset browse cancel confirm preserves FX and tempo'))
    bench.trace()
    bench.set(134,31); bench.panel(1,1,1)
    wait_for(lambda: bench.controls()[134], lambda x: x == 0, 'algorithm wraps31to0')
    bench.panel(1,1,-1)
    wait_for(lambda: bench.controls()[134], lambda x: x == 31, 'algorithm wraps0to31')
    cases.append(dict(case='algorithm detents and wrap', sound_policy='next note'))

    # Sound module receive filtering, including program changes and canonicalCC.
    bench.set(193,1); bench.transport(5)
    send(0xcf,7); send(0x9f,60,32); time.sleep(.04)
    if nb.status()['preset_id'] != 3 or legacy.query(bench.session,bench.journal,2)['active_voices']:
        raise RuntimeError('Wrong-channel program/note was accepted')
    send(0x8f,60); send(0xc0,8)
    wait_for(nb.status,lambda x:x['preset_id']==8,'channel1 program accepted')
    send(0x90,60,32); time.sleep(.04)
    if legacy.query(bench.session,bench.journal,2)['active_voices'] != 1:
        raise RuntimeError('Selected-channel note not accepted')
    send(0x80,60); send(0xb0,120)
    for cc, identifier, value in ((74,162,20000),(71,163,95),(73,164,10000),(72,167,10000)):
        send(0xb0,cc,127)
        wait_for(lambda:bench.controls()[identifier],lambda x:x==value,'CC control adoption')
    send(0x90,60,32);time.sleep(.03);bench.set(193,16)
    if legacy.query(bench.session,bench.journal,2)['active_voices']:
        raise RuntimeError('Channel change did not clear old owners')
    send(0x80,60);bench.set(193,0);send(0xcf,0)
    wait_for(nb.status,lambda x:x['preset_id']==0 and not x['sound_dirty'],'FM reset after channel checks')
    cases.append(dict(case='MIDI receive channel programs CC and owner cleanup'))
    bench.trace()

    # Stress optional FX only after core priority effects have retained capacity.
    for identifier,value in ((168,100),(169,100),(170,100),(171,1000),(172,85),
                             (173,100),(174,100),(194,100),(162,20000)):
        bench.set(identifier,value)
    legacy.reset_peaks(bench.session);bench.notes();time.sleep(.35)
    diag=bench.check(before);bench.notes(on=False);bench.transport(5)
    if diag['maximum_render_us'] >= 2032: raise RuntimeError('FX stress exceeded70% audio budget')
    cases.append(dict(case='all FX maximum four-note timing',diagnostics=diag))

    # Every inactive cell and exact name must survive a real upload/readback.
    original, _ = nb.snapshot()
    for budget, record in restore_probe_records(original):
        restored=nb.restore(record,directory)
        if musical(nb.snapshot()[0]) != musical(record): raise RuntimeError('Complete native readback differs')
        if legacy.query(bench.session,bench.journal,2)['voice_limit']!=budget:
            raise RuntimeError('Native import voice budget differs from running pool')
        cases.append(dict(case='complete RAM restore name inactive step and voice budget',budget=budget,**restored))
        bench.trace()
    # Well-formed stale and incomplete transactions are refused without changes.
    raw,status=nb.snapshot();tx=0x70701
    def reply(packet,op):
        return native.parse_result(nb.request(packet,'707_native_refusal_test'),opcode=op,transaction=tx)['result']
    if reply(native.begin_request(tx,status['live_generation']),16): raise RuntimeError('Begin failed')
    if reply(native.commit_request(tx),18)!=13: raise RuntimeError('Incomplete commit not refused')
    nb.abort_staging(tx)
    bench.set(162,19998)
    edited=nb.snapshot()[0]
    if reply(native.begin_request(tx,status['live_generation']),16): raise RuntimeError('Stale begin failed')
    for offset in range(0,native.SIZE,64):
        if reply(native.write_chunk_request(tx,offset,raw[offset:offset+64]),17):raise RuntimeError('Stale chunk failed')
    if reply(native.commit_request(tx),18)!=14:raise RuntimeError('Stale commit not refused')
    nb.abort_staging(tx)
    if musical(nb.snapshot()[0])!=musical(edited):raise RuntimeError('Refused import changed live state')
    cases.append(dict(case='incomplete and stale native imports preserve live state'))
    # Save freezes what was present at button press, even after later editing.
    prior_save=nb.status()
    if pending_save(prior_save):raise RuntimeError('Pending prior SAVE must be completed before SAVE workflow test')
    bench.button(9)
    saved=wait_for(nb.status,lambda x:x['save_token'] and x['save_token']!=prior_save['save_token'] and
                   x['save_token']!=x['save_acked_token'],'fresh SAVE snapshot')
    token=saved['save_token'];frozen=nb.read_token(token)
    committed=native.save_backup(frozen,directory,device_identity=bridge.IDENTITY,source='707 virtual SAVE protocol bench')
    bench.set(162,19999)
    if nb.read_token(token)!=frozen: raise RuntimeError('SAVE snapshot changed with later editing')
    nb.acknowledge_save(token,frozen)
    if nb.status()['save_acked_token']!=token: raise RuntimeError('Durable SAVE not acknowledged')
    cases.append(dict(case='SAVE frozen exact-file acknowledgement',backup=committed,token=token))
    bench.button(8)
    result['after']=bench.check(before)


def cleanup_and_restore(session,bench,nb,original,directory,result):
    """Attempt every release and complete restore, preserving all failures."""
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
    parser.add_argument('--mode',choices=('native','features','matrix','releases'),default='native')
    args=parser.parse_args(argv)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')+'-'+uuid.uuid4().hex[:8]
    journal=transport.Journal(transport.ROOT/'artifacts/fm1-707-bench'/stamp)
    directory=journal.directory/'backups'
    result=dict(success=False,identity=bridge.IDENTITY,mode=args.mode,flash_writes=False,audio_recorded=False,
                tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    session=bench=nb=None;original=None
    try:
        session=transport.find_session(hardware.WinMM(),bridge.IDENTITY,journal,wait=2)
        bench=feature.Bench(session,journal,identity=bridge.IDENTITY);nb=bridge.NativeBridge(session,journal)
        perf=bench.performance();led=telemetry.led_state(session,journal,identity=bridge.IDENTITY)
        if perf['seq_running'] or perf['seq_recording'] or perf['arp_held'] or led['physical_keys'] or led['held_buttons'] or led['active_voices']:
            raise RuntimeError('Bench requires released keys and stopped transport')
        if pending_save(nb.status()):
            raise RuntimeError('Complete pending SAVE-to-PC backup before starting the bench')
        captured,_=nb.snapshot()
        result['pre_test_backup']=native.save_backup(captured,directory,device_identity=bridge.IDENTITY,source='complete pre-bench backup')
        bench.trace(initial=True)
        # Only arm musical cleanup after a durable backup and before the first
        # permitted mutation. A failed read/backup must not issue note or panic commands.
        original=captured
        if args.mode=='native':run_native(bench,nb,result,directory)
        elif args.mode=='features':feature.run(bench,result)
        else:
            bench.set(193,0);bench.set(179,0)
            (legacy.run_matrix if args.mode=='matrix' else legacy.run_releases)(session,journal,result)
        result['success']=True
    except Exception as error:
        result.update(success=False,error=repr(error))
    finally:
        if original is not None:
            cleanup_and_restore(session,bench,nb,original,directory,result)
        if session is not None:
            try:
                failures=session.close()
                if failures:result.update(success=False,close_errors=failures)
            except Exception as error:result.update(success=False,close_errors=[repr(error)])
        try:
            journal.record('707_bench_finished',**result)
        except Exception as error:result.update(success=False,final_logging_error=repr(error))
        try:journal.close()
        except Exception as error:result.update(success=False,journal_close_error=repr(error))
        try:
            native._write_new(journal.directory/'report.json',(json.dumps(result,indent=2)+'\n').encode())
        except Exception as error:result.update(success=False,report_write_error=repr(error))
    print(json.dumps(dict(success=result['success'],error=result.get('error'),restoration_error=result.get('restoration_error'),
                         close_errors=result.get('close_errors'),final_logging_error=result.get('final_logging_error'),
                         report_write_error=result.get('report_write_error'),artifacts=str(journal.directory))))
    return 0 if result['success'] else 1


if __name__=='__main__':raise SystemExit(main())
