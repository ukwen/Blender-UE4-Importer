"""Verify retained on-demand legacy file-menu compatibility with original assets."""
import os,sys,json
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import asset_entrypoints
root=Path(os.environ['UE_WESTERN_PROJECT']);bpy.ops.wm.read_factory_settings(use_empty=True)
asset_entrypoints.register()
try:
    assert 'umap' not in sys.modules and 'umesh' not in sys.modules
    ops=getattr(bpy.ops,'import')
    # Material-bearing 508 static import now uses the native entrypoint.
    path=next(root.rglob('SM_Particle_Smoke_01.uasset'))
    before=set(bpy.data.objects);assert ops.umesh(filepath=str(path),materials=True)=={'FINISHED'}
    obj,=set(bpy.data.objects)-before;assert obj.type=='MESH' and len(obj.data.vertices)>0
    assert 'umesh' not in sys.modules
    # Original file-menu option contract remains available for older map import.
    before=set(bpy.data.objects);path=next(root.rglob('Overview.umap'))
    assert ops.umap(filepath=str(path),meshes=False,materials=False,cameras=False,lights_point=False,lights_spot=False,lights_dir=False,cubemaps=False,lightprobes=False)=={'FINISHED'}
    added=len(set(bpy.data.objects)-before);assert added>0 and 'umap' in sys.modules
    print('COMPATIBILITY_ENTRYPOINTS_PASS',added,flush=True)
finally:asset_entrypoints.unregister()
