import tempfile, unittest
from pathlib import Path
from import_workflow import table_scope, cached_tables, dependency_actions, Stages

class ImportWorkflowTests(unittest.TestCase):
    def test_scoped_reuse_invalidation_and_release(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'A.uasset';p.write_bytes(b'a');calls=[]
            def reader(path):
                calls.append(path);return {'names':['A']},path.read_bytes(),[],[],None,None
            with table_scope(8192) as c:
                self.assertEqual(cached_tables(p,reader)[1],b'a')
                with table_scope() as nested:
                    self.assertIs(nested,c);self.assertEqual(cached_tables(p,reader)[1],b'a')
                p.write_bytes(b'new');self.assertEqual(cached_tables(p,reader)[1],b'new')
                p.with_suffix('.uexp').touch();cached_tables(p,reader)
                self.assertEqual((c.hits,c.misses),(1,3));self.assertLessEqual(c.peak,c.budget)
            self.assertEqual(c.resident,0);cached_tables(p,reader);self.assertEqual(len(calls),4)
    def test_budget_eviction_and_failure(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'A.uasset';q=Path(d)/'B.uasset';p.touch();q.touch()
            def reader(path):return {'names':[]},b'xyz',[],[],None,None
            with table_scope(5000) as c:
                cached_tables(p,reader);cached_tables(q,reader);cached_tables(p,reader)
                self.assertEqual(c.evictions,2);self.assertLessEqual(c.peak,c.budget)
                def fail(path):raise ValueError('bad')
                with self.assertRaises(ValueError):cached_tables(q,fail)
                self.assertNotIn(q,c.items)
            with table_scope(0) as c:
                cached_tables(p,reader);cached_tables(p,reader);self.assertEqual(c.hits,0)
    def test_action_priority_and_scope(self):
        report=dict(dependencies={'/Game/B':dict(status='missing_game',hard=[],soft=['X']),'/Engine/A':dict(status='missing_engine',hard=['X','Y'],soft=[]),'/Game/C':dict(status='available',hard=['X'],soft=[])},unknown_tables=['X'],ready_for_strict_import=False)
        a=dependency_actions(report);self.assertEqual([r['package'] for r in a['packages']],['/Engine/A','/Game/B']);self.assertEqual(a['unresolved_packages'],2);self.assertIn('not a count',a['scope'])
    def test_progress_and_exception_timing(self):
        events=[];s=Stages(events.append);self.assertEqual(s.run('one',lambda:5),5)
        with self.assertRaises(ZeroDivisionError):s.run('two',lambda:1/0)
        self.assertEqual(events,['one','two']);self.assertEqual(set(s.report()['stage_seconds']),{'one','two'})
