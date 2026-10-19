from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
import acquire_stock_reference as stock


class StockReferenceTests(unittest.TestCase):
    def test_unknown_binary_never_accepted(self):
        for data in (b"",b"\0"*stock.SIZE,b"\xFF"*(stock.SIZE+1)):
            with self.assertRaises(ValueError): stock.decode_reference(data)

    def test_prior_acquisition_never_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"reference.bin"
            stock.preserve(path,b"original")
            stock.preserve(path,b"original")
            with self.assertRaises(ValueError): stock.preserve(path,b"changed")
            self.assertEqual(path.read_bytes(),b"original")


if __name__=="__main__": unittest.main()
