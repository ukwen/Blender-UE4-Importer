"""Typed UE4.27 material graph and global instance records.

Reference: UAssetAPI MaterialInputProperties and StructPropertyData (MIT,
third_party/UAssetAPI-LICENSE.txt), original versioned UE4 522 editor assets.
The common graph contract is shared with the UE5 editor translator; source
runtime functions and unrecognized layer/static data are not executed.
"""
import math
import struct
from classic_material import (require, unsupported, property_map, name, scalar,
                              integer, boolean, linear_color, object_index)
from package_records import read_package, ImportRecord, ExportRecord
from skeleton_native import Reader
from ue4_property_records import read_records

PROFILE='ue4_522_graph'


def props(r,names):
    records=read_records(r,names)
    require(all(v.index==0 for v in records),'Indexed material struct properties')
    return {v.name:v for v in records}


def nested(record,names,subtype):
    require(record.kind=='StructProperty' and record.parameters==(subtype,), 'Invalid '+subtype)
    r=Reader(record.data);p=props(r,names);require(r.pos==len(r.data),'Unexpected struct tail');return p


def array(record,names,subtype):
    require(record.kind=='ArrayProperty' and record.parameters==('StructProperty',),'Invalid material struct array')
    r=Reader(record.data);n=r.count(4096)
    require(r.name(names)==record.name and r.name(names)=='StructProperty','Invalid struct-array inner tag')
    size=r.unpack('q')[0];require(r.name(names)==subtype,'Invalid struct-array element class');r.take(16)
    flag=r.take(1)[0];require(flag in (0,1),'Invalid array GUID flag')
    if flag:r.take(16)
    require(size==len(r.data)-r.pos,'Invalid struct-array extent');result=[props(r,names) for _ in range(n)]
    require(r.pos==len(r.data),'Unexpected struct-array tail');return result


def guid(record):
    require(record.kind=='StructProperty' and record.parameters==('Guid',) and len(record.data)==16,'Invalid material GUID')
    return record.data.hex()


def imported(p,key,table,classes):
    index=object_index(p,key);entry=table.reference(index);package=table.package(index)
    require(isinstance(entry,ImportRecord) and entry.kind in classes and package,'Invalid material reference '+key)
    return package


def edge(data,names):
    require(len(data)==36,'Invalid classic expression input size')
    r=Reader(data);index,output=r.unpack('2i');nm=r.name(names);mask=list(r.unpack('5i'))
    require(index>=0 and (0<=output<64 or index==0 and output==-1) and all(x in (0,1) for x in mask),'Invalid classic expression input')
    return dict(index=index,output=output,mask=mask,input_name=nm)


