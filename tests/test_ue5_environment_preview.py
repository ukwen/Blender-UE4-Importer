import math,os,unittest
from pathlib import Path
from ue5_environment_preview import plan
from ue5_editor_lighting import records

class EnvironmentPlanTests(unittest.TestCase):
    def fixture(self):
        return [dict(kind='SkyLight',actor='sky',properties={'bRealTimeCapture':True}),dict(kind='SkyAtmosphere',actor='air',properties={}),dict(kind='DirectionalLight',actor='sun',properties={},fields={'RelativeRotation':(-30,90,0)})]
    def test_sun_orientation(self):
        r=plan(self.fixture());self.assertEqual(r['status'],'planned');self.assertAlmostEqual(r['sun_elevation'],math.pi/6);self.assertAlmostEqual(r['sun_rotation'],math.pi);self.assertAlmostEqual(r['strength'],1.)
    def test_ambiguous_and_explicit_cubemap_refused(self):
        f=self.fixture();self.assertEqual(plan(f+f[:1])['status'],'unsupported');f[0]['untranslated_component_fields']=['Cubemap'];self.assertEqual(plan(f)['status'],'unsupported')
    def test_disabled_sun_and_capture(self):
        f=self.fixture();f[2]['properties']['bAffectsWorld']=False;self.assertEqual(plan(f)['status'],'unsupported');f=self.fixture();f[0]['properties']['bRealTimeCapture']=False;self.assertEqual(plan(f)['status'],'unsupported')
    @unittest.skipUnless(os.environ.get('UE56_EDITOR_PROJECT'),'Original fixture required')
    def test_original_plans(self):
        c=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content';plans=[]
        for p in c.rglob('*.umap'):
            try:plans.append(plan(records(c,p)['records']))
            except ValueError:continue
        self.assertEqual(len(plans),6);self.assertEqual(sum(r['status']=='planned' for r in plans),5);self.assertEqual(sum('FogDensity' in x['properties'] for r in plans for x in r['fog_records']),4)
