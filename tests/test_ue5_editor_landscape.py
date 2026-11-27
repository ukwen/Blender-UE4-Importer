import os,unittest
from pathlib import Path
import numpy as np
from ue5_editor_landscape import collapse_heightmap,weld_tiles,records

class LandscapeTests(unittest.TestCase):
    def test_subsections_and_seams(self):
        # Two subsections of two vertices each: shared edge encoded twice.
        h=np.array([[0,1,1,2],[3,4,4,5],[3,4,4,5],[6,7,7,8]],dtype=np.int32)+32768
        a=np.zeros((4,4,4),dtype=np.uint8);a[:,:,2]=h>>8;a[:,:,1]=h&255
        tile=collapse_heightmap(a,1,2);np.testing.assert_array_equal(tile,np.arange(9).reshape(3,3))
        grid,origin,seams=weld_tiles({(0,0):tile,(2,0):tile+2},2);self.assertEqual((origin,seams,grid.shape),((0,0),1,(3,5)))
        with self.assertRaisesRegex(ValueError,'seam'):weld_tiles({(0,0):tile,(2,0):tile+3},2)
        with self.assertRaisesRegex(ValueError,'Sparse'):weld_tiles({(0,0):tile,(4,0):tile},2)
        a[0,2,1]+=1
        with self.assertRaisesRegex(ValueError,'seam'):collapse_heightmap(a,1,2)

    @unittest.skipUnless(os.environ.get('UE56_EDITOR_PROJECT') and os.environ.get('UE_EDITOR_PAYLOAD_DECODER'),'Original project and decoder required')
    def test_original_terrain(self):
        content=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content';r,s=records(content,content/'MyStuff/Maps/MainLevel.umap');self.assertFalse(s);self.assertEqual(len(r),1);d,g=r[0];self.assertEqual((len(d['components']),d['seams'],g.shape),(64,112,(1009,1009)));self.assertEqual((int(g.min()),int(g.max())),(-10812,10863));self.assertEqual(d['height_sha256'],'20b5548d01d7503413e1b55fe7a96c344a13d31fe074c3a735f908fa1176ab6e')
