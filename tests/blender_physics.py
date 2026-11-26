import bpy,sys,os,json,pathlib,math
import numpy as np
from mathutils import Matrix
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from physics_native import read_physics,build_physics,mesh_physics_reference,joint_local
from native_sockets import socket_local
from skeletal_mesh_native import read_native_mesh,build_mesh
raw=pathlib.Path(os.environ['UE_GOBLIN_RAW']);phys=pathlib.Path(os.environ['UE_GOBLIN_PHYSICS']);out=os.environ['UE_PHYSICS_OUTPUT'];bpy.ops.wm.read_factory_settings(use_empty=True)
scene=bpy.context.scene;coll=bpy.data.collections.new('Physics assets - wire overlays');scene.collection.children.link(coll)
results=[];vehicles=[]
for i,p in enumerate(sorted(phys.glob('PHYS*.uasset'))):
 d=read_physics(p);source=raw/(d['preview_mesh'].rsplit('/',1)[-1]+'.uasset');mesh,arm=build_mesh(read_native_mesh(source,'4.27'));arm.location=(i%7*3,i//7*4,0);arm['UE_source_mesh_path']=str(source);created=build_physics(arm,d,source,coll);bpy.context.view_layer.update();assert len(created)==sum(len(b['shapes']) for b in d['bodies'])+2*len(d['joints'])
 expected=[]
 for b in d['bodies']:
  for s in b['shapes']:expected.append((b['bone'],socket_local(dict(location_cm=s['center_cm'],rotation_pyr=s['rotation_pyr'],scale=(1,1,1)))))
 for j in d['joints']:
  for b,f in zip(j['bones'],j['frames']):expected.append((b,joint_local(f)))
 def verify():
  bpy.context.view_layer.update();err=0
  for o,(bone,local) in zip(created,expected):
   b=arm.data.bones[bone];m=b['UE_world_matrix_m'];rest=Matrix([m[k:k+4] for k in range(0,16,4)]);wanted=arm.matrix_world@arm.pose.bones[bone].matrix@b.matrix_local.inverted()@rest@local;err=max(err,max(abs(o.matrix_world[a][z]-wanted[a][z]) for a in range(4) for z in range(4)))
  return err
 err=verify();positions=[o.matrix_world.translation.copy() for o in created]
 for b in arm.pose.bones:
  if b.parent:b.rotation_mode='XYZ';b.rotation_euler.x=.08
 posed=verify();motion=max((o.matrix_world.translation-v).length for o,v in zip(created,positions));assert max(err,posed)<.0001 and motion>.0001,(p.name,err,posed,motion)
 for b in arm.pose.bones:b.matrix_basis=Matrix.Identity(4)
 assert verify()<.0001
 for o in created:
  if o.get('UE_physics_kind')=='capsule':
   s=json.loads(o['UE_physics_record']);v=[x.co.z for x in o.data.vertices];assert abs((max(v)-min(v))-(s['length_cm']+2*s['radius_cm'])*.01)<1e-6 and o.hide_render
 try:build_physics(arm,d,source,coll);raise AssertionError('Duplicate accepted')
 except ValueError:pass
 results.append(dict(asset=p.name,bodies=len(d['bodies']),capsules=sum(len(b['shapes']) for b in d['bodies']),joints=len(d['joints']),rest_error=err,pose_error=posed,motion_m=motion));print('PHYSICS PASS',p.name,err,posed,motion,flush=True)
vc=bpy.data.collections.new('Vehicles - editable articulation');scene.collection.children.link(vc);cursor=0
for p in sorted(phys.glob('SK_Veh*.uasset')):
 d=read_native_mesh(p,'4.27');mesh,arm=build_mesh(d,vc);arm.location=(cursor,18,0);arm['UE_source_mesh_path']=str(p);pts=np.array([v.co[:] for v in mesh.data.vertices]);cursor+=float(np.ptp(pts[:,0]))+3
 def evalpts():
  bpy.context.view_layer.update();return np.array([v.co[:] for v in mesh.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.vertices])
 weights=np.zeros((len(pts),len(d['bones'])))
 for i,w in enumerate(d['weights']):
  for k,v in w.items():weights[i,k]=v/255
 motions=[]
 for j,b in enumerate(d['bones']):
  if not j or not np.any(weights[:,j]):continue
  bone=arm.pose.bones[b['name']];bone.rotation_mode='XYZ';bone.rotation_euler.x=.25;moved=evalpts();mats=[np.array(arm.pose.bones[x['name']].matrix@arm.data.bones[x['name']].matrix_local.inverted()) for x in d['bones']];want=sum((pts@m[:3,:3].T+m[:3,3])*weights[:,k,None] for k,m in enumerate(mats));err=float(np.max(np.linalg.norm(moved-want,axis=1)));motion=float(np.max(np.linalg.norm(moved-pts,axis=1)));assert err<1e-4 and motion>.00001,(p.name,b['name'],err,motion);bone.rotation_euler.x=0;assert np.max(abs(evalpts()-pts))<1e-5;motions.append(dict(bone=b['name'],motion_m=motion,error_m=err))
 assert motions;vehicles.append(dict(asset=p.name,bones=len(d['bones']),tested=motions,physics_package=mesh_physics_reference(p)));print('VEHICLE PASS',p.name,len(motions),flush=True)
assert len(results)==21 and sum(r['capsules'] for r in results)==283 and sum(r['joints'] for r in results)==262 and len(vehicles)==13
report=dict(physics=results,vehicles=vehicles,simulation='not implemented',missing_vehicle_physics=[r['physics_package'] for r in vehicles]);bpy.data.texts.new('UE Physics acceptance.json').write(json.dumps(report,indent=2));bpy.ops.wm.save_as_mainfile(filepath=out);bpy.ops.wm.open_mainfile(filepath=out);assert sum(o.get('UE_physics_kind')=='capsule' for o in bpy.data.objects)==283 and sum(o.get('UE_physics_kind')=='joint' for o in bpy.data.objects)==524;assert sum(o.type=='ARMATURE' for o in bpy.data.objects)==34
pathlib.Path(os.environ['UE_PHYSICS_REPORT']).write_text(json.dumps(report,indent=2));print('PHYSICS_REOPEN_PASS',len(results),len(vehicles),sum(len(r['tested']) for r in vehicles),flush=True)
