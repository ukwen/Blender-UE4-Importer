"""Bounded UE4 cooked USkeleton reader and editable Blender reference armature.

Explicit tagged cooked 4.18/4.27 split-package profiles only. No offset scan.
The native reference skeleton is names/parents, FTransform array, name-index map.
"""
import math
import struct
from pathlib import Path

MAGIC=b'\xc1\x83\x2a\x9e'

class Reader:
    def __init__(self,data,pos=0): self.data,self.pos=data,pos
    def take(self,n):
        if n<0 or self.pos+n>len(self.data): raise ValueError('Truncated skeleton data')
        p=self.pos; self.pos+=n; return self.data[p:self.pos]
    def unpack(self,fmt): return struct.unpack('<'+fmt,self.take(struct.calcsize('<'+fmt)))
    def i(self): return self.unpack('i')[0]
    def count(self,limit):
        n=self.i()
        if not 0<=n<=limit: raise ValueError('Invalid skeleton count')
        return n
    def string(self):
        n=self.i()
        if not 0<n<=4096: raise ValueError('Unsupported skeleton name encoding')
        b=self.take(n)
        if b[-1:]!=b'\0': raise ValueError('Unterminated name')
        return b[:-1].decode('utf8')
    def name(self,names):
        idx,num=self.unpack('ii')
        if not 0<=idx<len(names) or not 0<=num<=1000000: raise ValueError('Invalid FName')
        return names[idx]+('_'+str(num-1) if num else '')


def reference_skeleton(r,names,precision="f"):
    n=r.count(8192)
    if not n: raise ValueError('Empty skeleton')
    bones=[]; seen=set()
    for i in range(n):
        name,parent=r.name(names),r.i()
        if not name or len(name.encode('utf8'))>63 or name.casefold() in seen or parent not in ([-1] if i==0 else range(i)):
            raise ValueError('Invalid bone name or hierarchy')
        seen.add(name.casefold()); bones.append({'name':name,'parent':parent})
    if r.i()!=n: raise ValueError('Reference pose count mismatch')
    for bone in bones:
        q,t,s=r.unpack('4'+precision),r.unpack('3'+precision),r.unpack('3'+precision)
        if not all(math.isfinite(x) for x in q+t+s) or abs(sum(x*x for x in q)-1)>0.001 or min(s)<=0:
            raise ValueError('Unsupported reference transform')
        bone.update(rotation=q,translation=t,scale=s)
    if r.i()!=n: raise ValueError('Bone name map count mismatch')
    seen=set()
    for _ in range(n):
        name,i=r.name(names),r.i()
        if not 0<=i<n or i in seen or name!=bones[i]['name']: raise ValueError('Bone name map mismatch')
        seen.add(i)
    return bones


def read_cooked_skeleton(path,version):
    if version=="5.0":
        from ue5_cooked_geometry import read_skeleton50
        return read_skeleton50(path)
    if version not in ('4.18','4.27'): raise NotImplementedError('Unsupported skeleton profile')
    path=Path(path); side=path.with_suffix('.uexp')
    if path.stat().st_size>16*1024*1024 or side.stat().st_size>64*1024*1024: raise ValueError('Skeleton size limit')
    header=path.read_bytes(); data=side.read_bytes(); r=Reader(header)
    if r.take(4)!=MAGIC or r.unpack('5i')!=(-7,0,0,0,0): raise ValueError('Expected unversioned header without custom version records')
    if r.i()!=len(header) or r.string()!='None': raise ValueError('Unsupported split package header')
    flags=r.unpack('I')[0]
    if not flags&0x80000000 or flags&0x2000: raise ValueError('Expected editor-filtered tagged properties')
    n,no=r.unpack('ii'); gc,go=r.unpack('ii'); ec,eo=r.unpack('ii'); ic,io=r.unpack('ii')
    if not (0<n<=100000 and gc==go==0 and ec==1 and 0<ic<=100000 and r.pos<=no<io<eo<len(header) and io+28*ic==eo):
        raise ValueError('Unsupported skeleton package tables')
    r.pos=no; names=[]
    for _ in range(n): names.append(r.string()); r.take(4)
    if r.pos!=io: raise ValueError('Name table boundary mismatch')
    imports=[]
    for _ in range(ic): imports.append((r.name(names),r.name(names),r.i(),r.name(names)))
    ci,si,ti,outer=r.unpack('4i'); name=r.name(names); r.take(4); size,offset=r.unpack('qq')
    if not -ic<=ci<0 or outer or imports[-ci-1][:2]!=('/Script/CoreUObject','Class') or imports[-ci-1][3]!='Skeleton':
        raise ValueError('Not a root USkeleton export')
    if offset!=len(header) or size!=len(data)-4 or data[-4:]!=MAGIC: raise ValueError('Invalid skeleton sidecar extent')
    r=Reader(data[:-4]); seen=set()
    # Skip only the bounded known tagged array property layout of this profile.
    while True:
        key=r.name(names)
        if key=='None': break
        if key in seen or key!='BoneTree' or r.name(names)!='ArrayProperty': raise ValueError('Unsupported skeleton property layout: '+key)
        seen.add(key); size,index=r.unpack('ii')
        if index or r.name(names)!='StructProperty' or r.take(1)!=b'\0': raise ValueError('Unsupported BoneTree tag')
        r.take(size)
    if r.i()!=0: raise ValueError('Unsupported object GUID flag')
    bones=reference_skeleton(r,names)
    return name,bones


