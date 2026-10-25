"""Observable profile persistence and install orchestration contracts; no hardware."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import companion_loadouts as profiles
import companion_install_loadout as install
import companion_jobs as jobs
import companion_device as device
import companion_archive as archive
import library
from tests.test_companion import fixture
from tests.test_companion_product import unit_backup

class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=profiles.Profiles(Path(self.temp.name),Path('unused'),[fixture(i%2) for i in range(64)])
    def call(self,action,**kw):return self.store.dispatch(dict(action=action,revision=self.store.snapshot()['revision'],**kw))
    def test_included_complete_and_custom_snapshot_independent_with_undo(self):
        initial=self.store.snapshot();self.assertEqual(len(initial['included']),5);self.assertEqual(len(initial['sounds']),192)
        self.assertFalse(self.store.path.exists())
        original=copy.deepcopy(initial['included'][0]);self.call('copy',id='A',title='My night set')
        p=self.store.snapshot()['slots'][0];p['slots'][0],p['slots'][63]=p['slots'][63],p['slots'][0]
        self.call('save',profile=p);self.assertEqual(self.store.get(p['id']),p);self.assertEqual(self.store.get('A'),original)
        self.call('undo');self.assertEqual(self.store.get(p['id'])['slots'],original['slots'])
        reopened=profiles.Profiles(Path(self.temp.name),Path('unused'),[fixture()]*64)
        self.assertEqual(reopened.get(p['id'])['title'],'My night set')
    def test_export_import_rename_delete_restore_and_checksum(self):
        exported=self.store.dispatch(dict(action='export',id='B'))
        self.call('import',file=exported);p=self.store.snapshot()['slots'][0];p['title']='Gig'
        self.call('save',profile=p);saved=self.store.path.read_bytes()
        bad=copy.deepcopy(exported);bad['payload']['slots'][0]['entry']['name']='MISMATCH'
        with self.assertRaises(ValueError):self.call('import',file=bad)
        self.assertEqual(saved,self.store.path.read_bytes())
        self.call('delete',id=p['id'],confirmation='Delete profile');self.assertFalse(self.store.snapshot()['slots'])
        self.call('undo');self.assertEqual(self.store.get(p['id'])['title'],'Gig')
    def test_conflicts_incomplete_builtin_edit_and_capacity_do_not_modify(self):
        self.call('copy',id='A',title='A copy');saved=self.store.path.read_bytes()
        with self.assertRaises(library.LibraryConflict):self.store.dispatch(dict(action='delete',revision=0,id=self.store.snapshot()['slots'][0]['id'],confirmation='Delete profile'))
        with self.assertRaises(ValueError):self.call('save',profile=self.store.get('A'))
        p=self.store.snapshot()['slots'][0];p['slots'].pop()
        with self.assertRaises(ValueError):self.call('save',profile=p)
        with patch.object(profiles,'CAPACITY',1),self.assertRaises(ValueError):self.call('copy',id='B',title='Too many')
        self.assertEqual(saved,self.store.path.read_bytes())
    def test_bank_mapping_exact_copies_and_corrupt_last_slot_rejected(self):
        envelope=self.store.dispatch(dict(action='export',id='C'))
        for target,slots in [('default',range(64,128)),('user',range(64)),('both',list(range(64,128))+list(range(64)))]:
            result=profiles.deployment(dict(profile=envelope,bank=target))
            self.assertEqual([r['slot'] for r in result['rows']],list(slots))
            self.assertEqual([r['entry'] for r in result['rows'][:64]],[s['entry'] for s in envelope['payload']['slots']])
        bad=copy.deepcopy(envelope);bad['payload']['slots'][-1]['entry']['native']='AAAA'
        bad['sha256']=__import__('hashlib').sha256(library.canonical(bad['payload'])).hexdigest()
        with self.assertRaises(ValueError):profiles.deployment(dict(profile=bad,bank='both'))
    def test_independent_default_and_user_profiles_preserve_exact_order(self):
        a=self.store.dispatch(dict(action='export',id='A'));b=self.store.dispatch(dict(action='export',id='B'))
        plan=profiles.bank_assignment(dict(default=a,user=b))
        self.assertEqual(len(plan['rows']),128)
        self.assertEqual([r['entry'] for r in plan['rows'][:64]],[s['entry'] for s in a['payload']['slots']])
        self.assertEqual([r['entry'] for r in plan['rows'][64:]],[s['entry'] for s in b['payload']['slots']])
        self.assertTrue(any(a['entry'] != b['entry'] for a,b in zip(plan['rows'][:64],plan['rows'][64:])))
        user=profiles.bank_assignment(dict(default=None,user=b))
        self.assertEqual([r['slot'] for r in user['rows']],list(range(64)))
        with self.assertRaises(ValueError):profiles.bank_assignment(dict(default=None,user=None))

class InstallTests(unittest.TestCase):
    def test_changed_inherited_sounds_are_preserved_except_explicit_destinations(self):
        before=unit_backup();after=copy.deepcopy(before)
        old=before['payload']['instruments'][0]
        replacement=copy.deepcopy(fixture());state=profiles.bank.decode_record(replacement['native'])
        state['controls'][162]=1234;replacement['native']=profiles.bank.pack(state)
        after['payload']['instruments'][0]=replacement['native']
        after['payload']['instruments'][64]=replacement['native']
        rows=install.preserved_rows(before,after,[dict(kind='instrument',slot=64)])
        self.assertEqual([r['slot'] for r in rows],[0])
        self.assertEqual(profiles.bank.decode_record(rows[0]['entry']['native']),profiles.bank.decode_record(old))
        self.assertEqual(install.preserved_rows(None,after,[]),[])

    def test_generation_only_changes_do_not_rewrite_instruments(self):
        before=unit_backup();after=copy.deepcopy(before)
        state=profiles.bank.decode_record(before['payload']['instruments'][0])
        state['source_generation']+=1
        after['payload']['instruments'][0]=profiles.bank.pack(state)
        self.assertEqual(install.preserved_rows(before,after,[]),[])

    def test_native12_downgrade_is_rejected_before_flash(self):
        with patch.object(install.unit_endpoints,'annotate',return_value=self.rows),patch.object(install.flash,'find_session',return_value=self.session),patch.object(install.flash,'perform_update') as flash:
            with self.assertRaisesRegex(ValueError,'native12'):
                install.run(self.api,Mock(report={'product':'FM-1_734'}),Mock(),None,self.root,Mock(),Mock())
            flash.assert_not_called()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.profile=profiles.seal(dict(id='test',title='Stage',description='',slots=[profiles.sound(fixture(i%2)) for i in range(64)]))
        self.request=dict(default=self.profile,user=None);self.request['confirmation']=profiles.bank_assignment(self.request)['plan']['confirmation']
        self.api=Mock();self.session=Mock(verified_identity='FM-1_735');self.session.close.return_value=[]
        self.rows={'inputs':[dict(id=0,name='FMER',location_paths=['PCIROOT(0)#PCI(1400)#USBROOT(0)#USB(4)'],interface_sha256='a')],
                   'outputs':[dict(id=0,name='FMER',location_paths=['PCIROOT(0)#PCI(1400)#USBROOT(0)#USB(4)'],interface_sha256='a')]}
    def exercise(self,fail=None,stock=False):
        events=[];checkpoints=[];backup=unit_backup();backup['payload']['identity']='FM-1_734';backup=archive.seal(backup['payload'])
        first=Mock(verified_identity='FM-1_015' if stock else 'FM-1_734');first.close.return_value=[]
        def capture(*a):
            events.append('backup')
            if fail=='backup':raise RuntimeError('read interrupted')
            return backup
        def flash(*a):events.append('flash')
        def deploy(client,rows,directory,progress,journal,result):
            self.assertTrue(Path(result['backup_path']).is_file());self.assertEqual([r['slot'] for r in rows],list(range(64,128)))
            events.append('deploy');result['completed']=[dict(kind='instrument',slot=64)]
            if fail=='deploy':raise RuntimeError('write interrupted')
        client=Mock();client.store_status.return_value=dict(ready=1,busy=0)
        with patch.object(install.unit_endpoints,'annotate',return_value=self.rows),patch.object(install.flash,'find_session',side_effect=[first,self.session]),patch.object(install.flash,'perform_update',side_effect=flash),patch.object(install.archive,'capture',side_effect=capture),patch.object(device,'native_client',return_value=client),patch.object(install.companion_transfer,'deploy',side_effect=deploy):
            try:result=install.run(self.api,Mock(report={'product':'FM-1_735'}),Mock(),self.request,self.root,Mock(),lambda r:checkpoints.append(copy.deepcopy(r)))
            except RuntimeError:
                if not fail:raise
                result=None
        return events,checkpoints,result
    def test_reflash_backs_up_before_firmware_and_again_before_bank_write(self):
        events,checkpoints,result=self.exercise()
        self.assertEqual(events,['backup','flash','backup','deploy']);self.assertTrue(result['loadout_complete'])
        self.assertTrue(result['firmware_installed']);self.assertTrue(checkpoints[0]['backup_path'])
        self.assertEqual(self.api.target_location,self.rows['inputs'][0]['location_paths'][0])
    def test_stock_first_install_skips_unsupported_backup_and_captures_initialized_banks(self):
        events,checkpoints,result=self.exercise(stock=True)
        self.assertEqual(events,['flash','backup','deploy']);self.assertIn('pre_install_backup_unavailable',result)
    def test_failed_backup_prevents_flash_and_partial_bank_failure_retains_phase(self):
        events,_,result=self.exercise(fail='backup');self.assertEqual(events,['backup']);self.assertIsNone(result)
        events,checkpoints,result=self.exercise(fail='deploy');self.assertIsNone(result)
        self.assertTrue(checkpoints[-1]['firmware_installed']);self.assertFalse(checkpoints[-1]['loadout_complete'])
        self.assertEqual(len(checkpoints[-1]['completed']),1)
    def test_job_refuses_unreviewed_or_non_fmer_loadout_before_worker(self):
        service=jobs.Jobs(Mock(),self.root);service.packages['t']=(Path('unused'),dict(product='FM-1_734',installable=True,compatible_profile='custom'))
        request=dict(action='install',inspection='t',confirmation='Install FM-1_734',loadout=self.request)
        with patch.object(jobs.threading,'Thread') as worker:
            with self.assertRaises(ValueError):service.start(request)
            service.packages['t'][1]['release_profile']='fm1-compatible-to-734-r3'
            request['loadout']={**self.request,'confirmation':'wrong'}
            with self.assertRaises(ValueError):service.start(request)
            worker.assert_not_called()

if __name__=='__main__':unittest.main()
