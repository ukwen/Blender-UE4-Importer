"""Host-independent tests for project discovery and package resolution."""
import ast
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Isolate the resolver from the original Blender-dependent binary parser.
source = Path(__file__).resolve().parents[1] / "uasset.py"
tree = ast.parse(source.read_text(encoding="utf-8"))
project = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "UProject")
namespace = dict(Path=Path, os=os, json=json, winreg=None)
exec(compile(ast.Module(body=[project], type_ignores=[]), str(source), "exec"), namespace)
UProject = namespace["UProject"]

class ProjectPathsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "My Project"
        self.content = self.root / "Content" / "Meshes"
        self.content.mkdir(parents=True)
        self.asset = self.content / "Chair.uasset"
        self.asset.touch()
        (self.root / "My Project.uproject").write_text('{"EngineAssociation":"4.27"}')
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_project_without_engine(self):
        p = UProject(str(self.asset))
        self.assertEqual(Path(p.dir), self.root)
        self.assertIsNone(p.engine_dir)
        self.assertEqual(Path(p.resolve_package("/Game/Meshes/Chair")), self.asset)

    def test_missing_engine_dependency(self):
        with self.assertRaises(FileNotFoundError):
            UProject(str(self.asset)).resolve_package("/Engine/BasicShapes/Cube")

    def test_optional_engine_override(self):
        engine = Path(self.temp.name) / "UE" / "Engine"
        (engine / "Content").mkdir(parents=True)
        with patch.dict(os.environ, {"UNREAL_ENGINE_ROOT": str(engine.parent)}):
            p = UProject(str(self.asset))
            self.assertEqual(Path(p.resolve_package("/Engine/BasicShapes/Cube")), engine / "Content" / "BasicShapes" / "Cube.uasset")

    def test_reject_invalid_mount_and_traversal(self):
        p = UProject(str(self.asset))
        for value in ("/Unknown/Mesh", "/Game/../Escape", "/Game//Mesh", "/Game/C:/Mesh"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                p.resolve_package(value)

    def test_content_only_folder(self):
        (self.root / "My Project.uproject").unlink()
        self.assertEqual(Path(UProject(str(self.asset)).dir), self.root)

    def test_ambiguous_descriptor(self):
        (self.root / "Other.uproject").write_text("{}")
        with self.assertRaises(ValueError):
            UProject(str(self.asset))

if __name__ == "__main__":
    unittest.main()
