# Independent-component migration (internal; commercial release prohibited pending rights review)

Reference baseline: development 0.10.95-dev, commit 8afb826f9a63f92a7e6c67d4cbfde7d820764de3, tree 954982b398cdbcf672cf7efea7d5c7ea485142a8. Preserve both development and master. Active migration branch: feature/independent-importer. Upstream Waffle1434 authorship retained. This is reimplementation with existing interface knowledge, not a certified clean-room process. No license grant for inherited code is established.

| Component | Migration result | Provenance / limitations |
|---|---|---|
| register_helper.py | Deleted; addon_lifecycle.py | Fresh class/menu registration via Blender Python API. No global driver namespace state. Integration callers still derived. |
| UE_nodes.blend | Deleted; generated_shader_groups.py | Fresh node construction from mathematical operations and required interface contracts, not extracted graphs. 22 groups, seven controlled CPU output evaluations. CameraVector, ScreenPosition, additive rendering explicitly approximate. Scalar math and vector/HLSL edge-case parity not established. CameraDepthFade now requires actual source function, no substitute. |
| umodel.exe | Deleted; native texture bridge | No automatic executable or implicit extracted cache. Existing validated editor reader, actual original T_UE_Logo_M success, missing source refusal, pack/reopen. Explicit-profile cooked operator remains; automatic cooked material texture fallback not yet replaced. Existing native readers have separate provenance reviews pending. |
| README.md | Replaced | New project description retains attribution. |
| uasset.py | Partial | New package_records.py reads immutable object tables for versioned UE4 522 and UE5 1004/1012–1018 monolithic editor profiles. UE4 522 preflight no longer instantiates UAsset. UE5 modern and legacy table callers use a compatibility adapter. Inherited UE4 property, payload, legacy profile and project-resolution code remains; no full removal or commercial clearance. |
| umesh.py | Pending | Modified inherited geometry integration; replace after package interface. |
| umat.py | Pending | Modified inherited graph and material integration; generated groups and texture boundary now decoupled but legacy mapping and graph code remain. |
| umap.py | Pending | Modified inherited level import integration; replace after parser and mesh engine. |
| __init__.py and other historical files | Audit pending | No claim of complete inventory or ownership. |

Dependency audit still required: Blender GPL obligations, UAssetAPI MIT attribution and scope, pinned pyooz and BLAKE3 source/binary rights (not included in installer), fixture rights, any use of Epic specifications or source. Do not rebrand as independently owned or distribute the migration candidate until review. Existing generated graphs in old .blend files are not rewritten; fresh imports select marked generated groups rather than same-named foreign groups. Existing packed images or old materials are not relicensed.

## 0.10.97 — bounded typed table reader

New `package_records.py`: read-only immutable records with signed package-index and name-index checks, exact supported fixed record strides, script offsets, export extents and overlap checks. Reference: UAssetAPI Import.cs, ExportTypes/Export.cs, UnrealTypes/ObjectVersion.cs (MIT attribution retained in third_party/UAssetAPI-LICENSE.txt); layout facts independently applied in Python, not a strict clean-room process. Summary/name metadata from existing MIT-reference package_inspector.py. Adapter preserves existing reconstruction interface; mutable dictionaries are transient, typed records immutable. UE4 522 preflight migrated away from inherited UAsset object parser for name/import/export/soft reference inspection. Earlier UE4 object versions and cooked formats remain on separate paths. No unversioned or split-file support claimed for this module.

Original corpus: 872 matching editor packages accepted (UE4 522: 3; UE5 1004: 3; 1013: 4; 1015: 2; 1016: 2; 1017: 853; 1018: 5). This is table acceptance only, not geometry or full reconstruction coverage. Three new regression tests include original UE4 class/soft-reference identity, immutable records and controlled malformed UE5.7 imports, exports, offsets, cycles, wrong profiles and truncation. 128 passes, 10 skipped. Original two-level and install tests recorded in TEST_REPORT and external checkpoint.

## Next priority

Replace inherited UE4 tagged property decoder and project/path resolution boundary, then migrate remaining UAsset callers; validate original legacy 508 and 522 fixtures and supported split/cooked layouts. Mesh, material and scene integration still derived; full provenance and dependency audit pending. Retain prior feature branch checkpoint and reference branches. No distribution clearance; no claims of strict clean-room provenance.
