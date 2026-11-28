"""Native catalog and geometry routing never silently call inherited backends."""
import builtins
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from project_geometry import root_class, load_static, classify_geometry_roots
from project_preflight import read_record
from package_records import PackageRecords, ExportRecord
from editor_static522 import UnsupportedProfile

CORE={'uasset','umesh','umat','umap'}

class NativeBoundaryTests(unittest.TestCase):
    def setUp(self):
        real=builtins.__import__
        def block(name,*args,**kwargs):
            if name.split('.')[0] in CORE:
                self.fail('Unexpected inherited import: '+name)
            return real(name,*args,**kwargs)
        self.guard=patch('builtins.__import__',side_effect=block)
        self.guard.start();self.addCleanup(self.guard.stop)

    def test_unsupported_monolithic_is_explicit(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'legacy.uasset';p.write_bytes(b'not a package')
            meta=dict(status='tables_inspected',legacy=-7,ue4=518,ue5=None,sidecars=[],flags=0)
            with patch('package_inspector.inspect_package',return_value=meta):
                with self.assertRaises(NotImplementedError):root_class(p,None)
                with self.assertRaises(NotImplementedError):load_static(p,None,'4.27')
                row=read_record(p,None)
            self.assertEqual(row['coverage'],'unknown');self.assertIn('Unsupported native',row['detail'])

    def test_unsupported_522_native_payload_not_retried(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'native.uasset';p.write_bytes(b'controlled')
            with patch('package_inspector.inspect_package',return_value=dict(ue4=522,ue5=None)),patch('editor_static522.read_static',side_effect=UnsupportedProfile('unknown layout')):
                with self.assertRaisesRegex(UnsupportedProfile,'unknown layout'):load_static(p,None,'4.27')

    def test_ambiguous_geometry_never_selected(self):
        def entry(name,kind):return ExportRecord(name,0,0,0,0,0,0,None,None,False,kind)
        table=PackageRecords((),(),(entry('a','StaticMesh'),entry('b','StaticMesh')))
        with self.assertRaises(NotImplementedError):classify_geometry_roots(table)
        self.assertEqual(classify_geometry_roots(PackageRecords((),(),(entry('a','Blueprint'),entry('b','BlueprintGeneratedClass')))),'NonGeometry')
        self.assertEqual(classify_geometry_roots(PackageRecords((),(),(entry('a','SkeletalMesh'),entry('a_USkeletalMeshEditorData','SkeletalMeshEditorData')))),'SkeletalMesh')

    @unittest.skipUnless(os.environ.get('UASSETAPI_ASSETS'),'Original packages required')
    def test_original_multiroot_and_non_geometry(self):
        root=Path(os.environ['UASSETAPI_ASSETS'])
        for path,kind in ((root/'TestJson/ABP_SMG_A.uasset','NonGeometry'),(root/'TestEditorAssets/TestActorBP.uasset','NonGeometry'),(root/'TestEditorAssets/TestMaterial.uasset','Material'),(root/'TestEditorAssets/TestSoundClass.uasset','SoundClass')):
            with self.subTest(path=path.name):self.assertEqual(root_class(path,None),kind)
