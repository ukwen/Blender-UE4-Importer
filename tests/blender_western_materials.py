"""Strict material and texture acceptance on the original UE4.14 Western Frontier pack."""
import bpy, sys, pathlib, json, collections, os, hashlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from static_scene import reconstruct_static_map
from texture_blender import load_editor_texture
from editor_texture import read_editor_texture
from material_stage import incomplete_graph, connected_surface
from uasset import UAsset
root=pathlib.Path(os.environ['UE_WESTERN_PROJECT']).resolve()
output=os.environ['UE_WESTERN_OUTPUT']; report_path=os.environ['UE_WESTERN_REPORT']
bpy.ops.wm.read_factory_settings(use_empty=True)
reports={}; bindings={}; rig_count=0
for p in sorted(root.rglob('*.umap')):
    c,r=reconstruct_static_map(str(p),materials=True,allow_partial_materials=False,components=True)
    m=r['material_report']; reports[p.stem]=r
    assert not m['errors'] and all(x['status']=='graph_imported_unverified' for x in m['packages'].values()),m
    assert m['bound_meshes']==(230 if p.stem=='Demonstration' else 352)
    assert r['actor_status']==({'reconstructed':1994,'missing':1} if p.stem=='Demonstration' else {'reconstructed':322,'missing':1})
    assert r['foliage_report']['instances']==(462 if p.stem=='Demonstration' else 0)
    assert r['component_report']['status']['reconstructed']==(6 if p.stem=='Demonstration' else 30)
    for o in c.objects:
        if o.type!='MESH':continue
        assert o.material_slots and all(s.material and not s.material.get('UE_unresolved_material',False) for s in o.material_slots),o.name
        for s in o.material_slots:
            assert s.material.node_tree and not incomplete_graph(s.material.node_tree) and connected_surface(s.material.node_tree),s.material.name
        a=o.data.attributes.get('UE_source_material_index')
        if a is not None: assert all(p.material_index==v.value for p,v in zip(o.data.polygons,a.data)),o.name
        source=json.loads(o.data['UE_material_bindings']); overrides=json.loads(o.get('UE_material_override_packages','[]'))
        effective=[overrides[i] if i<len(overrides) and overrides[i] else package for i,(slot,package) in enumerate(source)]
        assert effective==[s.material['UE_material_package'] for s in o.material_slots],o.name
        bindings[o.name]=effective
        if o.parent and o.parent.type=='ARMATURE':
            rig_count+=1; assert o.modifiers[0].object==o.parent
    if p.stem=='Overview': c.hide_viewport=True;c.hide_render=True
    print('STRICT_MAP_PASS',p.stem,m['bound_meshes'],len(m['packages']),flush=True)
assert rig_count==36
images={i.name:hashlib.sha256(i.packed_file.data).hexdigest() for i in bpy.data.images if i.packed_file}
assert len(images)==5
# Save the actual map scene before loading unreferenced source textures.
bpy.ops.wm.save_as_mainfile(filepath=output);bpy.ops.wm.open_mainfile(filepath=output)
assert len([o for o in bpy.data.objects if o.type=='ARMATURE'])==36
assert images=={i.name:hashlib.sha256(i.packed_file.data).hexdigest() for i in bpy.data.images if i.packed_file}
for name,expected in bindings.items():
    assert expected==[s.material['UE_material_package'] for s in bpy.data.objects[name].material_slots]
textures=[]
for p in sorted(root.rglob('*.uasset')):
    if 'Textures' not in p.parts:continue
    with UAsset(str(p)) as a:
        if not any(e.export_class_type=='Texture2D' for e in a.exports):continue
    png,meta=read_editor_texture(p);im=load_editor_texture(p)
    assert tuple(im.size)==(meta['width'],meta['height']) and im.packed_file
    digest=hashlib.sha256(png).hexdigest();assert digest==hashlib.sha256(im.packed_file.data).hexdigest()
    textures.append(dict(path=p.relative_to(root).as_posix(),sha256=digest,metadata=meta))
assert len(textures)==14
pathlib.Path(report_path).write_text(json.dumps(dict(levels=reports,source_textures=textures,packed_scene_images=images,verified_mesh_objects=len(bindings),verified_skeletal_actors=rig_count,reopen='passed'),indent=2))
print('WESTERN_MATERIAL_ACCEPTANCE_PASS',len(bindings),rig_count,len(textures),len(images),flush=True)
