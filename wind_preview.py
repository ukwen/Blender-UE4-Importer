"""Recover a restricted native WPO wrapper and offer an explicitly approximate preview.

The engine SimpleGrassWind implementation is NOT available here. Preserve the
actual input GUIDs, lerps and red-channel mask; never infer an engine waveform.
"""
import json
import math
import bpy

ENGINE = '/Engine/Functions/Engine_MaterialFunctions01/WorldPositionOffset/SimpleGrassWind'
NAMES = {'WindStregth', 'WindIntensity', 'WindSpeed'}
PROFILE = 'simple_grass_wind_one_minus_red_v1'


def require(condition, message):
    if not condition:
        raise NotImplementedError(message)


def source_link(exp, key, kind):
    inp = exp.properties.TryGetValue(key)
    require(inp is not None and inp.node is not None and inp.node_output_i == 0 and not inp.mask,
            'Unsupported WPO link: ' + key)
    require(inp.node.export_class_type == 'MaterialExpression' + kind, 'Unexpected WPO expression: ' + key)
    return inp.node


def read_profile(material_properties):
    """Recognize the actual wrapper topology, not a material or filename heuristic."""
    import uasset
    from material_stage import package_reference
    prop = material_properties['WorldPositionOffset']
    inp = getattr(prop, 'material_input', None)
    require(inp is not None and not inp.use_constant and not inp.mask and inp.node_output_i == 0,
            'Unsupported WPO surface input')
    call = inp.node
    require(call is not None and call.export_class_type == 'MaterialExpressionMaterialFunctionCall', 'WPO is not a function call')
    package = package_reference(call.properties.TryGetValue('MaterialFunction'))
    require(package and not call.properties.TryGetValue('FunctionInputs', ()), 'Unsupported WPO wrapper interface')
    outputs = call.properties.TryGetValue('FunctionOutputs', ())
    require(len(outputs) == 1, 'Unsupported WPO output count')
    with uasset.UAsset(call.asset.ToProjectPath(package), True, call.asset.uproject) as asset:
        functions = [e for e in asset.exports if e.export_class_type == 'MaterialExpressionFunctionOutput']
        require(len(functions) == 1 and str(functions[0].properties.TryGetValue('Id')) == str(outputs[0].TryGetValue('ExpressionOutputId')),
                'WPO output GUID mismatch')
        mul = source_link(functions[0], 'A', 'Multiply')
        engine = source_link(mul, 'A', 'MaterialFunctionCall')
        require(package_reference(engine.properties.TryGetValue('MaterialFunction')) == ENGINE, 'Not the supported engine wind dependency')
        inverse = source_link(mul, 'B', 'OneMinus')
        red = inverse.properties.TryGetValue('Input')
        require(red is not None and red.node is not None and red.node.export_class_type == 'MaterialExpressionVertexColor'
                and red.node_output_i == 1 and red.mask and tuple(red.mask_rgba) == (1, 0, 0, 0), 'Unsupported vertex color mask')
        entries = engine.properties.TryGetValue('FunctionInputs', ())
        require(len(entries) == 4, 'Unsupported engine wind interface')
        parameters, sockets = {}, []
        for entry in entries:
            guid = str(entry.TryGetValue('ExpressionInputId'))
            value = entry.TryGetValue('Input')
            require(value is not None and value.node is not None and not value.mask and value.node_output_i == 0, 'Unsupported engine input link')
            exp = value.node
            if exp.export_class_type == 'MaterialExpressionLinearInterpolate':
                a = float(source_link(exp, 'A', 'Constant').properties.TryGetValue('R', 0.0))
                b = float(source_link(exp, 'B', 'Constant').properties.TryGetValue('R', 0.0))
                p = source_link(exp, 'Alpha', 'ScalarParameter').properties
                name = p.TryGetValue('ParameterName')
                require(name in NAMES and name not in parameters, 'Unsupported or duplicate wind parameter')
                default = float(p.TryGetValue('DefaultValue', 0.0))
                require(all(math.isfinite(x) for x in (a, b, default)), 'Nonfinite wind parameter')
                parameters[name] = {'default': default, 'material_value': default,
                                    'custom_primitive_index': int(p.TryGetValue('PrimitiveDataIndex', 0)) if p.TryGetValue('bUseCustomPrimitiveData', False) else None}
                sockets.append({'guid': guid, 'parameter': name, 'a': a, 'b': b})
            elif exp.export_class_type == 'MaterialExpressionConstant3Vector':
                c = exp.properties.TryGetValue('Constant')
                require(c is not None, 'Missing constant engine input')
                sockets.append({'guid': guid, 'constant_rgb': [float(c.r), float(c.g), float(c.b)]})
            else:
                raise NotImplementedError('Unsupported wind input expression')
        require(set(parameters) == NAMES and len({s['guid'] for s in sockets}) == 4, 'Incomplete wind interface')
    return {'profile': PROFILE, 'source_function': package, 'engine_function': ENGINE,
            'mask': '1 - vertex color red', 'parameters': parameters, 'engine_inputs': sockets,
            'engine_input_semantics_verified': False, 'actor_custom_primitive_data_verified': False}


