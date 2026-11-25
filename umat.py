from __future__ import annotations
import bpy, sys, time, os, pathlib, subprocess, importlib
from struct import *
from mathutils import *
from bpy.props import *
from bpy_extras.io_utils import ImportHelper

cur_dir = os.path.dirname(__file__)
if cur_dir not in sys.path: sys.path.append(cur_dir)
import uasset, register_helper
from uasset import UAsset, Import, Export, Properties, UProperty

umodel_path = os.environ.get('UMODEL_PATH', os.path.join(cur_dir, 'umodel.exe' if os.name == 'nt' else 'umodel'))
mute_ior = True
mute_fresnel = True

blend_filepath = pathlib.Path(cur_dir) / "UE_nodes.blend"
node_tree_path = blend_filepath / "NodeTree"
def TryAppendNodeGroups():
    if 'AdditiveSurface' not in bpy.data.node_groups:
        with bpy.data.libraries.load(str(blend_filepath)) as (data_from, data_to):
            for node_group in data_from.node_groups:
                bpy.ops.wm.append(filepath=str(node_tree_path / node_group), directory=str(node_tree_path), filename=node_group, set_fake=True)

def TryGetExtractedImport(imp:Import, extract_dir):
    if not hasattr(imp, "extracted"):
        archive_path = imp.import_ref.object_name
        # Native editor source first; no source-tree writes or external executable.
        try:
            from texture_blender import load_editor_texture
            imp.extracted = load_editor_texture(imp.asset.ToProjectPath(archive_path), imp.asset.uproject)
            return imp.extracted
        except Exception as exc:
            print(f"Native editor texture unavailable for {archive_path}: {exc}")
        try:
            asset_path = imp.asset.ToProjectPath(archive_path)
            if not os.path.isfile(asset_path):
                imp.extracted = None
                return None
        except (OSError, ValueError):
            imp.extracted = None
            return None
        extracted_path = os.path.normpath(extract_dir + archive_path + ".png")
        if not os.path.exists(extracted_path):
            asset_path = imp.asset.ToProjectPath(archive_path)
            extract_dir = os.path.join(extract_dir, "Engine" if archive_path.startswith("/Engine/") else "Game")
            print(f"Extracting {asset_path}")
            try:
                subprocess.run([umodel_path, "-export", "-png", f"-out={extract_dir}", asset_path], check=True, timeout=180)
            except (OSError, subprocess.SubprocessError) as exc:
                print(f"Texture extraction failed for {archive_path}: {exc}")
                imp.extracted = None
                return None
        try:
            imp.extracted = tex = bpy.data.images.load(extracted_path, check_existing=True)

            tex_uasset_path = imp.asset.ToProjectPath(archive_path)
            with UAsset(tex_uasset_path, uproject=imp.asset.uproject) as asset:
                for export in asset.exports:
                    if export.export_class_type == 'Texture2D':
                        export.ReadProperties(False)
                        tex.colorspace_settings.name = 'sRGB' if export.properties.TryGetValue('SRGB',True) else 'Non-Color'
                        tex['flip_y'] = export.properties.TryGetValue('bFlipGreenChannel',False)
                        tex['UE_address_x'] = export.properties.TryGetValue('AddressX', 'TA_Wrap')
                        tex['UE_address_y'] = export.properties.TryGetValue('AddressY', 'TA_Wrap')
                        tex['clamp'] = export.properties.TryGetValue('AddressX', 'TA_Wrap') == 'TA_Clamp' and export.properties.TryGetValue('AddressY', 'TA_Wrap') == 'TA_Clamp'
                        break
        except: imp.extracted = None
    return imp.extracted

class UE2BlenderNodeMapping():
    def __init__(self, bl_idname, subtype=None, label=None, hide=True, inputs=None, constants=None, defaults=None, outputs=None, color=None, width=100, visible_outputs=None):
        self.bl_idname = bl_idname
        self.subtype = subtype
        self.label = label
        self.hide = hide
        self.inputs = inputs
        self.constants = constants
        self.defaults = defaults
        self.outputs = outputs
        self.color = color
        self.width = width
        self.visible_outputs = visible_outputs
class NodeData():
    def __init__(self, export:Export, classname=None, node=None, link_indirect=None, input_remap=None):
        self.export = export
        self.classname = classname if classname else export.export_class_type
        self.node = node
        self.link_indirect = link_indirect
        self.input_remap = input_remap
class GraphData(): # TODO: redundant, only returned node_guids used
    def __init__(self, stack=()):
        self.stack = stack
        self.nodes_data:dict[str,NodeData] = {}
        self.node_guids = {}
        self.param_nodes = {}

def HandleTextureObject(expr:Import, nodes_data:dict[str,NodeData], node_data:NodeData):
    tex_param_node_exp = expr.value.node
    if tex_imp := tex_param_node_exp.properties.TryGetValue('Texture'):
        node = node_data.node

        tex_param_node_data = nodes_data[tex_param_node_exp.object_name]
        tex_param_node_data.linked_tex_nodes = getattr(tex_param_node_data, 'linked_tex_nodes', [])
        tex_param_node_data.linked_tex_nodes.append(node)
        
        if tex := TryGetExtractedImport(tex_imp, tex_imp.asset.extract_dir): # TODO: unify?
            if node.bl_idname == 'ShaderNodeTexImage': SetNodeTexture(node, tex)
        else: print(f"Missing Texture \"{tex_imp.import_ref.object_name}\"")

default_mapping = UE2BlenderNodeMapping('ShaderNodeMath', label="UNKNOWN", color=Color((1,0,0)))
mat_mapping = UE2BlenderNodeMapping('ShaderNodeBsdfPrincipled', hide=False, width=None, inputs={ 'BaseColor':'Base Color','Metallic':'Metallic','Specular':'Specular IOR Level','Roughness':'Roughness',
                                       'EmissiveColor':'Emission Color','Opacity':'Alpha','OpacityMask':'Alpha','Normal':'Normal','Refraction':'IOR' }, defaults={'BaseColor':0})
