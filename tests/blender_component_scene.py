"""Genuine Overview component hierarchy; controlled skeletal dependency routing."""
import json,os,sys,tempfile
from pathlib import Path
from unittest.mock import patch
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import static_scene,component_scene,uproject_browser,uasset
root=Path(os.environ['GOBLIN_CONTENT']); path=str(root/'Maps/Overview.umap')
bpy.ops.wm.read_factory_settings(use_empty=True)
uproject_browser.register()
try:
    state=bpy.context.scene.ueimport_project; state.project_path=str(root.parents[1]/'Goblin.uproject'); state.components=True
    assert bpy.ops.ueimport.scan_project()=={'FINISHED'}
    assert bpy.ops.ueimport.reconstruct_static()=={'FINISHED'}
finally: uproject_browser.unregister()
c=next(c for c in bpy.data.collections if c.get('UE_report'))
r=json.loads(bpy.data.texts[c['UE_report']].as_string()); extra=r['component_report']
assert r['actor_status']=={'missing':559,'reconstructed':3}
assert extra['actors']=={'BlueprintActor':16,'SkeletalMeshActor':15} and extra['components']==84 and not extra['failures']
assert extra['status']=={'anchor_only':16,'inherited_mesh_unresolved':18,'socket_transform_unresolved':35,'missing':15}
assert len(c.objects)==646
anchors=[o for o in c.objects if o.get('UE_component_anchor')]
assert len(anchors)==84 and sum(o.parent is not None for o in anchors)==53
# Compare explicitly serialized translations and parent links for every anchor.
with uasset.UAsset(path) as asset:
    by_actor={e.object_name:i for i,e in enumerate(asset.exports,1) if e.export_class_type=='SkeletalMeshActor' or e.export_class_type.endswith('_C')}
    for o in anchors:
        e=next(e for e in asset.exports if e.outer_index==by_actor[o['UE_component_actor']] and e.object_name==o['UE_component'])
        e.ReadProperties(False); p=e.properties; loc=p.TryGetValue('RelativeLocation')
        if loc: assert max(abs(a-b) for a,b in zip(o.location,(loc.y*.01,loc.x*.01,loc.z*.01)))<.00003
        parent=p.TryGetValue('AttachParent')
        if parent: assert o.parent['UE_component']==parent.object_name
        socket=p.TryGetValue('AttachSocketName','None')
        if socket!='None': assert o['UE_attach_socket']==socket and o['UE_placement_unresolved']=='socket_transform_unresolved'
# Use genuine cooked worm solely as a controlled stand-in for two missing skeletal dependencies.
# Never save or report this as original Goblin geometry.
fixture=bpy.data.collections.new('TEST ONLY skeletal routing'); bpy.context.scene.collection.children.link(fixture)
resolver=static_scene.MeshResolver(uasset.UProject(path)); original=resolver.project.resolve_package
packages=[rec['package'] for rec in extra['records'] if rec['status']=='missing'][:2]
worm=Path(os.environ['MATYA_ASSETS'])/'4.27/SK_Worm.uasset'
with patch.object(resolver.project,'resolve_package',side_effect=lambda p:str(worm) if p in packages else original(p)):
    check=component_scene.extend_components(path,fixture,resolver)
assert check['status']['reconstructed']==2 and check['skeletal_decode_attempts']==2
meshes=[o for o in fixture.objects if o.type=='MESH']; assert len(meshes)==2
assert meshes[0].parent!=meshes[1].parent and all(o.parent.parent.get('UE_component_anchor') and len(o.vertex_groups)==6 and len(o.data.vertices)==640 for o in meshes)
assert all(o.modifiers[0].object==o.parent for o in meshes)
for o in list(fixture.objects): bpy.data.objects.remove(o,do_unlink=True)
bpy.data.collections.remove(fixture)
for store in (bpy.data.meshes,bpy.data.armatures,bpy.data.materials):
    for item in list(store):
        if not item.users: store.remove(item)
out=os.environ['UE_COMPONENT_OUTPUT']; bpy.ops.wm.save_as_mainfile(filepath=out); bpy.ops.wm.open_mainfile(filepath=out)
c=next(c for c in bpy.data.collections if c.get('UE_report')); assert len(c.objects)==646 and json.loads(bpy.data.texts[c['UE_report']].as_string())==r
print('COMPONENT_SCENE_PASS',extra['actors'],extra['status'],len(c.objects))
