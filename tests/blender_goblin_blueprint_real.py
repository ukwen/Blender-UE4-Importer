"""Acceptance for the 15 supplied mixed-version character Blueprint packages."""
import json,os,sys
from collections import Counter
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import static_scene

bpy.ops.wm.read_factory_settings(use_empty=True)
root=Path(os.environ['GOBLIN_BLUEPRINT_CONTENT'])
collection,report=static_scene.reconstruct_static_map(str(root/'Maps/Overview.umap'),components=True)
extra=report['component_report']; deps=extra['blueprint_dependencies']
assert Counter(d['status'] for d in deps)=={'inspected':15,'missing':1}
assert Counter(d.get('ue5','UE4') for d in deps if d['status']=='inspected')=={1012:11,'UE4':4}
records=[r for r in extra['records'] if r['reference_origin'] in ('CDO','SCS')]
assert len(records)==52 and Counter(r['kind'] for r in records)=={'StaticMeshComponent':35,'SkeletalMeshComponent':17}
assert Counter(r['reference_origin'] for r in records)=={'CDO':15,'SCS':37}
assert len({r['package'] for r in records})==48
assert sum(bool(r['socket']) for r in records)==34
assert any(r['component']=='SK_Chr_Attach_Hood_02' and r['package'].endswith('/SK_Chr_Attach_Hood_03') for r in records)
assert extra['components']==84 and report['actor_status']=={'missing':559,'reconstructed':3}
assert len(collection.objects)==646 and not any(o.get('UE_component_status')=='reconstructed' for o in collection.objects)
assert all(d['parent_blueprint'].endswith('/ThirdPersonCharacter') for d in deps if d.get('ue5'))
out=os.environ['UE_BP_REAL_OUTPUT']; bpy.ops.wm.save_as_mainfile(filepath=out); bpy.ops.wm.open_mainfile(filepath=out)
collection=next(c for c in bpy.data.collections if c.get('UE_report'))
assert json.loads(bpy.data.texts[collection['UE_report']].as_string())==report
print('GENUINE_MIXED_BLUEPRINT_PASS',len(records))
