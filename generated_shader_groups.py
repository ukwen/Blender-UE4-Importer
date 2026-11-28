"""Generate original graphs from mathematical definitions and Blender's node API.

The compatibility keys and socket contracts are required by the existing importer.
No old .blend node library is opened, embedded, or copied. Approximate renderer
semantics are identified explicitly. Unknown function graphs remain unsupported.
"""
import math
import bpy

SCHEMA = 'ui-generated-shaders-1'
KEYS = ('Log','Round','Truncate','Sign','Step','SmoothStep','Sine','Cosine','Tangent',
        'Const3','RGBA','If','TwoSidedSign','CameraPosition','CameraVector','ScreenPosition',
        'Desaturation','BlendAngleCorrectedNormals','RGBtoNormal','RGBtoNormalY-',
        'NormalToRGB','AdditiveSurface')
F='NodeSocketFloat'; V='NodeSocketVector'; C='NodeSocketColor'; S='NodeSocketShader'

class Graph:
    def __init__(self,key,inputs,outputs):
        self.tree=bpy.data.node_groups.new(key,'ShaderNodeTree')
        self.tree['UI_generated_schema']=SCHEMA
        self.tree['UI_group_key']=key
        for name,typ,default in inputs:
            sock=self.tree.interface.new_socket(name=name,in_out='INPUT',socket_type=typ)
            if default is not None: sock.default_value=default
        for name,typ in outputs:
            self.tree.interface.new_socket(name=name,in_out='OUTPUT',socket_type=typ)
        self.src=self.tree.nodes.new('NodeGroupInput');self.src.location=(-600,0)
        self.dst=self.tree.nodes.new('NodeGroupOutput');self.dst.location=(600,0)
        self.count=0
    def node(self,kind,op=None):
        n=self.tree.nodes.new(kind);n.location=(-350+(self.count//5)*190,200-(self.count%5)*150);self.count+=1
        if op is not None:n.operation=op
        return n
    def set(self,socket,value):
        if isinstance(value,bpy.types.NodeSocket):self.tree.links.new(value,socket)
        else:socket.default_value=value
    def scalar(self,op,*values):
        n=self.node('ShaderNodeMath',op)
        for i,v in enumerate(values):self.set(n.inputs[i],v)
        return n.outputs[0]
    def vector(self,op,*values):
        n=self.node('ShaderNodeVectorMath',op)
        for i,v in enumerate(values):self.set(n.inputs[i],v)
        return n.outputs[0]
    def split(self,value):
        n=self.node('ShaderNodeSeparateXYZ');self.set(n.inputs[0],value);return list(n.outputs)
    def combine(self,values):
        n=self.node('ShaderNodeCombineXYZ')
        for i,v in enumerate(values):self.set(n.inputs[i],v)
        return n.outputs[0]
    def mix(self,f,a,b):
        n=self.node('ShaderNodeMixRGB');n.blend_type='MIX'
        for i,v in enumerate((f,a,b)):self.set(n.inputs[i],v)
        return n.outputs[0]
    def result(self,*values):
        for i,v in enumerate(values):self.set(self.dst.inputs[i],v)
        return self.tree
    def approximate(self,reason):self.tree['UI_approximation']=reason


def build(key):
    if key in ('Log','Round','Truncate','Sign','Step','SmoothStep','Sine','Cosine','Tangent'):
        specs={'Log':[('X',F,1),('Base',F,2)],'Step':[('Y',F,0),('X',F,1)],'SmoothStep':[('Min',F,0),('Max',F,1),('Value',F,0)]}
        inputs=specs.get(key,[('Input',F,0),('Period',F,1)] if key in ('Sine','Cosine','Tangent') else [('Input',F,0)])
        g=Graph(key,inputs,[('Value',F)]);x=list(g.src.outputs)[:len(inputs)];m=g.scalar
        if key=='Log':v=m('LOGARITHM',*x)
        elif key=='Round':v=m('FLOOR',m('ADD',x[0],.5))
        elif key=='Truncate':v=m('TRUNC',x[0])
        elif key=='Sign':v=m('SIGN',x[0])
        elif key=='Step':v=m('SUBTRACT',1,m('LESS_THAN',x[1],x[0]))
        elif key=='SmoothStep':
            t=m('MINIMUM',1,m('MAXIMUM',0,m('DIVIDE',m('SUBTRACT',x[2],x[0]),m('SUBTRACT',x[1],x[0]))));v=m('MULTIPLY',m('MULTIPLY',t,t),m('SUBTRACT',3,m('MULTIPLY',2,t)))
        else:v=m({'Sine':'SINE','Cosine':'COSINE','Tangent':'TANGENT'}[key],m('MULTIPLY',math.tau,m('DIVIDE',*x)))
        return g.result(v)
    if key in ('Const3','RGBA'):
        inputs=[('RGB',C,(0,0,0,1))]+([('A',F,1)] if key=='RGBA' else [])
        g=Graph(key,inputs,[('RGB',C),('R',F),('G',F),('B',F)]+([('A',F)] if key=='RGBA' else []));rgb=g.src.outputs['RGB'];return g.result(rgb,*g.split(rgb),*([g.src.outputs['A']] if key=='RGBA' else []))
    if key in ('RGBtoNormal','RGBtoNormalY-','NormalToRGB'):
        encode=key=='NormalToRGB';g=Graph(key,[('Normal' if encode else 'RGB',V if encode else C,(0,0,1) if encode else (.5,.5,1,1))],[('RGB' if encode else 'Normal',C if encode else V)])
        values=g.split(g.src.outputs[0]);out=[]
        for i,x in enumerate(values):
            if encode:out.append(g.scalar('MULTIPLY_ADD',x,.5,.5))
            else:out.append(g.scalar('MULTIPLY_ADD',x,-2,1) if key.endswith('Y-') and i==1 else g.scalar('MULTIPLY_ADD',x,2,-1))
        return g.result(g.combine(out))
    if key=='If':
        g=Graph(key,[('A',F,0),('B',F,0),('EqualsThreshold',F,1e-5),('Greater',C,(0,0,0,1)),('Equal',C,(0,0,0,1)),('Less',C,(0,0,0,1))],[('Result',C)]);a,b,e,hi,eq,lo=list(g.src.outputs)[:6];delta=g.scalar('SUBTRACT',a,b);return g.result(g.mix(g.scalar('LESS_THAN',g.scalar('ABSOLUTE',delta),e),g.mix(g.scalar('GREATER_THAN',a,b),lo,hi),eq))
    if key=='Desaturation':
        g=Graph(key,[('Input',C,(0,0,0,1)),('Fraction',F,0)],[('Color',C)]);rgb,f=list(g.src.outputs)[:2];v=g.node('ShaderNodeVectorMath','DOT_PRODUCT');g.set(v.inputs[0],rgb);v.inputs[1].default_value=(.3,.59,.11);gray=g.combine([v.outputs['Value']]*3);return g.result(g.mix(f,rgb,gray))
    if key=='TwoSidedSign':
        g=Graph(key,[],[('Sign',F)]);return g.result(g.scalar('MULTIPLY_ADD',g.node('ShaderNodeNewGeometry').outputs['Backfacing'],-2,1))
    if key=='CameraPosition':
        g=Graph(key,[],[('Position',V)]);n=g.node('ShaderNodeVectorTransform');n.vector_type='POINT';n.convert_from='CAMERA';n.convert_to='WORLD';return g.result(n.outputs[0])
    if key=='CameraVector':
        g=Graph(key,[],[('Direction',V)]);g.approximate('Blender incoming world direction; Unreal coordinate basis not calibrated');return g.result(g.node('ShaderNodeNewGeometry').outputs['Incoming'])
    if key=='ScreenPosition':
        g=Graph(key,[],[('Position',V)]);g.approximate('Blender Window coordinates; Unreal viewport mapping not calibrated');return g.result(g.node('ShaderNodeTexCoord').outputs['Window'])
    if key=='BlendAngleCorrectedNormals':
        g=Graph(key,[('Base',V,(0,0,1)),('Detail',V,(0,0,1))],[('Normal',V)]);a,b=list(g.src.outputs)[:2];t=g.vector('ADD',a,(0,0,1));u=g.vector('MULTIPLY',b,(-1,-1,1));d=g.node('ShaderNodeVectorMath','DOT_PRODUCT');g.set(d.inputs[0],t);g.set(d.inputs[1],u);z=g.split(t)[2];k=g.scalar('DIVIDE',d.outputs['Value'],z);scale=g.node('ShaderNodeVectorMath','SCALE');g.set(scale.inputs[0],t);g.set(scale.inputs['Scale'],k);return g.result(g.vector('NORMALIZE',g.vector('SUBTRACT',scale.outputs[0],u)))
    if key=='AdditiveSurface':
        g=Graph(key,[('Emission',C,(0,0,0,1))],[('Surface',S)]);g.approximate('Transparent plus emission; no Unreal blend parity');e=g.node('ShaderNodeEmission');g.set(e.inputs['Color'],g.src.outputs[0]);a=g.node('ShaderNodeAddShader');g.set(a.inputs[0],g.node('ShaderNodeBsdfTransparent').outputs[0]);g.set(a.inputs[1],e.outputs[0]);return g.result(a.outputs[0])
    raise KeyError(key)


def find(key):
    return next((g for g in bpy.data.node_groups if g.get('UI_generated_schema')==SCHEMA and g.get('UI_group_key')==key),None)


def get(key):
    if key not in KEYS:raise KeyError(key)
    return find(key) or build(key)


def ensure():
    return {key:get(key) for key in KEYS}
