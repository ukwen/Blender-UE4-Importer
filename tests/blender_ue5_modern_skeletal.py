"""Native UE5.6 Quinn mesh and all three LODs through real Blender 4.2."""
import os,sys,json,shutil
from pathlib import Path
import bpy
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from skeletal_mesh_native import read_mesh
from ue5_modern_static import package
import skeleton_blender as sb, uproject_browser as browser
root=Path(os.environ['UASSETAPI_ASSETS']);src=next(root.rglob('SKM_Quinn_Simple.uasset'));project=Path(os.environ['UE56_PROJECT']);content=project/'Content'
for stem in ('SKM_Quinn_Simple','MI_Quinn_01','M_Mannequin'):
    p=src.with_name(stem+'.uasset'); identity=package(p)[-1];dst=content/(identity.removeprefix('/Game/')+'.uasset');dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dst);shutil.copyfile(p.with_suffix('.uexp'),dst.with_suffix('.uexp'))
desc=project/'Quinn.uproject';desc.write_text(json.dumps({'FileVersion':3,'EngineAssociation':'5.6'}))
bpy.ops.wm.read_factory_settings(use_empty=True);sb.register();browser.register()
s=bpy.context.scene.ueimport_project;s.project_path=str(desc);s.batch_scope='GEOMETRY';s.cooked_profile='5.6'
assert bpy.ops.ueimport.refresh_jobs()=={'FINISHED'} and len(s.job_items)==1
assert bpy.ops.ueimport.batch_import()=={'FINISHED'}
report=json.loads(bpy.data.texts[s.batch_report].as_string());assert report['results'][0]['status']=='reconstructed',report
out=os.environ['UE56_OUTPUT'];results=[]
for lod in range(3):
    if lod:
        assert getattr(bpy.ops,'import').ue_native_skeletal_mesh(filepath=str(src),profile='5.6',lod=lod)=={'FINISHED'}
    o=next(o for o in bpy.data.objects if o.type=='MESH' and o.data.get('UE_source_lod_index')==lod);a=o.parent;d=read_mesh(src,'5.6',lod);m=o.data
    assert len(m.vertices)==len(d['positions']) and len(m.polygons)==len(d['faces']) and len(a.data.bones)==89
    assert all(tuple(p.vertices)==f and p.material_index==s for p,f,s in zip(m.polygons,d['faces'],d['slots']))
    pos_error=max((v.co-Vector((y*.01,x*.01,z*.01))).length for v,(x,y,z) in zip(m.vertices,d['positions']))
    weight_error=0.
    for v,w in zip(m.vertices,d['weights']):
        g={x.group:x.weight for x in v.groups};assert set(g)==set(w);weight_error=max(weight_error,max(abs(g[j]-q/255) for j,q in w.items()))
    assert pos_error<1e-6 and weight_error<1e-7
    bpy.context.view_layer.update();before=[v.co.copy() for v in o.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.vertices]
    # Rotate a weighted non-root bone and compare every evaluated vertex to an independent weighted matrix sum.
    totals=[0]*89
    for w in d['weights']:
        for j,q in w.items():totals[j]+=q
    j=max((j for j in range(1,89) if totals[j]),key=lambda j:totals[j]);pb=a.pose.bones[d['bones'][j]['name']];pb.rotation_mode='XYZ';pb.rotation_euler.x=.25;bpy.context.view_layer.update()
    matrices=[a.pose.bones[b['name']].matrix@a.data.bones[b['name']].matrix_local.inverted() for b in d['bones']]
    evaluated=o.evaluated_get(bpy.context.evaluated_depsgraph_get());error=0.;move=0.;moved=0
    for v,w,rest,ev in zip(m.vertices,d['weights'],before,evaluated.data.vertices):
        expected=sum((matrices[j]@v.co*(q/255) for j,q in w.items()),Vector((0,0,0)));error=max(error,(ev.co-expected).length);dist=(ev.co-rest).length;move=max(move,dist);moved+=dist>1e-5
    assert error<1e-5 and move>.001
    pb.rotation_euler.x=0;bpy.context.view_layer.update();recovery=max((v.co-rest).length for v,rest in zip(o.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.vertices,before));assert recovery<1e-6
    if lod:a.location.x+=lod*2
    results.append(dict(lod=lod,vertices=len(m.vertices),triangles=len(m.polygons),bones=89,position_error_m=pos_error,weight_error=weight_error,deformation_error_m=error,max_movement_m=move,moved_vertices=moved,recovery_m=recovery));print('LOD_PASS',results[-1],flush=True)
bpy.ops.wm.save_as_mainfile(filepath=out);bpy.ops.wm.open_mainfile(filepath=out);s=bpy.context.scene.ueimport_project;n=len(bpy.data.objects);assert bpy.ops.ueimport.batch_import()=={'FINISHED'};repeat=json.loads(bpy.data.texts[s.batch_report].as_string());assert repeat['results'][0]['reused'] and len(bpy.data.objects)==n
assert sorted(o.data.get('UE_source_lod_index') for o in bpy.data.objects if o.type=='MESH')==[0,1,2]
Path(os.environ['UE56_REPORT']).write_text(json.dumps({'blender':bpy.app.version_string,'lods':results,'batch':report,'repeat':repeat},indent=2));print('UE56_QUINN_PASS',flush=True)
