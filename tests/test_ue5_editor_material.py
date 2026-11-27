import os,unittest,struct
from pathlib import Path
import numpy as np
from ue5_editor_texture import decode_delta,read_texture
from ue5_editor_material import read_material,resolve_material

class DeltaTests(unittest.TestCase):
    def test_stripe_boundaries_and_wrap(self):
        rng=np.random.default_rng(56);pixels=rng.integers(0,256,(65,13,4),dtype=np.uint8);encoded=pixels.copy()
        for y in range(1,len(pixels)):
            if y%32:encoded[y]=pixels[y]-pixels[y-1]
        self.assertTrue(np.array_equal(decode_delta(encoded.tobytes(),13,65),pixels))
        with self.assertRaises(ValueError):decode_delta(encoded.tobytes()[:-1],13,65)
        with self.assertRaises(ValueError):decode_delta(b'',9000,1)

@unittest.skipUnless(os.environ.get('UE56_EDITOR_PROJECT') and os.environ.get('UE_EDITOR_PAYLOAD_DECODER'),'Original editor fixture required')
class MaterialTests(unittest.TestCase):
    def root(self):return Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content'
    def path(self,stem):return next(self.root().rglob(stem+'.uasset'))
    def resolve(self,stem):return resolve_material(self.root(),'/Game/'+self.path(stem).relative_to(self.root()).with_suffix('').as_posix())
    def test_quinn_pixel_extrema_and_alpha(self):
        _,m=read_texture(self.path('T_Quinn_01_D'));self.assertEqual((m['width'],m['height']),(1024,1024));self.assertTrue(m['color_extrema_verified']);self.assertEqual(m['rgba_sha256'],'3edb555262b02300f798f201b32eac6c542290f2452d13afb197d2934a510698')
        with self.assertRaisesRegex(ValueError,'ColorMin mismatch'):read_texture(self.path('T_EnemySkull_Mask'))
    def test_nested_instances(self):
        d=self.resolve('MI_ThirdPersonColWay');self.assertEqual(len(d['chain']),3);nodes={n['parameter']:n for n in d['nodes'].values()};self.assertAlmostEqual(nodes['Roughness']['value'],.268,places=6);self.assertAlmostEqual(nodes['Base Color']['value'][1],.527115,places=6)
    def test_mannequin_channels(self):
        d=self.resolve('MI_Quinn_01');self.assertEqual(len(d['nodes']),54);n={v['parameter']:v for v in d['nodes'].values() if v['parameter']};self.assertTrue(n['MRA']['texture'].endswith('T_Quinn_01_MRA'));self.assertTrue(n['BNormal']['texture'].endswith('T_Quinn_01_N'));self.assertEqual(d['outputs']['Normal']['index'],62)
        d=self.resolve('MI_Manny_02_New');self.assertTrue(next(n for n in d['nodes'].values() if n['parameter']=='Logo?')['value'])