UE2BlenderNode_dict = {
    'Material'                                 : mat_mapping,
    'MaterialExpressionMakeMaterialAttributes' : mat_mapping,
    'MaterialExpressionAdd'               : UE2BlenderNodeMapping('ShaderNodeVectorMath', subtype='ADD', inputs={'A':0,'B':1}, defaults={'A':0,'B':1}),
    'MaterialExpressionSubtract'          : UE2BlenderNodeMapping('ShaderNodeVectorMath', subtype='SUBTRACT', inputs={'A':0,'B':1}, defaults={'A':0,'B':1}),
    'MaterialExpressionMultiply'          : UE2BlenderNodeMapping('ShaderNodeVectorMath', subtype='MULTIPLY', inputs={'A':0,'B':1}, defaults={'A':0,'B':1}),
    'MaterialExpressionDivide'            : UE2BlenderNodeMapping('ShaderNodeVectorMath', subtype='DIVIDE', inputs={'A':0,'B':1}, defaults={'A':1,'B':2}),
    'MaterialExpressionPower'             : UE2BlenderNodeMapping('ShaderNodeMath', subtype='POWER', inputs={'Base':0,'Exponent':1}, defaults={'Exponent':2}),
    'MaterialExpressionLogarithm2'        : UE2BlenderNodeMapping('ShaderNodeGroup', subtype='Log', inputs={'X':0}, constants={'Base':('Base',2)}, label="Log2"),
    'MaterialExpressionLogarithm10'       : UE2BlenderNodeMapping('ShaderNodeGroup', subtype='Log', inputs={'X':0}, constants={'Base':('Base',10)}, label="Log10"),
    'MaterialExpressionAbs'               : UE2BlenderNodeMapping('ShaderNodeVectorMath', subtype='ABSOLUTE', inputs={'Input':0}),
    'MaterialExpressionFrac'              : UE2BlenderNodeMapping('ShaderNodeVectorMath', subtype='FRACTION', inputs={'Input':0}),
    'MaterialExpressionFmod'              : UE2BlenderNodeMapping('ShaderNodeVectorMath', subtype='MODULO', inputs={'A':0,'B':1}),
    'MaterialExpressionCeil'              : UE2BlenderNodeMapping('ShaderNodeVectorMath', subtype='CEIL', inputs={'Input':0}),
    'MaterialExpressionFloor'             : UE2BlenderNodeMapping('ShaderNodeVectorMath', subtype='FLOOR', inputs={'Input':0}),
    'MaterialExpressionRound'             : UE2BlenderNodeMapping('ShaderNodeGroup', subtype='Round', inputs={'Input':0}),
    'MaterialExpressionTruncate'          : UE2BlenderNodeMapping('ShaderNodeGroup', subtype='Truncate', inputs={'Input':0}),
    'MaterialExpressionSign'              : UE2BlenderNodeMapping('ShaderNodeGroup', subtype='Sign', inputs={'Input':0}),
    'MaterialExpressionOneMinus'          : UE2BlenderNodeMapping('ShaderNodeVectorMath', subtype='SUBTRACT', inputs={'A':0,'Input':1}, defaults={'A':1}, label="1-x"),
    'MaterialExpressionMin'               : UE2BlenderNodeMapping('ShaderNodeVectorMath', subtype='MINIMUM', inputs={'A':0,'B':1}, defaults={'A':0,'B':1}),
    'MaterialExpressionMax'               : UE2BlenderNodeMapping('ShaderNodeVectorMath', subtype='MAXIMUM', inputs={'A':0,'B':1}, defaults={'A':0,'B':1}),
    'MaterialExpressionStep'              : UE2BlenderNodeMapping('ShaderNodeGroup', subtype='Step', inputs={'Y':0,'X':1}, defaults={'Y':0,'X':1}),
    'MaterialExpressionSmoothStep'        : UE2BlenderNodeMapping('ShaderNodeGroup', subtype='SmoothStep', inputs={'Min':0,'Max':1,'Value':2}, defaults={'Min':0,'Max':1,'Value':0}, width=120),
    'MaterialExpressionClamp'             : UE2BlenderNodeMapping('ShaderNodeClamp', inputs={'Input':0,'Min':1,'Max':2}),

    'MaterialExpressionDistance'          : UE2BlenderNodeMapping('ShaderNodeVectorMath', subtype='DISTANCE', inputs={'A':0,'B':1}),
    'MaterialExpressionDotProduct'        : UE2BlenderNodeMapping('ShaderNodeVectorMath', subtype='DOT_PRODUCT', inputs={'A':0,'B':1}, label="Dot"),
    'MaterialExpressionCrossProduct'      : UE2BlenderNodeMapping('ShaderNodeVectorMath', subtype='CROSS_PRODUCT', inputs={'A':0,'B':1}, label="Cross"),
    'MaterialExpressionNormalize'         : UE2BlenderNodeMapping('ShaderNodeVectorMath', subtype='NORMALIZE', inputs={'VectorInput':0}),

    'MaterialExpressionSine'              : UE2BlenderNodeMapping('ShaderNodeGroup', subtype='Sine', inputs={'Input':0}, constants={'Period':('Period',1)}, hide=False),
    'MaterialExpressionCosine'            : UE2BlenderNodeMapping('ShaderNodeGroup', subtype='Cosine', inputs={'Input':0}, constants={'Period':('Period',1)}, hide=False),
    'MaterialExpressionTangent'           : UE2BlenderNodeMapping('ShaderNodeGroup', subtype='Tangent', inputs={'Input':0}, constants={'Period':('Period',1)}, hide=False),
    'MaterialExpressionArcsine'           : UE2BlenderNodeMapping('ShaderNodeMath', subtype='ARCSINE', inputs={'Input':0}),
    'MaterialExpressionArccosine'         : UE2BlenderNodeMapping('ShaderNodeMath', subtype='ARCCOSINE', inputs={'Input':0}),
    'MaterialExpressionArctangent'        : UE2BlenderNodeMapping('ShaderNodeMath', subtype='ARCTANGENT', inputs={'Input':0}),
    'MaterialExpressionArcsineFast'       : UE2BlenderNodeMapping('ShaderNodeMath', subtype='ARCSINE', inputs={'Input':0}),
    'MaterialExpressionArccosineFast'     : UE2BlenderNodeMapping('ShaderNodeMath', subtype='ARCCOSINE', inputs={'Input':0}),
    'MaterialExpressionArctangentFast'    : UE2BlenderNodeMapping('ShaderNodeMath', subtype='ARCTANGENT', inputs={'Input':0}),

    'MaterialExpressionStaticBool'        : UE2BlenderNodeMapping('ShaderNodeValue', hide=False),
    'MaterialExpressionScalarParameter'   : UE2BlenderNodeMapping('ShaderNodeValue', hide=False),
    'MaterialExpressionConstant'          : UE2BlenderNodeMapping('ShaderNodeValue', hide=False),
    'MaterialExpressionConstant2Vector'   : UE2BlenderNodeMapping('ShaderNodeCombineXYZ', hide=False),
    'MaterialExpressionConstant3Vector'   : UE2BlenderNodeMapping('ShaderNodeGroup', subtype='Const3', hide=False, width=None),
    'MaterialExpressionConstant4Vector'   : UE2BlenderNodeMapping('ShaderNodeGroup', subtype='RGBA', hide=False, width=None), #outputs={'R':1,'G':2,'B':3,'A':4}
    'MaterialExpressionVectorParameter'   : UE2BlenderNodeMapping('ShaderNodeGroup', subtype='RGBA', hide=False, width=None, outputs={'RGB':0,'R':1,'G':2,'B':3,'A':4}),
    'MaterialExpressionStaticSwitch'      : UE2BlenderNodeMapping('ShaderNodeMixRGB', label="Switch", hide=False, inputs={'A':2,'B':1,'Value':0}),
    'MaterialExpressionStaticSwitchParameter' : UE2BlenderNodeMapping('ShaderNodeMixRGB', label="Switch", hide=False, inputs={'A':2,'B':1}),
    'MaterialExpressionTextureSample'     : UE2BlenderNodeMapping('ShaderNodeTexImage', hide=False, width=None, inputs={'Coordinates':0, 'TextureObject':HandleTextureObject}),
    'MaterialExpressionTextureSampleParameter2D' : UE2BlenderNodeMapping('ShaderNodeTexImage', hide=False, width=None, inputs={'Coordinates':0}),
    'MaterialExpressionTextureObjectParameter'   : UE2BlenderNodeMapping('ShaderNodeValue'),
    'MaterialExpressionTextureCoordinate' : UE2BlenderNodeMapping('ShaderNodeUVMap', hide=False, width=None),
    'MaterialExpressionIf'                : UE2BlenderNodeMapping('ShaderNodeGroup', subtype="If", hide=False, 
                                                                  inputs={'A':0,'B':1,'AGreaterThanB':3,'AEqualsB':4,'ALessThanB':5}, defaults={'B':0}, constants={'EqualsThreshold':(2,0.00001)}),
    'MaterialExpressionAppendVector'      : UE2BlenderNodeMapping('ShaderNodeCombineXYZ', label="Append", inputs={'A':0,'B':1}),
    'MaterialExpressionComponentMask'     : UE2BlenderNodeMapping('ShaderNodeSeparateXYZ', label="Mask", inputs={'Input':0}),
    'MaterialExpressionLinearInterpolate' : UE2BlenderNodeMapping('ShaderNodeMixRGB', label="Lerp", inputs={'A':1,'B':2,'Alpha':0}, defaults={'A':0,'B':1,'Alpha':0.5}), # constants={'A':(1,0), 'B':(2,1), 'Alpha':(0,0)}
    'MaterialExpressionTwoSidedSign'      : UE2BlenderNodeMapping('ShaderNodeGroup', subtype="TwoSidedSign", hide=False, width=140),
    'MaterialExpressionVertexColor'       : UE2BlenderNodeMapping('ShaderNodeVertexColor', hide=False, label="Vertex Color"),
    'MaterialExpressionVertexNormalWS'    : UE2BlenderNodeMapping('ShaderNodeNewGeometry', hide=False, label="Vertex Normal", visible_outputs=('Normal',), outputs={'Normal':'Normal'}),
    'MaterialExpressionWorldPosition'     : UE2BlenderNodeMapping('ShaderNodeNewGeometry', hide=False, width=170, label="Absolute World Position", visible_outputs=('Position',)),
    'MaterialExpressionObjectPositionWS'  : UE2BlenderNodeMapping('ShaderNodeObjectInfo', hide=False, width=None, label="Object Position", visible_outputs=('Location',)),
    'MaterialExpressionCameraPositionWS'  : UE2BlenderNodeMapping('ShaderNodeGroup', subtype='CameraPosition', hide=False, width=None),
    'MaterialExpressionCameraVectorWS'    : UE2BlenderNodeMapping('ShaderNodeGroup', subtype='CameraVector', hide=False, width=None),
    'MaterialExpressionScreenPosition'    : UE2BlenderNodeMapping('ShaderNodeGroup', subtype='ScreenPosition', hide=False, width=None),
    'MaterialExpressionPixelDepth'        : UE2BlenderNodeMapping('ShaderNodeCameraData', hide=False, width=None, visible_outputs=('View Z Depth',)),

    'MaterialExpressionDesaturation'      : UE2BlenderNodeMapping('ShaderNodeGroup', subtype='Desaturation', inputs={'Input':0,'Fraction':1}),
    'MaterialExpressionComment'           : UE2BlenderNodeMapping('NodeFrame', width=None),
    'MaterialExpressionReroute'           : UE2BlenderNodeMapping('NodeReroute', hide=False, width=None, inputs={'Input':0}),
    'MaterialExpressionFresnel'           : UE2BlenderNodeMapping('ShaderNodeFresnel', hide=False),
    'MaterialExpressionBlackBody'         : UE2BlenderNodeMapping('ShaderNodeBlackbody', hide=False, inputs={'Temp':0}),
    'CheapContrast_RGB'                   : UE2BlenderNodeMapping('ShaderNodeBrightContrast', width=None, hide=False, inputs={'FunctionInputs':('Color','Contrast')}),
    'BlendAngleCorrectedNormals'          : UE2BlenderNodeMapping('ShaderNodeGroup', subtype='BlendAngleCorrectedNormals', width=None, hide=False, inputs={'FunctionInputs':(0,1)}),
    'CameraDepthFade'                     : UE2BlenderNodeMapping('ShaderNodeGroup', subtype='CameraDepthFade', width=None, hide=False, inputs={'FunctionInputs':(0,1,2)}),
    'MaterialExpressionFunctionInput'     : UE2BlenderNodeMapping('NodeReroute', hide=False, width=None),
    'MaterialExpressionFunctionOutput'    : UE2BlenderNodeMapping('NodeReroute', hide=False, width=None, inputs={'A':0}),
}
ue_to_bl_type = { 'FunctionInput_Scalar':'NodeSocketFloat', 'FunctionInput_StaticBool':'NodeSocketFloat' }
class_blacklist = { 'SceneThumbnailInfoWithPrimitive', 'MetaData', 'MaterialExpressionPanner', 'MaterialExpressionBumpOffset', 'MaterialExpressionLightmassReplace' }
material_classes = { 'Material', 'MaterialInstanceConstant' }
node_whitelist = { 'ShaderNodeBsdfPrincipled', 'ShaderNodeOutputMaterial' }

