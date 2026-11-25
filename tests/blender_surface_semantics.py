"""Genuine UE4 surface records, controlled channel and binary opacity tests."""
import io, os, struct, sys, tempfile
from pathlib import Path
from types import SimpleNamespace as NS
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uasset, umat, surface_semantics as ss

with uasset.UAsset(os.environ['UE_GOBLIN_BASE'], True) as asset:
    root=next(e for e in asset.exports if e.export_class_type=='Material')
    expected={'BaseColor':'MaterialExpressionMultiply_0','Metallic':'MaterialExpressionScalarParameter_1','Roughness':'MaterialExpressionScalarParameter_2','Normal':'MaterialExpressionMultiply_2','EmissiveColor':'MaterialExpressionMultiply_6','WorldPositionOffset':'MaterialExpressionMaterialFunctionCall_1'}
    for name, expr_name in expected.items():
        inp=root.properties[name].material_input
        assert inp.node.object_name==expr_name and inp.node_output_i==0 and not inp.use_constant
    assert abs(root.properties['Roughness'].material_input.constant-.5)<1e-6
    masks=[p.value.mask_rgba for exp in asset.exports for p in exp.properties.values() if getattr(p,'struct_type','')=='ExpressionInput' and p.value.mask]
    assert len(masks)==5 and all(tuple(x)==(1,1,1,0) for x in masks)
print('GENUINE_SURFACE_INPUTS_PASS',len(expected),len(masks))

# Actual tagged scalar material input with zero expression index and explicit constant.
names=['None','Roughness','StructProperty','ScalarMaterialInput']
fn=lambda n: struct.pack('<ii',names.index(n),0)
raw=fn('Roughness')+fn('StructProperty')+struct.pack('<ii',44,0)+fn('ScalarMaterialInput')+bytes(16)+b'\0'+struct.pack('<10if',0,0,0,0,0,0,0,0,0,1,.73)+fn('None')
f=uasset.ByteStream(io.BytesIO(raw))
a=NS(f=f,names=names,summary=NS(version_ue4=522),GetExport=lambda i: (_ for _ in ()).throw(AssertionError('null expression must not resolve')),TryReadPropertyGuid=lambda: f.ReadGuid() if f.ReadBool() else None)
p=uasset.Properties().Read(a)
assert f.Position()==len(raw) and p['Roughness'].value is None and p['Roughness'].material_input.use_constant
m=bpy.data.materials.new('SurfaceSemantics'); m.use_nodes=True; m.use_fake_user=True
tree=m.node_tree; shader=tree.nodes['Principled BSDF']; d=NS(node=shader,input_remap=None)
assert umat.TryLinkSocket(tree,{},d,p['Roughness'],'Roughness','Roughness')
assert abs(shader.inputs['Roughness'].default_value-.73)<1e-6
print('TAGGED_CONSTANT_PASS')

# Preserve explicitly selected outputs even if hidden, and select an exact channel.
tex=tree.nodes.new('ShaderNodeTexImage'); sep=tree.nodes.new('ShaderNodeSeparateXYZ'); tree.links.new(tex.outputs['Color'],sep.inputs[0]); sep.outputs[1].hide=True
exp=NS(object_name='Texture'); src=NS(classname='MaterialExpressionTextureSample',node=sep,link_indirect=None)
inp=NS(node=exp,node_output_i=1,mask=0,mask_rgba=(0,0,0,0))
prop=NS(struct_type='ExpressionInput',value=inp)
assert umat.TryLinkSocket(tree,{'Texture':src},d,prop,'Metallic','Metallic')
assert shader.inputs['Metallic'].links[0].from_socket==sep.outputs[1]
# Vector RGB mask, exact G extraction; multi-channel swizzle must fail closed.
inp.mask=1; inp.mask_rgba=(0,1,0,0); inp.node_output_i=0
src.node=tex
assert umat.TryLinkSocket(tree,{'Texture':src},d,prop,'Roughness','Roughness')
link=shader.inputs['Roughness'].links[0]
assert link.from_socket.name=='Y' and link.from_node.bl_idname=='ShaderNodeSeparateXYZ'
inp.mask_rgba=(1,0,1,0)
assert not umat.TryLinkSocket(tree,{'Texture':src},d,prop,'Roughness','Roughness') and tree['Error']
print('EXACT_CHANNEL_SELECTION_PASS')

