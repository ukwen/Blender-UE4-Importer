import os,struct,unittest
from pathlib import Path
from collections import Counter
from ue5_editor_lighting import records,properties,srgb_linear

class LightingPropertiesTests(unittest.TestCase):
    def test_color_and_bool(self):
        p=properties({'LightColor':{'type':['StructProperty','Color','/Script/CoreUObject'],'data':bytes([12,34,56,0]),'flags':8},'CastShadows':{'type':['BoolProperty'],'flags':0,'data':b''}},[])
        self.assertEqual(p,{'LightColor':[56,34,12,0],'CastShadows':False})
        self.assertAlmostEqual(srgb_linear(128),.2158605001)
    def test_reject_nan(self):
        with self.assertRaises(ValueError):properties({'Intensity':{'type':['FloatProperty'],'data':struct.pack('<f',float('nan')),'flags':0}},[])

@unittest.skipUnless(os.environ.get('UE56_EDITOR_PROJECT'),'Original editor fixture required')
class LightingFixtureTests(unittest.TestCase):
    def test_original_root_records(self):
        root=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content'
        total=Counter();seen=set()
        for p in root.rglob('*.umap'):
            if p.relative_to(root).as_posix()=='MyStuff/TestLevel.umap':
                with self.assertRaises(ValueError):records(root,p)
                continue
            report=records(root,p);self.assertFalse(report['skipped']);total.update(x['kind'] for x in report['records'])
            for x in report['records']:
                key=(x['source'],x['actor']);self.assertNotIn(key,seen);seen.add(key)
        self.assertEqual(total,{'SpotLight':114,'PointLight':26,'DirectionalLight':6,'PlayerStart':6,'SkyLight':6,'ExponentialHeightFog':6,'SkyAtmosphere':5,'PostProcessVolume':5,'AtmosphericFog':1})