def DeDuplicateName(name):
    i = name.rfind('.')
    return name[:i] if i >= 0 else name
def GuessBaseDir(filename): return filename[:filename.find("Game")] # Unreal defaults to starting path with "Game" on asset export
def SetupNode(node_tree, name, mapping:UE2BlenderNodeMapping, node_data) -> bpy.types.ShaderNode: # TODO: inline
    node = node_tree.nodes.new(mapping.bl_idname)
    node.name = name
    node.hide = mapping.hide
    SetNodePos(node, node_data.export.properties)
    if mapping.subtype:
        if mapping.bl_idname == 'ShaderNodeGroup': node.node_tree = bpy.data.node_groups[mapping.subtype]
        else: node.operation = mapping.subtype
    if mapping.label: node.label = mapping.label
    node.use_custom_color = mapping.color != None
    if mapping.color: node.color = mapping.color
    if mapping.visible_outputs:
        for out_socket in node.outputs:
            if out_socket.name not in mapping.visible_outputs: out_socket.hide = True

    match mapping.bl_idname:
        case 'ShaderNodeTexImage' | 'ShaderNodeVertexColor':
            rgb_in = node.outputs['Color']
            if node_data.export.properties.TryGetValue('SamplerType') == 'SAMPLERTYPE_Normal':
                rgb2n = node_tree.nodes.new('ShaderNodeGroup')
                rgb2n.node_tree = bpy.data.node_groups['RGBtoNormalY-']
                rgb2n.hide = True
                SetNodePos(rgb2n, node_data.export.properties)
                rgb2n.location += Vector((0,30))
                node_tree.links.new(node.outputs['Color'], rgb2n.inputs['RGB'])
                rgb_in = rgb2n.outputs['Normal']

            rgba:bpy.types.ShaderNode = node_tree.nodes.new('ShaderNodeGroup')
            rgba.node_tree = bpy.data.node_groups['RGBA']
            rgba.hide, rgba.width,rgba.show_options  = (True, 100, False)
            rgba.location = node.location + Vector((160,-32))
            node_tree.links.new(rgb_in, rgba.inputs['RGB'])
            node_tree.links.new(node.outputs['Alpha'], rgba.inputs['A'])
            node_data.link_indirect = rgba.outputs
        case 'ShaderNodeMixRGB':
            node.inputs['Fac'].default_value = 0
    return node
