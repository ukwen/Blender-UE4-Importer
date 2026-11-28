import os,unittest
from pathlib import Path
from ue5_fog_preview import plan
from ue5_material_semantics import base_property_audit
from ue5_editor_lighting import records

class FogTests(unittest.TestCase):
    def fixture(self):return dict(kind='ExponentialHeightFog',actor='fog',properties={'FogDensity':.04},fields={'RelativeLocation':(0,0,-600),'RelativeScale3D':(1,1,1),'RelativeRotation':(0,0,0)},untranslated_component_fields=[])
    def test_plan(self):
        d=plan([self.fixture()]);self.assertEqual(d['status'],'planned');self.assertEqual(d['reference_height_m'],-6);self.assertEqual(d['source_density'],.04)
    def test_reject_missing_and_unknown(self):
        r=self.fixture();self.assertEqual(plan([r,r])['status'],'unsupported');r['properties']['StartDistance']=3;self.assertEqual(plan([r])['status'],'unsupported');r['properties']={};self.assertEqual(plan([r])['status'],'unsupported')
    @unittest.skipUnless(os.environ.get('UE56_EDITOR_PROJECT'),'Original fixture required')
    def test_real_maps(self):
        c=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content';p=[]
        for m in c.rglob('*.umap'):
            try:p.append(plan(records(c,m)['records']))
            except ValueError:continue
        self.assertEqual(len(p),6);self.assertEqual(sum(x['status']=='planned' for x in p),4)

class BasePropertyTests(unittest.TestCase):
    def test_active_child_and_inactive_parent(self):
        import struct
        def flag(v):return dict(type=['BoolProperty'],flags=16 if v else 0,data='')
        def val(v):return dict(type=['FloatProperty'],flags=0,data=struct.pack('<f',v).hex())
        def row(p,props):return dict(source_package=p,properties=props)
        history=[row('child',{'bOverride_OpacityMaskClipValue':flag(True),'OpacityMaskClipValue':val(.25),'bOverride_BlendMode':flag(True)}),row('parent',{'bOverride_OpacityMaskClipValue':flag(True),'OpacityMaskClipValue':val(.5),'TwoSided':flag(True)})];base={};a,i=base_property_audit(history,base);self.assertEqual(base['opacity_mask_clip'],.25);self.assertEqual({(x['source_package'],x['property']):x['status'] for x in a},{('child','BlendMode'):'active_unresolved',('child','OpacityMaskClipValue'):'applied',('parent','OpacityMaskClipValue'):'shadowed_by_child',('parent','TwoSided'):'inactive_no_flag'});self.assertEqual(i,['Unresolved base property: BlendMode'])
