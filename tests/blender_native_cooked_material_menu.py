"""Original cooked materials through standalone File > Import, no inherited modules."""
import hashlib, importlib.abc, json, os, shutil, sys, tempfile
from pathlib import Path
from unittest.mock import patch
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
CORE={'uasset','umap','umat','umesh'}; attempts=[]
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname in CORE:
            attempts.append(fullname);raise ImportError(fullname)
sys.meta_path.insert(0,Block());assert CORE.isdisjoint(sys.modules)
from asset_entrypoints import import_material, register, unregister
from project_session import new_ids
from native_texture import read_texture,decode_rgba,png_bytes
bpy.ops.wm.read_factory_settings(use_empty=True);register()
source=Path(os.environ['MATYA_ASSETS']); records={};images={};source_graph=None
with tempfile.TemporaryDirectory() as tmp:
    for profile in ('4.18','4.27','5.0'):
        project=Path(tmp)/profile;project.mkdir();(project/'Worm.uproject').write_text('{}');content=project/'Content';shutil.copytree(source/profile,content)
        path=content/'M_Worm.uasset';before=set(bpy.data.materials)
        assert getattr(bpy.ops,'import').umat(filepath=str(path),profile=profile)=={'FINISHED'}
        mat,=set(bpy.data.materials)-before;assert mat.use_fake_user and mat['UE_unresolved_material'] and mat['UE_material_status']=='shader_unresolved'
        assert not any(n.type in ('BSDF_PRINCIPLED','OUTPUT_MATERIAL') for n in mat.node_tree.nodes)
        dep,=json.loads(mat['UE_cooked_material_dependencies']);assert dep['status']=='typed_references_recovered'
        nodes=[n for n in mat.node_tree.nodes if n.type=='TEX_IMAGE'];assert len(nodes)==3
        assert {n['UE_texture_package'] for n in nodes}=={'/Game/T_Worm_A','/Game/T_Worm_D','/Game/T_Worm_N'}
        for n in nodes:
            assert n.image and n.image.packed_file and n.image.colorspace_settings.name=='Non-Color' and not any(s.is_linked for s in n.outputs)
            p=content/(n['UE_texture_package'].rsplit('/',1)[-1]+'.uasset');w,h,fmt,raw,count=read_texture(p,profile)
            assert bytes(n.image.packed_file.data)==png_bytes(w,h,decode_rgba(w,h,fmt,raw))
            images[n.image.name]=hashlib.sha256(n.image.packed_file.data).hexdigest()
        if profile=='4.18':
            graph=json.loads(mat['UE_cooked_source_edges']);source_graph=graph;assert graph['blend']=='BLEND_Translucent'
            assert {n['UE_texture_package']:json.loads(n['UE_cooked_source_inputs']) for n in nodes}=={'/Game/T_Worm_A':['Opacity'],'/Game/T_Worm_D':['BaseColor'],'/Game/T_Worm_N':['Normal']}
        records[mat.name]=profile
        # Dependency image reuse: no duplicate packed images for the same source revision.
        reused=import_material(path,profile=profile);assert {n.image.name for n in reused.node_tree.nodes if n.type=='TEX_IMAGE'}=={n.image.name for n in nodes}
        # Genuine wrong class, wrong identity, missing sidecar and implicit profile refusal.
        renamed=content/'Renamed.uasset';shutil.copyfile(path,renamed);shutil.copyfile(path.with_suffix('.uexp'),renamed.with_suffix('.uexp'))
        before=set(new_ids())
        for p,v in ((content/'SM_Worm.uasset',profile),(renamed,profile),(path,'NONE')):
            try:import_material(p,profile=v)
            except (ValueError,NotImplementedError):pass
            else:raise AssertionError('Invalid material accepted')
            assert set(new_ids())==before
        side=path.with_suffix('.uexp');saved=side.read_bytes();side.unlink()
        try:import_material(path,profile=profile)
        except OSError:pass
        else:raise AssertionError('Missing material sidecar accepted')
        assert set(new_ids())==before;side.write_bytes(saved)
        # Missing source is explicit; no substitute image from a prior import.
        (content/'T_Worm_D.uasset').unlink();missing=import_material(path,profile=profile)
        missing_node=next(n for n in missing.node_tree.nodes if n.get('UE_texture_package')=='/Game/T_Worm_D')
        assert missing_node.image is None and missing_node['UE_texture_dependency_status']=='unresolved'
        before=set(new_ids())
        with patch('cooked_material_catalog.recover_material_dependencies',side_effect=ValueError('injected')):
            try:import_material(path,profile=profile)
            except ValueError as e:assert str(e)=='injected'
            else:raise AssertionError('Injected error accepted')
        assert set(new_ids())==before
    out=Path(os.environ['UE_COOKED_MATERIAL_MENU_OUTPUT']);bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out))
    for n,v in records.items():
        m=bpy.data.materials[n];assert m['UE_cooked_profile']==v and len([n for n in m.node_tree.nodes if n.type=='TEX_IMAGE' and n.image])==3
        if v=='4.18':assert len(json.loads(m['UE_cooked_source_edges'])['edges'])==3
    assert images=={i.name:hashlib.sha256(i.packed_file.data).hexdigest() for i in bpy.data.images if i.packed_file}
assert not attempts and CORE.isdisjoint(sys.modules);unregister()
out.with_suffix('.json').write_text(json.dumps(dict(materials=records,packed_images=images,source_graph_418=source_graph,reopen=True,missing_dependency=True,rollback=True,inherited_import_attempts=attempts),indent=2));print('NATIVE_COOKED_MATERIAL_MENU_PASS',len(records),len(images),flush=True)
