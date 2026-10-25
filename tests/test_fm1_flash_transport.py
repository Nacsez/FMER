"""Offline updater framing, state, qualification and WinMM lifecycle tests."""
import ctypes as ct
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import device_protocol as protocol
import fm1_flash_transport as updater
import hardware_bridge as bridge


def reference_pack(data):
    bits = [((byte >> bit) & 1) for byte in data for bit in range(8)]
    return bytes(sum(bit << index for index, bit in enumerate(bits[start:start + 7]))
                 for start in range(0, len(bits), 7))


def request(address, length, flags=0, *, declared=8):
    body = b"\x00\x59\x30" + declared.to_bytes(3, "little") + bytes([flags])
    body += address.to_bytes(4, "little") + length.to_bytes(3, "little")
    return b"\xF0" + reference_pack(body + bytes([~sum(body[6:]) & 255])) + b"\xF7"


def package():
    image = bytes(range(256)) * 8
    return updater.QualifiedPackage(image, {"product": updater.TARGET_ID, "loader_image_bytes": 384,
                                           "files": {"ota.bin": {"offset": 512, "bytes": 512}}}, 1024, 2048)


def qualified_package():
    original = package()
    return updater.QualifiedPackage(original.image, dict(original.report, runtime_preflight_qualified=True), 1024, 2048)


def successor_package(target=None):
    import fm1_package
    target = target or updater.NEXT_TARGET_ID
    original = qualified_package()
    origin, loader, digest, package_hash = {
        updater.NEXT_TARGET_ID: (updater.TARGET_ID, updater.NEXT_LOADER_ID, fm1_package.INSTALLED_701_APP_SHA256, fm1_package.INSTALLED_701_PACKAGE_SHA256),
        updater.CURRENT_TARGET_ID: (updater.NEXT_TARGET_ID, updater.CURRENT_LOADER_ID, fm1_package.INSTALLED_702_APP_SHA256, fm1_package.INSTALLED_702_PACKAGE_SHA256),
        updater.BUILD_TARGET_ID: (updater.CURRENT_TARGET_ID, updater.BUILD_LOADER_ID, fm1_package.INSTALLED_703_APP_SHA256, fm1_package.INSTALLED_703_PACKAGE_SHA256),
        updater.LATEST_TARGET_ID: (updater.BUILD_TARGET_ID, updater.LATEST_LOADER_ID, fm1_package.INSTALLED_704_APP_SHA256, fm1_package.INSTALLED_704_PACKAGE_SHA256),
        updater.DEVELOPMENT_TARGET_ID: (updater.LATEST_TARGET_ID, updater.DEVELOPMENT_LOADER_ID, fm1_package.INSTALLED_705_APP_SHA256, fm1_package.INSTALLED_705_PACKAGE_SHA256),
        updater.CANDIDATE_TARGET_ID: (updater.DEVELOPMENT_TARGET_ID, updater.CANDIDATE_LOADER_ID, fm1_package.INSTALLED_706_APP_SHA256, fm1_package.INSTALLED_706_PACKAGE_SHA256),
        updater.INSTRUMENT_TARGET_ID: (updater.CANDIDATE_TARGET_ID, updater.INSTRUMENT_LOADER_ID, fm1_package.INSTALLED_707_APP_SHA256, fm1_package.INSTALLED_707_PACKAGE_SHA256),
        updater.BANK_TARGET_ID: (updater.INSTRUMENT_TARGET_ID, updater.BANK_LOADER_ID, fm1_package.INSTALLED_708_APP_SHA256, fm1_package.INSTALLED_708_PACKAGE_SHA256),
    }[target]
    report = dict(original.report, product=target, origin_identity=origin,
                  loader_identity=loader, origin_app_sha256=digest, origin_package_sha256=package_hash,
                  template=fm1_package.TEST01_TEMPLATE)
    return updater.QualifiedPackage(original.image, report, original.app_begin, original.app_end)


def ready_status(*, dirty=False, state=0, error=0):
    return {"state": state, "error": error, "app_dirty": dirty, "match_count": 1,
            "record_address": 0xE4F00, "loader_length": 384}


