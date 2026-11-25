"""Run: blender -b --factory-startup --python-exit-code 1 --python tests/blender_smoke.py"""
import importlib.util
from pathlib import Path
import sys
import bpy

assert bpy.app.version[:2] == (4, 2), bpy.app.version_string
root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ue_importer_dev", root / "__init__.py", submodule_search_locations=[str(root)])
addon = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = addon
spec.loader.exec_module(addon)
addon.register()
try:
    for operator in tuple(getattr(getattr(bpy.ops, 'import'), name) for name in ('umap', 'umesh', 'umat')):
        assert operator.get_rna_type().properties.get("files") is not None
    mat = bpy.data.materials.new("Compatibility test")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    for name in ("Specular IOR Level", "Emission Color", "Transmission Weight"):
        assert name in bsdf.inputs
    mat.surface_render_method = "DITHERED"
    tree = bpy.data.node_groups.new("Interface test", "ShaderNodeTree")
    tree.interface.new_socket(name="Input", in_out="INPUT", socket_type="NodeSocketFloat")
    for kind in ("SPHERE", "VOLUME"):
        bpy.data.lightprobes.new(kind, kind)
    print("BLENDER_SMOKE_PASS", bpy.app.version_string)
finally:
    addon.unregister()
