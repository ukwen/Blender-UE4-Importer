"""Host-independent saved-project discovery and package identity resolution.

Implementation based on the application's /Game and /Engine mount contract,
Python pathlib/JSON APIs and explicit engine-install configuration. No binary
parser, Blender API or original importer helper is required.
"""
from pathlib import Path
import json
import os
import re

_RESERVED = re.compile(r'^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$', re.I)
_EXTERNAL = {'__ExternalActors__', '__ExternalObjects__'}


def descriptor_metadata(path):
    path = Path(path)
    if path.suffix.lower() != '.uproject' or not path.is_file():
        raise ValueError('Select an existing .uproject file')
    with path.open(encoding='utf-8-sig') as stream:
        metadata = json.load(stream)
    if not isinstance(metadata, dict):
        raise ValueError('Invalid project descriptor')
    association = metadata.get('EngineAssociation')
    if association is not None and not isinstance(association, str):
        raise ValueError('Invalid EngineAssociation')
    return metadata


def _engine_locations(association):
    override = os.environ.get('UNREAL_ENGINE_ROOT')
    if override:
        yield Path(override).expanduser()
    if os.name == 'nt' and association and re.fullmatch(r'[A-Za-z0-9.{}_-]+', association):
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 'SOFTWARE\\EpicGames\\Unreal Engine\\' + association) as key:
                yield Path(winreg.QueryValueEx(key, 'InstalledDirectory')[0])
        except OSError:
            pass


def _parts(relative):
    parts = relative.split('/')
    if any(not p or p in ('.', '..') or p.endswith((' ', '.')) or _RESERVED.fullmatch(p)
           or any(ord(c) < 32 or c in '\\:<>"|?*' for c in p) for p in parts):
        raise ValueError('Invalid package path: ' + repr(relative))
    return parts


class ProjectPaths:
    """A project context, with optional engine content, independent of asset parsing."""
    def __init__(self, source):
        source = Path(source).expanduser().resolve()
        descriptor = None
        if source.suffix.lower() == '.uproject':
            descriptor = source
            root = source.parent
            metadata = descriptor_metadata(source)
        else:
            root = source.parent
            fallback = next((p.parent for p in source.parents if p.name.casefold() == 'content'), root)
            root = fallback
            metadata = {}
            for parent in source.parents:
                candidates = sorted(p for p in parent.glob('*.uproject') if p.is_file())
                if candidates:
                    if len(candidates) != 1:
                        raise ValueError(f'Ambiguous Unreal project descriptors in {parent}')
                    descriptor = candidates[0]
                    root = parent
                    metadata = descriptor_metadata(descriptor)
                    break
        self.descriptor = descriptor
        self.dir = str(root)
        self.engine_dir = None
        self.association = metadata.get('EngineAssociation')
        for location in _engine_locations(self.association):
            engine = next((p.resolve() for p in (location / 'Engine', location) if (p / 'Content').is_dir()), None)
            if engine is not None:
                self.engine_dir = str(engine)
                break

    def resolve_package(self, identity, extension='.uasset'):
        if extension not in ('.uasset', '.umap'):
            raise ValueError('Unsupported package extension')
        if not isinstance(identity, str):
            raise ValueError('Expected package identity string')
        mount, separator, relative = identity[1:].partition('/') if identity.startswith('/') else ('', '', '')
        if not separator or mount not in ('Game', 'Engine'):
            raise ValueError('Unsupported package mount: ' + identity)
        parts = _parts(relative)
        if mount == 'Engine' and self.engine_dir is None:
            raise FileNotFoundError('Engine dependency unavailable: ' + identity + '; set UNREAL_ENGINE_ROOT')
        root = (Path(self.dir if mount == 'Game' else self.engine_dir) / 'Content').resolve()
        target = root.joinpath(*parts[:-1], parts[-1] + extension).resolve()
        if not target.is_relative_to(root):
            raise ValueError('Package escapes content root: ' + identity)
        return str(target)


def discover_maps(descriptor, redirectors=None):
    """Inventory saved levels without Blender; never follow a map redirector."""
    from saved_project_levels import map_redirector
    project = ProjectPaths(descriptor)
    if project.descriptor is None or Path(descriptor).suffix.lower() != '.uproject':
        raise ValueError('Select an existing .uproject file')
    root = (Path(project.dir) / 'Content').resolve()
    if not root.is_dir():
        raise ValueError('Project Content directory is missing')
    results = []
    for path in root.rglob('*'):
        if path.suffix.lower() != '.umap' or not path.is_file():
            continue
        relative = path.relative_to(root)
        if _EXTERNAL.intersection(relative.parts) or not path.resolve().is_relative_to(root):
            continue
        target = map_redirector(path)
        if target:
            if redirectors is not None:
                redirectors.append(dict(source=relative.as_posix(), destination=target))
        else:
            results.append((relative.as_posix(), str(path.resolve())))
    return str(project.descriptor), project.association or 'Unknown', sorted(results)
