"""Controlled UE4.27 editor package and actual action on genuine skinned mesh."""
import os, sys, math, struct, tempfile
from pathlib import Path
import bpy
from mathutils import Matrix, Quaternion, Vector
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import animation_native as an, skeleton_blender as sb
from skeletal_mesh_native import read_mesh,build_mesh
root=Path(os.environ['MATYA_ASSETS']); mesh=read_mesh(root/'4.27/SK_Worm.uasset','4.27')
bpy.ops.wm.read_factory_settings(use_empty=True)
obj,arm=build_mesh(mesh); bpy.context.view_layer.objects.active=arm; arm.select_set(True)
scene=bpy.context.scene; scene.render.fps=24; scene.render.fps_base=1
bones=mesh['bones']; bn=[b['name'] for b in bones]; print('BONES',bn)
# Build a complete controlled versioned editor package, not a genuine source animation.
names=['None','/Script/CoreUObject','Class','AnimSequence','/Script/Engine','Skeleton','Package','/Game/Controlled/SK_Worm_Skeleton','SK_Worm_Skeleton','ControlledRaw','NumFrames','IntProperty','SequenceLength','FloatProperty','AnimationTrackNames','ArrayProperty','NameProperty','ObjectProperty','bone_c','Trans']
fn=lambda n:struct.pack('<ii',names.index(n),0)
p=lambda f,*v:struct.pack('<'+f,*v)
fs=lambda s:p('i',len(s)+1)+s.encode()+b'\0'
def tag(key,typ,payload,inner=None): return fn(key)+fn(typ)+p('ii',len(payload),0)+(fn(inner) if inner else b'')+b'\0'+payload
def channel(fmt,values): return p('ii',struct.calcsize('<'+fmt),len(values))+b''.join(p(fmt,*x) for x in values)
def track(t,q,s): return channel('3f',t)+channel('4f',q)+channel('3f',s)
rootbone=bones[0]; child=next(b for b in bones if b['name']=='bone_c')
assert rootbone['name']=='Trans'
t0=rootbone['translation']; tq=rootbone['rotation']; ts=rootbone['scale']; ct=child['translation']; cq=child['rotation']; cs=child['scale']
# Root motion is ordinary bone translation, not extracted Unreal root motion.
rot=Quaternion((cq[3],*cq[:3])); qnew=rot@Quaternion((1,0,0),.45); q2=(*qnew[1:],qnew[0]); qneg=tuple(-x for x in q2)
t1=(t0[0]+15,t0[1],t0[2]); rt=[t0,t1,t0]; cqkeys=[cq,qneg,cq]
raw=tag('NumFrames','IntProperty',p('i',3))+tag('SequenceLength','FloatProperty',p('f',1))+tag('AnimationTrackNames','ArrayProperty',p('i',2)+fn('Trans')+fn('bone_c'),'NameProperty')+tag('Skeleton','ObjectProperty',p('i',-2))+fn('None')+p('iBBi',0,0,0,2)+track(rt,[tq],[ts])+track([ct],cqkeys,[])+p('ii',0,0)
# Header fields correspond to the legacy UE4.27 reader and package inspector.
nt=b''.join(fs(n)+p('I',0) for n in names)
imports=b''.join(fn(cp)+fn(c)+p('i',outer)+fn(n)+fn('None') for cp,c,outer,n in [('/Script/CoreUObject','Class',0,'AnimSequence'),('/Script/Engine','Skeleton',-3,'SK_Worm_Skeleton'),('/Script/CoreUObject','Package',0,'/Game/Controlled/SK_Worm_Skeleton')])
def summary(h,no,io,eo):
    ev=p('HHHI',4,27,2,0)+fs('')
    return p('I5i',0x9e2a83c1,-7,0,522,0,0)+p('i',h)+fs('None')+p('Iii',0,len(names),no)+fs('')+p('iiiiii',0,0,1,eo,3,io)+p('iiii',0,0,0,0)+p('i',0)+bytes(32)+p('i',0)+ev+ev+p('IIIIi',0,0,0,0,0)+p('qiii',0,0,0,0)+p('i',0)
