"""Original cooked package classes and hard references, not shader semantics."""
import os
import shutil
from pathlib import Path
import tempfile
import unittest
from project_preflight import read_record, preflight
from project_geometry import split_root_class


@unittest.skipUnless(os.environ.get('MATYA_ASSETS'), 'Original Matya fixtures required')
class SplitPackageInventory(unittest.TestCase):
    def test_original_ue4(self):
        expected={'SM_Worm':('StaticMesh',['/Game/M_Worm']),
                  'SK_Worm':('SkeletalMesh',['/Game/M_Worm','/Game/SK_Worm_PhysicsAsset','/Game/SK_Worm_Skeleton']),
                  'M_Worm':('Material',['/Game/T_Worm_A','/Game/T_Worm_D','/Game/T_Worm_N']),
                  'SK_Worm_PhysicsAsset':('PhysicsAsset',[]),'SK_Worm_Skeleton':('Skeleton',[]),
                  **{f'T_Worm_{suffix}':('Texture2D',[]) for suffix in ('A','D','N')}}
        for profile in ('4.18','4.27'):
            for name,(kind,refs) in expected.items():
                with self.subTest(profile=profile,name=name):
                    p=Path(os.environ['MATYA_ASSETS'])/profile/(name+'.uasset')
                    row=read_record(p,None)
                    self.assertEqual((row['classes'],row['references']),([kind],refs))
                    self.assertEqual(row['coverage'],'ue4_cooked_import_table')
                    self.assertEqual(row['soft_coverage'],'unknown')
                    self.assertEqual(split_root_class(p),kind)

    def test_missing_and_corrupt_header(self):
        source=Path(os.environ['MATYA_ASSETS'])/'4.27/SM_Worm.uasset'
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/source.name;p.write_bytes(source.read_bytes())
            self.assertEqual(read_record(p,None)['coverage'],'unknown')
            p.with_suffix('.uexp').write_bytes(source.with_suffix('.uexp').read_bytes())
            p.write_bytes(p.read_bytes()[:-8])
            self.assertEqual(read_record(p,None)['coverage'],'unknown')

    def test_project_geometry_plan(self):
        source=Path(os.environ['MATYA_ASSETS'])/'4.27'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);desc=root/'Worm.uproject';desc.write_text('{"FileVersion":3,"EngineAssociation":"4.27"}')
            content=root/'Content';shutil.copytree(source,content)
            plan=preflight(desc,'GEOMETRY')
            self.assertEqual(plan['seeds'],['/Game/SK_Worm','/Game/SM_Worm'])
            self.assertEqual(plan['inventory_count'],8)
            self.assertEqual(plan['closure_count'],8)
            self.assertEqual(plan['coverage_counts'],{'ue4_cooked_import_table':8})
            self.assertEqual(plan['dependency_counts'],{'available':6})
            (content/'T_Worm_D.uasset').unlink()
            plan=preflight(desc,'GEOMETRY')
            self.assertEqual(plan['dependencies']['/Game/T_Worm_D']['status'],'missing_game')
