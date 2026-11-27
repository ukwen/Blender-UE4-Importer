"""Restore the exact partial Goblin fixture from existing Library originals, never alter originals."""
import argparse, hashlib, json, shutil
from pathlib import Path


def stage(source, destination, manifest):
    source=Path(source).resolve(); destination=Path(destination).resolve()
    if destination.exists(): raise ValueError('Use a new fixture directory')
    plan=[]; targets=set()
    for name,record in manifest['assets'].items():
        package=record['package']; parts=package.split('/')
        if (Path(name).name!=name or not package.startswith('/Game/') or any(x in ('','.','..') for x in parts[2:])
                or '\\' in package or ':' in package or not name.endswith(('.uasset','.umap'))):
            raise ValueError('Invalid fixture entry: '+name)
        p=source/name
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=record['sha256']:
            raise ValueError('Missing or changed original: '+name)
        target=destination/'Content'/('/'.join(parts[2:])+p.suffix)
        if target in targets: raise ValueError('Duplicate fixture package')
        targets.add(target);plan.append((p,target))
    destination.mkdir(parents=True)
    for src,dst in plan:
        dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
    (destination/'Fixture.uproject').write_text(json.dumps({'FileVersion':3,'Description':'Test-only descriptor; original project descriptor unavailable'}))
    (destination/'staged-assets.json').write_text(json.dumps(manifest,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('destination',type=Path)
    a=p.parse_args();stage(a.source,a.destination,json.loads((Path(__file__).resolve().parents[1]/'docs/GOBLIN_FIXTURE.json').read_text()))
