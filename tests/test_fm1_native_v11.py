"""Current recipes survive wire, journal and companion migrations."""
import struct,subprocess,tempfile,unittest
from pathlib import Path
from tests.test_companion import fixture
import companion_bank as bank
import fm1_native_state_v11 as native

class Native11Tests(unittest.TestCase):
    def test_recipes_roundtrip_and_migrate(self):
        state=bank.native._legacy(bank.decode_record(fixture()['native']));state['modulation_profiles']=[3,2]
        raw=native.encode(state)
        self.assertEqual(len(raw),4000);self.assertEqual(native.decode(raw),state)
        old=native.v10.encode(native._legacy(state))
        self.assertEqual(native.decode_compatible(old)['modulation_profiles'],[0,0])
        with tempfile.TemporaryDirectory() as tmp:
            for data in (raw,old):
                source=Path(tmp)/'in';source.write_bytes(data)
                for exe,cmd in (('fm1_native_state_tests','--roundtrip'),('fm1_bank_store_tests','--migrate')):
                    path=Path('artifacts/build/host/Release')/(exe+'.exe')
                    if not path.exists():self.skipTest('Build probes first')
                    out=Path(tmp)/'out';r=subprocess.run([str(path),cmd,str(source),str(out)],capture_output=True,timeout=10)
                    self.assertEqual(r.returncode,0,r.stdout+r.stderr)
                    self.assertEqual(out.read_bytes(),bank.native.encode(bank.native.decode_compatible(data)))
        bad=bytearray(raw);bad[3709]=4;struct.pack_into('<I',bad,28,native.record_crc(bad))
        with self.assertRaises(ValueError):native.decode(bad)

    def test_sound_recall_preserves_single_playing_mode(self):
        state=bank.native._legacy(bank.decode_record(fixture()['native']));state['controls'][150:153]=[1,350,2];state['controls'][191]=1
        sound=native.canonical_sound(state);sound['controls'][150:153]=[0,150,0]
        merged=native.merge_sound(sound,state)
        self.assertEqual(merged['controls'][150:153],[1,350,2]);self.assertEqual(merged['controls'][191],1)

if __name__=='__main__':unittest.main()
