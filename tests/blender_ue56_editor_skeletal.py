"""Original UE5.6 source mesh weights and editable rigs, no cooked geometry fallback."""
import os,sys,json
from pathlib import Path
import bpy
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ue5_editor_mesh import read_skeletal
import skeleton_blender as sb,uproject_browser as browser
bpy.ops.wm.read_factory_settings(use_empty=True);sb.register();browser.register()
project=Path(os.environ['UE56_EDITOR_PROJECT']);out=Path(os.environ['UE56_EDITOR_OUTPUT']);s=bpy.context.scene.ueimport_project;s.project_path=str(project);s.batch_scope='GEOMETRY';s.cooked_profile='5.6';s.job_filter='SKM_'
assert bpy.ops.ueimport.refresh_jobs()=={'FINISHED'};assert len(s.job_items)==2
assert bpy.ops.ueimport.batch_import()=={'FINISHED'}
report=json.loads(bpy.data.texts[s.batch_report].as_string());print('SKELETAL_BATCH',[(r['status'],r.get('detail')) for r in report['results']],flush=True);assert len(report['results'])==2 and all(r['status']=='reconstructed' for r in report['results'])
results=[]
for p in sorted(project.parent.rglob('SKM_*.uasset')):
    d=read_skeletal(p);o=next(o for o in bpy.data.objects if o.type=='MESH' and o.get('UE_mesh_package','').endswith('/'+p.stem));a=o.parent;m=o.data;ids=sorted(d['vertices']);index={v:i for i,v in enumerate(ids)}
    assert len(m.vertices)==len(ids) and len(m.polygons)==len(d['triangles']) and len(a.data.bones)==len(d['bones'])==89
    assert all(tuple(poly.vertices)==tuple(index[d['instances'][c]] for c in corners) and poly.material_index==d['group_to_slot'][g] for poly,(g,corners) in zip(m.polygons,d['triangles']))
    pos_error=max((v.co-Vector((y*.01,x*.01,z*.01))).length for v,(x,y,z) in zip(m.vertices,(d['vertices'][i] for i in ids)));weight_error=0
    for v,i in zip(m.vertices,ids):
        weights=d['weights'][i];g={x.group:x.weight for x in v.groups};assert set(g)==set(weights);weight_error=max(weight_error,max(abs(g[j]-w/65535) for j,w in weights.items()))
    assert pos_error<1e-6 and weight_error<1e-7
    bpy.context.view_layer.update();before=[v.co.copy() for v in o.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.vertices]
    totals=[0]*89
    for w in d['weights'].values():
        for j,q in w.items():totals[j]+=q
    j=max(range(1,89),key=lambda j:totals[j]);pb=a.pose.bones[d['bones'][j]['name']];pb.rotation_mode='XYZ';pb.rotation_euler.x=.25;bpy.context.view_layer.update()
    matrices=[a.pose.bones[b['name']].matrix@a.data.bones[b['name']].matrix_local.inverted() for b in d['bones']]
    ev=o.evaluated_get(bpy.context.evaluated_depsgraph_get());error=move=0.;moved=0
    for v,i,rest,e in zip(m.vertices,ids,before,ev.data.vertices):
        expected=sum((matrices[j]@v.co*(q/65535) for j,q in d['weights'][i].items()),Vector((0,0,0)));error=max(error,(e.co-expected).length);dist=(e.co-rest).length;move=max(move,dist);moved+=dist>1e-5
    assert error<1e-5 and move>.001
    pb.rotation_euler.x=0;bpy.context.view_layer.update();recovery=max((v.co-rest).length for v,rest in zip(o.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.vertices,before));assert recovery<1e-6
    pb.keyframe_insert(data_path='rotation_euler',frame=1);pb.rotation_euler.x=.25;pb.keyframe_insert(data_path='rotation_euler',frame=15);a.animation_data.action.name=p.stem+'_TestPose';bpy.context.scene.frame_set(1)
    result=dict(asset=p.stem,vertices=len(m.vertices),triangles=len(m.polygons),bones=89,position_error_m=pos_error,weight_error=weight_error,deformation_error_m=error,max_movement_m=move,moved_vertices=moved,recovery_m=recovery,material_slots=d['materials']);results.append(result);print('SKELETAL_PASS',result,flush=True)
n=len(bpy.data.objects);bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out));s=bpy.context.scene.ueimport_project;assert bpy.ops.ueimport.refresh_jobs()=={'FINISHED'};assert bpy.ops.ueimport.batch_import()=={'FINISHED'};repeat=json.loads(bpy.data.texts[s.batch_report].as_string());assert all(r.get('reused') for r in repeat['results']) and len(bpy.data.objects)==n
assert len([o for o in bpy.data.objects if o.type=='ARMATURE' and o.animation_data.action])==2
out.with_suffix('.json').write_text(json.dumps(dict(results=results,batch_reuse=True),indent=2));print('EDITOR_SKELETAL_PASS',flush=True)
