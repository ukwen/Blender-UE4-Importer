"""Original Blueprint parity and conservative typed-reference checks."""
import hashlib
import importlib.abc
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import unittest
from types import SimpleNamespace
from classic_blueprint import BlueprintRecords
from ue4_property_records import PropertyRecord


class BlueprintMigrationTests(unittest.TestCase):
    def test_bad_transform_and_reference(self):
        reader = BlueprintRecords.__new__(BlueprintRecords)
        reader.table = SimpleNamespace(reference=lambda i: (_ for _ in ()).throw(ValueError('Invalid reference')) if i != 0 else None)
        for p in (PropertyRecord('Mesh','NameProperty',0,(),bytes(4)), PropertyRecord('Mesh','ObjectProperty',0,(),bytes(3)),PropertyRecord('Mesh','ObjectProperty',0,(),struct.pack('<i',1))):
            with self.assertRaises(ValueError):reader.object_index({'Mesh':p},'Mesh')
        bad=PropertyRecord('RelativeLocation','StructProperty',0,('Vector',),struct.pack('<3f',float('inf'),0,0))
        with self.assertRaises(ValueError):reader.fields({'RelativeLocation':bad})
        absolute=PropertyRecord('bAbsoluteLocation','BoolProperty',0,(),b'',True)
        with self.assertRaises(ValueError):reader.fields({'bAbsoluteLocation':absolute})

    @unittest.skipUnless(os.environ.get('UASSETAPI_ASSETS'),'Original UE4 SCS fixture required')
    def test_original_scs_and_mismatch(self):
        p=Path(os.environ['UASSETAPI_ASSETS'])/'TestEditorAssets/TestActorBP.uasset'
        reader=BlueprintRecords(p,'TestActorBP_C')
        self.assertEqual(reader.parent(),('/Script/Engine','Actor'))
        self.assertEqual(reader.bindings(),{'DefaultSceneRoot':dict(fields={},**{'class':'SceneComponent'},package='',explicit=False,origin='SCS',template='DefaultSceneRoot_GEN_VARIABLE',socket='None',parent='None')})
        with self.assertRaises(ValueError):BlueprintRecords(p,'Wrong_C')
        with self.assertRaises(ValueError):reader.body_template()

    @unittest.skipUnless(os.environ.get('UE_BLUEPRINT_FIXTURES') and os.environ.get('UASSETAPI_ASSETS'),'Original mixed Blueprint fixtures required')
    def test_exact_original_corpus_without_inherited_imports(self):
        # Isolate import state; a late import from any of the inherited modules fails.
        code = '''
import importlib.abc,sys,json,os
from pathlib import Path
from types import SimpleNamespace
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname in {'uasset','umesh','umat','umap','bpy','material_stage'}:raise ImportError('Forbidden '+fullname)
sys.meta_path.insert(0,Block())
from blueprint_defaults import BlueprintResolver
from blueprint_placement import template
from package_inspector import inspect_package
paths=list(Path(os.environ['UE_BLUEPRINT_FIXTURES']).glob('*.uasset'))+[Path(os.environ['UASSETAPI_ASSETS'])/'TestEditorAssets/TestActorBP.uasset']
result={}
for p in sorted(paths):
 key=('/Game/'+p.stem,p.stem+'_C'); r=BlueprintResolver(SimpleNamespace(resolve_package=lambda _:str(p))).load_local(key)
 assert r['status']=='inspected',r
 result[p.stem]={'binding':r}
 if inspect_package(p)['ue5'] is None and p.stem!='TestActorBP':result[p.stem]['template']=template(p,key[1])
print(json.dumps(result,sort_keys=True,separators=(',',':')))
'''
        root=Path(__file__).resolve().parents[1]
        manifest=json.loads((root/'docs/GOBLIN_FIXTURE.json').read_text())['assets']
        for p in Path(os.environ['UE_BLUEPRINT_FIXTURES']).glob('*.uasset'):
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),manifest[p.name]['sha256'])
        raw=subprocess.check_output([sys.executable,'-c',code],cwd=root,text=True).strip()
        result=json.loads(raw)
        self.assertEqual(len(result),17)
        self.assertEqual(hashlib.sha256(raw.encode()).hexdigest(),'d6225d84cc4b39e4eebd07fb134cd178326607ed8362e4d0be124ef848106c9e')
