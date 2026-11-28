"""Native reference boundary must not load inherited package classes."""
import builtins
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from classic_map_records import MapEntry, MapRecords
from package_records import ImportRecord, PackageRecords
from reference_identity import package_reference


class ReferenceIdentityTests(unittest.TestCase):
    def test_typed_references_and_untrusted_objects(self):
        records = (ImportRecord('/Script/CoreUObject','Package',0,'/Game/Props/Mesh','',False),
                   ImportRecord('/Script/Engine','StaticMesh',-1,'Mesh','',False),
                   ImportRecord('/Script/CoreUObject','Package',0,'/Script/Engine','',False),
                   ImportRecord('/Script/CoreUObject','Class',-3,'StaticMesh','',False))
        owner = SimpleNamespace(table=PackageRecords((),records,()))
        refs = [MapEntry(owner,-i,r) for i,r in enumerate(records,1)]
        real_import = builtins.__import__
        def guarded(name,*args,**kwargs):
            if name.split('.')[0] in {'uasset','umap','umat','umesh'}:
                raise AssertionError('Inherited import attempted: '+name)
            return real_import(name,*args,**kwargs)
        with patch('builtins.__import__',guarded):
            self.assertEqual(package_reference(refs[1]),'/Game/Props/Mesh')
            self.assertEqual(package_reference(refs[0]),'/Game/Props/Mesh')
            self.assertEqual(package_reference(refs[3]),'')
            self.assertEqual(package_reference(None),'')
            self.assertEqual(package_reference(SimpleNamespace(object_name='/Game/fake',package_identity='/Game/fake')),'')
        invalid = MapEntry(owner,-99,records[0])
        with self.assertRaises(ValueError): package_reference(invalid)
        cyclic = ImportRecord('/Script/CoreUObject','Class',-1,'X','',False)
        with self.assertRaisesRegex(ValueError,'cycle'):
            package_reference(MapEntry(SimpleNamespace(table=PackageRecords((),(cyclic,),())),-1,cyclic))

    @unittest.skipUnless(os.environ.get('UE_WESTERN_PROJECT'),'Original Western project required')
    def test_original_map_reference_identities(self):
        p=next(Path(os.environ['UE_WESTERN_PROJECT']).rglob('Overview.umap'))
        m=MapRecords(p)
        refs=[(r,package_reference(r)) for r in m.imports]
        self.assertTrue(any(r.record.kind=='StaticMesh' and k.startswith('/Game/') for r,k in refs))
        self.assertTrue(any(r.record.kind=='Package' and k.startswith('/Game/') for r,k in refs))
        self.assertTrue(all(k==m.table.package(r.index) for r,k in refs))
        self.assertTrue(all(not package_reference(r) for r in m.exports))
