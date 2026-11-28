"""Original classic editor packages, with malformed table boundary checks."""
import os
from pathlib import Path
import struct
import unittest
from package_records import read_package, decode_records, soft_references_508
from legacy_static import read_legacy_static_path
from project_geometry import root_class
from project_preflight import read_record


@unittest.skipUnless(os.environ.get('UE_WESTERN_PROJECT'), 'Original Western Frontier required')
class Classic508Tests(unittest.TestCase):
    def setUp(self):
        self.root = Path(os.environ['UE_WESTERN_PROJECT'])
        self.paths = sorted(p for p in self.root.rglob('*') if p.suffix in ('.uasset', '.umap'))

    def test_corpus(self):
        self.assertEqual(len(self.paths),452)
        meshes=0
        for path in self.paths:
            meta,raw,table=read_package(path)
            self.assertEqual(meta['ue4'],508)
            report=read_record(path,None)
            self.assertEqual(report['coverage'],'import_table')
            self.assertEqual(report['soft_coverage'],'summary_table')
            if any(e.kind=='StaticMesh' and not e.outer for e in table.exports):
                self.assertEqual(root_class(path,None),'StaticMesh'); meshes+=1
        self.assertEqual(meshes,325)

    def test_corrupt_records(self):
        path=next(p for p in self.paths if p.name.startswith('SM_'))
        meta,raw,table=read_package(path)
        eo,io=meta['export_offset'],meta['import_offset']
        for offset,value in ((io,-1),(io+16,-100001),(eo,100001),(eo+28,-1),(eo+32,len(raw)+1)):
            bad=bytearray(raw);struct.pack_into('<i',bad,offset,value)
            with self.subTest(offset=offset),self.assertRaises(ValueError):decode_records(meta,bad)
        with self.assertRaises(ValueError):decode_records(meta,raw[:-1])
        with self.assertRaises(ValueError):soft_references_508(dict(meta,soft_package_count=1,soft_package_offset=meta['header_end']-1),raw,table)
        self.assertTrue(read_legacy_static_path(path)['points'])
