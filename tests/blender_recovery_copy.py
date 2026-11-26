import bpy,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));from project_session import save_recovery_copy,mark_collection,run_session,TAG
bpy.ops.wm.read_factory_settings(use_empty=True)
try:save_recovery_copy();raise AssertionError('unsaved recovery accepted')
except ValueError:pass
with tempfile.TemporaryDirectory() as tmp:
    source=Path(tmp)/'scene.blend';obj=bpy.data.objects.new('Original',None);bpy.context.scene.collection.objects.link(obj);obj.location.x=1
    bpy.ops.wm.save_as_mainfile(filepath=str(source));obj.location.x=7;dest=save_recovery_copy();assert bpy.data.filepath==str(source) and Path(dest).is_file()
    obj.location.x=10;bpy.ops.wm.open_mainfile(filepath=dest);assert bpy.data.objects['Original'].location.x==7
    bpy.ops.wm.open_mainfile(filepath=str(source));assert bpy.data.objects['Original'].location.x==1
print('RECOVERY_COPY_PASS',flush=True)