def SetNodePos(node, params:Properties, param_x='MaterialExpressionEditorX', param_y='MaterialExpressionEditorY'): node.location = (params.TryGetValue(param_x,0), -params.TryGetValue(param_y,0))
def HandleDefaultConstants(mapping, node, params):
    if mapping.defaults:
        for ue_name, default_value in mapping.defaults.items():
            const_name = f'Const{ue_name}'
            if ue_name not in params: # or const_name in params:
                value = params.TryGetValue(const_name, default_value)
                socket = node.inputs[mapping.inputs[ue_name]]
                match socket.type:
                    case 'VECTOR': socket.default_value = (value, value, value)
                    case 'RGBA':   socket.default_value = (value, value, value, 1)
                    case _:        socket.default_value = value
def TryRemapNormal(params, node_tree, node_data):
    if 'Normal' in params or params.TryGetValue('bUseMaterialAttributes', False):
        normal_map = node_tree.nodes.new('ShaderNodeNormalMap')
        normal_map.uv_map = 'UV0'  # UE mesh tangent basis, not active Blender UV.
        if not params.TryGetValue('TangentSpaceNormal', True):
            node_tree['Error'] = True
            normal_map['UE_unsupported_normal_space'] = 'World-space input requires a separate basis conversion'
        normal_map.location = node_data.node.location + Vector((-200, -570))
        node_tree.links.new(normal_map.outputs['Normal'], node_data.node.inputs['Normal'])

        n2rgb = node_tree.nodes.new('ShaderNodeGroup')
        n2rgb.node_tree = bpy.data.node_groups['NormalToRGB']
        n2rgb.location = normal_map.location + Vector((-160, -130))
        n2rgb.hide = True
        node_tree.links.new(n2rgb.outputs['RGB'], normal_map.inputs['Color'])

        node_data.input_remap = {**(node_data.input_remap or {}), 'Normal':n2rgb.inputs['Normal']}
def SetBlend(params, mat, node_data):
    match params.TryGetValue('BlendMode'):
        case 'BLEND_Translucent':
            mat.surface_render_method = 'BLENDED'
            node_data.node.inputs['Transmission Weight'].default_value = 1
        case 'BLEND_Masked':
            mat.surface_render_method = 'DITHERED'
            mat['UE_BlendModeApproximation'] = 'Masked alpha: dithered, clip threshold not reconstructed'
        case 'BLEND_Additive':
            mat.surface_render_method = 'BLENDED'

            additive = mat.node_tree.nodes.new('ShaderNodeGroup')
            additive.node_tree = bpy.data.node_groups['AdditiveSurface']
            additive.location = node_data.node.location + Vector((0, 150))
            mat.node_tree.links.new(additive.outputs[0], mat.node_tree.nodes['Material Output'].inputs['Surface'])
            node_data.input_remap = { 'EmissiveColor':additive.inputs['Emission'] }
        case _:
            mat.surface_render_method = 'DITHERED'
def SetTwoSided(params, mat): mat.use_backface_culling = not params.TryGetValue('TwoSided', False)

