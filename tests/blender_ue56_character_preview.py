import sys,os,json
from pathlib import Path
import bpy
from mathutils import Matrix,Vector
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ue5_editor_components import character_defaults,build_character_preview
import skeleton_blender
root=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content';out=Path(os.environ['UE56_CHARACTER_OUTPUT']);bpy.ops.wm.read_factory_settings(use_empty=True);skeleton_blender.register();report=[]
for name,vertices,z in [('BP_ThirdPersonCharacter',43761,-.89),('BP_CombatEnemy',46098,-.90)]:
    p=next(root.rglob(name+'.uasset'));before=set(bpy.data.objects);assert getattr(bpy.ops,'import').ue_editor_character(filepath=str(p),materials=True,partial=True,sockets=True)=={'FINISHED'};objs=set(bpy.data.objects)-before;arm=next(o for o in objs if o.type=='ARMATURE');mesh=next(o for o in objs if o.type=='MESH');anchor=arm.parent;assert mesh.parent==arm and len(mesh.data.vertices)==vertices and len(arm.data.bones)==89 and len([o for o in arm.children if o.get('UE_socket_name')])==4
    assert abs(arm.location.z-z)<1e-6 and abs(arm.rotation_euler.z-1.57079632679)<1e-6;textures=[n for s in mesh.material_slots for n in s.material.node_tree.nodes if n.type=='TEX_IMAGE'];print('CHARACTER_TEXTURES',name,[(n.get('UE_texture_package'),bool(n.image and n.image.packed_file)) for n in textures],flush=True);assert len(textures)==(6 if name=='BP_ThirdPersonCharacter' else 7) and all(n.image and n.image.packed_file and n.get('UE_texture_package') for n in textures)
    masks=[s.material for s in mesh.material_slots if s.material and s.material.get('UE_surface_preview')=='masked'];assert masks,[(s.material.name,s.material.get('UE_editor_material_issues')) for s in mesh.material_slots if s.material];assert all(any(n.get('UE_first_person_preview') and n.outputs[0].default_value==0 for n in m.node_tree.nodes) for m in masks);report.append(dict(name=name,vertices=vertices,sockets=4,body_z=arm.location.z,masked_slots=len(masks),packed_texture_nodes=len(textures)));anchor.location.x=len(report)*2
before=set(bpy.data.objects)
try:build_character_preview(next(root.rglob('BP_ShooterCharacter.uasset')))
except ValueError:pass
else:raise AssertionError('Missing original body silently substituted')
assert set(bpy.data.objects)==before
bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out));assert len([o for o in bpy.data.objects if o.get('UE_socket_name')])==8 and len([o for o in bpy.data.objects if o.get('UE_blueprint_package')])==2
assert all(any(s.material and s.material.get('UE_surface_preview')=='masked' for s in o.material_slots) for o in bpy.data.objects if o.type=='MESH');out.with_suffix('.json').write_text(json.dumps(report,indent=2));print('CHARACTER_PREVIEW_REOPEN_PASS',report,flush=True)
