# SPDX-License-Identifier: GPL-3.0-only
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import os
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import companion_community as community
import companion_soundpacks as packs
import companion_shelf as shelf
import companion_bank as bank
import library
import fm1_stock_catalog as stock
import extract_oem_v15
from tests.test_companion_dx7 import state

ROOT=Path(__file__).resolve().parents[1]


def info(family='Felucca'):
    version={'Felucca':b'FELUCCA v1.6.1','SLOOP':b'FELUCCA SLOOP 2.7.1','JIANT':b'JIANT 0.9.17'}[family]
    return version+b'\0'+bytes([1,111,20,64,103])+b'FM6\0\4'+(bytes([12]) if family=='SLOOP' else b'\x10\x46\x01\x08\0\x50\x01\3')


class FakeReader:
    def __init__(self,family='Felucca'):
        self.family=family;self.sent=[]
        self.voice=bytes(json.loads((ROOT/'third_party/oem_v15/voices.json').read_text())['voices'][0])
    def request(self,cmd,args=b''):
        self.sent.append((cmd,args))
        if cmd==1:return info(self.family)
        if cmd==70:return bytes([8,27 if self.family=='SLOOP' else 0])+b'\1PIANO 1\0'*8+(b'\0\0'*27 if self.family=='SLOOP' else b'')
        if cmd==68:return args+(b'\2' if args[0]==3 else b'\0'+self.voice)
        raise AssertionError('Unexpected write command')


class CommunityTests(unittest.TestCase):
    def test_family_and_capabilities_not_common_version_alone(self):
        for family in ('Felucca','SLOOP','JIANT'):self.assertEqual(community.info(info(family))['family'],family)
        with self.assertRaises(ValueError):community.info(info().replace(b'FELUCCA',b'UNKNOWN'))
        with self.assertRaises(ValueError):community.info(info().replace(b'FM6',b'ABC'))
        with self.assertRaises(ValueError):community.capture(FakeReader('SLOOP'),'FM-1_916')

    def test_capture_only_reads_and_preserves_slots(self):
        for family in ('Felucca','SLOOP','JIANT'):
            reader=FakeReader(family)
            result=community.capture(reader,'FM-1_916' if family=='Felucca' else 'FM-1_900')
            self.assertEqual(len(result['payload']['voices']),11 if family=='SLOOP' else 12)
            self.assertEqual(set(cmd for cmd,args in reader.sent),{1,68,70})
            self.assertEqual(result['sha256'],hashlib.sha256(library.canonical(result['payload'])).hexdigest())

    def test_malformed_or_changing_response_does_not_complete(self):
        for broken in ('short','range','change','slot'):
            reader=FakeReader();original=reader.request;count=[0]
            def request(cmd,args=b''):
                value=original(cmd,args)
                if cmd==68:
                    count[0]+=1
                    if broken=='short':return value[:-1]
                    if broken=='range':return value[:3]+bytes([127])+value[4:]
                    if broken=='slot':return b'\0\0'+value[2:]
                    if broken=='change' and count[0]%2==0:return value[:-1]+b'!'
                return value
            reader.request=request
            with self.subTest(broken=broken),self.assertRaises(ValueError):community.capture(reader,'FM-1_916')

    def test_reader_cannot_send_write_or_select_commands(self):
        class Session:
            def _send(self,*a):raise AssertionError('Must not emit')
        for cmd,args in ((69,b'\0\0'),(8,b'\0\0'),(65,b''),(68,b'\4\0'),(1,b'\0')):
            with self.assertRaises(ValueError):community.Reader(Session()).request(cmd,args)

    def test_wire_reader_ignores_pushes_and_checks_returned_slot(self):
        class Session:
            def __init__(self):self.sent=[];self.frames=[community.PREFIX+b'\x17\0\xf7',community.PREFIX+b'\x44\2\0\2\xf7']
            def _send(self,raw,purpose):self.sent.append(raw)
            def read(self,timeout):return self.frames.pop(0) if self.frames else None
        session=Session();reader=community.Reader(session)
        self.assertEqual(reader.request(68,b'\2\0'),b'\2\0\2')
        self.assertEqual(session.sent,[b'\xf0\x7dFL\x44\2\0\xf7'])
        session.frames=[community.PREFIX+b'\x44\2\1\2\xf7']
        with self.assertRaisesRegex(ValueError,'different slot'):reader.request(68,b'\2\0')

    def test_oem_source_coverage_and_reported_normalization(self):
        data=json.loads((ROOT/'third_party/oem_v15/voices.json').read_text())
        self.assertEqual(len(data['voices']),128)
        self.assertEqual(hashlib.sha256(b''.join(bytes(v) for v in data['voices'])).hexdigest(),data['bank_sha256'])
        changes=[i+1 for i,v in enumerate(data['voices']) if stock.normalize(stock.unpack_voice(bytes(v)))[1]]
        self.assertEqual(changes,[23,36,47,77,85,110,115,116,117,120,124])
        with self.assertRaises(ValueError):extract_oem_v15.extract(b'wrong publisher file')

    def test_archive_corruption_or_duplicate_source_refused(self):
        archive=community.capture(FakeReader(),'FM-1_916');archive['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'checksum'):community.decode(archive,[],None)


@unittest.skipUnless(os.environ.get('FMER_HOST_EXE'),'Set FMER_HOST_EXE for the compiled FM codec')
class ActualPackTests(unittest.TestCase):
    def test_complete_oem_catalog_native_fields_and_undo(self):
        exe=Path(os.environ['FMER_HOST_EXE']);defaults=bank.profile(exe)
        result=packs.prepare('oem-v15',defaults,library.PatchCodec(exe,lambda *a,**k:None))
        original=json.loads((ROOT/'third_party/oem_v15/voices.json').read_text())['voices']
        for item,packed in zip(result['catalog']['payload']['slots'],original):
            self.assertEqual(bank.decode_record(item['entry']['native'])['vced'],stock.normalize(stock.unpack_voice(bytes(packed)))[0])
        with tempfile.TemporaryDirectory() as d:
            cat=shelf.Catalog(Path(d),exe)
            after=cat.dispatch(dict(action='import',revision=0,backup=result['catalog']))
            self.assertEqual(len(after['slots']),128)
            self.assertEqual(cat.dispatch(dict(action='undo',revision=after['revision']))['slots'],[])

    def test_community_capture_import_preserves_packed_fm_voice(self):
        exe=Path(os.environ['FMER_HOST_EXE']);defaults=bank.profile(exe)
        reader=FakeReader('SLOOP');raw=community.capture(reader,'FM-1_900')
        result=community.decode(raw,defaults,library.PatchCodec(exe,lambda *a,**k:None))
        self.assertEqual(result['count'],11)
        for item in result['catalog']['payload']['slots']:
            self.assertEqual(bank.decode_record(item['entry']['native'])['vced'],stock.unpack_voice(reader.voice))


if __name__=='__main__':unittest.main()
