import os,unittest
from pathlib import Path
from cooked_material_dependencies import inspect_asset,texture_references

class CookedMaterialDependencyTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('MATYA_ASSETS'),'Set MATYA_ASSETS')
    def test_worm(self):
        root=Path(os.environ['MATYA_ASSETS'])/'5.0';cls,imports=inspect_asset(root/'M_Worm.uasset','5.0','/Game/M_Worm')
        self.assertEqual(cls,'Material')
        self.assertEqual(texture_references(imports),['/Game/T_Worm_A','/Game/T_Worm_D','/Game/T_Worm_N'])
        with self.assertRaises(ValueError): inspect_asset(root/'T_Worm_A.uasset','5.0','/Game/T_Worm_D')
    @unittest.skipUnless(os.environ.get('UASSETAPI_ASSETS'),'Set UASSETAPI_ASSETS')
    def test_modern(self):
        root=Path(os.environ['UASSETAPI_ASSETS']);p=next(root.rglob('M_Cube_1.uasset'))
        cls,imports=inspect_asset(p,'5.5','/Game/Meshes/M_Cube_1')
        self.assertEqual(cls,'Material');self.assertEqual(texture_references(imports),['/Game/Textures/T_Test'])
        with self.assertRaises(ValueError):inspect_asset(p,'5.5','/Game/Meshes/M_Cube_2')
    def test_invalid_reference(self):
        with self.assertRaises(ValueError):texture_references([('/Script/Engine','Texture2D',-2,'T_Invalid')])
