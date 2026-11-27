import os,unittest,struct
from pathlib import Path
import numpy as np
from ue5_editor_texture import decode_delta,read_texture
from ue5_editor_material import read_material,resolve_material

class DeltaTests(unittest.TestCase):
    def test_stripe_boundaries_and_wrap(self):
        rng=np.random.default_rng(56)
        for w,h,step in [(1024,65,32),(512,137,64),(256,260,128),(128,513,256)]:
            pixels=rng.integers(0,256,(h,w,4),dtype=np.uint8);encoded=pixels.copy()
            for y in range(1,h):
                if y%step:encoded[y]=pixels[y]-pixels[y-1]
            self.assertTrue(np.array_equal(decode_delta(encoded.tobytes(),w,h),pixels))
        with self.assertRaises(ValueError):decode_delta(encoded.tobytes()[:-1],w,h)
        with self.assertRaises(ValueError):decode_delta(b'',9000,1)
    def test_nonpower_opaque_regions(self):
        rng=np.random.default_rng(61);w,h=127,130
        pixels=rng.integers(0,256,(h,w,4),dtype=np.uint8);pixels[:,:,3]=255;encoded=pixels.copy()
        for left,right,step in [(0,64,53),(64,w,55)]:
            for y in range(1,h):
                if y%step:encoded[y,left:right]=pixels[y,left:right]-pixels[y-1,left:right]
        decoded,regions,profile=decode_delta(encoded.tobytes(),w,h,opaque=True,return_regions=True)
        self.assertEqual(regions,[(0,64,53),(64,127,55)]);self.assertTrue(np.array_equal(decoded,pixels))
        with self.assertRaises(ValueError):decode_delta(encoded.tobytes(),w,h)
        encoded[1,0,3]=255
        with self.assertRaises(ValueError):decode_delta(encoded.tobytes(),w,h,opaque=True)

@unittest.skipUnless(os.environ.get('UE56_EDITOR_PROJECT') and os.environ.get('UE_EDITOR_PAYLOAD_DECODER'),'Original editor fixture required')
class MaterialTests(unittest.TestCase):
    def root(self):return Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content'
    def path(self,stem):return next(self.root().rglob(stem+'.uasset'))
    def resolve(self,stem):return resolve_material(self.root(),'/Game/'+self.path(stem).relative_to(self.root()).with_suffix('').as_posix())
    def test_quinn_pixel_extrema_and_alpha(self):
        _,m=read_texture(self.path('T_Quinn_01_D'));self.assertEqual((m['width'],m['height']),(1024,1024));self.assertTrue(m['color_extrema_verified']);self.assertEqual(m['rgba_sha256'],'3edb555262b02300f798f201b32eac6c542290f2452d13afb197d2934a510698')
        _,mask=read_texture(self.path('T_EnemySkull_Mask'));self.assertEqual(mask['delta_regions'],[(0,640,53),(640,1254,55)]);self.assertTrue(mask['color_extrema_verified'])
        _,flare=read_texture(self.path('T_Lensflare_01'));self.assertEqual(flare['delta_regions'],[(0,512,64)])
    def test_nested_instances(self):
        d=self.resolve('MI_ThirdPersonColWay');self.assertEqual(len(d['chain']),3);nodes={n['parameter']:n for n in d['nodes'].values()};self.assertAlmostEqual(nodes['Roughness']['value'],.268,places=6);self.assertAlmostEqual(nodes['Base Color']['value'][1],.527115,places=6)
    def test_mannequin_channels(self):
        d=self.resolve('MI_Quinn_01');self.assertEqual(len(d['nodes']),54);n={v['parameter']:v for v in d['nodes'].values() if v['parameter']};self.assertTrue(n['MRA']['texture'].endswith('T_Quinn_01_MRA'));self.assertTrue(n['BNormal']['texture'].endswith('T_Quinn_01_N'));self.assertEqual(d['outputs']['Normal']['index'],62)
        d=self.resolve('MI_Manny_02_New');self.assertTrue(next(n for n in d['nodes'].values() if n['parameter']=='Logo?')['value'])
