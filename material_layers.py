"""Bounded default UE4 material layer stacks; no instance topology remapping."""
import json
from material_attributes import FIELDS, by_id, bundle_source, fail


def stack_records(props):
    p = props.TryGetValue('DefaultLayers')
    if not hasattr(p, 'TryGetValue'):
        raise ValueError('Unreadable DefaultLayers')
    def values(key):
        prop = p.get(key)
        if prop is None or getattr(prop, 'parse_error', None):
            raise ValueError('Missing or invalid layer array: '+key)
        return [entry.value for entry in prop.value]
    layers, blends, states = (values(k) for k in ('Layers','Blends','LayerStates'))
    if not 1 <= len(layers) <= 32 or len(blends)!=len(layers)-1 or len(states)!=len(layers):
        raise ValueError('Invalid layer stack lengths')
    if any(type(v) is not bool for v in states) or not states[0] or layers[0] is None:
        raise ValueError('Unsupported disabled or missing background layer')
    if any(enabled and ref is None for ref,enabled in zip(layers,states)):
        raise ValueError('Missing active layer')
    return layers,blends,states


def build(tree,data,graph,load,mesh):
    import bpy
    group=bpy.data.node_groups.new('UE default layer stack','ShaderNodeTree')
    for direction in ('INPUT','OUTPUT'):
        for field,value in FIELDS.items():
            s=group.interface.new_socket(name=field,in_out=direction,socket_type='NodeSocketVector' if isinstance(value,tuple) else 'NodeSocketFloat')
            s.default_value=value
    node=tree.nodes.new('ShaderNodeGroup'); node.node_tree=group; node.name=data.export.object_name
    node.label='UE default material layers'; data.node=node; data.attribute_bundle=True; data.layer_stack=True
    inp=group.nodes.new('NodeGroupInput'); out=group.nodes.new('NodeGroupOutput')
    registry={}; data.layer_needs_input=False
    try:
        if getattr(graph,'inside_function',False): raise ValueError('Layer stack inside function unsupported')
        if getattr(graph,'layer_stack_present',False): raise ValueError('Multiple layer stacks unsupported')
        graph.layer_stack_present=True
        layers,blends,states=stack_records(data.export.properties)
        def call(ref,scope,index,sources):
            fn,fg=load(ref,mesh,graph.stack)
            expected='MaterialLayer' if scope=='LayerParameter' else 'MaterialLayerBlend'
            if fn.get('UE_function_usage')!=expected: raise ValueError('Invalid function usage: '+expected)
            ids=json.loads(fn['UE_input_ids']); outputs=json.loads(fn['UE_output_ids'])
            order=json.loads(fn['UE_input_order'])
            if len(order)!=len(ids) or set(order)!=set(ids) or len(outputs)!=1:
                raise ValueError('Ambiguous layer function interface')
            if scope=='LayerParameter':
                if len(order)>1: raise ValueError('Layer accepts at most one bundle')
                if order: data.layer_needs_input=True
                sources=sources[:len(order)]
            elif len(order)!=2: raise ValueError('Blend requires two bundles')
            if len(order)!=len(sources) or any(not isinstance(ids[k],dict) or set(ids[k])!=set(FIELDS) for k in order):
                raise ValueError('Invalid layer function input fields')
            result=next(iter(outputs.values()))
            if not isinstance(result,dict) or set(result)!=set(FIELDS): raise ValueError('Expected one bundle output')
            n=group.nodes.new('ShaderNodeGroup'); n.node_tree=fn; n.label=f'{scope} {index}: {fn.name}'; n.location=(index*420,0 if scope=='LayerParameter' else -350)
            for key,src in zip(order,sources):
                for field in FIELDS: group.links.new(src[field],by_id(n.inputs,ids[key][field]))
            for name,entries in fg.param_nodes.items(): registry.setdefault((scope,index,name.casefold()),[]).extend(entries)
            return {field:by_id(n.outputs,result[field]) for field in FIELDS}
        current=None
        for i,ref in enumerate(layers):
            if not states[i]: continue
            top=call(ref,'LayerParameter',i,[inp.outputs])
            current=call(blends[i-1],'BlendParameter',i-1,[current,top]) if i and blends[i-1] is not None else top
        for field in FIELDS: group.links.new(current[field],out.inputs[field])
        graph.scoped_param_nodes.update(registry)
        node['UE_layer_states']=json.dumps(states)
    except (ValueError,KeyError,TypeError,AttributeError,FileNotFoundError,RuntimeError) as exc:
        graph.layer_topology_unresolved=True
        fail(tree,node,str(exc)); group['Error']=True
    return node


def connect(tree,nodes,data):
    if data.node.get('UE_attribute_error'): return
    prop=data.export.properties.get('Input')
    if not prop or getattr(prop.value,'node',None) is None:
        if data.layer_needs_input: fail(tree,data.node,'Layer input preview defaults unsupported')
        return
    try:
        source=bundle_source(nodes,prop)
        for field in FIELDS: tree.links.new(source[field],data.node.inputs[field])
    except (ValueError,KeyError,AttributeError) as exc: fail(tree,data.node,str(exc))
