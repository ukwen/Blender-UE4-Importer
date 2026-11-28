"""Controlled UE4.27 expression bytes; not evidence of original layer assets."""
import struct
import unittest
from dataclasses import replace
from unittest.mock import patch
from uuid import UUID
from package_records import PackageRecords, ExportRecord
from layer_function_graph import read_function, validate

NAMES = ('None','FunctionExpressions','ArrayProperty','ObjectProperty','Id','StructProperty','Guid','InputName','NameProperty','InputType','FunctionInput_MaterialAttributes','SortPriority','IntProperty','OutputName','A','B','Alpha','ExpressionInput','Roughness','DefaultValue','FloatProperty','ParameterName','Shared','Bottom','Top','Result')
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
