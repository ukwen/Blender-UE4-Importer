"""Genuine cooked static render buffers in two UE4 versions."""
import os,sys,tempfile
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cooked_static import read_static
import skeleton_blender as sb
root=Path(os.environ['MATYA_ASSETS'])
a,b=[read_static(root/v/'SM_Worm.uasset',v) for v in ('4.18','4.27')]
for k in ('positions','faces','uvs','slots','materials'): assert a[k]==b[k],k
assert len(a['positions'])==640 and len(a['faces'])==572
bpy.ops.wm.read_factory_settings(use_empty=True); sb.register()
try:
    for v,d in zip(('4.18','4.27'),(a,b)):
        before=set(bpy.data.objects)
        assert getattr(bpy.ops,'import').ue_cooked_static(filepath=str(root/v/'SM_Worm.uasset'),profile=v)=={'FINISHED'}
        obj=next(iter(set(bpy.data.objects)-before)); mesh=obj.data
        assert len(mesh.vertices)==640 and len(mesh.polygons)==572 and mesh.has_custom_normals
        assert len(mesh.uv_layers)==1 and mesh.materials[0]['UE_material_package']=='/Game/M_Worm'
        assert max(abs(c-x) for vert,(x0,y0,z0) in zip(mesh.vertices,d['positions']) for c,x in zip(vert.co,(y0*.01,x0*.01,z0*.01)))<1e-6
        assert all(tuple(p.vertices)==f for p,f in zip(mesh.polygons,d['faces']))
        assert max(abs(c-x) for l,uv in zip(mesh.loops,mesh.uv_layers[0].data) for c,x in zip(uv.uv,(d['uvs'][l.vertex_index][0],1-d['uvs'][l.vertex_index][1])))<1e-6
        obj.name='Cooked '+v; obj.location.x=0 if v=='4.18' else 1
    for v,p in [('4.18',root/'4.27/SM_Worm.uasset'),('4.27',root/'4.27/SK_Worm.uasset')]:
        try: read_static(p,v)
        except ValueError: pass
        else: raise AssertionError('Wrong profile/class accepted')
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp)/'bad.uasset'; orig=root/'4.27/SM_Worm.uasset'; p.write_bytes(orig.read_bytes()); p.with_suffix('.uexp').write_bytes(orig.with_suffix('.uexp').read_bytes()[:-10])
        try: read_static(p,'4.27')
        except ValueError: pass
        else: raise AssertionError('Truncated sidecar accepted')
    out=os.environ['UE_COOKED_STATIC_OUTPUT']; bpy.ops.wm.save_as_mainfile(filepath=out); bpy.ops.wm.open_mainfile(filepath=out)
    assert len(bpy.data.objects)==2 and all(o.data.attributes.get('UE_source_tangent') for o in bpy.data.objects)
    print('COOKED_STATIC_PASS',len(a['positions']),len(a['faces']))
finally: sb.unregister()
