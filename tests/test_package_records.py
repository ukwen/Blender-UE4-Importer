"""Typed object-table profiles, tested against real source and controlled corruption."""
from dataclasses import FrozenInstanceError
from pathlib import Path
import os
import struct
import tempfile
import unittest
from package_records import read_package, decode_records, soft_references_522
from project_preflight import read_record


@unittest.skipUnless(os.environ.get('UASSETAPI_ASSETS'), 'Original UAssetAPI editor fixtures required')
class PackageRecordTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(os.environ['UASSETAPI_ASSETS'])

    def test_original_ue4(self):
        expected = {'TestActorBP': {'Blueprint','BlueprintGeneratedClass','MetaData','TestActorBP_C'},
                    'TestMaterial': {'Material','MetaData'}, 'TestSoundClass': {'SoundClass','MetaData'}}
        seen = set()
        for path in (self.root/'TestEditorAssets').glob('*.uasset'):
            meta, raw, table = read_package(path)
            self.assertEqual(meta['ue4'],522)
            self.assertIsNone(meta['ue5'])
            self.assertEqual({x.kind for x in table.exports if not x.outer},expected[path.stem])
            self.assertEqual(set(read_record(path,None)['classes']),expected[path.stem])
            self.assertEqual(read_record(path,None)['coverage'],'import_table')
            self.assertEqual(soft_references_522(meta,raw,table),['/Game/TestActorBP'] if path.stem=='TestActorBP' else [])
            self.assertRaises(FrozenInstanceError,setattr,table.exports[0],'name','changed')
            seen.add(path.stem)
        self.assertEqual(seen,set(expected))

    def test_corrupted_ue57(self):
        p = next((self.root/'TestEditorUE5_7').rglob('BP_FirstPersonCharacter.uasset'))
        m,raw,records = read_package(p)
        self.assertEqual(len(records.exports),69)
        self.assertIsNone(records.reference(0))
        self.assertRaises(ValueError,records.reference,-len(records.imports)-1)
        self.assertRaises(ValueError,records.reference,len(records.exports)+1)
        io,eo=m['import_offset'],m['export_offset']
        for offset,format_,value in [(io,'i',-1),(io+16,'i',-100001),(io+36,'i',2),(eo,'i',100001),(eo+28,'q',-1),(eo+36,'q',len(raw)+1),(eo+96,'q',-1)]:
            with self.subTest(offset=offset):
                bad=bytearray(raw);struct.pack_into('<'+format_,bad,offset,value)
                self.assertRaises(ValueError,decode_records,m,bad)
        self.assertRaises(ValueError,decode_records,m,raw[:-1])
        bad=dict(m,depends_offset=eo+1)
        self.assertRaises(ValueError,decode_records,bad,raw)
        bad=bytearray(raw);struct.pack_into('<i',bad,io+16,-1)
        rec=decode_records(m,bad)
        self.assertRaises(ValueError,rec.package,-1,mounts=('/unmatched/',))

    def test_wrong_profile_refused(self):
        p = next((self.root/'TestEditorUE5_7').rglob('*.uasset'))
        m,raw,_ = read_package(p)
        for bad in (dict(m,ue5=1011),dict(m,sidecars=['.uexp']),dict(m,flags=m['flags']|0x2000),dict(m,cell_export_count=1)):
            self.assertRaises(ValueError,decode_records,bad,raw)
        with tempfile.TemporaryDirectory() as d:
            broken=Path(d)/'broken.uasset';broken.write_bytes(raw[:16])
            self.assertRaises(ValueError,read_package,broken)