# Binary threshold, inheritance update and restoring the original alpha source.
value=tree.nodes.new('ShaderNodeValue'); value.outputs[0].default_value=.4
tree.links.new(value.outputs[0],shader.inputs['Alpha'])
ss.set_opacity_clip(m,.4)
clip=tree.nodes['UE_OpacityClip']; visible=tree.nodes['UE_OpacityVisible']
assert clip.operation=='LESS_THAN' and visible.operation=='SUBTRACT'
assert clip.inputs[0].links[0].from_socket==value.outputs[0]
assert shader.inputs['Alpha'].links[0].from_node==visible
ss.set_opacity_clip(m,.6)
assert abs(clip.inputs[1].default_value-.6)<1e-6 and len([n for n in tree.nodes if n.name=='UE_OpacityClip'])==1
ss.clear_opacity_clip(m)
assert shader.inputs['Alpha'].links[0].from_node==value and not tree.nodes.get('UE_OpacityClip')
ss.set_opacity_clip(m,.4)
# Validate emission using the genuine material graph, not a fabricated native shader.
with tempfile.TemporaryDirectory() as tmp:
    out=str(Path(tmp)/'surface.blend'); bpy.ops.wm.save_as_mainfile(filepath=out); bpy.ops.wm.open_mainfile(filepath=out)
    mat=bpy.data.materials['SurfaceSemantics']; assert abs(mat['UE_opacity_mask_clip']-.4)<1e-6
    assert mat.node_tree.nodes['Principled BSDF'].inputs['Alpha'].links[0].from_node.name=='UE_OpacityVisible'
print('OPACITY_REOPEN_PASS')

# The original material, not synthetic images or a mock function. In the supplied
# partial project its three texture packages and wind function are absent.
from unittest.mock import patch
base=Path(os.environ['GOBLIN_CONTENT'])/'Materials/Base/M_PolygonGoblinWarCamp_Base.uasset'
with patch.object(umat.subprocess,'run',side_effect=AssertionError('Missing dependencies must not launch UModel')):
    native,graph=umat.ImportNodeGraph(str(base))
assert native['UE_material_status']=='partial_graph_unresolved' and native['UE_unresolved_material']
assert native['UE_unimplemented_surface_inputs']=='WorldPositionOffset'
assert len(native.node_tree.nodes)==24 and len(native.node_tree.links)==28
shader=native.node_tree.nodes['Principled BSDF']
assert all(shader.inputs[n].is_linked for n in ('Base Color','Metallic','Roughness','Normal','Emission Color'))
assert shader.inputs['Emission Strength'].default_value==1
tex=[n for n in native.node_tree.nodes if n.type=='TEX_IMAGE']
assert len(tex)==3 and all(n.image is None and n['UE_texture_package'].startswith('/Game/') for n in tex)
assert len(graph.param_nodes)==10 and native.node_tree.get('UE_missing_functions')
# Keep the saved evidence focused on the real graph, without controlled fixtures.
for m in list(bpy.data.materials):
    if m != native: bpy.data.materials.remove(m)
native.use_fake_user=True
bpy.ops.mesh.primitive_plane_add()
bpy.context.object.name='Diagnostic material swatch - unresolved source textures'
bpy.context.object.data.materials.append(native)
output=os.environ.get('UE_MATERIAL_PREVIEW')
if output: bpy.ops.wm.save_as_mainfile(filepath=output)
print('GENUINE_PARTIAL_BASE_GRAPH_PASS',len(native.node_tree.nodes),len(native.node_tree.links),len(graph.param_nodes))