class ProtocolTests(unittest.TestCase):
    def test_720_release5_and_release4_pairs_cannot_be_crossed_before_device_access(self):
        import fm1_package as pkg
        original = qualified_package()
        pairs = [(getattr(pkg, prefix+'_APP_SHA256'), getattr(pkg, prefix+'_PACKAGE_SHA256'))
                 for prefix in ('INSTALLED_720_RELEASE4', 'INSTALLED_720_RELEASE5')]
        report = dict(original.report, product='FM-1_720', origin_identity='FM-1_720', loader_identity='ota-FM-1_720',
                      origin_app_sha256=pairs[1][0], origin_package_sha256=pairs[1][1], template=pkg.TEST01_TEMPLATE)
        candidate = updater.QualifiedPackage(original.image, report, original.app_begin, original.app_end)
        self.assertEqual(updater.update_identities(candidate), ('FM-1_720', 'ota-FM-1_720', 'FM-1_720'))
        for resume, expected in ((False, ['FM-1_720', 'ota-FM-1_720', 'FM-1_720']), (True, ['ota-FM-1_720', 'FM-1_720'])):
            sessions = [Mock() for _ in expected]
            for session in sessions: session.close.return_value=[]; session.loader_control.return_value=ready_status(dirty=resume)
            with patch.object(updater, 'find_session', side_effect=sessions) as find, patch.object(updater, 'serve') as serve:
                updater.perform_update(Mock(), candidate, RecordJournal(), resume=resume)
            self.assertEqual([call.args[1] for call in find.call_args_list], expected)
            self.assertEqual([call.args[2] for call in serve.call_args_list], [2] if resume else [1, 2])
        changes = [dict(origin_app_sha256=pairs[0][0]), dict(origin_package_sha256=pairs[0][1]),
                   dict(origin_identity='FM-1_719'), dict(loader_identity='ota-FM-1_719'), dict(product='FM-1_719'),
                   dict(origin_app_sha256='0'*64), dict(origin_package_sha256=None), dict(template='published-v15'),
                   dict(runtime_preflight_qualified=False),
                   dict(origin_app_sha256=pkg.INSTALLED_719_INLINE_APP_SHA256,
                        origin_package_sha256=pkg.INSTALLED_719_INLINE_PACKAGE_SHA256)]
        for change in changes:
            bad = updater.QualifiedPackage(candidate.image, dict(report, **change), candidate.app_begin, candidate.app_end)
            for resume in (False, True):
                with self.subTest(change=change, resume=resume), patch.object(updater, 'find_session') as find, \
                     self.assertRaises(updater.UpdateError):
                    updater.perform_update(Mock(), bad, RecordJournal(), resume=resume)
                find.assert_not_called()

    def test_720_same_identity_requires_exact_release4_pair_before_device_access(self):
        import fm1_package as pkg
        original = qualified_package()
        report = dict(original.report, product='FM-1_720', origin_identity='FM-1_720', loader_identity='ota-FM-1_720',
                      origin_app_sha256=pkg.INSTALLED_720_RELEASE4_APP_SHA256,
                      origin_package_sha256=pkg.INSTALLED_720_RELEASE4_PACKAGE_SHA256, template=pkg.TEST01_TEMPLATE)
        candidate = updater.QualifiedPackage(original.image, report, original.app_begin, original.app_end)
        self.assertEqual(updater.update_identities(candidate), ('FM-1_720', 'ota-FM-1_720', 'FM-1_720'))
        for resume, expected in ((False, ['FM-1_720', 'ota-FM-1_720', 'FM-1_720']), (True, ['ota-FM-1_720', 'FM-1_720'])):
            sessions = [Mock() for _ in expected]
            for session in sessions: session.close.return_value=[]; session.loader_control.return_value=ready_status(dirty=resume)
            with patch.object(updater, 'find_session', side_effect=sessions) as find, patch.object(updater, 'serve') as serve:
                updater.perform_update(Mock(), candidate, RecordJournal(), resume=resume)
            self.assertEqual([call.args[1] for call in find.call_args_list], expected)
            self.assertEqual([call.args[2] for call in serve.call_args_list], [2] if resume else [1, 2])
        changes = [dict(origin_identity='FM-1_719'), dict(loader_identity='ota-FM-1_719'), dict(product='FM-1_719'),
                   dict(origin_app_sha256='0'*64), dict(origin_package_sha256=None), dict(template='published-v15'),
                   dict(runtime_preflight_qualified=False)]
        for prefix in ('INSTALLED_718', 'INSTALLED_719', 'INSTALLED_719_CORRECTED', 'INSTALLED_719_FINAL',
                       'INSTALLED_719_OPTIMIZED', 'INSTALLED_719_ARITHMETIC', 'INSTALLED_719_PHASER', 'INSTALLED_719_INLINE'):
            changes.extend([dict(origin_app_sha256=getattr(pkg, prefix+'_APP_SHA256')),
                            dict(origin_package_sha256=getattr(pkg, prefix+'_PACKAGE_SHA256')),
                            dict(origin_app_sha256=getattr(pkg, prefix+'_APP_SHA256'),
                                 origin_package_sha256=getattr(pkg, prefix+'_PACKAGE_SHA256'))])
        for change in changes:
            bad = updater.QualifiedPackage(candidate.image, dict(report, **change), candidate.app_begin, candidate.app_end)
            for resume in (False, True):
                with self.subTest(change=change, resume=resume), patch.object(updater, 'find_session') as find, \
                     self.assertRaises(updater.UpdateError):
                    updater.perform_update(Mock(), bad, RecordJournal(), resume=resume)
                find.assert_not_called()

    def test_720_route_requires_exact_inline719_pair_before_device_access(self):
        import fm1_package as pkg
        original=qualified_package()
        report=dict(original.report,product='FM-1_720',origin_identity='FM-1_719',loader_identity='ota-FM-1_720',
                    origin_app_sha256=pkg.INSTALLED_719_INLINE_APP_SHA256,
                    origin_package_sha256=pkg.INSTALLED_719_INLINE_PACKAGE_SHA256,template=pkg.TEST01_TEMPLATE)
        candidate=updater.QualifiedPackage(original.image,report,original.app_begin,original.app_end)
        self.assertEqual(updater.update_identities(candidate),('FM-1_719','ota-FM-1_720','FM-1_720'))
        for resume,expected in ((False,['FM-1_719','ota-FM-1_720','FM-1_720']),(True,['ota-FM-1_720','FM-1_720'])):
            sessions=[Mock() for _ in expected]
            for session in sessions:session.close.return_value=[];session.loader_control.return_value=ready_status(dirty=resume)
            with patch.object(updater,'find_session',side_effect=sessions) as find,patch.object(updater,'serve') as serve:
                updater.perform_update(Mock(),candidate,RecordJournal(),resume=resume)
            self.assertEqual([call.args[1] for call in find.call_args_list],expected)
            self.assertEqual([call.args[2] for call in serve.call_args_list],[2] if resume else [1,2])
        changes=[dict(origin_identity='FM-1_718'),dict(loader_identity='ota-FM-1_719'),dict(product='FM-1_719'),
                 dict(origin_app_sha256='0'*64),dict(origin_package_sha256='1'*64),dict(template='published-v15'),
                 dict(runtime_preflight_qualified=False)]
        for prefix in ('INSTALLED_719','INSTALLED_719_CORRECTED','INSTALLED_719_FINAL','INSTALLED_719_OPTIMIZED',
                       'INSTALLED_719_ARITHMETIC','INSTALLED_719_PHASER'):
            changes.extend([dict(origin_app_sha256=getattr(pkg,prefix+'_APP_SHA256')),
                            dict(origin_package_sha256=getattr(pkg,prefix+'_PACKAGE_SHA256')),
                            dict(origin_app_sha256=getattr(pkg,prefix+'_APP_SHA256'),
                                 origin_package_sha256=getattr(pkg,prefix+'_PACKAGE_SHA256'))])
        for change in changes:
            bad=updater.QualifiedPackage(candidate.image,dict(report,**change),candidate.app_begin,candidate.app_end)
            with self.subTest(change=change),patch.object(updater,'find_session') as find,self.assertRaises(updater.UpdateError):
                updater.perform_update(Mock(),bad,RecordJournal())
            find.assert_not_called()

    def test_fmer_control_codec_exact_requests_and_signed_error(self):
        self.assertEqual(updater.loader_control_request(1), bytes.fromhex("F0 7D 46 4D 45 52 01 01 F7"))
        self.assertEqual(updater.loader_control_request(2), bytes.fromhex("F0 7D 46 4D 45 52 01 02 F7"))
        body = b"\4" + (-67).to_bytes(4, "little", signed=True) + b"\0\1" + (0xE4F00).to_bytes(4, "little") + (4096).to_bytes(4, "little")
        frame = updater.CONTROL_PREFIX + b"\x41" + reference_pack(body + bytes([~sum(body) & 255])) + b"\xF7"
        decoded = updater.parse_loader_control_reply(frame, 1)
        self.assertEqual(decoded, {"protocol_version": 1, "operation": 1, "state": 4, "error": -67,
                                   "app_dirty": False, "match_count": 1, "record_address": 0xE4F00, "loader_length": 4096})
        for value in (frame[:-1], frame + b"\0", frame[:7] + b"\x42" + frame[8:]):
            with self.assertRaises(updater.UpdateError):
                updater.parse_loader_control_reply(value, 1)
        for op in (0, 3, True):
            with self.assertRaises(updater.UpdateError):
                updater.loader_control_request(op)

    def test_known_request_uses_all_address_bits_and_flags(self):
        for address in (0, 481, 0xE0000000, 0xF0000000, 0xFFFFFFFF):
            self.assertEqual(updater.parse_request(request(address, 8, 255)), updater.ReadRequest(255, address, 8))

    def test_partial_481_byte_reply_has_exact_dynamic_lengths(self):
        data = bytes(range(256)) + bytes(range(225))
        answer = updater.response(updater.ReadRequest(129, 0x10201, 481), data)
        decoded = protocol.unpack_seven_bit(answer[1:-1], 496)
        self.assertEqual(decoded[:7], b"\x00\x59\x30\xE9\x01\0\x81")
        self.assertEqual(int.from_bytes(decoded[11:14], "little"), 481)
        self.assertEqual(decoded[14:-1], data)
        self.assertEqual(decoded[-1], ~sum(decoded[6:-1]) & 255)
        self.assertEqual(answer, b"\xF0" + reference_pack(decoded) + b"\xF7")

    def test_noncanonical_and_malformed_requests_are_refused_atomically(self):
        valid = request(0, 64)
        bad_checksum = bytearray(valid); bad_checksum[-2] ^= 1
        bad_padding = bytearray(valid); bad_padding[-2] |= 64
        bad_status = bytearray(valid); bad_status[4] = 0xF8
        for frame in (valid[:-1], valid + b"\0", bytes(bad_checksum), bytes(bad_padding), bytes(bad_status), request(0, 64, declared=9)):
            stage = updater.PullStage(package(), 1)
            with self.subTest(frame=frame), self.assertRaises(updater.UpdateError):
                stage.accept(frame, 1)
            self.assertEqual((stage.requests, stage.covered, stage.finished), (0, 0, False))

    def test_response_refuses_wrong_payload_and_bad_address(self):
        for req, data in ((updater.ReadRequest(0, 0, 2), b"x"), (updater.ReadRequest(0, 0, 0), b""),
                          (updater.ReadRequest(0, -1, 1), b"x"), (updater.ReadRequest(256, 0, 1), b"x")):
            with self.assertRaises(updater.UpdateError):
                updater.response(req, data)


class StageTests(unittest.TestCase):
    def test_nonsequential_and_duplicate_reads_return_exact_bytes(self):
        stage = updater.PullStage(package(), 2)
        first, _ = stage.accept(request(1536, 512, 7), 1)
        duplicate, details = stage.accept(request(1536, 512, 7), 2)
        self.assertEqual(first, duplicate)
        self.assertEqual(details["duplicate_count"], 2)
        self.assertEqual(stage.covered, 512)
        stage.accept(request(0, 20), 3)
        stage.accept(request(1024, 512), 4)
        terminal, details = stage.accept(request(updater.WRITE_DONE, 8), 5)
        self.assertTrue(stage.finished)
        self.assertEqual(details["covered_app_bytes"], 1024)
        decoded = protocol.unpack_seven_bit(terminal[1:-1], 23)
        self.assertEqual(decoded[14:-1], b"success\0")

    def test_bounds_and_terminals_do_not_mutate_state(self):
        for stage_id, frame in ((1, request(0, 0)), (1, request(0, 513)), (1, request(2040, 9)),
                                (1, request(0xFFFFFFFF, 512)), (1, request(updater.WRITE_DONE, 8)),
                                (1, request(updater.VERIFY_DONE, 7)), (1, request(updater.VERIFY_DONE, 8)),
                                (2, request(updater.VERIFY_DONE, 8))):
            stage = updater.PullStage(package(), stage_id)
            with self.subTest(stage=stage_id, frame=frame), self.assertRaises(updater.UpdateError):
                stage.accept(frame, 1)
            self.assertEqual(stage.requests, 0)

    def test_stage2_requires_complete_coverage_and_counts_overlaps_once(self):
        stage = updater.PullStage(package(), 2)
        stage.accept(request(1024, 512), 1)
        stage.accept(request(1280, 512), 2)
        self.assertEqual(stage.covered, 768)
        with self.assertRaises(updater.UpdateError):
            stage.accept(request(updater.WRITE_DONE, 8), 3)
        stage.accept(request(1792, 256), 4)
        stage.accept(request(updater.WRITE_DONE, 8), 5)
        self.assertEqual(stage.covered, 1024)

    def test_finish_retries_are_idempotent_but_data_after_finish_is_refused(self):
        stage = updater.PullStage(package(), 1)
        stage.accept(request(512, 512), 1)
        first, _ = stage.accept(request(updater.VERIFY_DONE, 8), 2)
        again, _ = stage.accept(request(updater.VERIFY_DONE, 8), 3)
        self.assertEqual(first, again)
        with self.assertRaises(updater.UpdateError):
            stage.accept(request(100, 5), 4)

    def test_stage1_finish_requires_full_qualified_loader_coverage(self):
        stage = updater.PullStage(package(), 1)
        stage.accept(request(0, 64), 1)
        with self.assertRaises(updater.UpdateError):
            stage.accept(request(updater.VERIFY_DONE, 8), 2)
        stage.accept(request(768, 256), 3)
        stage.accept(request(512, 256), 4)
        stage.accept(request(updater.VERIFY_DONE, 8), 5)
        self.assertTrue(stage.finished)

    def test_duplicate_and_total_request_budgets_are_bounded(self):
        stage = updater.PullStage(package(), 1)
        for index in range(updater.MAX_DUPLICATES):
            stage.accept(request(0, 16), index / 10)
        with self.assertRaises(updater.UpdateError):
            stage.accept(request(0, 16), 2)
        stage = updater.PullStage(package(), 1)
        with patch.object(updater, "MAX_REQUESTS", 2):
            stage.accept(request(0, 1), 1)
            stage.accept(request(1, 1), 2)
            with self.assertRaises(updater.UpdateError):
                stage.accept(request(2, 1), 3)

    def test_idle_absolute_and_invalid_clock_deadlines(self):
        stage = updater.PullStage(package(), 1)
        for now in (9, -1, float("nan"), float("inf")):
            with self.subTest(now=now), self.assertRaises(updater.UpdateError):
                stage.check_timeout(now)
        stage.last = 179
        with self.assertRaises(updater.UpdateError):
            stage.check_timeout(181)


