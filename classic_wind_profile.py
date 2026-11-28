"""Read the recovered local wind wrapper from typed, expanded graph records.
Only source interface GUIDs, scalar lerps and vertex-red mask are recovered.
The missing engine SimpleGrassWind implementation is never synthesized.
"""
from uuid import UUID
import math

ENGINE='/Engine/Functions/Engine_MaterialFunctions01/WorldPositionOffset/SimpleGrassWind'
NAMES={'WindStregth','WindIntensity','WindSpeed'}
PROFILE='simple_grass_wind_one_minus_red_v1'


def require(ok,message):
    if not ok:raise NotImplementedError(message)


def extract_profile(data):
    nodes=data['nodes'];wpo=data['outputs'].get('WorldPositionOffset')
    if not wpo or not wpo['index']:return None
    def get(edge,kind,output=0,mask=None):
        require(edge and edge['index'] in nodes and edge['output']==output and edge['mask']==(mask if mask is not None else [0]*5),'Unsupported wind expression link')
        node=nodes[edge['index']];require(node['kind']==kind,'Unexpected wind expression '+kind);return node
    def src(node,key,kind):return get(node['inputs'].get(key),kind)
    require(not wpo['use_constant'],'Constant wind surface')
    call=get(wpo,'MaterialFunctionCall');package=call['function'];outputs=call.get('expanded_outputs',[])
    require(package.startswith('/Game/') and not call['function_inputs'] and len(call['function_outputs'])==len(outputs)==1,'Unsupported wind wrapper interface')
    out=nodes[outputs[0]];require(out['kind']=='FunctionOutput' and out.get('source_function')==package and out['interface_guid']==call['function_outputs'][0]['guid'],'Wind output GUID mismatch')
    mul=src(out,'A','Multiply');engine=src(mul,'A','MaterialFunctionCall');inverse=src(mul,'B','OneMinus')
    require(engine['function']==ENGINE and len(engine['function_inputs'])==4 and len(engine['function_outputs'])==1,'Unsupported engine wind interface')
    get(inverse['inputs'].get('Input'),'VertexColor',1,[1,1,0,0,0])
    parameters={};sockets=[]
    for entry in engine['function_inputs']:
        link=entry['edge'];require(link['index'] in nodes and link['output']==0 and link['mask']==[0]*5,'Invalid wind input')
        n=nodes[link['index']];guid=str(UUID(bytes_le=bytes.fromhex(entry['guid'])))
        if n['kind']=='LinearInterpolate':
            a=src(n,'A','Constant')['value'];b=src(n,'B','Constant')['value'];p=src(n,'Alpha','ScalarParameter');name=p['parameter'];default=p['default_value'];value=p['value']
            require(name in NAMES and name not in parameters and all(map(math.isfinite,(a,b,default,value))),'Invalid wind parameter')
            parameters[name]={'default':default,'material_value':value,'custom_primitive_index':p.get('custom_primitive_index')}
            sockets.append(dict(guid=guid,parameter=name,a=a,b=b,material_lerp_value=a+(b-a)*value))
        elif n['kind']=='Constant3Vector':
            value=n['value'];require(len(value)==4 and all(map(math.isfinite,value)),'Invalid wind vector');sockets.append(dict(guid=guid,constant_rgb=value[:3]))
        else:raise NotImplementedError('Unsupported wind input expression')
    require(set(parameters)==NAMES and len({s['guid'] for s in sockets})==4,'Incomplete wind interface')
    return dict(profile=PROFILE,source_function=package,engine_function=ENGINE,mask='1 - vertex color red',parameters=parameters,engine_inputs=sockets,engine_input_semantics_verified=False,actor_custom_primitive_data_verified=False)