def CreateNode(exp:Export, node_tree, nodes_data:dict[str,NodeData], graph_data:GraphData, mesh=None):
    name = exp.object_name
    classname = exp.export_class_type # TODO: inline?
    nodes_data[name] = node_data = NodeData(exp)
    params = exp.properties

    if classname in class_blacklist:
        if classname.startswith('MaterialExpression'): node_tree['Error'] = True
        return None

    from material_attributes import KINDS as ATTRIBUTE_KINDS, build as build_attributes
    if classname == 'MaterialExpressionFunctionInput' and params.TryGetValue('InputType') == 'FunctionInput_MaterialAttributes':
        node = build_attributes(node_tree, node_data)
        SetNodePos(node, params)
        return node_data
    if classname in ATTRIBUTE_KINDS:
        node = build_attributes(node_tree, node_data)
        SetNodePos(node, params)
        return node_data

    if classname in ('MaterialExpressionAppendVector', 'MaterialExpressionComponentMask'):
        from channel_ops import plan, build
        spec = plan(exp, (id(exp),))
        if spec is not None:
            node = build(node_tree, node_data, spec)
            SetNodePos(node, params)
            return node_data
        node_tree['Error'] = True
    mapping = UE2BlenderNode_dict.get(classname)
    if classname == 'MaterialExpressionMaterialFunctionCall':
        matfnc_imp = params.TryGetValue('MaterialFunction')
        if matfnc_imp is None:
            raise ValueError('Missing material function reference')
        classname = matfnc_imp.object_name
        mapping = UE2BlenderNode_dict.get(classname)
        if not mapping or (mapping.bl_idname == 'ShaderNodeGroup' and mapping.subtype not in bpy.data.node_groups):
            # Each imported call owns its group, so instance edits cannot mutate siblings.
            try:
                node_group, fn_graph = ImportMaterialFunction(matfnc_imp, mesh, graph_data.stack)
            except FileNotFoundError as exc:
                # Keep the genuine surface graph inspectable when a function is absent.
                # Never substitute a fabricated function or claim material acceptance.
                import json
                missing = json.loads(node_tree.get('UE_missing_functions', '[]'))
                missing.append({'name': classname, 'error': str(exc)})
                node_tree['UE_missing_functions'] = json.dumps(missing)
                node_tree['Error'] = True
                print(f'Missing material function {classname}: {exc}')
                return None
            inputs = tuple(i for i in node_group.interface.items_tree if i.item_type == 'SOCKET' and i.in_out == 'INPUT')
            outputs = tuple(i for i in node_group.interface.items_tree if i.item_type == 'SOCKET' and i.in_out == 'OUTPUT')
            import json
            input_ids = json.loads(node_group.get('UE_input_ids', '{}'))
            output_ids = json.loads(node_group.get('UE_output_ids', '{}'))
            call_inputs = params.TryGetValue('FunctionInputs', ())
            call_outputs = params.TryGetValue('FunctionOutputs', ())
            from material_attributes import interface_order
            in_order = interface_order(call_inputs, input_ids, inputs, 'ExpressionInputId')
            node_data.function_output_order = interface_order(call_outputs, output_ids, outputs, 'ExpressionOutputId')
            node_data.function_input_order = in_order
            mapping = UE2BlenderNodeMapping('ShaderNodeGroup', node_group.name, hide=False, inputs={'FunctionInputs':tuple(in_order)} if in_order else None)
            for key, entries in fn_graph.param_nodes.items():
                graph_data.param_nodes.setdefault(key, []).extend(entries)
    if classname in ('MaterialExpressionStaticSwitch', 'MaterialExpressionStaticSwitchParameter'):
        from typed_switch import layout
        typed = layout(params, classname.endswith('Parameter'))
        if typed is not None:
            node_data.switch_width, inputs = typed
            mapping = UE2BlenderNodeMapping('ShaderNodeMix', label='UE typed switch', hide=False, inputs=inputs)
        else:
            node_tree['Error'] = True
    node_data.classname = classname
    node_data.mapping = mapping

    if not mapping:
        print(f"UNKNOWN UMAT CLASS: {classname}")
        mapping = default_mapping
        node_tree['Error'] = True
    
    if mapping != mat_mapping: node_data.node = node = SetupNode(node_tree, name, mapping, node_data)
    else:
        node_data.node = node = node_tree.nodes['Principled BSDF']
        SetNodePos(node, node_data.export.properties)

    if hasattr(node_data, 'function_output_order'):
        node_data.function_bundles = {j:{k:node.outputs[i] for k,i in entry.items()} for j,entry in enumerate(node_data.function_output_order) if isinstance(entry,dict)}
        node_data.link_indirect = [None if isinstance(i,dict) else node.outputs[i] for i in node_data.function_output_order]
    if (sx := params.TryGetValue('SizeX')) != None: node.width = sx
    elif mapping.width: node.width = mapping.width
    if (sy := params.TryGetValue('SizeY')) != None: node.height = sy
    
    if param_name := params.TryGetValue('ParameterName'):
        param_nodes = graph_data.param_nodes.get(param_name)
        if not param_nodes: graph_data.param_nodes[param_name] = param_nodes = []
        param_nodes.append(node_data)
    if txt := params.TryGetValue('Text'): node.label = txt
    elif param_name: node.label, node.width = (param_name, max(node.width, 25 + 7*len(param_name)))

    HandleDefaultConstants(mapping, node, params)
    if mapping.constants:
        for ue_name, const in mapping.constants.items():
            bl_name, const_default = const
            const_val = params.TryGetValue(ue_name, const_default)
            node.inputs[bl_name].default_value = const_val

    if mapping.bl_idname == 'ShaderNodeGroup': node.show_options = False

    value = params.TryGetValue('DefaultValue')
    if value == None: value = params.TryGetValue('Constant')
    if value != None: # TODO: move to mapping class?
        match classname:
            case 'MaterialExpressionScalarParameter':
                node.outputs[0].default_value = value
            case 'MaterialExpressionConstant3Vector':
                rgb = tuple(value.ToTupleRGB())[:3]
                node.inputs[0].default_value = rgb + (1.0,) if node.inputs[0].type == 'RGBA' else rgb
            case 'MaterialExpressionVectorParameter':
                node.inputs['RGB'].default_value = value.ToTuple()
                node.inputs['A'].default_value = value.a
    else:
        match classname:
            case 'MaterialExpressionConstant':
                r = params.TryGetValue('R', 0)
                node.outputs[0].default_value = r
            case 'MaterialExpressionConstant2Vector':
                r = params.TryGetValue('R', 0)
                g = params.TryGetValue('G', 0)
                node.inputs[0].default_value = r
                node.inputs[1].default_value = g
                node.inputs[2].hide = True
    match classname:
        case 'MaterialExpressionTextureCoordinate':
            from uv_semantics import unreal_coordinates
            node_data.link_indirect = [unreal_coordinates(node_tree, node, params)]
        case 'MaterialExpressionTextureSampleParameter2D' | 'MaterialExpressionTextureSample':
            from uv_semantics import texture_coordinates
            node['UE_sampler_source'] = params.TryGetValue('SamplerSource', 'SSM_FromTextureAsset')
            texture_coordinates(node_tree, node, params)
            if tex_imp := params.TryGetValue('Texture'):
                from material_stage import package_reference
                node['UE_texture_package'] = package_reference(tex_imp)
                if tex := TryGetExtractedImport(tex_imp, exp.asset.extract_dir):
                    SetNodeTexture(node, tex)
                else: print(f"Missing Texture \"{tex_imp.import_ref.object_name}\"")
        #case 'MaterialExpressionMakeMaterialAttributes': node_tree.links.new(node.outputs[0], node_tree.nodes['Material Output'].inputs['Surface'])

    if classname == 'MaterialExpressionStaticBool':
        node.outputs[0].default_value = float(bool(params.TryGetValue('Value', False)))
    if classname in ('MaterialExpressionStaticSwitch', 'MaterialExpressionStaticSwitchParameter'):
        default = params.TryGetValue('DefaultValue', False)
        if hasattr(node_data, 'switch_width'):
            from typed_switch import configure
            node_data.link_indirect = [configure(node, node_data.switch_width, default)]
        else:
            node.inputs['Fac'].default_value = float(bool(default))
            node.use_clamp = False
            node['UE_switch_unsupported'] = 'Unresolved branch width or non-static selector' 

    TryRemapNormal(params, node_tree, node_data)

    if expr_guid := params.TryGetValue('ExpressionGUID'): graph_data.node_guids[expr_guid] = node_data
    return node_data
