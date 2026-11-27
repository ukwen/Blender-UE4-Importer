import io, os, sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ue5_legacy_editor import read_texture,read_material,tags
from skeleton_native import Reader
from project_preflight import read_record
from ue5_editor_material import resolve_material

@unittest.skipUnless(os.environ.get('UE56_EDITOR_PROJECT'),'Original ShooterSam fixture required')
class LegacyEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.root=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content'
    def fixture(self,name):return next(self.root.rglob(name+'.uasset'))
    def test_legacy_materials(self):
        for stem,n in [('MI_PrototypeGrid_Gray_02',6),('MI_PrototypeGrid_TopDark',7)]:
            p=self.fixture(stem);m=read_material(p);self.assertEqual(len(m['parameters']),n);self.assertEqual(m['parent'],'/Game/LevelPrototyping/Materials/M_PrototypeGrid');self.assertEqual(read_record(p,None)['coverage'],'import_table');self.assertEqual(read_record(p,None)['soft_coverage'],'unknown')
            d=resolve_material(self.root,'/Game/'+p.relative_to(self.root).with_suffix('').as_posix());self.assertEqual(len(d['parameters']),n);self.assertEqual(len(d['chain']),2)
            self.assertFalse(any('GUID mismatch' in x for x in d['unsupported']));self.assertEqual(len(d['function_packages']),1)
            if stem.endswith('TopDark'):
                self.assertEqual([v['value'] for v in d['nodes'].values() if v['kind']=='StaticSwitchParameter' and v['parameter']=='TopSurfaceColor'],[True]*3)
                self.assertEqual([v['value'] for v in d['nodes'].values() if v['parameter']=='ObjectAligned'],[True]*4)
    @unittest.skipUnless(os.environ.get('UE_EDITOR_PAYLOAD_DECODER'),'Configured decoder required')
    def test_png(self):
        p=self.fixture('T_GridChecker_A');png,m=read_texture(p);self.assertEqual((m['width'],m['height']),(512,512));self.assertFalse(m['srgb']);self.assertEqual(m['png_sha256'],'4ef26b0ae2b662d43f3d9fbc4aec1e843601c543cf37ed0489c02d7ef1e16021');self.assertIn('Texture2D',read_record(p,None)['classes'])
        from PIL import Image
        with Image.open(io.BytesIO(png)) as im:im.load();self.assertEqual(im.size,(512,512))
    def test_truncated_tags(self):
        with self.assertRaises(ValueError):tags(Reader(b'\x00'),['None'])
