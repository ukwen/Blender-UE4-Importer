"""Withhold exact original assets in disposable copy; restore through actual operator."""
import json,os,sys,shutil,tempfile,math
from pathlib import Path
from collections import Counter
import bpy
from mathutils import Matrix,Vector
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ue5_editor_mesh import read_static
from ue5_editor_repair import restore
from project_session import hash_file
import uproject_browser as browser
src=Path(os.environ['UE56_EDITOR_PROJECT']);out=Path(os.environ['UE56_EDITOR_OUTPUT']);temp=tempfile.TemporaryDirectory();root=Path(temp.name)/'ShooterSam';shutil.copytree(src.parent,root);project=root/src.name;content=root/'Content';map_path=content/'Variant_Combat/Lvl_Combat.umap'
names=['LevelPrototyping/Meshes/SM_Cube.uasset','LevelPrototyping/Interactable/Door/Assets/Meshes/SM_DoorFrame_Edge.uasset'];packages=['/Game/'+str(Path(n).with_suffix('')).replace('\\','/') for n in names];hashes={p:hash_file(src.parent/'Content'/n) for p,n in zip(packages,names)};native={p:read_static(src.parent/'Content'/n) for p,n in zip(packages,names)}
for n in names:(content/n).unlink()
bpy.ops.wm.read_factory_settings(use_empty=True);browser.register();s=bpy.context.scene.ueimport_project;s.project_path=str(project);s.components=True;s.static_materials=False;s.cooked_profile='5.6';assert bpy.ops.ueimport.scan_project()=={'FINISHED'};s.active=next(i for i,m in enumerate(s.maps) if Path(m.filepath)==map_path);assert bpy.ops.ueimport.reconstruct_static()=={'FINISHED'}
original=next(c for c in bpy.data.collections if c.get('UE_source_map_path')==str(map_path));original_report=bpy.data.texts[original['UE_report']].as_string();members={o.name for o in original.objects};anchors=[o for o in original.objects if o.get('UE_mesh_package') in packages];assert len(anchors)==36 and all(o.type=='EMPTY' and o['UE_geometry_status']=='missing' for o in anchors);engine=next(o for o in original.objects if o.get('UE_mesh_package','').startswith('/Engine/') and o['UE_geometry_status']=='missing');anchors[0].location.x+=.123 # preserve intentional user edits

def select(items):
    bpy.ops.object.select_all(action='DESELECT')
    for o in items:o.select_set(True)
    bpy.context.view_layer.objects.active=items[0]
select(anchors+[engine]);_,r=restore(str(map_path),anchors+[engine]);assert r['counts']=={'still_missing':37};assert not [o for o in bpy.data.objects if o.get('UE_repair_child')]
# Wrong original at the expected path must not be accepted even if the file has valid native geometry.
shutil.copy2(src.parent/'Content'/names[1],content/names[0]);_,r=restore(str(map_path),anchors+[engine]);assert r['counts']=={'unresolved':33,'still_missing':4},r
for n in names:shutil.copy2(src.parent/'Content'/n,content/n)
s.static_materials=True;s.partial_materials=True;assert bpy.ops.ueimport.repair_missing_meshes()=={'FINISHED'};repairs=[o for o in bpy.data.objects if o.get('UE_repair_child')];assert len(repairs)==36;assert len({o.data.as_pointer() for o in repairs})==2

def verify():
    bpy.context.view_layer.update();err=0.;v_err=0.;recovered=Counter();orig=bpy.data.collections[original_name];assert set(o.name for o in orig.objects)==members and bpy.data.texts[orig['UE_report']].as_string()==original_report
    for o in bpy.data.objects:
        if not o.get('UE_repair_child'):continue
        a=o.parent;p=o['UE_mesh_package'];d=native[p];assert a and a.name in members and a['UE_geometry_status']=='missing';assert o['UE_repair_source_sha256']==hashes[p];assert len(o.data.vertices)==len(d['vertices']) and len(o.data.polygons)==len(d['triangles']);assert o.data['UE_source_payload_blake3']==d['source_hash'];assert json.loads(o['UE_material_override_packages'])==json.loads(a['UE_material_override_packages']);assert o.matrix_basis==Matrix.Identity(4)
        err=max(err,max(abs(o.matrix_world[i][j]-a.matrix_world[i][j]) for i in range(4) for j in range(4)))
        v_err=max(v_err,max(abs(v.co[k]-x[k]) for v,xyz in zip(o.data.vertices,(d['vertices'][i] for i in sorted(d['vertices']))) for x in [(xyz[1]*.01,xyz[0]*.01,xyz[2]*.01)] for k in range(3)))
        for i,pkg in enumerate(json.loads(a['UE_material_override_packages'])):
            if pkg:assert o.material_slots[i].material.get('UE_material_package')==pkg
        recovered[p]+=1
    assert sum(recovered.values())==36 and err<1e-6 and v_err<1e-6
    return dict(recovered=dict(recovered),max_world_matrix_error=err,max_vertex_error_m=v_err)
original_name=original.name;before=verify();n=len(bpy.data.objects);repair_collection=next(c for c in bpy.data.collections if c.get('UE_repair_source_map'));material_report=json.loads(bpy.data.texts[repair_collection['UE_report']].as_string())['materials'];assert any(x['status'] in ('supported_pbr_subset','partial') for x in material_report.values()),material_report;_,r=restore(str(map_path),anchors+[engine],True,True);assert r['counts']=={'existing_repair':36,'still_missing':1};assert len(bpy.data.objects)==n
# Different source bytes after successful recovery must not silently replace prior mesh.
shutil.copy2(src.parent/'Content'/names[1],content/names[0]);_,r=restore(str(map_path),anchors+[engine],True,True);assert r['counts']=={'blocked_stale':33,'existing_repair':3,'still_missing':1};assert len(bpy.data.objects)==n;shutil.copy2(src.parent/'Content'/names[0],content/names[0])
bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out));after=verify();assert len(bpy.data.objects)==n;anchors=[o for o in bpy.data.collections[original_name].objects if o.get('UE_mesh_package') in packages];_,r=restore(str(map_path),anchors,True,True);assert r['counts']=={'existing_repair':36} and len(bpy.data.objects)==n
report=dict(before=before,after=after,materials=material_report,wrong_package_rejected=True,stale_source_rejected=True,duplicate_free=True,original_report_unchanged=True,original_collection_membership_unchanged=True,missing_engine_preserved=True,source_fixture_hashes=hashes,scope='Original packages withheld and restored in disposable fixture; genuine missing StarterBundle/Engine packages not supplied')
out.with_suffix('.json').write_text(json.dumps(report,indent=2));print('REPAIR_ACCEPTANCE_PASS',report,flush=True);temp.cleanup()