def TryLinkSocket(node_tree, nodes_data:dict[str,NodeData], node_data:NodeData, expr:UProperty, property:str, dst_index):
    try:
        from surface_semantics import constant_value, masked_socket
        inp = getattr(expr, 'material_input', None)
        if getattr(expr, 'material_input_unsupported', False):
            raise NotImplementedError('Unsupported material input layout')
        if inp is not None and inp.use_constant:
            dst = node_data.input_remap.get(property) if node_data.input_remap and property in node_data.input_remap else node_data.node.inputs[dst_index]
            dst.default_value = constant_value(inp)
            return True
        if inp is None and expr.struct_type == 'ExpressionInput': inp = expr.value
        link_node_exp = inp.node if inp is not None else expr.value
        if link_node_exp is None:
            if inp is not None and getattr(inp, 'node_index', 0) < 0: raise NotImplementedError('External expression input')
            return False
        if link_node_data := nodes_data.get(link_node_exp.object_name):
            link_node_type = link_node_data.classname
            if link_node_type in class_blacklist: raise NotImplementedError('Unsupported linked expression '+link_node_type)
            
            node, link_node = (node_data.node, link_node_data.node)
            if node is None or link_node is None:
                raise ValueError(f'Unresolved expression link: {link_node_exp.object_name} -> {property}')
            from material_attributes import bundle_outputs
            if bundle_outputs(link_node_data, inp.node_output_i if inp is not None else 0) is not None:
                raise NotImplementedError("Material attributes require explicit field selection")
            if getattr(link_node_data, "channel_spec", (0,))[0] == 4:
                raise NotImplementedError("Float4 requires explicit typed channel selection")
            outputs = link_node_data.link_indirect if link_node_data.link_indirect else link_node.outputs

            src_i = inp.node_output_i if inp is not None else 0
            if not 0 <= src_i < len(outputs): raise Exception(f"Link Failed, Missing Output Socket: {node.name}.{property} {src_i}/{len(outputs)}")
            src_socket = outputs[src_i]
            if src_socket.is_unavailable: raise ValueError('Selected output is unavailable')
            if inp is not None: src_socket = masked_socket(node_tree, src_socket, inp, link_node_data.link_indirect)

            dst_socket = node.inputs[dst_index]
            if node_data.input_remap and property in node_data.input_remap: dst_socket = node_data.input_remap[property]
            if src_socket and dst_socket:
                if node.bl_idname == 'ShaderNodeTexImage' and property == 'Coordinates':
                    from uv_semantics import sample_coordinates, connect_sample
                    connect_sample(node_tree, node, sample_coordinates(node_tree, src_socket))
                    return True
                link = node_tree.links.new(src_socket, dst_socket)
                if mute_fresnel and src_socket.node.bl_idname == 'ShaderNodeFresnel': link.is_muted = True
                return True
            else: raise Exception(f"Link Failed, Missing Socket: {node.name}.{property}")
        else: raise Exception(f"Link Failed, Missing Node: \"{expr.value}\" {str(link_node_exp.object_name)} (\"{os.path.basename(node_data.export.asset.filepath)}\")")
    except Exception as e:
        print(e)
        node_tree['Error'] = True
        return False
def LinkSockets(node_tree, nodes_data:dict[str,NodeData], node_data:NodeData):
    if getattr(node_data,'function_interface_bound',False): return
    if hasattr(node_data,'function_input_order') and any(isinstance(i,dict) for i in node_data.function_input_order):
        from material_attributes import connect_call
        connect_call(node_tree,nodes_data,node_data,TryLinkSocket)
        return
    if hasattr(node_data, 'attribute_kind'):
        from material_attributes import connect
        connect(node_tree, nodes_data, node_data, TryLinkSocket)
        return
    if node_data.classname == 'Material' and node_data.export.properties.TryGetValue('bUseMaterialAttributes', False):
        from material_attributes import connect_surface
        connect_surface(node_tree, nodes_data, node_data)
        return
    if hasattr(node_data, 'channel_spec'):
        from channel_ops import connect
        connect(node_tree, nodes_data, node_data)
        return
    mapping = getattr(node_data, 'mapping', UE2BlenderNode_dict.get(node_data.classname))
    if mapping and mapping.inputs:
        for property, map_val in mapping.inputs.items():
            expr = node_data.export.properties.get(property)
            if expr:
                if callable(map_val): map_val(expr, nodes_data, node_data)
                else:
                    match expr.type:
                        case 'StructProperty': TryLinkSocket(node_tree, nodes_data, node_data, expr, property, map_val)
                        case 'ArrayProperty':
                            for i, elem in enumerate(expr.value): TryLinkSocket(node_tree, nodes_data, node_data, elem['Input'], i, map_val[i])
def SetNodeTexture(node, image):
    node.image = image
    from uv_semantics import set_address
    set_address(node, image)
    node.interpolation = 'Closest' if image.get('nearest', False) else 'Linear'

    links = node.outputs['Color'].links
    if len(links) > 0:
        linked_node = links[0].to_node
        if linked_node.type == 'GROUP' and linked_node.node_tree and linked_node.node_tree.name.startswith('RGBtoNormal'):
            linked_node.node_tree = bpy.data.node_groups['RGBtoNormal' if image.get('flip_y', False) else 'RGBtoNormalY-']
def ImportMaterialFunction(mat_fnc_imp:Import, mesh=None, stack=()):
    from material_stage import package_reference
    package = package_reference(mat_fnc_imp)
    if not package:
        raise ValueError('Missing material function package')
    group, graph = ImportNodeGraph(mat_fnc_imp.asset.ToProjectPath(package), mat_fnc_imp.asset.uproject, mesh=mesh, _stack=stack)
    if not isinstance(group, bpy.types.ShaderNodeTree):
        raise ValueError('Referenced package is not a material function')
    return group, graph
def ImportNodeGraph(filepath, uproject=None, name=None, mesh=None, log=False, _stack=()):
    key = str(pathlib.Path(filepath).resolve())
    if key in _stack or len(_stack) >= 32:
        raise ValueError(f'Material dependency cycle or depth limit: {key}')
    return _ImportNodeGraph(filepath, uproject, name, mesh, log, _stack + (key,))


