import math,os,unittest
from pathlib import Path
from animation_native import authored_root_translation,read_animation

class RootTranslationTests(unittest.TestCase):
    def test_conversion(self):
        self.assertEqual(authored_root_translation([[(10,20,30),(110,-180,80)],[],[]],2),[(0,0,0),(-2,1,.5)])
        self.assertEqual(authored_root_translation([[(10,20,30)],[],[]],3),[(0,0,0)]*3)
    def test_invalid(self):
        for t in (None, [[],[],[]], [[(0,0,math.nan)],[],[]], [[(0,0)],[],[]], [[(0,0,0)]*3,[],[]]):
            with self.assertRaises(ValueError):authored_root_translation(t,2)
    @unittest.skipUnless(os.environ.get('UE56_EDITOR_PROJECT'),'Original editor fixture required')
    def test_original_inventory(self):
        root=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content/Characters/Mannequins/Anims'; enabled=[]
        for p in root.rglob('*.uasset'):
            try:d=read_animation(p)
            except ValueError:continue
            if d['source_root_motion']:
                track=next(t for name,t in d['tracks'].items() if name.casefold()=='root');trajectory=authored_root_translation(track,d['frames']);self.assertEqual(trajectory[0],(0,0,0));self.assertEqual(len(trajectory),d['frames']);enabled.append(d)
        self.assertEqual(len(enabled),62)
