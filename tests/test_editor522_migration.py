"""Original UE4.27 skeletal and physics migration fixtures."""
import os
from pathlib import Path
import unittest
from package_records import read_editor522, root_export, classic_custom_versions
from editor_skeletal import read_editor_mesh
from editor_skeleton import read_editor_skeleton
from physics_native import read_physics, mesh_physics_reference
from project_geometry import root_class

@unittest.skipUnless(os.environ.get('UE_EDITOR522_FIXTURES'), 'Original UE4.27 skeletal fixtures required')
class Editor522MigrationTests(unittest.TestCase):
    root = Path(os.environ.get('UE_EDITOR522_FIXTURES',''))

    def test_original_skeleton(self):
        path=self.root/'UE4_Mannequin_Skeleton.uasset'
        self.assertEqual(root_class(path,None),'Skeleton')
        data=read_editor_skeleton(path)
        self.assertEqual((len(data['bones']),len(data['sockets'])),(72,20))
        self.assertTrue(all(s['bone'] in {b['name'] for b in data['bones']} for s in data['sockets']))

    def test_original_meshes_and_physics(self):
        expected={'Ranger_01':8200,'Shaman_01':9002,'Warrior_Male_01':11432,'Wizard_01':8260}
        for name,count in expected.items():
            with self.subTest(asset=name):
                mesh=self.root/('SK_Chr_'+name+'.uasset');physics=self.root/('PHYS_Chr_'+name+'.uasset')
                self.assertEqual(root_class(mesh,None),'SkeletalMesh');self.assertEqual(root_class(physics,None),'PhysicsAsset')
                data=read_editor_mesh(mesh);ph=read_physics(physics)
                self.assertEqual((len(data['positions']),len(data['bones'])),(count,44))
                self.assertEqual(mesh_physics_reference(mesh).rsplit('/',1)[-1],physics.stem)
                self.assertEqual(ph['preview_mesh'].rsplit('/',1)[-1],mesh.stem)
                self.assertTrue(all(sum(w.values())==255 for w in data['weights']))
                self.assertTrue(all(b['bone'] in {x['name'] for x in data['bones']} for b in ph['bodies']))
        vehicle=self.root/'SK_Veh_War_Balloon_01.uasset';d=read_editor_mesh(vehicle)
        self.assertEqual((len(d['positions']),len(d['bones'])),(62917,11))
        self.assertEqual(mesh_physics_reference(vehicle).rsplit('/',1)[-1],'PHYS_Veh_War_Balloon_01Asset')

    def test_root_and_custom_versions_reject_wrong_identity(self):
        _,raw,table=read_editor522(self.root/'SK_Chr_Ranger_01.uasset')
        with self.assertRaises(ValueError):root_export(table,'Skeleton')
        self.assertEqual(len(classic_custom_versions(raw)),12)
        bad=bytearray(raw);bad[44:60]=bad[24:40]
        with self.assertRaises(ValueError):classic_custom_versions(bad)
        with self.assertRaises(ValueError):classic_custom_versions(raw[:25])
