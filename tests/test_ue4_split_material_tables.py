"""Original split object-map validation, independent of Blender."""
import os, shutil, tempfile, unittest
from pathlib import Path
from project_geometry import read_ue4_split_tables
from cooked_material_dependencies import inspect_asset, texture_references
from unittest.mock import patch
from editor_texture import read_editor_texture

class NativeTextureBoundary(unittest.TestCase):
    def test_unknown_profile_does_not_enter_legacy(self):
        with patch('package_inspector.inspect_package',return_value={'ue4':518,'ue5':None}):
            with self.assertRaisesRegex(NotImplementedError,'native UE4'):read_editor_texture('unknown.uasset')

@unittest.skipUnless(os.environ.get('MATYA_ASSETS'),'Original Matya fixtures required')
class SplitMaterialTables(unittest.TestCase):
    def test_original_tables(self):
        for v in ('4.18','4.27'):
            p=Path(os.environ['MATYA_ASSETS'])/v/'M_Worm.uasset'
            cls,name,_,imports,exports=read_ue4_split_tables(p)
            self.assertEqual((cls,name,len(exports)),('Material','M_Worm',4 if v=='4.18' else 1))
            self.assertEqual(texture_references(imports),['/Game/T_Worm_A','/Game/T_Worm_D','/Game/T_Worm_N'])
            with self.assertRaises(ValueError):inspect_asset(p,v,'/Game/Renamed')
    def test_genuine_filtered_source_edges(self):
        from cooked_classic_material import read_source_edges
        p=Path(os.environ['MATYA_ASSETS'])/'4.18'/'M_Worm.uasset'
        result=read_source_edges(p)
        self.assertEqual(result['blend'],'BLEND_Translucent')
        self.assertEqual({k:v['texture'] for k,v in result['edges'].items()},
            {'BaseColor':'/Game/T_Worm_D','Normal':'/Game/T_Worm_N','Opacity':'/Game/T_Worm_A'})
        self.assertEqual(result['edges']['Normal']['sampler'],'SAMPLERTYPE_Normal')
        with self.assertRaises(NotImplementedError):read_source_edges(p.parent.parent/'4.27'/'M_Worm.uasset')
    def test_sidecar_corruption(self):
        src=Path(os.environ['MATYA_ASSETS'])/'4.18'/'M_Worm.uasset'
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/src.name;shutil.copyfile(src,p);side=p.with_suffix('.uexp');raw=src.with_suffix('.uexp').read_bytes()
            for bad in (raw[:-1],raw[:-4]+bytes(4),raw[:10]+raw[11:],raw[:-4]+b'x'+raw[-4:]):
                side.write_bytes(bad)
                with self.assertRaises(ValueError):read_ue4_split_tables(p)
