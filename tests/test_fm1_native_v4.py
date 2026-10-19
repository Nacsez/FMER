"""Four-track native records: exact layout, strict migration and retained sound."""
import copy
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import fm1_native_state as v1
import fm1_native_state_v2 as v2
import fm1_native_state_v3 as v3
import fm1_native_state_v4 as native
from tests.test_fm1_native_v2 import state_fixture as legacy_fixture, v1_fixture


def fixture():
    s=native.decode(native.upgrade_v2(v2.encode(legacy_fixture())))
    s['controls'][150:155]=[2,430,1,1,2]
    s['controls'][158]=1
    s['tracks']=[dict(pattern=7-i,chain_mask=1<<i,sound_ref=120-i*35,level=100-i*25,mute=i%2) for i in range(4)]
    t=s['tracks'][2];s['controls'][155:158]=[t['sound_ref'],t['level'],t['mute']]
    s['patterns'][0]['steps'][60]=[129,122,90]
    return s


def crc_fixed(raw):
    b=bytearray(raw);struct.pack_into('<I',b,28,native.record_crc(b));return bytes(b)


class NativeV4Tests(unittest.TestCase):
    def test_exact_layout_and_hidden_ties_roundtrip(self):
        s=fixture();raw=native.encode(s)
        self.assertEqual(len(raw),2176);self.assertEqual(raw[:8],b'FMERNAT4')
        self.assertEqual(raw[2127:2131],b'TRK1');self.assertEqual(raw[2151:],bytes(25))
        self.assertEqual(raw[2131:2151],bytes(v for t in s['tracks'] for v in t.values()))
        self.assertEqual(native.decode(raw),s);self.assertEqual(native.encode(native.decode(raw)),raw)

    def test_each_extension_bit_is_crc_protected(self):
        raw=native.encode(fixture())
        for i in range(2127,2176):
            for bit in range(8):
                b=bytearray(raw);b[i]^=1<<bit
                with self.subTest(offset=i,bit=bit),self.assertRaises(native.NativeStateError):native.decode(b)

    def test_extension_magic_and_reserved_padding_refused_with_valid_crc(self):
        raw=native.encode(fixture())
        for i in [2127,2128,2129,2130,*range(2151,2176)]:
            b=bytearray(raw);b[i]^=1
            with self.subTest(offset=i),self.assertRaises(native.NativeStateError):native.decode(crc_fixed(b))

    def test_track_ranges_mirrors_and_unknown_fields_are_strict(self):
        for k,maximum in [('pattern',7),('chain_mask',255),('sound_ref',127),('level',100),('mute',1)]:
            for value in [-1,maximum+1,True,1.0]:
                s=fixture();s['tracks'][0][k]=value
                with self.subTest(field=k,value=value),self.assertRaises(native.NativeStateError):native.encode(s)
        for change in [lambda s:s['tracks'][0].update(extra=0),lambda s:s['tracks'].pop(),
                       lambda s:s['controls'].__setitem__(155,3),lambda s:s['controls'].__setitem__(156,99),
                       lambda s:s['controls'].__setitem__(157,1),lambda s:s['controls'].__setitem__(159,1)]:
            s=fixture();change(s)
            with self.assertRaises(native.NativeStateError):native.encode(s)

    def test_new_controls_reject_out_of_range_and_boolean_values(self):
        for i in range(150,160):
            lo,hi=native.control_bounds(i)
            for value in [-1,hi+1,True,1.0]:
                s=fixture();s['controls'][i]=value
                with self.subTest(id=i,value=value),self.assertRaises(native.NativeStateError):native.encode(s)

    def test_edit_pattern_may_differ_from_track_during_queue(self):
        s=fixture();self.assertNotEqual(s['controls'][195],s['tracks'][s['controls'][154]]['pattern'])
        self.assertEqual(native.decode(native.encode(s)),s)

    def test_selected_tie_is_valid_but_unknown_pitch_is_not(self):
        s=fixture();s['patterns'][7]['steps'][63][0]=129;s['controls'][188]=129
        self.assertEqual(native.decode(native.encode(s)),s)
        s['patterns'][7]['steps'][63][0]=130;s['controls'][188]=130
        with self.assertRaises(native.NativeStateError):native.encode(s)

    def test_v3_migration_preserves_all_old_sound_fx_and_sequence_values(self):
        old=v3.decode(v3.upgrade_v2(v2.encode(legacy_fixture())))
        old['controls'][145:150]=[2,91,0,1,1]
        old['controls'][162]=714;old['controls'][168:175]=[40,70,65,421,72,89,55]
        raw=v3.encode(old);saved=bytes(raw);s=native.decode_compatible(raw)
        self.assertEqual(raw,saved);self.assertEqual(s['vced'],old['vced']);self.assertEqual(s['patterns'],old['patterns'])
        self.assertEqual(s['controls'][:150],old['controls'][:150]);self.assertEqual(s['controls'][160:],old['controls'][160:])
        self.assertEqual(s['controls'][150:160],[0,150,0,0,0,127,100,0,0,0])
        self.assertEqual(s['tracks'],[dict(pattern=i,chain_mask=0,sound_ref=127,level=100,mute=0) for i in range(4)])
        self.assertEqual(s['source_generation'],old['source_generation'])

    def test_v1_v2_migration_uses_strict_historical_decoders(self):
        for raw in [v1.encode(v1_fixture()),v2.encode(legacy_fixture())]:
            s=native.decode_compatible(raw);self.assertEqual(s['controls'][147],1)
            self.assertEqual(s['controls'][150:155],[0,150,0,0,0]);self.assertEqual(s['version'],4)
            b=bytearray(raw);b[-1]=1
            with self.assertRaises(native.NativeStateError):native.decode_compatible(b)

    def test_legacy_decoder_never_accepts_new_bytes(self):
        raw=native.encode(fixture())
        for codec in (v1,v2,v3):
            with self.assertRaises(codec.NativeStateError):codec.decode(raw)
        for bad in [raw[:-1],raw+b'\0',b'',None,'x'*2176]:
            with self.assertRaises(native.NativeStateError):native.decode(bad)


if __name__=='__main__':unittest.main()
