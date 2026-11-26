"""Run in Blender 4.2.4 with UE_SOURCE and UE_WESTERN_PROJECT configured."""
import os, sys, pathlib, struct, json
import bpy
from mathutils import Vector, Matrix
sys.path.insert(0, os.environ['UE_SOURCE'])
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from uasset import UAsset
from foliage_legacy import read_component, build_instances, instance_matrix, decode_instances
from umap import Transform
root=pathlib.Path(os.environ['UE_WESTERN_PROJECT']); out=pathlib.Path(os.environ['UE_FOLIAGE_OUTPUT'])
bpy.ops.wm.read_factory_settings(use_empty=True)
# Archived reader recovery harness: reuse the published 0.10.41 FRawMesh layout
# for geometry only if the latest native module is absent. Not a production importer.
def mesh_for(package):
    path=root/'Content'/(package.removeprefix('/Game/')+'.uasset')
    with UAsset(str(path)) as a:
        e=next(e for e in a.exports if e.export_class_type=='StaticMesh')
        try:
            from legacy_static import read_legacy_static,build_legacy_static
        except ImportError:
            e.ReadProperties(False,False); f=a.f
            if f.ReadInt32(): f.ReadGuid()
            assert f.ReadBytes(2)==bytes(2) and f.ReadInt32()==0
            f.ReadInt32(); f.ReadInt32(); f.ReadFString(); f.ReadUInt32(); f.ReadGuid()
            for _ in range(f.ReadInt32()): f.ReadInt32()
            flags,count,size=f.ReadStruct('III',12); offset=f.ReadInt64()+a.summary.bulk_data_offset
            assert flags==1 and count==size and offset+size<=path.stat().st_size
            f.Seek(offset); blob=f.ReadBytes(size); pos=8
            assert struct.unpack_from('<ii',blob)==(1,0)
            def arr(fmt):
                nonlocal pos
                n=struct.unpack_from('<i',blob,pos)[0]; pos+=4; width=struct.calcsize('<'+fmt)
                assert 0<=n<=1000000 and pos+n*width<=len(blob)
                v=list(struct.iter_unpack('<'+fmt,blob[pos:pos+n*width]));pos+=n*width;return v
            slots=arr('i'); arr('I'); pts=arr('3f'); wedges=[v[0] for v in arr('i')]
            assert len(wedges)==len(slots)*3
            m=bpy.data.meshes.new(e.object_name);m.from_pydata([(y*.01,x*.01,z*.01) for x,y,z in pts],[],[wedges[i:i+3] for i in range(0,len(wedges),3)]);assert not m.validate();m.update();return m
        return build_legacy_static(read_legacy_static(e))
coll=bpy.data.collections.new('Western Frontier Foliage');bpy.context.scene.collection.children.link(coll)
expected={}; report=[]; roots={}; rejected=0
with UAsset(str(next(root.rglob('Demonstration.umap')))) as a:
    for e in a.exports:
        if e.export_class_type!='FoliageInstancedStaticMeshComponent':continue
        props,package,records=read_component(e); e.properties=props
        attach=props.TryGetValue('AttachParent'); assert attach is not None
        attach.ReadProperties(False)
        parent=bpy.data.objects.new(e.object_name+'_component',None);coll.objects.link(parent)
        root_obj=roots.get(id(attach))
        if root_obj is None:
            root_obj=bpy.data.objects.new(attach.object_name+'_root',None);coll.objects.link(root_obj);root_obj.rotation_mode='YXZ';Transform(attach,root_obj);roots[id(attach)]=root_obj
        parent.parent=root_obj;parent.rotation_mode='YXZ';Transform(e,parent)
        # Corrupt real native payloads to verify refusal, not only synthetic bytes.
        from uasset import Properties
        a.f.Seek(e.serial_desc.offset);Properties().Read(a,read_children=False);payload=a.f.ReadBytes(e.serial_desc.offset+e.serial_desc.count-a.f.Position())
        variants=[payload[:-1],payload[:31]+struct.pack('<I',64)+payload[35:],payload[:35]+struct.pack('<I',len(records)+1)+payload[39:],payload[:39]+struct.pack('<f',float('nan'))+payload[43:]]
        for bad in variants:
            try:decode_instances(bad,len(records))
            except ValueError:rejected+=1
            else:raise AssertionError('Accepted corrupted native payload')
        mesh=mesh_for(package); objs=build_instances(coll,parent,mesh,e.object_name,package,records)
        assert len(objs)==len(records) and all(o.data==mesh for o in objs)
        bpy.context.view_layer.update()
        error=0.
        for o,r in zip(objs,records):
            # Independent point mapping: Unreal row-vector affine transform of a Blender local point.
            for v in ((0,0,0),(1,0,0),(0,1,0),(0,0,1)):
                x,y,z=v[1]*100,v[0]*100,v[2]*100
                q=[(x*r[j]+y*r[4+j]+z*r[8+j]+r[12+j])*.01 for j in range(3)]
                actual=o.matrix_basis@Vector(v);error=max(error,(actual-Vector((q[1],q[0],q[2]))).length)
            expected[o.name]=[list(v) for v in o.matrix_world]
        assert error<0.00005,error
        report.append(dict(component=e.object_name,mesh=package,instances=len(objs),vertices=len(mesh.vertices),faces=len(mesh.polygons),max_local_point_error_m=error))
assert sorted(x['instances'] for x in report)==[223,239]
assert len(expected)==462 and rejected==8
# Invalid payload must fail closed.
for payload in (b'',bytes(47)):
    try:decode_instances(payload,223)
    except ValueError:pass
    else:raise AssertionError('Accepted invalid payload')
bpy.ops.wm.save_as_mainfile(filepath=str(out)); bpy.ops.wm.open_mainfile(filepath=str(out))
assert len({bpy.data.objects[name].data.as_pointer() for name in expected})==2
for name,m in expected.items():
    obj=bpy.data.objects[name];assert obj.parent and obj.type=='MESH';assert max(abs(obj.matrix_world[i][j]-m[i][j]) for i in range(4) for j in range(4))<1e-5
print('FOLIAGE_PASS',json.dumps(report), 'REOPEN_PASS',len(expected),'CORRUPTION_REFUSALS',rejected);out.with_suffix('.json').write_text(json.dumps(report,indent=2))
