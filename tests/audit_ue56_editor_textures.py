"""Full fixture texture acceptance. Pillow checks written RGBA PNG bytes independently."""
from pathlib import Path
import os,sys,io,hashlib,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ue5_editor_texture import read_texture
from ue5_blueprint import read_tables
from PIL import Image
root=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content'; results={}
for p in sorted(root.rglob('*.uasset')):
    try:
        m,b,im,ex,ref,pkg=read_tables(p)
        if not any(e['kind']=='Texture2D' and not e['outer'] for e in ex):continue
    except Exception:continue
    try:
        png,meta=read_texture(p);assert hashlib.sha256(Image.open(io.BytesIO(png)).convert('RGBA').tobytes()).hexdigest()==meta['rgba_sha256'];results[str(p.relative_to(root))]=dict(status='pass',**meta);print('PASS',p.name,meta['width'],meta['height'],flush=True)
    except Exception as e:results[str(p.relative_to(root))]=dict(status='fail',error=str(e));print('FAIL',p.name,str(e),flush=True)
Path(os.environ['UE56_TEXTURE_REPORT']).write_text(json.dumps(results,indent=2));print('TOTAL',len(results),sum(v['status']=='pass' for v in results.values()))
