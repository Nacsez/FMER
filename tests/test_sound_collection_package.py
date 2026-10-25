# SPDX-License-Identifier: GPL-3.0-only
"""Packaging refuses stale render evidence and missing/changed auditions."""
from copy import deepcopy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import package_sound_collections as packaging
from package_sound_collections import validate_rendered


class RenderPackaging(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name).resolve()
        self.manifest={'patches':[]};self.analysis={'results':[]}
        payload=b'explicit packaging test fixture; not actual audio'
        checksum=hashlib.sha256(payload).hexdigest()
        for i in range(192):
            clips=[];measurements=[]
            for slug in ('performance','soft','dry'):
                path=f'{i}-{slug}.wav';(self.root/path).write_bytes(payload)
                clips.append(dict(path=path))
                measurements.append(dict(test=slug,sha256=checksum))
            measurements.extend(dict(test='matrix'+str(j)) for j in range(11))
            metrics=dict(failures=[],render_count=14)
            self.manifest['patches'].append(dict(id=str(i),clips=clips,metrics=metrics))
            self.analysis['results'].append(dict(id=str(i),clips=deepcopy(clips),metrics=deepcopy(metrics),measurements=measurements))

    def test_complete_set_passes(self):
        validate_rendered(self.root,self.manifest,self.analysis)

    def test_stale_or_incomplete_measurements_cannot_pass(self):
        for bad in ({'results':[]},{'results':self.analysis['results'][:-1]}):
            with self.assertRaises(ValueError):validate_rendered(self.root,self.manifest,bad)
        self.manifest['patches'][0]['clips']=[]
        with self.assertRaises(ValueError):validate_rendered(self.root,self.manifest,self.analysis)

    def test_missing_or_modified_audio_cannot_pass(self):
        path=self.root/'0-soft.wav';path.write_bytes(b'changed')
        with self.assertRaises(ValueError):validate_rendered(self.root,self.manifest,self.analysis)
        path.unlink()
        with self.assertRaises(ValueError):validate_rendered(self.root,self.manifest,self.analysis)

    def test_existing_archive_is_preserved_before_creating_output(self):
        archive=self.root/'review.zip';archive.write_bytes(b'owner archive')
        with patch.object(packaging,'ROOT',self.root),self.assertRaises(ValueError):
            packaging.package(self.root,self.root/'review')
        self.assertEqual(archive.read_bytes(),b'owner archive')
        self.assertFalse((self.root/'review').exists())


if __name__=='__main__':unittest.main()
