import os,struct,unittest
from pathlib import Path
from ue5_editor_bsp import records,decode_model,decode_component
from ue5_editor_volumes import records as volumes,decode_volume_model
from ue5_blueprint import read_tables
from ue5_editor_brushes import native_tail
from ue5_full_scene import coverage


class BSPTests(unittest.TestCase):
    def test_bad_headers(self):
        for data in (b'',bytes(62),bytes(150),bytes(62)+struct.pack('<ii',13,1)+bytes(20)):
            with self.assertRaises(ValueError):decode_model(data)
        with self.assertRaises(ValueError):decode_component(bytes(16),1,1,{})
        with self.assertRaises(ValueError):decode_volume_model(bytes(1710))
    def test_volume_not_visible_geometry(self):
        class O(dict):type='MESH'
        self.assertEqual(coverage([dict(source='p',actor='v',kind='BlockingVolume')],[O(UE_source_actor_package='p',UE_actor='v',UE_volume_guide=True)])['representation_counts'],{'volume_guide':1})
    @unittest.skipUnless(os.environ.get('UE56_EDITOR_PROJECT'),'Original project unavailable')
    def test_original_compiled_models(self):
        c=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content'
        for name,count,faces,corners in [('MainLevel',17,917,4091),('TestLevel',9,76,304)]:
            p=c/'MyStuff/Maps'/f'{name}.umap';r,rep=records(c,p);self.assertEqual(rep['status'],'reconstructed');self.assertEqual(len(r),count);self.assertEqual(sum(len(x['faces']) for x in r),faces);self.assertEqual(sum(len(f['vertices']) for x in r for f in x['faces']),corners)
            _,raw,_,ex,ref,_=read_tables(p);mi=r[0]['model'];data=native_tail(raw,ref(mi));model=decode_model(data)
            for bad in (data[:-1],data+b'\0',data[:62]+struct.pack('<i',13)+data[66:]):
                with self.assertRaises(ValueError):decode_model(bad)
            ci=next(i for i,e in enumerate(ex,1) if e['name']==r[0]['actor'] and e['kind']=='ModelComponent');d=native_tail(raw,ref(ci))
            for bad in (d[:-1],d+b'\0',d[:8]+struct.pack('<i',mi+1)+d[12:]):
                with self.assertRaises(ValueError):decode_component(bad,mi,ci,model['faces'])
    @unittest.skipUnless(os.environ.get('UE56_EDITOR_PROJECT'),'Original project unavailable')
    def test_original_volumes(self):
        c=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content'
        for rel,count in [('MyStuff/Maps/MainLevel',3),('MyStuff/Maps/TestLevel',1),('ThirdPerson/Lvl_ThirdPerson',1),('Variant_Combat/Lvl_Combat',2),('Variant_Platforming/Lvl_Platforming',1),('Variant_SideScrolling/Lvl_SideScrolling',4)]:
            r,skips=volumes(c,c/(rel+'.umap'));self.assertEqual(skips,[]);self.assertEqual(len(r),count);self.assertTrue(all(len(x['polygons'])==6 for x in r))
