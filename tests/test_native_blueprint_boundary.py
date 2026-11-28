"""Native defaults boundary and typed component associations."""
import builtins
import os
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from blueprint_defaults import BlueprintResolver
from classic_blueprint import BlueprintRecords
from package_records import ExportRecord, ImportRecord, PackageRecords
from ue4_property_records import PropertyRecord

class NativeBlueprintBoundaryTests(unittest.TestCase):
    def setUp(self):
        real = builtins.__import__
        def guarded(name,*args,**kwargs):
            if name.split('.')[0] in {'uasset','umesh','umat','umap'}:
                self.fail('Inherited module requested: '+name)
            return real(name,*args,**kwargs)
        guard=patch('builtins.__import__',side_effect=guarded);guard.start();self.addCleanup(guard.stop)

    def test_unsupported_monolithic_and_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'Unknown.uasset';p.write_bytes(b'controlled')
            resolver=BlueprintResolver(SimpleNamespace(resolve_package=lambda _:p));key=('/Game/Unknown','Unknown_C')
            with patch('package_inspector.inspect_package',return_value={'ue4':518,'ue5':None}):
                r=resolver.load_local(key)
            self.assertEqual(r['status'],'unresolved');self.assertIn('Unsupported native',r['detail']);self.assertEqual(r['bindings'],{})
            self.assertIs(resolver.load_local(key),r)
            p.unlink();self.assertEqual(BlueprintResolver(resolver.project).load_local(key)['status'],'missing')

    @unittest.skipUnless(os.environ.get('UASSETAPI_ASSETS'),'Original UE4 Blueprint required')
    def test_real_blueprint_and_cooked_refusal(self):
        root=Path(os.environ['UASSETAPI_ASSETS']);p=root/'TestEditorAssets/TestActorBP.uasset'
        r=BlueprintResolver(SimpleNamespace(resolve_package=lambda _:p)).load_local(('/Game/TestActorBP','TestActorBP_C'))
        self.assertEqual(r['status'],'inspected');self.assertEqual(r['bindings']['DefaultSceneRoot']['origin'],'SCS')
        p=root/'TestJson/ABP_SMG_A.uasset';self.assertTrue(p.with_suffix('.uexp').is_file())
        r=BlueprintResolver(SimpleNamespace(resolve_package=lambda _:p)).load_local(('/Game/ABP_SMG_A','ABP_SMG_A_C'))
        self.assertEqual(r['status'],'unresolved');self.assertIn('Cooked Blueprint',r['detail'])

    def test_typed_cdo_scs_binding_and_explicit_null(self):
        def ex(name,kind,outer=0,ci=0):return ExportRecord(name,ci,0,0,outer,0,0,None,None,False,kind)
        cls=ex('BP_C','BlueprintGeneratedClass');cdo=ex('Default__BP_C','BP_C',ci=1)
        body=ex('UnrelatedName','StaticMeshComponent',2);script=ex('Script','SimpleConstructionScript',1)
        node=ex('Node','SCS_Node',4);template=ex('AnotherName','SkeletalMeshComponent',1)
        reader=BlueprintRecords.__new__(BlueprintRecords)
        names=('Character','PropMesh');imports=(ImportRecord('/Script/CoreUObject','Package',0,'/Game/Mesh','',False),ImportRecord('/Script/Engine','StaticMesh',-1,'Mesh','',False),ImportRecord('/Script/CoreUObject','Package',0,'/Game/Skeletal','',False),ImportRecord('/Script/Engine','SkeletalMesh',-3,'Skeletal','',False))
        reader.table=PackageRecords(names,imports,(cls,cdo,body,script,node,template));reader.class_index=1;reader.cls=cls;reader.cdo=(2,cdo)
        def obj(key,i):return PropertyRecord(key,'ObjectProperty',0,(),struct.pack('<i',i))
        def name(i):return PropertyRecord('InternalVariableName','NameProperty',0,(),struct.pack('<ii',i,0))
        reader.cache={cdo:{'PropMesh':obj('PropMesh',3)},body:{'StaticMesh':obj('StaticMesh',-2)},script:{'AllNodes':PropertyRecord('AllNodes','ArrayProperty',0,('ObjectProperty',),struct.pack('<ii',1,5))},node:{'ComponentTemplate':obj('ComponentTemplate',6),'InternalVariableName':name(0)},template:{'SkeletalMesh':obj('SkeletalMesh',-4)}}
        b=reader.bindings();self.assertEqual(b['PropMesh']['package'],'/Game/Mesh');self.assertEqual(b['Character']['package'],'/Game/Skeletal')
        reader.cache[body]['StaticMesh']=obj('StaticMesh',0);self.assertTrue(reader.bindings()['PropMesh']['explicit']);self.assertEqual(reader.bindings()['PropMesh']['package'],'')
        reader.cache[node]['InternalVariableName']=name(1)
        with self.assertRaisesRegex(ValueError,'Ambiguous'):reader.bindings()
