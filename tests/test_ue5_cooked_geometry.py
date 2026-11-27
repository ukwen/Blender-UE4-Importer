"""Native UE5.0 cooked geometry cross-version and malformed-input acceptance."""
import os, shutil, tempfile, unittest, struct
from pathlib import Path
from cooked_static import read_static
from skeletal_mesh_native import read_mesh
from skeleton_native import read_cooked_skeleton
from ue5_cooked_geometry import package

@unittest.skipUnless(os.environ.get('MATYA_ASSETS'),'Set MATYA_ASSETS')
class UE5CookedGeometry(unittest.TestCase):
    root=Path(os.environ.get('MATYA_ASSETS',''))
    def test_meshes(self):
        for reader,name in ((read_static,'SM_Worm'),(read_mesh,'SK_Worm')):
            a=reader(self.root/'5.0'/f'{name}.uasset','5.0'); b=reader(self.root/'4.27'/f'{name}.uasset','4.27')
            self.assertEqual((len(a['positions']),len(a['faces'])),(640,572))
            for key in ('positions','faces','normals','tangents','signs','slots','materials'):
                self.assertEqual(a[key],b[key],key)
            self.assertLessEqual(max(abs(x-y) for u,v in zip(a['uvs'],b['uvs']) for x,y in zip(u,v)),0.00048828125)
            if name.startswith('SK'):
                self.assertEqual(a['weights'],b['weights'])
                self.assertEqual([x['name'] for x in a['bones']],[x['name'] for x in b['bones']])
                for x,y in zip(a['bones'],b['bones']):
                    self.assertEqual(x['parent'],y['parent'])
                    self.assertLess(max(abs(v-w) for key in ('rotation','translation','scale') for v,w in zip(x[key],y[key])),1e-6)
    def test_skeleton(self):
        _,bones=read_cooked_skeleton(self.root/'5.0/SK_Worm_Skeleton.uasset','5.0'); mesh=read_mesh(self.root/'5.0/SK_Worm.uasset','5.0')
        self.assertEqual(len(bones),6)
        for x,y in zip(bones,mesh['bones']):
            self.assertEqual((x['name'],x['parent']),(y['name'],y['parent']))
            self.assertLess(max(abs(v-w) for key in ('rotation','translation','scale') for v,w in zip(x[key],y[key])),1e-12)
    def test_root_classes(self):
        types={package(p)[0] for p in (self.root/'5.0').glob('*.uasset')}
        self.assertEqual(types,{'StaticMesh','SkeletalMesh','Skeleton','Texture2D','PhysicsAsset','Material'})
    def test_wrong_profiles_and_classes(self):
        for reader,name in ((read_static,'SM_Worm'),(read_mesh,'SK_Worm'),(read_cooked_skeleton,'SK_Worm_Skeleton')):
            for v,profile in [('4.27','5.0'),('5.0','4.27')]:
                with self.assertRaises(ValueError): reader(self.root/v/f'{name}.uasset',profile)
            with self.assertRaises(ValueError): reader(self.root/'5.0/M_Worm.uasset','5.0')
    def test_malformed(self):
        for reader,name,changes in ((read_static,'SM_Worm',[(40999,0xff),(41201,0),(56633,0xff),(56634,0xff)]),(read_mesh,'SK_Worm',[(0,0xff),(12920,0),(28330,0),(28360,0xff)])):
            source=self.root/'5.0'/f'{name}.uasset'
            with tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp)/source.name; shutil.copyfile(source,p)
                if source.with_suffix('.ubulk').exists(): shutil.copyfile(source.with_suffix('.ubulk'),p.with_suffix('.ubulk'))
                data=source.with_suffix('.uexp').read_bytes(); side=p.with_suffix('.uexp')
                side.write_bytes(data[:-1]); self.assertRaises(ValueError,reader,p,'5.0')
                # Mutations are at fixture-specific offsets, not used by the decoder.
                for offset,val in changes:
                    corrupt=bytearray(data); corrupt[offset]=val; side.write_bytes(corrupt)
                    if name=='SM_Worm' and offset in (56633,56634):
                        # corrupt full index, not merely alter valid topology
                        corrupt[56633:56635]=b'\xff\xff'; side.write_bytes(corrupt)
                    self.assertRaises(ValueError,reader,p,'5.0')
                side.write_bytes(data)
                if name=='SM_Worm':
                    p.with_suffix('.ubulk').unlink(); self.assertRaises(ValueError,reader,p,'5.0')
                    p.with_suffix('.ubulk').write_bytes(b'bad'); self.assertRaises(ValueError,reader,p,'5.0')
