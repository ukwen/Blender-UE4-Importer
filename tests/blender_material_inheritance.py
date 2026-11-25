"""Genuine Goblin scalar records plus controlled inheritance and function interface tests."""
import json, os, sys, tempfile, uuid
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uasset, umat, material_instance as mi


def props(**items):
    p = uasset.Properties()
    for k,v in items.items(): p[k] = NS(value=v)
    return p


def entry(name,value,kind='GlobalParameter',index=-1):
    return NS(value=props(ParameterInfo=props(Name=name,Association=kind,Index=index),ParameterValue=value))


umat.TryAppendNodeGroups()
with uasset.UAsset(os.environ['UE_GOBLIN_MI'], True) as asset:
    e=next(e for e in asset.exports if e.export_class_type=='MaterialInstanceConstant')
    records,issues=mi.read_overrides(e.properties)
    assert not issues and len(records)==9
    actual={n:v for _,n,v in records}
    assert abs(actual['Roughness']-.85)<1e-6 and actual['Metallic']==1 and actual['WindSpeed']==0
    mat=bpy.data.materials.new('Goblin scalar evidence'); mat.use_nodes=True
    graph=umat.GraphData()
    for name,val in actual.items():
        node=mat.node_tree.nodes.new('ShaderNodeValue'); node.name=name
        graph.param_nodes[name]=[NS(node=node,classname='MaterialExpressionScalarParameter')]
    applied,issues=mi.apply_overrides(mat,graph,e.properties,None,None)
    assert len(applied)==9 and not issues
    assert all(abs(mat.node_tree.nodes[n].outputs[0].default_value-v)<1e-6 for n,v in actual.items())
    print('GENUINE_GOBLIN_SCALARS_PASS',actual)

# Parent and child overrides on independent real Blender graphs.
def graph_fixture(name):
    m=bpy.data.materials.new(name); m.use_nodes=True
    g=umat.GraphData(); t=m.node_tree
    s=t.nodes.new('ShaderNodeValue'); s.outputs[0].default_value=.1
    v=t.nodes.new('ShaderNodeGroup'); v.node_tree=bpy.data.node_groups['RGBA']
    tex=t.nodes.new('ShaderNodeTexImage')
    g.param_nodes={'Roughness':[NS(node=s,classname='MaterialExpressionScalarParameter')],
        'Tint':[NS(node=v,classname='MaterialExpressionVectorParameter')],
        'Diffuse':[NS(node=tex,classname='MaterialExpressionTextureSampleParameter2D')]}
    return m,g,s,v,tex

m,g,s,v,t=graph_fixture('Child'); sibling,sg,ss,sv,st=graph_fixture('Sibling')
a=bpy.data.images.new('ImageA',1,1); a['nearest']=True; a['clamp']=True
b=bpy.data.images.new('ImageB',1,1)
ra,rb=NS(asset=NS(extract_dir=''),image=a),NS(asset=NS(extract_dir=''),image=b)
load=lambda ref,_: ref.image
parent=props(ScalarParameterValues=[entry('Roughness',.7)],VectorParameterValues=[entry('Tint',uasset.FLinearColor(.2,.4,.6,.8))],TextureParameterValues=[entry('Diffuse',ra)])
child=props(ScalarParameterValues=[entry('roughness',.3)],TextureParameterValues=[entry('Diffuse',rb)])
assert not mi.apply_overrides(m,g,parent,load,umat.SetNodeTexture)[1]
assert t.image==a and t.interpolation=='Closest' and t.extension=='CLIP'
assert not mi.apply_overrides(m,g,child,load,umat.SetNodeTexture)[1]
assert abs(s.outputs[0].default_value-.3)<1e-6 and abs(v.inputs['A'].default_value-.8)<1e-6
assert t.image==b and t.interpolation=='Linear' and t.extension=='REPEAT'
assert abs(ss.outputs[0].default_value-.1)<1e-6 and st.image is None
assert len(json.loads(m['UE_instance_overrides']))==2
assert mi.apply_overrides(m,g,props(ScalarParameterValues=[entry('Roughness',.9,'LayerParameter',1)]),load,umat.SetNodeTexture)[1]
assert abs(s.outputs[0].default_value-.3)<1e-6 and m.node_tree['Error']
print('TYPED_INHERITANCE_AND_SCOPE_PASS')

# Two same-named functions with distinct interface ordering; no global cache alias.
def fn_fixture():
    ng=bpy.data.node_groups.new('SameFunction','ShaderNodeTree')
    ins=[ng.interface.new_socket(name=n,in_out='INPUT',socket_type='NodeSocketFloat') for n in ('A','B')]
    outs=[ng.interface.new_socket(name=n,in_out='OUTPUT',socket_type='NodeSocketFloat') for n in ('X','Y')]
    ng['UE_input_ids']=json.dumps({'a':ins[0].identifier,'b':ins[1].identifier})
    ng['UE_output_ids']=json.dumps({'x':outs[0].identifier,'y':outs[1].identifier})
    fg=umat.GraphData(); n=ng.nodes.new('ShaderNodeValue'); fg.param_nodes={'Inner':[NS(node=n,classname='MaterialExpressionScalarParameter')]}
    return ng,fg
f1,fg1=fn_fixture(); f2,fg2=fn_fixture()
param=props(MaterialFunction=NS(object_name='SameFunction'),FunctionInputs=[props(ExpressionInputId='b'),props(ExpressionInputId='a')],FunctionOutputs=[props(ExpressionOutputId='y'),props(ExpressionOutputId='x')])
exp=lambda name:NS(object_name=name,export_class_type='MaterialExpressionMaterialFunctionCall',properties=param)
with patch.object(umat,'ImportMaterialFunction',side_effect=[(f1,fg1),(f2,fg2)]):
    n1=umat.CreateNode(exp('Call1'),m.node_tree,g.nodes_data,g)
    n2=umat.CreateNode(exp('Call2'),sibling.node_tree,sg.nodes_data,sg)
assert n1.node.node_tree==f1 and n2.node.node_tree==f2
assert n1.mapping.inputs['FunctionInputs']==(1,0)
assert [x.name for x in n1.link_indirect]==['Y','X']
assert not mi.apply_overrides(m,g,props(ScalarParameterValues=[entry('Inner',.6)]),load,umat.SetNodeTexture)[1]
assert abs(fg1.param_nodes['Inner'][0].node.outputs[0].default_value-.6)<1e-6
assert fg2.param_nodes['Inner'][0].node.outputs[0].default_value==0
assert 'SameFunction' not in umat.UE2BlenderNode_dict
try: umat.ImportNodeGraph('/tmp/cycle.uasset',_stack=('/tmp/cycle.uasset',))
except ValueError: pass
else: raise AssertionError('Cycle accepted')
print('FUNCTION_INTERFACE_ISOLATION_CYCLE_PASS')
with tempfile.TemporaryDirectory() as d:
    m.use_fake_user=True; sibling.use_fake_user=True
    out=str(Path(d)/'inheritance.blend'); bpy.ops.wm.save_as_mainfile(filepath=out); bpy.ops.wm.open_mainfile(filepath=out)
    assert bpy.data.materials['Child'].get('UE_instance_overrides')
    assert bpy.data.materials['Child'].node_tree.nodes['Call1'].node_tree!=bpy.data.materials['Sibling'].node_tree.nodes['Call2'].node_tree
print('INHERITANCE_REOPEN_PASS')
