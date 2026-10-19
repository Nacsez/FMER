"""Product contracts. Isolated files and fake transports; never opens MIDI."""
import base64
from copy import deepcopy
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock,patch
from tests.test_companion import fixture
import companion_archive as archive
import companion_bank as bank
import companion_jobs as jobs
import companion_device as device
import companion_shelf as shelf
import library
import build_companion_help as help_builder


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=shelf.Catalog(Path(self.temp.name)/'catalog',Path('unused'))
    def call(self,action,**kw):return self.store.dispatch(dict(action=action,revision=self.store.snapshot()['revision'],**kw))
    def add(self,**kw):return self.call('add',kind='instrument',entry=fixture(),title='An instrument',**kw)['slots'][-1]
    def test_organize_restart_trash_recover_and_undo_preserve_native(self):
        item=self.add();identity=item['id'];native=item['entry']['native']
        self.call('update',id=identity,title='My bass',tags=['bass'],favorite=True)
        self.call('move',ids=[identity],collection='../A collection')
        self.call('trash',ids=[identity]);self.assertTrue(self.store.snapshot()['slots'][0]['trashed'])
        self.call('recover',ids=[identity]);self.assertFalse(self.store.snapshot()['slots'][0]['trashed'])
        self.call('undo');self.assertTrue(self.store.snapshot()['slots'][0]['trashed'])
        reopened=shelf.Catalog(self.store.root,Path('unused')).snapshot()['slots'][0]
        self.assertEqual(reopened['entry']['native'],native);self.assertEqual(reopened['collection'],'../A collection')
        self.assertEqual(len(list(Path(self.temp.name).iterdir())),1)
    def test_export_import_new_identity_restore_confirmation_and_tamper(self):
        item=self.add();backup=self.call('export',ids=[item['id']])['backup']
        imported=self.call('import',backup=backup)['slots']
        self.assertEqual(len(imported),2);self.assertNotEqual(imported[0]['id'],imported[1]['id'])
        before=self.store.path.read_bytes();bad=deepcopy(backup);bad['payload']['slots'][0]['title']='tampered'
        with self.assertRaises(ValueError):self.call('import',backup=bad)
        with self.assertRaises(ValueError):self.call('restore',backup=backup)
        self.assertEqual(self.store.path.read_bytes(),before)
        restored=self.call('restore',backup=backup,confirmation='Replace Local Catalog')
        self.assertEqual(restored['slots'],[item])
    def test_stale_revision_and_duplicate_ids_refused(self):
        item=self.add();before=self.store.path.read_bytes()
        with self.assertRaises(library.LibraryConflict):self.store.dispatch(dict(action='trash',revision=0,ids=[item['id']]))
        with self.assertRaises(ValueError):self.call('trash',ids=[item['id'],item['id']])
        self.assertEqual(self.store.path.read_bytes(),before)
    def test_project_dependencies_extract_and_hidden_steps_survive(self):
        entry=fixture();ref=str(bank.decode_record(entry['native'])['tracks'][0]['sound_ref'])
        result=self.call('add',kind='project',title='Song',entry=entry,dependencies={ref:fixture(1)})
        project=result['slots'][0];r=self.call('extract',id=project['id'])
        self.assertEqual(len(r['slots']),2);self.assertEqual(r['slots'][0],project)
        self.assertEqual(r['slots'][1]['entry'],fixture(1))
        state=bank.decode_record(r['slots'][1]['entry']['native']);self.assertEqual(state['patterns'][7]['steps'][63],[97,112,51])
    def test_invalid_dependencies_and_capacity_refused_without_loss(self):
        item=self.add();before=self.store.path.read_bytes()
        with self.assertRaises(ValueError):self.call('update',id=item['id'],dependencies={'999':fixture()})
        with patch.object(shelf,'CAPACITY',1),self.assertRaises(ValueError):self.call('duplicate',ids=[item['id']])
        self.assertEqual(self.store.path.read_bytes(),before)


class BankOrganizeTests(unittest.TestCase):
    def test_rename_copy_swap_move_delete_and_undo(self):
        with tempfile.TemporaryDirectory() as directory:
            store=bank.BankLibrary(Path(directory),Path('unused'),defaults=[fixture(i%2) for i in range(64)])
            def call(action,**kw):return store.dispatch(dict(action=action,revision=store.snapshot()['revision'],**kw))
            original=bank.decode_record(fixture()['native'])
            renamed=call('rename',slot=64,name='BASS')['slots'][64]
            state=bank.decode_record(renamed['native']);state['vced'][145:]=original['vced'][145:]
            self.assertEqual(state,original)
            call('copy',slot=64,destination=65);call('delete',slot=66)
            call('move',slot=65,destination=66)
            self.assertIsNone(store.snapshot()['slots'][65]);self.assertEqual(store.snapshot()['slots'][66],renamed)
            call('swap',slot=0,destination=66);self.assertEqual(store.snapshot()['slots'][0],renamed)
            with self.assertRaises(ValueError):call('delete',slot=0)
            with self.assertRaises(ValueError):call('move',slot=0,destination=65)
            call('undo');self.assertEqual(store.snapshot()['slots'][0],fixture())


