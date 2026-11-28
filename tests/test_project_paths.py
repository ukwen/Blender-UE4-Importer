"""Host-independent tests for project discovery and package resolution."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from project_paths import ProjectPaths as UProject, discover_maps

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

    def test_explicit_descriptor_disambiguates(self):
        other = self.root / 'Other.uproject'
        other.write_text('{}')
        self.assertEqual(UProject(other).descriptor, other)

    def test_invalid_descriptor(self):
        descriptor = self.root / 'My Project.uproject'
        for invalid in ('[]', '{"EngineAssociation":123}'):
            descriptor.write_text(invalid)
            with self.assertRaises(ValueError):
                UProject(descriptor)

    def test_map_extension_and_host_independent_discovery(self):
        level = self.content / 'Level.umap'
        level.touch()
        hidden = self.root / 'Content' / '__ExternalActors__'
        hidden.mkdir(); (hidden / 'Hidden.umap').touch()
        descriptor = self.root / 'My Project.uproject'
        self.assertEqual(Path(UProject(descriptor).resolve_package('/Game/Meshes/Level', '.umap')), level)
        self.assertEqual(discover_maps(descriptor)[2], [('Meshes/Level.umap', str(level))])

    def test_portable_identity_rejection(self):
        p = UProject(self.asset)
        for name in ('/Game/NUL', '/Game/Meshes/Bad?', '/Game/A.', '/Game/A ', '/Game/A\x00B'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                p.resolve_package(name)

    def test_symlink_escape(self):
        outside = Path(self.temp.name) / 'outside'
        outside.mkdir()
        link = self.root / 'Content' / 'Link'
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('Symlink creation unavailable')
        with self.assertRaises(ValueError):
            UProject(self.asset).resolve_package('/Game/Link/Chair')

if __name__ == "__main__":
    unittest.main()
