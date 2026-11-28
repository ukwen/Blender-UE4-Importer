import os,tempfile,unittest
from pathlib import Path
from saved_project_levels import validate_selection
from ue5_level_layout import inventory,saved_bool
from ue5_material_semantics import base_property_audit

class SavedLevelTests(unittest.TestCase):
    def test_selection(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);project=root/'P.uproject';project.touch();c=root/'Content';c.mkdir();p=c/'A.umap';p.touch();q=root/'B.umap';q.touch()
            self.assertEqual(validate_selection(project,[p]),[p])
            for paths in ([],[p,p],[q],[c/'missing.umap']):
                with self.assertRaises(ValueError):validate_selection(project,paths)
            (c/'__ExternalActors__').mkdir();x=c/'__ExternalActors__'/'x.umap';x.touch()
            with self.assertRaises(ValueError):validate_selection(project,[x])
    def test_external_actor_root_cannot_escape(self):
        from ue5_editor_scene import external_packages
        with tempfile.TemporaryDirectory() as d:
            r=Path(d);c=r/"Content";c.mkdir();outside=r/"outside";outside.mkdir();(c/"__ExternalActors__").symlink_to(outside,target_is_directory=True)
            with self.assertRaises(ValueError):external_packages(c,c/"A.umap")
    def test_saved_bool(self):
        self.assertIsNone(saved_bool({},'x'))
        for flags,expected in ((0,False),(16,True)):
            self.assertIs(saved_bool({'x':dict(type=['BoolProperty'],flags=flags,data=b'')},'x'),expected)
        with self.assertRaises(ValueError):saved_bool({'x':dict(type=['BoolProperty'],flags=32,data=b'')},'x')
    def test_invalid_child_does_not_inherit_parent_override(self):
        import struct
        f=dict(type=['FloatProperty'],flags=0,data=struct.pack('<f',.3).hex());b=dict(type=['BoolProperty'],flags=16,data='');bad=dict(b,flags=32)
        base={};rows,issues=base_property_audit([dict(source_package='child',properties={'bOverride_OpacityMaskClipValue':bad}),dict(source_package='parent',properties={'bOverride_OpacityMaskClipValue':b,'OpacityMaskClipValue':f})],base)
        self.assertEqual([x['status'] for x in rows],['invalid_flag','shadowed_by_child']);self.assertEqual(base,{});self.assertTrue(issues)
    @unittest.skipUnless(os.environ.get('UE56_EDITOR_PROJECT'),'Original fixture required')
    def test_original_partition_ownership(self):
        c=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content';expected={'Lvl_Platforming':144,'Lvl_ThirdPerson':65,'Lvl_SideScrolling':118,'Lvl_Combat':138}
        for p in c.rglob('Lvl_*.umap'):
            r=inventory(c,p);self.assertEqual(r['owned_external_packages'],expected.pop(p.stem));self.assertEqual(r['external_errors'],[]);self.assertTrue(r['flags']['bIsPartitioned']);self.assertIs(r['partition']['streaming_enabled'],False);self.assertEqual(r['composition_candidates'],[])
        self.assertEqual(expected,{})
        r=inventory(c,c/'MyStuff/Maps/MainLevel.umap');self.assertIsNone(r['partition']);self.assertEqual(r['owned_external_packages'],0)