def surface(record,names):
    require(record.kind=='StructProperty','Invalid surface property')
    kind=record.parameters;size={('ColorMaterialInput',):44,('ScalarMaterialInput',):44,('VectorMaterialInput',):52}.get(kind)
    unsupported(size is not None,'Unsupported classic surface input '+record.name)
    require(len(record.data)==size,'Invalid surface input extent')
    out=edge(record.data[:36],names);use=struct.unpack_from('<i',record.data,36)[0];require(use in (0,1),'Invalid surface constant flag')
    if kind==('ColorMaterialInput',):
        b,g,r,a=record.data[40:];linear=lambda v:v/255/12.92 if v/255<=.04045 else ((v/255+.055)/1.055)**2.4
        value=[linear(r),linear(g),linear(b),a/255]
    else:value=list(struct.unpack('<'+'f'*((size-40)//4),record.data[40:]))
    require(all(map(math.isfinite,value)),'Nonfinite surface constant');out.update(use_constant=use,constant=value);return out


def instance(p,table,entry):
    names=table.names
    allowed={'ParameterStateId','Parent','ScalarParameterValues','VectorParameterValues','TextureParameterValues','BasePropertyOverrides','ReferencedTextureGuids','CachedReferencedTextures','TextureStreamingDataVersion','TextureStreamingData','ThumbnailInfo','LightingGuid'}
    unsupported(set(p)<=allowed,'Unsupported classic instance fields: '+', '.join(sorted(set(p)-allowed)))
    result=dict(name=entry.name,kind='instance',source_profile=PROFILE,parent=imported(p,'Parent',table,('Material','MaterialInstanceConstant')),parameters=[],unsupported=[])
    for field,kind,sub in [('ScalarParameterValues','scalar','ScalarParameterValue'),('VectorParameterValues','vector','VectorParameterValue'),('TextureParameterValues','texture','TextureParameterValue')]:
        if field not in p:continue
        for item in array(p[field],names,sub):
            unsupported(set(item)<={'ParameterInfo','ParameterValue','ExpressionGUID','AtlasData'},'Unsupported classic parameter fields')
            info=nested(item['ParameterInfo'],names,'MaterialParameterInfo')
            require(set(info)=={'Name','Association','Index'} and name(info,'Association',names,'')=='GlobalParameter' and integer(info,'Index',0)==-1,'Unsupported classic parameter scope')
            if 'AtlasData' in item:
                atlas=nested(item['AtlasData'],names,'ScalarParameterAtlasInstanceData');none=struct.pack('<3i',names.index('None'),0,0)
                unsupported(set(atlas)=={'bIsUsedAsAtlasPosition','Curve','Atlas'} and not boolean(atlas,'bIsUsedAsAtlasPosition') and all(atlas[k].kind=='SoftObjectProperty' and atlas[k].data==none for k in ('Curve','Atlas')),'Active scalar atlas unsupported')
            val=scalar(item,'ParameterValue') if kind=='scalar' else list(linear_color(item,'ParameterValue')) if kind=='vector' else imported(item,'ParameterValue',table,('Texture2D',))
            require('ParameterValue' in item,'Missing parameter value');nm=name(info,'Name',names,'');require(bool(nm),'Empty material parameter')
            result['parameters'].append(dict(kind=kind,name=nm,value=val,guid=guid(item['ExpressionGUID'])))
    require(len({(x['kind'],x['name']) for x in result['parameters']})==len(result['parameters']),'Duplicate classic global parameter')
    if 'BasePropertyOverrides' in p:
        base=nested(p['BasePropertyOverrides'],names,'MaterialInstanceBasePropertyOverrides')
        result['base_overrides']={k:dict(type=[v.kind],flags=16 if v.boolean else 0,data=v.data.hex()) for k,v in base.items()}
    return result


def read_graph(path):
    meta,raw,table=read_package(path);names=table.names
    unsupported(meta['ue4']==522 and meta['ue5'] is None and meta['licensee']==0,'Unsupported classic graph profile')
    roots=[(i,e) for i,e in enumerate(table.exports,1) if not e.outer and e.kind in ('Material','MaterialInstanceConstant','MaterialFunction')]
    unsupported(len(roots)==1,'Expected one classic material/function root');index,entry=roots[0];p=property_map(raw,entry,names)
    if entry.kind=='MaterialInstanceConstant':return instance(p,table,entry)
    function=entry.kind=='MaterialFunction'
    listkey='FunctionExpressions' if function else 'Expressions';record=p.get(listkey)
    require(record is not None and record.kind=='ArrayProperty' and record.parameters==('ObjectProperty',),'Missing expression array')
    r=Reader(record.data);refs=[r.i() for _ in range(r.count(4096))];require(r.pos==len(r.data) and len(set(refs))==len(refs),'Invalid expression array')
    common={'Material','Function','MaterialExpressionEditorX','MaterialExpressionEditorY','MaterialExpressionGuid','ExpressionGUID','Desc','Group','SortPriority'}
    nodes={}
    for i in refs:
        e=table.reference(i);require(isinstance(e,ExportRecord) and e.outer==index and e.kind.startswith('MaterialExpression'),'Invalid expression ownership')
        kind=e.kind.removeprefix('MaterialExpression')
        if kind=='Comment':continue
        q=property_map(raw,e,names)
        node=dict(kind=kind,name=e.name,parameter=name(q,'ParameterName',names,''),guid=guid(q['ExpressionGUID']) if 'ExpressionGUID' in q else '',position=[integer(q,'MaterialExpressionEditorX'),integer(q,'MaterialExpressionEditorY')],inputs={k:edge(v.data,names) for k,v in q.items() if v.kind=='StructProperty' and v.parameters==('ExpressionInput',)})
        if kind in ('ScalarParameter','Constant'):
            key='DefaultValue' if kind=='ScalarParameter' else 'R';allowed={key,'ParameterName','bUseCustomPrimitiveData','PrimitiveDataIndex'};node['value']=scalar(q,key);node['default_value']=node['value']
            if boolean(q,'bUseCustomPrimitiveData'):
                v=q.get('PrimitiveDataIndex');require(v is None or v.kind=='ByteProperty' and v.parameters==('None',) and len(v.data)==1,'Invalid primitive data index');node['custom_primitive_index']=v.data[0] if v else 0
        elif kind in ('VectorParameter','Constant3Vector'):
            key='DefaultValue' if kind=='VectorParameter' else 'Constant';allowed={key,'ParameterName'};node['value']=list(linear_color(q,key))
        elif kind in ('TextureSampleParameter2D','TextureSample'):
            allowed={'ParameterName','Texture','SamplerType','SamplerSource','Coordinates'};node.update(texture=imported(q,'Texture',table,('Texture2D',)),sampler_type=name(q,'SamplerType',names,'SAMPLERTYPE_Color'),sampler_source=name(q,'SamplerSource',names,'SSM_FromTextureAsset'))
        elif kind in ('Multiply','Add','Subtract','Divide','LinearInterpolate'):
            defaults={'A':0.,'B':1.,'Alpha':.5} if kind=='LinearInterpolate' else {k:1. if kind in ('Multiply','Divide') else 0. for k in ('A','B')};allowed=set(defaults)|{'Const'+k for k in defaults};node['defaults']={k:scalar(q,'Const'+k,v) for k,v in defaults.items()}
        elif kind=='OneMinus':allowed={'Input'}
        elif kind=='VertexColor':allowed=set()
        elif kind=='FunctionOutput':
            allowed={'A','Id','OutputName','bLastPreviewed','SortPriority'};node.update(interface_guid=guid(q['Id']),interface_name=name(q,'OutputName',names,''))
        elif kind=='MaterialFunctionCall':
            allowed={'MaterialFunction','FunctionInputs','FunctionOutputs','Outputs'};node['function']=imported(q,'MaterialFunction',table,('MaterialFunction','MaterialFunctionInstance'))
            for key,sub,idkey,result in [('FunctionInputs','FunctionExpressionInput','ExpressionInputId','function_inputs'),('FunctionOutputs','FunctionExpressionOutput','ExpressionOutputId','function_outputs')]:
                node[result]=[]
                if key not in q:continue
                for v in array(q[key],names,sub):
                    require(set(v)=={idkey,'Input' if key=='FunctionInputs' else 'Output'},'Unsupported function interface fields');row={'guid':guid(v[idkey])}
                    if key=='FunctionInputs':
                        require(v['Input'].kind=='StructProperty' and v['Input'].parameters==('ExpressionInput',),'Invalid function input');row['edge']=edge(v['Input'].data,names)
                    else:
                        require(v['Output'].kind=='StructProperty' and v['Output'].parameters==('ExpressionOutput',),'Invalid function output');row['descriptor_hex']=v['Output'].data.hex()
                    node[result].append(row)
                require(len({v['guid'] for v in node[result]})==len(node[result]),'Repeated function interface GUID')
        else:raise NotImplementedError('Unsupported classic graph expression '+kind)
        unsupported(set(q)<=common|allowed,'Unsupported '+kind+' properties: '+', '.join(sorted(set(q)-common-allowed)))
        nodes[i]=node
    for n in nodes.values():
        require(all(not a['index'] or a['index'] in nodes for a in list(n['inputs'].values())+[v['edge'] for v in n.get('function_inputs',[])]),'Expression input outside owned graph')
    if function:
        allowed={'FunctionExpressions','bExposeToLibrary','FunctionEditorComments','DependentFunctionExpressionCandidates','StateId','CombinedOutputTypes','ThumbnailInfo'}
        unsupported(set(p)<=allowed,'Unsupported classic function properties')
        interfaces=[n['interface_guid'] for n in nodes.values() if n['kind']=='FunctionOutput'];require(len(interfaces)==len(set(interfaces)),'Repeated function output GUID')
        return dict(name=entry.name,kind='function',source_profile=PROFILE,nodes=nodes,unsupported=[])
    surface_keys={'BaseColor','Metallic','Specular','Roughness','Normal','EmissiveColor','Opacity','OpacityMask','WorldPositionOffset','AmbientOcclusion'}
    metadata={'Expressions','StateId','ThumbnailInfo','LightingGuid','bCanMaskedBeAssumedOpaque','ReferencedTextureGuids','BlendMode','ShadingModel','MaterialDomain','bUseMaterialAttributes','TwoSided','OpacityMaskClipValue','EditorX','EditorY','EditorComments','CachedExpressionData','ParameterGroupData','TextureStreamingDataVersion','TextureStreamingData','ParameterOverviewExpansion','TangentSpaceNormal'}
    unsupported(all(k in surface_keys|metadata or k.startswith('bUsedWith') for k in p),'Unsupported classic material fields: '+', '.join(sorted(set(p)-surface_keys-metadata)))
    unsupported(not boolean(p,'bUseMaterialAttributes') and name(p,'MaterialDomain',names,'MD_Surface')=='MD_Surface' and name(p,'ShadingModel',names,'MSM_DefaultLit')=='MSM_DefaultLit','Unsupported classic surface semantics')
    outputs={k:surface(p[k],names) for k in surface_keys if k in p};require(all(not a['index'] or a['index'] in nodes for a in outputs.values()),'Surface input outside graph')
    return dict(name=entry.name,kind='material',source_profile=PROFILE,blend=name(p,'BlendMode',names,'BLEND_Opaque'),shading_model='MSM_DefaultLit',shading_model_field=2,material_domain='MD_Surface',tangent_space_normal=boolean(p,'TangentSpaceNormal',True),opacity_mask_clip=scalar(p,'OpacityMaskClipValue') if 'OpacityMaskClipValue' in p else None,two_sided=boolean(p,'TwoSided'),nodes=nodes,outputs=outputs,unsupported=[])
