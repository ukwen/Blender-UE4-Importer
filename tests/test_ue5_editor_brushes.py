import os,struct,unittest
from pathlib import Path
from ue5_editor_brushes import decode_polys,mesh_arrays,records
from ue5_full_scene import coverage


def sample(vertices=((0.,0.,0.),(1.,0.,0.),(0.,1.,0.))):
    # Controlled FPolys payload with an intentionally off-plane texture base.
    return struct.pack('<ii12fi',0,1,0.,0.,5.,0.,0.,1.,1.,0.,0.,0.,1.,0.,len(vertices))+b''.join(struct.pack('<3f',*v) for v in vertices)+bytes(76)


class BrushTests(unittest.TestCase):
    def test_exact_vertices_and_winding(self):
        p=decode_polys(sample());self.assertEqual(p[0]['base_plane_offset'],-5.)
        v,f=mesh_arrays(p);self.assertEqual(v,[(0.,0.,0.),(0.,.01,0.),(.01,0.,0.)]);self.assertEqual(f,[(2,1,0)])
    def test_refuse_trailer_truncation_nonplanar_and_degenerate(self):
        for data in (sample()+b'\0',sample()[:-1],sample(((0.,0.,0.),(1.,0.,0.),(0.,1.,1.))),sample(((0.,0.,0.),(1.,0.,0.),(1.,0.,0.)))):
            with self.subTest(data=data[-10:]),self.assertRaises(ValueError):decode_polys(data)
    def test_operand_not_geometry(self):
        class O(dict):type='MESH'
        self.assertEqual(coverage([dict(source='a',actor='b',kind='Brush')],[O(UE_source_actor_package='a',UE_actor='b',UE_brush_operand=True)])['representation_counts'],{'brush_operand_guide':1})
    @unittest.skipUnless(os.environ.get('UE56_EDITOR_PROJECT'),'Original project unavailable')
    def test_original_brushes(self):
        c=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content'
        for name,n,faces in [('MainLevel',45,271),('TestLevel',8,48)]:
            r=records(c,c/'MyStuff/Maps'/f'{name}.umap');self.assertEqual(len(r['records']),n);self.assertEqual(r['skipped'],[]);self.assertEqual(sum(len(x['polygons']) for x in r['records']),faces)
