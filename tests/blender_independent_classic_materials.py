"""Original Goblin material chain, local function, packed textures and map integration."""
import hashlib,importlib.abc,json,os,sys
from pathlib import Path
import bpy
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
CORE={'uasset','umesh','umat','umap'};attempts=[]
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname,path=None,target=None):
        if fullname.split('.')[-1] in CORE:attempts.append(fullname);raise ImportError('Inherited importer prohibited: '+fullname)
assert not CORE.intersection(sys.modules);sys.meta_path.insert(0,Block())
from asset_entrypoints import import_material
from material_stage import MaterialResolver
from project_paths import ProjectPaths
from static_scene import reconstruct_static_map
from wind_preview import add_preview
from shader_texture_binding import assign_image
from generated_shader_groups import get
bpy.ops.wm.read_factory_settings(use_empty=True)
project=Path(os.environ['UE_CLASSIC_MATERIAL_PROJECT']);content=project.parent/'Content';out=Path(os.environ['UE_CLASSIC_MATERIAL_OUTPUT']);manifest=json.loads((ROOT/'docs/CLASSIC_MATERIAL_FIXTURES.json').read_text());reference=json.loads((ROOT/'docs/CLASSIC_WIND522_BASELINE.json').read_text());tex_ref=json.loads((ROOT/'docs/CLASSIC_TEXTURE522_BASELINE.json').read_text())
for name,row in manifest.items():assert hashlib.sha256((content/(row['package'][6:]+'.uasset')).read_bytes()).hexdigest()==row['sha256']
records={};surface={'BaseColor','Metallic','Roughness','Normal','EmissiveColor'}
for name,expected in reference.items():
    p=content/(manifest[name+'.uasset']['package'][6:]+'.uasset');mat=import_material(p,True);assert mat['UE_editor_material_status']=='partial';assert set(json.loads(mat['UE_editor_connected_outputs']))==surface
    assert json.loads(mat['UE_wind_profile'])==expected
    images={n.image.name+'.uasset':hashlib.sha256(n.image.packed_file.data).hexdigest() for n in mat.node_tree.nodes if n.type=='TEX_IMAGE' and n.image};assert images=={n:r['sha256'] for n,r in tex_ref.items()}
    records[mat.name]={'outputs':sorted(surface),'images':images,'wind':expected,'status':'partial'}
strict=import_material(p,False);assert strict['UE_editor_material_status']=='metadata_only' and not any(l.to_node.type=='BSDF_PRINCIPLED' for l in strict.node_tree.links)
# Actual original map; three available geometry records, two with source wind.
map_path=content/'FixtureMaps/Overview.umap'
collection,report=reconstruct_static_map(str(map_path),materials=True,allow_partial_materials=True)
assert report['actor_status']=={'missing':559,'reconstructed':3},report['actor_status']
objects=[o for o in collection.objects if o.type=='MESH' and 'UE_wind_profile' in o.material_slots[0].material];assert len(objects)==2
scene=bpy.context.scene;scene.render.fps=24;scene.render.fps_base=1
for o in objects:
    mod,w=add_preview(o);assert max(w)==0 and len(o.modifiers)==1
    source=[v.co.copy() for v in o.data.vertices]
    for frame in (1,13,25,37):
        scene.frame_set(frame);bpy.context.view_layer.update();ev=o.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=ev.to_mesh()
        try:assert max((a.co-b).length for a,b in zip(mesh.vertices,source))<1e-7
        finally:ev.to_mesh_clear()
# Shared texture binding only updates owned generated normal groups.
tree=bpy.data.materials.new('CONTROLLED texture binding').node_tree
m=bpy.data.materials['CONTROLLED texture binding'];m.use_nodes=True;tree=m.node_tree
n=tree.nodes.new('ShaderNodeTexImage');normal=tree.nodes.new('ShaderNodeGroup');normal.node_tree=get('RGBtoNormalY-');tree.links.new(n.outputs['Color'],normal.inputs[0]);im=next(i for i in bpy.data.images if i.name=='T_PolygonGoblinWarCamp_Normals_01');assign_image(n,im);assert normal.node_tree.get('UI_group_key')=='RGBtoNormal';bpy.data.materials.remove(m)
packed={i.name:hashlib.sha256(i.packed_file.data).hexdigest() for i in bpy.data.images if i.packed_file};assert len(packed)==3
scene.frame_set(1);bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out))
assert packed=={i.name:hashlib.sha256(i.packed_file.data).hexdigest() for i in bpy.data.images if i.packed_file}
for name,r in records.items():assert json.loads(bpy.data.materials[name]['UE_wind_profile'])==r['wind']
assert not attempts and not CORE.intersection(sys.modules),(attempts,CORE.intersection(sys.modules))
out.with_suffix('.json').write_text(json.dumps(dict(records=records,actor_status=report['actor_status'],wind_preview_objects=len(objects),packed_images=packed,zero_inherited_imports=True,reopen=True),indent=2));print('CLASSIC_MATERIALS_PASS',len(records),len(objects),flush=True)
