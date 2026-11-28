"""Original Western Frontier material+geometry acceptance without the four inherited imports."""
import bpy,sys,os,hashlib,json,importlib.abc
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
forbidden={'uasset','umesh','umat','umap'};attempts=[]
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname in forbidden:
            attempts.append(fullname);raise ImportError('Inherited module prohibited: '+fullname)
sys.meta_path.insert(0,Block());assert forbidden.isdisjoint(sys.modules)
from static_scene import reconstruct_static_map
from legacy_full_scene import inventory
from texture_blender import load_editor_texture
from editor_texture import read_editor_texture
from material_stage import incomplete_graph,connected_surface
from package_records import read_package
root=Path(os.environ['UE_WESTERN_PROJECT']).resolve();out=os.environ['UE_WESTERN_OUTPUT'];report_path=os.environ['UE_WESTERN_REPORT']
bpy.ops.wm.read_factory_settings(use_empty=True)
reports={};bindings={};rig_count=0;materials=set();lights=[]
for path in sorted(root.rglob('*.umap')):
    inv,lighting,skips=inventory(path,root/'Content');lights.extend(lighting)
    c,r=reconstruct_static_map(str(path),materials=True,allow_partial_materials=False,components=True);m=r['material_report'];reports[path.stem]=r
    print('MATERIAL_REPORT',path.stem,{k:(v['status'],v['errors']) for k,v in m['packages'].items()},flush=True)
    assert not m['errors'] and all(x['status']=='graph_imported_unverified' for x in m['packages'].values()),m
    assert m['bound_meshes']==(230 if path.stem=='Demonstration' else 352)
    assert r['actor_status']==({'reconstructed':1994,'missing':1} if path.stem=='Demonstration' else {'reconstructed':322,'missing':1})
    assert r['foliage_report']['instances']==(462 if path.stem=='Demonstration' else 0)
    assert r['component_report']['status']['reconstructed']==(6 if path.stem=='Demonstration' else 30)
    for o in c.objects:
        if o.type!='MESH':continue
        assert o.material_slots and all(s.material and not s.material.get('UE_unresolved_material',False) for s in o.material_slots),o.name
        for s in o.material_slots:
            mat=s.material;assert mat.get('UE_classic_material_profile')=='typed_508_basic_surface',mat.name
            assert mat.node_tree and not incomplete_graph(mat.node_tree) and connected_surface(mat.node_tree),mat.name
            materials.add(mat['UE_material_package'])
        a=o.data.attributes.get('UE_source_material_index')
        if a is not None:assert all(p.material_index==v.value for p,v in zip(o.data.polygons,a.data)),o.name
        source=json.loads(o.data['UE_material_bindings']);overrides=json.loads(o.get('UE_material_override_packages','[]'))
        effective=[overrides[i] if i<len(overrides) and overrides[i] else pkg for i,(slot,pkg) in enumerate(source)]
        assert effective==[s.material['UE_material_package'] for s in o.material_slots],o.name
        bindings[o.name]=effective
        if o.parent and o.parent.type=='ARMATURE':rig_count+=1;assert o.modifiers[0].object==o.parent
    if path.stem=='Overview':c.hide_viewport=True;c.hide_render=True
    print('INDEPENDENT_MAP_PASS',path.stem,m['bound_meshes'],len(m['packages']),flush=True)
assert rig_count==36
images={i.name:hashlib.sha256(i.packed_file.data).hexdigest() for i in bpy.data.images if i.packed_file}
assert len(images)==5
bpy.ops.wm.save_as_mainfile(filepath=out);bpy.ops.wm.open_mainfile(filepath=out)
assert len([o for o in bpy.data.objects if o.type=='ARMATURE'])==36
assert images=={i.name:hashlib.sha256(i.packed_file.data).hexdigest() for i in bpy.data.images if i.packed_file}
for name,expected in bindings.items():assert expected==[s.material['UE_material_package'] for s in bpy.data.objects[name].material_slots]
textures=[]
for path in sorted(root.rglob('*.uasset')):
    if 'Textures' not in path.parts:continue
    _,_,table=read_package(path)
    if not any(e.kind=='Texture2D' for e in table.exports):continue
    png,meta=read_editor_texture(path);image=load_editor_texture(path)
    assert tuple(image.size)==(meta['width'],meta['height']) and image.packed_file
    digest=hashlib.sha256(png).hexdigest();assert digest==hashlib.sha256(image.packed_file.data).hexdigest()
    textures.append(dict(path=path.relative_to(root).as_posix(),sha256=digest,metadata=meta))
assert len(textures)==14 and forbidden.isdisjoint(sys.modules) and not attempts,attempts
Path(report_path).write_text(json.dumps(dict(levels=reports,source_textures=textures,packed_scene_images=images,verified_mesh_objects=len(bindings),verified_skeletal_actors=rig_count,materials=sorted(materials),inventory_lights=lights,inherited_imports_blocked=True,reopen='passed'),indent=2))
print('INDEPENDENT_WESTERN_PASS',len(bindings),rig_count,len(textures),len(images),len(materials),flush=True)