def unit_backup():
    raw=fixture()['native']
    return archive.seal(dict(identity='FM-1_721',created=datetime.now(timezone.utc).isoformat(),
        instruments=[raw]+[None]*63+[raw]*64,projects=[raw]+[None]*15,live=raw,midi=[0]*8))


class ArchiveTests(unittest.TestCase):
    def test_validate_plan_and_overlay_writes_only_populated_slots(self):
        value=unit_backup();plan=archive.plan(value)
        self.assertEqual((plan['instruments'],plan['projects']),(65,1))
        client=Mock();progress=Mock();result=archive.restore(client,value,Path('unused'),progress)
        self.assertEqual(client.push_slot.call_count,65);self.assertEqual(client.push_project.call_count,1)
        self.assertEqual([c.args[1] for c in client.push_slot.call_args_list],[0]+list(range(64,128)))
        self.assertTrue(result['empty_slots_preserved']);client.midi_configure.assert_called_once_with([0]*8,persist=True,backup_directory=Path('unused'))
        self.assertEqual(progress.call_args.kwargs['completed'],result['completed'])
    def test_restore_stops_at_first_ambiguous_write_without_retry(self):
        client=Mock();client.push_slot.side_effect=[None,RuntimeError('disconnect')]
        with self.assertRaisesRegex(RuntimeError,'disconnect'):archive.restore(client,unit_backup(),Path('unused'))
        self.assertEqual(client.push_slot.call_count,2);client.push_project.assert_not_called();client.restore.assert_not_called()
    def test_capture_is_read_only_and_refuses_changes(self):
        client=Mock();raw=base64.b64decode(fixture()['native'])
        client.session.verified_identity='FM-1_731'
        client.store_status.return_value=dict(generation=7,job=0);client.snapshot.return_value=(raw,dict(live_generation=4))
        client.midi_status.return_value=dict(settings=[0]*8);client.status.return_value=dict(live_generation=4)
        client.slot_catalog.return_value=client.project_catalog.return_value=dict(present=True)
        client.read_slot.return_value=client.read_project.return_value=(raw,{})
        self.assertEqual(archive.plan(archive.capture(client))['instruments'],128)
        client.push_slot.assert_not_called();client.restore.assert_not_called()
        client.status.return_value=dict(live_generation=5)
        with self.assertRaisesRegex(RuntimeError,'changed during'):archive.capture(client)
    def test_corrupt_or_missing_default_refused(self):
        value=unit_backup();value['payload']['instruments'][64]=None
        with self.assertRaises(ValueError):archive.validate(value)
        with self.assertRaisesRegex(ValueError,'DEFAULT'):archive.validate(archive.seal(value['payload']))


