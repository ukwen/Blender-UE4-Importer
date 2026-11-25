import sys,os,traceback,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bpy,numpy as np
from editor_skeletal import read_editor_mesh
from skeletal_mesh_native import read_native_mesh,build_mesh
bpy.ops.wm.read_factory_settings(use_empty=True)
results=[]; cursor=0
for p in sorted(Path(os.environ['UE_CHARACTER_ASSETS']).glob('SK_Chr*.uasset')):
 try:
  d=read_native_mesh(p,'4.27'); obj,arm=build_mesh(d); assert len(obj.data.vertices)==len(d['positions']); pts=np.array([v.co[:] for v in obj.data.vertices]); assert np.max(abs(pts-np.array(d['positions'])[:,[1,0,2]]*.01))<1e-5
  assert len(obj.data.uv_layers)==4 and obj.data.color_attributes.get('UE_source_color')
  assert len(obj.data.attributes['UE_source_triangle_index'].data)==len(d['faces'])
  assert list(obj.data.get('UE_removed_source_triangle_indices',[]))==d['duplicate_faces']
  assert not d['duplicate_faces']
  for i,v in enumerate(obj.data.vertices):
   assert set(g.group for g in v.groups)==set(d['weights'][i]); assert all(abs(g.weight-d['weights'][i][g.group]/255)<1e-7 for g in v.groups)
  def evaluated():
   bpy.context.view_layer.update(); ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get()); return np.array([v.co[:] for v in ev.data.vertices])
  assert np.max(abs(evaluated()-pts))<1e-5
  counts={j:sum(w.get(j,0)>0 for w in d['weights']) for j in range(1,len(d['bones']))}; j=max(counts,key=counts.get); bone=arm.pose.bones[d['bones'][j]['name']]; bone.rotation_mode='XYZ'; bone.rotation_euler.x=.3; moved=evaluated(); mats=[np.array(arm.pose.bones[b['name']].matrix@arm.data.bones[b['name']].matrix_local.inverted()) for b in d['bones']]; weights=np.zeros((len(pts),len(mats)))
  for i,w in enumerate(d['weights']):
   for k,v in w.items(): weights[i,k]=v/255.
  expected=sum((pts@m[:3,:3].T+m[:3,3])*weights[:,k,None] for k,m in enumerate(mats)); err=float(np.max(np.linalg.norm(moved-expected,axis=1))); motion=float(np.max(np.linalg.norm(moved-pts,axis=1))); assert err<1e-4 and motion>.001
  bone.rotation_euler.x=0; assert np.max(abs(evaluated()-pts))<1e-5
  arm.location.x=cursor-float(pts[:,0].min()); cursor+=float(np.ptp(pts[:,0]))+1
  result=dict(asset=p.name,vertices=len(pts),triangles=len(obj.data.polygons),bones=len(d['bones']),motion=motion,error=err,tail=d['tail_bytes']); results.append(result);print('PASS',result,flush=True)
 except Exception as e: print('FAIL',p.name,repr(e),flush=True);traceback.print_exc(limit=3)
print('TOTAL',len(results),flush=True)

assert len(results)==19
if len(results)==19:
 bpy.ops.wm.save_as_mainfile(filepath=os.environ['UE_CHARACTER_OUTPUT']); bpy.ops.wm.open_mainfile(filepath=os.environ['UE_CHARACTER_OUTPUT']); assert len([o for o in bpy.data.objects if o.type=='ARMATURE'])==19
 Path(os.environ['UE_CHARACTER_REPORT']).write_text(json.dumps(results,indent=2))

