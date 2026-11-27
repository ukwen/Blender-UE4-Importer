import unittest
from ue5_full_scene import coverage
class Obj(dict):
    def __init__(self,kind,**kw):super().__init__(kw);self.type=kind
class CoverageTests(unittest.TestCase):
    def test_distinguishes_missing_geometry_and_marker(self):
        rows=[dict(source='a',actor=x,kind='Actor') for x in 'abcd']
        def obj(kind,x,**kw):return Obj(kind,UE_source_actor_package='a',UE_actor=x,**kw)
        result=coverage(rows,[obj('MESH','a'),obj('CAMERA','a'),obj('EMPTY','b',UE_geometry_status='missing'),obj('EMPTY','c')]);self.assertEqual(result['serialized_level_exports'],4);self.assertEqual(result['representation_counts'],dict(geometry=1,camera_preview=1,unresolved_geometry=1,anchor_or_marker=1,not_reconstructed=1))
    def test_does_not_match_actor_names_across_packages(self):
        result=coverage([dict(source='a',actor='x',kind='Actor')],[Obj('MESH',UE_source_actor_package='b',UE_actor='x')]);self.assertEqual(result['representation_counts'],{'not_reconstructed':1})
    def test_decal_is_not_geometry(self):
        r=coverage([dict(source='a',actor='x',kind='DecalActor')],[Obj('EMPTY',UE_source_actor_package='a',UE_actor='x',UE_decal_projector=True)])
        self.assertEqual(r['representation_counts'],{'decal_projector_guide':1})
