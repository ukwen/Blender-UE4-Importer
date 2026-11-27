"""Integrated original map reconstruction; independent source-axis world matrix test."""
import os,sys,json,math
from pathlib import Path
import bpy
from mathutils import Matrix,Vector
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ue5_editor_characters import placements
import uproject_browser as browser
project=Path(os.environ['UE56_EDITOR_PROJECT']);root=project.parent/'Content';out=Path(os.environ['UE56_EDITOR_OUTPUT']);bpy.ops.wm.read_factory_settings(use_empty=True);browser.register()
s=bpy.context.scene.ueimport_project;s.project_path=str(project);s.batch_scope='SELECTED_MAP';s.cooked_profile='5.6';s.components=True;s.static_materials=False
assert bpy.ops.ueimport.scan_project()=={'FINISHED'}
expected={};reports={}
for stem,n in [('MainLevel',6),('TestLevel',1)]:
    p=root/f'MyStuff/Maps/{stem}.umap';s.active=next(i for i,m in enumerate(s.maps) if Path(m.filepath)==p);assert bpy.ops.ueimport.refresh_jobs()=={'FINISHED'};assert bpy.ops.ueimport.batch_import()=={'FINISHED'}
    report=json.loads(bpy.data.texts[s.batch_report].as_string());r=report['results'][0];assert r['status']=='completed' and r['has_unresolved_characters'],r
    c=bpy.data.collections[r['collection']];data=json.loads(bpy.data.texts[c['UE_report']].as_string());ch=data['character_report'];print('LEVEL',stem,ch['status'],[x.get('detail') for x in ch['records']],flush=True);assert ch['status']=={'geometry_only_unresolved_slots':n},ch;assert ch['decoded_meshes']==1
    expected[c.name]=placements(root,p)['records'];reports[stem]=dict(static=data['actor_status'],characters=ch['status'],decoded_meshes=ch['decoded_meshes']);assert len(expected[c.name])==n

def verify():
    bpy.context.view_layer.update();swap=Matrix(((0,1,0),(1,0,0),(0,0,1)));n=vertices=bones=0;maxerr=0.
    def matrix(f):
        pitch,yaw,roll=map(math.radians,f['RelativeRotation']);R=swap@Matrix.Rotation(yaw,3,'Z')@Matrix.Rotation(-pitch,3,'Y')@Matrix.Rotation(-roll,3,'X')@swap
        S=Matrix.Diagonal(Vector((f['RelativeScale3D'][1],f['RelativeScale3D'][0],f['RelativeScale3D'][2])));M=(R@S).to_4x4();M.translation=swap@Vector(f['RelativeLocation'])*.01;return M
    for name,records in expected.items():
        c=bpy.data.collections[name];anchors={o['UE_actor']:o for o in c.objects if o.get('UE_character_record')};assert len(anchors)==len(records)
        for r in records:
            a=anchors[r['actor']];arm=next(o for o in a.children if o.type=='ARMATURE');mesh=next(o for o in arm.children if o.type=='MESH');assert mesh.modifiers[0].object==arm and len(mesh.vertex_groups)==155;assert arm.get('UE_socket_status','').startswith('missing original reference skeleton');assert len(mesh.data.vertices)==56434 and len(arm.data.bones)==155
            assert len(json.loads(mesh.data['UE_unresolved_material_groups']))==5 and len(json.loads(mesh.data['UE_original_material_table']))==5 and len(json.loads(mesh['UE_material_override_packages']))==5
            used={p.material_index for p in mesh.data.polygons};assert len(used)==5 and all(not mesh.material_slots[i].material.get('UE_material_package') for i in used)
            for actual,want in [(a.matrix_world,matrix(r['root_fields'])),(arm.matrix_world,matrix(r['root_fields'])@matrix(r['mesh_fields']))]:maxerr=max(maxerr,max(abs(actual[i][j]-want[i][j]) for i in range(4) for j in range(4)))
            n+=1;vertices+=len(mesh.data.vertices);bones+=len(arm.data.bones)
    assert n==7 and maxerr<1e-4,(n,maxerr);return dict(characters=n,vertices=vertices,bones=bones,max_world_matrix_error=maxerr)
before=verify();bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out));after=verify();s=bpy.context.scene.ueimport_project;n=len(bpy.data.objects);assert bpy.ops.ueimport.refresh_jobs()=={'FINISHED'};assert bpy.ops.ueimport.batch_import()=={'FINISHED'};r=json.loads(bpy.data.texts[s.batch_report].as_string());assert r['results'][0]['reused'] and len(bpy.data.objects)==n
out.with_suffix('.json').write_text(json.dumps(dict(levels=reports,before=before,after=after,reuse=True),indent=2));print('LEVEL_CHARACTERS_PASS',after,flush=True)
