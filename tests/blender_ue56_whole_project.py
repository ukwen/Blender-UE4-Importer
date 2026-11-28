"""All six original saved maps, registered UI, independent visibility, reopen.
The incomplete original project is not a complete visual/streaming transfer.
"""
import os,sys,json,hashlib
from pathlib import Path
from array import array
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uproject_browser as browser
from project_session import new_ids
from saved_project_levels import reconstruct,map_redirector
project=Path(os.environ['UE56_EDITOR_PROJECT']);out=Path(os.environ['UE56_EDITOR_OUTPUT']);content=project.parent/'Content'
all_paths=sorted(content.rglob('*.umap'));aliases={str(p):map_redirector(p) for p in all_paths if map_redirector(p)};paths=[p for p in all_paths if str(p) not in aliases];assert len(paths)==6 and len(aliases)==1,aliases
bpy.ops.wm.read_factory_settings(use_empty=True);browser.register();scene=bpy.context.scene
camera=bpy.data.objects.new('User Camera',bpy.data.cameras.new('User Camera'));scene.collection.objects.link(camera);scene.camera=camera
world=bpy.data.worlds.new('User World');scene.world=world
s=scene.ueimport_project;s.project_path=str(project);s.partial_materials=True;s.scene_cache_mib=0;assert bpy.ops.ueimport.scan_project()=={'FINISHED'}
assert {Path(m.filepath) for m in s.maps}==set(paths);assert json.loads(s.map_redirectors)==[dict(source='MyStuff/TestLevel.umap',destination='/Game/MyStuff/Maps/TestLevel')]
for m in s.maps:m.enabled=True
assert bpy.ops.ueimport.level_set()=={'FINISHED'}
group=next(c for c in scene.collection.children if c.get('UE_project_level_set'));report=json.loads(bpy.data.texts[group['UE_report']].as_string());assert len(report['levels'])==6
assert scene.camera==camera and scene.world==world

def snapshot():
    result={};group=next(c for c in bpy.context.scene.collection.children if c.get('UE_project_level_set'));settings=bpy.context.scene.ueimport_project
    roots={c['UE_full_scene_source']:c for c in group.children};assert set(roots)==set(map(str,paths))
    for p in paths:
        source=str(p);settings.active=next(i for i,m in enumerate(settings.maps) if m.filepath==source);assert bpy.ops.ueimport.activate_level()=={'FINISHED'};bpy.context.view_layer.update();root=roots[source]
        assert all(c.hide_render==c.hide_viewport==(k!=source) for k,c in roots.items())
        r=json.loads(bpy.data.texts[root['UE_report']].as_string());assert len(root.all_objects)==r['counts']['objects']
        h=hashlib.sha256();mesh_hashes={}
        for ob in sorted(root.all_objects,key=lambda x:x.name):
            h.update(repr((ob.name,ob.type,tuple(v for row in ob.matrix_world for v in row))).encode())
            if ob.type!='MESH':continue
            mesh=ob.data
            if mesh.name not in mesh_hashes:
                mh=hashlib.sha256()
                for coll,field,kind,n in ((mesh.vertices,'co','f',3),(mesh.loops,'vertex_index','i',1),(mesh.polygons,'loop_total','i',1),(mesh.polygons,'material_index','i',1)):
                    a=array(kind,[0])*(len(coll)*n);coll.foreach_get(field,a);mh.update(memoryview(a));del a
                for uv in mesh.uv_layers:
                    a=array('f',[0])*(len(uv.data)*2);uv.data.foreach_get('uv',a);mh.update(uv.name.encode());mh.update(memoryview(a));del a
                mh.update(repr(tuple(m.name if m else None for m in mesh.materials)).encode());mesh_hashes[mesh.name]=mh.hexdigest()
            h.update(mesh_hashes[mesh.name].encode())
        result[p.stem]={'counts':r['counts'],'scene_digest':h.hexdigest(),'mesh_datablocks':len(mesh_hashes)}
    return result
before=snapshot();ids=set(new_ids())
try:reconstruct(project,paths,True);raise AssertionError('Duplicate set accepted')
except ValueError as exc:assert 'already imported' in str(exc)
assert set(new_ids())==ids
bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out));assert bpy.context.scene.camera.name=='User Camera' and bpy.context.scene.world.name=='User World';assert snapshot()==before
result=dict(levels=before,redirectors=aliases,objects=sum(x['counts']['objects'] for x in before.values()),meshes=sum(x['counts']['meshes'] for x in before.values()),armatures=sum(x['counts']['armatures'] for x in before.values()),reopen=True,duplicate_refusal=True,world_camera_preserved=True,scope='All six available original maps in one independent level set. Missing assets remain unresolved; no streaming composition or render parity.')
out.with_suffix('.json').write_text(json.dumps(result,indent=2));print('WHOLE_PROJECT_PASS',result,flush=True)
