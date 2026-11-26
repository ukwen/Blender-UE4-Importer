"""Genuine editor SCS plus controlled CDO/SCS mesh associations, and real level dependencies."""
import os,sys
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uasset, blueprint_defaults as bd, static_scene

path=Path(os.environ['UE_TEST_ASSETS'])/'TestEditorAssets/TestActorBP.uasset'
with uasset.UAsset(str(path)) as a:
    binding=bd.read_bindings(a,'TestActorBP_C')['DefaultSceneRoot']
    assert all(binding[k]==v for k,v in {'class':'SceneComponent','package':'','explicit':False,'origin':'SCS','template':'DefaultSceneRoot_GEN_VARIABLE'}.items())
    assert binding['fields']=={}
print('GENUINE_SCS_PASS')
def props(**kw): return uasset.Properties({k:NS(value=v) for k,v in kw.items()})
def export(name,cls,outer=0,ci=0,**kw):
    e=uasset.Export.__new__(uasset.Export); e.object_name=name; e.export_class_type=cls; e.outer_index=outer; e.class_index=ci; e.properties=props(**kw); return e
def ref(package):
    r=uasset.Import.__new__(uasset.Import); r.object_name=package; return r
cls=export('BP_Test_C','BlueprintGeneratedClass'); cdo=export('Default__BP_Test_C','BP_Test_C',ci=1)
t=export('DifferentInternalName','StaticMeshComponent',2,StaticMesh=ref('/Game/Meshes/Rope'))
script=export('Script','SimpleConstructionScript',1); node=export('Node','SCS_Node',4)
t2=export('OtherInternalName','SkeletalMeshComponent',1,SkeletalMesh=ref('/Game/Meshes/Worm'))
cdo.properties=props(PropMesh=t); script.properties=props(AllNodes=[NS(value=node)]); node.properties=props(ComponentTemplate=t2,InternalVariableName='Character')
a=NS(exports=[cls,cdo,t,script,node,t2]); bindings=bd.read_bindings(a,'BP_Test_C',lambda e:e.properties)
assert bindings['PropMesh']['package']=='/Game/Meshes/Rope' and bindings['Character']['package']=='/Game/Meshes/Worm'
actor=export('Instance','BP_Test_C'); actor.export_class=ref('/Game/BP_Test'); c=export('NotTemplateName','StaticMeshComponent'); c2=export('NotOtherName','SkeletalMeshComponent')
actor.properties=props(PropMesh=c,Character=c2); resolver=bd.BlueprintResolver(None); resolver.cache[('/Game/BP_Test','BP_Test_C')]={'bindings':bindings}
assert resolver.component(actor,c)['origin']=='CDO' and resolver.component(actor,c2)['origin']=='SCS'
# An unbound component with matching template name must not resolve.
assert resolver.component(actor,export('DifferentInternalName','StaticMeshComponent')) is None
# Explicit null is distinct from absent property.
t.properties=props(StaticMesh=None); assert bd.read_bindings(a,'BP_Test_C',lambda e:e.properties)['PropMesh']['explicit']
node.properties=props(ComponentTemplate=t2,InternalVariableName='PropMesh')
try: bd.read_bindings(a,'BP_Test_C',lambda e:e.properties)
except ValueError: pass
else: raise AssertionError('Ambiguous bindings accepted')
print('CONTROLLED_BINDINGS_PASS')
bpy.ops.wm.read_factory_settings(use_empty=True)
root=Path(os.environ['GOBLIN_CONTENT']); collection,report=static_scene.reconstruct_static_map(str(root/'Maps/Overview.umap'),components=True)
extra=report['component_report']; deps=extra['blueprint_dependencies']
assert len(deps)==16 and all(d['status']=='missing' for d in deps)
assert extra['components']==84 and report['actor_status']=={'missing':559,'reconstructed':3}
assert all(o.get('UE_blueprint_package') for o in collection.objects if o.get('UE_blueprint_defaults_unresolved'))
print('GOBLIN_BLUEPRINT_DEPENDENCIES',len(deps))
import json
Path(os.environ['UE_BP_MANIFEST']).write_text(json.dumps({'blueprint_dependencies':deps,'missing_skeletal_packages':sorted({r['package'] for r in extra['records'] if r['status']=='missing' and r['kind']=='SkeletalMeshComponent'})},indent=2))
print('BLUEPRINT_DEFAULTS_PASS')
