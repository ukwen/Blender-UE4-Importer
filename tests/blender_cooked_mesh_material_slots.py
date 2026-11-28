"""Original cooked meshes, slot bindings, preview and rollback with legacy blocked."""
import importlib.abc,json,os,shutil,sys,tempfile
from pathlib import Path
from unittest.mock import patch
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
CORE={'uasset','umesh','umat','umap'};attempts=[]
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[-1] in CORE:
            attempts.append(fullname);raise ImportError(fullname)
sys.meta_path.insert(0,Block())
from asset_entrypoints import import_mesh,register
from project_session import new_ids
bpy.ops.wm.read_factory_settings(use_empty=True);register()
rows=[]
with tempfile.TemporaryDirectory() as tmp:
    for profile in ('4.18','4.27','5.0'):
        root=Path(tmp)/profile;root.mkdir();(root/'Worm.uproject').write_text('{}');content=root/'Content'
        shutil.copytree(Path(os.environ['MATYA_ASSETS'])/profile,content)
        for stem in ('SM_Worm','SK_Worm'):
            path=content/(stem+'.uasset');before=set(bpy.data.objects)
            assert getattr(bpy.ops,'import').umesh(filepath=str(path),materials=True,cooked_profile=profile,allow_cooked_preview=True)=={'FINISHED'}
            obj,=[o for o in set(bpy.data.objects)-before if o.type=='MESH'];mesh=obj.data
            assert (len(mesh.vertices),len(mesh.polygons))==(640,572)
            assert [p.material_index for p in mesh.polygons]==[v.value for v in mesh.attributes['UE_source_material_index'].data]
            mat=mesh.materials[0];assert mat['UE_material_package']=='/Game/M_Worm' and obj['UE_unresolved_material']
            report=json.loads(obj['UE_material_report'])['/Game/M_Worm'];status='partial_surface_preview' if profile=='4.18' else 'shader_unresolved'
            assert report['status']==mat['UE_material_status']==status
            assert len(report['dependencies'][0]['textures'])==3
            assert len([n for n in mat.node_tree.nodes if n.type=='TEX_IMAGE' and n.image and n.image.packed_file])==(6 if profile=='4.18' else 3)
            if profile=='4.18':assert len(mat.node_tree.links)==14 and mesh.uv_layers.get('UV0')
            else:assert not mat.node_tree.links
            if stem.startswith('SK'):assert len(obj.parent.data.bones)==6 and obj.modifiers[0].object==obj.parent
            rows.append(dict(profile=profile,asset=stem,name=obj.name,status=status,links=len(mat.node_tree.links)))
        path=content/'SM_Worm.uasset';raw,=import_mesh(path,True,False,profile)
        assert raw.data.materials[0]['UE_material_status']=='shader_unresolved' and not raw.data.materials[0].node_tree.links
        count=len(bpy.data.images);disabled,=import_mesh(path,False,False,profile,True)
        assert not disabled.get('UE_material_report') and len(bpy.data.images)==count
        before=set(new_ids())
        with patch('cooked_mesh_materials.import_cooked_material',side_effect=RuntimeError('injected')):
            try:import_mesh(path,True,False,profile,True)
            except RuntimeError as exc:assert str(exc)=='injected'
            else:raise AssertionError('expected failure')
        assert set(new_ids())==before
        # Controlled multi-slot mapping, with one genuine material reference and one unbound slot.
        from cooked_mesh_materials import CookedSlotResolver
        from material_stage import bind_native_mesh_slots
        from project_paths import ProjectPaths
        controlled=disabled.data
        controlled['UE_material_bindings']=json.dumps([['source','/Game/M_Worm'],['unbound','']])
        for i,v in enumerate(controlled.attributes['UE_source_material_index'].data):v.value=i%2
        resolver=CookedSlotResolver(ProjectPaths(path),profile)
        bind_native_mesh_slots(controlled,resolver)
        assert len(controlled.materials)==2 and [p.material_index for p in controlled.polygons]==[i%2 for i in range(572)]
        assert resolver.resolve('/Game/M_Worm','source')==controlled.materials[0] and controlled.materials[1]['UE_unresolved_material']
        (content/'T_Worm_N.uasset').unlink();missing_texture,=import_mesh(path,True,False,profile,True)
        dep=json.loads(missing_texture['UE_material_report'])['/Game/M_Worm']
        assert dep['status']=='shader_unresolved' and any(t['status']=='unresolved' and t['package']=='/Game/T_Worm_N' for t in dep['dependencies'][0]['textures'])
        (content/'M_Worm.uasset').unlink();missing,=import_mesh(path,True,False,profile,True)
        assert not missing.data.materials[0].use_nodes and 'unavailable' in json.loads(missing['UE_material_report'])['/Game/M_Worm']['detail']
    out=Path(os.environ['UE_COOKED_SLOT_OUTPUT']);bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out))
    for row in rows:
        obj=bpy.data.objects[row['name']];mat=obj.data.materials[0]
        assert mat['UE_material_status']==row['status'] and len(mat.node_tree.links)==row['links']
        assert [p.material_index for p in obj.data.polygons]==[v.value for v in obj.data.attributes['UE_source_material_index'].data]
        assert all(n.image.packed_file for n in mat.node_tree.nodes if n.type=='TEX_IMAGE')
        if row['asset'].startswith('SK'):assert obj.modifiers[0].object==obj.parent
assert not attempts and CORE.isdisjoint(sys.modules)
print('COOKED_MESH_MATERIAL_SLOTS_PASS',json.dumps(rows),flush=True)
