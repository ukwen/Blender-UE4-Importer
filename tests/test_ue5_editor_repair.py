import os,unittest
from pathlib import Path
from ue5_editor_repair import source_identity,record_index

@unittest.skipUnless(os.environ.get('UE56_EDITOR_PROJECT'),'Original fixture required')
class RepairTests(unittest.TestCase):
    def test_exact_source_identity(self):
        c=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content';path=next(c.rglob('SM_Door.uasset'));package='/Game/'+path.relative_to(c).with_suffix('').as_posix();source_identity(path,package)
        for wrong in (package+'_wrong','/Game/Other/SM_Door'):
            with self.assertRaises(ValueError):source_identity(path,wrong)
    def test_original_actor_index(self):
        c=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content';level,index=record_index(c,c/'Variant_Combat/Lvl_Combat.umap',True)
        self.assertEqual(level,'/Game/Variant_Combat/Lvl_Combat');self.assertEqual(len(index),131);self.assertEqual(sum(bool(k[2]) for k in index),64)
