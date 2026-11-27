"""Original selected-level audit and strict refusal before any scene mutation."""
import bpy,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from uasset import UProject
from ue5_scene_dependencies import audit
from ue5_full_scene import reconstruct
from project_session import new_ids
import uproject_browser as browser
p=Path(os.environ['UE56_EDITOR_PROJECT']);out=Path(os.environ['UE56_EDITOR_OUTPUT']);c=p.parent/'Content'
bpy.ops.wm.read_factory_settings(use_empty=True);browser.register();s=bpy.context.scene.ueimport_project;s.project_path=str(p);assert bpy.ops.ueimport.scan_project()=={'FINISHED'}
results={};missing={}
for rel in ['ThirdPerson/Lvl_ThirdPerson.umap','Variant_Combat/Lvl_Combat.umap','Variant_Platforming/Lvl_Platforming.umap','Variant_SideScrolling/Lvl_SideScrolling.umap','MyStuff/Maps/TestLevel.umap','MyStuff/Maps/MainLevel.umap']:
    level=c/rel; s.active=next(i for i,m in enumerate(s.maps) if Path(m.filepath)==level)
    before=set(new_ids());d=audit(UProject(p),level);assert set(new_ids())==before
    assert not d['ready_for_strict_import'];assert d['unresolved_hard']>0
    try: reconstruct(str(level),strict_dependencies=True);raise AssertionError('Incomplete level passed strict gate')
    except ValueError as e:assert 'Source dependency check failed' in str(e)
    assert set(new_ids())==before
    if rel.endswith('MainLevel.umap'):
        assert len([k for k,v in d['dependencies'].items() if k.startswith('/Game/StarterBundle/') and v['status']=='missing_game'])>=227
    if rel.startswith('ThirdPerson'):
        assert len(d['owned_packages'][d['level']])>=2
        assert bpy.ops.ueimport.scene_dependencies()=={'FINISHED'}
        saved=json.loads(bpy.data.texts[s.batch_report].as_string());assert saved==d
    missing[rel]={k:v for k,v in d['dependencies'].items() if v['status']!='available'}
    summary={k:d[k] for k in ('scanned_packages','dependency_counts','unresolved_hard','unresolved_soft_only','unknown_tables','ready_for_strict_import')};summary['external_packages']=sum(len(v) for v in d['owned_packages'].values());results[rel]=summary
    print('AUDIT',rel,{k:v for k,v in summary.items() if k!='unknown_tables'},'unknown',len(d['unknown_tables']),flush=True)
    if rel in ('Variant_Combat/Lvl_Combat.umap','Variant_Platforming/Lvl_Platforming.umap','Variant_SideScrolling/Lvl_SideScrolling.umap'):
        s.partial_materials=True;assert bpy.ops.ueimport.full_scene()=={'FINISHED'};root=next(x for x in bpy.context.scene.collection.children if x.get('UE_full_scene_source')==str(level));report=json.loads(bpy.data.texts[root['UE_report']].as_string());assert report['source_dependencies']==d;results[rel]['scene_counts']=report['counts'];results[rel]['geometry_status']=report['stages']['geometry']['actor_status'];print('TRANSFER',rel,report['counts'],flush=True)
        if rel.startswith('Variant_Combat'): assert report['counts']['meshes']>=66
        elif rel.startswith('Variant_Platforming'): assert report['counts']['meshes']>=134
        else: assert report['counts']['meshes']>=90
bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out))
for rel,d in results.items():
    if 'scene_counts' in d:
        root=next(x for x in bpy.context.scene.collection.children if x.get('UE_full_scene_source')==str(c/rel));assert len(root.all_objects)==d['scene_counts']['objects'];report=json.loads(bpy.data.texts[root['UE_report']].as_string());assert report['counts']==d['scene_counts'];assert report['source_dependencies']['unresolved_hard']==d['unresolved_hard']
out.with_name('missing-scene-dependencies-075.json').write_text(json.dumps(missing,indent=2))
out.with_suffix('.json').write_text(json.dumps(dict(levels=results,strict_no_mutation=True,report_ui=True,reopen=True),indent=2));print('SCENE_DEPENDENCY_PASS',flush=True)