def refresh_profile(mat, graph):
    if 'UE_wind_profile' not in mat:
        return
    profile = json.loads(mat['UE_wind_profile'])
    try:
        for name, record in profile['parameters'].items():
            targets = [n.node for key, nodes in graph.param_nodes.items() if key.casefold() == name.casefold()
                       for n in nodes if n.classname == 'MaterialExpressionScalarParameter']
            require(len(targets) == 1, 'Ambiguous wind parameter: ' + name)
            val = float(targets[0].outputs[0].default_value)
            require(math.isfinite(val), 'Nonfinite wind parameter')
            record['material_value'] = val
        for socket in profile['engine_inputs']:
            if 'parameter' in socket:
                a, b = socket['a'], socket['b']
                t = profile['parameters'][socket['parameter']]['material_value']
                socket['material_lerp_value'] = a + (b - a) * t
        mat['UE_wind_profile'] = json.dumps(profile, sort_keys=True)
    except Exception as exc:
        del mat['UE_wind_profile']
        mat['UE_wind_profile_error'] = str(exc)


def vertex_weights(mesh):
    """Validate exact point mask; refuse corner disagreements instead of averaging seams."""
    color = mesh.color_attributes.get('Color')
    require(color is not None and color.data_type == 'FLOAT_COLOR' and color.domain in ('POINT', 'CORNER'),
            'Native float vertex color layer missing')
    red = [None] * len(mesh.vertices)
    for i, vertex in enumerate(mesh.loops if color.domain == 'CORNER' else mesh.vertices):
        idx = vertex.vertex_index if color.domain == 'CORNER' else vertex.index
        value = float(color.data[i].color[0])
        require(math.isfinite(value) and 0 <= value <= 1, 'Vertex red outside supported range')
        require(red[idx] is None or abs(red[idx] - value) < 1e-6, 'Corner colors disagree at shared vertex')
        red[idx] = value
    require(red and all(x is not None for x in red), 'Missing point color coverage')
    return [1 - x for x in red]


