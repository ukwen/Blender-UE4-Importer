"""Controlled UE4.27 expression bytes; not evidence of original layer assets."""
import struct
import unittest
from dataclasses import replace
from unittest.mock import patch
from uuid import UUID
from package_records import PackageRecords, ExportRecord, ImportRecord
from layer_function_graph import read_function, validate

NAMES = ('None','FunctionExpressions','ArrayProperty','ObjectProperty','Id','StructProperty','Guid','InputName','NameProperty','InputType','FunctionInput_MaterialAttributes','SortPriority','IntProperty','OutputName','A','B','Alpha','ExpressionInput','Roughness','DefaultValue','FloatProperty','ParameterName','Shared','Bottom','Top','Result','LinearColor','Tint','BaseColor','Constant','R','ConstA','ConstB','ConstAlpha','Input','Texture','SamplerType','SAMPLERTYPE_Color','SAMPLERTYPE_Normal','Coordinates','Tex')
def fname(n):return struct.pack('<ii',NAMES.index(n),0)
def tag(n,k,v,extra=b''):return fname(n)+fname(k)+struct.pack('<ii',len(v),0)+extra+b'\0'+v
def st(n,k,v):return tag(n,'StructProperty',v,fname(k)+bytes(16))
def edge(n,i):return st(n,'ExpressionInput',struct.pack('<ii',i,0)+fname('None')+bytes(20))
def prop(n,v):return tag(n,'NameProperty',fname(v))
def idtag(i):return st('Id','Guid',UUID(int=i).bytes_le)
def record(kind,body):return kind,body+fname('None')
def make_fixture(blend=False):
    if blend:
        kinds=[record('MaterialExpressionFunctionInput',idtag(1)+prop('InputName','Bottom')+prop('InputType','FunctionInput_MaterialAttributes')),record('MaterialExpressionFunctionInput',idtag(2)+prop('InputName','Top')+prop('InputType','FunctionInput_MaterialAttributes')+tag('SortPriority','IntProperty',struct.pack('<i',1))),record('MaterialExpressionScalarParameter',prop('ParameterName','Shared')+tag('DefaultValue','FloatProperty',struct.pack('<f',.25))),record('MaterialExpressionBlendMaterialAttributes',edge('A',2)+edge('B',3)+edge('Alpha',4)),record('MaterialExpressionFunctionOutput',idtag(3)+prop('OutputName','Result')+edge('A',5))]
    else:
        kinds=[record('MaterialExpressionScalarParameter',prop('ParameterName','Shared')+tag('DefaultValue','FloatProperty',struct.pack('<f',.2))),record('MaterialExpressionMakeMaterialAttributes',edge('Roughness',2)),record('MaterialExpressionFunctionOutput',idtag(3)+prop('OutputName','Result')+edge('A',3))]
    refs=list(range(2,len(kinds)+2));root=record('MaterialFunctionMaterialLayerBlend' if blend else 'MaterialFunctionMaterialLayer',tag('FunctionExpressions','ArrayProperty',struct.pack('<'+'i'*(len(refs)+1),len(refs),*refs),fname('ObjectProperty')))
    raw=b'';exports=[]
    for i,(kind,body) in enumerate([root]+kinds):
        exports.append(ExportRecord('Function' if i==0 else 'Expr'+str(i),0,0,0,int(i!=0),len(raw),len(body),None,None,False,kind));raw+=body
    return dict(ue4=522,ue5=None,licensee=0),raw,PackageRecords(NAMES,(),tuple(exports))
def fixture(blend=False):
    with patch('layer_function_graph.read_package',return_value=make_fixture(blend)):
        return read_function('controlled.uasset')

class LayerFunctionTests(unittest.TestCase):
    def test_decode(self):
        a,b=fixture(),fixture(True);self.assertEqual(a.usage,'MaterialLayer');self.assertEqual(b.usage,'MaterialLayerBlend');self.assertEqual(len(validate(b)[1]),2)
        self.assertEqual(a.expressions[0].parameter,'Shared');self.assertAlmostEqual(a.expressions[0].value,.2)
    def test_invalid_graph(self):
        a=fixture(True);n=a.expressions[3]
        for links in ((('A',5),('B',3)),(('A',4),('B',3)),(('A',2),('B',99))):
            with self.assertRaises(ValueError):validate(replace(a,expressions=a.expressions[:3]+(replace(n,inputs=links),)+a.expressions[4:]))
        with self.assertRaises(ValueError):validate(replace(a,expressions=(a.expressions[0],replace(a.expressions[1],priority=0))+a.expressions[2:]))
    def test_ownership(self):
        m,raw,t=make_fixture();bad=replace(t.exports[1],outer=0)
        with patch('layer_function_graph.read_package',return_value=(m,raw,replace(t,exports=(t.exports[0],bad)+t.exports[2:]))):
            with self.assertRaises(ValueError):read_function('controlled.uasset')


