"""Original UE4.25 tagged split object maps, without any inherited parser."""
import os,struct,tempfile,unittest,shutil
from pathlib import Path
from package_records import read_split518,decode_records
from project_preflight import read_record,preflight

@unittest.skipUnless(os.environ.get('UASSETAPI_ASSETS'),'Original UE4.25 split fixture required')
class VersionedSplit518Tests(unittest.TestCase):
    def setUp(self):
        self.path=Path(os.environ['UASSETAPI_ASSETS'])/'TestJson/ABP_SMG_A.uasset'

    def test_original_records(self):
        meta,raw,table=read_split518(self.path)
        self.assertEqual((len(table.imports),len(table.exports)),(19,4))
        self.assertEqual([(e.name,e.kind,e.offset,e.size) for e in table.exports],[
            ('ExecuteUbergraph_ABP_SMG_A','Function',3150,112),('AnimGraph','Function',3262,147),
            ('ABP_SMG_A_C','AnimBlueprintGeneratedClass',3409,476),('Default__ABP_SMG_A_C','ABP_SMG_A_C',3885,867)])
        row=read_record(self.path,None)
        self.assertEqual(row['classes'],['ABP_SMG_A_C','AnimBlueprintGeneratedClass'])
        self.assertEqual(row['references'],['/Game/WeaponsNTools/SMG/SK_SMG_A_Skeleton','/Game/WeaponsNTools/SMG/WP_ANIM_SMG_A_Reload_A'])
        self.assertEqual(row['coverage'],'ue4_versioned_split_import_table')
        self.assertEqual(row['soft_coverage'],'unknown')

    def test_corruption_refused(self):
        m,raw,t=read_split518(self.path)
        for offset,fmt,value in [(m['import_offset'],'i',-1),(m['export_offset']+36,'q',len(raw)-3),
                                 (m['export_offset']+104+36,'q',t.exports[0].offset),
                                 (m['export_offset']+44,'i',3)]:
            bad=bytearray(raw);struct.pack_into('<'+fmt,bad,offset,value)
            with self.subTest(offset=offset),self.assertRaises(ValueError):decode_records(m,bad,split518=True)
        for bad in (raw[:-4],raw[:-1]+b'\0'):
            with self.assertRaises(ValueError):decode_records(m,bad,split518=True)
        with self.assertRaises(ValueError):decode_records(m,raw)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/self.path.name;shutil.copyfile(self.path,p)
            self.assertEqual(read_record(p,None)['coverage'],'unknown')
            p.with_suffix('.uexp').write_bytes(self.path.with_suffix('.uexp').read_bytes()[:-4])
            self.assertEqual(read_record(p,None)['coverage'],'unknown')

    def test_original_preflight_excludes_non_geometry(self):
        with tempfile.TemporaryDirectory() as d:
            desc=Path(d)/'Test.uproject';desc.write_text('{"FileVersion":3,"EngineAssociation":"4.25"}')
            content=desc.parent/'Content';content.mkdir()
            for p in (self.path,self.path.with_suffix('.uexp')):shutil.copyfile(p,content/p.name)
            plan=preflight(desc,'GEOMETRY')
            self.assertEqual(plan['seeds'],[])
            self.assertEqual(plan['inventory_count'],1)
            self.assertEqual(plan['closure_count'],0)
