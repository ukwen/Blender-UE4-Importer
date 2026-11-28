import tempfile
import unittest
from pathlib import Path
from tools.audit_inherited_components import audit


class RemovalGate(unittest.TestCase):
    def test_files_and_imports(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'umesh.py').write_text('# present')
            (root/'consumer.py').write_text('from uasset import UAsset\nimport importlib\nimportlib.import_module("umat")\n__import__("umap")\n')
            result=audit(root)
            self.assertEqual(result['remaining_files'],['umesh.py'])
            self.assertEqual([x['modules'] for x in result['references']],[['uasset'],['umat'],['umap']])
            self.assertFalse(result['known_removal_gate_passed'])
            (root/'umesh.py').unlink();(root/'consumer.py').unlink()
            self.assertTrue(audit(root)['known_removal_gate_passed'])
            self.assertFalse(audit(root)['commercial_clearance'])
