"""Run after opening a .blend: environment variables UE_POSE_REFERENCE, UE_POSE_ARMATURE, UE_POSE_REPORT."""
import bpy,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from animation_reference import compare_reference
source=Path(os.environ['UE_POSE_REFERENCE']);out=Path(os.environ['UE_POSE_REPORT'])
assert source.stat().st_size<=256*1024*1024,'Reference exceeds 256 MiB'
report=compare_reference(bpy.data.objects[os.environ['UE_POSE_ARMATURE']],bpy.context.scene,json.loads(source.read_text()))
out.write_text(json.dumps(report,indent=2));print('ANIMATION_REFERENCE',report,flush=True)
if not report['within_tolerance']:raise RuntimeError('Animation comparison outside tolerance; see report')
