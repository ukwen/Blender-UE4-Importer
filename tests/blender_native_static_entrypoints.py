"""Native material-bearing static menu and controlled LOD traversal, with inherited imports blocked."""
import hashlib,importlib.abc,json,os,sys
from pathlib import Path
from unittest.mock import patch
import bpy
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
CORE={'uasset','umesh','umat','umap'};attempts=[]
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname,path=None,target=None):
        if fullname.split('.')[-1] in CORE:attempts.append(fullname);raise ImportError('Inherited importer prohibited: '+fullname)
assert not CORE.intersection(sys.modules);sys.meta_path.insert(0,Block())
from asset_entrypoints import import_mesh,register,unregister
from editor_static522 import read_static_lods,read_source_models
from test_static522_lods import controlled
from skeleton_native import Reader
from project_session import new_ids
bpy.ops.wm.read_factory_settings(use_empty=True);register()
west=Path(os.environ['UE_WESTERN_PROJECT']); goblin=Path(os.environ['UE_GOBLIN_PROJECT']).parent; modern=Path(os.environ['UE56_EDITOR_PROJECT']).parent
cases=[(next(west.rglob('SM_Prop_Lantern_01.uasset')),'graph_imported_unverified'),(next(goblin.rglob('SM_Chr_Attach_Straw_01.uasset')),'partial_graph_unresolved'),(next(modern.rglob('SM_Door.uasset')),None)]
records=[]
for path,status in cases:
    before=set(bpy.data.objects)
    assert getattr(bpy.ops,'import').umesh(filepath=str(path),materials=True)=={'FINISHED'}
    o,=set(bpy.data.objects)-before;m=o.data;bindings=json.loads(m['UE_material_bindings']);assert len(bindings)==len(m.materials)>0
    assert all(mat['UE_material_package']==pkg for mat,(_,pkg) in zip(m.materials,bindings))
    assert all(0<=p.material_index<len(bindings) for p in m.polygons)
    if path.name=='SM_Prop_Lantern_01.uasset':
        from legacy_static import read_legacy_static_path
        source=read_legacy_static_path(path)
        assert len(bindings)==2 and {p.material_index for p in m.polygons}=={0,1}
        assert [p.material_index for p in m.polygons]==[source['sections'][i][0] for i in source['slots']]
    report=json.loads(o['UE_material_report']);assert report
    if status:assert status in {r['status'] for r in report.values()},report
    records.append(dict(name=o.name,vertices=len(m.vertices),triangles=len(m.polygons),bindings=bindings,indices=[p.material_index for p in m.polygons],statuses={p:r['status'] for p,r in report.items()}))
# Exercise the production builder and visibility with controlled LOD sequence using actual Rope payload.
rope=Path(os.environ['UE_STATIC522_FIXTURES'])/'SM_Prop_Rope_01.uasset';d,=read_static_lods(rope);block,raw,base,end=controlled(rope)
models,missing=read_source_models(Reader(block+bytes(4)+block),raw,base,end,3)
rows=[dict(d,geometry=g,lod_index=i,lod_count=3,missing_lods=missing) for i,g in models]
with patch('editor_static522.read_static_lods',return_value=rows):
    objects=import_mesh(rope,False,True)
    assert [o.data['UE_lod_index'] for o in objects]==[0,2]
    assert not objects[0].hide_get() and objects[1].hide_get() and objects[1].hide_render
    assert all(json.loads(o.data['UE_missing_source_lods'])==[1] for o in objects)
    primary,=import_mesh(rope,False,False);assert primary.data['UE_lod_index']==0
# Failure after geometry creation must roll back every new Blender ID.
before=set(new_ids())
with patch('material_stage.bind_native_mesh_slots',side_effect=ValueError('injected slot failure')):
    try:import_mesh(cases[0][0],True,False);raise AssertionError('failure not propagated')
    except ValueError as e:assert 'injected slot failure' in str(e)
assert set(new_ids())==before
packed={i.name:hashlib.sha256(i.packed_file.data).hexdigest() for i in bpy.data.images if i.packed_file};assert packed
out=Path(os.environ['UE_NATIVE_STATIC_OUTPUT']);bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out))
for row in records:
    m=bpy.data.objects[row['name']].data;assert [p.material_index for p in m.polygons]==row['indices'];assert json.loads(m['UE_material_bindings'])==row['bindings']
assert packed=={i.name:hashlib.sha256(i.packed_file.data).hexdigest() for i in bpy.data.images if i.packed_file}
assert not attempts and not CORE.intersection(sys.modules),(attempts,CORE.intersection(sys.modules))
unregister();out.with_suffix('.json').write_text(json.dumps(dict(original_assets=records,controlled_lods=[0,2],missing_lods=[1],packed_images=packed,rollback=True,reopen=True,zero_inherited_imports=True),indent=2));print('NATIVE_STATIC_ENTRYPOINTS_PASS',flush=True)