def build_group():
    """Artist-controlled local-space sine preview; no claims of engine equivalence."""
    group = bpy.data.node_groups.new('UE Wind Preview (approximate)', 'GeometryNodeTree')
    group['UE_wind_approximation'] = True
    group.interface.new_socket(name='Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
    group.interface.new_socket(name='Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
    for name, default, maximum, desc in (
        ('Amplitude (m)', .02, 10.0, 'Artist preview displacement in local X, not Unreal intensity'),
        ('Frequency (Hz)', .5, 30.0, 'Artist preview temporal frequency, not Unreal speed'),
        ('Spatial frequency', .5, 100.0, 'Cycles per local metre along X')):
        socket = group.interface.new_socket(name=name, in_out='INPUT', socket_type='NodeSocketFloat')
        socket.default_value = default; socket.min_value = 0; socket.max_value = maximum; socket.description = desc
    n = group.nodes; link = group.links.new
    def node(kind, label, x, y):
        p=n.new(kind); p.label=label; p.location=(x,y); return p
    def math_node(op, label, x, y, a=None, b=None):
        p=node('ShaderNodeMath',label,x,y); p.operation=op
        for i,v in enumerate((a,b)):
            if v is None: continue
            if isinstance(v,(float,int)): p.inputs[i].default_value=v
            else: link(v,p.inputs[i])
        return p.outputs[0]
    inp=node('NodeGroupInput','Editable preview settings',-900,300)
    out=node('NodeGroupOutput','Preview geometry',1100,300)
    color=node('GeometryNodeInputNamedAttribute','Native vertex color',-900,-180); color.data_type='FLOAT_COLOR'; color.inputs['Name'].default_value='Color'
    sep=node('FunctionNodeSeparateColor','Source red',-680,-180); sep.mode='RGB'; link(color.outputs['Attribute'],sep.inputs[0])
    mask=math_node('SUBTRACT','Exact native mask: 1 − R',-440,-180,1,sep.outputs['Red'])
    time=node('GeometryNodeInputSceneTime','Scene seconds',-900,60)
    pos=node('GeometryNodeInputPosition','Local position',-900,-460)
    xyz=node('ShaderNodeSeparateXYZ','Local X',-680,-460); link(pos.outputs['Position'],xyz.inputs[0])
    t=math_node('MULTIPLY','Temporal cycles',-680,60,time.outputs['Seconds'],inp.outputs['Frequency (Hz)'])
    x=math_node('MULTIPLY','Spatial cycles',-440,-460,xyz.outputs['X'],inp.outputs['Spatial frequency'])
    phase=math_node('ADD','Preview phase',-230,60,t,x)
    rad=math_node('MULTIPLY','Radians',-30,60,phase,math.tau)
    wave=math_node('SINE','Approximate sine',170,60,rad)
    valid=math_node('MULTIPLY','Zero if color layer removed',-230,-180,mask,color.outputs['Exists'])
    amp=math_node('MULTIPLY','Artist amplitude',-30,-180,valid,inp.outputs['Amplitude (m)'])
    dx=math_node('MULTIPLY','Masked displacement',380,60,wave,amp)
    vec=node('ShaderNodeCombineXYZ','Local X offset',580,60); link(dx,vec.inputs['X'])
    setpos=node('GeometryNodeSetPosition','Non-destructive preview',840,300)
    link(inp.outputs['Geometry'],setpos.inputs['Geometry']); link(vec.outputs[0],setpos.inputs['Offset']); link(setpos.outputs['Geometry'],out.inputs['Geometry'])
    return group


def add_preview(obj):
    require(obj.type == 'MESH' and obj.data.get('UE_source_format') == 'Legacy FMeshDescription', 'Expected native imported mesh')
    require(len(obj.material_slots) == 1 and obj.material_slots[0].material is not None, 'Only single-material native meshes supported')
    mat = obj.material_slots[0].material
    require('UE_wind_profile' in mat and json.loads(mat['UE_wind_profile'])['profile'] == PROFILE, 'No recognized native wind wrapper')
    weights = vertex_weights(obj.data)
    existing = [m for m in obj.modifiers if m.type == 'NODES' and m.node_group and m.node_group.get('UE_wind_approximation')]
    if existing:
        require(len(existing) == 1, 'Multiple wind preview modifiers')
        return existing[0], weights
    require(not obj.modifiers, 'Existing modifiers: preview order not validated')
    group = build_group()
    try:
        mod=obj.modifiers.new('UE Wind Preview (approximate)', 'NODES'); mod.node_group=group
    except Exception:
        bpy.data.node_groups.remove(group); raise
    obj['UE_wind_preview_status'] = 'approximate_asset_colors_only'
    obj['UE_wind_mask_min'] = min(weights); obj['UE_wind_mask_max'] = max(weights)
    return mod, weights


class UEIMPORT_OT_wind_preview(bpy.types.Operator):
    bl_idname = 'ueimport.wind_preview'
    bl_label = 'Add Approximate Wind Preview'
    bl_description = 'Opt-in artist preview using native red mask; not the missing Unreal engine wind function'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and any(o.type == 'MESH' for o in context.selected_objects)

    def execute(self, context):
        added = zero = 0
        for obj in context.selected_objects:
            if obj.type != 'MESH': continue
            try:
                _, weights = add_preview(obj); added += 1; zero += int(max(weights) == 0)
            except Exception as exc:
                self.report({'WARNING'}, f'{obj.name}: {exc}')
        if not added: return {'CANCELLED'}
        self.report({'INFO'}, f'{added} preview(s); {zero} zero-weight mesh(es); engine behavior unverified')
        return {'FINISHED'}


def register():
    bpy.utils.register_class(UEIMPORT_OT_wind_preview)


def unregister():
    bpy.utils.unregister_class(UEIMPORT_OT_wind_preview)
