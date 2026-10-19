"""Offline candidate-format regressions; fixtures are synthetic, never device dumps."""
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import struct
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("fm1_package", Path(__file__).resolve().parents[1]/"tools/fm1_package.py")
pkg = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pkg)


def loader_fixture():
    return b"\x00\x00\x00\x00" + pkg.LOADER_MARKER + bytes(range(256))*24


def elf_fixture(kind="app"):
    base = 0x02000120 if kind == "app" else pkg.LOADER_LOAD
    code = bytes.fromhex("04818000") + (b"data" if kind == "app" else pkg.LOADER_MARKER)
    names = b"\0.text\0.bss\0.shstrtab\0"
    data = bytearray(0x300)
    data[:7] = b"\x7fELF\x01\x01\x01"
    struct.pack_into("<HHIIIIIHHHHHH", data, 16, 2, 0xF1, 1, base, 52, 0x200, 0, 52, 32, 1, 40, 4, 3)
    struct.pack_into("<IIIIIIII", data, 52, 1, 0x100, base, base, len(code), len(code)+32, 5, 4)
    data[0x100:0x100+len(code)] = code
    data[0x180:0x180+len(names)] = names
    struct.pack_into("<IIIIIIIIII", data, 0x228, 1, 1, 6, base, 0x100, len(code), 0, 0, 4, 0)
    struct.pack_into("<IIIIIIIIII", data, 0x250, 7, 8, 3, base+len(code), 0, 32, 0, 0, 4, 0)
    struct.pack_into("<IIIIIIIIII", data, 0x278, 12, 3, 0, 0, 0x180, len(names), 0, 0, 1, 0)
    return bytes(data), code


