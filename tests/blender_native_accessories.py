"""Genuine hood/body combinations from the map-resolved Blueprint references."""
import json,os,sys
from pathlib import Path
import bpy,numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from skeletal_mesh_native import read_native_mesh,build_mesh
from native_attachments import bind_compatible_accessory
from skeleton_blender import register,unregister
root=Path(os.environ['UE_CHARACTER_ASSETS']); bpy.ops.wm.read_factory_settings(use_empty=True)
report=json.loads(Path(os.environ['UE_CHARACTER_DEPENDENCIES']).read_text()); results=[]
for bp in report['blueprints']:
    bindings=bp['bindings']; body=bindings.get('Mesh')
    if not body: continue
    accessories=[v for k,v in bindings.items() if k!='Mesh' and v['class']=='SkeletalMeshComponent' and v['package']]
    for v in accessories:
        d=read_native_mesh(root/(v['package'].split('/')[-1]+'.uasset'),'4.27'); bd=read_native_mesh(root/(body['package'].split('/')[-1]+'.uasset'),'4.27')
        obj,arm=build_mesh(d); bodyobj,bodyrig=build_mesh(bd)
        def coords(o):
            bpy.context.view_layer.update(); return np.array([v.co[:] for v in o.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.vertices])
        rest=coords(obj); expected=[]
        poses=[('head',.35),('spine_03',-.25)]
        for name,angle in poses:
            pb=arm.pose.bones[name]; pb.rotation_mode='XYZ'; pb.rotation_euler.x=angle
            expected.append(coords(obj)); pb.rotation_euler.x=0
        bpy.ops.object.select_all(action='DESELECT'); obj.select_set(True); bodyrig.select_set(True); bpy.context.view_layer.objects.active=bodyrig
        register()
        try: assert bpy.ops.object.ue_bind_accessory()=={'FINISHED'}
        finally: unregister()
        assert obj.parent==bodyrig and obj.modifiers[0].object==bodyrig and arm.name in bpy.data.objects
        assert np.max(abs(coords(obj)-rest))<1e-6
        errors=[]; motions=[]
        for (name,angle),ref in zip(poses,expected):
            pb=bodyrig.pose.bones[name]; pb.rotation_mode='XYZ'; pb.rotation_euler.x=angle
            moved=coords(obj); errors.append(float(np.max(np.linalg.norm(moved-ref,axis=1)))); motions.append(float(np.max(np.linalg.norm(moved-rest,axis=1)))); pb.rotation_euler.x=0
        assert max(errors)<1e-6 and max(motions)>.001 and np.max(abs(coords(obj)-rest))<1e-6
        bodyrig.location.x=len(results)*2.; arm.hide_set(True); arm.hide_render=True
        bodyrig['UE_assembly_status']='reference_space_preview_not_blueprint_placement'
        results.append(dict(blueprint=bp['class'],accessory=v['package'],body=body['package'],error=max(errors),motion=max(motions)))
assert len(results)==2
# Refuse same skeleton package with different reference transform, preserving original binding.
for name in ('SK_Chr_King_02','SK_Chr_Troll_01'):
    obj,arm=build_mesh(read_native_mesh(root/'SK_Chr_Attach_Hood_01.uasset','4.27')); body,rig=build_mesh(read_native_mesh(root/(name+'.uasset'),'4.27'))
    try: bind_compatible_accessory(obj,rig)
    except ValueError as exc: assert 'Incompatible reference transform' in str(exc),str(exc)
    else: raise AssertionError('Incompatible rig accepted')
    assert obj.parent==arm and obj.modifiers[0].object==arm
    for o in (obj,arm,body,rig): bpy.data.objects.remove(o,do_unlink=True)
for store in (bpy.data.meshes,bpy.data.armatures,bpy.data.materials):
    for item in list(store):
        if not item.users: store.remove(item)
out=os.environ['UE_ACCESSORY_OUTPUT']; bpy.ops.wm.save_as_mainfile(filepath=out); bpy.ops.wm.open_mainfile(filepath=out)
assert len([o for o in bpy.data.objects if o.get('UE_accessory_binding')])==2
for obj in [o for o in bpy.data.objects if o.get('UE_accessory_binding')]:
    assert obj.modifiers[0].object==obj.parent
Path(os.environ['UE_ACCESSORY_REPORT']).write_text(json.dumps(results,indent=2))
print('ACCESSORY_PASS',results)
