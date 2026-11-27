import os,unittest
from pathlib import Path
from ue5_editor_components import placements,class_defaults
from project_session import options_key

@unittest.skipUnless(os.environ.get('UE56_EDITOR_PROJECT'),'Original editor fixture required')
class EditorComponentTests(unittest.TestCase):
    def test_original_saved_components(self):
        root=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content'
        for rel,n,meshes,skips in [('Variant_Combat/Lvl_Combat.umap',58,64,0),('Variant_SideScrolling/Lvl_SideScrolling.umap',13,14,1)]:
            actors,errors=placements(root,root/rel);self.assertEqual(len(actors),n);self.assertEqual(sum(bool(c['package']) for a in actors for c in a['components']),meshes);self.assertEqual(len(errors),skips)
            for a in actors:
                seen=set()
                for c in a['components']:
                    self.assertNotIn(c['index'],seen);self.assertTrue(not c['parent'] or c['parent'] in seen);seen.add(c['index'])
            if 'Combat' in rel:
                door=next(a for a in actors if a['actor']=='BP_DoorFrame_C_1');self.assertEqual({c['name'] for c in door['components'] if c['package']},{'NODE_AddStaticMeshComponent-1','NODE_AddStaticMeshComponent-5',*('NODE_AddStaticMeshComponent-1_'+str(i) for i in range(4))});self.assertEqual(sum(c['default_origin']=='indexed_construction_template' for c in door['components']),4)
    def test_wrong_class_rejected(self):
        root=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content';p=next(root.rglob('BP_JumpPad.uasset'))
        with self.assertRaises(ValueError):class_defaults(p,'BP_NotTheClass_C')

class SessionOptionTests(unittest.TestCase):
    def test_components_not_equivalent_to_static_only(self):
        p={'scope':'ALL_MAPS','records':{'x':{'ue5':1017}}};self.assertNotEqual(options_key(p,'5.6',False,True,False,False),options_key(p,'5.6',False,False,False,False))

@unittest.skipUnless(os.environ.get('UE56_EDITOR_PROJECT'),'Original editor fixture required')
class CharacterDefaultsTests(unittest.TestCase):
    def test_explicit_cdo_body(self):
        from ue5_editor_components import character_defaults
        root=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content'
        for name,body in [('BP_ThirdPersonCharacter','SKM_Quinn_Simple'),('BP_CombatEnemy','SKM_Manny_Simple'),('BP_CombatCharacter','SKM_Quinn_Simple'),('BP_SideScrollingCharacter','SKM_Quinn_Simple'),('BP_PlatformingCharacter','SKM_Quinn_Simple')]:
            p=next(root.rglob(name+'.uasset'));d=character_defaults(p);self.assertTrue(d['mesh_package'].endswith('/'+body));self.assertEqual(d['mesh_fields']['RelativeRotation'],(0.,-90.,0.))
        with self.assertRaises(ValueError):character_defaults(next(root.rglob('BP_SideScrollingNPC.uasset')))
