# SPDX-License-Identifier: GPL-3.0-only
"""Passive bank intake regressions; no actual MIDI device is opened."""
import copy
import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import v16_bank_capture as capture
import library


def bank_bytes(channel=0, salt=0):
    payload = bytearray(4096)
    for i in range(32):
        payload[i*128+118:i*128+128] = f'TEST{i:02d}    '.encode()
    payload[0] = salt
    return bytes([0xf0,0x43,channel,9,0x20,0]) + bytes(payload) + bytes([(-sum(payload))&127,0xf7])


class CaptureTests(unittest.TestCase):
    def test_fragmentation_realtime_and_channel_voice_traffic(self):
        raw = bank_bytes(15)
        stream = b'\x90\x3c\x64' + b''.join(raw[i:i+32]+b'\xf8' for i in range(0,len(raw),32))
        for size in (1,2,47,128,512,8192):
            c = capture.BankCapture()
            for pos in range(0,len(stream),size): c.feed(stream[pos:pos+size])
            self.assertEqual(c.finish(),raw)
            self.assertTrue(c.progress()['complete'])
            self.assertGreater(c.progress()['realtime_messages'],0)
            self.assertEqual(capture.make_archive(raw,4)['payload']['channel'],16)

    def test_waiting_progress_and_partial_failure(self):
        c=capture.BankCapture();self.assertEqual(c.progress()['phase'],'waiting')
        c.feed(bank_bytes()[:512]);self.assertEqual(c.progress()['bytes_in_bank'],512)
        with self.assertRaisesRegex(ValueError,'complete'): c.finish()
        with self.assertRaises(ValueError): c.feed(bank_bytes())
        self.assertFalse(c.complete)

    def test_timeout_and_cancel_preserve_no_bank(self):
        now=[0];c=capture.BankCapture(clock=lambda:now[0],timeout=1)
        c.feed(bank_bytes()[:20]);now[0]=1
        with self.assertRaisesRegex(ValueError,'timed out'):c.feed(b'\xf8')
        self.assertIsNone(c.raw)
        self.assertEqual(c.progress()['phase'],'failed')
        c=capture.BankCapture();c.feed(bank_bytes());c.cancel()
        with self.assertRaisesRegex(ValueError,'cancelled'):c.finish()
        self.assertEqual(c.progress()['phase'],'cancelled')

    def test_duplicate_is_inert_but_second_different_bank_aborts(self):
        c=capture.BankCapture();c.feed(bank_bytes()*2)
        self.assertEqual(c.finish(),bank_bytes());self.assertEqual(c.duplicates,1)
        with self.assertRaisesRegex(ValueError,'different'):c.feed(bank_bytes(salt=1))
        self.assertIsNone(c.raw)

    def test_bad_envelopes_checksum_status_and_overflow(self):
        raw=bank_bytes()
        for packet in (raw[:7]+bytes([raw[7]^1])+raw[8:],raw[:2]+b'\x10'+raw[3:],
                       raw[:3]+b'\x00'+raw[4:],raw[:50]+b'\xf0'+raw[51:],
                       raw[:50]+b'\x90'+raw[51:],raw[:-1]+b'\0\xf7',b'\xf0\x7d\x01\xf7'):
            c=capture.BankCapture()
            with self.assertRaises(ValueError):c.feed(packet)
            self.assertFalse(c.complete)
        c=capture.BankCapture()
        with self.assertRaisesRegex(ValueError,'budget'):c.feed(b'\xf8'*65537)

    def test_invalid_bank_number_and_timeout(self):
        for value in (0,5,True,'1',None):
            with self.assertRaises(ValueError):capture.make_archive(bank_bytes(),value)
        for timeout in (0,301,float('nan'),True):
            with self.assertRaises(ValueError):capture.BankCapture(timeout=timeout)

    def test_archive_corruption_is_rejected_before_codec(self):
        archive=capture.make_archive(bank_bytes(),1)
        for key,value in [('source_sha256','0'*64),('channel',12),('declared_bank',5),('raw_base64','A'*5472)]:
            changed=copy.deepcopy(archive);changed['payload'][key]=value
            changed['sha256']=hashlib.sha256(library.canonical(changed['payload'])).hexdigest()
            codec=Mock()
            with self.assertRaises(ValueError):capture.decode_archive(changed,{},codec)
            codec.decode.assert_not_called()

    def test_real_codec_roundtrip_and_invalid_parameters(self):
        exe=ROOT/'artifacts/build/host/host/Release/fmer_host.exe'
        if not exe.is_file():self.skipTest('Optional compiled host unavailable')
        codec=library.PatchCodec(exe,lambda *a,**k:None)
        template=capture.bank.decode_record(capture.bank.profile(exe)[0]['native'])
        before=copy.deepcopy(template)
        raw=bank_bytes()
        result=capture.decode_archive(capture.make_archive(raw,1),template,codec)
        self.assertEqual(result['count'],32);self.assertEqual(template,before)
        self.assertFalse(result['library_written']);self.assertFalse(result['firmware_identity_verified'])
        bad=bank_bytes(salt=127) # Rate1 must not exceed99, despite a valid MIDI checksum.
        with self.assertRaises(ValueError):capture.decode_archive(capture.make_archive(bad,1),template,codec)
        self.assertEqual(template,before)


if __name__=='__main__':unittest.main()
