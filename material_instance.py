"""Typed global material-instance overrides; unsupported scopes remain explicit."""
import math
import json

KINDS = {'ScalarParameterValues': 'scalar', 'VectorParameterValues': 'vector',
         'TextureParameterValues': 'texture', 'StaticSwitchParameters': 'switch',
         'StaticSwitchParameterValues': 'switch'}
CLASSES = {'MaterialExpressionScalarParameter': 'scalar',
           'MaterialExpressionVectorParameter': 'vector',
           'MaterialExpressionTextureSampleParameter2D': 'texture',
           'MaterialExpressionTextureObjectParameter': 'texture',
           'MaterialExpressionStaticSwitchParameter': 'switch'}


def read_overrides(props, scoped=False):
    """Read legacy flat names or modern MaterialParameterInfo global names."""
    records, issues = [], []
    containers = [props]
    for key in ('StaticParameters', 'StaticParametersRuntime'):
        value = props.TryGetValue(key)
        if value is not None:
            if hasattr(value, 'TryGetValue') and not hasattr(props.get(key), 'raw'):
                containers.append(value)
            else:
                issues.append(f'Unreadable static parameter set: {key}')
    seen_switches = set()
    for source in containers:
      for array, kind in KINDS.items():
        if source is not props and kind != 'switch':
            continue
        prop = source.get(array)
        if prop is None:
            continue
        if getattr(prop, 'parse_error', None):
            issues.append(f'{array}: {prop.parse_error}')
            continue
        seen = set()
        for entry in source.TryGetValue(array, ()):
            try:
                p = entry.value
                info = p.TryGetValue('ParameterInfo')
                scope,index='GlobalParameter',-1
                if info is not None:
                    name = info.TryGetValue('Name')
                    association = info.TryGetValue('Association', 'GlobalParameter')
                    index = info.TryGetValue('Index', -1)
                    scope={0:'LayerParameter',1:'BlendParameter',2:'GlobalParameter'}.get(association,str(association).split('::')[-1])
                    if not ((scope=='GlobalParameter' and index==-1) or (scoped and scope in ('LayerParameter','BlendParameter') and type(index) is int and index>=0)):
                        raise ValueError(f'unsupported parameter scope {name}: {association}/{index}')
                else:
                    name = p.TryGetValue('ParameterName')
                if not isinstance(name, str) or not name or name == 'None':
                    raise ValueError('missing parameter name')
                key = (scope,index,name.casefold())
                if key in seen:
                    raise ValueError(f'duplicate {kind} parameter {name}')
                seen.add(key)
                if kind == 'switch':
                    override = p.TryGetValue('bOverride', False)
                    if type(override) is not bool:
                        raise ValueError(f'invalid static override flag {name}')
                    if not override:
                        continue
                    value = p.TryGetValue('Value', p.TryGetValue('ParameterValue', False))
                    if type(value) is not bool or key in seen_switches:
                        raise ValueError(f'invalid or duplicate static switch {name}')
                    seen_switches.add(key)
                else:
                    if 'ParameterValue' not in p:
                        raise ValueError(f'missing value for {name}')
                    value = p.TryGetValue('ParameterValue')
                if kind == 'scalar' and (not isinstance(value, (int, float)) or not math.isfinite(value)):
                    raise ValueError(f'invalid scalar {name}')
                if kind == 'vector':
                    value = tuple(value.ToTuple())
                    if len(value) != 4 or not all(math.isfinite(x) for x in value):
                        raise ValueError(f'invalid vector {name}')
                records.append((kind, name, value, scope, index) if scoped else (kind, name, value))
            except (ValueError, AttributeError, TypeError) as exc:
                issues.append(f'{array}: {exc}')
    for source in containers:
        for key in ('StaticComponentMaskParameters', 'StaticComponentMaskParameterValues', 'MaterialLayersParameters', 'TerrainLayerWeightParameters'):
            if source.TryGetValue(key):
                issues.append(f'Unsupported static/layer parameter data: {key}')
        if source is not props:
            for key in source:
                if key not in KINDS and key not in ('StaticComponentMaskParameters', 'StaticComponentMaskParameterValues', 'MaterialLayersParameters', 'TerrainLayerWeightParameters'):
                    issues.append(f'Unsupported static parameter field: {key}')
    return records, issues


def apply_overrides(mat, graph, props, load_texture, set_texture):
    scoped_targets=getattr(graph,'scoped_param_nodes',{})
    records, issues = read_overrides(props, scoped=bool(scoped_targets))
    containers=[props]
    for key in ('StaticParameters','StaticParametersRuntime'):
        value=props.TryGetValue(key)
        if value is not None:
            if hasattr(value,'TryGetValue') and not hasattr(props.get(key),'raw'): containers.append(value)
            else: graph.layer_topology_unresolved=True
    for c in containers:
        p=c.get('MaterialLayersParameters')
        if p is not None and (p.value or getattr(p,'parse_error',None) or hasattr(p,'raw')):
            graph.layer_topology_unresolved=True
    applied = []
    for record in records:
        kind,name,value=record[:3]
        scope,index=record[3:] if len(record)==5 else ('GlobalParameter',-1)
        if scope!='GlobalParameter':
            if getattr(graph,'layer_topology_unresolved',False):
                issues.append(f'Unresolved layer topology: {name}')
                continue
            candidates=scoped_targets.get((scope,index,name.casefold()),[])
        else:
            candidates=[n for key,nodes in graph.param_nodes.items() if key.casefold()==name.casefold() for n in nodes]
        targets=[n for n in candidates if CLASSES.get(n.classname)==kind]
        if not targets:
            issues.append(f'No supported {kind} target: {name}')
            continue
        if kind == 'texture':
            texture_nodes = [node for t in targets for node in ([t.node] if t.node.bl_idname == 'ShaderNodeTexImage' else getattr(t, 'linked_tex_nodes', []))]
            if not texture_nodes or value is None:
                issues.append(f'Unsupported or null texture override: {name}')
                continue
            image = load_texture(value, value.asset.extract_dir)
            if image is None:
                issues.append(f'Missing texture override: {name}')
                continue
            for node in texture_nodes:
                set_texture(node, image)
                from material_stage import package_reference
                package = package_reference(value)
                if package: node['UE_texture_package'] = package
        elif kind == 'switch':
            if any(t.node.bl_idname not in ('ShaderNodeMixRGB', 'ShaderNodeMix') or t.node.inputs[0].is_linked for t in targets):
                issues.append(f'Unsupported static switch target: {name}')
                continue
            for t in targets:
                t.node.inputs[0].default_value = float(value)
                if t.node.bl_idname == 'ShaderNodeMixRGB': t.node.use_clamp = False
        else:
            for t in targets:
                if kind == 'scalar':
                    t.node.outputs[0].default_value = value
                else:
                    t.node.inputs['RGB'].default_value = value
                    t.node.inputs['A'].default_value = value[3]
        result={'kind':kind, 'name':name, 'targets':len(targets)}
        if scope!='GlobalParameter': result.update(scope=scope,index=index)
        applied.append(result)
    history = json.loads(mat.get('UE_instance_overrides', '[]'))
    history.append({'applied':applied, 'issues':issues})
    mat['UE_instance_overrides'] = json.dumps(history)
    if issues:
        mat.node_tree['Error'] = True
    return applied, issues
