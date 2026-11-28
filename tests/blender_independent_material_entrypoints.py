"""Original standalone UE4/UE5 material imports with inherited modules forbidden."""
import hashlib, importlib.abc, json, os, shutil, sys, tempfile
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
CORE={'uasset','umesh','umat','umap'}; attempts=[]
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[-1] in CORE:
            attempts.append(fullname);raise ImportError('Inherited importer prohibited: '+fullname)
assert not CORE.intersection(sys.modules)
sys.meta_path.insert(0,Block())
from asset_entrypoints import register, unregister, import_material
from project_session import new_ids
from material_stage import MaterialResolver
from project_paths import ProjectPaths
bpy.ops.wm.read_factory_settings(use_empty=True);register()
root=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content';out=Path(os.environ['UE_MATERIAL_ENTRYPOINT_OUTPUT'])
def path(stem):return next(root.rglob(stem+'.uasset'))
def run(p,partial=False):
    before=set(bpy.data.materials)
    assert getattr(bpy.ops,'import').umat(filepath=str(p),allow_partial=partial)=={'FINISHED'}
    m,=set(bpy.data.materials)-before
    assert m.use_fake_user
    return m
records={}
for stem,partial in [('MI_ThirdPersonColWay',False),('MI_PrototypeGrid_TopDark',True),('MI_Quinn_01',False),('MI_Quinn_01',True)]:
    m=run(path(stem),partial);graph=json.loads(m['UE_editor_graph']);status=m['UE_editor_material_status'];outputs=json.loads(m['UE_editor_connected_outputs']);audit=json.loads(m['UE_parameter_audit'])
    if stem=='MI_ThirdPersonColWay':
        assert status=='supported_pbr_subset' and len(graph['chain'])==3
        bs=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED');assert abs(bs.inputs['Roughness'].links[0].from_socket.default_value-.268)<1e-6
    elif stem=='MI_PrototypeGrid_TopDark':
        a={v['name']:v for v in audit};assert len(a['TopSurfaceColor']['matched_nodes'])==3 and len(a['ObjectAligned']['matched_nodes'])==4
    elif not partial:
        assert status=='metadata_only' and not any(l.to_node.type=='BSDF_PRINCIPLED' for l in m.node_tree.links)
    else:
        assert status=='partial' and {'BaseColor','Metallic','Roughness','Normal'}<=set(outputs)
    records[m.name]=dict(status=status,chain=graph['chain'],outputs=outputs,partial=partial,issues=json.loads(m['UE_editor_material_issues']))
# The original 522 fixture is staged under a disposable Content root.
with tempfile.TemporaryDirectory() as tmp:
    project=Path(tmp);content=project/'Content';content.mkdir();(project/'Fixture.uproject').write_text('{}')
    p=content/'TestMaterial.uasset';shutil.copyfile(Path(os.environ['UASSETAPI_ASSETS'])/'TestEditorAssets/TestMaterial.uasset',p)
    m=run(p);assert m['UE_classic_material_profile']=='typed_522_basic_surface'
    bs=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED');assert bs.inputs['Base Color'].is_linked
    records[m.name]={'status':'typed_522_basic_surface'}
    resolver=MaterialResolver(ProjectPaths(p));m2=resolver.resolve('/Game/TestMaterial','Test');assert m2['UE_material_status']=='graph_imported_unverified'
    # A modern material relocated without its original dependency tree must fail
    # without leaking any new Blender IDs or invoking the inherited fallback.
    broken=content/'Broken.uasset';shutil.copyfile(path('MI_ThirdPersonColWay'),broken);before=set(new_ids())
    try:import_material(broken)
    except (ValueError,FileNotFoundError):pass
    else:raise AssertionError('Missing parent accepted')
    assert set(new_ids())==before
    # Also inject a failure after allocating IDs, testing rollback rather than
    # merely a pre-allocation failure. The fake is scoped to this controlled test.
    import ue5_editor_material
    original=ue5_editor_material.build_material
    def injected(*a,**k):
        bpy.data.materials.new('rollback_probe');raise ValueError('injected failure')
    ue5_editor_material.build_material=injected
    before=set(new_ids())
    try:
        try:import_material(path('MI_ThirdPersonColWay'))
        except ValueError as e:assert str(e)=='injected failure'
        else:raise AssertionError('Injected failure accepted')
        assert set(new_ids())==before
    finally:ue5_editor_material.build_material=original
packed={i.name:hashlib.sha256(i.packed_file.data).hexdigest() for i in bpy.data.images if i.packed_file};assert packed
bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out))
for n,d in records.items():
    m=bpy.data.materials[n];assert m.use_fake_user
    assert m.get('UE_editor_material_status',m.get('UE_classic_material_profile'))==d['status']
assert packed=={i.name:hashlib.sha256(i.packed_file.data).hexdigest() for i in bpy.data.images if i.packed_file}
assert not attempts and not CORE.intersection(sys.modules)
unregister();out.with_suffix('.json').write_text(json.dumps(dict(records=records,packed_images=packed,zero_inherited_imports=True,reopen=True,rollback=True),indent=2));print('MATERIAL_ENTRYPOINTS_PASS',len(records),len(packed),flush=True)
