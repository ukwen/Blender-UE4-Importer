"""Original UE4.27 material and function records, bounded override validation."""
import hashlib,json,os,unittest,tempfile,shutil
from pathlib import Path
from dataclasses import replace
from classic_material_graph import read_graph,array,edge
from classic_material import property_map
from classic_texture import read_source
from classic_wind_profile import extract_profile
from ue5_editor_material import resolve_material,apply_overrides
from package_records import read_package
ROOT=Path(__file__).resolve().parents[1]

class OverrideGuard(unittest.TestCase):
    def test_stale_classic_guid_requires_unique_ancestor(self):
        def node():return dict(kind='ScalarParameter',parameter='Wind',guid='01'*16,value=3.,name='wind')
        child=dict(kind='scalar',name='Wind',guid='02'*16,value=5.,source_package='/Game/Child')
        parent=dict(child,guid='01'*16,source_package='/Game/Parent',selected=False)
        overrides={('scalar','Wind'):child}
        for nodes,history,classic in [({1:node()},[],True),({1:node(),2:node()},[parent],True),({1:node()},[parent],False)]:
            issues=[];a=apply_overrides(nodes,overrides,issues,history,classic);self.assertEqual(a[0]['status'],'guid_mismatch');self.assertTrue(issues);self.assertTrue(all(n['value']==3. for n in nodes.values()))
        nodes={1:node()};issues=[];a=apply_overrides(nodes,overrides,issues,[parent],True);self.assertFalse(issues);self.assertEqual(nodes[1]['value'],5.);self.assertEqual(a[0]['guid'],child['guid']);self.assertEqual(a[0]['ancestor_guid_evidence']['guid'],parent['guid'])

@unittest.skipUnless(os.environ.get('UE_CLASSIC_MATERIAL_FIXTURES'),'Original Goblin material fixtures required')
class OriginalClassicGraph(unittest.TestCase):
    def setUp(self):
        self.originals=Path(os.environ['UE_CLASSIC_MATERIAL_FIXTURES']);self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.content=Path(self.temp.name)/'Content';self.manifest=json.loads((ROOT/'docs/CLASSIC_MATERIAL_FIXTURES.json').read_text())
        for name,row in self.manifest.items():
            source=self.originals/name;self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),row['sha256']);p=self.content/(row['package'][6:]+'.uasset');p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,p)
    def test_wind_and_instance_parity(self):
        reference=json.loads((ROOT/'docs/CLASSIC_WIND522_BASELINE.json').read_text());results={}
        for name,expected in reference.items():
            p=self.manifest[name+'.uasset']['package'];d=resolve_material(self.content,p);self.assertEqual(len(d['nodes']),34);self.assertFalse(d['unsupported']);self.assertEqual(extract_profile(d),expected);results[name]=d
        child=results['MI_PolygonGoblinWarCamp'];self.assertEqual(len(child['chain']),3);self.assertEqual(len(child['parameters']),13);self.assertEqual(sum('ancestor_guid_evidence' in a for a in child['parameter_audit']),3);self.assertEqual(child['function_packages'],[self.manifest['MF_VertexColorWind.uasset']['package']]);self.assertTrue(all(r['status']=='inactive_no_flag' for r in child['base_property_audit']))
    def test_original_texture_parity(self):
        expected=json.loads((ROOT/'docs/CLASSIC_TEXTURE522_BASELINE.json').read_text());result={}
        for name in expected:
            png,meta=read_source(self.originals/name);result[name]={'sha256':hashlib.sha256(png).hexdigest(),'metadata':meta}
        self.assertEqual(result,expected)
    def test_malformed_array_and_link(self):
        m,b,t=read_package(self.originals/'MI_PolygonGoblinWarCamp.uasset');p=property_map(b,t.exports[0],t.names)['ScalarParameterValues']
        for bad in (p.data[:-1],p.data+b'\0',b'\xff'*4+p.data[4:]):
            with self.assertRaises(ValueError):array(replace(p,data=bad),t.names,'ScalarParameterValue')
        with self.assertRaises(ValueError):edge(b'\xff'*36,t.names)
        with self.assertRaises(ValueError):edge(bytes(35),t.names)
        # A missing local function is reported rather than guessed.
        (self.content/(self.manifest['MF_VertexColorWind.uasset']['package'][6:]+'.uasset')).unlink();d=resolve_material(self.content,self.manifest['MI_PolygonGoblinWarCamp.uasset']['package']);self.assertTrue(any('Missing material function' in e for e in d['unsupported']))
