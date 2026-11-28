"""Cold registration, direct static-file import, exact payload parity and reopen.
Run in a fresh Blender process with original Goblin fixture Content and Western
project variables. Baseline hashes are from the previous accepted 0.10.103 mesh
builder; Blender version 4.2.4. No fixture bytes are stored in source.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import importlib.abc
import bpy

ROOT=Path(__file__).resolve().parents[1]
CORE={'uasset','umesh','umat','umap'}
assert not CORE.intersection(sys.modules)
attempts=[]
class Prohibit(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[-1] in CORE:
            attempts.append(fullname)
            raise ImportError('Inherited importer prohibited: '+fullname)
block=Prohibit();sys.meta_path.insert(0,block)

def digest(mesh):
    def seq(x):return [float(v) for v in x]
    data=dict(vertices=[seq(v.co) for v in mesh.vertices],faces=[list(p.vertices) for p in mesh.polygons],uv={l.name:[seq(d.uv) for d in l.data] for l in mesh.uv_layers},normals=[seq(n.vector) for n in mesh.corner_normals],props={k:json.loads(json.dumps(mesh[k],default=lambda x:list(x))) for k in mesh.keys() if k!='UAsset'},attrs={a.name:[seq(v.vector) if hasattr(v,'vector') else seq(v.color) if hasattr(v,'color') else v.value for v in a.data] for a in mesh.attributes if a.name.startswith('UE_') or a.name=='Color'})
    return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()

bpy.ops.wm.read_factory_settings(use_empty=True)
spec=importlib.util.spec_from_file_location('ue_importer_dev',ROOT/'__init__.py',submodule_search_locations=[str(ROOT)])
addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon)
addon.register()
try:
    for name in ('umap','umesh','umat'):
        assert getattr(getattr(bpy.ops,'import'),name).get_rna_type().properties.get('files') is not None
    expected=json.loads((ROOT/'docs/EDITOR_STATIC522_BASELINE.json').read_text())
    root=Path(os.environ['UE_STATIC522_FIXTURES']);records={}
    for name,sha in expected.items():
        path=next(root.rglob(name))
        before=set(bpy.data.objects)
        assert getattr(bpy.ops,'import').umesh(filepath=str(path),materials=False,all_lods=True)=={'FINISHED'}
        obj,=set(bpy.data.objects)-before
        assert obj.type=='MESH' and obj.data.name.endswith('_LOD0')
        actual=digest(obj.data);assert actual==sha,(name,actual,sha)
        records[name]={'object':obj.name,'sha256':actual,'vertices':len(obj.data.vertices),'triangles':len(obj.data.polygons)}
    western=Path(os.environ['UE_WESTERN_PROJECT']);path=next(western.rglob('SM_*.uasset'))
    before=set(bpy.data.objects);assert getattr(bpy.ops,'import').umesh(filepath=str(path),materials=False)=={'FINISHED'}
    obj,=set(bpy.data.objects)-before;assert len(obj.data.vertices)>0 and len(obj.data.polygons)>0
    matpath=next(western.rglob('Mat_PolygonWesternFrontier_01_A.uasset'))
    before=set(bpy.data.materials);assert getattr(bpy.ops,'import').umat(filepath=str(matpath))=={'FINISHED'}
    mat,=set(bpy.data.materials)-before
    assert mat['UE_classic_material_profile']=='typed_508_basic_surface'
    from material_stage import incomplete_graph,connected_surface
    assert connected_surface(mat.node_tree) and not incomplete_graph(mat.node_tree)
    material=mat.name
    packed={i.name:hashlib.sha256(i.packed_file.data).hexdigest() for i in bpy.data.images if i.packed_file}
    assert packed
    out=Path(os.environ['UE_ENTRYPOINT_OUTPUT']);bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out))
    for row in records.values():assert digest(bpy.data.objects[row['object']].data)==row['sha256']
    assert bpy.data.materials[material]['UE_classic_material_profile']=='typed_508_basic_surface'
    assert packed=={i.name:hashlib.sha256(i.packed_file.data).hexdigest() for i in bpy.data.images if i.packed_file}
    assert not attempts and not CORE.intersection(sys.modules),(attempts,CORE.intersection(sys.modules))
    out.with_suffix('.json').write_text(json.dumps(dict(records=records,classic508=path.name,material=material,packed_images=packed,zero_inherited_imports=True,reopened=True),indent=2))
finally:
    addon.unregister()
# Verify repeat enable/disable in the same process, still without inherited imports.
addon.register();addon.unregister();assert not attempts and not CORE.intersection(sys.modules)
print('INDEPENDENT_ENTRYPOINTS_PASS',len(records),flush=True)
