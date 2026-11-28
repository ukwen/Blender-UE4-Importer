import os,unittest
from pathlib import Path
from dataclasses import replace
from classic_material import read_material,surface_input,property_map
from package_records import read_package

@unittest.skipUnless(os.environ.get('UASSETAPI_ASSETS'),'Original UE4 editor fixture required')
class ClassicMaterial522(unittest.TestCase):
    def path(self):return Path(os.environ['UASSETAPI_ASSETS'])/'TestEditorAssets/TestMaterial.uasset'
    def test_original_material(self):
        data=read_material(self.path());self.assertEqual(data['version'],522)
        self.assertEqual(data['outputs']['BaseColor']['index'],2)
        self.assertEqual(data['nodes'][2]['value'],(0.,255.,255.,0.))
    def test_bad_name_and_extent(self):
        m,b,t=read_package(self.path());root=t.exports[0];p=property_map(b,root,t.names)['BaseColor']
        for data in (p.data[:8]+b'\xff'*4+p.data[12:],p.data[:-1],p.data+b'\0'):
            with self.subTest(data=data.hex()),self.assertRaises(ValueError):surface_input(replace(p,data=data),t.names)
