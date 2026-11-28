"""Original map report navigation, identity refusal, and persistence in Blender."""
import json,os,sys
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uproject_browser as browser
project=Path(os.environ['UE56_EDITOR_PROJECT']);out=Path(os.environ['UE56_EDITOR_OUTPUT'])
bpy.ops.wm.read_factory_settings(use_empty=True);browser.register()
s=bpy.context.scene.ueimport_project;s.project_path=str(project);s.partial_materials=True
assert bpy.ops.ueimport.scan_project()=={'FINISHED'}
for m in s.maps:m.enabled=m.name.endswith(('Lvl_ThirdPerson.umap','TestLevel.umap'))
assert bpy.ops.ueimport.level_set()=={'FINISHED'}
ctx=bpy.context;group=next(c for c in ctx.scene.collection.children if c.get('UE_project_level_set'))
roots={c['UE_full_scene_source']:c for c in group.children};assert len(roots)==2
names={}
def select(source):
    global s
    s=bpy.context.scene.ueimport_project;s.active=next(i for i,m in enumerate(s.maps) if m.filepath==source)
def open_report(kind,expected):
    area=next((a for a in bpy.context.screen.areas if a.type=='TEXT_EDITOR'),None) or next(a for a in bpy.context.screen.areas if a.type=='VIEW_3D')
    with bpy.context.temp_override(area=area):assert bpy.ops.ueimport.report(kind=kind)=={'FINISHED'}
    assert area.type=='TEXT_EDITOR' and area.spaces.active.text.name==expected
for source,c in roots.items():
    select(source);names[source]=c['UE_report'];assert browser.resolve_report(ctx,'LEVEL').name==names[source]
    open_report('LEVEL',names[source]);open_report('SET',group['UE_report'])
    assert browser.resolve_report(ctx,'LATEST').name==group['UE_report']
first,second=roots;select(first);assert bpy.ops.ueimport.scene_dependencies()=={'FINISHED'}
actions=s.scene_action_report;open_report('ACTIONS',actions)
select(second);assert browser.resolve_report(ctx,'ACTIONS') is None
assert bpy.ops.ueimport.report(kind='ACTIONS',copy=True)=={'CANCELLED'}
# A wrong existing text name must not allow cross-level report navigation.
root=roots[second];old=root['UE_report'];root['UE_report']=names[first]
assert bpy.ops.ueimport.report(kind='LEVEL',copy=True)=={'CANCELLED'};root['UE_report']=old
# Duplicate ownership and missing report are refused, not silently replaced by last operation.
dup=bpy.data.collections.new('Ambiguous test');ctx.scene.collection.children.link(dup);dup['UE_full_scene_source']=second
assert browser.resolve_report(ctx,'LEVEL') is None;bpy.data.collections.remove(dup)
root['UE_report']='missing';assert browser.resolve_report(ctx,'LEVEL') is None;root['UE_report']=old
saved=s.project_path;s.project_path=str(project.parent/'missing.uproject');assert browser.resolve_report(ctx,'LEVEL') is None;s.project_path=saved
bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out))
for source,name in names.items():select(source);open_report('LEVEL',name)
select(first);open_report('ACTIONS',actions)
result=dict(level_reports=2,set_report=True,latest_operation=True,source_actions=True,stale_selection_refused=True,wrong_content_refused=True,ambiguous_refused=True,missing_refused=True,changed_project_refused=True,reopen=True)
out.with_suffix('.json').write_text(json.dumps(result,indent=2));print('REPORT_NAVIGATION_PASS',result,flush=True)
