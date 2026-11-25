"""Native base property table and controlled tagged global static switch regression."""
import io, os, struct, sys, tempfile
from pathlib import Path
from types import SimpleNamespace as NS
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uasset, umat, material_instance as mi

with uasset.UAsset(os.environ['UE_GOBLIN_BASE'], False) as asset:
    exp = next(e for e in asset.exports if e.export_class_type == 'Material')
    asset.f.Seek(exp.serial_desc.offset)
    props = uasset.Properties().Read(asset, read_children=False)
    assert len(props) == 21 and len(props.TryGetValue('Expressions')) == 16
    assert len(props.TryGetValue('ParameterGroupData')) == 13
    p = props['ParameterOverviewExpansion']
    assert p.key_type == 'StrProperty' and p.value_type == 'BoolProperty' and len(p.value) == 44
    assert 'LightingGuid' in props and asset.f.Position() <= exp.serial_desc.offset + exp.serial_desc.count
    print('BASE_PROPERTY_TABLE_PASS', len(props), 'end', asset.f.Position())

# Synthetic tagged records, different lengths, using the actual binary reader.
names = ['None', 'StaticSwitchParameters', 'ArrayProperty', 'StructProperty', 'StaticSwitchParameter', 'ParameterName', 'NameProperty', 'Wind', 'bOverride', 'BoolProperty', 'Value', 'Wet', 'StaticParameters', 'StaticParameterSet']
fn = lambda n: struct.pack('<ii', names.index(n), 0)
head = lambda n,t,l: fn(n)+fn(t)+struct.pack('<ii',l,0)
name = lambda k,v: head(k,'NameProperty',8)+b'\0'+fn(v)
boolean = lambda k,v: head(k,'BoolProperty',0)+bytes([v,0])
r1 = name('ParameterName','Wind')+boolean('bOverride',1)+boolean('Value',1)+fn('None')
r2 = name('ParameterName','Wet')+boolean('bOverride',0)+fn('None')
arr = (struct.pack('<i',2)+fn('StaticSwitchParameters')+fn('StructProperty')+struct.pack('<q',len(r1+r2))+fn('StaticSwitchParameter')+bytes(16)+b'\0'+r1+r2)
inner = head('StaticSwitchParameters','ArrayProperty',len(arr))+fn('StructProperty')+b'\0'+arr+fn('None')
outer = head('StaticParameters','StructProperty',len(inner))+fn('StaticParameterSet')+bytes(16)+b'\0'+inner+fn('None')
f = uasset.ByteStream(io.BytesIO(outer))
asset = NS(f=f,names=names,summary=NS(version_ue4=522),TryReadPropertyGuid=lambda: f.ReadGuid() if f.ReadBool() else None)
p = uasset.Properties().Read(asset)
assert f.Position() == len(outer)
assert mi.read_overrides(p) == ([('switch','Wind',True)],[])
print('TAGGED_STATIC_SWITCH_PASS')

def props(**items):
    p = uasset.Properties()
    for k,v in items.items(): p[k]=NS(value=v)
    return p

def override(value, enable=True, scope='GlobalParameter'):
    return props(StaticParameters=props(StaticSwitchParameters=[NS(value=props(ParameterInfo=props(Name='wInD',Association=scope,Index=-1),bOverride=enable,Value=value))]))

def graph(name):
    m = bpy.data.materials.new(name); m.use_nodes=True; m.use_fake_user=True
    g = umat.GraphData()
    e = NS(object_name='WindSwitch', export_class_type='MaterialExpressionStaticSwitchParameter',properties=props(ParameterName='Wind',DefaultValue=True))
    n = umat.CreateNode(e,m.node_tree,g.nodes_data,g).node
    assert n.inputs['Fac'].default_value == 1 and not n.use_clamp
    n.inputs[1].default_value=(.1,.2,.3,1); n.inputs[2].default_value=(.8,.7,.6,1)
    m.node_tree.links.new(n.outputs[0],m.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
    return m,g,n
m,g,n=graph('ChildSwitch'); sibling,sg,sn=graph('SiblingSwitch')
assert not mi.apply_overrides(m,g,p,None,None)[1]
assert n.inputs['Fac'].default_value==1
assert not mi.apply_overrides(m,g,override(False),None,None)[1]
assert n.inputs['Fac'].default_value==0 and sn.inputs['Fac'].default_value==1
assert not mi.apply_overrides(m,g,override(True,False),None,None)[1]
assert n.inputs['Fac'].default_value==0
assert mi.apply_overrides(m,g,override(True,True,'LayerParameter'),None,None)[1]
assert n.inputs['Fac'].default_value==0
assert mi.read_overrides(props(StaticParameters=props(StaticComponentMaskParameters=[1])))[1]
e=NS(object_name='TrueBool',export_class_type='MaterialExpressionStaticBool',properties=props(Value=True))
assert umat.CreateNode(e,m.node_tree,g.nodes_data,g).node.outputs[0].default_value==1
with tempfile.TemporaryDirectory() as tmp:
    path=str(Path(tmp)/'switches.blend'); bpy.ops.wm.save_as_mainfile(filepath=path); bpy.ops.wm.open_mainfile(filepath=path)
    assert bpy.data.materials['ChildSwitch'].node_tree.nodes['WindSwitch'].inputs['Fac'].default_value==0
    assert bpy.data.materials['SiblingSwitch'].node_tree.nodes['WindSwitch'].inputs['Fac'].default_value==1
print('STATIC_SWITCH_INHERITANCE_REOPEN_PASS')
