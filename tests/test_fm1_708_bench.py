from contextlib import ExitStack, redirect_stdout
import io,json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import fm1_708_bench as bench
from tests.test_fm1_native_bridge_v2 import fixture


class MessageTests(unittest.TestCase):
    def setUp(self):
        self.api=SimpleNamespace(dll=SimpleNamespace(midiOutShortMsg=Mock()),checked=Mock())
        self.session=SimpleNamespace(verified_identity='FM-1_708',api=self.api,output=123)
        self.journal=Mock()
    def test_all64_programs_and_quiet_note_cleanup_pack_exactly(self):
        messages=[(0xcf,id,0) for id in range(64)]+[(0x9f,n,32) for n in (60,64,67,71)]+[(0x8f,n,0) for n in (60,64,67,71)]
        messages += [(status,cc,value) for status in (0xb0,0xbf) for cc in (71,72,73,74) for value in (0,64,127)]
        messages += [(status,cc,0) for status in (0xb0,0xbf) for cc in (64,120,123)]
        for status,a,b in messages:
            bench.short_message(self.session,self.journal,status,a,b)
            self.api.checked.assert_called_with('midiOutShortMsg',123,status|a<<8|b<<16)
        self.assertEqual(self.api.checked.call_count,len(messages))
    def test_unknown_identity_loud_notes_and_arbitrary_messages_never_reach_api(self):
        for values in ((0xcf,64,0),(0xcf,1,1),(0x9f,60,127),(0x91,60,32),(0x9f,61,32),(0xbf,7,127),(0xbf,74,63),(0xbf,64,127),(0x9f,60,True)):
            with self.assertRaises(ValueError):bench.short_message(self.session,self.journal,*values)
        self.session.verified_identity='FM-1_707'
        with self.assertRaises(ValueError):bench.short_message(self.session,self.journal,0xcf,0)
        self.api.checked.assert_not_called()
    def test_failed_logging_still_sends_cleanup_but_blocks_attacks(self):
        self.journal.record.side_effect=OSError('disk full')
        with self.assertRaises(OSError):bench.short_message(self.session,self.journal,0x9f,60,32)
        self.api.checked.assert_not_called()
        for values in ((0x8f,60,0),(0xbf,64,0),(0xbf,120,0)):
            with self.assertRaisesRegex(RuntimeError,'Cleanup sent'):bench.short_message(self.session,self.journal,*values)
        self.assertEqual(self.api.checked.call_count,3)


