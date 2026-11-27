"""Original Quinn UE5.6 fixed-weight inline LODs, no generated fixture."""
import os, shutil, tempfile, unittest
from pathlib import Path
from collections import Counter
from skeletal_mesh_native import read_mesh
from ue5_modern_static import package

@unittest.skipUnless(os.environ.get('UASSETAPI_ASSETS'),'Set UASSETAPI_ASSETS')
class ModernSkeletalTests(unittest.TestCase):
    def source(self): return next(Path(os.environ['UASSETAPI_ASSETS']).rglob('SKM_Quinn_Simple.uasset'))
    def test_lods(self):
        for lod,(verts,faces,slots) in enumerate(((45993,87280,{0:35612,1:51668}),(14865,26998,{0:10782,1:16216}),(7421,12998,{0:5276,1:7722}))):
            d=read_mesh(self.source(),'5.6',lod)
            self.assertEqual((len(d['positions']),len(d['faces']),len(d['bones'])),(verts,faces,89))
            self.assertEqual(Counter(d['slots']),slots)
            self.assertEqual(d['lod_index'],lod)
            self.assertEqual(d['skeleton_package'],'/Game/Characters/Mannequins/Meshes/SK_Mannequin')
            self.assertTrue(all(sum(w.values())==255 for w in d['weights']))
    def test_corruption(self):
        src=self.source()
        with tempfile.TemporaryDirectory() as t:
            dst=Path(t)/src.name;shutil.copyfile(src,dst);side=dst.with_suffix('.uexp');raw=src.with_suffix('.uexp').read_bytes();side.write_bytes(raw)
            start=raw.index(package(dst)[4].data)
            for offset in (466,10092,10580,534271,1638153,3388415):
                b=bytearray(raw);b[start+offset]=255;side.write_bytes(b)
                self.assertRaises(ValueError,read_mesh,dst,'5.6')
            side.write_bytes(raw[:-1]);self.assertRaises(ValueError,read_mesh,dst,'5.6')
            side.write_bytes(raw);self.assertRaises(ValueError,read_mesh,dst,'5.6',3)
