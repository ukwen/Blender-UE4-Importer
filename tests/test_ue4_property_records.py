"""Original classic tags and controlled malformed streams."""
import os
import struct
import unittest
from unittest.mock import patch
import tempfile
from pathlib import Path
from skeleton_native import Reader
from ue4_property_records import read_records, read_tagged_properties
from package_records import read_package


class ClassicTagTests(unittest.TestCase):
    names = ('None', 'Field', 'IntProperty', 'BoolProperty', 'MapProperty', 'NameProperty')

    def tag(self, kind, payload, index=0, metadata=b'', guid=b'\0'):
        return struct.pack('<6i', 1, 0, kind, 0, len(payload), index) + metadata + guid + payload

    def test_indexed_and_native_tail(self):
        data = self.tag(2, struct.pack('<i', 17)) + self.tag(2, struct.pack('<i', 18), index=1) + bytes(8) + b'native'
        reader = Reader(data)
        records = read_records(reader, self.names)
        self.assertEqual([r.index for r in records], [0, 1])
        self.assertEqual(reader.take(6), b'native')
        with self.assertRaises(ValueError):
            read_tagged_properties(Reader(data), self.names)

    def test_invalid_and_opaque_tags(self):
        for data in (self.tag(2,b'1234')[:-1], self.tag(3,b'',metadata=b'\x02')+bytes(8), self.tag(2,b'1234',guid=b'\x02')+bytes(8), self.tag(2,b'1234')*2+bytes(8)):
            with self.subTest(data=data), self.assertRaises(ValueError):
                read_records(Reader(data),self.names)
        data=self.tag(4,b'opaque',metadata=struct.pack('<4i',5,0,2,0))+bytes(8)
        record=read_records(Reader(data),self.names)[0]
        self.assertEqual(record.parameters,('NameProperty','IntProperty'))
        self.assertEqual(record.data,b'opaque')

    @unittest.skipUnless(os.environ.get('UASSETAPI_ASSETS'),'Original UE4 editor fixtures required')
    def test_original_roots(self):
        root=Path(os.environ['UASSETAPI_ASSETS'])/'TestEditorAssets'
        for name,kind,count,tail in [('TestActorBP','Blueprint',10,4),('TestMaterial','Material',7,8),('TestSoundClass','SoundClass',0,4)]:
            m,raw,table=read_package(root/(name+'.uasset'))
            e=next(e for e in table.exports if e.kind==kind and not e.outer)
            r=Reader(raw[e.offset:e.offset+e.size]); records=read_records(r,table.names)
            self.assertEqual(len(records),count);self.assertEqual(e.size-r.pos,tail)
            if kind=='Blueprint':
                parent=next(p for p in records if p.name=='ParentClass')
                self.assertEqual(table.reference(struct.unpack('<i',parent.data)[0]).name,'Actor')
            if kind=='Material':
                color=next(p for p in records if p.name=='BaseColor')
                self.assertEqual(color.parameters,('ColorMaterialInput',))

    def test_animation_boundary_controlled(self):
        # Typed object-table routing is isolated; this is not an original animation fixture.
        from animation_native import read_animation
        from package_records import ImportRecord, ExportRecord, PackageRecords
        names=('None','NumFrames','SequenceLength','Skeleton','AnimationTrackNames','IntProperty','FloatProperty','ObjectProperty','ArrayProperty','NameProperty','Root')
        def prop(name,kind,data,extra=b''):
            return struct.pack('<6i',names.index(name),0,names.index(kind),0,len(data),0)+extra+b'\0'+data
        payload=prop('NumFrames','IntProperty',struct.pack('<i',2))+prop('SequenceLength','FloatProperty',struct.pack('<f',.5))+prop('Skeleton','ObjectProperty',struct.pack('<i',-1))+prop('AnimationTrackNames','ArrayProperty',struct.pack('<3i',1,10,0),struct.pack('<2i',9,0))+bytes(8)
        # object GUID marker, raw strip flags, one track and three constant channels, zero source tracks, no compressed data
        payload+=bytes(6)+struct.pack('<i',1)+struct.pack('<2i3f',12,1,0,0,0)+struct.pack('<2i4f',16,1,0,0,0,1)+struct.pack('<2i3f',12,1,1,1,1)+bytes(8)
        meta=dict(status='tables_inspected',legacy=-7,ue4=522,ue5=None,sidecars=[],flags=0,size=len(payload))
        table=PackageRecords(names,(ImportRecord('/Script/Engine','Skeleton',-2,'SK', 'None',False),ImportRecord('/Script/CoreUObject','Package',0,'/Game/SK','None',False)),(ExportRecord('Animation',0,0,0,0,0,len(payload),None,None,False,'AnimSequence'),))
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'Animation.uasset';p.write_bytes(payload)
            with patch('package_inspector.inspect_package',return_value=meta),patch('package_records.read_package',return_value=(meta,payload,table)):
                result=read_animation(p)
        self.assertEqual(result['skeleton_package'],'/Game/SK');self.assertEqual(result['frames'],2);self.assertEqual(result['tracks']['Root'][2],[(1.,1.,1.)])