class OracleTests(unittest.TestCase):
    def test_stable_midi_ids_are_not_incorrectly_partitioned_at32(self):
        self.assertEqual(sum(bench.program_engine(id)==0 for id in range(64)),32)
        for id,engine in ((0,0),(7,0),(8,1),(15,1),(16,0),(31,0),(39,0),(40,1),(63,1)):
            self.assertEqual(bench.program_engine(id),engine)
        self.assertEqual(len(set(bench.NAMES)),64)
        for id in (-1,64,True):
            with self.assertRaises(ValueError):bench.program_engine(id)
    def test_independent_arp_traces_distinguish_endpoint_and_played_variants(self):
        self.assertEqual(bench.expected_arp(2,8),[[60],[64],[67],[64],[60],[64],[67],[64]])
        self.assertEqual(bench.expected_arp(4,8),[[60],[64],[67],[67],[64],[60],[60],[64]])
        self.assertEqual(bench.expected_arp(7,8),[[67],[64],[60],[64],[67],[64],[60],[64]])
        self.assertEqual(bench.expected_arp(8,8),[[67],[64],[60],[60],[64],[67],[67],[64]])
        self.assertEqual(bench.expected_arp(3,3),[[67],[60],[64]])
        self.assertEqual(bench.expected_arp(6,2),[[60,64,67],[60,64,67]])
        self.assertEqual(bench.expected_arp(9,3),[[60],[67],[64]])
        self.assertEqual(bench.expected_arp(5,4),[[60],[64],[60],[67]])
    def test_trace_oracle_rejects_pitch_sample_missing_and_unowned_errors(self):
        origin=0xfffff000;expected=bench.expected_arp(7,8)
        groups=[dict(frame=(origin+i*44100//8)&0xffffffff,notes=notes) for i,notes in enumerate(expected)]
        self.assertEqual(bench.verify_groups(groups,expected,'test')['steps'],8)
        wrong=[dict(g) for g in groups];wrong[3]=dict(wrong[3],frame=(wrong[3]['frame']+1)&0xffffffff)
        with self.assertRaises(RuntimeError):bench.verify_groups(wrong,expected,'wrong sample')
        wrong=[dict(g) for g in groups];wrong[3]=dict(wrong[3],notes=[61])
        with self.assertRaises(RuntimeError):bench.verify_groups(wrong,expected,'wrong pitch')
        with self.assertRaises(RuntimeError):bench.verify_groups(groups[:3],expected,'too few')
        events=[dict(kind=10,source=5,value=32,audio_frame_low32=100,pitch=60),
                dict(kind=10,source=5,value=32,audio_frame_low32=100,pitch=64),
                dict(kind=10,source=5,value=0,audio_frame_low32=110,pitch=64),
                dict(kind=10,source=4,value=32,audio_frame_low32=120,pitch=67)]
        self.assertEqual(bench.generated_groups(events,5),[dict(frame=100,notes=[60,64])])
    def test_pattern_probe_retains_all_banks_and_isolated_high_steps(self):
        source=fixture();raw=bench.native.encode(source);record=bench.pattern_probe(raw,chain_mask=1)
        state=bench.native.decode(record)
        self.assertEqual(state['controls'][195:198],[0,1,1]);self.assertEqual(state['controls'][178],120)
        self.assertEqual([s[0] for s in state['patterns'][0]['steps'][:4]],[60,64,60,64])
        self.assertEqual([s[0] for s in state['patterns'][1]['steps'][:2]],[67,71])
        for bank,p in enumerate(state['patterns']):self.assertEqual(p['steps'][63],[90+bank,70+bank,80+bank])
        self.assertEqual(bench.native.decode(raw),source)
    def test_708_bounds_are_explicit_and_legacy_remains_narrow(self):
        for id,value in ((180,9),(195,7),(196,1),(197,255)):
            packet=bench.feature.parameter_packet(id,value,parameter_count=198)
            self.assertEqual(packet[7]|packet[8]<<7,id)
        for id,value in ((180,7),(195,0),(196,0),(197,1)):
            with self.assertRaises(ValueError):bench.feature.parameter_packet(id,value,parameter_count=195)
        for id,value in ((180,10),(195,8),(196,2),(197,0),(197,256)):
            with self.assertRaises(ValueError):bench.feature.parameter_packet(id,value,parameter_count=198)


class LifecycleTests(unittest.TestCase):
    def run_main(self,*,backup_error=False,run_error=False,active=False,restore_error=False):
        with tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
            journal=Mock(directory=Path(directory));session=Mock();session.close.return_value=[]
            feature=Mock(journal=journal);feature.performance.return_value=dict(seq_running=0,seq_recording=0,arp_held=0)
            native=Mock();native.store_status.return_value=dict(ready=1,busy=0)
            native.status.return_value=dict(save_token=0,save_acked_token=0);native.snapshot.return_value=(b'original',{})
            native.restore.return_value={'complete_state_verified':True}
            if restore_error:native.restore.side_effect=RuntimeError('restore failed')
            stack.enter_context(patch.object(bench.transport,'Journal',return_value=journal))
            stack.enter_context(patch.object(bench.hardware,'WinMM'))
            stack.enter_context(patch.object(bench.transport,'find_session',return_value=session))
            stack.enter_context(patch.object(bench.feature,'Bench',return_value=feature))
            stack.enter_context(patch.object(bench.bridge,'NativeBridge',return_value=native))
            stack.enter_context(patch.object(bench.telemetry,'led_state',return_value=dict(physical_keys=int(active),held_buttons=0,active_voices=0)))
            save=stack.enter_context(patch.object(bench.native,'save_backup',side_effect=OSError('disk full') if backup_error else None,return_value={'path':'safe-original'}))
            run=stack.enter_context(patch.object(bench,'run_essentials',side_effect=RuntimeError('test failed') if run_error else None))
            cleanup=stack.enter_context(patch.object(bench,'short_message'))
            stack.enter_context(patch.object(bench.native,'_write_new'))
            out=io.StringIO()
            with redirect_stdout(out):code=bench.main([])
            return dict(code=code,session=session,feature=feature,native=native,save=save,run=run,cleanup=cleanup,output=json.loads(out.getvalue()))
    def test_idle_prebackup_precedes_bench_and_final_restore_is_complete(self):
        r=self.run_main();self.assertEqual(r['code'],0);r['run'].assert_called_once()
        r['native'].restore.assert_called_once();self.assertEqual(r['native'].restore.call_args.args[0],b'original')
        self.assertEqual(r['cleanup'].call_count,8);r['session'].close.assert_called_once()
    def test_active_player_or_failed_backup_never_arms_musical_cleanup(self):
        for args in ({'active':True},{'backup_error':True}):
            r=self.run_main(**args);self.assertEqual(r['code'],1);r['run'].assert_not_called()
            r['cleanup'].assert_not_called();r['native'].restore.assert_not_called();r['session'].close.assert_called_once()
    def test_failed_bench_still_releases_and_restores_original(self):
        r=self.run_main(run_error=True);self.assertEqual(r['code'],1)
        self.assertIn('test failed',r['output']['error']);self.assertEqual(r['cleanup'].call_count,8)
        r['native'].restore.assert_called_once()
    def test_restore_failure_is_reported_separately_and_never_success(self):
        r=self.run_main(restore_error=True);self.assertEqual(r['code'],1)
        self.assertIn('restore failed',r['output']['restoration_error'])
    def test_cleanup_attempts_every_step_even_when_prior_step_fails(self):
        feature,native=Mock(),Mock();feature.cleanup.side_effect=RuntimeError('panic failed')
        native.restore.return_value={'complete_state_verified':True};result=dict(success=False,error='original failure')
        with patch.object(bench,'short_message',side_effect=RuntimeError('release failed')) as send:
            bench.cleanup_and_restore(object(),feature,native,b'original',Path('.'),result)
        self.assertEqual(send.call_count,8);native.restore.assert_called_once();feature.button.assert_called_once_with(8)
        self.assertEqual(len(result['final_cleanup_errors']),9);self.assertEqual(result['error'],'original failure')


class PresetRunnerTests(unittest.TestCase):
    def run_presets(self,*,bad_program=None,bad_voices=False):
        selected={'id':0};state=fixture();feature=Mock();native=Mock();result={'cases':[]}
        def send(session,journal,status,a,b=0):
            if status==0xcf:selected['id']=a
        def snapshot():
            program=selected['id'];state['preset_id']=program
            state['vced'][145:]=list(bench.NAMES[program].ljust(10).encode())
            state['controls'][160]=bench.program_engine(program)^(program==bad_program)
            return bench.native.encode(state),{}
        native.snapshot.side_effect=snapshot
        native.status.side_effect=lambda:dict(preset_id=selected['id'],sound_dirty=0)
        feature.check.return_value=dict(maximum_render_voices=3 if bad_voices else 4,active_voices=4)
        with patch.object(bench,'short_message',side_effect=send) as messages, \
             patch.object(bench.legacy,'reset_peaks'),patch.object(bench.time,'sleep'), \
             patch.object(bench.legacy,'query',return_value={'active_voices':0}):
            bench.run_presets(feature,native,result,{})
        return result,messages
    def test_every_program_gets_full_native_engine_name_and_four_note_check(self):
        result,messages=self.run_presets()
        self.assertEqual([case['program'] for case in result['cases']],list(range(64)))
        self.assertEqual([c.args[3] for c in messages.call_args_list if c.args[2]==0xcf],list(range(64)))
        self.assertEqual(sum(c.args[2]==0x9f for c in messages.call_args_list),256)
        self.assertEqual(sum(c.args[2]==0x8f for c in messages.call_args_list),256)
    def test_wrong_engine_or_incomplete_polyphony_cannot_pass(self):
        for kwargs in ({'bad_program':39},{'bad_voices':True}):
            with self.assertRaises(RuntimeError):self.run_presets(**kwargs)


if __name__=='__main__':unittest.main()
