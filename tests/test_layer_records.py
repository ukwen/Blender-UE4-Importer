"""Controlled serialized UE4.27 layer arrays; no original layer package available."""
import struct
import unittest
from dataclasses import replace, FrozenInstanceError
from uuid import UUID
from package_records import ImportRecord, PackageRecords
from ue4_property_records import PropertyRecord
from layer_records import decode_stack, decode_override, LayerStack, DetachedSnapshot

NAMES = ('None','DefaultLayers','StructProperty','MaterialLayersFunctions','Layers','Blends','LayerStates','ArrayProperty','ObjectProperty','BoolProperty','MaterialLayersParameters','StaticMaterialLayersParameter','ParameterInfo','MaterialParameterInfo','Name','NameProperty','LayerGuids','Guid','LayerLinkStates','ByteProperty','UnlinkedFromParent','LinkedToParent','bOverride','Value','Stack','Association','GlobalParameter','Index','IntProperty')
TABLE = PackageRecords(NAMES, (
    ImportRecord('/Script/Engine','MaterialFunctionMaterialLayer',-4,'LayerA','None',False),
    ImportRecord('/Script/Engine','MaterialFunctionMaterialLayer',-5,'LayerB','None',False),
    ImportRecord('/Script/Engine','MaterialFunctionMaterialLayerBlend',-6,'Blend','None',False),
    ImportRecord('/Script/CoreUObject','Package',0,'/Game/A','None',False),
    ImportRecord('/Script/CoreUObject','Package',0,'/Game/B','None',False),
    ImportRecord('/Script/CoreUObject','Package',0,'/Game/Blend','None',False)), ())
IDS = tuple(UUID(int=i) for i in (1,2,3))

def fn(x): return struct.pack('<ii',NAMES.index(x),0)
def tag(n,k,data,extra=b''): return fn(n)+fn(k)+struct.pack('<ii',len(data),0)+extra+b'\0'+data
def arr(n,k,data,count): return tag(n,'ArrayProperty',struct.pack('<i',count)+data,fn(k))
def struct_tag(n,k,data): return tag(n,'StructProperty',data,fn(k)+bytes(16))
def struct_array(n,k,data,count): return arr(n,'StructProperty',fn(n)+fn('StructProperty')+struct.pack('<q',len(data))+fn(k)+bytes(17)+data,count)
def topology(indices=(-1,-2,-1),blends=(0,-3),states=(1,0,1)):
    return arr('Layers','ObjectProperty',struct.pack('<'+'i'*len(indices),*indices),len(indices))+arr('Blends','ObjectProperty',struct.pack('<'+'i'*len(blends),*blends),len(blends))+arr('LayerStates','BoolProperty',bytes(states),len(states))
def default_record(**kwargs): return PropertyRecord('DefaultLayers','StructProperty',0,('MaterialLayersFunctions',),topology(**kwargs)+fn('None'))
def override_fields(guids=IDS,links=('UnlinkedFromParent',)*3,indices=(-1,-2,-1),blends=(0,-3),states=(1,0,1),enabled=True):
    info=struct_tag('ParameterInfo','MaterialParameterInfo',tag('Name','NameProperty',fn('Stack'))+fn('None'))
    value=struct_tag('Value','MaterialLayersFunctions',topology(indices,blends,states)+struct_array('LayerGuids','Guid',b''.join(g.bytes_le for g in guids),len(guids))+arr('LayerLinkStates','ByteProperty',b''.join(map(fn,links)),len(links))+fn('None'))
    record=info+fn('bOverride')+fn('BoolProperty')+bytes(8)+bytes([enabled,0])+value+fn('None')
    from layer_records import fields
    from skeleton_native import Reader
    return fields(Reader(struct_array('MaterialLayersParameters','StaticMaterialLayersParameter',record,1)+fn('None')),NAMES)

class LayerRecordTests(unittest.TestCase):
    def test_stack(self):
        s=decode_stack(default_record(),TABLE)
        self.assertEqual(s,LayerStack(('/Game/A','/Game/B','/Game/A'),(None,'/Game/Blend'),(True,False,True)))
        with self.assertRaises(FrozenInstanceError): s.states=()
    def test_snapshot(self):
        s=decode_override(override_fields(),TABLE)
        self.assertIsInstance(s,DetachedSnapshot);self.assertEqual(s.guids,IDS);self.assertEqual(s.name,'Stack')
        self.assertIs(decode_override(override_fields(enabled=False),TABLE),False)
        self.assertIsNone(decode_override({},TABLE))
    def test_invalid_topologies(self):
        for kwargs in ({'states':(0,1,1)},{'states':(1,2,1)},{'indices':(-3,-2,-1)},{'indices':(0,-2,-1)},{'indices':(-99,-2,-1)},{'blends':(0,)},{'blends':(-1,-3)}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError): decode_stack(default_record(**kwargs),TABLE)
        p=default_record()
        for data in (p.data[:-1],p.data+b'X'):
            with self.assertRaises(ValueError): decode_stack(replace(p,data=data),TABLE)
    def test_invalid_snapshots(self):
        for kwargs in ({'guids':(IDS[0],)*3},{'guids':IDS[:2]},{'guids':(UUID(int=0),*IDS[1:])},{'links':('LinkedToParent',)*3}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError): decode_override(override_fields(**kwargs),TABLE)
        p=override_fields();a=p['MaterialLayersParameters']
        for data in (a.data[:-1],a.data+b'X'):
            with self.assertRaises(ValueError): decode_override({'MaterialLayersParameters':replace(a,data=data)},TABLE)
    def test_typed_export_dispatch(self):
        from unittest.mock import patch
        from package_records import ExportRecord
        from layer_records import read_stack, read_override
        raw=struct_tag('DefaultLayers','MaterialLayersFunctions',topology()+fn('None'))+fn('None')
        export=ExportRecord('LayerExpression',0,0,0,0,0,len(raw),None,None,False,'MaterialExpressionMaterialAttributeLayers')
        table=replace(TABLE,exports=(export,))
        meta={'ue4':522,'ue5':None,'licensee':0}
        with patch('layer_records.read_package',return_value=(meta,raw,table)):
            self.assertEqual(read_stack('controlled.uasset','LayerExpression'),decode_stack(default_record(),TABLE))
            with self.assertRaises(ValueError):read_stack('controlled.uasset','NotLayerExpression')
        with patch('layer_records.read_package',return_value=(meta,raw,replace(table,exports=(export,export)))):
            with self.assertRaises(ValueError):read_stack('controlled.uasset','LayerExpression')
        with patch('layer_records.read_package',return_value=(dict(meta,licensee=1),raw,table)):
            with self.assertRaises(ValueError):read_stack('controlled.uasset','LayerExpression')
        from material_layers import explicit_override
        self.assertIsNone(explicit_override(None,None,None))
        with self.assertRaises(ValueError):explicit_override(None,None,object())
