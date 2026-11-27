"""Genuine UE5.0 and UE5.5 material packages and matching source textures."""
import os,sys,json
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from project_geometry import import_geometry_folder
from cooked_material_dependencies import inspect_asset
from texture_blender import load_native_texture
bpy.ops.wm.read_factory_settings(use_empty=True)
results={}
for profile,env,expected in [('5.0','UE53_WORM_PROJECT',{'/Game/T_Worm_A','/Game/T_Worm_D','/Game/T_Worm_N'}),('5.5','UE53_MODERN_PROJECT',{'/Game/Textures/T_Test'})]:
    coll,report=import_geometry_folder(os.environ[env],profile=profile)
    assert report['counts'].get('reconstructed')== (2 if profile=='5.0' else 1),report
    objects=[o for o in coll.all_objects if o.type=='MESH']; mats=[m for o in objects for m in o.data.materials]
    refs=set()
    for mat in mats:
        data=json.loads(mat['UE_cooked_material_dependencies']);assert mat['UE_unresolved_material']
        for dep in data:
            for t in dep['textures']:
                assert t['status']=='packed_raw_channels',t;refs.add(t['package'])
        nodes=[n for n in mat.node_tree.nodes if n.get('UE_texture_dependency_status')]
        if not nodes:
            assert profile=='5.5' and data[0]['package']=='/Game/Meshes/M_Cube_2' and data[0]['status']=='unresolved'
            continue
        assert nodes and all(n.image and n.image.packed_file and not any(s.is_linked for s in n.outputs) for n in nodes),(profile,mat.name,data,[(n.name,n.image) for n in nodes])
    assert refs==expected,(profile,refs)
    images=[i for i in bpy.data.images if i.get('UE_texture_package') in expected]
    assert len(images)==len(expected) and all(i.colorspace_settings.name=='Non-Color' for i in images)
    results[profile]=dict(material_slots=len(mats),unique_source_textures=len(images),packages=sorted(refs),image_bytes=sum(len(i.packed_file.data) for i in images),shader_status='unresolved')
# A real package copied into the wrong target cannot satisfy the source identity.
p=Path(os.environ['UE53_WORM_PROJECT']).parent/'Content'/'T_Worm_A.uasset'
try:inspect_asset(p,'5.0','/Game/T_Worm_D');raise AssertionError('wrong texture accepted')
except ValueError:pass
out=os.environ['UE53_MATERIAL_OUTPUT'];bpy.ops.wm.save_as_mainfile(filepath=out);bpy.ops.wm.open_mainfile(filepath=out)
images=[i for i in bpy.data.images if i.get('UE_raw_texture_key')];assert len(images)==4 and all(i.packed_file for i in images)
assert len({i['UE_raw_texture_key'] for i in images})==4
for m in bpy.data.materials:
    if m.get('UE_cooked_material_dependencies'):
        assert all(n.image and n.image.packed_file for n in m.node_tree.nodes if n.get('UE_texture_dependency_status')=='packed_raw_channels')
Path(os.environ['UE53_MATERIAL_REPORT']).write_text(json.dumps(dict(profiles=results,packed_images=4,save_reopen=True,wrong_identity_rejected=True),indent=2))
print('COOKED_MATERIAL_DEPENDENCIES_PASS',results,flush=True)
