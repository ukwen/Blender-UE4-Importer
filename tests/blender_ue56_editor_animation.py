"""Original UE5.6 editor FK source samples applied to native textured rigs."""
import os,sys,json,math
from pathlib import Path
import bpy,numpy as np
from mathutils import Matrix,Vector,Quaternion
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from animation_native import read_animation,make_action
from ue5_blueprint import read_tables
from ue5_editor_tags import export_tags,read_tag_stream
from skeleton_native import Reader
root=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content';out=Path(os.environ['UE56_ANIM_OUTPUT']);bpy.ops.wm.open_mainfile(filepath=os.environ['UE56_ANIM_INPUT']);scene=bpy.context.scene;scene.render.fps=30;scene.render.fps_base=1
rigs=[o for o in bpy.data.objects if o.type=='ARMATURE'];assert len(rigs)==2
axis=Matrix(((0,1,0,0),(1,0,0,0),(0,0,1,0),(0,0,0,1)))
# Independent direct byte reads and Euler matrices, rather than the importer quaternion calculation.
def raw_euler(p,n):
    m,b,im,ex,ref,pkg=read_tables(p);e=next(e for e in ex if e['kind']=='MovieSceneControlRigParameterSection');v=export_tags(b,e,m['names'])['TransformParameterNamesAndCurves'];r=Reader(v['data']);result={}
    import struct
    for _ in range(r.i()):
        tags=read_tag_stream(r,m['names'],indexed=True);name=Reader(tags['ParameterName']['data']).name(m['names'])[:-8];ch=[]
        for k in ('Translation','Rotation','Scale'):
            for j in range(3):
                data=tags[k if j==0 else (k,j)]['data'];count=struct.unpack_from('<i',data,6)[0];ch.append([struct.unpack_from('<f',data,18+4*count+28*i)[0] for i in range(count)] if count else [struct.unpack_from('<f',data,len(data)-20)[0]]*n)
        result[name]=ch
    return result

def worlds(bones,ch,i):
    result=[]
    for b in bones:
        if b.name in ch:
            v=[c[i] for c in ch[b.name]];rx,ry,rz=map(math.radians,v[3:6]);m=axis@Matrix.Translation(Vector(v[:3])*.01)@Matrix.Rotation(rz,4,'Z')@Matrix.Rotation(-ry,4,'Y')@Matrix.Rotation(-rx,4,'X')@Matrix.Diagonal((*v[6:],1.))@axis
        else:
            q=b['UE_local_rotation_xyzw'];m=axis@Matrix.LocRotScale(Vector(b['UE_local_translation_cm'])*.01,Quaternion((q[3],*q[:3])),Vector(b['UE_local_scale']))@axis
        result.append(result[b.parent.get('UE_bone_index')]@m if b.parent else m)
    return result
report=[];actions={}
for clip in ('MM_Idle','MM_Rifle_Equip','MF_Rifle_Walk_Fwd_Left'):
    p=next(root.rglob(clip+'.uasset'));d=read_animation(p);n=d['frames'];ch=raw_euler(p,n); assert len(ch)==89
    for rig in rigs:
        if rig.animation_data:rig.animation_data.action=None
        if set(d['tracks'])!=set(b.name for b in rig.data.bones):
            try:make_action(rig,d,scene)
            except ValueError:pass
            else:raise AssertionError('Subset accepted without opt-in')
        a=make_action(rig,d,scene,allow_subset=True);actions[(rig.name,clip)]=a;assert len(a.fcurves)==890 and a['UE_source_fps']==30
        bones=sorted(rig.data.bones,key=lambda b:b['UE_bone_index']);rest=[Matrix([b['UE_world_matrix_m'][j:j+4] for j in range(0,16,4)]) for b in bones];obj=next(o for o in bpy.data.objects if o.type=='MESH' and any(m.type=='ARMATURE' and m.object==rig for m in o.modifiers));pts=np.array([v.co[:] for v in obj.data.vertices]);weights=np.zeros((len(pts),89));index={b.name:i for i,b in enumerate(bones)}
        for v in obj.data.vertices:
            for g in v.groups:
                name=obj.vertex_groups[g.group].name
                if name in index:weights[v.index,index[name]]=g.weight
        maxbone=maxskin=motion=0.
        for i in sorted(set([0,n//4,n//2,3*n//4,n-1])):
            scene.frame_set(i+1);bpy.context.view_layer.update();w=worlds(bones,ch,i)
            for j,b in enumerate(bones):
                want=w[j]@rest[j].inverted()@b.matrix_local;pb=rig.pose.bones[b.name];maxbone=max(maxbone,max(abs(want[x][y]-pb.matrix[x][y]) for x in range(4) for y in range(4)))
            matrices=[np.array(x@y.inverted()) for x,y in zip(w,rest)];expected=sum((pts@m[:3,:3].T+m[:3,3])*weights[:,j,None] for j,m in enumerate(matrices));ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());actual=np.array([v.co[:] for v in ev.data.vertices]);maxskin=max(maxskin,float(np.max(np.linalg.norm(actual-expected,axis=1))));motion=max(motion,float(np.max(np.linalg.norm(actual-pts,axis=1))))
        assert maxbone<.0001 and maxskin<.0001 and motion>.01,(maxbone,maxskin,motion)
        row=dict(clip=clip,rig=rig.name,frames=n,vertices=len(pts),bone_error=maxbone,skin_error_m=maxskin,max_displacement_m=motion,root_motion=d['source_root_motion']);report.append(row);print('EDITOR_ANIMATION_PASS',row,flush=True)
        rig.animation_data.action=None
for rig in rigs:rig.animation_data.action=actions[rig.name,'MF_Rifle_Walk_Fwd_Left']
scene.frame_start=1;scene.frame_end=47;scene.frame_set(24);bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out));assert sum(1 for a in bpy.data.actions if a.get('UE_source_fps')==30)==6;assert all(r.animation_data.action and r.animation_data.action.name.startswith('MF_Rifle_Walk_Fwd_Left') for r in bpy.data.objects if r.type=='ARMATURE');out.with_suffix('.json').write_text(json.dumps(report,indent=2));print('EDITOR_ANIMATION_REOPEN_PASS',flush=True)
