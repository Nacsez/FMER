"""Release-candidate companion contracts; isolated storage, no physical MIDI."""
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import companion_transfer as transfer
import companion_device as device
import compatible_firmware as compatible
import fm1_package as package
import fm1_flash_transport as transport
import release_firmware as release
import companion_shelf as shelf
import companion_bank as bank
from tests.test_companion import fixture


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.rows=[dict(kind='instrument',slot=n,entry=fixture(n)) for n in (0,1)]

    def test_review_binds_bytes_and_destinations_and_refuses_collisions(self):
        plan=transfer.plan(self.rows)
        self.assertEqual([r['destination'] for r in plan['rows']],['USER 00','USER 01'])
        changed=deepcopy(self.rows);changed[1]['slot']=64
        self.assertNotEqual(plan['confirmation'],transfer.plan(changed)['confirmation'])
        changed[1]['slot']=0
        with self.assertRaisesRegex(ValueError,'same destination'):transfer.plan(changed)
        changed[1]['slot']=128
        with self.assertRaises(ValueError):transfer.plan(changed)

    def test_invalid_last_record_and_wrong_confirmation_open_no_device(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(device.hardware_bridge,'WinMM') as midi:
            service=device.Device(Path('unused'),Path(tmp))
            for rows,confirmation in ((self.rows,'Deploy wrong'),([self.rows[0],{**self.rows[1],'entry':{}}],'anything')):
                with self.assertRaises(ValueError):
                    service.dispatch(dict(action='deploy_library',rows=rows,confirmation=confirmation))
            midi.assert_not_called()

    def test_complete_backup_precedes_all_writes_and_working_state_restored(self):
        with tempfile.TemporaryDirectory() as tmp:
            service=device.Device(Path('unused'),Path(tmp))
            session=Mock();session.verified_identity=device.bridge.IDENTITY;session.close.return_value=[]
            client=Mock();wire=bank.native.encode(bank.decode_record(self.rows[0]['entry']['native']))
            client.restore.return_value=dict(verified=True)
            client.push_slot.return_value=dict(verified=True)
            snapshot=dict(payload=dict(live=base64.b64encode(wire).decode()))
            def write(raw,slot,directory):
                paths=list(Path(tmp).glob('device-logs/*/unit-backup.fmer-backup.json'))
                self.assertEqual(len(paths),1)
                self.assertEqual(json.loads(paths[0].read_text()),snapshot)
            client.push_slot.side_effect=write
            with patch.object(device.hardware_bridge,'WinMM'),patch.object(device.bridge.transport,'find_session',return_value=session),patch.object(device.bridge,'NativeBridge',return_value=client),patch.object(device.archive,'capture',return_value=snapshot):
                result=service.dispatch(dict(action='deploy_library',rows=self.rows,confirmation=transfer.plan(self.rows)['confirmation']))
            self.assertEqual([r['slot'] for r in result['completed']],[0,1])
            self.assertEqual(client.restore.call_args.args[0],wire)
            self.assertEqual(client.push_slot.call_count,2);session.close.assert_called_once()

    def test_interruption_reports_partial_writes_no_retry_and_attempts_restore(self):
        client=Mock();client.push_slot.side_effect=[{},RuntimeError('Disconnected')]
        result=dict(backup=dict(payload=dict(live=self.rows[0]['entry']['native'])),backup_path='saved.json')
        with self.assertRaisesRegex(RuntimeError,'1/2 verified'):
            transfer.deploy(client,self.rows,Path('unused'),Mock(),Mock(),result)
        self.assertEqual([r['slot'] for r in result['completed']],[0])
        self.assertEqual(client.push_slot.call_count,2);client.restore.assert_called_once()

    def test_sounds_written_before_project_and_restore_failure_is_not_success(self):
        rows=[dict(kind='project',slot=0,entry=fixture()),*self.rows]
        client=Mock();calls=[]
        client.push_slot.side_effect=lambda raw,slot,path:calls.append(('sound',slot))
        client.push_project.side_effect=lambda raw,slot,path:calls.append(('project',slot))
        client.restore.side_effect=RuntimeError('No response')
        result=dict(backup=dict(payload=dict(live=self.rows[0]['entry']['native'])),backup_path='saved.json')
        with self.assertRaisesRegex(RuntimeError,'working state could not'):
            transfer.deploy(client,rows,Path('unused'),Mock(),Mock(),result)
        self.assertEqual(calls,[('sound',0),('sound',1),('project',0)])

    def test_bank_pack_import_preserves_both_engines_and_has_one_undo(self):
        entries=[fixture(i%2) for i in range(128)]
        converted=shelf.from_banks(dict(slots=entries))
        with tempfile.TemporaryDirectory() as tmp:
            store=shelf.Catalog(Path(tmp),Path('unused'))
            store.dispatch(dict(action='import',revision=0,backup=converted))
            self.assertEqual([i['entry'] for i in store.snapshot()['slots']],entries)
            store.dispatch(dict(action='undo',revision=1))
            self.assertEqual(store.snapshot()['slots'],[])

    def test_failed_job_backup_download_is_bounded_and_validated(self):
        from companion_jobs import Jobs
        from tests.test_companion_product import unit_backup
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);service=Jobs(device.Device(Path('unused'),root),root/'operations')
            path=root/'device-logs/run/unit-backup.fmer-backup.json';path.parent.mkdir(parents=True)
            saved=unit_backup();path.write_text(json.dumps(saved))
            with patch.object(service,'status',return_value=dict(progress=dict(backup_path=str(path)))):
                self.assertEqual(service.backup('ignored-by-fake-status'),saved)
                path.write_text('{}')
                with self.assertRaises(ValueError):service.backup('ignored-by-fake-status')
            with patch.object(service,'status',return_value=dict(progress=dict(backup_path=str(root/'outside.json')))):
                with self.assertRaisesRegex(ValueError,'outside'):service.backup('ignored-by-fake-status')


class CompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=release.ROOT/'firmware/releases'/release.catalog()[0]['filename'] if release.catalog() else None
        if not path or not path.is_file():raise unittest.SkipTest('Release binary not present in source-only tree')
        cls.raw=release.bundled(release.PROFILE)
        _,_,cls.files=package.decode_package(cls.raw)
        cls.region,cls.layout=package.app_layout(cls.files['flash.bin']['payload'][0x4000:],package.TEST01_APP_SLOT)

    def make(self,*,identity='FM-1_735',metadata=False,head=False):
        region=bytearray(self.region)
        start,end=0x120,0x120+package.TEST01_APP_SLOT
        region[start:end]=region[start:end].replace(b'FM-1_734\0',identity.encode()+b'\0')
        if metadata:region[224]^=1
        struct.pack_into('<H',region,34,package.crc16(region[start:end]))
        struct.pack_into('<H',region,32,package.crc16(region[34:64]))
        struct.pack_into('<H',region,2,package.crc16(region[32:self.layout['area_bytes']]))
        struct.pack_into('<H',region,0,package.crc16(region[2:32]))
        package.sfc(region,0,len(region),0,package.KEY)
        prefix=bytearray(release.distribution_head())
        if head:prefix[200]^=1
        return package.ufw(bytes(prefix)+region,self.files['ota.bin']['payload'],identity)

    def test_different_application_same_loader_and_layout_qualifies_without_private_dump(self):
        raw=self.make()
        with patch.object(package,'validate_package',side_effect=AssertionError('No private evidence needed')):
            report=compatible.inspect_bytes(raw)
            self.assertFalse(report['hardware_qualified'])
            self.assertEqual(report['product'],'FM-1_735')
            with tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/'custom.fwsc';path.write_bytes(raw)
                qualified=transport.qualify_package(path,hashlib.sha256(raw).hexdigest(),report['loader_sha256'])
                self.assertEqual(transport.update_identities(qualified),('compatible-FM-1','ota-FM-1_935','FM-1_735'))
                qualified.report['record_address']=0xE4F00
                with self.assertRaises(ValueError):transport.update_identities(qualified)

    def test_boot_metadata_and_invalid_crc_refused(self):
        for kwargs in (dict(head=True),dict(metadata=True)):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):compatible.inspect_bytes(self.make(**kwargs))
        raw=bytearray(self.make());raw[5000]^=1
        with self.assertRaises(ValueError):compatible.inspect_bytes(raw)

    def test_an_unknown_updater_never_receives_an_install_token(self):
        from companion_jobs import Jobs
        loader=bytearray(package.validate_loader(self.files['ota.bin']['payload']))
        loader[-1]^=1
        raw=package.ufw(self.files['flash.bin']['payload'],package.loader_wrap(bytes(loader)),'FM-1_734')
        with self.assertRaisesRegex(ValueError,'different updater'):
            compatible.inspect_bytes(raw)
        with tempfile.TemporaryDirectory() as tmp:
            jobs=Jobs(Mock(),Path(tmp))
            report=jobs.inspect(dict(action='inspect',raw=base64.b64encode(raw).decode()))
            self.assertFalse(report['installable']);self.assertNotIn('inspection',report)
            self.assertEqual(jobs.packages,{})

    def test_custom_report_reconstruction_rejects_modified_application(self):
        raw=self.make();report=compatible.inspect_bytes(raw)
        _,image,_=package.decode_package(raw,compatible_identity=True)
        image=bytearray(image);image[20000]^=1
        offset=report['files']['flash.bin']['offset']
        qualified=transport.QualifiedPackage(bytes(image),report,offset+0x4000,offset+0x93000)
        with self.assertRaises(ValueError):compatible.update_identities(qualified)


if __name__=='__main__':unittest.main()