class RecordJournal:
    def __init__(self, fail=None):
        self.events, self.fail = [], fail

    def record(self, event, **values):
        if event == self.fail:
            raise OSError("injected journal failure")
        self.events.append({"event": event, **values})


def caps_row(identifier=1, name="FM-1 Midi"):
    return {"id": identifier, "name": name, "driver_manufacturer_id": 12,
            "driver_product_id": 34, "driver_version": 56}


class FakeWinMM:
    callback_type = getattr(ct, "WINFUNCTYPE", ct.CFUNCTYPE)(None, bridge.HANDLE, bridge.UINT,
                                                            bridge.UINTPTR, bridge.UINTPTR, bridge.UINTPTR)

    def __init__(self, mismatch=False, fail=None):
        self.calls, self.mismatch, self.fail = [], mismatch, fail

    def checked(self, name, *args):
        self.calls.append((name, args))
        if name == self.fail:
            raise bridge.BridgeError("injected " + name)
        if name in ("midiInOpen", "midiOutOpen"):
            ct.cast(args[0], ct.POINTER(bridge.HANDLE))[0] = bridge.HANDLE(101 if name == "midiInOpen" else 102)
        if name in ("midiInGetDevCapsW", "midiOutGetDevCapsW"):
            kind = bridge.MidiInCaps if name.startswith("midiIn") else bridge.MidiOutCaps
            caps = ct.cast(args[1], ct.POINTER(kind)).contents
            caps.szPname = "Other synth" if self.mismatch else "FM-1 Midi"
            caps.wMid, caps.wPid, caps.vDriverVersion = 12, 34, 56
        if name == "midiOutLongMsg":
            ct.cast(args[1], ct.POINTER(bridge.MidiHeader)).contents.dwFlags = bridge.MHDR_DONE


