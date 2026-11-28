"""Exercise the actual legacy-free geometry route and save/reopen all original static meshes."""
import builtins,json,os,sys
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from project_geometry import load_static,root_class
from package_records import read_package
root=Path(os.environ['UE_WESTERN_PROJECT']);out=Path(os.environ['UE_WESTERN_OUTPUT'])
original=builtins.__import__
def guard(name,*a,**k):
    if name.split('.')[0] in ('uasset','umesh','umat','umap'):raise AssertionError('Inherited importer loaded: '+name)
    return original(name,*a,**k)
builtins.__import__=guard
bpy.ops.wm.read_factory_settings(use_empty=True)
objects=[]
for path in sorted(root.rglob('*.uasset')):
    _,_,table=read_package(path)
    if not any(e.kind=='StaticMesh' and not e.outer for e in table.exports):continue
    assert root_class(path,None)=='StaticMesh'
    mesh=load_static(path,None,'4.27');obj=bpy.data.objects.new(mesh.name,mesh);bpy.context.scene.collection.objects.link(obj)
    objects.append(obj.name)
assert len(objects)==325
result={'objects':len(objects),'vertices':sum(len(bpy.data.objects[n].data.vertices) for n in objects),'triangles':sum(len(bpy.data.objects[n].data.polygons) for n in objects),'split_faces':sum(bpy.data.objects[n].data['UE_duplicate_faces_split'] for n in objects)}
assert (result['vertices'],result['triangles'],result['split_faces'])==(130412,228484,16)
bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out))
assert len(bpy.context.scene.objects)==325
assert all(bpy.data.objects[n].data['UE_source_format']=='UE4.14 FRawMesh' for n in objects)
result['reopen']=True;out.with_suffix('.json').write_text(json.dumps(result,indent=2));print('EDITOR508_PASS',result,flush=True)
