"""Platform-local, isolated Blender installation smoke test (not a desktop UI test)."""
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('blender','decoder','project','archive','out'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--version',required=True);p.add_argument('--sha256',required=True);a=p.parse_args()
    paths={key:getattr(a,key).resolve() for key in ('blender','decoder','project','archive','out')}
    for key in ('blender','decoder','project','archive'):
        if not paths[key].is_file():p.error(f'{key} file missing: {paths[key]}')
    digest=hashlib.sha256(paths['archive'].read_bytes()).hexdigest()
    if digest.lower()!=a.sha256.lower():p.error('Archive SHA-256 mismatch')
    out=paths['out'];out.mkdir(parents=True,exist_ok=False)
    env=dict(os.environ,UE56_EDITOR_PROJECT=str(paths['project']),UE_EDITOR_PAYLOAD_DECODER=str(paths['decoder']),UE_IMPORTER_ARCHIVE=str(paths['archive']),UE_IMPORTER_EXPECTED_VERSION=a.version,UE56_EDITOR_OUTPUT=str(out/'acceptance.blend'),BLENDER_USER_CONFIG=str(out/'config'),BLENDER_USER_SCRIPTS=str(out/'scripts'))
    script=Path(__file__).resolve().parents[1]/'tests'/'blender_install_archive.py'
    with (out/'acceptance.log').open('w',encoding='utf8') as log:
        result=subprocess.run([str(paths['blender']),'-b','-t','2','--factory-startup','--python-exit-code','1','--python',str(script)],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=600)
    evidence=out/'acceptance.json'
    if result.returncode or not evidence.is_file():raise SystemExit(f'Acceptance failed; see {out / "acceptance.log"}')
    data=json.loads(evidence.read_text());assert data['installed'] and data['imported']==3 and data['reopen_reuse']
    data['archive_sha256']=digest;data['launcher_platform']=sys.platform;evidence.write_text(json.dumps(data,indent=2));print(json.dumps(data,indent=2))

if __name__=='__main__':main()
