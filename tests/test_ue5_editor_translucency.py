import os, unittest
from pathlib import Path
from ue5_editor_material import resolve_material, unlit_translucent_profile

class ProfileTests(unittest.TestCase):
    def test_profile_refusals(self):
        d=dict(blend='BLEND_Translucent',shading_model='MSM_Unlit',shading_model_field=1,material_domain='MD_Surface',outputs={},unsupported=[])
        self.assertTrue(unlit_translucent_profile(d))
        for change in (dict(blend='BLEND_Additive'),dict(blend='BLEND_Masked'),dict(shading_model_field=3),dict(shading_model_field=None),dict(shading_model='MSM_DefaultLit'),dict(material_domain='MD_PostProcess'),dict(unsupported=['BasePropertyOverrides']),dict(outputs={'PixelDepthOffset':{'index':1}})):
            self.assertFalse(unlit_translucent_profile(dict(d,**change)),change)

@unittest.skipUnless(os.environ.get('UE56_EDITOR_PROJECT'),'Original editor fixture required')
class TranslucentFixtureTests(unittest.TestCase):
    def test_source_shading_fields(self):
        root=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content'
        for name,expected in [('M_radial_ramp_soft',True),('M_SimpleGlow',True),('M_WP_Linkgun_Connection',True),('M_Mannequin',False),('M_LensFlare_02',False)]:
            p=next(root.rglob(name+'.uasset')); d=resolve_material(root,'/Game/'+p.relative_to(root).with_suffix('').as_posix());self.assertEqual(unlit_translucent_profile(d),expected,name)
