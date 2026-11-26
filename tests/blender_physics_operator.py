import sys,pathlib,os,importlib.util
import bpy
root=pathlib.Path(__file__).resolve().parents[1];spec=importlib.util.spec_from_file_location('ue_importer_dev',root/'__init__.py',submodule_search_locations=[str(root)]);addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon);addon.register()
try:
 from skeletal_mesh_native import read_native_mesh,build_mesh
 from physics_native import build_physics,read_physics,Tags,capsule_geometry
 p=pathlib.Path(os.environ['UE_GOBLIN_RAW'])/'SK_Chr_Archer_Female_01.uasset';phys=pathlib.Path(os.environ['UE_GOBLIN_PHYSICS']);obj,arm=build_mesh(read_native_mesh(p,'4.27'));bpy.context.view_layer.objects.active=arm;arm.select_set(True)
 assert getattr(bpy.ops,'import').ue_physics_asset.poll()
 assert getattr(bpy.ops,'import').ue_physics_asset(filepath=str(phys/'PHYS_Chr_Archer_Female_01.uasset'))=={'FINISHED'}
 assert sum(o.get('UE_physics_kind')=='capsule' for o in arm.children)==17
 for fn in (lambda:build_physics(arm,read_physics(phys/'PHYS_Chr_Archer_Male_01.uasset'),p),lambda:build_physics(arm,read_physics(phys/'PHYS_Chr_Archer_Female_01.uasset'),p),lambda:Tags(b'123',[]).tags(),lambda:capsule_geometry(-1,1),lambda:Tags(b'\x00'*8,[]).tags()):
  try:fn();raise AssertionError('Invalid input accepted')
  except ValueError:pass
 print('PHYSICS_OPERATOR_PASS')
finally:addon.unregister()