def build_armature(name,bones,collection=None):
    import bpy
    from mathutils import Matrix,Quaternion,Vector
    if bpy.context.mode!='OBJECT': raise ValueError('Import skeleton in Object mode')
    # Reflect the coordinate basis by swapping X/Y, and convert cm to m.
    axis=Matrix(((0,1,0,0),(1,0,0,0),(0,0,1,0),(0,0,0,1)))
    worlds=[]; rests=[]
    for bone in bones:
        x,y,z,w=bone['rotation']; q=Quaternion((w,x,y,z)).normalized()
        local=Matrix.LocRotScale(Vector(bone['translation'])*.01,q,Vector(bone['scale']))
        local=axis@local@axis
        world=worlds[bone['parent']]@local if bone['parent']>=0 else local
        worlds.append(world)
        # Blender bone rest transforms are rigid; keep original local scale and
        # full accumulated matrix as metadata, not silently discard scaling.
        rot=world.to_3x3().normalized()
        if any(abs(rot.col[i].dot(rot.col[j]))>0.0001 for i in range(3) for j in range(i)):
            raise ValueError('Sheared reference skeleton unsupported')
        rest=rot.to_4x4(); rest.translation=world.translation; rests.append(rest)
    arm=bpy.data.armatures.new(name); obj=bpy.data.objects.new(name,arm)
    (collection or bpy.context.collection).objects.link(obj)
    prev=bpy.context.view_layer.objects.active
    try:
        bpy.context.view_layer.objects.active=obj; obj.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')
        for i,bone in enumerate(bones):
            b=arm.edit_bones.new(bone['name']); b.head=(0,0,0); b.tail=(0,.1,0)
            if bone['parent']>=0: b.parent=arm.edit_bones[bones[bone['parent']]['name']]
            b.matrix=rests[i]; b.use_connect=False
            distances=[(rests[j].translation-rests[i].translation).length for j,child in enumerate(bones) if child['parent']==i]
            b.length=max(.01,min(1.,next((x for x in distances if x>1e-5),.1)))
        bpy.ops.object.mode_set(mode='OBJECT')
        for i,rec in enumerate(bones):
            b=arm.bones[rec['name']]; b['UE_bone_index']=i; b['UE_local_rotation_xyzw']=rec['rotation']; b['UE_local_translation_cm']=rec['translation']; b['UE_local_scale']=rec['scale']; b['UE_world_matrix_m']=[v for row in worlds[i] for v in row]
        obj['UE_skeleton_status']='reference_pose_only'; obj.show_in_front=True
        return obj
    except Exception:
        if bpy.context.mode=='EDIT_ARMATURE': bpy.ops.object.mode_set(mode='OBJECT')
        bpy.data.objects.remove(obj,do_unlink=True); bpy.data.armatures.remove(arm)
        raise
    finally:
        bpy.context.view_layer.objects.active=prev
