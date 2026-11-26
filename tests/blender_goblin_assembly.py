"""Real mixed-version Blueprint assembly and source animation acceptance.
Stage original packages by their original /Game paths. Missing geometry remains missing.
"""
import bpy,sys,json,pathlib,collections,os,math
import numpy as np
from mathutils import Matrix, Vector, Quaternion
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from static_scene import reconstruct_static_map
from animation_native import read_animation,make_action
from native_sockets import socket_local
bpy.ops.wm.read_factory_settings(use_empty=True)
scene=bpy.context.scene;scene.render.fps=30;scene.render.fps_base=1
c,r=reconstruct_static_map(os.environ['UE_GOBLIN_MAP'],materials=True,allow_partial_materials=True,components=True)
recs=r['component_report']['records']; bodies=[x for x in recs if x['reference_origin']=='CDO']; acc=[x for x in recs if x['reference_origin']=='SCS']; assert len(bodies)==15 and all(x['status']=='reconstructed' and x['sockets']['created']==20 for x in bodies)
assert len(acc)==37 and all(x.get('accessory_placement') for x in acc)
assert sum(x['status']=='reconstructed' for x in acc)==3
assert collections.Counter(x['status'] for x in acc)=={'reconstructed':3,'missing':34}
assert not r['material_report']['errors']
anchors={(o['UE_component_actor'],o['UE_component']):o for o in c.objects if o.get('UE_component_anchor')}
rigs={x['actor']:next(o for o in anchors[x['actor'],x['component']].children if o.type=='ARMATURE') for x in bodies}
hoods=[o for o in c.objects if o.get('UE_master_pose_component')];assert len(hoods)==2
for h in hoods:assert h.parent==h.modifiers[0].object and h.parent.name==h['UE_master_pose_component']
for rec in acc:
 o=anchors[rec['actor'],rec['component']]; assert not o['UE_blueprint_defaults_unresolved']
 if rec['socket']:assert o.parent.get('UE_socket_name')==rec['socket']
 assert o.get('UE_accessory_placement')=='serialized_template_map'
axis=Matrix(((0,1,0,0),(1,0,0,0),(0,0,1,0),(0,0,0,1)))
clips=[read_animation(pathlib.Path(os.environ['UE_GOBLIN_RAW'])/(n+'.uasset')) for n in ('ThirdPersonIdle','ThirdPersonWalk','ThirdPersonRun')]
report=[]; active={}
for actor,rig in rigs.items():
 bones=sorted(rig.data.bones,key=lambda b:b['UE_bone_index']); parents=[b.parent['UE_bone_index'] if b.parent else -1 for b in bones]
 mesh=next(o for o in rig.children if o.type=='MESH' and not o.get('UE_master_pose_component'))
 related=[mesh]+[h for h in hoods if h.parent==rig]
 def evaluated(o):return np.array([v.co[:] for v in o.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.vertices])
 restpts={o.name:np.array([v.co[:] for v in o.data.vertices]) for o in related}
 for d in clips:
  action=make_action(rig,d,scene,allow_subset=True); action.name=actor+' / '+d['name'];action['UE_target_actor']=actor
  maxbone=maxsocket=0.;motion={o.name:0. for o in related}
  for i in sorted(set([0,d['frames']//2,d['frames']-1])):
   t=1+d['duration']*30*i/(d['frames']-1); scene.frame_set(math.floor(t),subframe=t%1);bpy.context.view_layer.update();world=[]
   for j,b in enumerate(bones):
    defaults=(b['UE_local_translation_cm'],b['UE_local_rotation_xyzw'],b['UE_local_scale']);track=d['tracks'].get(b.name)
    loc,q,s=[channel[0 if len(channel)==1 else i] if channel else default for channel,default in zip(track,defaults)] if track else defaults
    local=axis@Matrix.LocRotScale(Vector(loc)*.01,Quaternion((q[3],*q[:3])).normalized(),Vector(s))@axis
    w=world[parents[j]]@local if parents[j]>=0 else local;world.append(w);m=b['UE_world_matrix_m'];rest=Matrix([m[k:k+4] for k in range(0,16,4)]);expected=w@rest.inverted()@b.matrix_local
    maxbone=max(maxbone,max(abs(expected[x][y]-rig.pose.bones[b.name].matrix[x][y]) for x in range(4) for y in range(4)))
   for so in rig.children:
    if not so.get('UE_socket_name'):continue
    sr=json.loads(so['UE_socket_definition']);b=rig.data.bones[sr['bone']]; want=rig.matrix_world@world[b['UE_bone_index']]@socket_local(sr)
    maxsocket=max(maxsocket,max(abs(so.matrix_world[x][y]-want[x][y]) for x in range(4) for y in range(4)))
   for o in related: motion[o.name]=max(motion[o.name],float(np.max(np.linalg.norm(evaluated(o)-restpts[o.name],axis=1))))
  assert maxbone<.0001 and maxsocket<.0002 and min(motion.values())>.001,(actor,d['name'],maxbone,maxsocket,motion)
  report.append(dict(actor=actor,clip=d['name'],frames=d['frames'],bone_error=maxbone,socket_error=maxsocket,motion=motion,curves=len(action.fcurves)))
  if d['name']=='ThirdPersonWalk':active[actor]=action
  rig.animation_data.action=None
  for b in rig.pose.bones:b.matrix_basis=Matrix.Identity(4)
 print('ANIMATED',actor,flush=True)
for actor,rig in rigs.items():rig.animation_data.action=active[actor]
scene.frame_start=1;scene.frame_end=31;scene.frame_set(1);bpy.context.view_layer.update()
r['assembly_animation_acceptance']=report
bpy.data.texts[c['UE_report']].clear();bpy.data.texts[c['UE_report']].write(json.dumps(r,indent=2))
out=os.environ['UE_GOBLIN_OUTPUT'];bpy.ops.wm.save_as_mainfile(filepath=out);bpy.ops.wm.open_mainfile(filepath=out)
assert len(bpy.data.actions)==45 and sum(bool(o.get('UE_master_pose_component')) for o in bpy.data.objects)==2
assert len([o for o in bpy.data.objects if o.type=='ARMATURE' and o.animation_data and o.animation_data.action])==15
assert sum(bool(o.get('UE_accessory_placement')) for o in bpy.data.objects)==37
assert sum(bool(o.get('UE_socket_name')) for o in bpy.data.objects)==300
bpy.context.scene.frame_set(16);bpy.context.view_layer.update()
pathlib.Path(os.environ['UE_GOBLIN_REPORT']).write_text(json.dumps(r,indent=2));print('GOBLIN_ASSEMBLY_REOPEN_PASS',len(report),max(x['bone_error'] for x in report),max(x['socket_error'] for x in report),flush=True)
