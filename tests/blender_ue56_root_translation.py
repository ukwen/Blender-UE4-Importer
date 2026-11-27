"""Real source root split, native full skeleton, every source frame and reopen."""
import json,os,sys,struct
from pathlib import Path
import bpy
from mathutils import Vector,Matrix
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from animation_native import read_animation,make_action
from ue5_blueprint import read_tables
from ue5_editor_tags import export_tags,read_tag_stream
from skeleton_native import Reader
import skeleton_blender as sb
root=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content';out=Path(os.environ['UE56_EDITOR_OUTPUT'])
bpy.ops.wm.read_factory_settings(use_empty=True);sb.register();scene=bpy.context.scene;scene.render.fps=24;scene.render.fps_base=1
source=root/'Characters/Mannequins/Meshes/SK_Mannequin.uasset'
assert getattr(bpy.ops,'import').ue_reference_skeleton(filepath=str(source))=={'FINISHED'}
rig=next(o for o in bpy.data.objects if o.type=='ARMATURE');rig.select_set(True);bpy.context.view_layer.objects.active=rig;rig.location=(2,3,4)
# Read root translation bytes independently of the animation decoder.
def raw_root(p,n):
    m,b,im,ex,ref,pkg=read_tables(p);e=next(e for e in ex if e['kind']=='MovieSceneControlRigParameterSection');r=Reader(export_tags(b,e,m['names'])['TransformParameterNamesAndCurves']['data'])
    for _ in range(r.i()):
        t=read_tag_stream(r,m['names'],indexed=True);name=Reader(t['ParameterName']['data']).name(m['names'])
        if name.casefold()!='root_control':continue
        ch=[]
        for j in range(3):
            v=t['Translation' if j==0 else ('Translation',j)]['data'];count=struct.unpack_from('<i',v,6)[0];ch.append([struct.unpack_from('<f',v,18+4*count+28*i)[0] for i in range(count)] if count else [struct.unpack_from('<f',v,len(v)-20)[0]]*n)
        return [Vector(((ch[1][i]-ch[1][0])*.01,(ch[0][i]-ch[0][0])*.01,(ch[2][i]-ch[2][0])*.01)) for i in range(n)]
    raise AssertionError('root not found')
def detach():
    if rig.animation_data:rig.animation_data.action=None
reports=[];pairs=[]
for clip in ('MF_Rifle_Walk_Fwd_Left','MM_Rifle_Jump_Fall_Loop','MM_Dash','MM_Attack_01','MF_Unarmed_Walk_Fwd','MM_Pistol_Jump_RecoveryAdditive'):
    p=next(root.rglob(clip+'.uasset'));d=read_animation(p);n=d['frames'];delta=raw_root(p,n)
    # Use full rig for wide clips and a matched native simple rig for 89 tracks.
    if len(d['tracks'])==89:
        if 'simple' not in locals():
            from ue5_editor_mesh import read_skeletal
            from ue5_editor_mesh import build_skeletal
            mesh=read_skeletal(next(root.rglob('SKM_Manny_Simple.uasset')));obj,simple=build_skeletal(mesh);simple.location=(2,3,4)
        rig=simple
    else:rig=next(o for o in bpy.data.objects if o.type=='ARMATURE' and len(o.data.bones)==161)
    detach();original=make_action(rig,d,scene,start=3,allow_subset=True,apply_rate_scale=True,allow_source_preview=True);detach()
    # Exercise the actual import operator, including options.
    bpy.context.view_layer.objects.active=rig;rig.select_set(True)
    assert getattr(bpy.ops,'import').ue_raw_animation(filepath=str(p),start_frame=3,allow_subset=True,apply_rate_scale=True,allow_source_preview=True,root_translation_mode='IN_PLACE')=={'FINISHED'}
    split=rig.animation_data.action;assert split['UE_root_translation_mode']=='in_place_first_sample_translation_only';assert len(split.fcurves)==len(original.fcurves)+3
    pairs.append((rig.name,original.name,split.name,clip,n,delta,d['source_rate_scale']))

