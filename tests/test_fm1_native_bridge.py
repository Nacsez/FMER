import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import fm1_native_state as native
import fm1_native_bridge as bridge
from tests.test_fm1_native_state import state_fixture, reply


class Journal:
    def __init__(self): self.events = []
    def record(self, event, **values): self.events.append(dict(event=event, **values))


class Session:
    """Independent wire-level in-memory target; no production codec on input."""
    verified_identity = "FM-1_707"

    def __init__(self):
        self.state = state_fixture()
        self.state["source_generation"] = 7
        self.generation = 7
        self.export = 0
        self.tx = self.last_tx = self.last_result = 0
        self.received = bytearray()
        self.sent = []
        self.status_count = 0
        self.stale_after_backup = False
        self.commit_result = 0
        self.corrupt_after_commit = False
        self.never_snapshot = False
        self.chunk_failure = False
        self.commit_timeout = False
        self.frame = None

    def _send(self, packet, purpose):
        self.sent.append(packet)
        op = packet[6]
        number = lambda start, count=5: sum(packet[start + i] << (7 * i) for i in range(count))
        if op == 13:
            self.status_count += 1
            if self.stale_after_backup and self.status_count == 3:
                self.generation += 1
            self.frame = reply(op, [1, self.generation, self.state["preset_id"], 0, 0, 0,
                                    self.export, self.last_tx, self.last_result])
        elif op == 14:
            if not self.never_snapshot:
                self.export += 1
                state = copy.deepcopy(self.state)
                state["source_generation"] = self.generation
                self.frozen = native.encode(state)
            self.frame = packet
        elif op == 15:
            token, offset = number(7), number(12, 2)
            assert token == self.export
            raw = self.frozen[offset:offset + 64]
            self.frame = reply(op, [token, offset, len(raw), *raw])
        elif op == 16:
            self.tx, self.expected = number(7), number(12)
            self.received = bytearray()
            self.frame = reply(op, [self.tx, 0])
        elif op == 17:
            tx, offset, count = number(7), number(12, 2), packet[14]
            assert tx == self.tx and offset == len(self.received)
            assert len(packet) == 16 + 2 * count
            self.received.extend((packet[15 + 2 * i] << 4) | packet[16 + 2 * i] for i in range(count))
            self.frame = reply(op, [tx, 12 if self.chunk_failure else 0])
        elif op == 18:
            tx = number(7)
            self.frame = reply(op, [tx, self.commit_result or 9])
            if not self.commit_result:
                self.state = native.decode(bytes(self.received))
                if self.corrupt_after_commit:
                    self.state["controls"][194] = 72
                self.generation += 1
                self.state["source_generation"] = self.generation
                self.last_tx, self.last_result = tx, 0
            if self.commit_timeout: self.frame = None
        elif op == 19:
            self.frame = reply(op, [number(7), 0])
        elif op == 20:
            self.tx = 0
            self.received = bytearray()
            self.frame = reply(op, [number(7), 0])
        else:
            raise AssertionError("Unrequested/unknown device command")

    def read(self, timeout):
        result = self.frame
        self.frame = None
        return result


