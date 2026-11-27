import os,unittest
from pathlib import Path
from ue5_editor_material import masked_surface_profile,resolve_material
class MaskedProfileTests(unittest.TestCase):
    def test_profile_refusal(self):
        d=dict(blend='BLEND_Masked',material_domain='MD_Surface',shading_model='not_serialized',shading_model_field=None,outputs={},unsupported=[],opacity_mask_clip=None)
        self.assertTrue(masked_surface_profile(d))
        for patch in (dict(blend='BLEND_Additive'),dict(shading_model='MSM_Unlit'),dict(material_domain='MD_PostProcess'),dict(opacity_mask_clip=-1.),dict(opacity_mask_clip=1.1),dict(unsupported=['BasePropertyOverrides']),dict(outputs={'WorldPositionOffset':{'index':1}})):
            self.assertFalse(masked_surface_profile(dict(d,**patch)))
    @unittest.skipUnless(os.environ.get('UE56_EDITOR_PROJECT'),'Original fixture required')
    def test_original_graph(self):
        root=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content';d=resolve_material(root,'/Game/Characters/Mannequins/Materials/M_Mannequin');self.assertTrue(masked_surface_profile(d));self.assertIsNone(d['opacity_mask_clip']);self.assertEqual(d['nodes'][d['outputs']['OpacityMask']['index']]['kind'],'LinearInterpolate');self.assertEqual([n['value'] for n in d['nodes'].values() if n['parameter']=='Head Cutout'],[16.40704345703125])
