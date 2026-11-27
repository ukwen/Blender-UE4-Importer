import os, unittest
from pathlib import Path
from ue5_editor_material import resolve_material

@unittest.skipUnless(os.environ.get('UE56_EDITOR_PROJECT'),'Original editor fixture required')
class ProceduralFixtureTests(unittest.TestCase):
    def resolve(self,stem):
        root=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content';p=next(root.rglob(stem+'.uasset'));return resolve_material(root,'/Game/'+p.relative_to(root).with_suffix('').as_posix())
    def test_radial_ramp(self):
        d=self.resolve('M_radial_ramp_soft');n={v['kind']:v for v in d['nodes'].values()};self.assertEqual(n['Constant2Vector']['value'],[.5,.5]);self.assertEqual(n['Power']['exponent'],5.);self.assertEqual(n['SphereMask']['hardness_percent'],0.);self.assertAlmostEqual(n['Constant']['value'],.6);self.assertEqual(d['blend'],'BLEND_Translucent')
    def test_panner_and_offset(self):
        d=self.resolve('M_WP_Linkgun_Connection');n=[v for v in d['nodes'].values() if v['kind']=='Panner'];self.assertEqual(len(n),3);self.assertEqual(n[1]['speed'],[-3.,0.]);self.assertFalse(any(v['fractional'] for v in n));m=self.resolve('M_Mannequin');offsets=[v['world_offset'] for v in m['nodes'].values() if v['kind']=='WorldPosition'];self.assertEqual(offsets.count('default_not_serialized'),1);self.assertEqual(len(offsets),2)