class DeviceTransactionTests(unittest.TestCase):
    def test_restore_commits_destination_backup_before_first_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);service=device.Device(Path('unused'),root/'local');client=Mock();session=Mock();session.verified_identity=device.bridge.IDENTITY;session.close.return_value=[]
            saved=unit_backup();observed=[]
            def restore(*args):
                files=list((root/'local/device-logs').glob('*/unit-backup.fmer-backup.json'))
                self.assertEqual(len(files),1);self.assertEqual(json.loads(files[0].read_text()),saved);observed.append(True)
                raise RuntimeError('write interrupted')
            with patch.object(device,'ROOT',root),patch.object(device.hardware_bridge,'WinMM'),patch.object(device.bridge.transport,'find_session',return_value=session),patch.object(device.bridge,'NativeBridge',return_value=client),patch.object(device.archive,'capture',return_value=saved),patch.object(device.archive,'restore',side_effect=restore) as action:
                with self.assertRaisesRegex(RuntimeError,'interrupted'):service.dispatch(dict(action='restore_all',backup=saved,confirmation='Restore populated unit slots'))
                action.assert_called_once()
            self.assertEqual(observed,[True]);session.close.assert_called_once()
            report=json.loads(next((root/'local/device-logs').glob('*/report.json')).read_text())
            self.assertFalse(report['success']);self.assertTrue(Path(report['backup_path']).is_file())
    def test_new_unconfirmed_commands_never_open_midi(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(device.hardware_bridge,'WinMM') as api:
            service=device.Device(Path('unused'),Path(directory))
            for request in (dict(action='restore_all',backup=unit_backup()),dict(action='instrument_copy',slot=0,destination=1),dict(action='instrument_rename',slot=0,name='Bad\nname',confirmation='Apply unit instrument change')):
                with self.assertRaises(ValueError):service.dispatch(request)
            api.assert_not_called()


class JobTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.device=Mock();self.service=jobs.Jobs(self.device,self.root)
    def wait(self,identifier):
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            result=self.service.status(identifier)
            if result['state']!='running':return result
            time.sleep(.01)
        self.fail('Background job did not finish')
    def test_serial_jobs_progress_failure_and_restart_evidence(self):
        entered=threading.Event();release=threading.Event()
        def operation(req,progress):
            progress('Verified first slot',completed=[0]);entered.set();release.wait(3);raise RuntimeError('simulated disconnect')
        self.device.dispatch.side_effect=operation
        job=self.service.start(dict(action='device',request=dict(action='catalog')))
        self.assertTrue(entered.wait(2))
        with self.assertRaises(library.LibraryConflict):self.service.start(dict(action='device',request=dict(action='catalog')))
        release.set();result=self.wait(job['id']);self.assertEqual(result['state'],'failed');self.assertEqual(result['progress']['completed'],[0])
        self.assertEqual(jobs.Jobs(self.device,self.root).status(job['id'])['error'],'simulated disconnect')
        self.assertEqual(self.device.dispatch.call_count,1)
    def test_interrupted_job_reports_uncertainty_and_never_replays(self):
        identifier='a'*32;self.service._save(dict(id=identifier,state='running'))
        result=self.service.status(identifier);self.assertEqual(result['state'],'interrupted');self.device.dispatch.assert_not_called()
        with self.assertRaises(ValueError):self.service.status('../elsewhere')
    def test_closing_server_refuses_new_device_work(self):
        self.service.closing=True
        with self.assertRaises(library.LibraryConflict):self.service.start(dict(action='device',request=dict(action='probe')))
        self.device.dispatch.assert_not_called()

    def test_invalid_firmware_or_restore_cannot_start_device(self):
        with self.assertRaises(ValueError):self.service.inspect(dict(action='inspect',raw='not base64'))
        with self.assertRaises(ValueError):self.service.start(dict(action='install',inspection='missing',confirmation='yes'))
        with self.assertRaises(ValueError):self.service.start(dict(action='device',request=dict(action='restore_all',backup={})))
        self.device.dispatch.assert_not_called()


class HelpTests(unittest.TestCase):
    def test_documented_midi_examples_match_wire_encoder(self):
        # Exercise copy/paste handbook messages against the production encoder.
        # This catches decimal/hex confusion, wrong byte order and wrong opcodes.
        from fm1_704_bench import parameter_packet
        from fm1_session import controls_request
        page=help_builder.build()['midi.htm']
        examples=re.findall(r'<code>(F0 [0-9A-F ]+ F7)</code>',page)
        expected=[parameter_packet(i,v,parameter_count=198,fx=True,workstation=True,
                                  projects=True,sync=True,polish=True)
                  for i,v in ((162,1000),(146,60),(134,4))]
        expected.append(controls_request(162,count=198))
        self.assertEqual([bytes.fromhex(x) for x in examples],expected)

    def test_complete_canonical_coverage_and_all_local_links(self):
        files=help_builder.build();coverage=json.loads(files['coverage.json'])
        self.assertEqual({p['id'] for p in coverage['parameters']},set(range(198)))
        self.assertEqual(coverage['panel_pages'],45)  # 731 adds the explicit USB link page.
        for name,content in files.items():
            if not name.endswith('.htm'):continue
            for href in re.findall(r'href=[\"\']([^\"\']+)',content):
                if href=='/':continue
                target,_,anchor=href.partition('#')
                if target.endswith(('.png','.svg')):
                    self.assertTrue((help_builder.R/'host/help'/target).is_file(),(name,href));continue
                self.assertIn(target,files,(name,href))
                if anchor:self.assertIn('id="'+anchor+'"',files[target])
        self.assertIn('OP1 Output level',files['search.js']);self.assertNotIn('fetch(',files['search.js'])
    def test_generated_files_are_current(self):
        for name,content in help_builder.build().items():
            self.assertEqual((help_builder.R/'host/help'/name).read_text(encoding='utf8'),content,name)


if __name__=='__main__':unittest.main()
