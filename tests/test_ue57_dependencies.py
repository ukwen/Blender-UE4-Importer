"""Original UE5.7 tagged editor fixtures, no synthetic asset compatibility claims."""
import os,struct,tempfile,unittest
from pathlib import Path
from package_inspector import inspect_package
from ue5_dependencies import read_dependencies
from ue5_blueprint import inspect_blueprint
from project_preflight import read_record

@unittest.skipUnless(os.environ.get('UASSETAPI_ASSETS'),'Set UASSETAPI_ASSETS')
class UE57DependencyTests(unittest.TestCase):
    def sources(self):return sorted((Path(os.environ['UASSETAPI_ASSETS'])/'TestEditorUE5_7').rglob('*.uasset'))
    def test_original_packages(self):
        expected={'BP_FP_CameraManager':(0,7,11,3),'BP_FirstPersonCameraManager':(0,5,11,3),'BP_FirstPersonCharacter':(9,21,69,125),'BP_FirstPersonGameMode':(2,5,10,2),'BP_FirstPersonPlayerController':(4,9,33,70)}
        for p in self.sources():
            with self.subTest(p=p.name):
                m=inspect_package(p);d=read_dependencies(p);r=read_record(p,None)
                self.assertEqual((m['ue5'],m['fortnite_main_version']),(1018,225))
                self.assertEqual(d['subpath_encoding'],'utf8')
                self.assertEqual((len(d['hard_references']),len(d['soft_object_paths']),len(d['export_dependency_rows']),sum(map(len,d['export_dependency_rows']))),expected[p.stem])
                self.assertEqual(d['soft_references'],['/Game/FirstPerson/Blueprints/'+p.stem]);self.assertEqual(d['import_hierarchy_coverage'],'empty')
                self.assertEqual(r['soft_coverage'],'ue5_1018_summary_tables');self.assertEqual(r['coverage'],'import_table');self.assertEqual(r['references'],d['hard_references'])
                self.assertIn('BlueprintGeneratedClass',r['classes'])
                blueprint=inspect_blueprint(p);self.assertEqual(blueprint["version"],1018);self.assertEqual(blueprint["generated_class"],p.stem+"_C") # saved composition only
        self.assertEqual(len(self.sources()),5)
    def test_corrupt_subpaths_and_indices(self):
        p=next(p for p in self.sources() if p.stem=='BP_FirstPersonCharacter');m=inspect_package(p);raw=p.read_bytes();off=m['soft_object_offset']
        with tempfile.TemporaryDirectory() as t:
            f=Path(t)/p.name
            for loc,value in [(off,-1),(off+16,-1),(off+16,65537),(m['depends_offset'],100001),(m['depends_offset']+4,1000001)]:
                b=bytearray(raw);struct.pack_into('<i',b,loc,value);f.write_bytes(b);self.assertRaises(ValueError,read_dependencies,f)
            b=bytearray(raw);b[off+20]=255;f.write_bytes(b);self.assertRaises(UnicodeError,read_dependencies,f)
