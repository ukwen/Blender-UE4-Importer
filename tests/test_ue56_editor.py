"""Genuine ShooterSam editor sources, guarded by explicit fixture environment."""
import os,unittest
from pathlib import Path
from ue5_editor_mesh import read_static,read_skeletal
from ue5_blueprint import read_tables
from ue5_editor_payload import read_trailer,extract_payload,compressed_header
from ue5_editor_scene import placement_records

@unittest.skipUnless(os.environ.get('UE56_EDITOR_PROJECT') and os.environ.get('UE_EDITOR_PAYLOAD_DECODER'),'Set UE56_EDITOR_PROJECT and UE_EDITOR_PAYLOAD_DECODER')
class TestEditor56(unittest.TestCase):
    def root(self):return Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content'
    def source(self,name):return next(self.root().rglob(name+'.uasset'))
    def test_source_door_and_corruption(self):
        p=self.source('SM_Door');d=read_static(p);self.assertGreater(len(d['triangles']),0)
        _,raw,_,exports,*_=read_tables(p);records=read_trailer(raw,max(x['offset']+x['size'] for x in exports));h=next(iter(records));rec=records[h];buf=raw[rec['offset']:rec['offset']+rec['stored']]
        b=bytearray(buf);b[4]^=1
        with self.assertRaises(ValueError):compressed_header(b)
        b=bytearray(raw);b[-12]^=1
        with self.assertRaises(ValueError):read_trailer(b)
        with self.assertRaises(ValueError):extract_payload(raw,records,h,rec['decoded']+1)
    def test_original_skeletal(self):
        for name,n,faces in [('SKM_Manny_Simple',46098,92178),('SKM_Quinn_Simple',43761,87280)]:
            d=read_skeletal(self.source(name));self.assertEqual((len(d['vertices']),len(d['triangles']),len(d['bones'])),(n,faces,89));self.assertTrue(all(sum(w.values())==65535 for w in d['weights'].values()))
    def test_external_actors(self):
        root=self.root(); totals=[0,0]
        for p in [root/'ThirdPerson/Lvl_ThirdPerson.umap',root/'Variant_Combat/Lvl_Combat.umap',root/'Variant_Platforming/Lvl_Platforming.umap',root/'Variant_SideScrolling/Lvl_SideScrolling.umap']:
            r=placement_records(root,p);totals[0]+=r['external_count'];totals[1]+=len(r['records'])
        self.assertEqual(totals,[465,348])
