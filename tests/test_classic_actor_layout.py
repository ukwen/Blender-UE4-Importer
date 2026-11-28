"""Classic actor records: genuine map evidence and controlled invalid inputs."""
import os
from dataclasses import replace
from pathlib import Path
import struct
import unittest
from classic_actor_layout import inspect_layout, parent_links, Placement, object_index, triple, string_value
from ue4_property_records import PropertyRecord


class ActorRecordTests(unittest.TestCase):
    def test_invalid_payload(self):
        p = PropertyRecord('Ref','ObjectProperty',0,(),b'\x00')
        with self.assertRaises(ValueError): object_index({'Ref':p},'Ref')
        p = PropertyRecord('Vector','StructProperty',0,('Vector',),struct.pack('<3f',float('nan'),0,0))
        with self.assertRaises(ValueError): triple({'Vector':p},'Vector','Vector',(0,0,0))
        p = PropertyRecord('Label','StrProperty',0,(),struct.pack('<i',4)+b'abcd')
        with self.assertRaises(ValueError): string_value({'Label':p},'Label','')

    def test_parent_graph(self):
        a = Placement('a','a',1,0,'','/Game/A',(0,0,0),(0,0,0),(1,1,1),(),())
        b = replace(a, actor='b',root_index=2,parent_index=1)
        self.assertEqual(parent_links([b,a]),({2:1},set()))
        self.assertEqual(parent_links([replace(a,parent_index=2),b]),({}, {1,2}))
        self.assertEqual(parent_links([replace(a,parent_index=99)]),({}, {1}))
        with self.assertRaises(ValueError): parent_links([a,a])

    @unittest.skipUnless(os.environ.get('UE_WESTERN_PROJECT'),'Original Western Frontier required')
    def test_original_map_records(self):
        counts={}
        for path in Path(os.environ['UE_WESTERN_PROJECT']).rglob('*.umap'):
            actors,skipped=inspect_layout(path)
            links,unresolved=parent_links(actors)
            self.assertFalse(skipped);self.assertFalse(unresolved)
            self.assertEqual(len(links),sum(bool(a.parent_index) for a in actors))
            self.assertEqual(len(set(a.root_index for a in actors)),len(actors))
            self.assertTrue(all(a.package.startswith(('/Game/','/Engine/')) for a in actors))
            counts[path.stem]=len(actors)
        self.assertEqual(counts,{'Demonstration':1995,'Overview':323})

    @unittest.skipUnless(os.environ.get('UE_WESTERN_PROJECT'),'Original Western Frontier required')
    def test_original_foliage_records(self):
        from classic_foliage import inspect_foliage
        counts={}
        for path in Path(os.environ['UE_WESTERN_PROJECT']).rglob('*.umap'):
            records,errors=inspect_foliage(path)
            self.assertFalse(errors)
            self.assertTrue(all(len(row)==20 for record in records for row in record.rows))
            counts[path.stem]=sorted(len(record.rows) for record in records)
        self.assertEqual(counts,{'Demonstration':[223,239],'Overview':[]})
