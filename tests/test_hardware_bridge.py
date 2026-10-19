"""No physical APIs are loaded; exercise bridge refusals, framing and lifecycle."""
import ctypes as ct
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import hardware_bridge as bridge


class FakeWinMM:
    callback_type = staticmethod(lambda callback: callback)

    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    def checked(self, name, *args):
        self.calls.append(name)
        if name == self.fail:
            raise bridge.BridgeError("injected " + name)


class BridgeTests(unittest.TestCase):
    def endpoints(self):
        return {"inputs": [{"id": 2, "name": "2- FM-1 Midi"}],
                "outputs": [{"id": 3, "name": "2- FM-1 Midi"}]}

    def test_selection_ignores_unrelated_ports_and_requires_unique(self):
        data = self.endpoints()
        data["outputs"].append({"id": 1, "name": "Other synth"})
        self.assertEqual(bridge.select_pair(data)[1]["id"], 3)
        data["inputs"].append({"id": 5, "name": "FM-1 Midi"})
        with self.assertRaises(bridge.BridgeError):
            bridge.select_pair(data)
        self.assertEqual(bridge.select_pair(data, 5, 3)[0]["id"], 5)
        with self.assertRaises(bridge.BridgeError):
            bridge.select_pair(data, 5, 1)

    def test_empty_or_disconnected_selection_refuses(self):
        with self.assertRaises(bridge.BridgeError):
            bridge.select_pair({"inputs": [], "outputs": []})
        with self.assertRaises(bridge.BridgeError):
            bridge.select_pair(self.endpoints(), 9, 3)

    def test_split_messages_and_interleaved_realtime(self):
        a = bridge.SysexAssembler()
        self.assertEqual(a.feed(bytes.fromhex("F0 01 F8 02")), [])
        self.assertEqual(a.feed(bytes.fromhex("03 FE F7 F0 04 F7")),
                         [bytes.fromhex("F0 01 02 03 F7"), bytes.fromhex("F0 04 F7")])

    def test_broken_frames_and_bounds_refuse(self):
        for data in (b"\x01", b"\xF0\xF0", b"\xF0\x90", b"\xF0" + b"\0"*8,
                     b"\xF0" + b"\0"*7 + b"\xF7"):
            with self.subTest(data=data), self.assertRaises(bridge.BridgeError):
                bridge.SysexAssembler(maximum=8).feed(data)

    def test_native_header_width(self):
        self.assertEqual(ct.sizeof(bridge.MidiHeader), 120 if ct.sizeof(ct.c_void_p) == 8 else 64)

    def test_normal_cleanup_does_not_reset_output_or_send_notes(self):
        api = FakeWinMM(); events = []
        session = bridge.IdentitySession(api, 0, 0, events)
        session.input, session.output = bridge.HANDLE(1), bridge.HANDLE(2)
        header = bridge.MidiHeader(dwFlags=bridge.MHDR_DONE)
        session.out_buffer = (header, b"retained")
        self.assertEqual(session.close(), [])
        self.assertNotIn("midiOutReset", api.calls)
        self.assertEqual(api.calls, ["midiInStop", "midiInReset", "midiInClose",
                                     "midiOutUnprepareHeader", "midiOutClose"])

    def test_cleanup_failure_retains_driver_owned_memory(self):
        api = FakeWinMM("midiOutUnprepareHeader")
        session = bridge.IdentitySession(api, 0, 0, [])
        session.output = bridge.HANDLE(2)
        session.out_buffer = (bridge.MidiHeader(dwFlags=bridge.MHDR_DONE), b"retained")
        self.assertTrue(session.close())
        self.assertIn(session, bridge._unreleased_sessions)
        bridge._unreleased_sessions.remove(session)

    def test_pending_output_cancellation_is_recorded(self):
        api = FakeWinMM(); events = []
        session = bridge.IdentitySession(api, 0, 0, events)
        session.output = bridge.HANDLE(2)
        session.out_buffer = (bridge.MidiHeader(dwFlags=bridge.MHDR_INQUEUE), b"retained")
        session.close()
        self.assertIn("midiOutReset", api.calls)
        self.assertTrue(events[0]["may_silence_notes"])

    def test_unsent_prepared_output_is_not_reset(self):
        api = FakeWinMM()
        session = bridge.IdentitySession(api, 0, 0, [])
        session.output = bridge.HANDLE(2)
        session.out_buffer = (bridge.MidiHeader(), b"retained")
        session.close()
        self.assertNotIn("midiOutReset", api.calls)

    def test_callback_queue_is_bounded(self):
        session = bridge.IdentitySession(FakeWinMM(), 0, 0, [])
        for i in range(65):
            session._callback(1, bridge.MIM_LONGDATA, 0, i, 0)
        self.assertEqual(len(session.received), 64)
        self.assertTrue(session.callback_overflow)

    def test_evidence_is_exclusive(self):
        with tempfile.TemporaryDirectory() as temp:
            target = bridge.write_report({"status": "test"}, Path(temp))
            with self.assertRaises(FileExistsError):
                bridge.write_report({"status": "overwrite"}, Path(temp))
            self.assertEqual(json.loads(target.read_text())["status"], "test")


if __name__ == "__main__":
    unittest.main()
