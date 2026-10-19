"""Exact724 connected MIDI bench. Backs up/restores live sound and global setup.
Uses WinMM short-message captures, source-separated incoming traffic, clocks,
transport, CCs and real generated-note output. No device flash writes.
"""
from pathlib import Path
from datetime import datetime,timezone
import json,time,traceback,hashlib
import fm1_native_bridge_v18 as bridge
import fm1_724_bench as musical
import fm1_704_bench as feature
import fm1_bench as legacy
import hardware_bridge as hw
import fm1_session as telemetry

def main():
 out=bridge.transport.ROOT/'artifacts/fm1-724-midi-bench'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
 journal=bridge.transport.Journal(out);report=dict(success=False,identity=bridge.IDENTITY,flash_writes=False,tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),cases=[])
 session=nb=b=None;original=old_midi=None
 def case(name,**kw):
  report['cases'].append(dict(case=name,**kw));journal.record('midi_case_passed',case=name,**kw);print(name,flush=True)
  (out/'progress.json').write_text(json.dumps(report,indent=2),encoding='utf8')
 def send(status,a=0,c=0):
  assert session.verified_identity==bridge.IDENTITY
  assert status in (0x90,0x80,0x9f,0x8f,0xbf,0xef,0xfa,0xfb,0xfc,0xf8,0xf2,0xfe,0xff) and 0<=a<128 and 0<=c<128
  journal.record('midi_input_intent',status=status,data1=a,data2=c)
  fun=session.api.dll.midiOutShortMsg;fun.argtypes,fun.restype=[hw.HANDLE,hw.DWORD],hw.UINT
  session.api.checked('midiOutShortMsg',session.output,status|(a<<8)|(c<<16))
 def drain(label):
  time.sleep(.04);rows=[]
  while session.short_received:
   p,t,bad=session.short_received.popleft();assert not bad
   rows.append(dict(status=p&255,data1=(p>>8)&127,data2=(p>>16)&127,driver_ms=t))
  assert not session.short_overflow
  journal.record('midi_output_capture',label=label,packets=rows);return rows
 def notes(rows):return [x for x in rows if x['status']&240==144 and x['data2']]
 def configure(values):
  result=nb.midi_configure(values);drain('settings cleanup');return result
 try:
  session=bridge.transport.find_session(hw.WinMM(),bridge.IDENTITY,journal,wait=2);session.capture_short=True
  nb=bridge.NativeBridge(session,journal);b=feature.Bench(session,journal,identity=bridge.IDENTITY)
  lights=telemetry.led_state(session,journal,identity=bridge.IDENTITY)
  if lights['physical_keys'] or lights['held_buttons']:raise RuntimeError('Physical keys must be released')
  original,_=nb.snapshot();report['backup']=bridge.native.save_backup(original,out/'backups',device_identity=bridge.IDENTITY,source='before724 MIDI bench')
  old_midi=nb.midi_status();report['midi_before']=old_midi;before=legacy.query(session,journal,2)
  nb.restore(musical.pattern_probe(original,chain_mask=1),out/'backups')
  configure([3,15,1,0,0,1,1,0])
  send(0x9f,60,32);time.sleep(.04);assert legacy.query(session,journal,2)['active_voices']==1
  send(0x8f,60);send(0xbf,120);assert not notes(drain('received notes no echo'))
  send(0xbf,74,65);assert not drain('received cutoff no echo')
  b.set(162,1000);cc=drain('panel cutoff out');assert any(x['status']==0xbf and x['data1']==74 for x in cc)
  case('USB notes and selected CC input; no input echo; panel tone CC output',output=cc)
  configure([2,15,1,0,1,1,0,0]);b.set(178,120)
  b.transport(1);time.sleep(1.04);b.transport(3);rows=drain('internal clock sequence')
  clocks=[x for x in rows if x['status']==0xf8];assert 46<=len(clocks)<=55,(len(clocks),rows)
  assert sum(x['status']==0xfa for x in rows)==1 and sum(x['status']==0xfc for x in rows)==1
  attacks=notes(rows);offs=[x for x in rows if x['status']==0x8f];assert len(attacks)>=7 and len(attacks)==len(offs)
  assert all(x['status']==0x9f for x in attacks)
  case('Internal24PPQN clock, Start/Stop and balanced channel16 sequencer notes',clocks=len(clocks),notes=len(attacks),clock_intervals_ms=[c['driver_ms']-a['driver_ms'] for a,c in zip(clocks,clocks[1:])])
  configure([2,15,1,1,1,1,0,0]);start=nb.midi_status();send(0xf2,3);send(0xfb)
  for _ in range(24):send(0xf8);time.sleep(.021)
  send(0xfc);rows=drain('external located sequence');attacks=notes(rows);after=nb.midi_status()
  assert after['received_clock']-start['received_clock']==24 and after['received_song_position']==start['received_song_position']+1
  assert [x['data1'] for x in attacks]==[64,60,64,60],attacks
  assert not any(x['status']>=0xf8 for x in rows),'external clock or transport echoed'
  case('USB Song Position/Continue, exact24 incoming pulses, correct sequence notes and no realtime echo',notes=attacks,midi=after)
  send(0xfa);send(0xf8);time.sleep(.7);assert not b.performance()['seq_running'];assert nb.midi_status()['clock_timeouts']==start['clock_timeouts']+1
  case('Clock loss stops slaved playback and increments timeout counter')
  configure([3,15,1,1,0,1,0,0]);b.set(179,1);b.set(180,2);b.set(181,16);b.set(182,1)
  for p in (60,64,67):send(0x9f,p,32)
  send(0xfa);drain('held notes suppressed')
  for _ in range(24):send(0xf8);time.sleep(.021)
  send(0xfc);rows=drain('clocked arp');assert [x['data1'] for x in notes(rows)]==[60,64,67,64]
  for p in (60,64,67):send(0x8f,p)
  case('Exclusive arp follows external clock, releases on Stop, emits expected pitch order')
  configure([2,15,1,0,0,1,0,0]);b.set(179,1);b.set(180,6);b.set(182,4)
  for p in (60,64):send(0x9f,p,32)
  time.sleep(.30);b.transport(3);rows=drain('expanded Repeat');pitches={x['data1'] for x in notes(rows)}
  assert pitches=={60,64,72,76,84,88,96,100},pitches
  case('Repeat transmits all8 expanded pitches independently of4 local voices',pitches=sorted(pitches))
  configure([0,0,1,0,0,1,0,0]);b.set(179,0);b.set(193,16)
  send(0x90,60,32);time.sleep(.04);assert not legacy.query(session,journal,2)['active_voices']
  send(0x9f,60,32);time.sleep(.04);assert legacy.query(session,journal,2)['active_voices']==1
  for cc,value in ((1,127),(7,100),(11,100),(64,127)):send(0xbf,cc,value)
  send(0xef,0,96);send(0x8f,60);time.sleep(.03);assert legacy.query(session,journal,2)['active_voices']==1
  send(0xbf,64,0);send(0xbf,121,0);send(0xbf,120,0)
  send(0xfe);send(0x9f,64,32);time.sleep(.45);assert not legacy.query(session,journal,2)['active_voices']
  case('Receive-channel filtering, CC1/7/11/64/121/120, pitch bend and Active Sensing release')
  after=legacy.query(session,journal,2);perf=b.performance();midi=nb.midi_status()
  for key in ('overruns','midi_overflows','rejected_messages','retained_crash_count','load_sheds','lcd_timeouts'):assert after[key]==before[key],(key,before[key],after[key])
  assert perf['performance_errors']==0 and not midi['queue_overflows'] and not midi['output_refused']
  case('No new audio/MIDI overflow, rejected input, crash, shed or display timeout',diagnostics=after,performance=perf,midi=midi)
  report['success']=True
 except Exception as e:report.update(error=repr(e),traceback=traceback.format_exc());print(report['traceback'],flush=True)
 finally:
  if session is not None and nb is not None:
   try:
    if b:b.cleanup()
    if old_midi:nb.midi_configure(old_midi['settings'])
    if original:report['restored']=nb.restore(original,out/'backups')
    if b:b.button(8)
   except Exception as e:report.update(success=False,cleanup_error=repr(e))
  if session is not None:
   errors=session.close()
   if errors:report.update(success=False,close_errors=errors)
  (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf8');journal.close();print(out,flush=True)
 return 0 if report['success'] else 1
if __name__=='__main__':raise SystemExit(main())
