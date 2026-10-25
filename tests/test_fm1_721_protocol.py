import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from unittest.mock import patch
from tools import fm1_package as pkg
from tools import fm1_native_bridge_v15 as bridge
from tools import fm1_session as capture

class Protocol721Tests(unittest.TestCase):
    def test_loader_admits_only_installed720_release6(self):
        digest=bytes.fromhex(pkg.INSTALLED_720_RELEASE6_APP_SHA256)
        with patch.object(pkg,'installed_720_release6_reference',return_value=b'checked'):
            result=pkg.transition_profile(pkg.PERFORMANCE_PRODUCT,pkg.TEST01_TEMPLATE,b'prefix'+digest+b'suffix')
            self.assertEqual(result['origin_identity'],'FM-1_720')
            self.assertEqual(result['loader_identity'],'ota-FM-1_721')
            for bad in (b'',digest*2,digest+bytes.fromhex(pkg.INSTALLED_720_RELEASE5_APP_SHA256)):
                with self.assertRaises(ValueError):pkg.transition_profile(pkg.PERFORMANCE_PRODUCT,pkg.TEST01_TEMPLATE,bad)

    def test_usb_counter_extent_and_read_only_capability(self):
        values=[1,500,1,1,1,1,1,32,*range(12)]
        packet=capture.PREFIX+bytes([31])+' '.join(map(str,values)).encode()+bytes([247])
        self.assertEqual(bridge.parse_usb_audio(packet)['ring_frames'],32)
        with self.assertRaises(ValueError):bridge.parse_usb_audio(capture.PREFIX+bytes([31])+b"1 2"+bytes([247]))
        session=object.__new__(capture.ReadOnlySession)
        with patch.object(capture.transport.MidiSession,'_send'):
            for identity in capture.SUPPORTED_IDENTITIES:
                session.expected_identity=session.verified_identity=identity
                if identity in ('FM-1_721','FM-1_722','FM-1_723','FM-1_724','FM-1_725','FM-1_726','FM-1_727','FM-1_728','FM-1_729','FM-1_730','FM-1_731','FM-1_733','FM-1_734','FM-1_735'):session._send(bridge.usb_audio_request(),'read stream counters')
                else:
                    with self.assertRaises(capture.CaptureError):session._send(bridge.usb_audio_request(),'unsupported counters')
