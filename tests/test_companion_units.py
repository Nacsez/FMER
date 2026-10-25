"""Independent named setups, stale writes and explicit hardware-label boundary."""
import tempfile,unittest,copy
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from unittest.mock import Mock,patch
import companion_units as units,companion_jobs as jobs,library

class UnitProfilesTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.loadouts=Mock()
        self.loadouts.get.side_effect=lambda id:dict(id=id)
        self.loadouts.dispatch.side_effect=lambda r:dict(profile=r['id'])
        self.store=units.Units(self.root,Path('unused'),self.loadouts)
    def save(self,name,a='A',b='B'):
        return self.store.dispatch(dict(action='save',revision=self.store.snapshot()['revision'],profile=dict(id='new',name=name,notes='',collection=name,default=a,user=b)))
    def test_independent_assignments_rename_restart_and_undo(self):
        self.save('Malachite');self.save('Citrine','C','D')
        before=self.store.snapshot();a,b=before['slots'];changed=copy.deepcopy(a);changed.update(name='Studio',default='D')
        self.store.dispatch(dict(action='save',revision=before['revision'],profile=changed))
        self.assertEqual(self.store.get(b['id']),b)
        self.assertEqual(self.store.assignments(a['id']),dict(default=dict(profile='D'),user=dict(profile='B')))
        self.assertEqual(units.Units(self.root,Path('unused'),self.loadouts).get(a['id'])['name'],'Studio')
        self.store.dispatch(dict(action='undo',revision=self.store.snapshot()['revision']))
        self.assertEqual(self.store.get(a['id']),a)
    def test_duplicate_names_missing_loadouts_and_stale_revisions_refused(self):
        self.save('Malachite');original=self.store.path.read_bytes()
        with self.assertRaisesRegex(ValueError,'unique'):self.save('MALACHITE')
        self.assertEqual(self.store.path.read_bytes(),original)
        row=self.store.snapshot()['slots'][0]
        with self.assertRaises(library.LibraryConflict):self.store.dispatch(dict(action='save',revision=0,profile=row))
        self.loadouts.get.side_effect=ValueError('missing')
        with self.assertRaisesRegex(ValueError,'missing'):self.save('Citrine','gone')
        self.assertEqual(self.store.path.read_bytes(),original)
    def test_delete_only_local_profile_and_job_captures_label_without_identity_claim(self):
        row=self.save('Amethyst')['slots'][0]
        service=jobs.Jobs(Mock(),self.root/'jobs');service.units=self.store
        with patch.object(jobs.threading,'Thread'):
            record=service.start(dict(action='device',request=dict(action='backup_all'),unit_profile=row['id']))
        self.assertEqual(record['unit_profile'],dict(id=row['id'],name='Amethyst',hardware_identity_verified=False))
        self.store.dispatch(dict(action='delete',revision=1,id=row['id'],confirmation='Delete unit profile'))
        self.assertEqual(self.store.snapshot()['slots'],[])
        self.assertEqual(record['unit_profile']['name'],'Amethyst')
        self.loadouts.dispatch.assert_not_called()

if __name__=='__main__':unittest.main()
