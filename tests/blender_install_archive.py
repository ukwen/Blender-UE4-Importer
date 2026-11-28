"""Install a development archive in an isolated Blender user directory, exercise a real import, then disable."""
import bpy,json,os,sys
from pathlib import Path
archive=Path(os.environ['UE_IMPORTER_ARCHIVE']);module=os.environ.get('UE_IMPORTER_MODULE','ue_importer_dev');project=Path(os.environ['UE56_EDITOR_PROJECT']);out=Path(os.environ['UE56_EDITOR_OUTPUT'])
assert bpy.app.version[:2]==(4,2)
assert bpy.ops.preferences.addon_install(filepath=str(archive),overwrite=True)=={'FINISHED'}
assert bpy.ops.preferences.addon_enable(module=module)=={'FINISHED'}
try:
    addon=sys.modules[module];assert addon.bl_info['version']==tuple(map(int,os.environ.get('UE_IMPORTER_EXPECTED_VERSION','0.10.89').split('.')))
    settings=bpy.context.scene.ueimport_project;settings.project_path=str(project);settings.batch_scope='GEOMETRY';settings.cooked_profile='5.6';settings.job_filter='SM_Door';settings.static_materials=False
    assert bpy.ops.ueimport.refresh_jobs()=={'FINISHED'};assert len(settings.job_items)==3
    assert bpy.ops.ueimport.batch_import()=={'FINISHED'};report=json.loads(bpy.data.texts[settings.batch_report].as_string());assert len(report['results'])==3 and all(x['status']=='reconstructed' for x in report['results']),report
    bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out));settings=bpy.context.scene.ueimport_project
    assert bpy.ops.ueimport.refresh_jobs()=={'FINISHED'};assert bpy.ops.ueimport.batch_import()=={'FINISHED'};report=json.loads(bpy.data.texts[settings.batch_report].as_string());assert all(x.get('reused') for x in report['results']),report
    out.with_suffix('.json').write_text(json.dumps({'platform':sys.platform,'blender':bpy.app.version_string,'installed':True,'imported':3,'reopen_reuse':True},indent=2));print('INSTALL_PASS',flush=True)
finally:
    assert bpy.ops.preferences.addon_disable(module=module)=={'FINISHED'}