class NativeBridgeTests(unittest.TestCase):
    def setUp(self):
        self.session, self.journal = Session(), Journal()
        self.bridge = bridge.NativeBridge(self.session, self.journal, sleep=lambda duration: None)

    def test_identity_gate_precedes_every_native_command(self):
        self.session.verified_identity = "FM-1_706"
        with self.assertRaises(RuntimeError): bridge.NativeBridge(self.session, self.journal)
        self.assertEqual(self.session.sent, [])

    def test_backup_saves_complete_frozen_state_without_musical_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.bridge.backup(Path(directory))
            state = native.decode(Path(result["backup"]["path"]).read_bytes())
            self.assertEqual(state, self.session.state)
            self.assertEqual(set(packet[6] for packet in self.session.sent), {13,14,15})

    def test_restore_backs_up_then_applies_and_verifies_every_field(self):
        desired = state_fixture()
        desired["controls"][194] = 41
        desired["vced"][145:] = list(b"EXACT NAME")
        with tempfile.TemporaryDirectory() as directory:
            result = self.bridge.restore(native.encode(desired), Path(directory), transaction=89)
            prior = native.decode(Path(result["pre_restore_backup"]["path"]).read_bytes())
            self.assertEqual(prior["source_generation"], 7)
            self.assertEqual(prior["controls"][194], 100)
            self.assertEqual(self.session.state["vced"][145:], list(b"EXACT NAME"))
            self.assertEqual(self.session.state["controls"][194], 41)
            self.assertTrue(result["complete_state_verified"])
            self.assertFalse(result["flash_writes"])
        kinds = [item["event"] for item in self.journal.events]
        self.assertLess(kinds.index("native_pre_restore_backup_committed"), kinds.index("native_restore_intent"))

    def test_invalid_restore_sends_no_command(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(native.NativeStateError):
                self.bridge.restore(bytes(784), Path(directory))
        self.assertEqual(self.session.sent, [])

    def test_failed_pre_restore_backup_prevents_mutation(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(native, "save_backup", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.bridge.restore(native.encode(state_fixture()), Path(directory))
        self.assertEqual(set(packet[6] for packet in self.session.sent), {13,14,15})

    def test_intervening_edit_after_backup_refuses_restore(self):
        self.session.stale_after_backup = True
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "changed after pre-restore"):
                self.bridge.restore(native.encode(state_fixture()), Path(directory))
            self.assertEqual(len(list(Path(directory).glob("*.fmer-native"))), 1)
        self.assertEqual(set(packet[6] for packet in self.session.sent), {13,14,15})

    def test_commit_stale_refusal_is_not_reported_as_success(self):
        self.session.commit_result = 14
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "commit refused: stale"):
                self.bridge.restore(native.encode(state_fixture()), Path(directory), transaction=89)
        self.assertEqual(self.session.state["source_generation"], 7)

    def test_readback_mismatch_is_retained_and_not_reported_as_success(self):
        self.session.corrupt_after_commit = True
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "complete native state differs"):
                self.bridge.restore(native.encode(state_fixture()), Path(directory), transaction=89)
        self.assertIn("native_restore_readback_mismatch", [item["event"] for item in self.journal.events])

    def test_snapshot_timeout_is_bounded(self):
        self.session.never_snapshot = True
        with self.assertRaisesRegex(TimeoutError, "did not publish"):
            self.bridge.snapshot()
        self.assertLessEqual(self.session.status_count, 101)

    def test_backup_ack_contains_exact_token_and_crc(self):
        raw = native.encode(self.session.state)
        result = self.bridge.acknowledge_save(16, raw)
        self.assertEqual(result["result"], 0)
        self.assertEqual(self.session.sent, [native.backup_ack_request(16, int.from_bytes(raw[28:32], "little"))])

    def test_failed_chunk_discards_own_staging(self):
        self.session.chunk_failure = True
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "chunk refused"):
                self.bridge.restore(native.encode(state_fixture()), Path(directory), transaction=89)
        self.assertEqual(self.session.sent[-1], native.abort_request(89))
        self.assertEqual(self.session.received, bytearray())
        self.assertEqual(self.session.state["source_generation"], 7)

    def test_ambiguous_commit_timeout_does_not_claim_abort_or_rollback(self):
        self.session.commit_timeout = True
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(TimeoutError):
                self.bridge.restore(native.encode(state_fixture()), Path(directory), transaction=89)
        self.assertEqual(self.session.sent[-1][6], 18)
        self.assertEqual(self.session.last_tx, 89)

    def test_previous_transaction_id_cannot_look_like_new_success(self):
        self.session.last_tx = 89
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "differ from the previous"):
                self.bridge.restore(native.encode(state_fixture()), Path(directory), transaction=89)
        self.assertNotIn(16, [packet[6] for packet in self.session.sent])


if __name__ == "__main__":
    unittest.main()
