"""Bounded classic inputs and real Western particle graph records."""
import os
import struct
import unittest
from pathlib import Path
from skeleton_native import Reader
from classic_particle_material import read_edge, read_graph


class EdgeTests(unittest.TestCase):
    def test_input_identity_and_validation(self):
        raw=struct.pack('<8i',3,4,0,1,0,0,0,1)
        self.assertEqual(read_edge(Reader(raw)),dict(index=3,output=4,mask=[1,0,0,0,1],input_name=''))
        for data in (raw[:-1],struct.pack('<8i',3,5,0,1,0,0,0,1),struct.pack('<8i',-3,4,0,1,0,0,0,1),struct.pack('<8i',3,4,0,2,0,0,0,1),struct.pack('<3i',3,4,5000)):
            with self.subTest(data=data),self.assertRaises(ValueError):read_edge(Reader(data))


@unittest.skipUnless(os.environ.get('UE_WESTERN_PROJECT'),'Original Western fixture required')
class OriginalParticleGraphs(unittest.TestCase):
    def test_original_smoke_and_dust(self):
        root=Path(os.environ['UE_WESTERN_PROJECT'])
        smoke=read_graph(next(root.rglob('Mat_FX.uasset')))
        dust=read_graph(next(root.rglob('Mat_Dust_FX.uasset')))
        self.assertEqual(smoke['blend'],'BLEND_Translucent')
        self.assertEqual(smoke['shading_model'],'MSM_Unlit')
        self.assertEqual(smoke['outputs']['Opacity']['output'],4)
        self.assertEqual(dust['shading_model'],'MSM_DefaultLit')
        self.assertEqual(dust['nodes'][3]['inputs']['A']['index'],5)
        self.assertEqual(dust['nodes'][3]['inputs']['B']['index'],4)
        self.assertEqual(dust['nodes'][5]['texture'],'/Game/PolygonWesternFrontier/Textures/CircleSoft')
        self.assertEqual(len(smoke['nodes'])+len(dust['nodes']),5)
