import math,os,struct,unittest
from pathlib import Path
from ue5_editor_camera import records,merged_fields

class CameraFieldTests(unittest.TestCase):
    def test_instance_overrides_and_fov(self):
        def f(v):return dict(type=['FloatProperty'],flags=0,data=struct.pack('<f',v))
        default={'TargetArmLength':f(250.),'FieldOfView':f(80.)};_,props=merged_fields({'TargetArmLength':f(300.)},default)
        self.assertEqual(props,{'TargetArmLength':300.,'FieldOfView':80.})
        for invalid in (0.,float('nan'),180.):
            with self.assertRaises(ValueError):merged_fields({'FieldOfView':f(invalid)},default)
        with self.assertRaises(ValueError):merged_fields({'RelativeScale3D':dict(type=['StructProperty','Vector','/Script/CoreUObject'],flags=8,data=struct.pack('<3d',1,2,1))},default)

@unittest.skipUnless(os.environ.get('UE56_EDITOR_PROJECT'),'Original editor fixture required')
class CameraFixtureTests(unittest.TestCase):
    def test_saved_cameras(self):
        content=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content'
        for stem,n in [('MainLevel',6),('TestLevel',1)]:
            d=records(content,content/f'MyStuff/Maps/{stem}.umap');self.assertEqual(len(d['records']),n);self.assertFalse(d['skipped'])
            for r in d['records']:
                self.assertEqual(r['blueprint'],'/Game/MyStuff/Blueprints/BP_EnemyCharacter');self.assertEqual(r['components'][1]['properties'],{'TargetArmLength':250.,'SocketOffset':(0.,20.,0.)});self.assertEqual(r['fov_source'],'preview_default_not_serialized');self.assertEqual(r['components'][1]['fields']['RelativeLocation'][1],60.)
