import bpy,sys,pathlib,math,json,os
from mathutils import Vector
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from legacy_skeletal import read_legacy_skeletal
from skeletal_mesh_native import build_mesh
root=pathlib.Path(os.environ['UE_WESTERN_PROJECT'])
bpy.ops.wm.read_factory_settings(use_empty=True);results=[]; max_rest=0.; max_weight=0.; total=0
for p in sorted(root.rglob('SK_*.uasset')):
 if p.stem.endswith(('_PhysicsAsset','_Skeleton')):continue
 d=read_legacy_skeletal(p); o,a=build_mesh(d); bpy.context.view_layer.update(); assert len(o.data.vertices)==len(d['positions']) and len(o.data.polygons)==len(d['faces']); assert len(a.data.bones)==len(d['bones'])
 # Validate imported bone and skin data with explicit source records.
 for v, weights in zip(o.data.vertices,d['weights']):
  actual={g.group:g.weight for g in v.groups};assert set(actual)==set(weights)
  max_weight=max(max_weight,max(abs(actual[j]-w/255) for j,w in weights.items()))
  x,y,z=d['positions'][v.index];max_rest=max(max_rest,(v.co-Vector((y*.01,x*.01,z*.01))).length)
 dg=bpy.context.evaluated_depsgraph_get(); ev=o.evaluated_get(dg); before=[v.co.copy() for v in ev.data.vertices]
 # Pose a weighted bone, then reset. Translation chosen to guarantee movement.
 j=max(range(len(d['bones'])),key=lambda j:sum(weights.get(j,0) for weights in d['weights'])); pb=a.pose.bones[d['bones'][j]['name']];pb.location.x+=.05;bpy.context.view_layer.update();ev=o.evaluated_get(bpy.context.evaluated_depsgraph_get());move=max((v.co-co).length for v,co in zip(ev.data.vertices,before));assert move>.001
 pb.location.x-=.05;bpy.context.view_layer.update();ev=o.evaluated_get(bpy.context.evaluated_depsgraph_get());recovery=max((v.co-co).length for v,co in zip(ev.data.vertices,before));assert recovery<1e-5
 results.append(dict(asset=p.name,vertices=len(o.data.vertices),faces=len(o.data.polygons),bones=len(a.data.bones),movement_m=move,recovery_m=recovery));print('DEFORM_PASS',p.name,move,recovery,flush=True)
 bpy.data.objects.remove(o,do_unlink=True);bpy.data.objects.remove(a,do_unlink=True)
assert len(results)==31;assert max_weight<1e-7 and max_rest<1e-5
pathlib.Path(os.environ['UE_SKELETAL_REPORT']).write_text(json.dumps(dict(assets=results,max_weight_error=max_weight,max_vertex_error_m=max_rest),indent=2));print('SKELETAL_ACCEPTANCE_PASS',len(results),max_weight,max_rest)
