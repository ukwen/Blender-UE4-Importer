import os,struct,unittest,math
from pathlib import Path
from ue5_editor_animation import read_channel,quaternion_xyz,read_scalar_channel
from animation_native import read_animation

class ChannelTests(unittest.TestCase):
    def channel(self,times,values,default=1.):
        return struct.pack('<BBii',4,4,4,len(times))+struct.pack('<'+'i'*len(times),*times)+struct.pack('<ii',28,len(values))+b''.join(struct.pack('<f',v)+b'\0'*24 for v in values)+struct.pack('<f4i',default,int(not times),30,1,0)
    def test_dense_and_constant(self):
        self.assertEqual(read_channel(self.channel([0,1],[1.,2.]),2),[1.,2.]);self.assertEqual(read_channel(self.channel([],[],3.),3),[3.]*3)
    def test_invalid_channels(self):
        for data in (self.channel([0,2],[1.,2.]),self.channel([0],[1.]),self.channel([0,1],[1.,math.nan]),self.channel([0,1],[1.,2.])[:-1]):
            with self.assertRaises(ValueError):read_channel(data,2)
    def test_scalar_sparse_and_invalid(self):
        raw=self.channel([0,3],[0.,1.]);d=read_scalar_channel(raw,4)
        self.assertEqual([(k['frame'],k['value']) for k in d['keys']],[(0,0.),(3,1.)])
        for bad in (self.channel([3,0],[0.,1.]),self.channel([0,4],[0.,1.]),self.channel([0,0],[0.,1.]),self.channel([0,3],[0.,math.nan]),raw[:-1]):
            with self.assertRaises(ValueError):read_scalar_channel(bad,4)
        weighted=bytearray(raw);weighted[18+8+20]=1
        with self.assertRaises(ValueError):read_scalar_channel(weighted,4)
    def test_rotator_convention(self):
        for angles,expected in [((90,0,0),(-1,0,0,1)),((0,90,0),(0,-1,0,1)),((0,0,90),(0,0,1,1))]:
            self.assertTrue(all(abs(x-y/math.sqrt(2))<1e-12 for x,y in zip(quaternion_xyz(*angles),expected)))

@unittest.skipUnless(os.environ.get('UE56_EDITOR_PROJECT'),'Original editor fixture required')
class GenuineAnimationTests(unittest.TestCase):
    def test_original_sequences(self):
        root=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content'
        for name,n,root_motion in [('MM_Idle',228,False),('MM_Rifle_Equip',51,False),('MF_Rifle_Walk_Fwd_Left',47,True)]:
            d=read_animation(next(root.rglob(name+'.uasset')));self.assertEqual(d['frames'],n);self.assertEqual(len(d['tracks']),89);self.assertEqual(d['source_root_motion'],root_motion);self.assertTrue(d['skeleton_package'].endswith('/SK_Mannequin'));self.assertEqual(d['duration'],(n-1)/30)
        reload=read_animation(next(root.rglob('MM_Rifle_Reload.uasset')));self.assertEqual([k['frame'] for k in reload['scalar_curves']['DisableLHandIK']['keys']],[10,14,20,23])
        land=read_animation(next(root.rglob('MM_Rifle_Jump_Fall_Land.uasset')));self.assertEqual(len(land['scalar_curves']['GroundDistance']['keys']),13)
        loop=read_animation(next(root.rglob('MM_Rifle_Jump_Fall_Loop.uasset')));self.assertEqual(loop['source_rate_scale'],2.)
        for name,count in [('MM_Jump',159),('MM_Attack_01',161)]:self.assertEqual(len(read_animation(next(root.rglob(name+'.uasset')))['tracks']),count)
        self.assertTrue(read_animation(next(root.rglob('MM_Rifle_Fire.uasset')))['source_preview_required'])
    def test_audit(self):
        root=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content/Characters/Mannequins/Anims';accepted=[]
        for p in root.rglob('*.uasset'):
            try:accepted.append(read_animation(p))
            except ValueError:pass
        self.assertEqual((len(accepted),sum(a['frames'] for a in accepted),sum(a['source_preview_required'] for a in accepted)),(97,4589,52))

    def test_full_skeleton_and_preview_metadata(self):
        from ue5_editor_skeleton import read_skeleton
        root=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content/Characters/Mannequins';d=read_skeleton(root/'Meshes/SK_Mannequin.uasset')
        self.assertEqual((len(d['bones']),len(d['sockets']),len(d['retarget_sources'])),(161,5,2));self.assertEqual(set(d['retarget_sources']),{'SKM_Manny','SKM_Quinn'})
        a=read_animation(next(root.rglob('MF_Unarmed_Walk_Fwd.uasset')));self.assertEqual(len(a['source_retarget']['pose']),161);self.assertEqual(a['source_retarget']['asset'],d['retarget_sources']['SKM_Quinn']['asset'])
        self.assertEqual(len({x.casefold() for x in a['tracks']} & {b['name'].casefold() for b in d['bones']}),159)
        b=read_animation(next(root.rglob('MM_Rifle_Fire.uasset')));self.assertEqual(b['source_additive']['mode'],'AAT_RotationOffsetMeshSpace');self.assertTrue(b['source_additive']['sequence']['self_reference'])
        c=read_animation(next(root.rglob('MF_Pistol_Idle_ADS_AO_CD.uasset')));self.assertFalse(c['source_retarget']['reference_pose_present']);self.assertTrue(c['source_preview_required'])
