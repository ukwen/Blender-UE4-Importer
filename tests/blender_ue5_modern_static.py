"""Original UAssetAPI cooked static fixtures via native Blender import and saved sessions."""
import json,os,sys,shutil
from pathlib import Path
from collections import Counter
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cooked_static import read_static
from ue5_modern_static import package, PROFILES
from project_preflight import preflight
import skeleton_blender as sb, uproject_browser as browser, texture_blender as tb

root=Path(os.environ['UASSETAPI_ASSETS']); output=Path(os.environ['UE_MODERN_OUTPUT']); work=Path(os.environ['UE_MODERN_PROJECT']); report={}
bpy.ops.wm.read_factory_settings(use_empty=True); sb.register(); browser.register(); tb.register()
for v in PROFILES:
    project=work/('UE'+v); content=project/'Content'; content.mkdir(parents=True,exist_ok=True)
    srcdir=root/('TestUE'+v.replace('.','_'))/('BpThirdPerson' if v=='5.6' else 'BlankGame')
    src=srcdir/('SM_BlueCube.uasset' if v=='5.4' else 'SM_Cube.uasset')
    for srcfile in srcdir.glob('*.uasset'):
        try: cls,_,_,_,_,identity=package(srcfile)
        except ValueError: continue
        dest=content/(identity.removeprefix('/Game/')+'.uasset'); dest.parent.mkdir(parents=True,exist_ok=True)
        for suffix in ('.uasset','.uexp','.ubulk','.uptnl'):
            if srcfile.with_suffix(suffix).is_file(): shutil.copyfile(srcfile.with_suffix(suffix),dest.with_suffix(suffix))
    path=content/(package(src)[-1].removeprefix('/Game/')+'.uasset'); desc=project/'Sample.uproject'; desc.write_text(json.dumps({'FileVersion':3,'EngineAssociation':v}))
    plan=preflight(str(desc),'GEOMETRY',job_filter=path.stem); assert len(plan['jobs'])==1,plan['jobs']
    assert plan['records'][package(src)[-1]]['coverage']=='ue5_modern_cooked_import_table'
    s=bpy.context.scene.ueimport_project; s.project_path=str(desc);s.batch_scope='GEOMETRY';s.cooked_profile=v;s.job_filter=path.stem
    assert bpy.ops.ueimport.refresh_jobs()=={'FINISHED'} and len(s.job_items)==1
    before=set(bpy.data.objects);assert bpy.ops.ueimport.batch_import()=={'FINISHED'}
    batch=json.loads(bpy.data.texts[s.batch_report].as_string());assert len(batch['results'])==1 and batch['results'][0]['status']=='reconstructed',batch
    obj=next(iter(set(bpy.data.objects)-before)); mesh=obj.data; d=read_static(src,v)
    assert mesh.has_custom_normals and len(mesh.vertices)==24 and len(mesh.polygons)==12
    assert len(mesh.uv_layers)==len(d['uvs'][0])//2
    assert all(tuple(p.vertices)==f and p.material_index==slot for p,f,slot in zip(mesh.polygons,d['faces'],d['slots']))
    err=max(abs(c-x) for vert,(x0,y0,z0) in zip(mesh.vertices,d['positions']) for c,x in zip(vert.co,(y0*.01,x0*.01,z0*.01)))
    assert err<1e-6
    for k in range(len(mesh.uv_layers)):
        assert max(abs(c-x) for l,uv in zip(mesh.loops,mesh.uv_layers[k].data) for c,x in zip(uv.uv,(d['uvs'][l.vertex_index][2*k],1-d['uvs'][l.vertex_index][2*k+1])))<1e-6
    assert [m['UE_material_package'] for m in mesh.materials]==[p for _,p in d['materials']]
    assert mesh['UE_external_bulk_bytes']==d['external_bulk_bytes']
    material_results=batch['results'][0]['result']['material_instances']
    if v=='5.4':
        assert material_results[0]['status']=='parameters_recovered_parent_unresolved'
        mat=mesh.materials[0];meta=json.loads(mat['UE_cooked_instance']);assert len(meta['parameters'])==2 and mat['UE_unresolved_material']
        controls=[n for n in mat.node_tree.nodes if n.get('UE_parameter_identity')]
        assert len(controls)==2 and all(not s.is_linked for n in controls for s in n.outputs)
        rgb=next(n for n in controls if n.type=='RGB');assert list(rgb.outputs[0].default_value)==meta['parameters'][1]['value']
    if v=='5.5':
        assert bpy.ops.ueimport.native_texture(filepath=str(srcdir/'T_Test.uasset'),version='5.5',srgb=True)=={'FINISHED'}
        image=bpy.data.images['T_Test'];assert tuple(image.size)==(2048,2048) and image.packed_file and image['UE_mips_validated']==12
    if v=='5.6':
        assert getattr(bpy.ops,'import').ue_cooked_material_instance(filepath=str(srcdir/'MI_Quinn_01.uasset'),profile=v)=={'FINISHED'}
        mat=bpy.data.materials['MI_Quinn_01'];meta=json.loads(mat['UE_cooked_instance']);assert len(meta['parameters'])==5
        assert len([n for n in mat.node_tree.nodes if n.get('UE_texture_package')])==3
    
    # Exercise the direct import operator, then remove its independent test object.
    before_direct=set(bpy.data.objects);assert getattr(bpy.ops,'import').ue_cooked_static(filepath=str(path),profile=v)=={'FINISHED'}
    extra=next(iter(set(bpy.data.objects)-before_direct)); bpy.data.objects.remove(extra,do_unlink=True)
    obj.name='UE '+v+' - '+src.stem; obj['UE_fixture_version']=v
    report[v]=dict(source=package(src)[-1],vertices=len(mesh.vertices),triangles=len(mesh.polygons),uv_sets=len(mesh.uv_layers),material_slots=len(mesh.materials),slot_faces=dict(Counter(d['slots'])),position_error_m=err,external_bulk_bytes=d['external_bulk_bytes'],dependencies=plan['dependency_counts'],material_instances=material_results,scope=d['geometry_scope'],project=str(desc),job_filter=path.stem)
assert len(bpy.data.objects)==3
bpy.ops.wm.save_as_mainfile(filepath=str(output));bpy.ops.wm.open_mainfile(filepath=str(output))
assert len(json.loads(bpy.data.materials['MI_Quinn_01']['UE_cooked_instance'])['parameters'])==5
assert bpy.data.images['T_Test'].packed_file and tuple(bpy.data.images['T_Test'].size)==(2048,2048)
for v,d in report.items():
    s=bpy.context.scene.ueimport_project;s.project_path=d['project'];s.batch_scope='GEOMETRY';s.cooked_profile=v;s.job_filter=d['job_filter'];assert bpy.ops.ueimport.refresh_jobs()=={'FINISHED'}
    n=len(bpy.data.objects);assert bpy.ops.ueimport.batch_import()=={'FINISHED'}; r=json.loads(bpy.data.texts[s.batch_report].as_string());assert r['results'][0].get('reused') and len(bpy.data.objects)==n
    d['reused_after_reopen']=True
bpy.ops.wm.save_as_mainfile(filepath=str(output));output.with_suffix('.json').write_text(json.dumps({'profiles':report,'packed_texture':{'name':'T_Test','dimensions':[2048,2048],'mips':12,'format':'PF_DXT1'},'instance_parameters':{'MI_BlueCube':2,'MI_Quinn_01':5}},indent=2))
print('UE5_MODERN_STATIC_PASS',flush=True)
