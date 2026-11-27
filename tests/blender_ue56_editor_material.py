"""Real UE5.6 textured character gallery, material inheritance and level binding."""
import os,sys,json,hashlib
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ue5_editor_material import build_material,resolve_material
from static_scene import reconstruct_static_map
import uproject_browser as browser
project=Path(os.environ['UE56_EDITOR_PROJECT']);root=project.parent/'Content';out=Path(os.environ['UE56_EDITOR_OUTPUT']);bpy.ops.wm.read_factory_settings(use_empty=True);browser.register()
def pkg(stem):return '/Game/'+next(root.rglob(stem+'.uasset')).relative_to(root).with_suffix('').as_posix()
flat=build_material(root,pkg('MI_ThirdPersonColWay'));assert flat['UE_editor_material_status']=='supported_pbr_subset'; bs=next(n for n in flat.node_tree.nodes if n.type=='BSDF_PRINCIPLED');assert abs(bs.inputs['Roughness'].links[0].from_socket.default_value-.268)<1e-6;assert abs(bs.inputs['Base Color'].links[0].from_socket.default_value[1]-.527115)<1e-6
strict=build_material(root,pkg('MI_Quinn_01'));assert strict['UE_editor_material_status']=='metadata_only';assert not any(l.to_node.type=='BSDF_PRINCIPLED' for l in strict.node_tree.links)
s=bpy.context.scene.ueimport_project;s.project_path=str(project);s.batch_scope='GEOMETRY';s.cooked_profile='5.6';s.job_filter='SKM_';s.static_materials=True;s.partial_materials=True
assert bpy.ops.ueimport.refresh_jobs()=={'FINISHED'};assert len(s.job_items)==2;assert bpy.ops.ueimport.batch_import()=={'FINISHED'}
r=json.loads(bpy.data.texts[s.batch_report].as_string());assert len(r['results'])==2 and all(x['status']=='reconstructed' for x in r['results']),r['results'];materials={}
for o in bpy.data.objects:
    if o.type!='MESH':continue
    assert len(o.material_slots)==2
    for slot in o.material_slots:
        m=slot.material;assert m['UE_editor_material_status']=='partial';output=json.loads(m['UE_editor_connected_outputs']);assert set(('BaseColor','Metallic','Roughness','Normal'))<=set(output),output
        imgs=[n.image for n in m.node_tree.nodes if n.type=='TEX_IMAGE' and n.image];assert len(imgs)==3 and all(x.packed_file and x.get('UE_source_rgba_sha256') for x in imgs)
        materials[m['UE_material_package']]=dict(status=m['UE_editor_material_status'],outputs=output,issues=json.loads(m['UE_editor_material_issues']),images=[x.name for x in imgs])
assert len(materials)==4
collection,report=reconstruct_static_map(str(root/'ThirdPerson/Lvl_ThirdPerson.umap'),materials=True,allow_partial_materials=True,cooked_profile='5.6');assert report['actor_status']['reconstructed']==53 and report['materials_imported'];print('MAP_MATERIALS',report['material_report'],flush=True)
assert any(x['status']=='supported_pbr_subset' for x in report['material_report'].values());count=len(bpy.data.objects);image_count=len(bpy.data.images);bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out));s=bpy.context.scene.ueimport_project;assert bpy.ops.ueimport.refresh_jobs()=={'FINISHED'};assert bpy.ops.ueimport.batch_import()=={'FINISHED'};r=json.loads(bpy.data.texts[s.batch_report].as_string());assert all(x.get('reused') for x in r['results']) and len(bpy.data.objects)==count and len(bpy.data.images)==image_count
s.partial_materials=False;assert bpy.ops.ueimport.batch_import()=={'FINISHED'};r=json.loads(bpy.data.texts[s.batch_report].as_string());assert all(x['status']=='blocked_stale' for x in r['results']) and len(bpy.data.objects)==count,r['results']
out.with_suffix('.json').write_text(json.dumps(dict(character_materials=materials,map_materials=report['material_report'],packed_images=sum(bool(x.packed_file) for x in bpy.data.images),batch_reuse=True,changed_settings_blocked=True),indent=2));print('EDITOR_MATERIAL_PASS',flush=True)
