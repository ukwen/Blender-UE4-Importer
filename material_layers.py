"""Bounded UE4 layer stacks and detached snapshots with conservative scalar replay."""
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


def build(tree,data,graph,load,mesh,records=None):
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
        layers,blends,states=records if records is not None else stack_records(data.export.properties)
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
        graph.layer_context=(data,load,mesh,(layers,blends,states))
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


def explicit_override(props, graph):
    """Accept only one complete, detached snapshot, not parent-link reconciliation."""
    from types import SimpleNamespace
    from uuid import UUID
    containers=[props]
    for key in ('StaticParameters','StaticParametersRuntime'):
        p=props.get(key)
        if p is not None:
            if hasattr(p,'raw') or not hasattr(p.value,'TryGetValue'):
                raise ValueError('Unreadable static parameter set')
            containers.append(p.value)
    records=[]
    for c in containers:
        p=c.get('MaterialLayersParameters')
        if p is not None:
            if hasattr(p,'raw') or getattr(p,'parse_error',None) or not isinstance(p.value,list):
                raise ValueError('Unreadable layer override records')
            records.extend(p.value)
    if not records: return None
    if len(records)!=1: raise ValueError('Multiple layer overrides unsupported')
    record=records[0].value
    if not hasattr(record,'TryGetValue'): raise ValueError('Invalid layer override record')
    enabled=record.TryGetValue('bOverride',False)
    if type(enabled) is not bool: raise ValueError('Invalid layer override flag')
    if not enabled: return False
    if not hasattr(graph,'layer_context'): raise ValueError('No default layer stack')
    data,_,_,_=graph.layer_context
    info=record.TryGetValue('ParameterInfo')
    if not hasattr(info,'TryGetValue') or info.TryGetValue('Association','GlobalParameter') not in ('GlobalParameter',2) or info.TryGetValue('Index',-1)!=-1:
        raise ValueError('Invalid layer override scope')
    name=info.TryGetValue('Name'); expected=data.export.properties.TryGetValue('ParameterName')
    if not isinstance(name,str) or not isinstance(expected,str) or name.casefold()!=expected.casefold():
        raise ValueError('Layer parameter name mismatch')
    value=record.TryGetValue('Value')
    snapshot=stack_records(SimpleNamespace(TryGetValue=lambda key: value))
    def values(key):
        p=value.get(key)
        if p is None or getattr(p,'parse_error',None): raise ValueError('Missing '+key)
        return [entry.value for entry in p.value]
    guids=values('LayerGuids'); links=values('LayerLinkStates')
    if len(guids)!=len(snapshot[0]) or len(set(guids))!=len(guids) or any(not isinstance(g,UUID) or not g.int for g in guids):
        raise ValueError('Invalid layer GUIDs')
    if len(links)!=len(guids) or any(str(v).split('::')[-1] not in ('NotFromParent','UnlinkedFromParent') for v in links):
        raise ValueError('Parent-linked layer reconciliation unsupported')
    remap_scalars(graph,snapshot,guids)
    return snapshot,guids


def reference_key(ref):
    from material_stage import package_reference
    # String references occur only in controlled fixtures; native references
    # must resolve to the original canonical package, never a basename.
    return ref if isinstance(ref,str) else package_reference(ref)


def remap_scalars(graph,snapshot,guids):
    """Replay only known successful scalar overrides on unchanged functions.

    A blend is identified by its upper layer GUID and its function package.
    No claim of general Unreal parent-linked reconciliation is made.
    """
    if getattr(graph,'layer_topology_unresolved',False) or getattr(graph,'scoped_remap_blocked',False):
        raise ValueError('Cannot remap inherited scoped parameters safely')
    ledger=getattr(graph,'scoped_scalar_records',{})
    if not getattr(graph,'scoped_history',False): return {}
    old_ids=getattr(graph,'layer_guids',None)
    if not old_ids or not ledger:
        raise ValueError('Missing stable identity or inherited scalar records')
    old_layers,old_blends,old_states=graph.layer_context[3]
    layers,blends,states=snapshot
    result={}
    for (scope,index,name),record in ledger.items():
        old_slot=index if scope=='LayerParameter' else index+1
        if not 0<=old_slot<len(old_ids) or old_ids[old_slot] not in guids:
            raise ValueError('Overridden layer was removed')
        slot=guids.index(old_ids[old_slot])
        if not old_states[old_slot] or not states[slot]:
            raise ValueError('Overridden layer disabled')
        if scope=='LayerParameter':
            old_ref,new_ref=old_layers[old_slot],layers[slot]
            dst=slot
        else:
            if slot==0: raise ValueError('Overridden blend moved to background')
            old_ref,new_ref=old_blends[index],blends[slot-1]
            dst=slot-1
        if not reference_key(old_ref) or reference_key(old_ref)!=reference_key(new_ref):
            raise ValueError('Overridden function package changed')
        result[scope,dst,name]=record
    return result


def replace_snapshot(mat,graph,snapshot,guids):
    """Build off to the side; swap only after all functions and links validate."""
    import bpy
    from types import SimpleNamespace
    from material_stage import incomplete_graph
    replay=remap_scalars(graph,snapshot,guids)
    data,load,mesh,_=graph.layer_context
    tree=mat.node_tree; old=data.node
    staging=SimpleNamespace(stack=graph.stack,scoped_param_nodes={})
    trial=SimpleNamespace(export=data.export)
    stores=(bpy.data.node_groups,bpy.data.images)
    before={item.as_pointer() for store in stores for item in store}
    incoming=[(s.name,l.from_socket) for s in old.inputs for l in s.links]
    outgoing=[(s.name,l.to_socket) for s in old.outputs for l in s.links]
    try:
        new=build(tree,trial,staging,load,mesh,records=snapshot)
        group=new.node_tree
        if new.get('UE_attribute_error') or incomplete_graph(group):
            raise ValueError('Replacement layer stack incomplete')
        for key,(value,count) in replay.items():
            targets=[t for t in staging.scoped_param_nodes.get(key,[]) if t.classname=='MaterialExpressionScalarParameter']
            if len(targets)!=count: raise ValueError('Inherited scalar target count changed')
            for t in targets: t.node.outputs[0].default_value=value
        # Preserve the original external links explicitly rather than rely on interface IDs.
        if trial.layer_needs_input and not incoming:
            raise ValueError('Replacement requires missing base attribute input')
        new.location=old.location.copy(); new.label=old.label
        new['UE_layer_guids']=json.dumps([str(g) for g in guids])
        for key,source in incoming: tree.links.new(source,new.inputs[key])
        for key,target in outgoing: tree.links.new(new.outputs[key],target)
        name=old.name; old_group=old.node_tree
        tree.nodes.remove(old); new.name=name
        data.node=new; data.layer_needs_input=trial.layer_needs_input
        graph.scoped_param_nodes=staging.scoped_param_nodes
        graph.layer_context=(data,load,mesh,snapshot)
        graph.layer_guids=list(guids)
        graph.scoped_scalar_records=replay
    except Exception:
        if getattr(trial,'node',None) is not None:
            tree.nodes.remove(trial.node)
        # Restore outgoing links in case a connection failed mid-swap.
        for key,target in outgoing: tree.links.new(old.outputs[key],target)
        # Remove only newly created groups/images, never the existing imported stack.
        created=[item for store in stores for item in store if item.as_pointer() not in before]
        if created: bpy.data.batch_remove(ids=created)
        raise
    if old_group.users==0: bpy.data.node_groups.remove(old_group)
