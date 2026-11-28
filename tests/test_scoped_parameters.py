"""Controlled scoped records and original global instance parity."""
import os, struct, unittest
from dataclasses import replace, FrozenInstanceError
from pathlib import Path
from uuid import UUID
from package_records import ImportRecord, PackageRecords
from scoped_parameters import decode_parameters, read_parameters
from classic_material_graph import read_graph
from skeleton_native import Reader
from layer_records import fields

NAMES=tuple('None ScalarParameterValues ScalarParameterValue VectorParameterValues VectorParameterValue TextureParameterValues TextureParameterValue StaticSwitchParameters StaticSwitchParameter StaticSwitchParameterValues StaticParameters StaticParameterSet ArrayProperty StructProperty ParameterInfo MaterialParameterInfo Name NameProperty Shared Association ByteProperty LayerParameter BlendParameter GlobalParameter Index IntProperty ParameterValue FloatProperty LinearColor ObjectProperty ExpressionGUID Guid bOverride BoolProperty Value'.split())
TABLE=PackageRecords(NAMES,(ImportRecord('/Script/Engine','Texture2D',-2,'Texture','None',False),ImportRecord('/Script/CoreUObject','Package',0,'/Game/Texture','None',False)),())
def fn(s): return struct.pack('<ii',NAMES.index(s),0)
def tag(n,k,data,extra=b''):return fn(n)+fn(k)+struct.pack('<ii',len(data),0)+extra+b'\0'+data
def st(n,k,data):return tag(n,'StructProperty',data,fn(k)+bytes(16))
def flag(n,v):return fn(n)+fn('BoolProperty')+bytes(8)+bytes((v,0))
def array(n,k,data,count=1):return tag(n,'ArrayProperty',struct.pack('<i',count)+fn(n)+fn('StructProperty')+struct.pack('<q',len(data))+fn(k)+bytes(17)+data,fn('StructProperty'))
def identity(index,scope='LayerParameter'):
    return st('ParameterInfo','MaterialParameterInfo',tag('Name','NameProperty',fn('Shared'))+tag('Association','ByteProperty',fn(scope),fn('None'))+tag('Index','IntProperty',struct.pack('<i',index))+fn('None'))
def records(index=1,scope='LayerParameter',scalar=.6,texture=-1,enabled=True):
    info=identity(index,scope);g=st('ExpressionGUID','Guid',UUID(int=17).bytes_le);end=fn('None')
    return (array('ScalarParameterValues','ScalarParameterValue',info+g+tag('ParameterValue','FloatProperty',struct.pack('<f',scalar))+end)+array('VectorParameterValues','VectorParameterValue',info+g+st('ParameterValue','LinearColor',struct.pack('<4f',.3,.5,.7,.9))+end)+array('TextureParameterValues','TextureParameterValue',info+g+tag('ParameterValue','ObjectProperty',struct.pack('<i',texture))+end)+st('StaticParameters','StaticParameterSet',array('StaticSwitchParameters','StaticSwitchParameter',info+g+flag('bOverride',enabled)+flag('Value',True)+end)+end))
def decode(data):return decode_parameters(fields(Reader(data+fn('None')),NAMES),TABLE)

class ScopedTests(unittest.TestCase):
    def test_four_kinds(self):
        r=decode(records()); self.assertEqual([v.kind for v in r],['scalar','vector','texture','switch']);self.assertEqual(r[2].value,'/Game/Texture');self.assertIs(r[3].value,True);self.assertTrue(all(v.index==1 and v.scope=='LayerParameter' and v.guid==UUID(int=17) for v in r));self.assertEqual(len(decode(records(enabled=False))),3)
        with self.assertRaises(FrozenInstanceError):r[0].index=2
        self.assertEqual(decode(records(-1,'GlobalParameter'))[0].scope,'GlobalParameter');self.assertEqual(decode(records(0,'BlendParameter'))[0].index,0)
    def test_reject_invalid(self):
        for raw in (records(-1),records(32),records(0,'GlobalParameter'),records(scalar=float('nan')),records(texture=0),records(texture=-2),records(texture=-3),records()[:-1]):
            with self.subTest(length=len(raw)),self.assertRaises(ValueError):decode(raw)
        item=identity(1)+tag('ParameterValue','FloatProperty',struct.pack('<f',1))+fn('None')
        with self.assertRaises(ValueError):decode(array('ScalarParameterValues','ScalarParameterValue',item+item,2))
    @unittest.skipUnless(os.environ.get('UE_CLASSIC_MATERIAL_FIXTURES'),'Original Goblin material fixtures required')
    def test_original_global_parity(self):
        for p in Path(os.environ['UE_CLASSIC_MATERIAL_FIXTURES']).glob('MI*.uasset'):
            actual=read_parameters(p,p.stem);expected=read_graph(p)['parameters'];self.assertEqual(len(actual),len(expected))
            for a,e in zip(actual,expected):
                self.assertEqual((a.kind,a.name,a.value,a.guid.bytes_le.hex()),(e['kind'],e['name'],tuple(e['value']) if isinstance(e['value'],list) else e['value'],e['guid']))