class PackageTests(unittest.TestCase):
    def test_720_release5_origin_keeps_three_finite_routes_and_rejects_mixed_digests(self):
        origins = [('719_INLINE', 'FM-1_719', 'installed_719_inline_reference'),
                   ('720_RELEASE4', 'FM-1_720', 'installed_720_release4_reference'),
                   ('720_RELEASE5', 'FM-1_720', 'installed_720_release5_reference')]
        digests = [bytes.fromhex(getattr(pkg, 'INSTALLED_'+name+'_APP_SHA256')) for name, _, _ in origins]
        with patch.object(pkg, origins[0][2]) as oldest, patch.object(pkg, origins[1][2]) as first, \
             patch.object(pkg, origins[2][2]) as second:
            for (name, identity, _), digest in zip(origins, digests):
                profile = pkg.transition_profile(pkg.PROJECT_PRODUCT, pkg.TEST01_TEMPLATE, b'code'+digest)
                self.assertEqual(profile, dict(origin_identity=identity, loader_identity='ota-FM-1_720',
                    origin_app_sha256=getattr(pkg, 'INSTALLED_'+name+'_APP_SHA256'),
                    origin_package_sha256=getattr(pkg, 'INSTALLED_'+name+'_PACKAGE_SHA256')))
            invalid = [a+b for a in digests for b in digests]+[b''.join(digests), b'', bytes(32), bytearray(digests[2])]
            invalid += [digests[2][:-1]+bytes([digests[2][-1]^1]),
                        digests[2]+bytes.fromhex(pkg.INSTALLED_719_PHASER_APP_SHA256)]
            for raw in invalid:
                with self.subTest(raw=raw.hex()), self.assertRaisesRegex(ValueError, 'fingerprint'):
                    pkg.transition_profile(pkg.PROJECT_PRODUCT, pkg.TEST01_TEMPLATE, raw)
            oldest.assert_called_once(); first.assert_called_once(); second.assert_called_once()
        with patch.object(pkg, 'installed_720_release5_reference', side_effect=ValueError('missing installation proof')), \
             self.assertRaisesRegex(ValueError, 'installation proof'):
            pkg.transition_profile(pkg.PROJECT_PRODUCT, pkg.TEST01_TEMPLATE, digests[2])

    def test_720_release5_package_validator_selects_only_its_installed_predecessor(self):
        original = self.exact_fixture()
        with patch.object(pkg, 'test01_flash_reference', return_value=original), \
             patch.object(pkg, 'sdk_file', side_effect=self.sdk.__getitem__), \
             patch.object(pkg, 'installed_719_inline_reference') as old, \
             patch.object(pkg, 'installed_720_release4_reference') as first, \
             patch.object(pkg, 'installed_720_release5_reference') as second:
            flash = pkg.flash_image(self.app+b'FM-1_720\0', pkg.KEY, pkg.TEST01_TEMPLATE)
            current = bytes.fromhex(pkg.INSTALLED_720_RELEASE5_APP_SHA256)
            def wrapped(digest):
                return pkg.ufw(flash, pkg.loader_wrap(loader_fixture()+b'ota-FM-1_720\0'+digest), pkg.PROJECT_PRODUCT)
            report = pkg.validate_package(wrapped(current))
            self.assertEqual(report['origin_identity'], 'FM-1_720')
            self.assertEqual(report['origin_package_sha256'], pkg.INSTALLED_720_RELEASE5_PACKAGE_SHA256)
            self.assertEqual(report['origin_app_sha256'], pkg.INSTALLED_720_RELEASE5_APP_SHA256)
            self.assertFalse(report['runtime_preflight_qualified'])
            old.assert_not_called(); first.assert_not_called(); second.assert_called_once()
            for invalid in (current+bytes.fromhex(pkg.INSTALLED_720_RELEASE4_APP_SHA256), current+current):
                with self.assertRaisesRegex(ValueError, 'fingerprint'): pkg.validate_package(wrapped(invalid))

    def test_720_release5_reference_requires_exact_completed_installation(self):
        with tempfile.TemporaryDirectory() as directory:
            raw, app = b'synthetic release5 package', b'synthetic release5 raw application'
            root = Path(directory); package = root/'candidate.fwsc'; package.write_bytes(raw)
            journal = root/'events.jsonl'; package_hash = hashlib.sha256(raw).hexdigest()
            events = [dict(event='qualified_before_device_access', package=dict(package_sha256=package_hash)),
                      dict(event='completed', identity='FM-1_720')]
            journal_bytes = ('\n'.join(json.dumps(event) for event in events)+'\n').encode()
            journal.write_bytes(journal_bytes)
            with patch.multiple(pkg, INSTALLED_720_RELEASE5_PACKAGE=package,
                    INSTALLED_720_RELEASE5_PACKAGE_SHA256=package_hash, INSTALLED_720_RELEASE5_JOURNAL=journal,
                    INSTALLED_720_RELEASE5_JOURNAL_SHA256=hashlib.sha256(journal_bytes).hexdigest(),
                    INSTALLED_720_RELEASE5_APP_SHA256=hashlib.sha256(app).hexdigest()), \
                 patch.object(pkg, 'validate_package', return_value=dict(template=pkg.TEST01_TEMPLATE)), \
                 patch.object(pkg, 'decode_package', return_value=('FM-1_720', b'', {'flash.bin': {'payload': bytes(0x4000)+app}})):
                self.assertEqual(pkg.installed_720_release5_reference(), app)
                for field, error in (('PACKAGE_SHA256','package SHA-256'), ('APP_SHA256','raw application SHA-256'),
                                     ('JOURNAL_SHA256','journal SHA-256')):
                    with patch.object(pkg, 'INSTALLED_720_RELEASE5_'+field, '0'*64), self.assertRaisesRegex(ValueError, error):
                        pkg.installed_720_release5_reference()
                for bad in (events[:1], [events[0], dict(event='completed', identity='FM-1_719')],
                            [dict(event='qualified_before_device_access', package=dict(package_sha256='0'*64)), events[1]]):
                    data = ('\n'.join(json.dumps(event) for event in bad)+'\n').encode(); journal.write_bytes(data)
                    with patch.object(pkg, 'INSTALLED_720_RELEASE5_JOURNAL_SHA256', hashlib.sha256(data).hexdigest()), \
                         self.assertRaisesRegex(ValueError, 'successful transition'): pkg.installed_720_release5_reference()

    def test_720_release4_origin_is_exact_and_old_inline_route_remains_finite(self):
        prior = bytes.fromhex(pkg.INSTALLED_719_INLINE_APP_SHA256)
        current = bytes.fromhex(pkg.INSTALLED_720_RELEASE4_APP_SHA256)
        with patch.object(pkg, 'installed_719_inline_reference') as old, \
             patch.object(pkg, 'installed_720_release4_reference') as installed:
            historical = pkg.transition_profile(pkg.PROJECT_PRODUCT, pkg.TEST01_TEMPLATE)
            self.assertEqual(historical['origin_identity'], 'FM-1_719')
            self.assertEqual(pkg.transition_profile(pkg.PROJECT_PRODUCT, pkg.TEST01_TEMPLATE, prior), historical)
            corrected = pkg.transition_profile(pkg.PROJECT_PRODUCT, pkg.TEST01_TEMPLATE, b'code'+current)
            self.assertEqual(corrected, dict(origin_identity='FM-1_720', loader_identity='ota-FM-1_720',
                origin_app_sha256=pkg.INSTALLED_720_RELEASE4_APP_SHA256,
                origin_package_sha256=pkg.INSTALLED_720_RELEASE4_PACKAGE_SHA256))
            older = [bytes.fromhex(getattr(pkg, prefix+'_APP_SHA256')) for prefix in
                ('INSTALLED_718', 'INSTALLED_719', 'INSTALLED_719_CORRECTED', 'INSTALLED_719_FINAL',
                 'INSTALLED_719_OPTIMIZED', 'INSTALLED_719_ARITHMETIC', 'INSTALLED_719_PHASER')]
            invalid = [b'', bytes(32), bytearray(current), current+prior, prior+current, current+current,
                       prior+prior, current[:-1]+bytes([current[-1]^1])]
            invalid += [current+digest for digest in older]+older
            for raw in invalid:
                with self.subTest(raw=raw.hex()), self.assertRaisesRegex(ValueError, 'fingerprint'):
                    pkg.transition_profile(pkg.PROJECT_PRODUCT, pkg.TEST01_TEMPLATE, raw)
            self.assertEqual(old.call_count, 2); installed.assert_called_once()
        with patch.object(pkg, 'installed_720_release4_reference', side_effect=ValueError('missing installation proof')), \
             self.assertRaisesRegex(ValueError, 'installation proof'):
            pkg.transition_profile(pkg.PROJECT_PRODUCT, pkg.TEST01_TEMPLATE, current)

    def test_720_release4_package_validator_keeps_both_exact_predecessor_routes(self):
        original = self.exact_fixture()
        with patch.object(pkg, 'test01_flash_reference', return_value=original), \
             patch.object(pkg, 'sdk_file', side_effect=self.sdk.__getitem__), \
             patch.object(pkg, 'installed_719_inline_reference') as old, \
             patch.object(pkg, 'installed_720_release4_reference') as installed:
            flash = pkg.flash_image(self.app+b'FM-1_720\0', pkg.KEY, pkg.TEST01_TEMPLATE)
            def wrapped(digest):
                return pkg.ufw(flash, pkg.loader_wrap(loader_fixture()+b'ota-FM-1_720\0'+digest), pkg.PROJECT_PRODUCT)
            historical = pkg.validate_package(wrapped(bytes.fromhex(pkg.INSTALLED_719_INLINE_APP_SHA256)))
            self.assertEqual(historical['origin_identity'], 'FM-1_719'); installed.assert_not_called()
            current = bytes.fromhex(pkg.INSTALLED_720_RELEASE4_APP_SHA256)
            report = pkg.validate_package(wrapped(current))
            self.assertEqual(report['origin_identity'], 'FM-1_720')
            self.assertEqual(report['origin_package_sha256'], pkg.INSTALLED_720_RELEASE4_PACKAGE_SHA256)
            self.assertEqual(report['origin_app_sha256'], pkg.INSTALLED_720_RELEASE4_APP_SHA256)
            self.assertFalse(report['runtime_preflight_qualified'])
            old.assert_called_once(); installed.assert_called_once()
            for invalid in (bytes(32), current+bytes.fromhex(pkg.INSTALLED_719_INLINE_APP_SHA256)):
                with self.assertRaisesRegex(ValueError, 'fingerprint'): pkg.validate_package(wrapped(invalid))

    def test_720_release4_reference_requires_package_journal_completion_and_raw_app(self):
        with tempfile.TemporaryDirectory() as directory:
            raw, app = b'synthetic release4 package', b'synthetic raw720 application'
            root = Path(directory); package = root/'candidate.fwsc'; package.write_bytes(raw)
            journal = root/'events.jsonl'; package_hash = hashlib.sha256(raw).hexdigest()
            events = [dict(event='qualified_before_device_access', package=dict(package_sha256=package_hash)),
                      dict(event='completed', identity='FM-1_720')]
            journal_bytes = ('\n'.join(json.dumps(event) for event in events)+'\n').encode()
            journal.write_bytes(journal_bytes)
            with patch.multiple(pkg, INSTALLED_720_RELEASE4_PACKAGE=package,
                    INSTALLED_720_RELEASE4_PACKAGE_SHA256=package_hash, INSTALLED_720_RELEASE4_JOURNAL=journal,
                    INSTALLED_720_RELEASE4_JOURNAL_SHA256=hashlib.sha256(journal_bytes).hexdigest(),
                    INSTALLED_720_RELEASE4_APP_SHA256=hashlib.sha256(app).hexdigest()), \
                 patch.object(pkg, 'validate_package', return_value=dict(template=pkg.TEST01_TEMPLATE)), \
                 patch.object(pkg, 'decode_package', return_value=('FM-1_720', b'', {'flash.bin': {'payload': bytes(0x4000)+app}})):
                self.assertEqual(pkg.installed_720_release4_reference(), app)
                with patch.object(pkg, 'INSTALLED_720_RELEASE4_PACKAGE_SHA256', '0'*64), \
                     self.assertRaisesRegex(ValueError, 'package SHA-256'): pkg.installed_720_release4_reference()
                with patch.object(pkg, 'INSTALLED_720_RELEASE4_APP_SHA256', '0'*64), \
                     self.assertRaisesRegex(ValueError, 'raw application SHA-256'): pkg.installed_720_release4_reference()
                journal.write_bytes(journal_bytes+b' ')
                with self.assertRaisesRegex(ValueError, 'journal SHA-256'): pkg.installed_720_release4_reference()
                for bad in (events[:1], [events[0], dict(event='completed', identity='FM-1_719')],
                            [dict(event='qualified_before_device_access', package=dict(package_sha256='0'*64)), events[1]]):
                    data = ('\n'.join(json.dumps(event) for event in bad)+'\n').encode(); journal.write_bytes(data)
                    with patch.object(pkg, 'INSTALLED_720_RELEASE4_JOURNAL_SHA256', hashlib.sha256(data).hexdigest()), \
                         self.assertRaisesRegex(ValueError, 'successful transition'): pkg.installed_720_release4_reference()

    def test_720_requires_exact_inline719_origin_and_rejects_ambiguous_loader(self):
        digest=bytes.fromhex(pkg.INSTALLED_719_INLINE_APP_SHA256)
        with patch.object(pkg,'installed_719_inline_reference') as installed:
            expected=dict(origin_identity='FM-1_719',loader_identity='ota-FM-1_720',
                          origin_app_sha256=pkg.INSTALLED_719_INLINE_APP_SHA256,
                          origin_package_sha256=pkg.INSTALLED_719_INLINE_PACKAGE_SHA256)
            self.assertEqual(pkg.transition_profile(pkg.PROJECT_PRODUCT,pkg.TEST01_TEMPLATE,b'code'+digest),expected)
            installed.assert_called_once()
            older=(pkg.INSTALLED_718_APP_SHA256,pkg.INSTALLED_719_APP_SHA256,pkg.INSTALLED_719_CORRECTED_APP_SHA256,
                   pkg.INSTALLED_719_FINAL_APP_SHA256,pkg.INSTALLED_719_OPTIMIZED_APP_SHA256,
                   pkg.INSTALLED_719_ARITHMETIC_APP_SHA256,pkg.INSTALLED_719_PHASER_APP_SHA256)
            invalid=[b'',bytes(32),bytearray(digest),digest+digest,digest[:-1]+bytes([digest[-1]^1])]
            invalid += [bytes.fromhex(value) for value in older]+[digest+bytes.fromhex(value) for value in older]
            for raw in invalid:
                with self.subTest(raw=raw.hex()),self.assertRaisesRegex(ValueError,'fingerprint'):
                    pkg.transition_profile(pkg.PROJECT_PRODUCT,pkg.TEST01_TEMPLATE,raw)
            installed.assert_called_once()
        with patch.object(pkg,'installed_719_inline_reference',side_effect=ValueError('missing installation proof')), \
             self.assertRaisesRegex(ValueError,'installation proof'):
            pkg.transition_profile(pkg.PROJECT_PRODUCT,pkg.TEST01_TEMPLATE,digest)

    def test_720_package_validator_binds_app_loader_and_exact_predecessor(self):
        original=self.exact_fixture()
        with patch.object(pkg,'test01_flash_reference',return_value=original), \
             patch.object(pkg,'sdk_file',side_effect=self.sdk.__getitem__),patch.object(pkg,'installed_719_inline_reference') as installed:
            flash=pkg.flash_image(self.app+b'FM-1_720\0',pkg.KEY,pkg.TEST01_TEMPLATE)
            loader=loader_fixture()+b'ota-FM-1_720\0'+bytes.fromhex(pkg.INSTALLED_719_INLINE_APP_SHA256)
            raw=pkg.ufw(flash,pkg.loader_wrap(loader),pkg.PROJECT_PRODUCT)
            report=pkg.validate_package(raw)
            self.assertEqual(report['product'],'FM-1_720')
            self.assertEqual(report['origin_package_sha256'],pkg.INSTALLED_719_INLINE_PACKAGE_SHA256)
            self.assertEqual(report['origin_app_sha256'],pkg.INSTALLED_719_INLINE_APP_SHA256)
            self.assertFalse(report['runtime_preflight_qualified'])
            installed.assert_called_once()
            for bad in (loader.replace(b'ota-FM-1_720',b'ota-FM-1_719'),loader[:-32]+bytes(32)):
                with self.assertRaises(ValueError):pkg.validate_package(pkg.ufw(flash,pkg.loader_wrap(bad),pkg.PROJECT_PRODUCT))

    def test_inline719_reference_requires_exact_journal_and_raw_app(self):
        with tempfile.TemporaryDirectory() as directory:
            raw=b'synthetic inline719';app=b'synthetic raw app719';root=Path(directory)
            package=root/'candidate.fwsc';package.write_bytes(raw);journal=root/'events.jsonl'
            package_hash=hashlib.sha256(raw).hexdigest()
            events=[dict(event='qualified_before_device_access',package=dict(package_sha256=package_hash)),
                    dict(event='completed',identity='FM-1_719')]
            journal_bytes=('\n'.join(json.dumps(event) for event in events)+'\n').encode();journal.write_bytes(journal_bytes)
            with patch.multiple(pkg,INSTALLED_719_INLINE_PACKAGE=package,INSTALLED_719_INLINE_PACKAGE_SHA256=package_hash,
                    INSTALLED_719_INLINE_JOURNAL=journal,INSTALLED_719_INLINE_JOURNAL_SHA256=hashlib.sha256(journal_bytes).hexdigest(),
                    INSTALLED_719_INLINE_APP_SHA256=hashlib.sha256(app).hexdigest()), \
                 patch.object(pkg,'validate_package',return_value=dict(template=pkg.TEST01_TEMPLATE)), \
                 patch.object(pkg,'decode_package',return_value=('FM-1_719',b'',{'flash.bin':{'payload':bytes(0x4000)+app}})):
                self.assertEqual(pkg.installed_719_inline_reference(),app)
                with patch.object(pkg,'INSTALLED_719_INLINE_APP_SHA256','0'*64),self.assertRaisesRegex(ValueError,'raw application SHA-256'):
                    pkg.installed_719_inline_reference()
                journal.write_bytes(journal_bytes+b' ')
                with self.assertRaisesRegex(ValueError,'journal SHA-256'):pkg.installed_719_inline_reference()
                missing=(json.dumps(events[0])+'\n').encode();journal.write_bytes(missing)
                with patch.object(pkg,'INSTALLED_719_INLINE_JOURNAL_SHA256',hashlib.sha256(missing).hexdigest()), \
                     self.assertRaisesRegex(ValueError,'successful transition'):pkg.installed_719_inline_reference()

    def test_719_same_identity_requires_one_exact_admitted_origin(self):
        prior=bytes.fromhex(pkg.INSTALLED_718_APP_SHA256)
        current=bytes.fromhex(pkg.INSTALLED_719_APP_SHA256)
        with patch.object(pkg,'installed_718_reference') as old,patch.object(pkg,'installed_719_reference') as installed:
            historical=pkg.transition_profile(pkg.WORKSTATION_PRODUCT,pkg.TEST01_TEMPLATE)
            self.assertEqual(historical['origin_identity'],pkg.REACTIVE_PRODUCT)
            self.assertEqual(pkg.transition_profile(pkg.WORKSTATION_PRODUCT,pkg.TEST01_TEMPLATE,b'code'+prior),historical)
            corrected=pkg.transition_profile(pkg.WORKSTATION_PRODUCT,pkg.TEST01_TEMPLATE,b'code'+current)
            self.assertEqual(corrected,dict(origin_identity=pkg.WORKSTATION_PRODUCT,loader_identity='ota-FM-1_719',
                origin_app_sha256=pkg.INSTALLED_719_APP_SHA256,origin_package_sha256=pkg.INSTALLED_719_PACKAGE_SHA256))
            self.assertEqual(old.call_count,2);installed.assert_called_once()
            for raw in (b'',b'unknown'+bytes(32),prior+current,current+current,prior+prior,current[:-1]+bytes([current[-1]^1])):
                with self.subTest(raw=raw.hex()),self.assertRaisesRegex(ValueError,'fingerprint'):
                    pkg.transition_profile(pkg.WORKSTATION_PRODUCT,pkg.TEST01_TEMPLATE,raw)
            self.assertEqual(old.call_count,2);installed.assert_called_once()
        with patch.object(pkg,'installed_719_reference',side_effect=ValueError('missing installation proof')),self.assertRaisesRegex(ValueError,'installation proof'):
            pkg.transition_profile(pkg.WORKSTATION_PRODUCT,pkg.TEST01_TEMPLATE,current)

    def test_719_package_validator_uses_embedded_origin_without_version_recursion(self):
        original=self.exact_fixture();prior=bytes.fromhex(pkg.INSTALLED_718_APP_SHA256);current=bytes.fromhex(pkg.INSTALLED_719_APP_SHA256)
        with patch.object(pkg,'test01_flash_reference',return_value=original),patch.object(pkg,'sdk_file',side_effect=self.sdk.__getitem__), \
             patch.object(pkg,'installed_718_reference') as old,patch.object(pkg,'installed_719_reference') as installed:
            flash=pkg.flash_image(self.app+b'FM-1_719\0',pkg.KEY,pkg.TEST01_TEMPLATE)
            def wrapped(digest):return pkg.ufw(flash,pkg.loader_wrap(loader_fixture()+b'ota-FM-1_719\0'+digest),pkg.WORKSTATION_PRODUCT)
            historical=pkg.validate_package(wrapped(prior));self.assertEqual(historical['origin_identity'],'FM-1_718')
            installed.assert_not_called()
            corrected=pkg.validate_package(wrapped(current));self.assertEqual(corrected['origin_identity'],'FM-1_719')
            self.assertEqual(corrected['origin_app_sha256'],pkg.INSTALLED_719_APP_SHA256)
            self.assertEqual(corrected['origin_package_sha256'],pkg.INSTALLED_719_PACKAGE_SHA256)
            self.assertEqual(old.call_count,1);installed.assert_called_once()
            for invalid in (bytes(32),current+prior):
                with self.subTest(invalid=invalid.hex()),self.assertRaisesRegex(ValueError,'fingerprint'):pkg.validate_package(wrapped(invalid))

    def test_719_third_image_requires_only_corrected_origin_and_rejects_all_mixed_digests(self):
        digests = [bytes.fromhex(value) for value in
                   (pkg.INSTALLED_718_APP_SHA256, pkg.INSTALLED_719_APP_SHA256, pkg.INSTALLED_719_CORRECTED_APP_SHA256)]
        with patch.object(pkg, 'installed_718_reference') as prior, \
             patch.object(pkg, 'installed_719_reference') as initial, \
             patch.object(pkg, 'installed_719_corrected_reference') as corrected:
            profile = pkg.transition_profile(pkg.WORKSTATION_PRODUCT, pkg.TEST01_TEMPLATE, b'code'+digests[2])
            self.assertEqual(profile, dict(origin_identity=pkg.WORKSTATION_PRODUCT, loader_identity='ota-FM-1_719',
                origin_app_sha256=pkg.INSTALLED_719_CORRECTED_APP_SHA256,
                origin_package_sha256=pkg.INSTALLED_719_CORRECTED_PACKAGE_SHA256))
            prior.assert_not_called(); initial.assert_not_called(); corrected.assert_called_once()
            invalid = [b'', bytes(32), bytearray(digests[2]), digests[2][:-1]+bytes([digests[2][-1]^1])]
            invalid += [a+b for a in digests for b in digests]
            invalid += [b''.join(digests)]
            for raw in invalid:
                with self.subTest(raw=raw.hex()), self.assertRaisesRegex(ValueError, 'fingerprint'):
                    pkg.transition_profile(pkg.WORKSTATION_PRODUCT, pkg.TEST01_TEMPLATE, raw)
            prior.assert_not_called(); initial.assert_not_called(); corrected.assert_called_once()
        with patch.object(pkg, 'installed_719_corrected_reference', side_effect=ValueError('missing corrected installation proof')), \
             self.assertRaisesRegex(ValueError, 'installation proof'):
            pkg.transition_profile(pkg.WORKSTATION_PRODUCT, pkg.TEST01_TEMPLATE, digests[2])

    def test_719_third_package_validator_retains_finite_historical_chain(self):
        original = self.exact_fixture()
        with patch.object(pkg, 'test01_flash_reference', return_value=original), \
             patch.object(pkg, 'sdk_file', side_effect=self.sdk.__getitem__), \
             patch.object(pkg, 'installed_718_reference') as prior, \
             patch.object(pkg, 'installed_719_reference') as initial, \
             patch.object(pkg, 'installed_719_corrected_reference') as corrected:
            flash = pkg.flash_image(self.app+b'FM-1_719\0', pkg.KEY, pkg.TEST01_TEMPLATE)
            def wrapped(digest):
                return pkg.ufw(flash, pkg.loader_wrap(loader_fixture()+b'ota-FM-1_719\0'+bytes.fromhex(digest)), pkg.WORKSTATION_PRODUCT)
            pkg.validate_package(wrapped(pkg.INSTALLED_718_APP_SHA256))
            initial.assert_not_called(); corrected.assert_not_called()
            pkg.validate_package(wrapped(pkg.INSTALLED_719_APP_SHA256))
            corrected.assert_not_called()
            report = pkg.validate_package(wrapped(pkg.INSTALLED_719_CORRECTED_APP_SHA256))
            self.assertEqual(report['origin_app_sha256'], pkg.INSTALLED_719_CORRECTED_APP_SHA256)
            self.assertEqual(report['origin_package_sha256'], pkg.INSTALLED_719_CORRECTED_PACKAGE_SHA256)
            self.assertEqual(report['origin_identity'], 'FM-1_719')
            prior.assert_called_once(); initial.assert_called_once(); corrected.assert_called_once()

    def test_corrected719_reference_requires_exact_package_and_completed_pinned_journal(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = b'synthetic corrected719'; app = b'synthetic encrypted app'
            package = Path(directory)/'candidate.fwsc'; package.write_bytes(raw)
            journal = Path(directory)/'events.jsonl'
            package_hash = hashlib.sha256(raw).hexdigest()
            events = [dict(event='qualified_before_device_access', package=dict(package_sha256=package_hash)),
                      dict(event='completed', identity='FM-1_719')]
            journal_bytes = ('\n'.join(json.dumps(event) for event in events)+'\n').encode()
            journal.write_bytes(journal_bytes)
            with patch.multiple(pkg, INSTALLED_719_CORRECTED_PACKAGE=package,
                    INSTALLED_719_CORRECTED_PACKAGE_SHA256=package_hash, INSTALLED_719_CORRECTED_JOURNAL=journal,
                    INSTALLED_719_CORRECTED_JOURNAL_SHA256=hashlib.sha256(journal_bytes).hexdigest(),
                    INSTALLED_719_CORRECTED_APP_SHA256=hashlib.sha256(app).hexdigest()), \
                 patch.object(pkg, 'validate_package', return_value=dict(template=pkg.TEST01_TEMPLATE)) as validate, \
                 patch.object(pkg, 'decode_package', return_value=('FM-1_719', b'', {'flash.bin': {'payload': bytes(0x4000)+app}})):
                self.assertEqual(pkg.installed_719_corrected_reference(), app)
                validate.assert_called_once_with(raw, pkg.TEST01_TEMPLATE)
                journal.unlink()
                with self.assertRaises(FileNotFoundError): pkg.installed_719_corrected_reference()
                journal.write_bytes(journal_bytes+b' ')
                with self.assertRaisesRegex(ValueError, 'journal SHA-256'): pkg.installed_719_corrected_reference()
                incomplete = json.dumps(events[0]).encode()+b'\n'
                journal.write_bytes(incomplete)
                with patch.object(pkg, 'INSTALLED_719_CORRECTED_JOURNAL_SHA256', hashlib.sha256(incomplete).hexdigest()), \
                     self.assertRaisesRegex(ValueError, 'successful transition evidence'):
                    pkg.installed_719_corrected_reference()
                journal.write_bytes(journal_bytes); package.write_bytes(raw+b'changed')
                with self.assertRaisesRegex(ValueError, 'package SHA-256'): pkg.installed_719_corrected_reference()
                self.assertEqual(validate.call_count, 1)

    def test_optimized719_only_admits_the_exact_third_package_without_historical_recursion(self):
        original = self.exact_fixture()
        origins = (
            (pkg.INSTALLED_718_APP_SHA256, pkg.INSTALLED_718_PACKAGE_SHA256),
            (pkg.INSTALLED_719_APP_SHA256, pkg.INSTALLED_719_PACKAGE_SHA256),
            (pkg.INSTALLED_719_CORRECTED_APP_SHA256, pkg.INSTALLED_719_CORRECTED_PACKAGE_SHA256),
            (pkg.INSTALLED_719_FINAL_APP_SHA256, pkg.INSTALLED_719_FINAL_PACKAGE_SHA256),
        )
        with patch.object(pkg, 'test01_flash_reference', return_value=original), \
             patch.object(pkg, 'sdk_file', side_effect=self.sdk.__getitem__), \
             patch.object(pkg, 'installed_718_reference') as prior, \
             patch.object(pkg, 'installed_719_reference') as initial, \
             patch.object(pkg, 'installed_719_corrected_reference') as corrected, \
             patch.object(pkg, 'installed_719_final_reference') as third:
            flash = pkg.flash_image(self.app+b'FM-1_719\0', pkg.KEY, pkg.TEST01_TEMPLATE)
            references = (prior, initial, corrected, third)
            for index, (digest, package_hash) in enumerate(origins):
                for reference in references: reference.reset_mock()
                raw = pkg.ufw(flash, pkg.loader_wrap(loader_fixture()+b'ota-FM-1_719\0'+bytes.fromhex(digest)), pkg.WORKSTATION_PRODUCT)
                report = pkg.validate_package(raw)
                self.assertEqual(report['origin_app_sha256'], digest)
                self.assertEqual(report['origin_package_sha256'], package_hash)
                for j, reference in enumerate(references): self.assertEqual(reference.call_count, int(j == index))
            digest = bytes.fromhex(origins[-1][0])
            invalid = [b'', bytes(32), digest[:-1]+bytes([digest[-1]^1]), bytearray(digest)]
            invalid += [digest+bytes.fromhex(origin[0]) for origin in origins]
            for value in invalid:
                with self.subTest(value=value.hex()), self.assertRaisesRegex(ValueError, 'fingerprint'):
                    pkg.transition_profile(pkg.WORKSTATION_PRODUCT, pkg.TEST01_TEMPLATE, value)
            third.assert_called_once()
        with patch.object(pkg, 'installed_719_final_reference', side_effect=ValueError('missing third installation proof')), \
             self.assertRaisesRegex(ValueError, 'installation proof'):
            pkg.transition_profile(pkg.WORKSTATION_PRODUCT, pkg.TEST01_TEMPLATE, digest)

    def test_arithmetic719_only_admits_exact_fourth_package_and_finite_history(self):
        original = self.exact_fixture()
        origins = (
            (pkg.INSTALLED_718_APP_SHA256, pkg.INSTALLED_718_PACKAGE_SHA256),
            (pkg.INSTALLED_719_APP_SHA256, pkg.INSTALLED_719_PACKAGE_SHA256),
            (pkg.INSTALLED_719_CORRECTED_APP_SHA256, pkg.INSTALLED_719_CORRECTED_PACKAGE_SHA256),
            (pkg.INSTALLED_719_FINAL_APP_SHA256, pkg.INSTALLED_719_FINAL_PACKAGE_SHA256),
            (pkg.INSTALLED_719_OPTIMIZED_APP_SHA256, pkg.INSTALLED_719_OPTIMIZED_PACKAGE_SHA256),
        )
        with patch.object(pkg, 'test01_flash_reference', return_value=original), \
             patch.object(pkg, 'sdk_file', side_effect=self.sdk.__getitem__), \
             patch.object(pkg, 'installed_718_reference') as prior, \
             patch.object(pkg, 'installed_719_reference') as initial, \
             patch.object(pkg, 'installed_719_corrected_reference') as corrected, \
             patch.object(pkg, 'installed_719_final_reference') as third, \
             patch.object(pkg, 'installed_719_optimized_reference') as fourth:
            flash = pkg.flash_image(self.app+b'FM-1_719\0', pkg.KEY, pkg.TEST01_TEMPLATE)
            references = (prior, initial, corrected, third, fourth)
            for index, (digest, package_hash) in enumerate(origins):
                for reference in references: reference.reset_mock()
                raw = pkg.ufw(flash, pkg.loader_wrap(loader_fixture()+b'ota-FM-1_719\0'+bytes.fromhex(digest)), pkg.WORKSTATION_PRODUCT)
                report = pkg.validate_package(raw)
                self.assertEqual(report['origin_app_sha256'], digest)
                self.assertEqual(report['origin_package_sha256'], package_hash)
                for j, reference in enumerate(references): self.assertEqual(reference.call_count, int(j == index))
            digest = bytes.fromhex(origins[-1][0])
            invalid = [b'', bytes(32), digest[:-1]+bytes([digest[-1]^1]), bytearray(digest)]
            invalid += [digest+bytes.fromhex(origin[0]) for origin in origins]
            for value in invalid:
                with self.subTest(value=value.hex()), self.assertRaisesRegex(ValueError, 'fingerprint'):
                    pkg.transition_profile(pkg.WORKSTATION_PRODUCT, pkg.TEST01_TEMPLATE, value)
            fourth.assert_called_once()
        with patch.object(pkg, 'installed_719_optimized_reference', side_effect=ValueError('missing fourth installation proof')), \
             self.assertRaisesRegex(ValueError, 'installation proof'):
            pkg.transition_profile(pkg.WORKSTATION_PRODUCT, pkg.TEST01_TEMPLATE, digest)

    def test_phaser719_only_admits_exact_fifth_package_and_finite_history(self):
        original = self.exact_fixture()
        origins = (
            (pkg.INSTALLED_718_APP_SHA256, pkg.INSTALLED_718_PACKAGE_SHA256),
            (pkg.INSTALLED_719_APP_SHA256, pkg.INSTALLED_719_PACKAGE_SHA256),
            (pkg.INSTALLED_719_CORRECTED_APP_SHA256, pkg.INSTALLED_719_CORRECTED_PACKAGE_SHA256),
            (pkg.INSTALLED_719_FINAL_APP_SHA256, pkg.INSTALLED_719_FINAL_PACKAGE_SHA256),
            (pkg.INSTALLED_719_OPTIMIZED_APP_SHA256, pkg.INSTALLED_719_OPTIMIZED_PACKAGE_SHA256),
            (pkg.INSTALLED_719_ARITHMETIC_APP_SHA256, pkg.INSTALLED_719_ARITHMETIC_PACKAGE_SHA256),
        )
        with patch.object(pkg, 'test01_flash_reference', return_value=original), \
             patch.object(pkg, 'sdk_file', side_effect=self.sdk.__getitem__), \
             patch.object(pkg, 'installed_718_reference') as prior, \
             patch.object(pkg, 'installed_719_reference') as initial, \
             patch.object(pkg, 'installed_719_corrected_reference') as corrected, \
             patch.object(pkg, 'installed_719_final_reference') as third, \
             patch.object(pkg, 'installed_719_optimized_reference') as fourth, \
             patch.object(pkg, 'installed_719_arithmetic_reference') as fifth:
            flash = pkg.flash_image(self.app+b'FM-1_719\0', pkg.KEY, pkg.TEST01_TEMPLATE)
            references = (prior, initial, corrected, third, fourth, fifth)
            for index, (digest, package_hash) in enumerate(origins):
                for reference in references: reference.reset_mock()
                raw = pkg.ufw(flash, pkg.loader_wrap(loader_fixture()+b'ota-FM-1_719\0'+bytes.fromhex(digest)), pkg.WORKSTATION_PRODUCT)
                report = pkg.validate_package(raw)
                self.assertEqual(report['origin_app_sha256'], digest)
                self.assertEqual(report['origin_package_sha256'], package_hash)
                for j, reference in enumerate(references): self.assertEqual(reference.call_count, int(j == index))
            digest = bytes.fromhex(origins[-1][0])
            invalid = [b'', bytes(32), digest[:-1]+bytes([digest[-1]^1]), bytearray(digest)]
            invalid += [digest+bytes.fromhex(origin[0]) for origin in origins]
            for value in invalid:
                with self.subTest(value=value.hex()), self.assertRaisesRegex(ValueError, 'fingerprint'):
                    pkg.transition_profile(pkg.WORKSTATION_PRODUCT, pkg.TEST01_TEMPLATE, value)
            fifth.assert_called_once()
        with patch.object(pkg, 'installed_719_arithmetic_reference', side_effect=ValueError('missing fifth installation proof')), \
             self.assertRaisesRegex(ValueError, 'installation proof'):
            pkg.transition_profile(pkg.WORKSTATION_PRODUCT, pkg.TEST01_TEMPLATE, digest)

    def test_dispatch719_only_admits_exact_sixth_package_and_finite_history(self):
        original = self.exact_fixture()
        origins = (
            (pkg.INSTALLED_718_APP_SHA256, pkg.INSTALLED_718_PACKAGE_SHA256),
            (pkg.INSTALLED_719_APP_SHA256, pkg.INSTALLED_719_PACKAGE_SHA256),
            (pkg.INSTALLED_719_CORRECTED_APP_SHA256, pkg.INSTALLED_719_CORRECTED_PACKAGE_SHA256),
            (pkg.INSTALLED_719_FINAL_APP_SHA256, pkg.INSTALLED_719_FINAL_PACKAGE_SHA256),
            (pkg.INSTALLED_719_OPTIMIZED_APP_SHA256, pkg.INSTALLED_719_OPTIMIZED_PACKAGE_SHA256),
            (pkg.INSTALLED_719_ARITHMETIC_APP_SHA256, pkg.INSTALLED_719_ARITHMETIC_PACKAGE_SHA256),
            (pkg.INSTALLED_719_PHASER_APP_SHA256, pkg.INSTALLED_719_PHASER_PACKAGE_SHA256),
        )
        with patch.object(pkg, 'test01_flash_reference', return_value=original), \
             patch.object(pkg, 'sdk_file', side_effect=self.sdk.__getitem__), \
             patch.object(pkg, 'installed_718_reference') as prior, \
             patch.object(pkg, 'installed_719_reference') as initial, \
             patch.object(pkg, 'installed_719_corrected_reference') as corrected, \
             patch.object(pkg, 'installed_719_final_reference') as third, \
             patch.object(pkg, 'installed_719_optimized_reference') as fourth, \
             patch.object(pkg, 'installed_719_arithmetic_reference') as fifth, \
             patch.object(pkg, 'installed_719_phaser_reference') as sixth:
            flash = pkg.flash_image(self.app+b'FM-1_719\0', pkg.KEY, pkg.TEST01_TEMPLATE)
            references = (prior, initial, corrected, third, fourth, fifth, sixth)
            for index, (digest, package_hash) in enumerate(origins):
                for reference in references: reference.reset_mock()
                raw = pkg.ufw(flash, pkg.loader_wrap(loader_fixture()+b'ota-FM-1_719\0'+bytes.fromhex(digest)), pkg.WORKSTATION_PRODUCT)
                report = pkg.validate_package(raw)
                self.assertEqual(report['origin_app_sha256'], digest)
                self.assertEqual(report['origin_package_sha256'], package_hash)
                for j, reference in enumerate(references): self.assertEqual(reference.call_count, int(j == index))
            digest = bytes.fromhex(origins[-1][0])
            invalid = [b'', bytes(32), digest[:-1]+bytes([digest[-1]^1]), bytearray(digest)]
            invalid += [digest+bytes.fromhex(origin[0]) for origin in origins]
            for value in invalid:
                with self.subTest(value=value.hex()), self.assertRaisesRegex(ValueError, 'fingerprint'):
                    pkg.transition_profile(pkg.WORKSTATION_PRODUCT, pkg.TEST01_TEMPLATE, value)
            sixth.assert_called_once()
        with patch.object(pkg, 'installed_719_phaser_reference', side_effect=ValueError('missing sixth installation proof')), \
             self.assertRaisesRegex(ValueError, 'installation proof'):
            pkg.transition_profile(pkg.WORKSTATION_PRODUCT, pkg.TEST01_TEMPLATE, digest)

    @classmethod
    def setUpClass(cls):
        cls.sdk = {"uboot.boot": b"SPL"*100, "cfg_tool.bin": bytes(383), "cfg/eq_cfg_hw.bin": bytes(655)}
        cls.app = bytes.fromhex("04818000") + b"Synthetic FMER test app"*32
        cls.loader = pkg.loader_wrap(loader_fixture())
        with patch.object(pkg, "sdk_file", side_effect=cls.sdk.__getitem__):
            cls.reference = pkg._format_flash_image(bytes.fromhex("04818000")+b"stock fixture", pkg.KEY)[0x4000:]
        cls.ref_patch = patch.object(pkg, "stock_app_reference", return_value=cls.reference)
        cls.ref_patch.start()
        with patch.object(pkg, "sdk_file", side_effect=cls.sdk.__getitem__):
            cls.flash = pkg.flash_image(cls.app, pkg.KEY)
        cls.raw = pkg.ufw(cls.flash, cls.loader, pkg.PRODUCT)

    @classmethod
    def tearDownClass(cls):
        cls.ref_patch.stop()

    def test_crc_standard_vector(self):
        self.assertEqual(pkg.crc16(b"123456789"), 0x31C3)

    def test_sdk_hash_is_hard_gate(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)/"cpu/wl82/tools/uboot.boot"
            p.parent.mkdir(parents=True)
            p.write_bytes(b"untrusted")
            with patch.object(pkg, "SDK", Path(folder)):
                with self.assertRaisesRegex(ValueError, "SHA-256"):
                    pkg.sdk_file("uboot.boot")
                p.unlink()
                with self.assertRaisesRegex(ValueError, "missing"):
                    pkg.sdk_file("uboot.boot")

    def test_round_trip_and_determinism(self):
        with patch.object(pkg, "sdk_file", side_effect=self.sdk.__getitem__):
            report = pkg.validate_package(self.raw)
            self.assertEqual(self.raw, pkg.ufw(pkg.flash_image(self.app, pkg.KEY), self.loader, pkg.PRODUCT))
        self.assertEqual(report["product"], "FM-1_701")
        self.assertEqual(report["app_write_range"], [0x4000, 0x93000])
        self.assertFalse(report["hardware_qualified"])
        self.assertEqual(report["package_sha256"], hashlib.sha256(self.raw).hexdigest())

    def test_lz4_roundtrip_at_block_boundaries(self):
        rng = random.Random(701)
        for n in [1, 4, 12, 15, 16, 255, 1024, 4000]:
            for data in [bytes(n), bytes(rng.randrange(256) for _ in range(n))]:
                self.assertEqual(pkg.lz4_decompress(pkg.lz4_compress(data), n), data)

    def test_lz4_malformed_refused(self):
        for data, count in [(b"\xf0", 20), (b"\x50abc", 5), (b"\x00\x00\x00", 4),
                            (b"\x10A\x02\x00", 5), (b"\x1fA\x01\x00\xff", 20),
                            (b"\x11A", 1), (b"\x10A\x01", 5)]:
            with self.subTest(data=data), self.assertRaises(ValueError):
                pkg.lz4_decompress(data, count)

    def test_loader_truncation_crc_address_and_size(self):
        for end in [0, 31, 63, 71, len(self.loader)-1]:
            with self.assertRaises(ValueError):
                pkg.validate_loader(self.loader[:end])
        bad = bytearray(self.loader)
        bad[-1] ^= 1
        with self.assertRaisesRegex(ValueError, "CRC"):
            pkg.validate_loader(bad)
        inner = bytearray(self.loader[32:])
        struct.pack_into("<I", inner, 8, 0x02000120)
        struct.pack_into("<H", inner, 0, pkg.crc16(inner[2:32]))
        bad = pkg.entry(pkg.crc16(inner), 32, len(inner), 0x41, 0, 0, pkg.LOADER_NAME)+inner
        with self.assertRaisesRegex(ValueError, "RAM"):
            pkg.validate_loader(bad)

    def test_package_truncation_corruption_identity(self):
        for end in [0, 940, 960, 1043, len(self.raw)-1]:
            with self.assertRaises(ValueError):
                pkg.decode_package(self.raw[:end])
        for off in [0, 70, 960+1024, len(self.raw)-1]:
            bad = bytearray(self.raw)
            bad[off] ^= 1
            with self.assertRaises(ValueError):
                pkg.decode_package(bad)
        bad = bytearray(self.raw)
        bad[47] ^= 1
        with self.assertRaisesRegex(ValueError, "identity"):
            pkg.decode_package(bad)

    def test_recomputed_outer_crc_does_not_hide_nested_corruption(self):
        flash = bytearray(self.flash)
        flash[0x8100] ^= 0x40
        raw = pkg.ufw(flash, self.loader, pkg.PRODUCT)
        with patch.object(pkg, "sdk_file", side_effect=self.sdk.__getitem__):
            with self.assertRaisesRegex(ValueError, "nested data CRC"):
                pkg.validate_package(raw)

    def test_wrong_chip_key_refused_with_valid_container_crcs(self):
        with patch.object(pkg, "sdk_file", side_effect=self.sdk.__getitem__):
            raw = pkg.ufw(pkg.flash_image(self.app, 0x1234), self.loader, pkg.PRODUCT)
            with self.assertRaises(ValueError):
                pkg.validate_package(raw)

    def test_app_entry_and_slot_refused(self):
        with patch.object(pkg, "sdk_file", side_effect=self.sdk.__getitem__):
            for data in [b"", b"wrong", bytes.fromhex("04818000")+bytes(pkg.APP_SLOT)]:
                with self.assertRaises(ValueError):
                    pkg.flash_image(data, pkg.KEY)

    def test_stock_calibration_and_descriptors_preserved(self):
        area = self.flash[0x4000:]
        for start,end in [(4,32),(36,0x120),(0x120+pkg.APP_SLOT,len(area))]:
            self.assertEqual(area[start:end], self.reference[start:end])

    def test_runtime_qualification_binds_package_loader_and_sources(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(pkg, "sdk_file", side_effect=self.sdk.__getitem__):
            root=Path(folder); source=root/"loader.c"; source.write_bytes(b"reviewed source")
            manifest=root/"firmware/fm1/loader/QUALIFICATION.json"; manifest.parent.mkdir(parents=True)
            review={"runtime_preflight_qualified":True,"package_sha256":hashlib.sha256(self.raw).hexdigest(),
                    "loader_sha256":hashlib.sha256(loader_fixture()).hexdigest(),
                    "template":pkg.PUBLISHED_TEMPLATE,"stock_app_reference_sha256":pkg.STOCK_APP_SHA256,
                    "source_files":[{"path":"loader.c","sha256":hashlib.sha256(source.read_bytes()).hexdigest()}]}
            manifest.write_text(json.dumps(review))
            with patch.object(pkg,"ROOT",root):
                self.assertTrue(pkg.validate_package(self.raw)["runtime_preflight_qualified"])
                source.write_bytes(b"changed source")
                self.assertFalse(pkg.validate_package(self.raw)["runtime_preflight_qualified"])
                source.write_bytes(b"reviewed source")
                review["package_sha256"]="0"*64;manifest.write_text(json.dumps(review))
                self.assertFalse(pkg.validate_package(self.raw)["runtime_preflight_qualified"])

    def exact_fixture(self):
        sdk = dict(self.sdk)
        sdk["cfg/eq_cfg_hw.bin"] = bytes(range(256))*11+b"calibration-table"*3+bytes(6)
        with patch.object(pkg, "sdk_file", side_effect=sdk.__getitem__), patch.object(pkg, "APP_SLOT", pkg.TEST01_APP_SLOT):
            result = bytearray(pkg._format_flash_image(bytes.fromhex("04818000")+b"unit original", pkg.KEY))
        # Observable private metadata variant: preserve USR reserved byte80,
        # including its own header CRC and the containing area data/header CRCs.
        plain = bytearray(result[0x4000:])
        pkg.sfc(plain, 0, len(plain), 0, pkg.KEY)
        plain[192+13] = 0x80
        struct.pack_into("<H", plain, 192, pkg.crc16(plain[194:224]))
        end = pkg.jlfs_header(plain)[3]
        struct.pack_into("<H", plain, 2, pkg.crc16(plain[32:end]))
        struct.pack_into("<H", plain, 0, pkg.crc16(plain[2:32]))
        pkg.sfc(plain, 0, len(plain), 0, pkg.KEY)
        result[0x4000:] = plain
        return bytes(result)

    def test_exact_unit_layout_and_every_nonpayload_byte_preserved(self):
        original = self.exact_fixture()
        with patch.object(pkg, "test01_flash_reference", return_value=original), patch.object(pkg, "sdk_file", side_effect=self.sdk.__getitem__):
            flash = pkg.flash_image(self.app, pkg.KEY, pkg.TEST01_TEMPLATE)
            report = pkg.validate_package(pkg.ufw(flash, self.loader, pkg.PRODUCT))
        self.assertEqual(report["template"], pkg.TEST01_TEMPLATE)
        self.assertEqual(report["template_layout"]["app_slot_bytes"], 0x8DD1C)
        self.assertEqual(report["template_layout"]["area_bytes"], 0x8DFBB)
        self.assertTrue(report["protected_head_preserved_from_backup"])
        allowed = report["allowed_raw_flash_changes"]
        self.assertTrue(all(a == b or any(start <= i < end for start, end in allowed)
                            for i, (a, b) in enumerate(zip(flash, original))))
        self.assertEqual(flash[:0x4000], original[:0x4000])
        self.assertEqual(flash[0x4000+0x120+pkg.TEST01_APP_SLOT:], original[0x4000+0x120+pkg.TEST01_APP_SLOT:])

    def test_exact_unit_slot_key_and_template_refusal(self):
        original = self.exact_fixture()
        with patch.object(pkg, "test01_flash_reference", return_value=original), patch.object(pkg, "sdk_file", side_effect=self.sdk.__getitem__):
            for app, key, template in [(bytes.fromhex("04818000")+bytes(pkg.TEST01_APP_SLOT-3), pkg.KEY, pkg.TEST01_TEMPLATE),
                                        (self.app, 0x1234, pkg.TEST01_TEMPLATE), (self.app, pkg.KEY, "unknown")]:
                with self.assertRaises(ValueError):
                    pkg.flash_image(app, key, template)
            flash = pkg.flash_image(self.app, pkg.KEY, pkg.TEST01_TEMPLATE)
            with self.assertRaisesRegex(ValueError, "template/app slot"):
                pkg.validate_package(pkg.ufw(flash, self.loader, pkg.PRODUCT), pkg.PUBLISHED_TEMPLATE)

    def successor_fixture(self, *, product=None, app_identity=True, loader_identity=True, origin_digest=True):
        product = product or pkg.NEXT_PRODUCT
        app = self.app + ((product+"\0").encode() if app_identity else b"FM-1_701\0")
        loader = loader_fixture() + (("ota-"+product+"\0").encode() if loader_identity else b"ota-FM-1_701\0")
        digest = {pkg.NEXT_PRODUCT: pkg.INSTALLED_701_APP_SHA256,
                  pkg.CURRENT_PRODUCT: pkg.INSTALLED_702_APP_SHA256,
                  pkg.BUILD_PRODUCT: pkg.INSTALLED_703_APP_SHA256,
                  pkg.LATEST_PRODUCT: pkg.INSTALLED_704_APP_SHA256,
                  pkg.DEVELOPMENT_PRODUCT: pkg.INSTALLED_705_APP_SHA256,
                  pkg.CANDIDATE_PRODUCT: pkg.INSTALLED_706_APP_SHA256,
                  pkg.INSTRUMENT_PRODUCT: pkg.INSTALLED_707_APP_SHA256,
                  pkg.BANK_PRODUCT: pkg.INSTALLED_708_APP_SHA256}[product]
        loader += bytes.fromhex(digest) if origin_digest else bytes(32)
        flash = pkg.flash_image(app, pkg.KEY, pkg.TEST01_TEMPLATE)
        return pkg.ufw(flash, pkg.loader_wrap(loader), product), loader

    def test_703_profile_preserves_older_validation_and_requires_702_digest(self):
        original = self.exact_fixture()
        with patch.object(pkg, "test01_flash_reference", return_value=original), \
             patch.object(pkg, "sdk_file", side_effect=self.sdk.__getitem__), \
             patch.object(pkg, "installed_701_reference", return_value=original[0x4000:]), \
             patch.object(pkg, "installed_702_reference", return_value=original[0x4000:]):
            for product, origin in [(pkg.NEXT_PRODUCT, pkg.PRODUCT), (pkg.CURRENT_PRODUCT, pkg.NEXT_PRODUCT)]:
                raw, _ = self.successor_fixture(product=product)
                report = pkg.validate_package(raw)
                self.assertEqual(report["product"], product)
                self.assertEqual(report["origin_identity"], origin)
                self.assertEqual(report["loader_identity"], "ota-"+product)
                self.assertFalse(report["runtime_preflight_qualified"])
            for change in ({"app_identity": False}, {"loader_identity": False}, {"origin_digest": False}):
                with self.subTest(change=change), self.assertRaisesRegex(ValueError, "identity|fingerprint"):
                    pkg.validate_package(self.successor_fixture(product=pkg.CURRENT_PRODUCT, **change)[0])
            with patch.object(pkg, "installed_702_reference", side_effect=ValueError("missing known 702 proof")), \
                 self.assertRaisesRegex(ValueError, "known 702"):
                pkg.transition_profile(pkg.CURRENT_PRODUCT, pkg.TEST01_TEMPLATE)

    def test_702_format_requires_exact_template_origin_digest_and_wire_identities(self):
        original = self.exact_fixture()
        with patch.object(pkg, "test01_flash_reference", return_value=original), \
             patch.object(pkg, "sdk_file", side_effect=self.sdk.__getitem__), \
             patch.object(pkg, "installed_701_reference", return_value=original[0x4000:]):
            raw, _ = self.successor_fixture()
            report = pkg.validate_package(raw)
            self.assertEqual(report["product"], "FM-1_702")
            self.assertEqual(report["origin_identity"], "FM-1_701")
            self.assertEqual(report["loader_identity"], "ota-FM-1_702")
            self.assertEqual(report["origin_app_sha256"], pkg.INSTALLED_701_APP_SHA256)
            self.assertEqual(report["stock_app_reference_sha256"], pkg.TEST01_APP_SHA256)
            self.assertFalse(report["runtime_preflight_qualified"])
            for change in ({"app_identity": False}, {"loader_identity": False}, {"origin_digest": False}):
                with self.subTest(change=change), self.assertRaisesRegex(ValueError, "identity|fingerprint"):
                    pkg.validate_package(self.successor_fixture(**change)[0])
            with self.assertRaisesRegex(ValueError, "exact Test01"):
                pkg.transition_profile(pkg.NEXT_PRODUCT, pkg.PUBLISHED_TEMPLATE)

    def test_704_requires_exact_703_origin_while_retaining_older_profiles(self):
        original = self.exact_fixture()
        with patch.object(pkg, "test01_flash_reference", return_value=original), \
             patch.object(pkg, "sdk_file", side_effect=self.sdk.__getitem__), \
             patch.object(pkg, "installed_703_reference", return_value=original[0x4000:]) as origin:
            report = pkg.validate_package(self.successor_fixture(product=pkg.BUILD_PRODUCT)[0])
            self.assertEqual(report["origin_identity"], pkg.CURRENT_PRODUCT)
            self.assertEqual(report["loader_identity"], "ota-FM-1_704")
            self.assertEqual(report["origin_app_sha256"], pkg.INSTALLED_703_APP_SHA256)
            self.assertEqual(report["origin_package_sha256"], pkg.INSTALLED_703_PACKAGE_SHA256)
            self.assertFalse(report["runtime_preflight_qualified"])
            origin.assert_called_once()
            for change in ({"app_identity": False}, {"loader_identity": False}, {"origin_digest": False}):
                with self.subTest(change=change), self.assertRaisesRegex(ValueError, "identity|fingerprint"):
                    pkg.validate_package(self.successor_fixture(product=pkg.BUILD_PRODUCT, **change)[0])
            with patch.object(pkg, "installed_703_reference", side_effect=ValueError("missing known 703 proof")), \
                 self.assertRaisesRegex(ValueError, "known 703"):
                pkg.transition_profile(pkg.BUILD_PRODUCT, pkg.TEST01_TEMPLATE)
            with self.assertRaisesRegex(ValueError, "exact Test01"):
                pkg.transition_profile(pkg.BUILD_PRODUCT, pkg.PUBLISHED_TEMPLATE)

    def test_705_requires_exact_704_origin_while_retaining_older_profiles(self):
        original = self.exact_fixture()
        with patch.object(pkg, "test01_flash_reference", return_value=original), \
             patch.object(pkg, "sdk_file", side_effect=self.sdk.__getitem__), \
             patch.object(pkg, "installed_704_reference", return_value=original[0x4000:]) as origin:
            report = pkg.validate_package(self.successor_fixture(product=pkg.LATEST_PRODUCT)[0])
            self.assertEqual(report["origin_identity"], pkg.BUILD_PRODUCT)
            self.assertEqual(report["loader_identity"], "ota-FM-1_705")
            self.assertEqual(report["origin_app_sha256"], pkg.INSTALLED_704_APP_SHA256)
            self.assertEqual(report["origin_package_sha256"], pkg.INSTALLED_704_PACKAGE_SHA256)
            self.assertFalse(report["runtime_preflight_qualified"])
            origin.assert_called_once()
            for change in ({"app_identity": False}, {"loader_identity": False}, {"origin_digest": False}):
                with self.subTest(change=change), self.assertRaisesRegex(ValueError, "identity|fingerprint"):
                    pkg.validate_package(self.successor_fixture(product=pkg.LATEST_PRODUCT, **change)[0])
            with patch.object(pkg, "installed_704_reference", side_effect=ValueError("missing known 704 proof")), \
                 self.assertRaisesRegex(ValueError, "known 704"):
                pkg.transition_profile(pkg.LATEST_PRODUCT, pkg.TEST01_TEMPLATE)
            with self.assertRaisesRegex(ValueError, "exact Test01"):
                pkg.transition_profile(pkg.LATEST_PRODUCT, pkg.PUBLISHED_TEMPLATE)

    def test_706_requires_exact_705_origin_while_retaining_older_profiles(self):
        original = self.exact_fixture()
        with patch.object(pkg, "test01_flash_reference", return_value=original), \
             patch.object(pkg, "sdk_file", side_effect=self.sdk.__getitem__), \
             patch.object(pkg, "installed_705_reference", return_value=original[0x4000:]) as origin:
            report = pkg.validate_package(self.successor_fixture(product=pkg.DEVELOPMENT_PRODUCT)[0])
            self.assertEqual(report["origin_identity"], pkg.LATEST_PRODUCT)
            self.assertEqual(report["loader_identity"], "ota-FM-1_706")
            self.assertEqual(report["origin_app_sha256"], pkg.INSTALLED_705_APP_SHA256)
            self.assertEqual(report["origin_package_sha256"], pkg.INSTALLED_705_PACKAGE_SHA256)
            self.assertFalse(report["runtime_preflight_qualified"])
            origin.assert_called_once()
            for change in ({"app_identity": False}, {"loader_identity": False}, {"origin_digest": False}):
                with self.subTest(change=change), self.assertRaisesRegex(ValueError, "identity|fingerprint"):
                    pkg.validate_package(self.successor_fixture(product=pkg.DEVELOPMENT_PRODUCT, **change)[0])
            with patch.object(pkg, "installed_705_reference", side_effect=ValueError("missing known 705 proof")), \
                 self.assertRaisesRegex(ValueError, "known 705"):
                pkg.transition_profile(pkg.DEVELOPMENT_PRODUCT, pkg.TEST01_TEMPLATE)
            with self.assertRaisesRegex(ValueError, "exact Test01"):
                pkg.transition_profile(pkg.DEVELOPMENT_PRODUCT, pkg.PUBLISHED_TEMPLATE)

    def test_707_requires_exact_706_origin_while_retaining_older_profiles(self):
        original = self.exact_fixture()
        with patch.object(pkg, "test01_flash_reference", return_value=original), \
             patch.object(pkg, "sdk_file", side_effect=self.sdk.__getitem__), \
             patch.object(pkg, "installed_706_reference", return_value=original[0x4000:]) as origin:
            report = pkg.validate_package(self.successor_fixture(product=pkg.CANDIDATE_PRODUCT)[0])
            self.assertEqual(report["origin_identity"], pkg.DEVELOPMENT_PRODUCT)
            self.assertEqual(report["loader_identity"], "ota-FM-1_707")
            self.assertEqual(report["origin_app_sha256"], pkg.INSTALLED_706_APP_SHA256)
            self.assertEqual(report["origin_package_sha256"], pkg.INSTALLED_706_PACKAGE_SHA256)
            self.assertFalse(report["runtime_preflight_qualified"])
            origin.assert_called_once()
            for change in ({"app_identity": False}, {"loader_identity": False}, {"origin_digest": False}):
                with self.subTest(change=change), self.assertRaisesRegex(ValueError, "identity|fingerprint"):
                    pkg.validate_package(self.successor_fixture(product=pkg.CANDIDATE_PRODUCT, **change)[0])
            with patch.object(pkg, "installed_706_reference", side_effect=ValueError("missing known 706 proof")), \
                 self.assertRaisesRegex(ValueError, "known 706"):
                pkg.transition_profile(pkg.CANDIDATE_PRODUCT, pkg.TEST01_TEMPLATE)
            with self.assertRaisesRegex(ValueError, "exact Test01"):
                pkg.transition_profile(pkg.CANDIDATE_PRODUCT, pkg.PUBLISHED_TEMPLATE)

    def test_708_requires_exact_707_origin_while_retaining_older_profiles(self):
        original = self.exact_fixture()
        with patch.object(pkg, "test01_flash_reference", return_value=original), \
             patch.object(pkg, "sdk_file", side_effect=self.sdk.__getitem__), \
             patch.object(pkg, "installed_707_reference", return_value=original[0x4000:]) as origin:
            report = pkg.validate_package(self.successor_fixture(product=pkg.INSTRUMENT_PRODUCT)[0])
            self.assertEqual(report["origin_identity"], pkg.CANDIDATE_PRODUCT)
            self.assertEqual(report["loader_identity"], "ota-FM-1_708")
            self.assertEqual(report["origin_app_sha256"], pkg.INSTALLED_707_APP_SHA256)
            self.assertEqual(report["origin_package_sha256"], pkg.INSTALLED_707_PACKAGE_SHA256)
            self.assertFalse(report["runtime_preflight_qualified"])
            origin.assert_called_once()
            for change in ({"app_identity": False}, {"loader_identity": False}, {"origin_digest": False}):
                with self.subTest(change=change), self.assertRaisesRegex(ValueError, "identity|fingerprint"):
                    pkg.validate_package(self.successor_fixture(product=pkg.INSTRUMENT_PRODUCT, **change)[0])
            with patch.object(pkg, "installed_707_reference", side_effect=ValueError("missing known 707 proof")), \
                 self.assertRaisesRegex(ValueError, "known 707"):
                pkg.transition_profile(pkg.INSTRUMENT_PRODUCT, pkg.TEST01_TEMPLATE)
            with self.assertRaisesRegex(ValueError, "exact Test01"):
                pkg.transition_profile(pkg.INSTRUMENT_PRODUCT, pkg.PUBLISHED_TEMPLATE)

    def test_709_requires_exact_708_origin_while_retaining_older_profiles(self):
        original = self.exact_fixture()
        with patch.object(pkg, "test01_flash_reference", return_value=original), \
             patch.object(pkg, "sdk_file", side_effect=self.sdk.__getitem__), \
             patch.object(pkg, "installed_708_reference", return_value=original[0x4000:]) as origin:
            report = pkg.validate_package(self.successor_fixture(product=pkg.BANK_PRODUCT)[0])
            self.assertEqual(report["origin_identity"], pkg.INSTRUMENT_PRODUCT)
            self.assertEqual(report["loader_identity"], "ota-FM-1_709")
            self.assertEqual(report["origin_app_sha256"], pkg.INSTALLED_708_APP_SHA256)
            self.assertEqual(report["origin_package_sha256"], pkg.INSTALLED_708_PACKAGE_SHA256)
            self.assertFalse(report["runtime_preflight_qualified"])
            origin.assert_called_once()
            for change in ({"app_identity": False}, {"loader_identity": False}, {"origin_digest": False}):
                with self.subTest(change=change), self.assertRaisesRegex(ValueError, "identity|fingerprint"):
                    pkg.validate_package(self.successor_fixture(product=pkg.BANK_PRODUCT, **change)[0])
            with patch.object(pkg, "installed_708_reference", side_effect=ValueError("missing known 708 proof")), \
                 self.assertRaisesRegex(ValueError, "known 708"):
                pkg.transition_profile(pkg.BANK_PRODUCT, pkg.TEST01_TEMPLATE)
            with self.assertRaisesRegex(ValueError, "exact Test01"):
                pkg.transition_profile(pkg.BANK_PRODUCT, pkg.PUBLISHED_TEMPLATE)

    def test_702_qualification_binds_origin_and_target_in_addition_to_sources(self):
        original = self.exact_fixture()
        with tempfile.TemporaryDirectory() as folder, patch.object(pkg, "test01_flash_reference", return_value=original), \
             patch.object(pkg, "sdk_file", side_effect=self.sdk.__getitem__), \
             patch.object(pkg, "installed_701_reference", return_value=original[0x4000:]):
            root = Path(folder)
            source = root/"loader.c"; source.write_bytes(b"reviewed 702 source")
            manifest = root/"firmware/fm1/loader/QUALIFICATION.json"; manifest.parent.mkdir(parents=True)
            raw, loader = self.successor_fixture()
            review = {"schema": 3, "runtime_preflight_qualified": True, "product": pkg.NEXT_PRODUCT,
                      "package_sha256": hashlib.sha256(raw).hexdigest(), "loader_sha256": hashlib.sha256(loader).hexdigest(),
                      "template": pkg.TEST01_TEMPLATE, "reference_backup_sha256": pkg.TEST01_DUMP_SHA256,
                      "reference_backup_report_sha256": pkg.TEST01_REPORT_SHA256,
                      **pkg.transition_profile(pkg.NEXT_PRODUCT, pkg.TEST01_TEMPLATE),
                      "source_files": [{"path": "loader.c", "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}]}
            with patch.object(pkg, "ROOT", root):
                manifest.write_text(json.dumps(review))
                self.assertTrue(pkg.validate_package(raw)["runtime_preflight_qualified"])
                for key, value in [("origin_identity", "FM-1_015"), ("origin_app_sha256", pkg.TEST01_APP_SHA256),
                                   ("origin_package_sha256", "0"*64), ("loader_identity", "ota-FM-1_701"),
                                   ("product", pkg.PRODUCT), ("schema", 2), ("source_files", []),
                                   ("reference_backup_report_sha256", "0"*64)]:
                    manifest.write_text(json.dumps(dict(review, **{key: value})))
                    with self.subTest(key=key):
                        self.assertFalse(pkg.validate_package(raw)["runtime_preflight_qualified"])

    def test_installed_701_origin_requires_exact_package_and_success_journal(self):
        original = self.exact_fixture()
        with tempfile.TemporaryDirectory() as folder, patch.object(pkg, "test01_flash_reference", return_value=original), \
             patch.object(pkg, "sdk_file", side_effect=self.sdk.__getitem__):
            root = Path(folder); package_path = root/"701.fwsc"; journal = root/"events.jsonl"
            flash = pkg.flash_image(self.app, pkg.KEY, pkg.TEST01_TEMPLATE)
            raw = pkg.ufw(flash, self.loader, pkg.PRODUCT); package_path.write_bytes(raw)
            package_hash = hashlib.sha256(raw).hexdigest()
            events = [{"event": "qualified_before_device_access", "package": {"package_sha256": package_hash}},
                      {"event": "completed", "identity": pkg.PRODUCT}]
            journal.write_text("\n".join(json.dumps(e) for e in events)+"\n")
            with patch.object(pkg, "INSTALLED_701_PACKAGE", package_path), patch.object(pkg, "INSTALLED_701_JOURNAL", journal), \
                 patch.object(pkg, "INSTALLED_701_PACKAGE_SHA256", package_hash), \
                 patch.object(pkg, "INSTALLED_701_APP_SHA256", hashlib.sha256(flash[0x4000:]).hexdigest()), \
                 patch.object(pkg, "INSTALLED_701_JOURNAL_SHA256", hashlib.sha256(journal.read_bytes()).hexdigest()):
                self.assertEqual(pkg.installed_701_reference(), flash[0x4000:])
                for path in (package_path, journal):
                    good = path.read_bytes(); path.write_bytes(good[:-1])
                    with self.subTest(path=path), self.assertRaisesRegex(ValueError, "SHA-256"):
                        pkg.installed_701_reference()
                    path.write_bytes(good)
                journal.write_text(json.dumps(events[0])+"\n"+json.dumps({"event": "failed"})+"\n")
                with patch.object(pkg, "INSTALLED_701_JOURNAL_SHA256", hashlib.sha256(journal.read_bytes()).hexdigest()), \
                     self.assertRaisesRegex(ValueError, "successful transition"):
                    pkg.installed_701_reference()

    def test_installed_702_origin_requires_its_own_success_journal_and_raw_bytes(self):
        original = self.exact_fixture()
        with tempfile.TemporaryDirectory() as folder, patch.object(pkg, "test01_flash_reference", return_value=original), \
             patch.object(pkg, "sdk_file", side_effect=self.sdk.__getitem__), \
             patch.object(pkg, "installed_701_reference", return_value=original[0x4000:]):
            root = Path(folder); path = root/"702.fwsc"; journal = root/"702.jsonl"
            raw, _ = self.successor_fixture(); path.write_bytes(raw)
            package_hash = hashlib.sha256(raw).hexdigest()
            _, _, files = pkg.decode_package(raw); expected = files['flash.bin']['payload'][0x4000:]
            events = [{"event": "qualified_before_device_access", "package": {"package_sha256": package_hash}},
                      {"event": "completed", "identity": pkg.NEXT_PRODUCT}]
            journal.write_text("\n".join(json.dumps(e) for e in events)+"\n")
            with patch.object(pkg, "INSTALLED_702_PACKAGE", path), patch.object(pkg, "INSTALLED_702_JOURNAL", journal), \
                 patch.object(pkg, "INSTALLED_702_PACKAGE_SHA256", package_hash), \
                 patch.object(pkg, "INSTALLED_702_JOURNAL_SHA256", hashlib.sha256(journal.read_bytes()).hexdigest()), \
                 patch.object(pkg, "INSTALLED_702_APP_SHA256", hashlib.sha256(expected).hexdigest()):
                self.assertEqual(pkg.installed_702_reference(), expected)
                with patch.object(pkg, "INSTALLED_702_APP_SHA256", pkg.INSTALLED_701_APP_SHA256), \
                     self.assertRaisesRegex(ValueError, "raw application SHA-256"):
                    pkg.installed_702_reference()
                events[-1]['identity'] = pkg.PRODUCT
                journal.write_text("\n".join(json.dumps(e) for e in events)+"\n")
                with patch.object(pkg, "INSTALLED_702_JOURNAL_SHA256", hashlib.sha256(journal.read_bytes()).hexdigest()), \
                     self.assertRaisesRegex(ValueError, "successful transition"):
                    pkg.installed_702_reference()

    def test_installed_703_origin_requires_its_own_success_journal_and_raw_bytes(self):
        original = self.exact_fixture()
        with tempfile.TemporaryDirectory() as folder, patch.object(pkg, "test01_flash_reference", return_value=original), \
             patch.object(pkg, "sdk_file", side_effect=self.sdk.__getitem__), \
             patch.object(pkg, "installed_702_reference", return_value=original[0x4000:]):
            root = Path(folder); path = root/"703.fwsc"; journal = root/"703.jsonl"
            raw, _ = self.successor_fixture(product=pkg.CURRENT_PRODUCT); path.write_bytes(raw)
            package_hash = hashlib.sha256(raw).hexdigest()
            _, _, files = pkg.decode_package(raw); expected = files['flash.bin']['payload'][0x4000:]
            events = [{"event": "qualified_before_device_access", "package": {"package_sha256": package_hash}},
                      {"event": "completed", "identity": pkg.CURRENT_PRODUCT}]
            journal.write_text("\n".join(json.dumps(e) for e in events)+"\n")
            with patch.object(pkg, "INSTALLED_703_PACKAGE", path), patch.object(pkg, "INSTALLED_703_JOURNAL", journal), \
                 patch.object(pkg, "INSTALLED_703_PACKAGE_SHA256", package_hash), \
                 patch.object(pkg, "INSTALLED_703_JOURNAL_SHA256", hashlib.sha256(journal.read_bytes()).hexdigest()), \
                 patch.object(pkg, "INSTALLED_703_APP_SHA256", hashlib.sha256(expected).hexdigest()):
                self.assertEqual(pkg.installed_703_reference(), expected)
                with patch.object(pkg, "INSTALLED_703_APP_SHA256", pkg.INSTALLED_701_APP_SHA256), \
                     self.assertRaisesRegex(ValueError, "raw application SHA-256"):
                    pkg.installed_703_reference()
                events[-1]['identity'] = pkg.PRODUCT
                journal.write_text("\n".join(json.dumps(e) for e in events)+"\n")
                with patch.object(pkg, "INSTALLED_703_JOURNAL_SHA256", hashlib.sha256(journal.read_bytes()).hexdigest()), \
                     self.assertRaisesRegex(ValueError, "successful transition"):
                    pkg.installed_703_reference()

    def test_installed_704_origin_requires_its_own_success_journal_and_raw_bytes(self):
        original = self.exact_fixture()
        with tempfile.TemporaryDirectory() as folder, patch.object(pkg, "test01_flash_reference", return_value=original), \
             patch.object(pkg, "sdk_file", side_effect=self.sdk.__getitem__), \
             patch.object(pkg, "installed_703_reference", return_value=original[0x4000:]):
            root = Path(folder); path = root/"704.fwsc"; journal = root/"704.jsonl"
            raw, _ = self.successor_fixture(product=pkg.BUILD_PRODUCT); path.write_bytes(raw)
            package_hash = hashlib.sha256(raw).hexdigest()
            _, _, files = pkg.decode_package(raw); expected = files['flash.bin']['payload'][0x4000:]
            events = [{"event": "qualified_before_device_access", "package": {"package_sha256": package_hash}},
                      {"event": "completed", "identity": pkg.BUILD_PRODUCT}]
            journal.write_text("\n".join(json.dumps(e) for e in events)+"\n")
            with patch.object(pkg, "INSTALLED_704_PACKAGE", path), patch.object(pkg, "INSTALLED_704_JOURNAL", journal), \
                 patch.object(pkg, "INSTALLED_704_PACKAGE_SHA256", package_hash), \
                 patch.object(pkg, "INSTALLED_704_JOURNAL_SHA256", hashlib.sha256(journal.read_bytes()).hexdigest()), \
                 patch.object(pkg, "INSTALLED_704_APP_SHA256", hashlib.sha256(expected).hexdigest()):
                self.assertEqual(pkg.installed_704_reference(), expected)
                with patch.object(pkg, "INSTALLED_704_APP_SHA256", pkg.INSTALLED_701_APP_SHA256), \
                     self.assertRaisesRegex(ValueError, "raw application SHA-256"):
                    pkg.installed_704_reference()
                events[-1]['identity'] = pkg.PRODUCT
                journal.write_text("\n".join(json.dumps(e) for e in events)+"\n")
                with patch.object(pkg, "INSTALLED_704_JOURNAL_SHA256", hashlib.sha256(journal.read_bytes()).hexdigest()), \
                     self.assertRaisesRegex(ValueError, "successful transition"):
                    pkg.installed_704_reference()

    def test_installed_705_origin_requires_its_own_success_journal_and_raw_bytes(self):
        original = self.exact_fixture()
        with tempfile.TemporaryDirectory() as folder, patch.object(pkg, "test01_flash_reference", return_value=original), \
             patch.object(pkg, "sdk_file", side_effect=self.sdk.__getitem__), \
             patch.object(pkg, "installed_704_reference", return_value=original[0x4000:]):
            root = Path(folder); path = root/"705.fwsc"; journal = root/"705.jsonl"
            raw, _ = self.successor_fixture(product=pkg.LATEST_PRODUCT); path.write_bytes(raw)
            package_hash = hashlib.sha256(raw).hexdigest()
            _, _, files = pkg.decode_package(raw); expected = files['flash.bin']['payload'][0x4000:]
            events = [{"event": "qualified_before_device_access", "package": {"package_sha256": package_hash}},
                      {"event": "completed", "identity": pkg.LATEST_PRODUCT}]
            journal.write_text("\n".join(json.dumps(e) for e in events)+"\n")
            with patch.object(pkg, "INSTALLED_705_PACKAGE", path), patch.object(pkg, "INSTALLED_705_JOURNAL", journal), \
                 patch.object(pkg, "INSTALLED_705_PACKAGE_SHA256", package_hash), \
                 patch.object(pkg, "INSTALLED_705_JOURNAL_SHA256", hashlib.sha256(journal.read_bytes()).hexdigest()), \
                 patch.object(pkg, "INSTALLED_705_APP_SHA256", hashlib.sha256(expected).hexdigest()):
                self.assertEqual(pkg.installed_705_reference(), expected)
                with patch.object(pkg, "INSTALLED_705_APP_SHA256", pkg.INSTALLED_701_APP_SHA256), \
                     self.assertRaisesRegex(ValueError, "raw application SHA-256"):
                    pkg.installed_705_reference()
                events[-1]['identity'] = pkg.PRODUCT
                journal.write_text("\n".join(json.dumps(e) for e in events)+"\n")
                with patch.object(pkg, "INSTALLED_705_JOURNAL_SHA256", hashlib.sha256(journal.read_bytes()).hexdigest()), \
                     self.assertRaisesRegex(ValueError, "successful transition"):
                    pkg.installed_705_reference()

    def test_installed_706_origin_requires_its_own_success_journal_and_raw_bytes(self):
        original = self.exact_fixture()
        with tempfile.TemporaryDirectory() as folder, patch.object(pkg, "test01_flash_reference", return_value=original), \
             patch.object(pkg, "sdk_file", side_effect=self.sdk.__getitem__), \
             patch.object(pkg, "installed_705_reference", return_value=original[0x4000:]):
            root = Path(folder); path = root/"706.fwsc"; journal = root/"706.jsonl"
            raw, _ = self.successor_fixture(product=pkg.DEVELOPMENT_PRODUCT); path.write_bytes(raw)
            package_hash = hashlib.sha256(raw).hexdigest()
            _, _, files = pkg.decode_package(raw); expected = files['flash.bin']['payload'][0x4000:]
            events = [{"event": "qualified_before_device_access", "package": {"package_sha256": package_hash}},
                      {"event": "completed", "identity": pkg.DEVELOPMENT_PRODUCT}]
            journal.write_text("\n".join(json.dumps(e) for e in events)+"\n")
            with patch.object(pkg, "INSTALLED_706_PACKAGE", path), patch.object(pkg, "INSTALLED_706_JOURNAL", journal), \
                 patch.object(pkg, "INSTALLED_706_PACKAGE_SHA256", package_hash), \
                 patch.object(pkg, "INSTALLED_706_JOURNAL_SHA256", hashlib.sha256(journal.read_bytes()).hexdigest()), \
                 patch.object(pkg, "INSTALLED_706_APP_SHA256", hashlib.sha256(expected).hexdigest()):
                self.assertEqual(pkg.installed_706_reference(), expected)
                with patch.object(pkg, "INSTALLED_706_APP_SHA256", pkg.INSTALLED_701_APP_SHA256), \
                     self.assertRaisesRegex(ValueError, "raw application SHA-256"):
                    pkg.installed_706_reference()
                events[-1]['identity'] = pkg.PRODUCT
                journal.write_text("\n".join(json.dumps(e) for e in events)+"\n")
                with patch.object(pkg, "INSTALLED_706_JOURNAL_SHA256", hashlib.sha256(journal.read_bytes()).hexdigest()), \
                     self.assertRaisesRegex(ValueError, "successful transition"):
                    pkg.installed_706_reference()

    def test_installed_707_origin_requires_its_own_success_journal_and_raw_bytes(self):
        original = self.exact_fixture()
        with tempfile.TemporaryDirectory() as folder, patch.object(pkg, "test01_flash_reference", return_value=original), \
             patch.object(pkg, "sdk_file", side_effect=self.sdk.__getitem__), \
             patch.object(pkg, "installed_706_reference", return_value=original[0x4000:]):
            root = Path(folder); path = root/"707.fwsc"; journal = root/"707.jsonl"
            raw, _ = self.successor_fixture(product=pkg.CANDIDATE_PRODUCT); path.write_bytes(raw)
            package_hash = hashlib.sha256(raw).hexdigest()
            _, _, files = pkg.decode_package(raw); expected = files['flash.bin']['payload'][0x4000:]
            events = [{"event": "qualified_before_device_access", "package": {"package_sha256": package_hash}},
                      {"event": "completed", "identity": pkg.CANDIDATE_PRODUCT}]
            journal.write_text("\n".join(json.dumps(e) for e in events)+"\n")
            with patch.object(pkg, "INSTALLED_707_PACKAGE", path), patch.object(pkg, "INSTALLED_707_JOURNAL", journal), \
                 patch.object(pkg, "INSTALLED_707_PACKAGE_SHA256", package_hash), \
                 patch.object(pkg, "INSTALLED_707_JOURNAL_SHA256", hashlib.sha256(journal.read_bytes()).hexdigest()), \
                 patch.object(pkg, "INSTALLED_707_APP_SHA256", hashlib.sha256(expected).hexdigest()):
                self.assertEqual(pkg.installed_707_reference(), expected)
                with patch.object(pkg, "INSTALLED_707_APP_SHA256", pkg.INSTALLED_701_APP_SHA256), \
                     self.assertRaisesRegex(ValueError, "raw application SHA-256"):
                    pkg.installed_707_reference()
                events[-1]['identity'] = pkg.PRODUCT
                journal.write_text("\n".join(json.dumps(e) for e in events)+"\n")
                with patch.object(pkg, "INSTALLED_707_JOURNAL_SHA256", hashlib.sha256(journal.read_bytes()).hexdigest()), \
                     self.assertRaisesRegex(ValueError, "successful transition"):
                    pkg.installed_707_reference()

    def test_recomputed_crcs_do_not_allow_exact_unit_metadata_changes(self):
        original = self.exact_fixture()
        with patch.object(pkg, "test01_flash_reference", return_value=original), patch.object(pkg, "sdk_file", side_effect=self.sdk.__getitem__):
            flash = bytearray(pkg.flash_image(self.app, pkg.KEY, pkg.TEST01_TEMPLATE))
            plain = bytearray(flash[0x4000:])
            pkg.sfc(plain, 0, len(plain), 0, pkg.KEY)
            plain[192+13] ^= 1
            struct.pack_into("<H", plain, 192, pkg.crc16(plain[194:224]))
            end = pkg.jlfs_header(plain)[3]
            struct.pack_into("<H", plain, 2, pkg.crc16(plain[32:end]))
            struct.pack_into("<H", plain, 0, pkg.crc16(plain[2:32]))
            pkg.sfc(plain, 0, len(plain), 0, pkg.KEY)
            flash[0x4000:] = plain
            with self.assertRaisesRegex(ValueError, "canonical"):
                pkg.validate_package(pkg.ufw(flash, self.loader, pkg.PRODUCT))

    def test_private_template_requires_pinned_report_journal_and_both_dumps(self):
        prefix = self.exact_fixture()
        dump = prefix + bytes(0x100000-len(prefix))
        sha = hashlib.sha256(dump).hexdigest()
        events = b'{"event":"synthetic verified double read"}\n'
        report = {"status":"verified_double_dump", "comparison":{"byte_equal":True,"sha256":sha},
                  "loader":{"chip_key":pkg.KEY,"device_type":3,"flash_id":0x856014},
                  "events_sha256":hashlib.sha256(events).hexdigest()}
        report_bytes = json.dumps(report).encode()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/"report.json").write_bytes(report_bytes)
            (root/"events.jsonl").write_bytes(events)
            for number in (1,2):
                (root/f"flash-pass-{number}.bin").write_bytes(dump)
            with patch.object(pkg,"TEST01_BACKUP",root), patch.object(pkg,"TEST01_DUMP_SHA256",sha), \
                 patch.object(pkg,"TEST01_APP_SHA256",hashlib.sha256(prefix[0x4000:]).hexdigest()), \
                 patch.object(pkg,"TEST01_REPORT_SHA256",hashlib.sha256(report_bytes).hexdigest()):
                self.assertEqual(pkg.test01_flash_reference(), prefix)
                for filename in ("report.json", "events.jsonl", "flash-pass-1.bin", "flash-pass-2.bin"):
                    path = root/filename; valid = path.read_bytes()
                    path.write_bytes(valid[:-1] + bytes([valid[-1]^1]))
                    with self.subTest(filename=filename), self.assertRaisesRegex(ValueError, "SHA-256"):
                        pkg.test01_flash_reference()
                    path.write_bytes(valid)

    def test_elf_extraction_excludes_noload(self):
        data, code = elf_fixture()
        actual, report = pkg.extract_elf(data, "app")
        self.assertEqual(actual, code)
        self.assertTrue(report["sections"][1]["noload"])

    def test_elf_bad_architecture_extent_or_lma_refused(self):
        source, _ = elf_fixture()
        for off, fmt, value in [(18, "H", 0x3E), (24, "I", 0), (58, "H", 0xFFFF), (64, "I", 0x01C00000)]:
            data = bytearray(source)
            struct.pack_into("<"+fmt, data, off, value)
            with self.subTest(off=off), self.assertRaises(ValueError):
                pkg.extract_elf(data, "app")
        with self.assertRaises(ValueError):
            pkg.extract_elf(source[:100], "app")


if __name__ == "__main__":
    unittest.main()
