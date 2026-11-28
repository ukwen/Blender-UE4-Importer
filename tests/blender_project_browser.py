import sys, tempfile, types
from pathlib import Path
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uproject_browser as browser
assert bpy.app.version == (4, 2, 4)
with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    project = root / 'Sample.uproject'
    project.write_text('{"EngineAssociation":"4.27"}')
    for name in ['Maps/Z.umap', 'Maps/A.umap', 'Meshes/Chair.uasset', '__ExternalActors__/X.umap']:
        file = root / 'Content' / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.touch()
    browser.register()
    try:
        state = bpy.context.scene.ueimport_project
        state.project_path = str(project)
        assert bpy.ops.ueimport.scan_project() == {'FINISHED'}
        assert [m.name for m in state.maps] == ['Maps/A.umap', 'Maps/Z.umap']
        assert state.engine == '4.27'
        print('PASS scan, sorted map list, external actor exclusion')
        calls = []
        import asset_entrypoints
        def record(paths,partial,strict,scale,profile):
            calls.append((paths,partial,strict,scale,profile))
            return {'UE_report':'mock report'},{}
        asset_entrypoints.import_saved_levels=record
        state.active = 1
        state.materials = True
        assert bpy.ops.ueimport.import_selected_map() == {'FINISHED'}
        assert calls == [([str(root / 'Content/Maps/Z.umap')],False,False,1.,'4.27')]
        print('PASS selected map routing (mock native transaction)')
        state.materials=False
        try:
            bpy.ops.ueimport.import_selected_map()
        except RuntimeError as exc:
            assert 'Historical materials-off' in str(exc)
        else:
            raise AssertionError('Unsupported historical material filter accepted')
        assert len(calls)==1
        state.materials=True
        state.project_path = str(root / 'missing.uproject')
        try:
            bpy.ops.ueimport.import_selected_map()
        except RuntimeError:
            pass
        assert len(calls) == 1
        print('PASS invalid project does not call importer')
    finally:
        browser.unregister()
    assert not hasattr(bpy.types.Scene, 'ueimport_project')
    browser.register(); browser.unregister()
    print('PASS registration, unregistration, re-registration')
mat = bpy.data.materials.new('Probe'); mat.use_nodes = True
bsdf = mat.node_tree.nodes.get('Principled BSDF')
for name in ('Specular IOR Level', 'Emission Color', 'Transmission Weight'):
    assert name in bsdf.inputs
mat.surface_render_method = 'BLENDED'; mat.surface_render_method = 'DITHERED'
print('PASS modern material API')
for kind in ('SPHERE', 'VOLUME'):
    probe = bpy.data.lightprobes.new(kind, kind)
    print('PASS probe', kind, 'falloff', hasattr(probe,'falloff'), 'influence',hasattr(probe,'influence_distance'))
mesh = bpy.data.meshes.new('triangle'); mesh.from_pydata([(0,0,0),(1,0,0),(0,1,0)],[],[(0,1,2)])
mesh.normals_split_custom_set([(0,0,1)]*3)
print('PASS mesh custom normals')
print('ALL TARGETED CHECKS PASS')
