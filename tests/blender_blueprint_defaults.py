"""Genuine typed editor SCS and real level dependencies; controlled tests are in test_native_blueprint_boundary.py."""
import os,sys
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import static_scene
from classic_blueprint import BlueprintRecords

path=Path(os.environ['UE_TEST_ASSETS'])/'TestEditorAssets/TestActorBP.uasset'
binding=BlueprintRecords(path,'TestActorBP_C').bindings()['DefaultSceneRoot']
assert all(binding[k]==v for k,v in {'class':'SceneComponent','package':'','explicit':False,'origin':'SCS','template':'DefaultSceneRoot_GEN_VARIABLE'}.items())
assert binding['fields']=={}
print('GENUINE_SCS_PASS')
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
