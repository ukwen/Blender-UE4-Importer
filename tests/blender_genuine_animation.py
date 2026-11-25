"""Genuine UE4.27 Mannequin animation sequences and Goblin subset playback."""
import json,os,sys,math
from pathlib import Path
import bpy,numpy as np
from mathutils import Matrix,Quaternion,Vector
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from editor_skeleton import read_editor_skeleton
from animation_native import read_animation,make_action
from skeletal_mesh_native import read_native_mesh,build_mesh
from skeleton_native import build_armature
from skeleton_blender import register,unregister
p=Path(os.environ['UE_ANIMATION_ASSETS']); bpy.ops.wm.read_factory_settings(use_empty=True)
scene=bpy.context.scene; scene.render.fps=30; scene.render.fps_base=1
sk=read_editor_skeleton(p/'UE4_Mannequin_Skeleton.uasset'); assert len(sk['bones'])==72 and len(sk['sockets'])==20
assert next(s for s in sk['sockets'] if s['name']=='SOC_hand_l')['scale']==(1.,1.,-1.)
register()
try: assert getattr(bpy.ops,'import').ue_reference_skeleton(filepath=str(p/'UE4_Mannequin_Skeleton.uasset'))=={'FINISHED'}
finally: unregister()
full=next(o for o in bpy.data.objects if o.type=='ARMATURE'); assert len(json.loads(full['UE_socket_definitions']))==20
body=read_native_mesh(p/'SK_Chr_Archer_Female_01.uasset','4.27'); obj,arm=build_mesh(body); assert len(body['bones'])==44
axis=Matrix(((0,1,0,0),(1,0,0,0),(0,0,1,0),(0,0,0,1)))
def world(bones,tracks=None,i=0):
    result=[]
    for b in bones:
        t,q,s=b['translation'],b['rotation'],b['scale']; track=(tracks or {}).get(b['name'])
        if track: t,q,s=[channel[0 if len(channel)==1 else i] if channel else fallback for channel,fallback in zip(track,(t,q,s))]
        m=axis@Matrix.LocRotScale(Vector(t)*.01,Quaternion((q[3],*q[:3])).normalized(),Vector(s))@axis
        result.append(result[b['parent']]@m if b['parent']>=0 else m)
    return result
rest=world(body['bones']); pts=np.array([v.co[:] for v in obj.data.vertices]); weights=np.zeros((len(pts),len(rest)))
for i,w in enumerate(body['weights']):
    for j,v in w.items(): weights[i,j]=v/255.
report=[]; actions=[]
for name,n in [('ThirdPersonIdle',79),('ThirdPersonWalk',30),('ThirdPersonRun',18)]:
    d=read_animation(p/(name+'.uasset')); assert d['frames']==n and len(d['tracks'])==68 and d['skeleton_package']==body['skeleton_package']
    try: make_action(arm,d,scene)
    except ValueError: pass
    else: raise AssertionError('Subset accepted without opt-in')
    fa=make_action(full,d,scene); ba=make_action(arm,d,scene,allow_subset=True); actions.append(ba)
    assert len(fa.fcurves)==720 and len(ba.fcurves)==440 and len(ba['UE_omitted_tracks'].split(','))==27
    maxbone=0.; maxskin=0.; motion=0.
    # Test every original sample for all 72 source skeleton bones and all 44 body bones.
    for i in range(n):
        time=1+d['duration']*30*i/(n-1); frame=math.floor(time); scene.frame_set(frame,subframe=time-frame); bpy.context.view_layer.update()
        for rig,source in [(full,sk['bones']),(arm,body['bones'])]:
            expected=world(source,d['tracks'],i); ref=world(source)
            for j,b in enumerate(source):
                pb=rig.pose.bones[b['name']]; want=expected[j]@ref[j].inverted()@pb.bone.matrix_local; maxbone=max(maxbone,max(abs(want[x][y]-pb.matrix[x][y]) for x in range(4) for y in range(4)))
        if i in (0,n//4,n//2,3*n//4,n-1):
            matrices=[np.array(w@r.inverted()) for w,r in zip(world(body['bones'],d['tracks'],i),rest)]; expected=sum((pts@m[:3,:3].T+m[:3,3])*weights[:,j,None] for j,m in enumerate(matrices)); ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get()); actual=np.array([v.co[:] for v in ev.data.vertices]); maxskin=max(maxskin,float(np.max(np.linalg.norm(actual-expected,axis=1)))); motion=max(motion,float(np.max(np.linalg.norm(actual-pts,axis=1))))
    assert maxbone<.0001 and maxskin<.0001 and motion>.01
    report.append(dict(clip=name,samples=n,tracks=68,duration=d['duration'],body_curves=440,full_curves=720,omitted_tracks=27,bone_matrix_error=maxbone,skin_error_m=maxskin,max_displacement_m=motion))
    print('GENUINE_ANIM_PASS',report[-1],flush=True); full.animation_data.action=None; arm.animation_data.action=None
# Keep all actions via fake users, active walk action on body; separate reference skeleton hidden for inspection.
arm.animation_data.action=actions[1]; full.hide_set(True); full.hide_render=True
scene.frame_start=1; scene.frame_end=31; scene.frame_set(1); bpy.ops.object.select_all(action='DESELECT'); arm.select_set(True); bpy.context.view_layer.objects.active=arm
out=os.environ['UE_GENUINE_ANIM_OUTPUT']; bpy.ops.wm.save_as_mainfile(filepath=out); bpy.ops.wm.open_mainfile(filepath=out)
assert len(bpy.data.actions)==6 and sum(len(a.fcurves) for a in bpy.data.actions)==3480
arm=next(o for o in bpy.data.objects if o.type=='ARMATURE' and o.animation_data and o.animation_data.action); assert arm.animation_data.action.name.startswith('ThirdPersonWalk')
bpy.context.scene.frame_set(16); bpy.context.view_layer.update(); assert len(arm.animation_data.action.fcurves)==440
Path(os.environ['UE_GENUINE_ANIM_REPORT']).write_text(json.dumps(report,indent=2)); print('GENUINE_ANIMATION_REOPEN_PASS')
