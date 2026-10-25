"""Independent-bank safety, complete-state retention and actual-core HTTP tests.

All writes target TemporaryDirectory, never the owner's companion workspace.
"""
import base64
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import companion_bank as bank
import companion
from companion_http import CompanionHTTPServer as HTTPServer
import library
import sandbox

def fixture(engine=0):
    c=[bank.native.control_bounds(i)[0] for i in range(198)]
    c[160]=engine;c[186:191]=[16,0,128,100,75];c[191]=4
    s=dict(schema=bank.native.SCHEMA,version=bank.native.VERSION,source_generation=17,preset_id=65535,
           controls=c,vced=c[:145]+list(b'TEST SOUND'),
           patterns=[dict(length=16,steps=[[128,100,75] for _ in range(64)]) for _ in range(bank.native.PATTERN_COUNT)])
    bank.native.initialize_tracks(s)
    s['patterns'][7]['steps'][63]=[97,112,51] # Hidden data must survive every sound edit.
    return dict(name='TEST SOUND',category='Custom',favorite=False,audition_note=60,native=bank.pack(s))

class BankTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'banks'
        self.defaults=[fixture(i%2) for i in range(64)]
        self.store=bank.BankLibrary(self.root,Path('unused'),defaults=self.defaults)
    def tearDown(self):self.tmp.cleanup()
    def call(self,action,**kw):
        return self.store.dispatch(dict(action=action,revision=self.store.snapshot()['revision'],**kw))
    def test_seeded_banks_are_independent_and_first_read_is_not_a_write(self):
        s=self.store.snapshot();self.assertEqual(s['slots'][:64],s['slots'][64:]);self.assertFalse(self.root.exists())
        s['slots'][0]['name']='OUTSIDE';self.assertEqual(self.store.snapshot()['slots'][64],fixture())
    def test_each_bank_accepts_either_engine_and_restart_retains_all_patterns(self):
        for slot,engine in ((0,1),(63,0),(64,1),(127,0)):
            self.call('save',slot=slot,entry=fixture(engine))
        restart=bank.BankLibrary(self.root,Path('unused'),defaults=self.defaults)
        for slot,engine in ((0,1),(63,0),(64,1),(127,0)):
            s=bank.decode_record(restart.snapshot()['slots'][slot]['native'])
            self.assertEqual(s['controls'][160],engine);self.assertEqual(s['patterns'][7]['steps'][63],[97,112,51])
    def test_reset_defaults_leaves_every_user_byte_unchanged(self):
        edit=fixture(1);edit['favorite']=True
        self.call('save',slot=0,entry=edit);self.call('save',slot=127,entry=edit)
        before=self.store.snapshot()['slots'][64:]
        result=self.call('reset_defaults',confirmation=bank.CONFIRM['reset_defaults'])
        self.assertEqual(result['slots'][:64],self.defaults);self.assertEqual(result['slots'][64:],before)
    def test_user_reset_uses_original_profile_not_edited_defaults(self):
        edit=fixture(1);edit['favorite']=True;self.call('save',slot=0,entry=edit)
        self.call('clear_user',confirmation=bank.CONFIRM['clear_user'])
        self.assertEqual(self.store.snapshot()['slots'][64:],[None]*64)
        r=self.call('reset_user',confirmation=bank.CONFIRM['reset_user'])
        self.assertEqual(r['slots'][0],edit);self.assertEqual(r['slots'][64:],self.defaults)
    def test_clear_undo_and_backup_restore_preserve_both_banks(self):
        self.call('save',slot=8,entry=fixture(1));before=self.store.snapshot()['slots']
        backup=self.call('backup')['backup'];self.call('clear_user',confirmation=bank.CONFIRM['clear_user'])
        self.assertEqual(self.call('undo')['slots'],before)
        self.call('clear_user',confirmation=bank.CONFIRM['clear_user'])
        self.assertEqual(self.call('restore',backup=backup)['slots'],before)
    def test_resets_require_exact_named_confirmation(self):
        for action in bank.CONFIRM:
            for confirmation in (None,'yes',bank.CONFIRM['clear_user'] if action!='clear_user' else 'Reset User Bank'):
                with self.subTest(action=action,confirmation=confirmation),self.assertRaises(ValueError):
                    self.call(action,confirmation=confirmation)
        self.assertFalse(self.root.exists())
    def test_stale_revision_and_failed_commit_preserve_last_saved_file(self):
        self.call('save',slot=0,entry=fixture());before=self.store.path.read_bytes()
        with self.assertRaises(library.LibraryConflict):self.store.dispatch(dict(action='save',revision=0,slot=1,entry=fixture(1)))
        real=self.store._atomic
        def fail_primary(path,data):
            if path==self.store.path:raise OSError('simulated interrupted commit')
            real(path,data)
        with patch.object(self.store,'_atomic',side_effect=fail_primary),self.assertRaises(OSError):
            self.call('clear_user',confirmation=bank.CONFIRM['clear_user'])
        self.assertEqual(self.store.path.read_bytes(),before)
    def test_corruption_and_unknown_fields_cannot_modify_bank(self):
        self.call('save',slot=0,entry=fixture());before=self.store.path.read_bytes()
        bad=fixture();raw=bytearray(base64.b64decode(bad['native']));raw[-1]^=1;bad['native']=base64.b64encode(raw).decode()
        with self.assertRaises(ValueError):self.call('save',slot=64,entry=bad)
        backup=self.call('backup')['backup'];backup['payload']['slots'][0]=None
        backup['sha256']=hashlib.sha256(library.canonical(backup['payload'])).hexdigest()
        with self.assertRaises(ValueError):self.call('restore',backup=backup)
        with self.assertRaises(ValueError):self.call('save',slot=64,entry=fixture(),device_write=True)
        self.assertEqual(self.store.path.read_bytes(),before)
    def test_deployment_is_a_data_plan_and_contains_no_device_action(self):
        r=self.call('deployment',bank='user');self.assertTrue(r['requires_reconciliation']);self.assertFalse(r['device_writes'])
        self.assertEqual(r['slots'],self.defaults);self.assertFalse(self.root.exists())
    def test_render_settings_include_every_target_va_and_effect_value(self):
        e=fixture(1);s=bank.decode_record(e['native']);s['controls'][163:168]=[37,121,345,62,876]
        s['controls'][175:178]=[345,13,2631];e['native']=bank.pack(s);r=bank.render_settings(e)
        self.assertEqual(r['va'],dict(resonance=.37,attack_ms=121,decay_ms=345,sustain=.62,release_ms=876,lfo_rate_hz=3.45,lfo_depth_cents=13))
        self.assertEqual(r['cutoff'],2631);self.assertEqual(r['budget'],4)

    def test_v4_save_backup_fx_and_restart_preserve_all_track_and_glide_metadata(self):
        from tests.test_fm1_native_v4 import fixture as workstation
        import fm1_native_state_v4 as v4
        s=bank.native.decode_compatible(v4.encode(workstation()));s['vced'][145:]=list(b'TEST SOUND');entry=fixture();entry['native']=bank.pack(s)
        self.call('save',slot=64,entry=entry)
        backup=self.call('backup')['backup']
        self.call('clear_user',confirmation=bank.CONFIRM['clear_user']);self.call('restore',backup=backup)
        restart=bank.BankLibrary(self.root,Path('unused'),defaults=self.defaults)
        self.assertEqual(bank.decode_record(restart.snapshot()['slots'][64]['native']),s)
        fx=bank.export_fx(s);fx['controls']['173']=71
        changed=bank.import_fx(s,fx);self.assertEqual(changed['controls'][173],71)
        changed['controls'][173]=s['controls'][173]
        self.assertEqual(changed,s)
        s['controls'][191]=1;entry['native']=bank.pack(s)
        rendered=bank.render_settings(entry)
        self.assertTrue(rendered['mono']);self.assertEqual(rendered['glide'],dict(mode=2,time_ms=430,curve=1))

    def test_reading_718_library_never_rewrites_legacy_user_records(self):
        from tests.test_fm1_native_v2 import state_fixture
        import fm1_native_state_v2 as v2
        import fm1_native_state_v3 as v3
        s=v3.decode(v3.upgrade_v2(v2.encode(state_fixture())))
        s['vced'][145:]=list(b'TEST SOUND');e=fixture();e['native']=base64.b64encode(v3.encode(s)).decode()
        payload=self.store._empty();payload['profile']='FMER Default 718.1';payload['slots'][64]=e
        self.root.mkdir(parents=True);self.store.path.write_bytes(library.canonical(self.store._envelope(payload)))
        before=self.store.path.read_bytes();snapshot=self.store.snapshot()
        self.assertEqual(snapshot['slots'][64],e);self.assertEqual(self.store.path.read_bytes(),before)
        migrated=bank.decode_record(e['native']);self.assertEqual(migrated['controls'][150:155],[0,150,0,0,0])
        self.assertEqual(migrated['patterns'][:8],s['patterns']);self.assertEqual(migrated['controls'][160:],s['controls'][160:])
        self.assertTrue(all(step[0]==128 for p in migrated['patterns'][8:] for step in p['steps']))

