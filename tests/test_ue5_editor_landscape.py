import os,unittest
from pathlib import Path
import numpy as np
from ue5_editor_landscape import collapse_heightmap,weld_tiles,records,source_atlas,source_corner_uv,mesh_coordinates,mesh_corner_indices

class LandscapeTests(unittest.TestCase):
    def test_optimized_buffers_match_reference(self):
        rng=np.random.default_rng(100)
        for h,w in [(3,5),(9,7),(127,253)]:
            g=rng.integers(-32768,32768,size=(h,w),dtype=np.int32)
            for x,y in [(0,0),(-126,252),(123,-789)]:
                yy,xx=np.indices((h,w),dtype=np.float32)
                expected=np.stack(((yy+y)*.01,(xx+x)*.01,g.astype(np.float32)/128*.01),axis=-1).ravel()
                np.testing.assert_array_equal(mesh_coordinates(g,(x,y)),expected)
                ids=np.arange(h*w,dtype=np.int32).reshape(h,w);a=ids[:-1,:-1].ravel()
                np.testing.assert_array_equal(mesh_corner_indices(g.shape),np.stack((a,a+w,a+w+1,a+1),axis=1).ravel())
        for q,s,n,cols,rows in [(63,63,1,3,2),(126,63,2,2,3),(2,1,2,2,1)]:
            h,w=rows*q+1,cols*q+1;side=(s+1)*n;meta=dict(component_quads=q,subsection_quads=s,subsections=n,width=cols*side,height=rows*side)
            yy,xx=np.indices((h-1,w-1),dtype=np.int32);tx,ty=xx//q,yy//q;lx,ly=xx%q,yy%q
            u=(tx*side+lx+lx//s).ravel();v=(ty*side+ly+ly//s).ravel();expected=np.empty((len(u),4,2),dtype=np.float32)
            for k,(dx,dy) in enumerate(((0,0),(0,1),(1,1),(1,0))):
                expected[:,k,0]=(u+dx+.5)/meta['width'];expected[:,k,1]=1-(v+dy+.5)/meta['height']
            uv,comp=source_corner_uv(meta,(h,w));np.testing.assert_array_equal(uv,expected.reshape(-1,2));np.testing.assert_array_equal(comp,(ty*cols+tx).ravel())

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

    def test_source_atlas_duplicate_edges(self):
        a=np.arange(4*4*4,dtype=np.uint8).reshape(4,4,4)
        b=a+80
        atlas,meta=source_atlas({(0,0):a,(2,0):b},2,1,2)
        np.testing.assert_array_equal(atlas[:,:4],a[:,:,[2,1,0,3]])
        np.testing.assert_array_equal(atlas[:,4:],b[:,:,[2,1,0,3]])
        uv,comp=source_corner_uv(meta,(3,5));texel=uv.reshape(-1,4,2)*[8,-4]+[-.5,3.5]
        np.testing.assert_array_equal(texel[0],[[0,0],[0,1],[1,1],[1,0]])
        np.testing.assert_array_equal(texel[1],[[2,0],[2,1],[3,1],[3,0]])
        np.testing.assert_array_equal(texel[2],[[4,0],[4,1],[5,1],[5,0]])
        np.testing.assert_array_equal(comp,[0,0,1,1,0,0,1,1])
        with self.assertRaisesRegex(ValueError,'grid'):source_atlas({(0,0):a,(4,0):b},2,1,2)
        with self.assertRaisesRegex(ValueError,'tile'):source_atlas({(0,0):a.astype(float)},2,1,2)

    @unittest.skipUnless(os.environ.get('UE56_EDITOR_PROJECT') and os.environ.get('UE_EDITOR_PAYLOAD_DECODER'),'Original project and decoder required')
    def test_original_terrain(self):
        content=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content';r,s=records(content,content/'MyStuff/Maps/MainLevel.umap');self.assertFalse(s);self.assertEqual(len(r),1);d,g=r[0];self.assertEqual((len(d['components']),d['seams'],g.shape),(64,112,(1009,1009)));self.assertEqual((int(g.min()),int(g.max())),(-10812,10863));self.assertEqual(d['height_sha256'],'20b5548d01d7503413e1b55fe7a96c344a13d31fe074c3a735f908fa1176ab6e');self.assertEqual(d['source_atlas']['rgba_sha256'],'f4cd488a03bbf31c9011da6045930ed0bf1d28d9449af69830719931e5ebf839');self.assertEqual(d['weight_layers_status'],'not_serialized_in_supported_profile');self.assertTrue(all(len(c['material_bindings']['instances'][0]['chain'])==2 and c['material_bindings']['lod_indices']==[0]*6 for c in d['components']));self.assertTrue(all(c['material_bindings']['instances'][0]['chain'][0]['texture_parameters'][0]['name']=='Heightmap' and c['material_bindings']['instances'][0]['chain'][0]['texture_parameters'][0]['value']['name']==c['texture'] for c in d['components']))
