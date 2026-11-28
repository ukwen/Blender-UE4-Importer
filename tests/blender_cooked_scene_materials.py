"""Original cooked geometry/materials in a controlled map-style collection."""
import importlib.abc,json,os,shutil,sys,tempfile
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
CORE={'uasset','umesh','umat','umap'};attempts=[]
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[-1] in CORE:
            attempts.append(fullname);raise ImportError(fullname)
sys.meta_path.insert(0,Block())
from asset_entrypoints import import_mesh
from material_stage import bind_scene_materials
from project_paths import ProjectPaths
bpy.ops.wm.read_factory_settings(use_empty=True)
rows=[]
with tempfile.TemporaryDirectory() as tmp:
    for profile in ('4.18','4.27','5.0'):
        root=Path(tmp)/profile;root.mkdir();(root/'Worm.uproject').write_text('{}');content=root/'Content'
        shutil.copytree(Path(os.environ['MATYA_ASSETS'])/profile,content)
        c=bpy.data.collections.new(profile);bpy.context.scene.collection.children.link(c)
        for stem in ('SM_Worm','SK_Worm'):
            obj,=import_mesh(content/(stem+'.uasset'),False,False,profile)
            c.objects.link(obj)
        static=next(o for o in c.objects if not o.parent)
        other=static.copy();other.data=static.data.copy();c.objects.link(other)
        for uv in list(other.data.uv_layers): other.data.uv_layers.remove(uv)
        inst=static.copy();inst.data=static.data;c.objects.link(inst)
        inst['UE_material_override_packages']=json.dumps(['/Game/M_Worm'])
        report=bind_scene_materials(c,ProjectPaths(content/'SM_Worm.uasset'),True,profile)
        assert report['bound_meshes']==3 and not report['errors'],report
        statuses={o.name:o.material_slots[0].material['UE_material_status'] for o in c.objects if o.type=='MESH'}
        assert statuses[other.name]=='shader_unresolved'
        assert statuses[static.name]==('partial_surface_preview' if profile=='4.18' else 'shader_unresolved')
        assert inst.material_slots[0].link=='OBJECT' and inst.material_slots[0].material==static.material_slots[0].material
        assert len(report['packages'])==2,report
        for o in c.objects:
            if o.type!='MESH':continue
            assert [p.material_index for p in o.data.polygons]==[v.value for v in o.data.attributes['UE_source_material_index'].data]
            rows.append((o.name,statuses[o.name]))
        print('COOKED_SCENE_BINDING_PASS',profile,report['bound_meshes'],statuses,flush=True)
    out=Path(os.environ['UE_COOKED_SCENE_OUTPUT']);bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out))
    for name,status in rows:
        assert bpy.data.objects[name].material_slots[0].material['UE_material_status']==status
assert not attempts and CORE.isdisjoint(sys.modules),attempts
print('COOKED_SCENE_MATERIALS_PASS',len(rows),flush=True)