def math_fixture():
    def number(key,value):return tag(key,'FloatProperty',struct.pack('<f',value))
    kinds=[
        record('MaterialExpressionVectorParameter',prop('ParameterName','Tint')+st('DefaultValue','LinearColor',struct.pack('<4f',.2,.4,.6,.75))),
        record('MaterialExpressionConstant',number('R',.2)),
        record('MaterialExpressionAdd',edge('A',3)+number('ConstB',.1)),
        record('MaterialExpressionMultiply',edge('A',4)+number('ConstB',2.)),
        record('MaterialExpressionSubtract',edge('A',5)+number('ConstB',.1)),
        record('MaterialExpressionOneMinus',edge('Input',6)),
        record('MaterialExpressionLinearInterpolate',edge('A',7)+number('ConstB',.7)+number('ConstAlpha',1.5)),
        record('MaterialExpressionMakeMaterialAttributes',edge('BaseColor',2)+edge('Roughness',8)),
        record('MaterialExpressionFunctionOutput',idtag(3)+prop('OutputName','Result')+edge('A',9))]
    refs=list(range(2,len(kinds)+2));root=record('MaterialFunctionMaterialLayer',tag('FunctionExpressions','ArrayProperty',struct.pack('<'+'i'*(len(refs)+1),len(refs),*refs),fname('ObjectProperty')))
    raw=b'';exports=[]
    for i,(kind,body) in enumerate([root]+kinds):
        exports.append(ExportRecord('MathFunction' if i==0 else 'Expr'+str(i),0,0,0,int(i!=0),len(raw),len(body),None,None,False,kind));raw+=body
    with patch('layer_function_graph.read_package',return_value=(dict(ue4=522,ue5=None,licensee=0),raw,PackageRecords(NAMES,(),tuple(exports)))):
        return read_function('controlled_math.uasset')

class ExtendedLayerFunctionTests(unittest.TestCase):
    def test_vector_math_decode(self):
        fn=math_fixture();nodes,_,_=validate(fn)
        self.assertEqual(nodes[2].parameter,'Tint');self.assertAlmostEqual(nodes[2].color[3],.75)
        self.assertEqual([nodes[i].kind for i in range(4,9)],['Add','Multiply','Subtract','OneMinus','LinearInterpolate'])
        self.assertAlmostEqual(dict(nodes[8].defaults)['Alpha'],1.5)
    def test_reject_vector_scalar_mix(self):
        fn=math_fixture();bad=replace(fn.expressions[2],inputs=(('A',2),))
        with self.assertRaises(NotImplementedError):validate(replace(fn,expressions=fn.expressions[:2]+(bad,)+fn.expressions[3:]))
    def test_reject_missing_one_minus_and_duplicate_defaults(self):
        fn=math_fixture()
        for index,changes in [(5,{'inputs':()}),(2,{'defaults':(('A',0.),('A',1.),('B',0.))})]:
            with self.assertRaises(ValueError):validate(replace(fn,expressions=fn.expressions[:index]+(replace(fn.expressions[index],**changes),)+fn.expressions[index+1:]))
    def test_constant_vector(self):
        from layer_function_graph import decode_expression
        from classic_material import property_map
        kind,body=record('MaterialExpressionConstant3Vector',st('Constant','LinearColor',struct.pack('<4f',.1,.2,.3,1.)))
        e=ExportRecord('Const',0,0,0,1,0,len(body),None,None,False,kind)
        n=decode_expression(2,'Constant3Vector','Const',property_map(body,e,NAMES),NAMES)
        self.assertAlmostEqual(n.color[2],.3)


def texture_fixture_data(sampler='SAMPLERTYPE_Color', coordinate=0, texture=-1):
    kinds=[record('MaterialExpressionTextureSampleParameter2D',prop('ParameterName','Tex')+tag('Texture','ObjectProperty',struct.pack('<i',texture))+prop('SamplerType',sampler)+edge('Coordinates',coordinate)),record('MaterialExpressionMakeMaterialAttributes',edge('BaseColor',2)),record('MaterialExpressionFunctionOutput',idtag(3)+prop('OutputName','Result')+edge('A',3))]
    refs=list(range(2,len(kinds)+2));root=record('MaterialFunctionMaterialLayer',tag('FunctionExpressions','ArrayProperty',struct.pack('<'+'i'*(len(refs)+1),len(refs),*refs),fname('ObjectProperty')))
    raw=b'';exports=[]
    for i,(kind,body) in enumerate([root]+kinds):
        exports.append(ExportRecord('TextureFunction' if i==0 else 'Expr'+str(i),0,0,0,int(i!=0),len(raw),len(body),None,None,False,kind));raw+=body
    imports=(ImportRecord('/Script/Engine','Texture2D',-2,'Source','None',False),ImportRecord('/Script/CoreUObject','Package',0,'/Game/Source','None',False))
    return dict(ue4=522,ue5=None,licensee=0,status='tables_inspected',flags=0,sidecars=[]),raw,PackageRecords(NAMES,imports,tuple(exports))

class LayerTextureTests(unittest.TestCase):
    def test_texture_reference(self):
        with patch('layer_function_graph.read_package',return_value=texture_fixture_data()):
            fn=read_function('controlled_texture.uasset')
        self.assertEqual(fn.expressions[0].texture,'/Game/Source');self.assertEqual(fn.expressions[0].parameter,'Tex')
    def test_texture_unsupported(self):
        for kwargs in ({'sampler':'SAMPLERTYPE_Normal'},{'coordinate':3}):
            with patch('layer_function_graph.read_package',return_value=texture_fixture_data(**kwargs)),self.assertRaises(NotImplementedError):read_function('controlled_texture.uasset')
        with patch('layer_function_graph.read_package',return_value=texture_fixture_data(texture=-2)),self.assertRaises(ValueError):read_function('controlled_texture.uasset')

    def test_unserialized_math_default(self):
        from layer_function_graph import decode_expression
        from classic_material import property_map
        kind,body=record('MaterialExpressionAdd',edge('A',3))
        entry=ExportRecord('Math',0,0,0,1,0,len(body),None,None,False,kind)
        with self.assertRaises(NotImplementedError):decode_expression(2,'Add','Math',property_map(body,entry,NAMES),NAMES)
