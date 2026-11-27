import os,struct,unittest
from pathlib import Path
from ue5_editor_decals import fields,records

class DecalFields(unittest.TestCase):
    def test_explicit_size_and_signed_scale(self):
        def v(x):return dict(type=['StructProperty','Vector','/Script/CoreUObject'],flags=8,data=struct.pack('<3d',*x))
        t,s,p=fields({'DecalSize':v((2,3,4)),'RelativeScale3D':v((-1,2,3)),'SortOrder':dict(type=['IntProperty'],flags=0,data=struct.pack('<i',-2))})
        self.assertEqual(s,(2,3,4));self.assertEqual(t['RelativeScale3D'],(-1,2,3));self.assertEqual(p['SortOrder'],-2)
        self.assertIsNone(fields({})[1])
        for x in [(0,1,1),(float('nan'),1,1),(-1,1,1)]:
            with self.assertRaises(ValueError):fields({'DecalSize':v(x)})
        with self.assertRaises(ValueError):fields({'bAbsoluteLocation':{}})

@unittest.skipUnless(os.environ.get('UE56_EDITOR_PROJECT'),'Original editor fixture required')
class DecalFixture(unittest.TestCase):
    def test_mainlevel(self):
        c=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content';r=records(c,c/'MyStuff/Maps/MainLevel.umap');self.assertEqual(len(r['records']),561);self.assertFalse(r['skipped']);self.assertEqual(sum(x['decal_size_cm'] is not None for x in r['records']),549);self.assertTrue(all(x['material_status']=='missing' for x in r['records']));self.assertEqual(len({x['material_package'] for x in r['records']}),103)
