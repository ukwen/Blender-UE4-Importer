"""Genuine UE5.0 cooked split assets through the production gallery and import menus."""
import os,sys,json,shutil
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cooked_static import read_static
from skeletal_mesh_native import read_mesh
from skeleton_native import read_cooked_skeleton
from texture_blender import load_native_texture
from project_preflight import preflight
from project_session import run_session
import skeleton_blender as sb, uproject_browser as browser

root=Path(os.environ['MATYA_ASSETS']); project=Path(os.environ['UE5_COOKED_PROJECT']); content=project/'Content'; content.mkdir(parents=True,exist_ok=True)
for p in (root/'5.0').iterdir():
    if p.is_file(): shutil.copyfile(p,content/p.name)
desc=project/'Worm.uproject'; desc.write_text(json.dumps({'FileVersion':3,'EngineAssociation':'5.0'}))
bpy.ops.wm.read_factory_settings(use_empty=True); sb.register(); browser.register()
plan=preflight(str(desc),'GEOMETRY'); assert len(plan['jobs'])==2 and plan['inventory_count']==8 and plan['closure_count']==8,plan
assert all(v['coverage']=='ue5_cooked_import_table' for v in plan['records'].values())
assert set(plan['dependencies'])=={'/Game/M_Worm','/Game/SK_Worm_PhysicsAsset','/Game/SK_Worm_Skeleton','/Game/T_Worm_A','/Game/T_Worm_D','/Game/T_Worm_N'}
assert plan['dependency_counts']=={'available':6},plan['dependency_counts']
s=bpy.context.scene.ueimport_project;s.project_path=str(desc);s.batch_scope='GEOMETRY';s.cooked_profile='5.0'
assert bpy.ops.ueimport.refresh_jobs()=={'FINISHED'} and len(s.job_items)==2
assert bpy.ops.ueimport.batch_import()=={'FINISHED'}
report=json.loads(bpy.data.texts[s.batch_report].as_string());assert len(report['results'])==2 and all(x['status']=='reconstructed' for x in report['results']),report
meshes=[o for o in bpy.data.objects if o.type=='MESH'];assert len(meshes)==2
for obj in meshes:
    m=obj.data; assert (len(m.vertices),len(m.polygons))==(640,572) and m.has_custom_normals and len(m.uv_layers)==1
    assert m.materials[0]['UE_material_package']=='/Game/M_Worm'
    native=(read_mesh if obj.parent else read_static)(content/('SK_Worm.uasset' if obj.parent else 'SM_Worm.uasset'),'5.0')
    assert max(abs(c-x) for v,(x0,y0,z0) in zip(m.vertices,native['positions']) for c,x in zip(v.co,(y0*.01,x0*.01,z0*.01)))<1e-6
    assert all(tuple(p.vertices)==f for p,f in zip(m.polygons,native['faces']))
    assert max(abs(c-x) for l,uv in zip(m.loops,m.uv_layers[0].data) for c,x in zip(uv.uv,(native['uvs'][l.vertex_index][0],1-native['uvs'][l.vertex_index][1])))<1e-6
# Reference-skeleton and individual static mesh import menu paths.
assert getattr(bpy.ops,'import').ue_reference_skeleton(filepath=str(content/'SK_Worm_Skeleton.uasset'),profile='5.0')=={'FINISHED'}
armatures=[o for o in bpy.data.objects if o.type=='ARMATURE'];assert len(armatures)==2 and all(len(o.data.bones)==6 for o in armatures)
assert getattr(bpy.ops,'import').ue_cooked_static(filepath=str(content/'SM_Worm.uasset'),profile='5.0')=={'FINISHED'}
extra=next(o for o in bpy.data.objects if o.type=='MESH' and o not in meshes);bpy.data.objects.remove(extra,do_unlink=True)
# Textures are original decoded pixels; material graph intentionally unresolved.
for name in ('A','D','N'):
    im=load_native_texture(content/f'T_Worm_{name}.uasset','5.0',srgb=name=='D');im.use_fake_user=True
    assert tuple(im.size)==(256,256) and im.packed_file
out=os.environ['UE5_COOKED_OUTPUT'];bpy.ops.wm.save_as_mainfile(filepath=out);bpy.ops.wm.open_mainfile(filepath=out)
assert len([i for i in bpy.data.images if i.packed_file and i.get('UE_raw_texture_key')])==3
assert len([i for i in bpy.data.images if i.packed_file and i.get('UE_texture_format') and not i.get('UE_raw_texture_key')])==3
n=len(bpy.data.objects);s=bpy.context.scene.ueimport_project;assert bpy.ops.ueimport.batch_import()=={'FINISHED'}
repeat=json.loads(bpy.data.texts[s.batch_report].as_string());assert len(repeat['results'])==2 and all(x.get('reused') for x in repeat['results']) and len(bpy.data.objects)==n
bpy.ops.wm.save_as_mainfile(filepath=out)
Path(os.environ['UE5_COOKED_REPORT']).write_text(json.dumps({'blender':bpy.app.version_string,'inventory':plan,'batch':report,'repeat':repeat,'vertices':1280,'triangles':1144,'skeleton_bones':6,'packed_textures':3,'native_material_graph':'unresolved'},indent=2))
print('UE5_COOKED_GALLERY_PASS',flush=True)
