"""Genuine UAssetAPI modern static mesh fixture acceptance."""
import os, shutil, struct, tempfile, unittest
from pathlib import Path
from collections import Counter
from cooked_static import read_static
from ue5_modern_static import package, PROFILES
from project_geometry import split_root_class

@unittest.skipUnless(os.environ.get('UASSETAPI_ASSETS'),'Set UASSETAPI_ASSETS')
class ModernStaticTests(unittest.TestCase):
    root=Path(os.environ.get('UASSETAPI_ASSETS',''))
    def source(self,v):
        return next((self.root/('TestUE'+v.replace('.','_'))).rglob('SM_BlueCube.uasset' if v=='5.4' else 'SM_Cube.uasset'))
    def test_geometry(self):
        for v in PROFILES:
            with self.subTest(v=v):
                p=self.source(v); d=read_static(p,v)
                self.assertEqual(split_root_class(p),'StaticMesh')
                self.assertEqual((len(d['positions']),len(d['faces'])),(24,12))
                self.assertEqual(Counter(d['slots']),{0:10,1:2} if v=='5.5' else {0:12})
                self.assertEqual(len(d['uvs'][0]),2 if v=='5.5' else 4)
                self.assertEqual(len(d['materials']),2 if v=='5.5' else 1)
                self.assertEqual(d['external_bulk_bytes'],{'5.4':0,'5.5':121292,'5.6':19708}[v])
                # Independent cuboid invariant: 8 welded corners, 12 triangles,
                # side lengths within float rounding of the source units.
                corners={tuple(round(x,3) for x in p) for p in d['positions']}
                self.assertEqual(len(corners),8)
                side=100 if v=='5.6' else 200
                for i in range(3): self.assertAlmostEqual(max(p[i] for p in corners)-min(p[i] for p in corners),side,places=3)
    def test_wrong_profile(self):
        for v in PROFILES:
            for other in PROFILES:
                if other!=v:
                    with self.assertRaises(ValueError): read_static(self.source(v),other)
    def test_corruption(self):
        for v in PROFILES:
            src=self.source(v)
            with tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp)/src.name; shutil.copyfile(src,p)
                side=p.with_suffix('.uexp'); original=src.with_suffix('.uexp').read_bytes(); side.write_bytes(original[:-1])
                with self.assertRaises(ValueError): read_static(p,v)
                side.write_bytes(original); root=package(p)[4].data; start=original.index(root)
                for offset,value in [({'5.4':218,'5.5':252,'5.6':271}[v],255),({'5.4':962,'5.5':900,'5.6':1015}[v],255)]:
                    broken=bytearray(original); broken[start+offset]=value; side.write_bytes(broken)
                    with self.assertRaises(ValueError): read_static(p,v)
                side.write_bytes(original)
                # Reject truncated package import/export header.
                p.write_bytes(src.read_bytes()[:-1])
                with self.assertRaises(ValueError): read_static(p,v)

    def test_material_instances(self):
        from ue5_cooked_material import read_instance
        blue=read_instance(self.source('5.4').with_name('MI_BlueCube.uasset'),'5.4')
        quinn=read_instance(self.source('5.6').with_name('MI_Quinn_01.uasset'),'5.6')
        self.assertEqual(blue['parent'],'/Game/Materials/M_Cube')
        self.assertEqual(blue['parameters'][0]['value'],0.)
        self.assertEqual(blue['parameters'][1]['name'],'ColorTint')
        self.assertEqual(blue['parameters'][1]['value'],[0.,0.41931700706481934,1.,1.])
        self.assertEqual(len(quinn['parameters']),5)
        self.assertEqual([p['value'].split('/')[-1] for p in quinn['parameters'] if p['kind']=='texture'],['T_Quinn_01_D','T_Quinn_01_N','T_Quinn_01_MRA'])
        self.assertTrue(all(p['uv_channel']==0 and p['sampling_scale']==1. for p in quinn['streaming']))
        for v,n in [('5.4','MI_BlueCube'),('5.6','MI_Quinn_01')]:
            src=self.source(v).with_name(n+'.uasset')
            with self.assertRaises(ValueError): read_instance(src,'5.6' if v=='5.4' else '5.4')
            with tempfile.TemporaryDirectory() as tmp:
                dst=Path(tmp)/src.name; shutil.copyfile(src,dst); raw=src.with_suffix('.uexp').read_bytes(); side=dst.with_suffix('.uexp')
                side.write_bytes(raw[:-1]); self.assertRaises(ValueError,read_instance,dst,v)
                bad=bytearray(raw); bad[14 if v=='5.4' else 12:18 if v=='5.4' else 16]=bytes(4); side.write_bytes(bad);self.assertRaises(ValueError,read_instance,dst,v)

    def test_modern_texture(self):
        import io
        from PIL import Image
        from ue5_modern_texture import read_texture55
        from native_texture import decode_rgba,read_texture
        src=self.source('5.5').with_name('T_Test.uasset')
        w,h,fmt,mips=read_texture55(src)
        self.assertEqual((w,h,fmt,len(mips)),(2048,2048,'PF_DXT1',12))
        for i,raw in enumerate(mips):
            a,b=max(1,w>>i),max(1,h>>i)
            dds=b'DDS '+struct.pack('<7I',124,0x81007,b,a,len(raw),0,1)+bytes(44)+struct.pack('<II4s5I',32,4,b'DXT1',0,0,0,0,0)+struct.pack('<5I',0x1000,0,0,0,0)+raw
            self.assertEqual(decode_rgba(a,b,fmt,raw),Image.open(io.BytesIO(dds)).convert('RGBA').tobytes())
        self.assertEqual(read_texture(src,'5.5'),(w,h,fmt,mips[0],12))
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/src.name; shutil.copyfile(src,p);shutil.copyfile(src.with_suffix('.uexp'),p.with_suffix('.uexp'))
            with self.assertRaises(ValueError):read_texture55(p)
            p.with_suffix('.ubulk').write_bytes(src.with_suffix('.ubulk').read_bytes()[:-1]);self.assertRaises(ValueError,read_texture55,p)
            shutil.copyfile(src.with_suffix('.ubulk'),p.with_suffix('.ubulk'));raw=bytearray(src.with_suffix('.uexp').read_bytes());raw[106]=1;p.with_suffix('.uexp').write_bytes(raw);self.assertRaises(ValueError,read_texture55,p)