def _ImportNodeGraph(filepath, uproject, name, mesh, log, stack):
    t0 = time.time()
    '''if not os.path.exists(filepath):
        print(f"Error: \"{filepath}\" Does Not Exist!")
        return (None, None)'''
    TryAppendNodeGroups()
    out = None
    with UAsset(filepath, True, uproject) as asset:
        for exp in asset.exports:
            classname = exp.export_class_type
            params = exp.properties
            match classname:
                case 'Material': # TODO: can this not be first?
                    graph_data = GraphData(stack) # TODO: replace with attributes on export?
                    nodes_data = graph_data.nodes_data

                    if not name: name = exp.object_name
                    out = mat = bpy.data.materials.new(name)
                    mat.use_nodes = True
                    mat["UAsset"] = asset.f.byte_stream.name
                    node_tree = mat.node_tree
                    node = node_tree.nodes['Principled BSDF']
                    SetNodePos(node, params, 'EditorX', 'EditorY')
                    HandleDefaultConstants(UE2BlenderNode_dict['Material'], node, params)
                    node_tree.nodes['Material Output'].location = node.location + Vector((300,0))
                    nodes_data[node.name] = node_data = NodeData(exp, node=node)

                    for exr_exp in params.TryGetValue('Expressions', ()): CreateNode(exr_exp.value, node_tree, nodes_data, graph_data, mesh)
                    for comment_exp in params.TryGetValue('EditorComments', ()):
                        comment_node = CreateNode(comment_exp.value, node_tree, nodes_data, graph_data, mesh).node
                        for eval_node in filter(lambda n: not n.parent, node_tree.nodes):
                            diff = eval_node.location - comment_node.location
                            if diff.x > 0 and diff.x < comment_node.width and diff.y < 0 and diff.y > -comment_node.height: eval_node.parent = comment_node

                    if params.TryGetValue('ShadingModel', '') == 'MSM_Unlit':
                        emission = node_tree.nodes.new('ShaderNodeEmission')
                        emission.location = node.location + Vector((0, 150))
                        node_tree.links.new(emission.outputs[0], node_tree.nodes['Material Output'].inputs['Surface'])
                        node_data.input_remap = { 'EmissiveColor':emission.inputs['Color'] }

                    SetBlend(params, mat, node_data)
                    if 'EmissiveColor' in params: node.inputs['Emission Strength'].default_value = 1.0
                    if 'WorldPositionOffset' in params:
                        mat['UE_unimplemented_surface_inputs'] = 'WorldPositionOffset'
                        node_tree['Error'] = True
                        try:
                            import json
                            from wind_preview import read_profile
                            mat['UE_wind_profile'] = json.dumps(read_profile(params), sort_keys=True)
                        except Exception as exc:
                            mat['UE_wind_profile_error'] = str(exc)
                    SetTwoSided(params, mat)

                    TryRemapNormal(params, node_tree, node_data)

                    for name in nodes_data: LinkSockets(node_tree, nodes_data, nodes_data[name]) # TODO: this iterates nodes without links!
                    
                    if params.TryGetValue('BlendMode') == 'BLEND_Masked':
                        from surface_semantics import set_opacity_clip
                        set_opacity_clip(mat, params.TryGetValue('OpacityMaskClipValue', 0.333333))
                        if 'UE_BlendModeApproximation' in mat: del mat['UE_BlendModeApproximation']
                    ior = node.inputs['IOR']
                    if ior.is_linked: ior.links[0].is_muted = mute_ior
                case 'MaterialInstanceConstant':
                    from material_instance import apply_overrides
                    from material_stage import package_reference
                    mat_parent = params.TryGetValue('Parent')
                    parent_package = package_reference(mat_parent)
                    if not parent_package:
                        raise ValueError('Missing external material parent reference')
                    mat_path = asset.ToProjectPath(parent_package)
                    if not name: name = exp.object_name
                    mat, graph_data = ImportNodeGraph(mat_path, asset.uproject, name, mesh, _stack=stack)
                    if not isinstance(mat, bpy.types.Material):
                        raise ValueError('Material instance parent is not a material')
                    out = mat
                    apply_overrides(mat, graph_data, params, TryGetExtractedImport, SetNodeTexture)
                    import json
                    chain = json.loads(mat.get('UE_instance_chain', '[]'))
                    chain.append(str(pathlib.Path(filepath).resolve()))
                    mat['UE_instance_chain'] = json.dumps(chain)
                    mat['UAsset'] = str(pathlib.Path(filepath).resolve())

                    if overrides := params.TryGetValue('BasePropertyOverrides'):
                        if overrides.TryGetValue('bOverride_BlendMode'):
                            if graph_data.nodes_data['Principled BSDF'].export.properties.TryGetValue('bUseMaterialAttributes', False):
                                mat.node_tree['Error'] = True
                                mat['UE_attribute_blend_override_unsupported'] = True
                            SetBlend(overrides, mat, graph_data.nodes_data['Principled BSDF'])
                            from surface_semantics import set_opacity_clip, clear_opacity_clip
                            if overrides.TryGetValue('BlendMode') == 'BLEND_Masked':
                                set_opacity_clip(mat, mat.get('UE_opacity_mask_clip', 0.333333))
                                if 'UE_BlendModeApproximation' in mat: del mat['UE_BlendModeApproximation']
                            else: clear_opacity_clip(mat)
                        if overrides.TryGetValue('bOverride_OpacityMaskClipValue') and 'UE_opacity_mask_clip' in mat:
                            from surface_semantics import set_opacity_clip
                            set_opacity_clip(mat, overrides.TryGetValue('OpacityMaskClipValue', 0.333333))
                        if overrides.TryGetValue('bOverride_TwoSided'): SetTwoSided(overrides, mat)
                case 'MaterialFunction': # TODO: very similar to Material, merge?
                    out = node_tree = bpy.data.node_groups.new(exp.object_name, 'ShaderNodeTree')
                    graph_data = GraphData(stack) # TODO: replace with attributes on export?
                    nodes_data = graph_data.nodes_data

                    in_node = node_tree.nodes.new('NodeGroupInput')
                    out_node = node_tree.nodes.new('NodeGroupOutput')
                    input_positions = []
                    output_positions = []
                    input_ids, output_ids = {}, {}
                    
                    from material_attributes import FIELDS, interface_bundle, by_id, bundle_source
                    # Create all nodes first so a function output may reference a later expression.
                    for exr_exp in params.TryGetValue('FunctionExpressions', ()):
                        CreateNode(exr_exp.value, node_tree, nodes_data, graph_data, None)
                    for node_data in nodes_data.values():
                        if node_data.node is None: continue
                        props = node_data.export.properties
                        guid=props.TryGetValue('Id')
                        match node_data.classname:
                            case 'MaterialExpressionFunctionInput':
                                input_positions.append(node_data.node.location)
                                label=props.TryGetValue('InputName','In')
                                if props.TryGetValue('InputType')=='FunctionInput_MaterialAttributes':
                                    ids=interface_bundle(node_tree,label,'INPUT')
                                    for k,ident in ids.items(): node_tree.links.new(by_id(in_node.outputs,ident),node_data.node.inputs[k])
                                    node_data.function_interface_bound=True
                                else:
                                    socket=node_tree.interface.new_socket(name=label,in_out='INPUT',socket_type=ue_to_bl_type.get(props.TryGetValue('InputType','FunctionInput_Vector3'),'NodeSocketVector'))
                                    ids=socket.identifier
                                    node_tree.links.new(by_id(in_node.outputs,ids),node_data.node.inputs[0])
                                if guid is not None: input_ids[str(guid)]=ids
                            case 'MaterialExpressionFunctionOutput':
                                output_positions.append(node_data.node.location)
                                label=props.TryGetValue('OutputName','Result')
                                try: source=bundle_source(nodes_data,props.get('A'))
                                except ValueError: source=None
                                if source is not None:
                                    ids=interface_bundle(node_tree,label,'OUTPUT')
                                    for k,ident in ids.items(): node_tree.links.new(source[k],by_id(out_node.inputs,ident))
                                    node_data.function_interface_bound=True
                                else:
                                    socket=node_tree.interface.new_socket(name=label,in_out='OUTPUT',socket_type='NodeSocketVector')
                                    ids=socket.identifier
                                    node_tree.links.new(node_data.node.outputs[0],by_id(out_node.inputs,ids))
                                if guid is not None: output_ids[str(guid)]=ids
                    import json
                    node_tree['UE_input_ids'] = json.dumps(input_ids)
                    node_tree['UE_output_ids'] = json.dumps(output_ids)
                    if len(input_positions) > 0:
                        in_pos = Vector((0,0))
                        for pos in input_positions: in_pos += pos
                        in_node.location = in_pos / len(input_positions) + Vector((-300,50))
                    if len(output_positions) > 0:
                        out_pos = Vector((0,0))
                        for pos in output_positions: out_pos += pos
                        out_node.location = out_pos / len(output_positions) + Vector((200,50))
                    for name in nodes_data:
                        LinkSockets(node_tree, nodes_data, nodes_data[name]) # TODO: this iterates nodes without links!
    
    if log and out is not None: print(f"Imported {out.name}: {(time.time() - t0) * 1000:.2f}ms")
    if isinstance(out, bpy.types.Material):
        from wind_preview import refresh_profile
        refresh_profile(out, graph_data)
        from material_stage import incomplete_graph
        if incomplete_graph(out.node_tree):
            out['UE_material_status'] = 'partial_graph_unresolved'
            out['UE_unresolved_material'] = True
        else:
            out['UE_material_status'] = 'graph_imported_unverified'
    return (out, graph_data)
