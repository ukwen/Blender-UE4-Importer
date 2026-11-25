"""Controlled two-slot mesh, actual native shader and independent object overrides."""
import json, os, sys, tempfile, shutil
from pathlib import Path
from unittest.mock import patch
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import material_stage, uasset, umat
with tempfile.TemporaryDirectory() as temp:
    root=Path(temp); (root/'Content').mkdir(); (root/'P.uproject').write_text('{}')
    sample=Path(os.environ['UE_TEST_ASSETS'])/'TestEditorAssets/TestMaterial.uasset'
    shutil.copy(sample,root/'Content/TestMaterial.uasset')
    shutil.copy(sample,root/'Content/Bad.uasset')
    project=uasset.UProject(str(root/'Content/TestMaterial.uasset'))
    mesh=bpy.data.meshes.new('TwoSlots'); mesh.from_pydata([(0,0,0),(1,0,0),(0,1,0),(1,1,0)],[],[(0,1,2),(1,3,2)])
    mesh['UE_source_format']='Legacy FMeshDescription'
    mesh['UE_polygon_group_ids']=[4,9]; mesh['UE_material_slots']=['B','A']
    attr=mesh.attributes.new('UE_polygon_group','INT','FACE'); attr.data.foreach_set('value',[4,9])
    mesh['UE_material_bindings']=json.dumps([['A','/Game/TestMaterial'],['B','/Game/Missing']])
    collection=bpy.data.collections.new('Test'); bpy.context.scene.collection.children.link(collection)
    a=bpy.data.objects.new('A',mesh); b=bpy.data.objects.new('B',mesh)
    collection.objects.link(a); collection.objects.link(b)
    b['UE_material_override_packages']=json.dumps(['/Game/Override',''])
    report=material_stage.bind_scene_materials(collection,project)
    assert report['bound_meshes']==1 and not report['errors'], report
    assert [p.material_index for p in mesh.polygons]==[1,0]
    assert a.data==b.data and a.material_slots[0].material==mesh.materials[0]
    assert a.material_slots[0].material['UE_material_status']=='graph_imported_unverified'
    assert b.material_slots[0].link=='OBJECT' and b.material_slots[0].material['UE_material_package']=='/Game/Override'
    assert b.material_slots[1].material==a.material_slots[1].material
    print('MULTISLOT_OVERRIDE_PASS')
    umat.TryAppendNodeGroups()
    baseline={x.as_pointer() for store in (bpy.data.materials,bpy.data.node_groups,bpy.data.images) for x in store}
    def bad(*args):
        m=bpy.data.materials.new('FailedGraph'); m.use_nodes=True
        g=bpy.data.node_groups.new('FailedGroup','ShaderNodeTree'); g.nodes.new('ShaderNodeTexImage')
        m.node_tree.nodes.new('ShaderNodeGroup').node_tree=g
        bpy.data.images.new('FailedImage',width=1,height=1)
        return m,None
    with patch.object(umat,'ImportNodeGraph',side_effect=bad):
        fallback=material_stage.MaterialResolver(project).resolve('/Game/Bad','Bad')
    assert fallback['UE_material_status']=='graph_failed'
    assert not bpy.data.materials.get('FailedGraph') and not bpy.data.node_groups.get('FailedGroup') and not bpy.data.images.get('FailedImage')
    assert baseline <= {x.as_pointer() for store in (bpy.data.materials,bpy.data.node_groups,bpy.data.images) for x in store}
    print('FAILED_GRAPH_ROLLBACK_PASS')
    path=str(root/'slots.blend'); bpy.ops.wm.save_as_mainfile(filepath=path); bpy.ops.wm.open_mainfile(filepath=path)
    assert bpy.data.objects['B'].material_slots[0].link=='OBJECT'
    assert bpy.data.objects['A'].data==bpy.data.objects['B'].data
    print('MATERIAL_REOPEN_PASS')
