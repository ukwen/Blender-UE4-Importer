# Acceptance report — 0.10.77-dev

## Verified in this development turn

- GitHub development baseline `af1d82cb8d07ec251744f2a63d5b40b0b9b0900f`, 276 files; locally recovered archive tree `609634dac5498ac3579758ea728a2d12acb7d7ed` exactly matches previous verified tree. GitHub file/blob identity for `ue5_full_scene.py` and `UE_nodes.blend` matches archive. Master baseline `95f19676ca8c76b14bfc445c1ef2fe28348a1ad0`. No fork releases returned by GitHub release API.
- Fresh Library materialization: five original archives; SHA-256 equals manifest and 0.10.76 checkpoint. Fresh setup extracted Blender and ShooterSam, built native decoder from pinned source, reported Blender 4.2.4 LTS. Python 3.13.5, GCC 14.2.0 (Linux x86-64). No native Unreal Editor runtime.
- Baseline `python -m unittest discover -s tests -p 'test_*.py'`: 91 discovered, 68 passed, 23 fixture-dependent skips, 0 failed. New code: 94 discovered, 71 passed, 23 skipped, 0 failed; repeated on freshly restored environment. Three controlled tests cover inline and external ownership, nested components, wrong level, cycles/templates and unknown inventory. No native instance payload decoded.
- Blender 4.2.4 `tests/blender_ue56_full_scene.py`: ThirdPerson 53 meshes, TestLevel one mesh, one rig, one camera; duplicate refusal, injected fatal-stage rollback, camera preservation and save/reopen passed. Both original level reports found zero supported-class instance-component exports; no positive original UE5 instancing evidence. Readable ShooterSam packages scanned for ISM/HISM/foliage yielded no such exports; unreadable packages do not prove absence. Goblin War Camp Overview.umap retrieved, current UE5 table reader rejected it; no instance decoding claimed.

- Isolated Blender add-on installation: version 0.10.77 enabled, three original SM_Door jobs reconstructed, save/reopen and all three reused, then disabled. Test used fresh Blender user directories.

## Previously reported (not independently rerun here)

0.10.76 original landscape geometry: 64 components, 112 exact borders, 1,018,081 vertices, 0.172 mm world-position error, save/reopen. Earlier original level and animation/material acceptance: see milestone-specific docs and Library checkpoints. Those numbers are historical, not new measurements.

## Blocked / unverified

UE5 native instance/foliage decoding and rendering parity require format evidence and original fixtures. Missing source assets constrain full scene completeness. Unreal runtime comparison and Windows native acceptance remain unverified. Do not claim production readiness or commercial pack compatibility.