@unittest.skipUnless(os.environ.get('FMER_HOST_EXE'),'actual renderer requires FMER_HOST_EXE')
class ActualCompanionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exe=Path(os.environ['FMER_HOST_EXE']);cls.profile=bank.profile(cls.exe)
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.previous=sandbox.OUTPUT;sandbox.OUTPUT=self.root/'audio'
        self.server=HTTPServer(('127.0.0.1',0),companion.handler_for(self.exe,self.root/'banks'))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}'
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();sandbox.OUTPUT=self.previous;self.tmp.cleanup()
    def request(self,path,data=None,origin=None):
        headers={'Content-Type':'application/json'}
        if origin:headers['Origin']=origin
        with urlopen(Request(self.url+path,None if data is None else library.canonical(data),headers),timeout=15) as r:
            self.assertEqual(r.headers['Cache-Control'],'no-store');return json.load(r)
    def test_all64_valid_seeded_sounds_have_correct_engine_and_full_native_state(self):
        s=self.request('/api/banks');self.assertEqual(s['slots'],self.profile*2)
        self.assertEqual(sum(bank.decode_record(e['native'])['controls'][160] for e in self.profile),28)
        self.assertEqual(len({e['native'] for e in self.profile}),64)
    def test_http_save_restart_reset_scopes_and_cross_origin_refusal(self):
        e=deepcopy(self.profile[63]);e['favorite']=True
        r=self.request('/api/banks',dict(action='save',revision=0,slot=64,entry=e));self.assertEqual(r['revision'],1)
        with self.assertRaises(HTTPError) as caught:self.request('/api/banks',dict(action='clear_user',revision=1,confirmation='Clear User Bank'),'https://elsewhere.invalid')
        self.assertEqual(caught.exception.code,403)
        self.assertEqual(self.request('/api/banks')['slots'][64],e)
    def test_browser_startup_diagnostics_export_and_origin_guard(self):
        event=dict(event='script_load_error',detail='/companion_app.js',browser='Regression browser')
        self.request('/api/startup',event)
        report=self.request('/api/startup-report')
        self.assertEqual(report['events'][-1]['detail'],event['detail'])
        self.assertEqual(report['format'],'FMER-STARTUP-DIAGNOSTICS')
        for path,data in (('/api/startup',event),('/api/startup-report',None)):
            with self.assertRaises(HTTPError) as caught:self.request(path,data,'https://elsewhere.invalid')
            self.assertEqual(caught.exception.code,403)
        self.assertEqual(self.request('/api/startup-report'),report)
        self.assertFalse((self.root/'banks/library.json').exists())

    def test_simultaneous_bank_saves_keep_revision_conflict_and_data(self):
        from concurrent.futures import ThreadPoolExecutor
        e=deepcopy(self.profile[0]);e['favorite']=True
        self.request('/api/banks')
        def save(slot):
            try:return self.request('/api/banks',dict(action='save',revision=0,slot=slot,entry=e))['revision']
            except HTTPError as error:return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(save,(64,65)))
        self.assertEqual(sorted(results),[1,409])
        snapshot=self.request('/api/banks')
        self.assertEqual(snapshot['revision'],1)
        self.assertEqual(sum(snapshot['slots'][i]['favorite'] for i in (64,65)),1)
    def test_actual_audition_uses_va_envelope_and_budget_and_preserves_saved_state(self):
        e=deepcopy(next(e for e in self.profile if bank.decode_record(e['native'])['controls'][160]==1));s=bank.decode_record(e['native']);s['controls'][167]=777
        r=self.request('/api/work',dict(action='audition',entry=e,state=s,scenario='chord',velocity=110))
        self.assertEqual(r['voice_limit'],6);self.assertEqual(r['clipped_samples'],0);self.assertGreater(r['rms'],.001)
        records=list((self.root/'audio').glob('*/process.json'));self.assertEqual(len(records),1)
        process=json.loads(records[0].read_text());self.assertIn('release_ms=777',process['argv'])
        self.assertEqual(process['input']['vced'],s['vced']);self.assertFalse((self.root/'banks/library.json').exists())
    def test_native_import_preserves_hidden_patterns_without_saving(self):
        e=fixture(1);r=self.request('/api/work',dict(action='import',raw=e['native']))
        self.assertEqual(r['entry']['native'],e['native']);self.assertEqual(r['state']['patterns'][7]['steps'][63],[97,112,51])
        self.assertFalse((self.root/'banks/library.json').exists())

    def test_dx7_http_inspection_and_roundtrip_leave_library_unchanged(self):
        entry=next(e for e in self.profile if bank.decode_record(e['native'])['controls'][160]==0)
        exported=self.request('/api/dx7',dict(action='export',entries=[entry]))
        self.assertEqual(len(base64.b64decode(exported['raw'])),163)
        decoded=self.request('/api/dx7',dict(action='decode',raw=exported['raw'],collection='Community FM'))
        self.assertEqual(decoded['count'],1);self.assertFalse(decoded['hardware_access'])
        self.assertEqual(bank.decode_record(decoded['entries'][0]['native'])['vced'],bank.decode_record(entry['native'])['vced'])
        self.assertEqual(self.request('/api/catalog')['slots'],[])
        self.assertEqual(self.request('/api/banks')['revision'],0)
        imported=self.request('/api/catalog',dict(action='import',revision=0,backup=decoded['catalog']))
        self.assertEqual(len(imported['slots']),1)
        self.assertEqual(self.request('/api/catalog',dict(action='undo',revision=imported['revision']))['slots'],[])
        bad=bytearray(base64.b64decode(exported['raw']));bad[-2]^=1
        with self.assertRaises(HTTPError):self.request('/api/dx7',dict(action='decode',raw=base64.b64encode(bad).decode()))
        with self.assertRaises(HTTPError):self.request('/api/dx7',dict(action='export',entries=[next(e for e in self.profile if bank.decode_record(e['native'])['controls'][160]==1)]))
        with self.assertRaises(HTTPError) as caught:self.request('/api/dx7',dict(action='export',entries=[entry]),'https://elsewhere.invalid')
        self.assertEqual(caught.exception.code,403)

    def test_v4_native_import_and_encode_preserve_complete_metadata(self):
        from tests.test_fm1_native_v4 import fixture as workstation
        import fm1_native_state_v4 as v4
        s=bank.native.decode_compatible(v4.encode(workstation()));e=fixture();s['vced'][145:]=list(b'TEST SOUND');e['native']=bank.pack(s)
        r=self.request('/api/work',dict(action='import',raw=e['native']))
        self.assertEqual(r['state'],s);self.assertEqual(r['entry']['native'],e['native'])
        encoded=self.request('/api/work',dict(action='encode',entry=r['entry'],state=r['state']))
        self.assertEqual(encoded['entry']['native'],e['native']);self.assertFalse((self.root/'banks/library.json').exists())

    def test_actual_mono_glide_preview_is_audible_and_reports_exact_controls(self):
        e=deepcopy(self.profile[34]);s=bank.decode_record(e['native']);s['controls'][191]=1
        s['controls'][150:153]=[2,430,1]
        moving=self.request('/api/work',dict(action='audition',entry=e,state=s,scenario='sequence',velocity=100))
        self.assertTrue(moving['mono']);self.assertEqual(moving['glide'],dict(mode=2,time_ms=430,curve=1))
        s['controls'][150]=0
        dry=self.request('/api/work',dict(action='audition',entry=e,state=s,scenario='sequence',velocity=100))
        self.assertNotEqual(moving['waveform'],dry['waveform']);self.assertEqual(moving['clipped_samples'],0)
        self.assertGreater(moving['peak'],.01);self.assertEqual(moving['active_voices_end'],0)
    def test_all10_arp_orders_and_target20bpm_floor_reach_actual_renderer(self):
        e=deepcopy(self.profile[0]);s=bank.decode_record(e['native']);s['controls'][178]=20
        for order in range(10):
            with self.subTest(order=order):
                s['controls'][180]=order
                r=self.request('/api/work',dict(action='audition',entry=e,state=s,scenario='arp',velocity=100))
                self.assertEqual(r['scenario'],'arp');self.assertGreater(r['peak'],0)
                self.assertEqual(r['active_voices_end'],0);self.assertEqual(r['clipped_samples'],0)
    def test_selected_pattern_audition_uses_saved_notes_and_keeps_hidden_steps(self):
        e=deepcopy(self.profile[8]);s=bank.decode_record(e['native']);s['controls'][195]=7
        s['patterns'][7]['steps'][0]=[62,93,60];s['controls'][188:191]=[62,93,60]
        s['patterns'][7]['steps'][63]=[97,112,51]
        r=self.request('/api/work',dict(action='audition',entry=e,state=s,scenario='pattern',velocity=110))
        notes=[event for event in r['events'] if event['type']=='NoteOn']
        self.assertTrue(notes);self.assertTrue(all(n['data1']==62 and n['data2']==93 for n in notes))
        process=json.loads(next((self.root/'audio').glob('*/process.json')).read_text())
        self.assertEqual(process['input']['pattern']['steps'][63]['notes'],[{'pitch':97,'velocity':112}])

if __name__=='__main__':unittest.main()
