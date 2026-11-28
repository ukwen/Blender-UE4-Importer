# Recovery dependencies

Linux x86-64: Blender 4.2.4 LTS, Python 3 (standard unittest), Bash, tar/xz, unzip, git, sha256sum, GCC/g++ with SSE4.1. Use existing Library originals only. `tools/restore_development.sh` checks all four immutable archives and builds the native editor payload decoder from pinned sources. Run with trusted assets; the experimental decoder is not a sandbox. Review third-party licenses before distribution; do not bundle decoder sources/binaries into the add-on.

| Original filename | Library directory |
| --- | --- |
| blender-4.2.4-linux-x64.tar.xz | /Development Tools/Blender/ |
| ShooterSam-UE5.6-editor.zip | /Development Tools/Unreal Importer/Reference Sources/ |
| pyooz-fde8c26-source.zip | same Reference Sources |
| blake3-282d066-source.zip | same Reference Sources |
| Blender-UE4-Importer-<version>-local.zip | same Reference Sources |
| Unreal_Importer_<version>_checkpoint.json | same Reference Sources |
| install-<milestone>.zip | same Reference Sources (from 077 onwards; older releases may only be conversation attachments) |

Hashes of the four input archives: RECOVERY_ASSETS.sha256. Source/release hashes and commit identity: per-milestone checkpoint. Goblin War Camp (existing Library) and Matya/UAssetAPI fixtures are supplemental; do not fabricate missing paths. Fixture-gated tests may be skipped where original assets are absent. Existing ShooterSam has 227 missing MainLevel static mesh packages (1,976 references); missing terrain material and Wraith skeleton, engine meshes and unmatched material groups. Native Unreal runtime not available; Windows needs separate acceptance.

Run `source /new/workdir/environment.sh`, then `python -m unittest discover -s tests -p 'test_*.py'`. Example real scene regression: `UE56_EDITOR_OUTPUT=/absolute/output.blend "$BLENDER" -b --factory-startup --python-exit-code 1 --python tests/blender_ue56_full_scene.py`. See DEVELOPMENT.md and individual milestone notes for other fixture variables. Isolated installation test requires UE_IMPORTER_ARCHIVE and UE_IMPORTER_MODULE (default ue_importer_dev), UE_IMPORTER_EXPECTED_VERSION, and UE56_EDITOR_OUTPUT; set BLENDER_USER_SCRIPTS and BLENDER_USER_CONFIG to fresh directories. Never equate this with Unreal runtime parity.

Supplemental original commercial fixture: `/Development Tools/Unreal Importer/Western Frontier/Unreal Engine POLYGON - Western Frontier Pack (4.25 - 4.27, 5.0 - 5.3).zip` (56,701,078 bytes; SHA-256 `3830b17b674ae4a390785f6ea5769e29fccac94a8ce4f196bf9e73bba2a44701`). Retrieve only for legacy acceptance; extract to a fresh folder and set `UE_WESTERN_PROJECT` to `POLYGON - Western Frontier Pack 4.27/PolygonWestFrontier`. Original maps have editor package version 508. No new downloads or bundling of third-party test assets.

Goblin mixed-version fixture: recover the 59 files named by [GOBLIN_FIXTURE.json](GOBLIN_FIXTURE.json) from its Library directory, into a flat originals directory. `python tools/stage_goblin_fixture.py ORIGINALS NEW_FIXTURE` checks every hash and stages only the recorded package paths. The original Overview map is UE4 editor 522 (compatible engine 4.26); newer Blueprint files are mixed in; synthetic `Fixture.uproject` and `Content/FixtureMaps/Overview.umap` location are for testing only. This is not a complete original project. Set `UE_GOBLIN_PROJECT=NEW_FIXTURE/Fixture.uproject` and `UE_GOBLIN_OUTPUT` to a fresh absolute .blend path; run `"$BLENDER" -b -t 2 --factory-startup --python-exit-code 1 --python tests/blender_goblin_full_scene.py`. Do not bundle commercial asset bytes in the repository or public release.

Migration candidate 0.10.96 removes the bundled texture executable and uses only native validated editor textures in automatic legacy material binding. Explicit-profile cooked texture operator remains. Unsupported editor/cooked automatic material texture paths are reported missing; no implicit external execution. Generated shader graphs require Blender only. Review rights of all native decoder dependencies and all inherited modules before distribution.