# Use offsets calculated from the same bounded fields, no scanning.
no=len(summary(0,0,0,0)); io=no+len(nt); eo=io+len(imports)
def export(h): return p('iiii',-1,0,0,0)+fn('ControlledRaw')+p('Iqq',0,len(raw),h)+bytes(12+16+4+4+4+20)
h=eo+len(export(0)); package=summary(h,no,io,eo)+nt+imports+export(h)+raw
assert len(package)==h+len(raw)
with tempfile.TemporaryDirectory() as tmp:
    path=Path(tmp)/'ControlledRaw.uasset'; path.write_bytes(package)
    d=an.read_animation(path); assert d['frames']==3 and d['duration']==1 and list(d['tracks'])==['Trans','bone_c']
    assert d['skeleton_package']=='/Game/Controlled/SK_Worm_Skeleton'
    sb.register()
    try: assert getattr(bpy.ops,'import').ue_raw_animation(filepath=str(path))=={'FINISHED'}
    finally: sb.unregister()
    # Refuse a second action rather than overwrite the first.
    action=arm.animation_data.action; assert len(action.fcurves)==60 and tuple(action.frame_range)==(1.,25.)
    try: an.make_action(arm,d,scene)
    except ValueError: pass
    else: raise AssertionError('Existing animation overwritten')
    assert arm.animation_data.action==action
    # Independently construct original world transforms and compare skinning with evaluated Blender.
    axis=Matrix(((0,1,0,0),(1,0,0,0),(0,0,1,0),(0,0,0,1)))
    def local(t,q,s): return axis@Matrix.LocRotScale(Vector(t)*.01,Quaternion((q[3],*q[:3])),Vector(s))@axis
    def world(i):
        result=[]
        for b in bones:
            t,q,s=b['translation'],b['rotation'],b['scale']
            if b['name']=='Trans': t=rt[i]
            if b['name']=='bone_c': q=cqkeys[i]
            m=local(t,q,s); result.append(result[b['parent']]@m if b['parent']>=0 else m)
        return result
    rest=world(0); points=[v.co.copy() for v in obj.data.vertices]; maximum=0; displacement=0
    for i,frame in enumerate((1,13,25)):
        scene.frame_set(frame); bpy.context.view_layer.update(); matrices=[m@r.inverted() for m,r in zip(world(i),rest)]
        expected=[sum((matrices[j]@v*(w/255) for j,w in weights.items()),Vector((0,0,0))) for v,weights in zip(points,mesh['weights'])]
        ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get()); actual=[v.co.copy() for v in ev.data.vertices]
        error=max((a-b).length for a,b in zip(actual,expected)); maximum=max(error,maximum); displacement=max(displacement,max((a-b).length for a,b in zip(actual,points)))
        print('FRAME',frame,'ERROR',error); assert error<1e-5
    assert displacement>.1
    for broken in (raw[:-1],raw.replace(p('iBBi',0,0,0,2),p('iBBi',0,1,0,2),1)):
        try: an.read_export(broken,names,'Broken')
        except ValueError: pass
        else: raise AssertionError('Malformed raw animation accepted')
    out=os.environ['UE_ANIMATION_OUTPUT']; scene.frame_set(1); bpy.ops.wm.save_as_mainfile(filepath=out)
    bpy.ops.wm.open_mainfile(filepath=out); arm=next(o for o in bpy.data.objects if o.type=='ARMATURE'); assert len(arm.animation_data.action.fcurves)==60
    bpy.context.scene.frame_set(13); bpy.context.view_layer.update()
    obj=next(o for o in bpy.data.objects if o.type=='MESH'); ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get()); assert max((v.co-p).length for v,p in zip(ev.data.vertices,points))>.1
    print('RAW_ACTION_PASS',maximum,displacement,len(arm.animation_data.action.fcurves))
