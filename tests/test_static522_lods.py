"""Original payload plus controlled source-model header sequence (not a genuine multi-LOD package)."""
import os,struct,unittest
from pathlib import Path
from editor_static522 import read_static_lods,read_source_models,UnsupportedProfile
from package_inspector import inspect_package
from package_records import read_package,root_export
from ue4_property_records import read_records
from skeleton_native import Reader


def controlled(path):
    meta,raw,table=read_package(path);e=root_export(table,'StaticMesh')
    r=Reader(raw[e.offset:e.offset+e.size]);read_records(r,table.names)
    at=r.pos+46  # recorded original Rope: no GUID, empty high-resolution name and sockets
    block=r.data[at:at+44]
    assert len(block)==44 and struct.unpack_from('<2I',block)==(1,0x203)
    summary=inspect_package(path,include_bulk_522=True)
    return block,raw,summary['bulk_data_offset'],max(e.offset+e.size for e in table.exports)


@unittest.skipUnless(os.environ.get('UE_STATIC522_FIXTURES'),'Original UE4.27 Rope fixture required')
class SourceModels(unittest.TestCase):
    def test_original_and_controlled_missing_lod(self):
        path=Path(os.environ['UE_STATIC522_FIXTURES'])/'SM_Prop_Rope_01.uasset'
        original,=read_static_lods(path)
        self.assertEqual((original['lod_index'],original['lod_count'],original['missing_lods']),(0,1,[]))
        block,raw,base,end=controlled(path)
        r=Reader(block+bytes(4)+block+b'next')
        models,missing=read_source_models(r,raw,base,end,3)
        self.assertEqual([i for i,g in models],[0,2]);self.assertEqual(missing,[1]);self.assertEqual(r.take(4),b'next')
        self.assertTrue(all(g==original['geometry'] for i,g in models))
        models,missing=read_source_models(Reader(bytes(4)+block),raw,base,end,2)
        self.assertEqual([i for i,g in models],[1]);self.assertEqual(missing,[0])
        overlap=bytearray(block);offset=struct.unpack_from('<q',overlap,16)[0];struct.pack_into('<q',overlap,16,offset+1);struct.pack_into('<I',overlap,12,struct.unpack_from('<I',block,12)[0]-1)
        with self.assertRaisesRegex(ValueError,'Overlapping source bulk'):
            read_source_models(Reader(block+overlap),raw,base,end,2)
        for bad,count in ((block,0),(block,65),(bytes(12),3),(block[:-1],1),(b'\x02\0\0\0',1)):
            with self.subTest(count=count),self.assertRaises((ValueError,UnsupportedProfile)):
                read_source_models(Reader(bad),raw,base,end,count)
