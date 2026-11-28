"""Original 522 compressed MeshDescription assets and corrupt bulk refusal."""
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from editor_static522 import read_static
from package_records import read_package, root_export
from skeleton_native import Reader
from ue4_property_records import read_records

EXPECTED={'SM_Chr_Attach_Straw_01.uasset':(12,20), 'SM_Env_Skydome_01.uasset':(91,160), 'SM_Veh_War_Balloon_01_OarLock_R.uasset':(71,142),'SM_Prop_Rope_01.uasset':(32,60)}

@unittest.skipUnless(os.environ.get('UE_STATIC522_FIXTURES'), 'Original Goblin static meshes required')
class Static522Tests(unittest.TestCase):
    def sources(self):
        root=Path(os.environ['UE_STATIC522_FIXTURES']);manifest=json.loads((Path(__file__).resolve().parents[1]/'docs/GOBLIN_FIXTURE.json').read_text())
        # The manifest's top-level field is identified once, not by guessing paths.
        records=dict(manifest["assets"], **{"SM_Prop_Rope_01.uasset":{"sha256":"7bb0d838cf91b8d2cf56e62404f60e692f624c31ac90ad418e467daf8e0fc0da"}})
        for name in EXPECTED:
            p=next(root.rglob(name)); self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),records[name]['sha256']);yield p

    def test_original_meshes(self):
        for p in self.sources():
            d=read_static(p);self.assertEqual((len(d['geometry']['vertices']),len(d['geometry']['triangles'])),EXPECTED[p.name]);self.assertEqual(len(d['materials']),1)

    def test_malformed_bulk_refusal(self):
        p=next(self.sources());meta,raw,table=read_package(p);e=root_export(table,'StaticMesh');r=Reader(raw[e.offset:e.offset+e.size]);read_records(r,table.names)
        # Original fixture has zero GUID marker, no high-resolution name or sockets.
        native=e.offset+r.pos;bulk=native+50
        self.assertEqual(struct.unpack_from('<I',raw,bulk)[0],0x203)
        for relative,fmt,value in ((4,'I',0),(8,'I',len(raw)),(12,'q',-1)):
            with self.subTest(relative=relative),tempfile.TemporaryDirectory() as folder:
                bad=bytearray(raw);struct.pack_into('<'+fmt,bad,bulk+relative,value);path=Path(folder)/p.name;path.write_bytes(bad)
                with self.assertRaises(ValueError):read_static(path)