class TransportTests(unittest.TestCase):
    def test_corrected719_same_identity_routes_require_exact_initial719_hashes(self):
        import fm1_package as pkg
        original=qualified_package()
        report=dict(original.report,product='FM-1_719',origin_identity='FM-1_719',loader_identity='ota-FM-1_719',
                    origin_app_sha256=pkg.INSTALLED_719_APP_SHA256,origin_package_sha256=pkg.INSTALLED_719_PACKAGE_SHA256,
                    template=pkg.TEST01_TEMPLATE)
        candidate=updater.QualifiedPackage(original.image,report,1024,2048)
        self.assertEqual(updater.update_identities(candidate),('FM-1_719','ota-FM-1_719','FM-1_719'))
        for resume,identities in ((False,['FM-1_719','ota-FM-1_719','FM-1_719']),(True,['ota-FM-1_719','FM-1_719'])):
            sessions=[Mock() for _ in identities]
            for session in sessions:session.close.return_value=[];session.loader_control.return_value=ready_status(dirty=resume)
            with patch.object(updater,'find_session',side_effect=sessions) as find,patch.object(updater,'serve') as serve:
                updater.perform_update(Mock(),candidate,RecordJournal(),resume=resume)
            self.assertEqual([c.args[1] for c in find.call_args_list],identities)
            self.assertEqual([c.args[2] for c in serve.call_args_list],[2] if resume else [1,2])
        for changed in ({'origin_app_sha256':pkg.INSTALLED_718_APP_SHA256}, {'origin_package_sha256':pkg.INSTALLED_718_PACKAGE_SHA256},
                        {'origin_app_sha256':'0'*64}, {'origin_package_sha256':None}, {'origin_identity':'FM-1_718'},
                        {'loader_identity':'ota-FM-1_718'}, {'runtime_preflight_qualified':False}):
            invalid=updater.QualifiedPackage(original.image,dict(report,**changed),1024,2048)
            with self.subTest(changed=changed),patch.object(updater,'find_session') as find,self.assertRaises(updater.UpdateError):
                updater.perform_update(Mock(),invalid,RecordJournal())
            find.assert_not_called()
        historical=dict(report,origin_identity='FM-1_718',origin_app_sha256=pkg.INSTALLED_718_APP_SHA256,
                        origin_package_sha256=pkg.INSTALLED_718_PACKAGE_SHA256)
        self.assertEqual(updater.update_identities(updater.QualifiedPackage(original.image,historical,1024,2048)),
                         ('FM-1_718','ota-FM-1_719','FM-1_719'))

    def test_third719_routes_require_paired_corrected719_hashes_before_device_access(self):
        import fm1_package as pkg
        original = qualified_package()
        report = dict(original.report, product='FM-1_719', origin_identity='FM-1_719', loader_identity='ota-FM-1_719',
                      origin_app_sha256=pkg.INSTALLED_719_CORRECTED_APP_SHA256,
                      origin_package_sha256=pkg.INSTALLED_719_CORRECTED_PACKAGE_SHA256, template=pkg.TEST01_TEMPLATE)
        candidate = updater.QualifiedPackage(original.image, report, 1024, 2048)
        self.assertEqual(updater.update_identities(candidate), ('FM-1_719', 'ota-FM-1_719', 'FM-1_719'))
        for resume, identities in ((False, ['FM-1_719', 'ota-FM-1_719', 'FM-1_719']),
                                   (True, ['ota-FM-1_719', 'FM-1_719'])):
            sessions = [Mock() for _ in identities]
            for session in sessions:
                session.close.return_value = []
                session.loader_control.return_value = ready_status(dirty=resume)
            with patch.object(updater, 'find_session', side_effect=sessions) as find, patch.object(updater, 'serve') as serve:
                updater.perform_update(Mock(), candidate, RecordJournal(), resume=resume)
            self.assertEqual([call.args[1] for call in find.call_args_list], identities)
            self.assertEqual([call.args[2] for call in serve.call_args_list], [2] if resume else [1, 2])
        for changed in (
            {'origin_app_sha256': pkg.INSTALLED_719_APP_SHA256},
            {'origin_package_sha256': pkg.INSTALLED_719_PACKAGE_SHA256},
            {'origin_app_sha256': pkg.INSTALLED_718_APP_SHA256},
            {'origin_package_sha256': pkg.INSTALLED_718_PACKAGE_SHA256},
            {'origin_app_sha256': '0'*64}, {'origin_package_sha256': None},
            {'origin_identity': 'FM-1_718'}, {'loader_identity': 'ota-FM-1_718'},
            {'runtime_preflight_qualified': False}, {'template': pkg.PUBLISHED_TEMPLATE},
        ):
            invalid = updater.QualifiedPackage(original.image, dict(report, **changed), 1024, 2048)
            with self.subTest(changed=changed), patch.object(updater, 'find_session') as find, self.assertRaises(updater.UpdateError):
                updater.perform_update(Mock(), invalid, RecordJournal())
            find.assert_not_called()

    def test_optimized719_routes_require_paired_third719_hashes_before_device_access(self):
        import fm1_package as pkg
        original = qualified_package()
        report = dict(original.report, product='FM-1_719', origin_identity='FM-1_719', loader_identity='ota-FM-1_719',
                      origin_app_sha256=pkg.INSTALLED_719_FINAL_APP_SHA256,
                      origin_package_sha256=pkg.INSTALLED_719_FINAL_PACKAGE_SHA256, template=pkg.TEST01_TEMPLATE)
        candidate = updater.QualifiedPackage(original.image, report, 1024, 2048)
        self.assertEqual(updater.update_identities(candidate), ('FM-1_719', 'ota-FM-1_719', 'FM-1_719'))
        for resume, identities in ((False, ['FM-1_719', 'ota-FM-1_719', 'FM-1_719']),
                                   (True, ['ota-FM-1_719', 'FM-1_719'])):
            sessions = [Mock() for _ in identities]
            for session in sessions:
                session.close.return_value = []
                session.loader_control.return_value = ready_status(dirty=resume)
            with patch.object(updater, 'find_session', side_effect=sessions) as find, patch.object(updater, 'serve') as serve:
                updater.perform_update(Mock(), candidate, RecordJournal(), resume=resume)
            self.assertEqual([call.args[1] for call in find.call_args_list], identities)
            self.assertEqual([call.args[2] for call in serve.call_args_list], [2] if resume else [1, 2])
        for changed in (
            {'origin_app_sha256': pkg.INSTALLED_719_CORRECTED_APP_SHA256},
            {'origin_package_sha256': pkg.INSTALLED_719_CORRECTED_PACKAGE_SHA256},
            {'origin_app_sha256': pkg.INSTALLED_719_APP_SHA256},
            {'origin_package_sha256': pkg.INSTALLED_719_PACKAGE_SHA256},
            {'origin_app_sha256': pkg.INSTALLED_718_APP_SHA256},
            {'origin_package_sha256': pkg.INSTALLED_718_PACKAGE_SHA256},
            {'origin_app_sha256': '0'*64}, {'origin_package_sha256': None},
            {'origin_identity': 'FM-1_718'}, {'loader_identity': 'ota-FM-1_718'},
            {'runtime_preflight_qualified': False}, {'template': pkg.PUBLISHED_TEMPLATE},
        ):
            invalid = updater.QualifiedPackage(original.image, dict(report, **changed), 1024, 2048)
            with self.subTest(changed=changed), patch.object(updater, 'find_session') as find, self.assertRaises(updater.UpdateError):
                updater.perform_update(Mock(), invalid, RecordJournal())
            find.assert_not_called()

    def test_arithmetic719_routes_require_paired_fourth719_hashes_before_device_access(self):
        import fm1_package as pkg
        original = qualified_package()
        report = dict(original.report, product='FM-1_719', origin_identity='FM-1_719', loader_identity='ota-FM-1_719',
                      origin_app_sha256=pkg.INSTALLED_719_OPTIMIZED_APP_SHA256,
                      origin_package_sha256=pkg.INSTALLED_719_OPTIMIZED_PACKAGE_SHA256, template=pkg.TEST01_TEMPLATE)
        candidate = updater.QualifiedPackage(original.image, report, 1024, 2048)
        self.assertEqual(updater.update_identities(candidate), ('FM-1_719', 'ota-FM-1_719', 'FM-1_719'))
        for resume, identities in ((False, ['FM-1_719', 'ota-FM-1_719', 'FM-1_719']),
                                   (True, ['ota-FM-1_719', 'FM-1_719'])):
            sessions = [Mock() for _ in identities]
            for session in sessions:
                session.close.return_value = []
                session.loader_control.return_value = ready_status(dirty=resume)
            with patch.object(updater, 'find_session', side_effect=sessions) as find, patch.object(updater, 'serve') as serve:
                updater.perform_update(Mock(), candidate, RecordJournal(), resume=resume)
            self.assertEqual([call.args[1] for call in find.call_args_list], identities)
            self.assertEqual([call.args[2] for call in serve.call_args_list], [2] if resume else [1, 2])
        for changed in (
            {'origin_app_sha256': pkg.INSTALLED_719_FINAL_APP_SHA256},
            {'origin_package_sha256': pkg.INSTALLED_719_FINAL_PACKAGE_SHA256},
            {'origin_app_sha256': pkg.INSTALLED_719_CORRECTED_APP_SHA256},
            {'origin_package_sha256': pkg.INSTALLED_719_CORRECTED_PACKAGE_SHA256},
            {'origin_app_sha256': pkg.INSTALLED_719_APP_SHA256},
            {'origin_package_sha256': pkg.INSTALLED_719_PACKAGE_SHA256},
            {'origin_app_sha256': pkg.INSTALLED_718_APP_SHA256},
            {'origin_package_sha256': pkg.INSTALLED_718_PACKAGE_SHA256},
            {'origin_app_sha256': '0'*64}, {'origin_package_sha256': None},
            {'origin_identity': 'FM-1_718'}, {'loader_identity': 'ota-FM-1_718'},
            {'runtime_preflight_qualified': False}, {'template': pkg.PUBLISHED_TEMPLATE},
        ):
            invalid = updater.QualifiedPackage(original.image, dict(report, **changed), 1024, 2048)
            with self.subTest(changed=changed), patch.object(updater, 'find_session') as find, self.assertRaises(updater.UpdateError):
                updater.perform_update(Mock(), invalid, RecordJournal())
            find.assert_not_called()

    def test_phaser719_routes_require_paired_fifth719_hashes_before_device_access(self):
        import fm1_package as pkg
        original = qualified_package()
        report = dict(original.report, product='FM-1_719', origin_identity='FM-1_719', loader_identity='ota-FM-1_719',
                      origin_app_sha256=pkg.INSTALLED_719_ARITHMETIC_APP_SHA256,
                      origin_package_sha256=pkg.INSTALLED_719_ARITHMETIC_PACKAGE_SHA256, template=pkg.TEST01_TEMPLATE)
        candidate = updater.QualifiedPackage(original.image, report, 1024, 2048)
        self.assertEqual(updater.update_identities(candidate), ('FM-1_719', 'ota-FM-1_719', 'FM-1_719'))
        for resume, identities in ((False, ['FM-1_719', 'ota-FM-1_719', 'FM-1_719']),
                                   (True, ['ota-FM-1_719', 'FM-1_719'])):
            sessions = [Mock() for _ in identities]
            for session in sessions:
                session.close.return_value = []
                session.loader_control.return_value = ready_status(dirty=resume)
            with patch.object(updater, 'find_session', side_effect=sessions) as find, patch.object(updater, 'serve') as serve:
                updater.perform_update(Mock(), candidate, RecordJournal(), resume=resume)
            self.assertEqual([call.args[1] for call in find.call_args_list], identities)
            self.assertEqual([call.args[2] for call in serve.call_args_list], [2] if resume else [1, 2])
        for changed in (
            {'origin_app_sha256': pkg.INSTALLED_719_OPTIMIZED_APP_SHA256},
            {'origin_package_sha256': pkg.INSTALLED_719_OPTIMIZED_PACKAGE_SHA256},
            {'origin_app_sha256': pkg.INSTALLED_719_FINAL_APP_SHA256},
            {'origin_package_sha256': pkg.INSTALLED_719_FINAL_PACKAGE_SHA256},
            {'origin_app_sha256': pkg.INSTALLED_719_CORRECTED_APP_SHA256},
            {'origin_package_sha256': pkg.INSTALLED_719_CORRECTED_PACKAGE_SHA256},
            {'origin_app_sha256': pkg.INSTALLED_719_APP_SHA256},
            {'origin_package_sha256': pkg.INSTALLED_719_PACKAGE_SHA256},
            {'origin_app_sha256': pkg.INSTALLED_718_APP_SHA256},
            {'origin_package_sha256': pkg.INSTALLED_718_PACKAGE_SHA256},
            {'origin_app_sha256': '0'*64}, {'origin_package_sha256': None},
            {'origin_identity': 'FM-1_718'}, {'loader_identity': 'ota-FM-1_718'},
            {'runtime_preflight_qualified': False}, {'template': pkg.PUBLISHED_TEMPLATE},
        ):
            invalid = updater.QualifiedPackage(original.image, dict(report, **changed), 1024, 2048)
            with self.subTest(changed=changed), patch.object(updater, 'find_session') as find, self.assertRaises(updater.UpdateError):
                updater.perform_update(Mock(), invalid, RecordJournal())
            find.assert_not_called()

    def test_dispatch719_routes_require_paired_sixth719_hashes_before_device_access(self):
        import fm1_package as pkg
        original = qualified_package()
        report = dict(original.report, product='FM-1_719', origin_identity='FM-1_719', loader_identity='ota-FM-1_719',
                      origin_app_sha256=pkg.INSTALLED_719_PHASER_APP_SHA256,
                      origin_package_sha256=pkg.INSTALLED_719_PHASER_PACKAGE_SHA256, template=pkg.TEST01_TEMPLATE)
        candidate = updater.QualifiedPackage(original.image, report, 1024, 2048)
        self.assertEqual(updater.update_identities(candidate), ('FM-1_719', 'ota-FM-1_719', 'FM-1_719'))
        for resume, identities in ((False, ['FM-1_719', 'ota-FM-1_719', 'FM-1_719']),
                                   (True, ['ota-FM-1_719', 'FM-1_719'])):
            sessions = [Mock() for _ in identities]
            for session in sessions:
                session.close.return_value = []
                session.loader_control.return_value = ready_status(dirty=resume)
            with patch.object(updater, 'find_session', side_effect=sessions) as find, patch.object(updater, 'serve') as serve:
                updater.perform_update(Mock(), candidate, RecordJournal(), resume=resume)
            self.assertEqual([call.args[1] for call in find.call_args_list], identities)
            self.assertEqual([call.args[2] for call in serve.call_args_list], [2] if resume else [1, 2])
        for changed in (
            {'origin_app_sha256': pkg.INSTALLED_719_ARITHMETIC_APP_SHA256},
            {'origin_package_sha256': pkg.INSTALLED_719_ARITHMETIC_PACKAGE_SHA256},
            {'origin_app_sha256': pkg.INSTALLED_719_OPTIMIZED_APP_SHA256},
            {'origin_package_sha256': pkg.INSTALLED_719_OPTIMIZED_PACKAGE_SHA256},
            {'origin_app_sha256': pkg.INSTALLED_719_FINAL_APP_SHA256},
            {'origin_package_sha256': pkg.INSTALLED_719_FINAL_PACKAGE_SHA256},
            {'origin_app_sha256': pkg.INSTALLED_719_CORRECTED_APP_SHA256},
            {'origin_package_sha256': pkg.INSTALLED_719_CORRECTED_PACKAGE_SHA256},
            {'origin_app_sha256': pkg.INSTALLED_719_APP_SHA256},
            {'origin_package_sha256': pkg.INSTALLED_719_PACKAGE_SHA256},
            {'origin_app_sha256': pkg.INSTALLED_718_APP_SHA256},
            {'origin_package_sha256': pkg.INSTALLED_718_PACKAGE_SHA256},
            {'origin_app_sha256': '0'*64}, {'origin_package_sha256': None},
            {'origin_identity': 'FM-1_718'}, {'loader_identity': 'ota-FM-1_718'},
            {'runtime_preflight_qualified': False}, {'template': pkg.PUBLISHED_TEMPLATE},
        ):
            invalid = updater.QualifiedPackage(original.image, dict(report, **changed), 1024, 2048)
            with self.subTest(changed=changed), patch.object(updater, 'find_session') as find, self.assertRaises(updater.UpdateError):
                updater.perform_update(Mock(), invalid, RecordJournal())
            find.assert_not_called()

    def test_loader_probe_observes_190_seconds_after_valid_status_without_stage2_or_abort(self):
        clock, journal = [0.0], RecordJournal()
        stock, loader = Mock(), Mock()
        stock.close.return_value = loader.close.return_value = []
        def read_status(operation):
            self.assertEqual(operation, updater.CONTROL_STATUS)
            if not loader.loader_control.call_count > 1:
                clock[0] += 1.5  # initial status work is outside the hold window
            return ready_status()
        loader.loader_control.side_effect = read_status
        with patch.object(updater, "find_session", side_effect=[stock, loader]) as find, \
             patch.object(updater, "serve") as serve, \
             patch.object(updater.time, "monotonic", side_effect=lambda: clock[0]), \
             patch.object(updater.time, "sleep", side_effect=lambda seconds: clock.__setitem__(0, clock[0] + seconds)):
            updater.perform_loader_probe(object(), qualified_package(), journal)
        self.assertEqual([call.args[1] for call in find.call_args_list], [updater.STOCK_ID, updater.LOADER_ID])
        self.assertEqual(find.call_args_list[1].kwargs["wait"], 45.0)
        self.assertTrue(find.call_args_list[1].kwargs["retry_identity_timeout"])
        serve.assert_called_once_with(stock, unittest.mock.ANY, 1, journal)
        stock.loader_control.assert_not_called()
        self.assertEqual(loader.loader_control.call_count, 39)
        samples = [event for event in journal.events if event["event"] == "loader_probe_sample"]
        self.assertEqual([sample["elapsed_seconds"] for sample in samples], list(range(0, 191, 5)))
        self.assertEqual(clock[0], 191.5)
        self.assertFalse(journal.events[-1]["app_upgrade_sent"])
        stock.close.assert_called_once()
        loader.close.assert_called_once()

    def test_loader_probe_disconnect_records_last_state_and_does_not_reconnect(self):
        clock, journal = [0.0], RecordJournal()
        stock, loader = Mock(), Mock()
        stock.close.return_value = loader.close.return_value = []
        loader.loader_control.side_effect = [ready_status(), updater.UpdateError("control reply timed out")]
        with patch.object(updater, "find_session", side_effect=[stock, loader]) as find, \
             patch.object(updater, "serve") as serve, \
             patch.object(updater.time, "monotonic", side_effect=lambda: clock[0]), \
             patch.object(updater.time, "sleep", side_effect=lambda seconds: clock.__setitem__(0, clock[0] + seconds)):
            with self.assertRaisesRegex(updater.UpdateError, "timed out"):
                updater.perform_loader_probe(object(), qualified_package(), journal)
        self.assertEqual(find.call_count, 2)
        serve.assert_called_once()
        self.assertEqual(journal.events[-1]["phase"], "loader_status")
        self.assertEqual(journal.events[-1]["last_status"], ready_status())
        self.assertEqual(journal.events[-1]["samples"], 1)
        loader.close.assert_called_once()

    def test_loader_probe_refuses_unqualified_bad_duration_and_invalid_initial_status(self):
        backend = Mock()
        with self.assertRaises(updater.UpdateError):
            updater.perform_loader_probe(backend, package(), RecordJournal())
        for duration in (0, -1, 191, True, float("nan"), float("inf")):
            with self.subTest(duration=duration), self.assertRaises(updater.UpdateError):
                updater.perform_loader_probe(backend, qualified_package(), RecordJournal(), duration=duration)
        backend.enumerate.assert_not_called()
        for bad_status in (ready_status(dirty=True), ready_status(state=4, error=-15)):
            stock, loader, journal = Mock(), Mock(), RecordJournal()
            stock.close.return_value = loader.close.return_value = []
            loader.loader_control.return_value = bad_status
            with patch.object(updater, "find_session", side_effect=[stock, loader]), patch.object(updater, "serve") as serve:
                with self.assertRaises(updater.UpdateError):
                    updater.perform_loader_probe(backend, qualified_package(), journal)
            serve.assert_called_once()
            loader.close.assert_called_once()
            self.assertEqual(journal.events[-1]["last_status"], bad_status)

    def test_identity_startup_retry_reopens_only_after_specific_timeout_and_clean_release(self):
        api, first, second, journal = Mock(), MagicMock(), MagicMock(), RecordJournal()
        api.target_location=None
        api.enumerate.return_value = {"inputs": [caps_row()], "outputs": [caps_row(2)]}
        first.identify.side_effect = updater.IdentityTimeout("Identity reply timed out")
        first.close.return_value = second.close.return_value = []
        second.identify.return_value = updater.LOADER_ID
        with patch.object(updater, "MidiSession", side_effect=[first, second]), patch.object(updater.time, "sleep"):
            result = updater.find_session(api, updater.LOADER_ID, journal, wait=45, retry_identity_timeout=True)
        self.assertIs(result, second)
        first.close.assert_called_once()
        second.close.assert_not_called()
        self.assertEqual(journal.events[-1]["event"], "identity_timeout")
        self.assertTrue(journal.events[-1]["retry_allowed"])

    def test_discovery_logs_visible_ports_and_refuses_missing_pairs_without_opening(self):
        cases=[({'inputs':[], 'outputs':[]},'no_ports'),
               ({'inputs':[dict(id=0,name='Other synth')], 'outputs':[]},'unrecognized_ports'),
               ({'inputs':[caps_row()], 'outputs':[]},'incomplete_pair')]
        for ports,reason in cases:
            api,journal=Mock(),RecordJournal();api.target_location=None;api.enumerate.return_value=ports
            with self.subTest(reason=reason),patch.object(updater,'MidiSession') as session:
                with self.assertRaisesRegex(updater.UpdateError,'discovery:'+reason):
                    updater.find_session(api,None,journal,wait=0)
                session.assert_not_called()
            self.assertEqual(journal.events[0]['event'],'discovery_ports')
            self.assertEqual(journal.events[-1]['reason'],reason)
            self.assertEqual(journal.events[-1]['visible_ports']['inputs'],[{k:r[k] for k in ('id','name')} for r in ports['inputs']])

    def test_unchanged_discovery_ports_are_not_logged_every_poll(self):
        api,journal=Mock(),RecordJournal();api.target_location=None
        api.enumerate.return_value={'inputs':[], 'outputs':[]}
        with patch.object(updater.time,'monotonic',side_effect=[0,0,0,1]),patch.object(updater.time,'sleep'):
            with self.assertRaises(updater.UpdateError):updater.find_session(api,None,journal,wait=1)
        self.assertEqual([e['event'] for e in journal.events],['discovery_ports','discovery_timeout'])

    def test_identity_retry_refuses_wrong_identity_other_errors_and_failed_cleanup(self):
        for failure, identity, cleanup, retries in (
                (None, "ota-FM-1_999", [], True),
                (updater.UpdateError("malformed identity"), None, [], True),
                (updater.IdentityTimeout("Identity reply timed out"), None, ["close failed"], True),
                (updater.IdentityTimeout("Identity reply timed out"), None, [], False)):
            api, session = Mock(), MagicMock()
            api.target_location=None
            api.enumerate.return_value = {"inputs": [caps_row()], "outputs": [caps_row(2)]}
            session.identify.side_effect, session.identify.return_value = failure, identity
            session.close.return_value = cleanup
            with patch.object(updater, "MidiSession", return_value=session) as constructor:
                with self.subTest(failure=failure, identity=identity, cleanup=cleanup), self.assertRaises(updater.UpdateError):
                    updater.find_session(api, updater.LOADER_ID, RecordJournal(), wait=45, retry_identity_timeout=retries)
            constructor.assert_called_once()
            session.close.assert_called_once()

    def test_identity_timeout_retries_stop_at_bounded_startup_deadline(self):
        clock, api, journal = [0.0], Mock(), RecordJournal()
        api.target_location=None
        api.enumerate.return_value = {"inputs": [caps_row()], "outputs": [caps_row(2)]}
        sessions = []
        def new_session(*args):
            session = MagicMock()
            session.close.return_value = []
            def timeout():
                clock[0] += 2
                raise updater.IdentityTimeout("Identity reply timed out")
            session.identify.side_effect = timeout
            sessions.append(session)
            return session
        with patch.object(updater, "MidiSession", side_effect=new_session), \
             patch.object(updater.time, "monotonic", side_effect=lambda: clock[0]), \
             patch.object(updater.time, "sleep", side_effect=lambda seconds: clock.__setitem__(0, clock[0] + seconds)):
            with self.assertRaisesRegex(updater.UpdateError, "Timed out waiting"):
                updater.find_session(api, updater.LOADER_ID, journal, wait=45, retry_identity_timeout=True)
        self.assertLessEqual(clock[0], 47)
        self.assertGreaterEqual(clock[0], 45)
        self.assertEqual(len([e for e in journal.events if e['event']=='identity_timeout']), len(sessions))
        self.assertEqual(journal.events[-1]['event'], 'discovery_timeout')
        self.assertEqual(journal.events[-1]['reason'], 'identity_timeout')
        for session in sessions:
            session.close.assert_called_once()

    def test_completed_stage_accepts_stop_nodriver_only_after_full_release(self):
        class DisconnectedWinMM(FakeWinMM):
            def checked(self, name, *args):
                super().checked(name, *args)
                if name == "midiInStop":
                    raise bridge.WinMMError(name, 6)
        api, journal = DisconnectedWinMM(), RecordJournal()
        session = updater.MidiSession(api, (caps_row(), caps_row(2)), journal)
        session.__enter__()
        stage = updater.PullStage(package(), 1, updater.time.monotonic())
        session.answer(stage, request(512, 512))
        session.answer(stage, request(updater.VERIFY_DONE, 8))
        self.assertEqual(session.completed_stage, 1)
        self.assertEqual(session.close(), [])
        self.assertNotIn(session, bridge._unreleased_sessions)
        self.assertTrue(any(event["event"] == "expected_mode_switch_disconnect" for event in journal.events))
        self.assertEqual(sum(call["operation"] == "midiInUnprepareHeader" and call["ok"]
                             for call in session.cleanup_results), 4)

    def test_stop_nodriver_is_fatal_before_terminal_or_with_any_other_cleanup_error(self):
        for completed, extra, result in ((None, None, 6), (1, "midiInReset", 6),
                                         (1, "midiInUnprepareHeader", 6), (2, "midiOutClose", 6),
                                         (1, None, 5)):
            class BrokenWinMM(FakeWinMM):
                def checked(self, name, *args):
                    super().checked(name, *args)
                    if name == "midiInStop":
                        raise bridge.WinMMError(name, result)
                    if name == extra:
                        raise bridge.WinMMError(name, 5)
            session = updater.MidiSession(BrokenWinMM(), (caps_row(), caps_row(2)), RecordJournal())
            session.__enter__()
            session.completed_stage = completed
            with self.subTest(completed=completed, extra=extra, result=result):
                self.assertTrue(session.close())
                self.assertIn(session, bridge._unreleased_sessions)
            bridge._unreleased_sessions.remove(session)

    def test_every_supported_loader_has_exact_loader_control_admission(self):
        # Catalog releases can use a loader with its own version (734 uses935).
        # Never infer a callable updater from an application identity.
        for identity in updater.SUPPORTED_LOADER_IDS:
            with self.subTest(identity=identity):
                session = object.__new__(updater.MidiSession)
                session.expected_loader_identity = session.verified_identity = identity
                session._send = Mock()
                session.read = Mock(return_value=b"status")
                session.journal = RecordJournal()
                with patch.object(updater, "parse_loader_control_reply", return_value=ready_status()):
                    self.assertEqual(session.loader_control(updater.CONTROL_STATUS), ready_status())
                session._send.assert_called_once()

    def test_fmer_control_never_sends_without_matching_loader_identity(self):
        api = FakeWinMM()
        with updater.MidiSession(api, (caps_row(), caps_row(2)), RecordJournal()) as session:
            for identity in (None, updater.STOCK_ID, updater.TARGET_ID, "ota-FM-1_900", "ota-FM-1_734"):
                session.verified_identity = identity
                with self.assertRaises(updater.UpdateError):
                    session.loader_control(1)
        self.assertNotIn("midiOutLongMsg", [name for name, args in api.calls])

    def test_update_order_reenumerates_and_verifies_exact_final_identity(self):
        qualified = qualified_package()
        journal = RecordJournal()
        from unittest.mock import Mock
        sessions = [Mock() for _ in range(3)]
        for session in sessions:
            session.close.return_value = []
            session.loader_control.return_value = ready_status()
        with patch.object(updater, "find_session", side_effect=sessions) as find, \
             patch.object(updater, "serve") as serve:
            updater.perform_update(object(), qualified, journal)
        self.assertEqual([call.args[1] for call in find.call_args_list], [updater.STOCK_ID, updater.LOADER_ID, updater.TARGET_ID])
        self.assertEqual([call.args[2] for call in serve.call_args_list], [1, 2])
        self.assertTrue(any(event["event"] == "post_reboot_identity_verified" for event in journal.events))
        for session in sessions:
            session.close.assert_called_once()

    def test_702_uses_only_explicit_701_origin_and_702_loader_target(self):
        candidate = successor_package()
        for resume, identities in [(False, ["FM-1_701", "ota-FM-1_702", "FM-1_702"]),
                                   (True, ["ota-FM-1_702", "FM-1_702"])]:
            sessions = [Mock() for _ in identities]
            for session in sessions:
                session.close.return_value = []
                session.loader_control.return_value = ready_status(dirty=resume)
            journal = RecordJournal()
            with patch.object(updater, "find_session", side_effect=sessions) as find, patch.object(updater, "serve") as serve:
                updater.perform_update(Mock(), candidate, journal, resume=resume)
            self.assertEqual([c.args[1] for c in find.call_args_list], identities)
            self.assertEqual([c.args[2] for c in serve.call_args_list], [2] if resume else [1, 2])
            self.assertEqual(journal.events[-1]["identity"], "FM-1_702")

    def test_702_refuses_origin_tampering_or_missing_qualification_before_device_access(self):
        original = successor_package()
        for change in ({"origin_identity": "FM-1_015"}, {"loader_identity": "ota-FM-1_701"},
                       {"product": "FM-1_703"}, {"origin_app_sha256": "0" * 64},
                       {"origin_package_sha256": "1" * 64}, {"template": "published-v15"},
                       {"runtime_preflight_qualified": False, "stock_v15_handoff_qualified": True}):
            candidate = updater.QualifiedPackage(original.image, dict(original.report, **change), 1024, 2048)
            with patch.object(updater, "find_session") as find, self.subTest(change=change), self.assertRaises(updater.UpdateError):
                updater.perform_update(Mock(), candidate, RecordJournal())
            find.assert_not_called()

    def test_702_fresh_update_refuses_dirty_origin_before_application_stage(self):
        origin, loader = Mock(), Mock()
        origin.close.return_value = loader.close.return_value = []
        loader.loader_control.return_value = ready_status(dirty=True)
        with patch.object(updater, "find_session", side_effect=[origin, loader]), patch.object(updater, "serve") as serve:
            with self.assertRaises(updater.UpdateError):
                updater.perform_update(Mock(), successor_package(), RecordJournal())
        self.assertEqual([c.args[2] for c in serve.call_args_list], [1])

    def test_703_route_refuses_701_origin_and_resumes_only_703_loader(self):
        candidate = successor_package(updater.CURRENT_TARGET_ID)
        for resume, expected in [(False, ["FM-1_702", "ota-FM-1_703", "FM-1_703"]),
                                 (True, ["ota-FM-1_703", "FM-1_703"])]:
            sessions = [Mock() for _ in expected]
            for session in sessions:
                session.close.return_value = []
                session.loader_control.return_value = ready_status(dirty=resume)
            with patch.object(updater, "find_session", side_effect=sessions) as find, patch.object(updater, "serve") as serve:
                updater.perform_update(Mock(), candidate, RecordJournal(), resume=resume)
            self.assertEqual([call.args[1] for call in find.call_args_list], expected)
            self.assertEqual([call.args[2] for call in serve.call_args_list], [2] if resume else [1,2])
        old = successor_package().report
        for key in ("origin_identity", "loader_identity", "origin_app_sha256", "origin_package_sha256"):
            bad = updater.QualifiedPackage(candidate.image, dict(candidate.report, **{key: old[key]}),1024,2048)
            with self.subTest(key=key), patch.object(updater, "find_session") as find, self.assertRaises(updater.UpdateError):
                updater.perform_update(Mock(), bad, RecordJournal())
            find.assert_not_called()

    def test_704_route_refuses_702_origin_and_resumes_only_704_loader(self):
        candidate = successor_package(updater.BUILD_TARGET_ID)
        for resume, expected in [(False, ["FM-1_703", "ota-FM-1_704", "FM-1_704"]),
                                 (True, ["ota-FM-1_704", "FM-1_704"])]:
            sessions = [Mock() for _ in expected]
            for session in sessions:
                session.close.return_value = []
                session.loader_control.return_value = ready_status(dirty=resume)
            with patch.object(updater, "find_session", side_effect=sessions) as find, patch.object(updater, "serve") as serve:
                updater.perform_update(Mock(), candidate, RecordJournal(), resume=resume)
            self.assertEqual([call.args[1] for call in find.call_args_list], expected)
            self.assertEqual([call.args[2] for call in serve.call_args_list], [2] if resume else [1,2])
        old = successor_package(updater.CURRENT_TARGET_ID).report
        for key in ("origin_identity", "loader_identity", "origin_app_sha256", "origin_package_sha256"):
            bad = updater.QualifiedPackage(candidate.image, dict(candidate.report, **{key: old[key]}),1024,2048)
            with self.subTest(key=key), patch.object(updater, "find_session") as find, self.assertRaises(updater.UpdateError):
                updater.perform_update(Mock(), bad, RecordJournal())
            find.assert_not_called()

    def test_705_route_refuses_703_origin_and_resumes_only_705_loader(self):
        candidate = successor_package(updater.LATEST_TARGET_ID)
        for resume, expected in [(False, ["FM-1_704", "ota-FM-1_705", "FM-1_705"]),
                                 (True, ["ota-FM-1_705", "FM-1_705"])]:
            sessions = [Mock() for _ in expected]
            for session in sessions:
                session.close.return_value = []
                session.loader_control.return_value = ready_status(dirty=resume)
            with patch.object(updater, "find_session", side_effect=sessions) as find, patch.object(updater, "serve") as serve:
                updater.perform_update(Mock(), candidate, RecordJournal(), resume=resume)
            self.assertEqual([call.args[1] for call in find.call_args_list], expected)
            self.assertEqual([call.args[2] for call in serve.call_args_list], [2] if resume else [1,2])
        old = successor_package(updater.BUILD_TARGET_ID).report
        for key in ("origin_identity", "loader_identity", "origin_app_sha256", "origin_package_sha256"):
            bad = updater.QualifiedPackage(candidate.image, dict(candidate.report, **{key: old[key]}),1024,2048)
            with self.subTest(key=key), patch.object(updater, "find_session") as find, self.assertRaises(updater.UpdateError):
                updater.perform_update(Mock(), bad, RecordJournal())
            find.assert_not_called()

    def test_706_route_refuses_704_origin_and_resumes_only_706_loader(self):
        candidate = successor_package(updater.DEVELOPMENT_TARGET_ID)
        for resume, expected in [(False, ["FM-1_705", "ota-FM-1_706", "FM-1_706"]),
                                 (True, ["ota-FM-1_706", "FM-1_706"])]:
            sessions = [Mock() for _ in expected]
            for session in sessions:
                session.close.return_value = []
                session.loader_control.return_value = ready_status(dirty=resume)
            with patch.object(updater, "find_session", side_effect=sessions) as find, patch.object(updater, "serve") as serve:
                updater.perform_update(Mock(), candidate, RecordJournal(), resume=resume)
            self.assertEqual([call.args[1] for call in find.call_args_list], expected)
            self.assertEqual([call.args[2] for call in serve.call_args_list], [2] if resume else [1,2])
        old = successor_package(updater.LATEST_TARGET_ID).report
        for key in ("origin_identity", "loader_identity", "origin_app_sha256", "origin_package_sha256"):
            bad = updater.QualifiedPackage(candidate.image, dict(candidate.report, **{key: old[key]}),1024,2048)
            with self.subTest(key=key), patch.object(updater, "find_session") as find, self.assertRaises(updater.UpdateError):
                updater.perform_update(Mock(), bad, RecordJournal())
            find.assert_not_called()

    def test_707_route_refuses_705_origin_and_resumes_only_707_loader(self):
        candidate = successor_package(updater.CANDIDATE_TARGET_ID)
        for resume, expected in [(False, ["FM-1_706", "ota-FM-1_707", "FM-1_707"]),
                                 (True, ["ota-FM-1_707", "FM-1_707"])]:
            sessions = [Mock() for _ in expected]
            for session in sessions:
                session.close.return_value = []
                session.loader_control.return_value = ready_status(dirty=resume)
            with patch.object(updater, "find_session", side_effect=sessions) as find, patch.object(updater, "serve") as serve:
                updater.perform_update(Mock(), candidate, RecordJournal(), resume=resume)
            self.assertEqual([call.args[1] for call in find.call_args_list], expected)
            self.assertEqual([call.args[2] for call in serve.call_args_list], [2] if resume else [1,2])
        old = successor_package(updater.DEVELOPMENT_TARGET_ID).report
        for key in ("origin_identity", "loader_identity", "origin_app_sha256", "origin_package_sha256"):
            bad = updater.QualifiedPackage(candidate.image, dict(candidate.report, **{key: old[key]}),1024,2048)
            with self.subTest(key=key), patch.object(updater, "find_session") as find, self.assertRaises(updater.UpdateError):
                updater.perform_update(Mock(), bad, RecordJournal())
            find.assert_not_called()

    def test_708_route_refuses_706_origin_and_resumes_only_708_loader(self):
        candidate = successor_package(updater.INSTRUMENT_TARGET_ID)
        for resume, expected in [(False, ["FM-1_707", "ota-FM-1_708", "FM-1_708"]),
                                 (True, ["ota-FM-1_708", "FM-1_708"])]:
            sessions = [Mock() for _ in expected]
            for session in sessions:
                session.close.return_value = []
                session.loader_control.return_value = ready_status(dirty=resume)
            with patch.object(updater, "find_session", side_effect=sessions) as find, patch.object(updater, "serve") as serve:
                updater.perform_update(Mock(), candidate, RecordJournal(), resume=resume)
            self.assertEqual([call.args[1] for call in find.call_args_list], expected)
            self.assertEqual([call.args[2] for call in serve.call_args_list], [2] if resume else [1,2])
        old = successor_package(updater.CANDIDATE_TARGET_ID).report
        for key in ("origin_identity", "loader_identity", "origin_app_sha256", "origin_package_sha256"):
            bad = updater.QualifiedPackage(candidate.image, dict(candidate.report, **{key: old[key]}),1024,2048)
            with self.subTest(key=key), patch.object(updater, "find_session") as find, self.assertRaises(updater.UpdateError):
                updater.perform_update(Mock(), bad, RecordJournal())
            find.assert_not_called()

    def test_709_route_refuses_707_origin_and_resumes_only_709_loader(self):
        candidate = successor_package(updater.BANK_TARGET_ID)
        for resume, expected in [(False, ["FM-1_708", "ota-FM-1_709", "FM-1_709"]),
                                 (True, ["ota-FM-1_709", "FM-1_709"])]:
            sessions = [Mock() for _ in expected]
            for session in sessions:
                session.close.return_value = []
                session.loader_control.return_value = ready_status(dirty=resume)
            with patch.object(updater, "find_session", side_effect=sessions) as find, patch.object(updater, "serve") as serve:
                updater.perform_update(Mock(), candidate, RecordJournal(), resume=resume)
            self.assertEqual([call.args[1] for call in find.call_args_list], expected)
            self.assertEqual([call.args[2] for call in serve.call_args_list], [2] if resume else [1,2])
        old = successor_package(updater.INSTRUMENT_TARGET_ID).report
        for key in ("origin_identity", "loader_identity", "origin_app_sha256", "origin_package_sha256"):
            bad = updater.QualifiedPackage(candidate.image, dict(candidate.report, **{key: old[key]}),1024,2048)
            with self.subTest(key=key), patch.object(updater, "find_session") as find, self.assertRaises(updater.UpdateError):
                updater.perform_update(Mock(), bad, RecordJournal())
            find.assert_not_called()

    def test_loader_control_rejects_a_different_known_version_without_sending(self):
        with updater.MidiSession(FakeWinMM(), (caps_row(), caps_row(2)), RecordJournal()) as session:
            session.verified_identity = updater.LOADER_ID
            session.expected_loader_identity = updater.NEXT_LOADER_ID
            with patch.object(session, "_send") as send, self.assertRaises(updater.UpdateError):
                session.loader_control(updater.CONTROL_STATUS)
            send.assert_not_called()

    def test_stage_failure_stops_without_automatic_retry_or_abort(self):
        qualified = qualified_package()
        from unittest.mock import Mock
        session = Mock(); session.close.return_value = []
        with patch.object(updater, "find_session", return_value=session) as find, \
             patch.object(updater, "serve", side_effect=updater.UpdateError("injected")):
            with self.assertRaises(updater.UpdateError):
                updater.perform_update(object(), qualified, RecordJournal())
        find.assert_called_once()
        session.close.assert_called_once()
        session.loader_control.assert_not_called()

    def test_direct_update_api_also_refuses_unqualified_package(self):
        from unittest.mock import Mock
        backend = Mock()
        with self.assertRaises(updater.UpdateError):
            updater.perform_update(backend, package(), RecordJournal())
        backend.enumerate.assert_not_called()

    def test_explicit_dirty_resume_starts_only_stage2_and_never_aborts(self):
        qualified = qualified_package()
        from unittest.mock import Mock
        loader, app = Mock(), Mock()
        loader.close.return_value = app.close.return_value = []
        loader.loader_control.return_value = ready_status(dirty=True, state=4, error=-7)
        journal = RecordJournal()
        with patch.object(updater, "find_session", side_effect=[loader, app]) as find, \
             patch.object(updater, "serve") as serve:
            updater.perform_update(object(), qualified, journal, resume=True)
        self.assertEqual([call.args[1] for call in find.call_args_list], [updater.LOADER_ID, updater.TARGET_ID])
        self.assertEqual([call.args[2] for call in serve.call_args_list], [2])
        loader.loader_control.assert_called_once_with(updater.CONTROL_STATUS)
        self.assertTrue(any(e["event"] == "explicit_resume_status" and e["status"]["app_dirty"] for e in journal.events))

    def test_loader_readiness_rejects_wrong_extent_key_flash_and_record(self):
        for change in ({"record_address": 0xE9F00}, {"record_address": 0xE4F01}, {"match_count": 2},
                       {"loader_length": 385}, {"state": 4, "error": -6}, {"state": 4, "error": -14},
                       {"state": 4, "error": -15}, {"state": 2}, {"state": 4, "error": -999}):
            with self.subTest(change=change), self.assertRaises(updater.UpdateError):
                updater.require_loader_ready(dict(ready_status(), **change), package(), resume=True)
        with self.assertRaises(updater.UpdateError):
            updater.require_loader_ready(ready_status(dirty=True), package(), resume=False)
        updater.require_loader_ready(ready_status(dirty=True), package(), resume=True)
        for error in (-5, -7, -8, -9, -10, -11, -12, -13):
            updater.require_loader_ready(ready_status(state=4, error=error), package(), resume=True)

    def test_names_refuse_unrelated_or_multiple_instruments(self):
        for name in ("FM-1 Midi", "2- FM-1 Midi", "FMER Test01", "FMER Update", "ota-FM-1"):
            pair = updater.select_pair({"inputs": [caps_row(1, name)], "outputs": [caps_row(2, name)]})
            self.assertEqual(pair[0]["name"], name)
        for name in ("USB Composite Device", "Felucca", "Other FM-1 Synth", "FMER Test02"):
            with self.assertRaises(updater.UpdateError):
                updater.select_pair({"inputs": [caps_row(1, name)], "outputs": [caps_row(2, name)]})
        with self.assertRaises(updater.UpdateError):
            updater.select_pair({"inputs": [caps_row(), caps_row(2)], "outputs": [caps_row()]})

    def test_opened_handle_caps_are_verified_before_transmission(self):
        api, journal = FakeWinMM(), RecordJournal()
        session = updater.MidiSession(api, (caps_row(4), caps_row(9)), journal)
        with session:
            caps_calls = [args[0] for name, args in api.calls if name.endswith("GetDevCapsW")]
            self.assertEqual(caps_calls, [101, 102])  # handles, never enumeration indices 4/9
            self.assertNotIn("midiOutLongMsg", [name for name, args in api.calls])

    def test_changed_handle_or_open_failure_closes_without_sends(self):
        for api in (FakeWinMM(mismatch=True), FakeWinMM(fail="midiOutOpen")):
            session = updater.MidiSession(api, (caps_row(), caps_row(2)), RecordJournal())
            with self.assertRaises((updater.UpdateError, bridge.BridgeError)):
                session.__enter__()
            names = [name for name, args in api.calls]
            self.assertNotIn("midiOutLongMsg", names)
            self.assertIn("midiInClose", names)

    def test_journal_failure_before_send_prevents_driver_action(self):
        api = FakeWinMM()
        session = updater.MidiSession(api, (caps_row(), caps_row(2)), RecordJournal("send_intent"))
        with session, self.assertRaises(OSError):
            session.begin_stage(1)
        self.assertNotIn("midiOutLongMsg", [name for name, args in api.calls])

    def test_successful_send_frees_only_completed_output(self):
        api, journal = FakeWinMM(), RecordJournal()
        with updater.MidiSession(api, (caps_row(), caps_row(2)), journal) as session:
            session.begin_stage(1)
            self.assertIsNone(session.out_buffer)
        names = [name for name, args in api.calls]
        self.assertEqual(names.count("midiOutLongMsg"), 1)
        self.assertNotIn("midiOutReset", names)
        self.assertTrue(any(e["event"] == "upgrade_intent" and e["device_writes_possible"] for e in journal.events))

    def test_callback_fragments_are_bounded_reassembled_and_requeued(self):
        api, journal = FakeWinMM(), RecordJournal()
        packet = request(1024, 512)
        with updater.MidiSession(api, (caps_row(), caps_row(2)), journal) as session:
            chunks = [packet[:7] + b"\xF8", packet[7:]]
            for (header, storage), chunk in zip(session.buffers, chunks):
                ct.memmove(header.lpData, chunk, len(chunk))
                header.dwBytesRecorded = len(chunk)
                session._callback(101, bridge.MIM_LONGDATA, 0, ct.addressof(header), 5)
            self.assertEqual(session.read(0), packet)
            self.assertIsNone(session.read(0))
            self.assertEqual(sum(name == "midiInAddBuffer" for name, args in api.calls), 6)

    def test_invalid_driver_callback_never_reads_outside_owned_buffer(self):
        for failure in ("address", "length", "longerror", "overflow"):
            with self.subTest(failure=failure):
                api = FakeWinMM()
                with updater.MidiSession(api, (caps_row(), caps_row(2)), RecordJournal()) as session:
                    header, _ = session.buffers[0]
                    if failure == "length":
                        header.dwBytesRecorded = header.dwBufferLength + 1
                    if failure == "overflow":
                        session.callback_overflow = True
                    session._callback(101, bridge.MIM_LONGERROR if failure == "longerror" else bridge.MIM_LONGDATA,
                                      0, 999 if failure == "address" else ct.addressof(header), 0)
                    with self.assertRaises(updater.UpdateError):
                        session.read(0)
                self.assertNotIn("midiOutLongMsg", [name for name, args in api.calls])

    def test_durable_journal_is_exclusive_and_records_in_order(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / "run"
            journal = updater.Journal(directory)
            journal.record("qualified", hash="test")
            journal.record("send_intent", hex="f0 f7")
            journal.close()
            records = [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()]
            self.assertEqual([r["sequence"] for r in records], [0, 1])
            with self.assertRaises(FileExistsError):
                updater.Journal(directory)

    def test_cli_refuses_unqualified_stock_handoff_before_winmm(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(updater, "qualify_package", return_value=package()), \
             patch.object(bridge, "WinMM") as backend, patch("sys.stderr", new_callable=io.StringIO):
            code = updater.main(["flash", "unused.fwsc", "--expected-sha256", "0" * 64,
                                 "--expected-loader-sha256", "1" * 64, "--artifacts-root", temp])
            self.assertEqual(code, 1)
            backend.assert_not_called()
            logs = list(Path(temp).glob("*/events.jsonl"))
            self.assertEqual(len(logs), 1)
            failure = json.loads(logs[0].read_text().splitlines()[-1])
            self.assertEqual(failure["event"], "failed")
            self.assertFalse(failure["device_writes_possible"])

    def test_qualification_rejects_wrong_hash_before_package_decoder(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.fwsc"; path.write_bytes(b"bad")
            with self.assertRaises(updater.UpdateError):
                updater.qualify_package(path, "0" * 64, "1" * 64)
            with self.assertRaises(updater.UpdateError):
                updater.qualify_package(path, "not-a-hash", "1" * 64)


if __name__ == "__main__":
    unittest.main()
