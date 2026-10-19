import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import fm1_stock_catalog as stock


class StockCatalogTests(unittest.TestCase):
    def report(self,directory,report):
        raw=json.dumps(report).encode()
        (directory/'report.json').write_bytes(raw)
        (directory/'report.sha256').write_text(hashlib.sha256(raw).hexdigest()+'  report.json\n')
    def voice(self):
        raw=bytearray(128)
        raw[118:]=b'SYNTH TEST'
        return raw

    def test_operator_mapping_and_name(self):
        raw=self.voice();raw[:17]=bytes([60,61,62,63,90,80,70,0,39,10,20,9,59,22,87,7,23])
        voice=stock.unpack_voice(bytes(raw))
        self.assertEqual(voice[:21],[60,61,62,63,90,80,70,0,39,10,20,1,2,3,2,5,87,1,3,23,7])
        self.assertEqual(bytes(voice[145:]),b'SYNTH TEST')

    def test_normalization_keeps_original_and_reports_every_change(self):
        raw=self.voice();raw[12]=120;raw[112]=127
        original=stock.unpack_voice(bytes(raw));before=copy.deepcopy(original)
        normalized,changes=stock.normalize(original)
        self.assertEqual(original,before)
        self.assertEqual(changes,[dict(parameter=20,original=15,imported=14),dict(parameter=137,original=127,imported=99)])
        self.assertEqual(normalized[20],14);self.assertEqual(normalized[137],99)

    def test_valid_voice_is_lossless(self):
        voice=stock.unpack_voice(bytes(self.voice()))
        self.assertEqual(stock.normalize(voice),(voice,[]))

    def test_bad_voice_is_refused(self):
        for offset,value in ((0,128),(11,16),(13,32),(15,64),(110,32),(111,16),(118,0)):
            with self.subTest(offset=offset):
                raw=self.voice();raw[offset]=value
                with self.assertRaises(ValueError):stock.unpack_voice(raw)
        with self.assertRaises(ValueError):stock.unpack_voice(bytes(127))

    def test_double_read_required_and_hash_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp);data=bytes(0x100000)
            report=dict(status='verified_double_dump',dumps=[])
            for i in (1,2):
                name=f'flash-pass-{i}.bin';(directory/name).write_bytes(data)
                report['dumps'].append(dict(file=name,sha256=hashlib.sha256(data).hexdigest()))
            self.report(directory,report)
            self.assertEqual(stock.verified_dump(directory),data)
            (directory/'flash-pass-2.bin').write_bytes(data[:-1]+b'\1')
            with self.assertRaises(ValueError):stock.verified_dump(directory)

    def test_unverified_report_and_path_traversal_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            for report in (dict(status='failed'),dict(status='verified_double_dump',dumps=[dict(file='../other.bin')])):
                self.report(directory,report)
                with self.assertRaises(ValueError):stock.verified_dump(directory)
