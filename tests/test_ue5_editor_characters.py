import os,unittest,struct
from pathlib import Path
from ue5_editor_components import character_fields
from ue5_editor_characters import placements
from ue5_editor_mesh import read_skeletal

class CharacterFieldsTest(unittest.TestCase):
    def test_serialized_instance_transform(self):
        t=dict(type=['StructProperty','Vector','/Script/CoreUObject'],flags=8,data=struct.pack('<3d',1,2,3))
        self.assertEqual(character_fields({'RelativeLocation':t})['RelativeLocation'],(1,2,3))
        for v in [dict(t,flags=32),dict(t,data=struct.pack('<3d',float('nan'),2,3))]:
            with self.assertRaises(ValueError):character_fields({'RelativeLocation':v})
        with self.assertRaises(ValueError):character_fields({'AttachSocketName':{}})

@unittest.skipUnless(os.environ.get('UE56_EDITOR_PROJECT'),'Original fixture required')
class CharacterPlacementTest(unittest.TestCase):
    def test_saved_instances(self):
        root=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content'
        for stem,n in [('MainLevel',6),('TestLevel',1)]:
            d=placements(root,root/f'MyStuff/Maps/{stem}.umap');self.assertEqual(len(d['records']),n);self.assertFalse(d['skipped'])
            for r in d['records']:
                self.assertEqual(r['mesh_fields']['RelativeLocation'],(0.,0.,-89.));self.assertEqual(len(r['overrides']),5)
        d=placements(root,root/'Variant_SideScrolling/Lvl_SideScrolling.umap');self.assertFalse(d['records']);self.assertEqual(len(d['skipped']),1);self.assertIn('No unique explicit skeletal mesh',d['skipped'][0]['detail'])
    @unittest.skipUnless(os.environ.get('UE_EDITOR_PAYLOAD_DECODER'),'Original payload decoder required')
    def test_unmatched_material_groups(self):
        p=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content/MyStuff/EnemyCharacter/Meshes/SK_EnemyCharacter.uasset'
        with self.assertRaisesRegex(ValueError,'Ambiguous skeletal material slot'):read_skeletal(p)
        d=read_skeletal(p,allow_unresolved_slots=True);self.assertEqual((len(d['vertices']),len(d['bones']),len(d['unresolved_material_groups'])),(56434,155,5))
        self.assertTrue(all(not d['materials'][d['group_to_slot'][g]][1] for g in d['slots']))
        self.assertEqual(len(d['original_materials']),5)
