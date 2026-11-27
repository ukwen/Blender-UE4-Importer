import tempfile, unittest
from pathlib import Path
from ue5_scene_dependencies import audit,package_file

class Project:
    def __init__(self,root):self.dir=str(root);self.engine_dir=None
    def resolve_package(self,p):
        if p.startswith('/Engine/'):raise FileNotFoundError(p)
        if not p.startswith('/Game/') or '..' in p.split('/'):raise ValueError(p)
        return str(Path(self.dir)/'Content'/(p[6:]+'.uasset'))

class SceneDependencyTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name);self.p=Project(self.root);self.c=self.root/'Content';self.c.mkdir()
        self.map=self.make('Maps/L.umap')
    def make(self,p):
        f=self.c/p;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(b'fixture');return f
    def test_closure_external_objects_and_cycles(self):
        self.make('Mesh.uasset');self.make('Maps/B.umap');self.make('__ExternalActors__/Maps/L/a.uasset');self.make('__ExternalObjects__/Maps/L/o.uasset')
        refs={'L.umap':['/Game/Mesh','/Game/Maps/B'],'Mesh.uasset':['/Game/Maps/L'],'a.uasset':['/Engine/Floor'],'o.uasset':['/Game/Absent']}
        def read(p,project):return dict(coverage='import_table',soft_coverage='summary',references=refs.get(p.name,[]),soft_references=['/Plugin/Thing'] if p.name=='B.umap' else [])
        d=audit(self.p,self.map,reader=read)
        self.assertEqual(d['scanned_packages'],5);self.assertEqual(len(d['owned_packages']['/Game/Maps/L']),2);self.assertEqual(d['unresolved_hard'],2);self.assertEqual(d['unresolved_soft_only'],1);self.assertFalse(d['ready_for_strict_import']);self.assertEqual(d['dependencies']['/Game/Maps/B']['status'],'available')
    def test_clean_and_unknown_tables(self):
        def read(p,project):return dict(coverage='import_table',soft_coverage='summary',references=[],soft_references=[])
        self.assertTrue(audit(self.p,self.map,reader=read)['ready_for_strict_import'])
        def unknown(p,project):raise ValueError('bad tables')
        d=audit(self.p,self.map,reader=unknown);self.assertFalse(d['ready_for_strict_import']);self.assertEqual(d['unknown_tables'],['/Game/Maps/L'])
    def test_ambiguous_and_bounded(self):
        self.make('Maps/L.uasset')
        with self.assertRaises(ValueError):package_file(self.p,'/Game/Maps/L')
        self.make('Other.uasset')
        def read(p,project):return dict(coverage='import_table',soft_coverage='summary',references=['/Game/Other'],soft_references=[])
        with self.assertRaisesRegex(ValueError,'limit'):audit(self.p,self.map,limit=1,reader=read)