def verify():
    rows=[]
    for rig_name,orig,split,clip,n,delta,rate in pairs:
        rig=bpy.data.objects[rig_name];scene=bpy.context.scene;expected=[];skin={};obj=next((o for o in rig.children if o.type=='MESH'),None);rig.animation_data.action=bpy.data.actions[orig]
        for i in range(n):
            f=3+i*24/30/rate;scene.frame_set(int(f),subframe=f-int(f));bpy.context.view_layer.update();expected.append([b.matrix.copy() for b in rig.pose.bones])
            if obj and i in (0,n//2,n-1):skin[i]=[v.co.copy() for v in obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.vertices]
        rig.animation_data.action=bpy.data.actions[split];maxbone=maxpath=maxskin=0.;stored=json.loads(rig.animation_data.action['UE_authored_root_translation_json']);assert len(stored['delta_m'])==n
        for i in range(n):
            f=3+i*24/30/rate;scene.frame_set(int(f),subframe=f-int(f));bpy.context.view_layer.update();v=Vector(rig['UE_authored_root_delta_m']);maxpath=max(maxpath,(v-delta[i]).length,(Vector(stored['delta_m'][i])-delta[i]).length)
            for bone,want in zip(rig.pose.bones,expected[i]):
                actual=Matrix.Translation(v)@bone.matrix;maxbone=max(maxbone,max(abs(actual[x][y]-want[x][y]) for x in range(4) for y in range(4)))
            if i in skin:
                actual=obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.vertices;maxskin=max(maxskin,max((vtx.co+v-want).length for vtx,want in zip(actual,skin[i])))
        assert maxpath<.00005 and maxbone<.0001 and maxskin<.0001,(clip,maxpath,maxbone);assert tuple(rig.location)==(2,3,4)
        rows.append(dict(clip=clip,frames=n,bones=len(rig.data.bones),end_delta_m=list(delta[-1]),max_path_error_m=maxpath,max_recomposition_matrix_error=maxbone,max_skin_recomposition_error_m=maxskin,skin_vertices=len(obj.data.vertices) if obj else 0));print('ROOT_SPLIT_PASS',rows[-1],flush=True)
    return rows
before=verify();rig=bpy.data.objects[pairs[0][0]];detach();bad=read_animation(next(root.rglob('MM_Idle.uasset')));count=len(bpy.data.actions)
try:make_action(rig,bad,scene,allow_subset=True,root_translation_mode='IN_PLACE')
except ValueError:pass
else:raise AssertionError('non-root-motion clip accepted')
assert len(bpy.data.actions)==count
# Existing unrelated property must never be overwritten.
rig['UE_authored_root_delta_owner']='unrelated';d=read_animation(next(root.rglob('MF_Rifle_Walk_Fwd_Left.uasset')))
try:make_action(rig,d,scene,allow_subset=True,root_translation_mode='IN_PLACE')
except ValueError:pass
else:raise AssertionError('property collision accepted')
assert rig['UE_authored_root_delta_owner']=='unrelated' and len(bpy.data.actions)==count;rig['UE_authored_root_delta_owner']='editor_fk_v1'
bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out));after=verify();out.with_suffix('.json').write_text(json.dumps(dict(before=before,after=after,refusals=True,runtime_equivalence=False),indent=2));print('ROOT_SPLIT_REOPEN_PASS',flush=True)
# Exercise the reference-comparison gate on original source bytes independently.
# Deliberately not an engine-evaluated reference.
from animation_reference import compare_reference
from mathutils import Quaternion
import math,hashlib
rig_name,orig,_,clip,n,_,_=pairs[0];rig=bpy.data.objects[rig_name];scene=bpy.context.scene;rig.animation_data.action=bpy.data.actions[orig];p=next(root.rglob(clip+'.uasset'))
m,b,im,ex,ref,pkg=read_tables(p);e=next(e for e in ex if e['kind']=='MovieSceneControlRigParameterSection');reader=Reader(export_tags(b,e,m['names'])['TransformParameterNamesAndCurves']['data']);tracks={}
for _ in range(reader.i()):
    tags=read_tag_stream(reader,m['names'],indexed=True);name=Reader(tags['ParameterName']['data']).name(m['names'])[:-8].casefold();ch=[]
    for k in ('Translation','Rotation','Scale'):
        for j in range(3):
            v=tags[k if j==0 else (k,j)]['data'];count=struct.unpack_from('<i',v,6)[0];ch.append([struct.unpack_from('<f',v,18+4*count+28*i)[0] for i in range(count)] if count else [struct.unpack_from('<f',v,len(v)-20)[0]]*n)
    tracks[name]=ch
bones=sorted(rig.data.bones,key=lambda b:b['UE_bone_index']);frames=[]
for i in range(n):
    worlds=[]
    for b in bones:
        ch=tracks.get(b.name.casefold())
        if ch:
            v=[c[i] for c in ch];rx,ry,rz=map(math.radians,v[3:6]);local=Matrix.Translation(Vector(v[:3]))@Matrix.Rotation(rz,4,'Z')@Matrix.Rotation(-ry,4,'Y')@Matrix.Rotation(-rx,4,'X')@Matrix.Diagonal((*v[6:],1.))
        else:
            q=b['UE_local_rotation_xyzw'];local=Matrix.LocRotScale(Vector(b['UE_local_translation_cm']),Quaternion((q[3],*q[:3])),Vector(b['UE_local_scale']))
        worlds.append(worlds[b.parent['UE_bone_index']]@local if b.parent else local)
    frames.append(dict(sample=i,matrices=[[v for row in w for v in row] for w in worlds]))
reference=dict(schema='ue_component_pose_reference_v1',provenance=dict(kind='authored_fixture',description='Independent original serialized Euler channels, NOT Unreal evaluated'),source_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),skeleton_package=rig['UE_skeleton_package'],animation_name=clip,space='unreal_component_cm_column_vector',bones=[b.name for b in bones],frames=frames)
old=scene.frame_current,scene.frame_subframe;report=compare_reference(rig,scene,reference);assert report['within_tolerance'] and not report['provenance_authenticated'],report;assert (scene.frame_current,scene.frame_subframe)==old
reference['frames'][5]['matrices'][1][3]+=1.;bad_report=compare_reference(rig,scene,reference);assert not bad_report['within_tolerance'] and bad_report['max_position_error_m']>.009
reference['source_sha256']='0'*64
try:compare_reference(rig,scene,reference)
except ValueError:pass
else:raise AssertionError('Mismatched source accepted')
report['negative_control_position_error_m']=bad_report['max_position_error_m'];report['wrong_source_rejected']=True;out.with_name('reference-070.json').write_text(json.dumps(report,indent=2));print('REFERENCE_GATE_PASS',report,flush=True)
