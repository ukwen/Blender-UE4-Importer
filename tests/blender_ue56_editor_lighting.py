"""Native light import via actual Blender operator; independent transform and field checks."""
import json,math,os,sys
from pathlib import Path
from collections import Counter
import bpy
from mathutils import Matrix,Vector
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ue5_editor_lighting import records,LIGHTS
import uproject_browser as browser
project=Path(os.environ['UE56_EDITOR_PROJECT']);root=project.parent/'Content';out=Path(os.environ['UE56_EDITOR_OUTPUT'])
bpy.ops.wm.read_factory_settings(use_empty=True);browser.register()
s=bpy.context.scene.ueimport_project;s.project_path=str(project);assert bpy.ops.ueimport.scan_project()=={'FINISHED'}
expected={};results={};counts=Counter();sentinel=bpy.data.objects.new('Existing user object',None);bpy.context.scene.collection.objects.link(sentinel);sentinel.location=(7,8,9)
for i,m in enumerate(s.maps):
    path=Path(m.filepath)
    if path.relative_to(root).as_posix()=='MyStuff/TestLevel.umap':continue
    s.active=i;data=records(root,path);expected[str(path.resolve())]=data;assert bpy.ops.ueimport.lighting_preview()=={'FINISHED'}
    c=next(c for c in bpy.data.collections if c.get('UE_lighting_source')==str(path.resolve()));counts.update(o['UE_actor_kind'] for o in c.objects);results[m.name]=len(c.objects)
    assert len(c.objects)==len(data['records']) and not data['skipped']
    # Duplicate import must not mutate or add objects (execute raises RuntimeError on ERROR report).
    n=len(bpy.data.objects)
    try:assert bpy.ops.ueimport.lighting_preview()=={'CANCELLED'}
    except RuntimeError as e:assert 'already imported' in str(e)
    assert len(bpy.data.objects)==n
assert sum(counts.values())==175 and sum(counts[k] for k in LIGHTS)==146

def verify():
    bpy.context.view_layer.update();err=0.;direrr=0.;props=0
    swap=Matrix(((0,1,0),(1,0,0),(0,0,1)))
    for source,data in expected.items():
        c=next(c for c in bpy.data.collections if c.get('UE_lighting_source')==source);r=json.loads(bpy.data.texts[c['UE_report']].as_string());assert len(r['records'])==len(data['records'])
        lookup={(o['UE_source_actor_package'],o['UE_actor']):o for o in c.objects}
        for x in data['records']:
            o=lookup[x['source'],x['actor']];t,p,s=x['fields']['RelativeLocation'],x['fields']['RelativeRotation'],x['fields']['RelativeScale3D'];pos=(t[1]*.01,t[0]*.01,t[2]*.01);err=max(err,math.dist(tuple(o.location),pos))
            pitch,yaw,roll=map(math.radians,p);rot=swap@Matrix.Rotation(yaw,3,'Z')@Matrix.Rotation(-pitch,3,'Y')@Matrix.Rotation(-roll,3,'X')@swap
            assert json.loads(o['UE_light_source_properties'])==x['properties'];assert o['UE_preview_only']
            if x['kind'] in LIGHTS:
                assert o.type=='LIGHT' and o.data.type==LIGHTS[x['kind']][1];want=rot@Vector((0,1,0));got=o.rotation_quaternion@Vector((0,0,-1));direrr=max(direrr,(got-want).length)
                p=x['properties'];d=o.data
                if 'Intensity' in p:assert math.isclose(d.energy,p['Intensity']*(1 if d.type=='SUN' else .01),rel_tol=1e-6)
                if 'OuterConeAngle' in p:assert math.isclose(d.spot_size,math.radians(2*p['OuterConeAngle']),rel_tol=1e-6)
                if 'AttenuationRadius' in p:assert d.use_custom_distance and math.isclose(d.cutoff_distance,p['AttenuationRadius']*.01,rel_tol=1e-6)
                if 'CastShadows' in p:assert d.use_shadow==p['CastShadows']
                props+=len(p)
            else:assert o.type=='EMPTY'
    assert tuple(bpy.data.objects['Existing user object'].location)==(7,8,9)
    assert err<1e-4 and direrr<1e-5,(err,direrr)
    return dict(max_position_error_m=err,max_forward_vector_error=direrr,verified_light_properties=props)
a=verify();bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out));b=verify()
report=dict(counts=dict(counts),levels=results,before=a,after=b,duplicate_rejected=True,scope='Approximate light preview; environment markers only, no Unreal renderer equivalence')
out.with_suffix('.json').write_text(json.dumps(report,indent=2));print('LIGHTING_ACCEPTANCE_PASS',report,flush=True)
# A practical single-level scene, avoiding the overlapping six-level audit layout.
from static_scene import reconstruct_static_map
from ue5_editor_lighting import reconstruct
bpy.ops.wm.read_factory_settings(use_empty=True)
path=root/'ThirdPerson/Lvl_ThirdPerson.umap';geo,geo_report=reconstruct_static_map(str(path),cooked_profile='5.6',materials=True,allow_partial_materials=True,components=True)
light,light_report=reconstruct(str(path));assert len(geo.objects)==55 and geo_report['actor_status']['reconstructed']==53 and len(light.objects)==6
assert all(o not in light.objects[:] for o in geo.objects)
combined=out.with_name(out.stem+'_thirdperson.blend');bpy.ops.wm.save_as_mainfile(filepath=str(combined));bpy.ops.wm.open_mainfile(filepath=str(combined))
assert len([o for o in bpy.data.objects if o.get('UE_geometry_status')=='reconstructed'])==53
assert len([o for o in bpy.data.objects if o.get('UE_actor_kind')=='DirectionalLight'])==1
report['single_level']=dict(geometry=geo_report['actor_status'],lights_and_markers=light_report['counts'],reopen=True)
out.with_suffix('.json').write_text(json.dumps(report,indent=2));print('COMBINED_MAP_LIGHT_PASS',report['single_level'],flush=True)
