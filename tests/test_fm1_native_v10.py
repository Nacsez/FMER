import base64
from copy import deepcopy
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from tests.test_companion import fixture
import companion_bank
import fm1_native_state_v10 as native


class Native10Tests(unittest.TestCase):
    def state(self):
        state=companion_bank.native._legacy(companion_bank.decode_record(fixture()['native']))
        for t,lane in enumerate(state['song']):
            lane.update(enabled=True,loop=bool(t%2),length=32)
            for r,row in enumerate(lane['entries']):
                row.update(pattern=r%17,transpose=(r+t)%49-24,repeats=r+1)
        return state

    def test_complete_song_and_sound_scope(self):
        state=self.state();raw=native.encode(state)
        self.assertEqual(len(raw),4000);self.assertEqual(native.decode(raw),state)
        self.assertEqual(native.canonical_sound(state)['song'],native.empty_song())
        sound=native.canonical_sound(state);sound['controls'][162]=1234
        merged=native.merge_sound(sound,state)
        self.assertEqual(merged['song'],state['song']);self.assertEqual(merged['controls'][162],1234)
        old=native.v9.encode(native._legacy(state))
        upgraded=native.decode_compatible(old)
        self.assertEqual(upgraded['song'],native.empty_song())
        self.assertEqual(native.v9.encode(native._legacy(upgraded)),old)

    def test_invalid_wire_and_state_are_rejected(self):
        raw=bytearray(native.encode(self.state()))
        for offset,value in ((3728,33),(3732,2),(3740,1),(3744,31)):
            bad=bytearray(raw);bad[offset]=value;struct.pack_into('<I',bad,28,native.record_crc(bad))
            with self.assertRaises(ValueError):native.decode(bad)
        for field,value in (('pattern',17),('transpose',25),('repeats',0),('repeats',33)):
            state=self.state();state['song'][0]['entries'][0][field]=value
            with self.assertRaises(ValueError):native.encode(state)

    def test_cpp_and_compact_journal_migration_match(self):
        root=Path(__file__).resolve().parents[1]
        codec=root/'artifacts/build/host/Release/fm1_native_state_tests.exe'
        bank=root/'artifacts/build/host/Release/fm1_bank_store_tests.exe'
        if not codec.exists() or not bank.exists():self.skipTest('Build current probes first')
        state=self.state();new=native.encode(state);old=native.v9.encode(native._legacy(state))
        with tempfile.TemporaryDirectory() as tmp:
            for raw in (old,new):
                source=Path(tmp)/'input';source.write_bytes(raw)
                for exe,command in ((codec,'--roundtrip'),(bank,'--migrate')):
                    out=Path(tmp)/'output'
                    result=subprocess.run([str(exe),command,str(source),str(out)],capture_output=True,timeout=10)
                    self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                    self.assertEqual(out.read_bytes(),companion_bank.native.encode(companion_bank.native.decode_compatible(raw)))

    def test_transfer_tail_is_not_truncated(self):
        raw=native.encode(self.state())
        for at in (3712,3776,3968):
            chunk=raw[at:at+64]
            self.assertIn(bytes([len(chunk)]),native.write_chunk_request(1,at,chunk))
            frame=native.PREFIX+bytes([15])+' '.join(map(str,[1,at,len(chunk),*chunk])).encode()+bytes([247])
            self.assertEqual(native.parse_chunk(frame,token=1,offset=at),chunk)
            with self.assertRaises(ValueError):native.parse_chunk(frame,token=2,offset=at)
            self.assertTrue(native.chunk_request(1,at).endswith(bytes([247])))
        with self.assertRaises(ValueError):native.chunk_request(1,4000)


if __name__=='__main__':unittest.main()
