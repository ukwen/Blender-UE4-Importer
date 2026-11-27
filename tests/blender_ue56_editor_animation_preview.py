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
        if b.name.casefold() in ch:
            v=[c[i] for c in ch[b.name.casefold()]];rx,ry,rz=map(math.radians,v[3:6]);m=axis@Matrix.Translation(Vector(v[:3])*.01)@Matrix.Rotation(rz,4,'Z')@Matrix.Rotation(-ry,4,'Y')@Matrix.Rotation(-rx,4,'X')@Matrix.Diagonal((*v[6:],1.))@axis
        else:
            q=b['UE_local_rotation_xyzw'];m=axis@Matrix.LocRotScale(Vector(b['UE_local_translation_cm'])*.01,Quaternion((q[3],*q[:3])),Vector(b['UE_local_scale']))@axis
        result.append(result[b.parent.get('UE_bone_index')]@m if b.parent else m)
    return result
report=[];actions={}
for clip in ('MM_Rifle_Fire','MF_Unarmed_Walk_Fwd','MF_Pistol_Idle_ADS_AO_CD'):
    p=next(root.rglob(clip+'.uasset'));d=read_animation(p);n=d['frames'];ch=raw_euler(p,n); assert len(ch)==d['source_controls'];ch={k.casefold():v for k,v in ch.items()}
    for rig in rigs:
        if rig.animation_data:rig.animation_data.action=None
        if set(d['tracks'])!=set(b.name for b in rig.data.bones):
            try:make_action(rig,d,scene)
            except ValueError:pass
            else:raise AssertionError('Subset accepted without opt-in')
        try:make_action(rig,d,scene,allow_subset=True)
        except ValueError as exc:assert 'explicit authored source preview' in str(exc)
        else:raise AssertionError('Preview accepted without opt-in')
        a=make_action(rig,d,scene,allow_subset=True,apply_rate_scale=True,allow_source_preview=True);actions[(rig.name,clip)]=a;assert len(a.fcurves)==890+len(d['scalar_curves']) and a['UE_source_fps']==30
        rate=d['source_rate_scale'];assert abs(a.frame_range[1]-(1+(n-1)/rate))<1e-4
        maxcurve=0.
        for name,curve in d['scalar_curves'].items():
            fc=a.fcurves.find('[\"UE_curve_'+name+'\"]');ks=curve['keys'];assert fc and len(fc.keyframe_points)==len(ks)
            for key in ks:maxcurve=max(maxcurve,abs(fc.evaluate(1+key['frame']/rate)-key['value']))
            for left,right in zip(ks,ks[1:]):
                # Independently evaluate the scalar segment at interior samples.
                for u in (.25,.5,.75):
                    dt=right['frame']-left['frame'];v0,v1=left['value'],right['value'];want=(v0*(1-u)+v1*u if left['interpolation']==0 else v0 if left['interpolation']==1 else (2*u**3-3*u**2+1)*v0+(u**3-2*u**2+u)*dt*left['leave']+(-2*u**3+3*u**2)*v1+(u**3-u**2)*dt*right['arrive']);maxcurve=max(maxcurve,abs(fc.evaluate(1+(left['frame']+dt*u)/rate)-want))
            assert maxcurve<.0001,maxcurve
        bones=sorted(rig.data.bones,key=lambda b:b['UE_bone_index']);rest=[Matrix([b['UE_world_matrix_m'][j:j+4] for j in range(0,16,4)]) for b in bones];obj=next(o for o in bpy.data.objects if o.type=='MESH' and any(m.type=='ARMATURE' and m.object==rig for m in o.modifiers));pts=np.array([v.co[:] for v in obj.data.vertices]);weights=np.zeros((len(pts),89));index={b.name:i for i,b in enumerate(bones)}
        for v in obj.data.vertices:
            for g in v.groups:
                name=obj.vertex_groups[g.group].name
                if name in index:weights[v.index,index[name]]=g.weight
        maxbone=maxskin=motion=0.
        for i in sorted(set([0,n//4,n//2,3*n//4,n-1])):
            f=1+i/rate;scene.frame_set(int(f),subframe=f-int(f));bpy.context.view_layer.update();w=worlds(bones,ch,i)
            for j,b in enumerate(bones):
                want=w[j]@rest[j].inverted()@b.matrix_local;pb=rig.pose.bones[b.name];maxbone=max(maxbone,max(abs(want[x][y]-pb.matrix[x][y]) for x in range(4) for y in range(4)))
            matrices=[np.array(x@y.inverted()) for x,y in zip(w,rest)];expected=sum((pts@m[:3,:3].T+m[:3,3])*weights[:,j,None] for j,m in enumerate(matrices));ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());actual=np.array([v.co[:] for v in ev.data.vertices]);maxskin=max(maxskin,float(np.max(np.linalg.norm(actual-expected,axis=1))));motion=max(motion,float(np.max(np.linalg.norm(actual-pts,axis=1))))
        assert maxbone<.0001 and maxskin<.0001 and motion>.01,(maxbone,maxskin,motion)
        row=dict(clip=clip,rig=rig.name,frames=n,vertices=len(pts),bone_error=maxbone,skin_error_m=maxskin,max_displacement_m=motion,root_motion=d['source_root_motion'],scalar_error=maxcurve,source_rate_scale=rate,omitted_tracks=len(set(d['tracks'])-set(b.name for b in bones)));report.append(row);print('EDITOR_ANIMATION_PASS',row,flush=True)
        rig.animation_data.action=None
# Native full reference skeleton: imported through actual operator, no invented skin geometry.
import skeleton_blender
skeleton_blender.register()
try:
    before=set(bpy.data.objects);source=root/'Characters/Mannequins/Meshes/SK_Mannequin.uasset';assert getattr(bpy.ops,'import').ue_reference_skeleton(filepath=str(source))=={'FINISHED'}
    full=(set(bpy.data.objects)-before).pop();assert len(full.data.bones)==161;assert len(json.loads(full['UE_socket_definitions']))==5;assert len(json.loads(full['UE_retarget_sources_json']))==2
finally:skeleton_blender.unregister()
full.location.x=3
for clip in ('MM_Attack_01','MF_Unarmed_Walk_Fwd'):
    p=next(root.rglob(clip+'.uasset'));d=read_animation(p);n=d['frames'];ch={k.casefold():v for k,v in raw_euler(p,n).items()}
    a=make_action(full,d,scene,allow_subset=(len(ch)!=161),allow_source_preview=True);assert not a['UE_omitted_tracks'];assert len(a.fcurves)==1610+len(d['scalar_curves']);assert len(a['UE_unanimated_bones'].split(','))==(1 if len(ch)==161 else 2)
    bones=sorted(full.data.bones,key=lambda b:b['UE_bone_index']);rest=[Matrix([b['UE_world_matrix_m'][j:j+4] for j in range(0,16,4)]) for b in bones];err=0.
    for i in sorted({0,n//2,n-1}):
        scene.frame_set(i+1);bpy.context.view_layer.update();w=worlds(bones,ch,i)
        for j,b in enumerate(bones):
            want=w[j]@rest[j].inverted()@b.matrix_local;actual=full.pose.bones[b.name].matrix;err=max(err,max(abs(want[x][y]-actual[x][y]) for x in range(4) for y in range(4)))
    assert err<.0001,err;report.append(dict(clip=clip,rig=full.name,frames=n,bone_error=err,source_preview=bool(a['UE_source_preview_only']),omitted_tracks=0,source_bones=len(ch),target_bones=161));print('FULL_SKELETON_PASS',report[-1],flush=True);full.animation_data.action=None;actions[full.name,clip]=a
for rig in rigs:rig.animation_data.action=actions[rig.name,'MF_Unarmed_Walk_Fwd']
full.animation_data.action=actions[full.name,'MF_Unarmed_Walk_Fwd'];scene.frame_end=46;scene.frame_set(24);bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out))
assert sum(1 for a in bpy.data.actions if a.get('UE_source_fps')==30)==8
assert all(r.animation_data.action and r.animation_data.action['UE_source_preview_only'] for r in bpy.data.objects if r.type=='ARMATURE')
out.with_suffix('.json').write_text(json.dumps(report,indent=2));print('EDITOR_PREVIEW_REOPEN_PASS',flush=True)