def TryGetUMaterialImport(mat_imp:Import, mesh=None):
    mat = bpy.data.materials.get(mat_imp.object_name)
    if not mat:
        umat_path = mat_imp.asset.ToProjectPath(mat_imp.import_ref.object_name)
        try: mat, graph_data = ImportNodeGraph(umat_path, mat_imp.asset.uproject, mesh=mesh)
        except Exception as e: print(f"Failed to Import {mat_imp.object_name}: {e}")
    return mat

def menu_import_umat(self, context): self.layout.operator(ImportUMat.bl_idname, text="UE Material (.uasset)")
class ImportUMat(bpy.types.Operator, ImportHelper):
    """Import Unreal Engine Material File"""
    bl_idname    = "import.umat"
    bl_label     = "Import"
    filename_ext = ".uasset"
    filter_glob: StringProperty(default="*.uasset", options={'HIDDEN'}, maxlen=255)
    files:       CollectionProperty(type=bpy.types.OperatorFileListElement, options={'HIDDEN','SKIP_SAVE'})
    directory:   StringProperty(options={'HIDDEN'})

    def execute(self, context):
        for file in self.files:
            if file.name != "": ImportNodeGraph(self.directory + file.name)
        return {'FINISHED'}

ImportUMat.__annotations__ = {name: eval(value, globals()) if isinstance(value, str) else value
                              for name, value in ImportUMat.__annotations__.items()}
reg_classes = ( ImportUMat, )

def register():
    register_helper.RegisterClasses(reg_classes)
    register_helper.RegisterDrawFnc(bpy.types.TOPBAR_MT_file_import, ImportUMat, menu_import_umat)
def unregister():
    register_helper.TryUnregisterClasses(reg_classes)
    register_helper.UnregisterDrawFnc(bpy.types.TOPBAR_MT_file_import, ImportUMat, menu_import_umat)

if __name__ != "umat":
    importlib.reload(uasset)
    unregister()
    register()

    for mat in bpy.data.materials: bpy.data.materials.remove(mat)
    for group in bpy.data.node_groups: bpy.data.node_groups.remove(group)

    #filepath = r"F:\Projects\Unreal Projects\Assets\Content\ModSci_Engineer\Materials\M_Base_Trim.uasset"
    #filepath = r"F:\Projects\Unreal Projects\Assets\Content\ModSci_Engineer\Materials\MI_Trim_A_Red2.uasset"
    #filepath = r"C:\Users\jdeacutis\Documents\Unreal Projects\Assets\Content\NewMaterial.uasset"
    #filepath = r"F:\Projects\Unreal Projects\Assets\Content\Test1434.uasset"
    #filepath = r"C:\Program Files\Epic Games\UE_4.27\Engine\Content\EngineMaterials\DefaultMaterial.uasset"
    #filepath = r"C:\Users\jdeacutis\Documents\Unreal Projects\Assets\Content\StarterBundle\ModularScifiProps\Materials\MI_Laptop_Mail.uasset"
    #filepath = r"C:/Users/jdeacutis/Documents/Unreal Projects/Assets/Content/StarterBundle/UE4_Assets/Environment_B/Materials/M_BigSnow.uasset"
    #filepath = r"C:\Users\jdeacutis\Documents\Unreal Projects\Assets\Content\Military_VOL5_Devices\Materials\MI_Mortar_02a.uasset"
    #filepath = r"C:\Users\jdeacutis\Documents\Unreal Projects\Assets\Content\Military_VOL3_Checkpoint\Materials\MI_Sandbags_02a.uasset"
    #filepath = r"C:/Users/jdeacutis/Documents/Unreal Projects/Assets/Content/Military_VOL3_Checkpoint/Materials/MI_Barbed_Wire_Stop_01a.uasset"
    filepath = r"C:\Users\jdeacutis\Documents\Unreal Projects\Assets\Content\FPS_Weapon_Bundle\Weapons\Materials\Master_Material\M_RDS_Master.uasset"
    ImportNodeGraph(filepath)
    print("Done")