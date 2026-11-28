"""Explicit, non-overwriting recovery of missing /Game editor asset packages.
No filename-only matches, no downloads, no cooked/split or map restoration.
"""
import os
import tempfile
from pathlib import Path
from collections import Counter
from project_session import hash_file
from package_inspector import inspect_package
from ue5_blueprint import read_tables, require
from ue5_scene_dependencies import audit

SIDECARS=('.uexp','.ubulk','.uptnl','.umap')
SCOPE='Exact serialized UE5.6 monolithic /Game asset identity and table bounds; not complete payload, dependency or rendering validation. Existing files never replaced.'


def _target(content, package):
    require(package.startswith('/Game/'),'Only /Game asset recovery supported')
    parts=package[6:].split('/')
    require(all(p and p not in ('.','..') and not any(c in p for c in ('\\',':','\x00')) for p in parts),'Invalid package path')
    require(parts[0] not in ('__ExternalActors__','__ExternalObjects__'),'External actor/object packages require original map ownership')
    p=content.joinpath(*parts[:-1],parts[-1]+'.uasset')
    require(p.resolve()==p and p.is_relative_to(content),'Recovery target uses a symlink or escapes Content')
    require(not os.path.lexists(p) and not any(os.path.lexists(p.with_suffix(e)) for e in SIDECARS),'Existing asset, map or sidecar blocks recovery')
    return p


def _qualify(path,package):
    require(path.resolve()==path and path.is_file(),'Recovery candidate is not a regular contained file')
    require(not any(os.path.lexists(path.with_suffix(e)) for e in SIDECARS),'Split or ambiguous source package')
    sha=hash_file(path)
    meta,_,_,exports,_,_=read_tables(path)
    require(meta['ue5'] in (1016,1017) and meta.get('package_name')==package,'Serialized package identity/profile mismatch')
    roots=[e for e in exports if not e['outer'] and e['name']==package.rsplit('/',1)[-1]]
    require(len(roots)==1 and roots[0]['kind'] not in ('World','Level','Package'),'Missing or ambiguous primary asset export')
    require(hash_file(path)==sha,'Source changed during validation')
    return dict(source=str(path),sha256=sha,size_bytes=path.stat().st_size,asset_class=roots[0]['kind'],ue5=meta['ue5'])


def plan(project,level,folder,limit=10000):
    content=(Path(project.dir)/'Content').resolve();level=Path(level).resolve();folder=Path(folder).expanduser().resolve()
    require(folder.is_dir() and not folder.is_relative_to(content),'Choose a recovery folder outside project Content')
    require(1<=limit<=10000,'Invalid recovery scan limit')
    deps=audit(project,level)
    missing={k:v for k,v in deps['dependencies'].items() if v['status']=='missing_game'}
    rows={k:dict(package=k,status='not_found',hard_references=len(v['hard']),soft_references=len(v['soft']),candidates=[]) for k,v in missing.items()}
    for k,r in rows.items():
        try:r['destination']=str(_target(content,k))
        except ValueError as e:r.update(status='blocked',detail=str(e))
    scanned=directories=0
    for root,dirs,files in os.walk(folder,followlinks=False):
        directories+=1;require(directories<=limit,'Recovery directory limit exceeded')
        dirs[:]=sorted(d for d in dirs if not (Path(root)/d).is_symlink() and not (Path(root)/d).resolve().is_relative_to(content))
        for name in sorted(files):
            if not name.lower().endswith('.uasset'):continue
            scanned+=1;require(scanned<=limit,'Recovery file limit exceeded; choose a narrower folder')
            p=Path(root)/name
            if p.resolve()!=p or not p.is_file() or not p.is_relative_to(folder):continue
            try:meta=inspect_package(p)
            except (OSError,ValueError):continue
            k=meta.get('package_name');r=rows.get(k)
            if not r or r['status']=='blocked':continue
            try:r['candidates'].append(_qualify(p,k))
            except Exception as e:r['candidates'].append(dict(source=str(p),detail=f'{type(e).__name__}: {e}'))
    for r in rows.values():
        if r['status']=='blocked':continue
        n=len(r['candidates'])
        if n>1:r['status']='ambiguous'
        elif n==1:r['status']='ready' if 'sha256' in r['candidates'][0] else 'unsupported'
    return dict(project=str(Path(project.dir).resolve()),level=str(level),folder=str(folder),scanned_files=scanned,counts=dict(Counter(r['status'] for r in rows.values())),rows=sorted(rows.values(),key=lambda r:r['package']),scope=SCOPE)


def restore(project,level,folder,reviewed):
    """Recompute the reviewed plan, then publish verified copies without overwrite.

    Hard-link publication from same-directory temp files is atomic/no-clobber.
    Filesystems lacking hard links fail closed. Roll back created files on error;
    not a crash-proof transaction or protection against hostile concurrent edits.
    """
    current=plan(project,level,folder)
    require(current==reviewed,'Source recovery plan changed; locate candidates again')
    rows=[r for r in current['rows'] if r['status']=='ready'];require(rows,'No verified missing packages to restore')
    content=(Path(project.dir)/'Content').resolve();created=[];dirs=[]
    try:
        for row in rows:
            p=_target(content,row['package']);candidate=row['candidates'][0];src=Path(candidate['source'])
            require(_qualify(src,row['package'])==candidate,'Source candidate changed')
            parents=[];parent=p.parent
            while not parent.exists():parents.append(parent);parent=parent.parent
            for d in reversed(parents):d.mkdir();dirs.append(d)
            _target(content,row['package'])
            fd,tmp=tempfile.mkstemp(prefix='.ue-recovery-',suffix='.tmp',dir=p.parent)
            try:
                import shutil
                with os.fdopen(fd,'wb') as out,src.open('rb') as inp:
                    shutil.copyfileobj(inp,out,1024*1024);out.flush();os.fsync(out.fileno())
                require(hash_file(tmp)==candidate['sha256'] and hash_file(src)==candidate['sha256'],'Source copy hash mismatch')
                _target(content,row['package']);os.link(tmp,p)
                st=p.stat();created.append((p,st.st_dev,st.st_ino))
            finally:Path(tmp).unlink(missing_ok=True)
        result=audit(project,level)
        require(all(result['dependencies'].get(r['package'],{}).get('status')=='available' for r in rows),'Restored package not available in new audit')
        return dict(restored=[dict(package=r['package'],destination=r['destination'],sha256=r['candidates'][0]['sha256']) for r in rows],remaining_hard=result['unresolved_hard'],remaining_soft_only=result['unresolved_soft_only'],unknown_tables=result['unknown_tables'],scope=SCOPE),result
    except Exception:
        for p,dev,ino in reversed(created):
            try:
                s=p.lstat()
                if (s.st_dev,s.st_ino)==(dev,ino):p.unlink()
            except FileNotFoundError:pass
        for d in reversed(dirs):
            try:d.rmdir()
            except OSError:pass
        raise
