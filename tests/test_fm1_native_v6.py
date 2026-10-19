"""Native721 mixer flags and lossless migration; no device access."""
import copy
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from tests.test_fm1_native_v5 import fixture as old_fixture
import fm1_native_state_v5 as old
import fm1_native_state_v6 as native

def fixture():return native.decode_compatible(old.encode(old_fixture()))

class NativeV6Tests(unittest.TestCase):
    def test_preserves_complete_old_song_without_storage_growth(self):
        before=old_fixture();raw=old.encode(before);after=native.decode_compatible(raw)
        self.assertEqual(after['controls'],before['controls']);self.assertEqual(after['patterns'],before['patterns'])
        self.assertEqual(after['vced'],before['vced'])
        for a,b in zip(after['tracks'],before['tracks']):self.assertEqual(a,dict(b,solo=0,fx_bypass=0))
        self.assertEqual(len(native.encode(after)),len(raw));self.assertEqual(raw,old.encode(before))

    def test_all_mute_solo_and_fx_flag_combinations_roundtrip(self):
        for flags in range(8):
            state=fixture();state['tracks'][2].update(mute=flags&1,solo=(flags>>1)&1,fx_bypass=(flags>>2)&1)
            if state['controls'][154]==2:state['controls'][157]=flags&1
            raw=native.encode(state);self.assertEqual(raw[:8],b'FMERNAT6');self.assertEqual(raw[3671:3675],b'TRK3')
            self.assertEqual(raw[3675+6*2+5],flags);self.assertEqual(native.decode(raw),state)
            self.assertEqual(raw[3699:],bytes(29))

    def test_unknown_flags_rejected_even_with_valid_crc(self):
        raw=bytearray(native.encode(fixture()));raw[3680]=8
        struct.pack_into('<I',raw,28,native.record_crc(raw))
        with self.assertRaises(native.NativeStateError):native.decode(raw)
        state=fixture();state['tracks'][0]['solo']=2
        with self.assertRaises(native.NativeStateError):native.encode(state)

    def test_sound_projection_does_not_leak_solo_or_bypass_into_instruments(self):
        state=fixture();state['tracks'][1].update(solo=1,fx_bypass=1)
        sound=native.canonical_sound(state)
        self.assertTrue(all(not t['solo'] and not t['fx_bypass'] for t in sound['tracks']))
        restored=native.merge_sound(sound,state)
        self.assertEqual(restored['tracks'],state['tracks']);self.assertEqual(restored['patterns'],state['patterns'])

    def test_current_c_codec_and_python_preserve_flags_and_legacy(self):
        root=Path(__file__).resolve().parents[1];probe=root/'artifacts/build/host/Release/fm1_native_state_tests.exe'
        if not probe.exists():self.skipTest('Build current Release codec probe')
        state=fixture();state['tracks'][3].update(solo=1,fx_bypass=1)
        for raw in (old.encode(old_fixture()),native.encode(state)):
            with tempfile.TemporaryDirectory() as tmp:
                src=Path(tmp)/'in';out=Path(tmp)/'out';src.write_bytes(raw)
                result=subprocess.run([str(probe),'--roundtrip',str(src),str(out)],capture_output=True,timeout=10)
                self.assertEqual(result.returncode,0,result.stderr)
                import fm1_native_state_v11 as current
                self.assertEqual(current.decode(out.read_bytes()),current.decode_compatible(raw))
