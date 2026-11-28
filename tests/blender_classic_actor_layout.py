"""Actual original maps, legacy-free static route, baseline parity and reopen."""
import builtins,json,os,sys
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
original=builtins.__import__
def guard(name,*a,**k):
    if name.split('.')[0] in ('uasset','umesh','umat','umap'):
        raise AssertionError('Inherited importer loaded: '+name)
    return original(name,*a,**k)
builtins.__import__=guard
from static_scene import reconstruct_static_map
from classic_foliage import inspect_foliage
from mathutils import Vector
root=Path(os.environ['UE_WESTERN_PROJECT']); out=Path(os.environ['UE_WESTERN_OUTPUT'])
baseline=json.loads(Path(os.environ['UE_LAYOUT_BASELINE']).read_text())
bpy.ops.wm.read_factory_settings(use_empty=True)
report={}; saved={}
for path in sorted(root.rglob('*.umap')):
    coll,stats=reconstruct_static_map(str(path))
    bpy.context.view_layer.update()
    expected=baseline[path.name]['actors']
    assert not stats['skipped'] and not stats['unresolved_parents']
    static_objects=[o for o in coll.objects if o.get("UE_actor")]
    assert len(static_objects)==len(expected)
    maxerr=0.;missing=[]
    for obj in static_objects:
        e=expected[obj['UE_actor']]
        assert obj.name==e['name'] and obj['UE_mesh_package']==e['package']
        assert (obj.parent['UE_actor'] if obj.parent else None)==e['parent']
        assert list(obj.get('UE_material_overrides',[]))==e['overrides']
        assert json.loads(obj.get('UE_material_override_packages','[]'))==json.loads(e['override_packages'])
        mat=[float(v) for row in obj.matrix_world for v in row]
        maxerr=max(maxerr,max(abs(a-b) for a,b in zip(mat,e['matrix'])))
        if obj.type!='MESH':missing.append(obj['UE_mesh_package'])
        saved[obj.name]=(mat,obj.data.name if obj.type=='MESH' else None)
    assert maxerr<1e-5 and missing==['/Engine/BasicShapes/Cube']
    foliage,errors=inspect_foliage(path)
    assert not errors
    max_foliage_error=0.;instances=0
    for record in foliage:
        objects=sorted((o for o in coll.objects if o.get('UE_foliage_component')==record.name),key=lambda o:o['UE_foliage_instance_index'])
        assert len(objects)==len(record.rows) and len({o.data.as_pointer() for o in objects})==1
        for obj,row in zip(objects,record.rows):
            assert obj['UE_mesh_package']==record.package and list(obj['UE_lightmap_shadowmap_bias'])==list(row[16:20])
            for v in ((0,0,0),(1,0,0),(0,1,0),(0,0,1)):
                x,y,z=v[1]*100,v[0]*100,v[2]*100
                q=[(x*row[j]+y*row[4+j]+z*row[8+j]+row[12+j])*.01 for j in range(3)]
                max_foliage_error=max(max_foliage_error,(obj.matrix_basis@Vector(v)-Vector((q[1],q[0],q[2]))).length)
            saved[obj.name]=([v for row in obj.matrix_world for v in row],obj.data.name)
        instances+=len(objects)
    assert max_foliage_error<.00005 and instances==(462 if path.stem=='Demonstration' else 0)
    assert stats['foliage_report']['instances']==instances
    report[path.stem]={'placements':len(static_objects),'geometry':len(static_objects)-len(missing),'missing':missing,'max_baseline_matrix_error':maxerr,'decode_attempts':stats['decode_attempts'],'foliage_instances':instances,'max_foliage_local_point_error_m':max_foliage_error}
bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out))
for name,(mat,mesh) in saved.items():
    obj=bpy.data.objects[name]
    assert (obj.data.name if obj.type=='MESH' else None)==mesh
    assert max(abs(a-b) for a,b in zip(mat,[v for row in obj.matrix_world for v in row]))<1e-5
report['reopen']=True;out.with_suffix('.json').write_text(json.dumps(report,indent=2));print('CLASSIC_LAYOUT_PASS',report,flush=True)
