import os,struct,unittest,math
from pathlib import Path
from ue5_editor_animation import read_channel,quaternion_xyz
from animation_native import read_animation

class ChannelTests(unittest.TestCase):
    def channel(self,times,values,default=1.):
        return struct.pack('<BBii',4,4,4,len(times))+struct.pack('<'+'i'*len(times),*times)+struct.pack('<ii',28,len(values))+b''.join(struct.pack('<f',v)+b'\0'*24 for v in values)+struct.pack('<f4i',default,int(not times),30,1,0)
    def test_dense_and_constant(self):
        self.assertEqual(read_channel(self.channel([0,1],[1.,2.]),2),[1.,2.]);self.assertEqual(read_channel(self.channel([],[],3.),3),[3.]*3)
    def test_invalid_channels(self):
        for data in (self.channel([0,2],[1.,2.]),self.channel([0],[1.]),self.channel([0,1],[1.,math.nan]),self.channel([0,1],[1.,2.])[:-1]):
            with self.assertRaises(ValueError):read_channel(data,2)
    def test_rotator_convention(self):
        for angles,expected in [((90,0,0),(-1,0,0,1)),((0,90,0),(0,-1,0,1)),((0,0,90),(0,0,1,1))]:
            self.assertTrue(all(abs(x-y/math.sqrt(2))<1e-12 for x,y in zip(quaternion_xyz(*angles),expected)))

@unittest.skipUnless(os.environ.get('UE56_EDITOR_PROJECT'),'Original editor fixture required')
class GenuineAnimationTests(unittest.TestCase):
    def test_original_sequences(self):
        root=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content'
        for name,n,root_motion in [('MM_Idle',228,False),('MM_Rifle_Equip',51,False),('MF_Rifle_Walk_Fwd_Left',47,True)]:
            d=read_animation(next(root.rglob(name+'.uasset')));self.assertEqual(d['frames'],n);self.assertEqual(len(d['tracks']),89);self.assertEqual(d['source_root_motion'],root_motion);self.assertTrue(d['skeleton_package'].endswith('/SK_Mannequin'));self.assertEqual(d['duration'],(n-1)/30)
        with self.assertRaises(ValueError):read_animation(next(root.rglob('MM_Rifle_Jump_Start.uasset')))
