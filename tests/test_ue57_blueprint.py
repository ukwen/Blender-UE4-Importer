"""Original UE5.7 composition fixtures: no geometry or runtime claims."""
import os,struct,tempfile,unittest
from pathlib import Path
from ue5_blueprint import inspect_blueprint,read_tables
from ue5_editor_blueprint import inspect_class

@unittest.skipUnless(os.environ.get('UASSETAPI_ASSETS'),'Original UAssetAPI fixtures required')
class Blueprint57Tests(unittest.TestCase):
    def setUp(self):self.root=Path(os.environ['UASSETAPI_ASSETS'])/'TestEditorUE5_7'/'Blueprints'
    def test_character_topology(self):
        d=inspect_blueprint(self.root/'BP_FirstPersonCharacter.uasset');c={x['variable']:x for x in d['components']}
        self.assertEqual(len(c),6);self.assertEqual(d['parent_class'],'Character');self.assertEqual(d['parent_blueprint'],'/Script/Engine');self.assertEqual(d['root_index'],c['CapsuleComponent']['index']);self.assertEqual(c['CapsuleComponent']['aliases'],['CapsuleComponent','RootComponent'])
        self.assertEqual(c['Mesh']['parent_index'],d['root_index']);self.assertEqual(c['FirstPersonMesh']['parent_index'],c['Mesh']['index']);self.assertEqual(c['FirstPersonCamera']['parent_index'],c['FirstPersonMesh']['index']);self.assertEqual(c['FirstPersonCamera']['socket'],'head');self.assertEqual(c['FirstPersonCamera']['placement'],'unresolved_socket')
        self.assertEqual(c['FirstPersonCamera']['properties']['FirstPersonFieldOfView'],70.);self.assertAlmostEqual(c['FirstPersonCamera']['properties']['FirstPersonScale'],.6,places=6)
        self.assertTrue(c['Mesh']['properties']['bOwnerNoSee']);self.assertTrue(c['FirstPersonMesh']['properties']['bOnlyOwnerSee']);self.assertEqual(c['Mesh']['package'],c['FirstPersonMesh']['package']);self.assertTrue(c['Mesh']['package'].endswith('/SKM_Manny_Simple'));self.assertEqual(c['CharacterMovement']['placement'],'metadata_only_non_scene_component');self.assertEqual(d['inactive_scs_nodes'],['SCS_Node_0'])
    def test_camera_and_game_mode(self):
        for stem in ['BP_FP_CameraManager','BP_FirstPersonCameraManager']:
            d=inspect_class(self.root/(stem+'.uasset'));self.assertEqual(d['cdo_properties'],{'ViewPitchMin':-70.,'ViewPitchMax':80.});self.assertEqual(len(d['components']),1)
        d=inspect_class(self.root/'BP_FirstPersonGameMode.uasset');self.assertEqual(d['cdo_references']['DefaultPawnClass']['name'],'BP_FirstPersonCharacter_C');self.assertEqual(d['components'][0]['variable'],'DefaultSceneRoot');self.assertFalse(d['inactive_scs_nodes'])
    def test_invalid_scs_array_refuses(self):
        p=self.root/'BP_FirstPersonCharacter.uasset';m,raw,_,ex,_,_=read_tables(p);e=next(e for e in ex if e['kind']=='SimpleConstructionScript');start=e['offset']+e['script_start'];end=e['offset']+e['script_end'];buf=raw[start:end]
        # Original AllNodes array: count 2 and two known SCS node export indices.
        source=inspect_class(p);nodes=[i for i,x in enumerate(ex,1) if x['kind']=='SCS_Node' and x['name']!='SCS_Node_0'];self.assertEqual(len(nodes),2)
        needle=struct.pack('<3i',2,*reversed(nodes));self.assertEqual(buf.count(needle),1)
        at=start+buf.index(needle);copy=bytearray(raw);struct.pack_into('<i',copy,at+8,10000000)
        with tempfile.TemporaryDirectory() as t:
            f=Path(t)/p.name;f.write_bytes(copy)
            with self.assertRaises(ValueError):inspect_class(f)
