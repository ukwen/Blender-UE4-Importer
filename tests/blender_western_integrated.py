"""Real Western Frontier map reconstruction through the project geometry route."""
import bpy,os,sys,pathlib,json
from mathutils import Vector
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from static_scene import reconstruct_static_map
from uasset import UAsset
from foliage_legacy import read_component
root=pathlib.Path(os.environ['UE_WESTERN_PROJECT']); out=os.environ['UE_WESTERN_OUTPUT']
bpy.ops.wm.read_factory_settings(use_empty=True)
reports={}; expected={}; max_error=0
for path in sorted(root.rglob('*.umap')):
    coll,report=reconstruct_static_map(str(path),components=True)
    reports[path.stem]=report; print('RESULT',path.stem,report['actor_status'],report['foliage_report'],report['component_report']['status'],flush=True)
    assert report['actor_status']==({'reconstructed':1994,'missing':1} if path.stem=='Demonstration' else {'reconstructed':322,'missing':1})
    assert report['foliage_report']['instances']==(462 if path.stem=='Demonstration' else 0)
    assert not report['skipped'] and not report['unresolved_parents']
    assert report['component_report']['actors']['SkeletalMeshActor']==(6 if path.stem=='Demonstration' else 30)
    assert report['component_report']['status'].get('reconstructed')==(6 if path.stem=='Demonstration' else 30)
    assert not report['component_report']['status'].get('failed')
    rigs=[o for o in coll.objects if o.type=='ARMATURE']; assert len(rigs)==(6 if path.stem=='Demonstration' else 30)
    for arm in rigs:
        skin=next(o for o in arm.children if o.type=='MESH');assert skin.modifiers[0].object==arm and len(skin.vertex_groups)==len(arm.data.bones)
        assert all(abs(sum(g.weight for g in v.groups)-1)<1e-6 for v in skin.data.vertices)
    bpy.context.view_layer.update()
    with UAsset(str(path)) as asset:
        for e in asset.exports:
            if e.export_class_type!='FoliageInstancedStaticMeshComponent':continue
            _,pkg,rows=read_component(e)
            objs=sorted((o for o in coll.objects if o.get('UE_foliage_component')==e.object_name),key=lambda o:o['UE_foliage_instance_index'])
            assert len(objs)==len(rows) and len({o.data.as_pointer() for o in objs})==1
            for o,r in zip(objs,rows):
                assert o['UE_mesh_package']==pkg and list(o['UE_lightmap_shadowmap_bias'])==list(r[16:20])
                for v in ((0,0,0),(1,0,0),(0,1,0),(0,0,1)):
                    x,y,z=v[1]*100,v[0]*100,v[2]*100
                    q=[(x*r[j]+y*r[4+j]+z*r[8+j]+r[12+j])*.01 for j in range(3)]
                    max_error=max(max_error,(o.matrix_basis@Vector(v)-Vector((q[1],q[0],q[2]))).length)
                expected[o.name]=[list(r) for r in o.matrix_world]
    reports[path.stem]['skin_totals']={'rigs':len(rigs),'vertices':sum(len(o.data.vertices) for a in rigs for o in a.children if o.type=='MESH'),'triangles':sum(len(o.data.polygons) for a in rigs for o in a.children if o.type=='MESH'),'bones':sum(len(a.data.bones) for a in rigs)}
    if path.stem=='Overview':coll.hide_viewport=True;coll.hide_render=True
assert max_error<.00005 and len(expected)==462
bpy.ops.wm.save_as_mainfile(filepath=out);bpy.ops.wm.open_mainfile(filepath=out)
assert len([o for o in bpy.data.objects if o.type=='ARMATURE'])==36
for name,mat in expected.items():
    assert max(abs(bpy.data.objects[name].matrix_world[i][j]-mat[i][j]) for i in range(4) for j in range(4))<.00005
pathlib.Path(os.environ['UE_WESTERN_REPORT']).write_text(json.dumps({'levels':reports,'max_foliage_local_point_error_m':max_error,'reopen':'passed'},indent=2))
print('WESTERN_INTEGRATED_PASS',max_error,flush=True)
