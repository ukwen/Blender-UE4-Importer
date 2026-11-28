# 0.10.0 development candidate — Blender 4.2

This is an unaccepted compatibility candidate on the development branch, not a release. Original master is preserved. Target Blender 4.2.4 LTS; no UE5 import support is claimed. UE5 legacy package headers are rejected before the UE4 layout is read.

Changes: optional engine discovery and explicit engine-dependency errors; cross-platform project paths; updated Principled sockets, group interfaces, blend settings and probe enums; guarded removed mesh smoothing property; material extraction subprocess uses argument list and timeout. Blender 4.2 masked materials use a documented dithered approximation, not exact clipping. Native texture extraction still requires a compatible UModel binary (UMODEL_PATH for Linux). Plugin mounts remain unsupported.

Acceptance commands (from repository root):

    python -m unittest discover -s tests -p "test_*.py" -v
    blender -b --factory-startup --python-exit-code 1 --python tests/blender_smoke.py

Blender runtime and genuine UE4 import regression tests must pass before acceptance. Compare mesh vertices/faces, UVs, material slots, actor transforms, and saved/reopened scenes against the original baseline. No distribution or installer until original licensing is resolved.

## 0.10.44-dev

See [Goblin character assembly](docs/0.10.44-goblin-assembly.md).

## 0.10.45-dev

See [Physics asset collision preview](docs/0.10.45-physics-preview.md).

## 0.10.46-dev

See [Native vehicle collision and automatic association](docs/0.10.46-vehicle-physics.md).

## 0.10.47-dev

See [Project batch workflow](docs/0.10.47-project-batch.md).

## 0.10.48-dev

See [Saved-scene import sessions and asset selection](docs/0.10.48-project-sessions.md).

## 0.10.49-dev

See [UE5 dependency inventory and Blueprint ancestry](docs/0.10.49-ue5-dependencies.md).

## 0.10.50-dev

See [UE5.0 cooked geometry acceptance](docs/0.10.50-ue5-cooked-geometry.md).

## 0.10.51-dev

See [Modern UE5 cooked geometry, material parameters and texture acceptance](docs/0.10.51-modern-ue5.md).

## 0.10.52-dev

See [UE5.6 native skeletal LOD acceptance](docs/0.10.52-ue5-skeletal-lods.md).

## 0.10.53-dev

See [Shared LODs and cooked material dependencies](docs/0.10.53-shared-lods-material-dependencies.md).

## 0.10.54-dev

See [UE5.7 editor dependency tables](docs/0.10.54-ue57-dependencies.md).

## 0.10.55-dev
See [UE5.6 editor source reconstruction](docs/0.10.55-ue56-editor.md).

## 0.10.56-dev

See [UE5.6 source textures and material graphs](docs/0.10.56-editor-materials.md).

## 0.10.57-dev

See [UE5.6 editor FK animation](docs/0.10.57-editor-animation.md).

## 0.10.58-dev

See [editor animation curves and expanded compatibility](docs/0.10.58-editor-animation-curves.md).

## 0.10.59-dev

See [full UE5.6 reference skeleton and authored animation previews](docs/0.10.59-editor-skeleton-preview.md).

## 0.10.60-dev

See [editor Blueprint components and sockets](docs/0.10.60-editor-components.md).

## 0.10.61-dev

See [editor texture regions and decoder portability](docs/0.10.61-editor-texture-regions.md).

## 0.10.62-dev

See [legacy UE5 editor source profiles](docs/0.10.62-legacy-editor.md).

## 0.10.63-dev

See [local material functions and saved construction components](docs/0.10.63-editor-functions-components.md).

## 0.10.64-dev

See [native UE5.6 lighting and scene markers](docs/0.10.64-editor-lighting.md).

## 0.10.65-dev

See [UE5.7 saved Blueprint composition](docs/0.10.65-ue57-blueprint.md).

## 0.10.66-dev

See [targeted missing mesh recovery](docs/0.10.66-missing-mesh-repair.md).

## 0.10.67-dev

See [legacy PNG material channel previews and grid validation](docs/0.10.67-grid-channel-preview.md).

## 0.10.68-dev

See [saved UE5.6 spring-arm camera rig previews](docs/0.10.68-camera-preview.md).

## 0.10.69-dev

See [procedural material coordinate and opacity previews](docs/0.10.69-procedural-preview.md).

## 0.10.70-dev

See [authored root translation and external pose validation](docs/0.10.70-root-translation.md).

## 0.10.71-dev

See [bounded unlit translucent surface previews](docs/0.10.71-unlit-translucency.md).

## 0.10.72-dev

See [saved masked character materials and source character integration](docs/0.10.72-masked-character.md).

## 0.10.73-dev

See [saved skeletal characters in native level reconstruction](docs/0.10.73-level-characters.md).

## 0.10.74-dev

See [one-operation saved level transfer](docs/0.10.74-full-scene.md).

## 0.10.75-dev

See [selected-level source dependency qualification](docs/0.10.75-scene-dependencies.md).

## 0.10.76-dev

See [native saved landscape heightfield reconstruction](docs/0.10.76-landscape.md).

## 0.10.77-dev

See [handoff](docs/HANDOFF.md), [roadmap](docs/ROADMAP.md), and [test report](docs/TEST_REPORT.md). Saved UE5 instance-component inventory reports unsupported payloads rather than treating component counts as decoded instances.

## 0.10.78-dev

See [saved decal projector placement](docs/0.10.78-decal-projectors.md).

## 0.10.79-dev

See [unified legacy commercial scene transfer](docs/0.10.79-legacy-full-scene.md). The one-click operation now also dispatches the bounded UE4 editor 508 profile, with original foliage and materials, light preview and explicit coverage.

## 0.10.80-dev

See [legacy 522 mixed-version Goblin full-scene acceptance](docs/0.10.80-goblin-full-scene.md). The single scene operation recognizes the bounded UE4 editor 522 profile and validates both legacy map table extents before import. Existing native decoders are reused.

## 0.10.81-dev

See [opt-in sky preview](docs/0.10.81-environment-preview.md). Separate saved-world previews never silently change the scene world.

## 0.10.82-dev

See [editor sampler fidelity](docs/0.10.82-sampler-fidelity.md). Explicit UV0, shared address helper and bounded direct tangent normal source-art preview; no runtime tangent/compression parity claim.

## 0.10.83-dev

See [instance fidelity](docs/0.10.83-instance-fidelity.md): preserve selected/shadowed instance overrides and unresolved bindings; unclamped scalar-factor RGB interpolation validated in actual Blender CPU render.

## 0.10.84-dev

See [fog and material semantics](docs/0.10.84-fog-and-material.md). Explicit base property flags, bounded RGB-factor Lerp and opt-in finite fog. Original map toggle/reopen and controlled CPU render verified; no engine parity claim.

## 0.10.85-dev

See [saved level sets and partition ownership](docs/0.10.85-level-sets.md). Atomic checked independent maps, partition ownership and explicit unsupported composition, material override guard and external actor path safety.

## 0.10.86-dev

[Native saved brush operands](docs/0.10.86-brush-operands.md): exact bounded inline UE5.6 Polys geometry, 53 original operands, explicit CSG roles and non-rendering collection. Compiled BSP and volume reconstruction remain outstanding.

## 0.10.87-dev

See [compiled BSP and volume bounds](docs/0.10.87-compiled-bsp.md). Original compiled render buffers (26 components) and 12 non-rendering volume guides; native BSP materials remain absent or unspecified in fixtures.

## 0.10.88-dev

See [landscape source atlas](docs/0.10.88-landscape-atlas.md). Original 64 embedded finest-mip textures, exact lossless RGBA, 4,064,256 derived corner UVs, component material ancestry and Heightmap bindings. Painted layers and missing material graphs are not reconstructed.

## 0.10.89-dev

[Workflow performance and source actions](docs/0.10.89-workflow.md). No persistent package cache, measured table reuse and original geometry digests.

## 0.10.90-dev

[Source recovery, cancellation and memory](docs/0.10.90-source-recovery.md). Explicit read-only recovery plan and non-overwriting verified copies, restored source geometry under original level collections, between-map transaction close rollback, adjustable package cache budget and measured process peak RSS.

## 0.10.91-dev

See [landscape memory and whole-project acceptance](docs/0.10.91-landscape-memory.md). Lower temporary allocation with exact old/candidate terrain digests; map redirector detection; six-world and three commercial-map regressions.

## 0.10.92-dev

Primary sidebar workflow, project-path and rescan guards, safe inter-map event interval, explicit filesystem confirmation warning. Linux Xvfb actual X11 clipboard and keyboard acceptance, two original maps, original package recovery in disposable copy. See [desktop workflow](docs/0.10.92-desktop-workflow.md).

## 0.10.93-dev

Selected-level, level-set, source-action and last-operation report navigation and copy. Original two-level Blender and X11 acceptance; see [report navigation](docs/0.10.93-report-navigation.md).

## 0.10.94-dev

Scoped recovery plan review and confirmation, ignored-file diagnostics, zero-ready and stale-plan refusal. Original recovery, overlay and actual X11 confirmation regression. See [recovery review](docs/0.10.94-recovery-review.md).

## 0.10.95-dev

Cooperative UE5.6 full-scene and checked-level reconstruction with safe in-map actor/component/material checkpoints; exact rollback, actual X11 Escape, source-backed material closure diagnostics including decal/terrain, original UE5.7 fixture audit, and platform-local installer acceptance launcher. See [stage cancellation and evidence audit](docs/0.10.95-stage-cancellation.md).

## 0.10.96-dev — independent component migration

Separate `feature/independent-importer` branch, preserving development 0.10.95. Remove three inherited files; generated shader groups, registration lifecycle, native editor texture boundary. See [provenance and remaining replacements](docs/INDEPENDENCE.md). Not a clean-room or commercial release claim.

## 0.10.97-dev — typed editor package table migration

See [independence](docs/INDEPENDENCE.md) and [tests](docs/TEST_REPORT.md). Modern UE5 and UE4 522 preflight use bounded typed records; remaining inherited parser and import integration are still pending.

## 0.10.98-dev — project paths and classic property records

Independent project resolution, Python-only saved level inventory, bounded classic UE4 property headers, typed animation routing. See docs/INDEPENDENCE.md and docs/TEST_REPORT.md.

## 0.10.99-dev — native skeletal and physics migration

UE4.27 editor skeletal, reference-skeleton and PhysicsAsset readers now use typed package records without inherited parser imports; all ten recovered original decoded records exactly match 0.10.98. See docs/TEST_REPORT.md and docs/INDEPENDENCE.md.

## 0.10.100-dev — classic static geometry migration

Typed UE4 object version 508 package tables, soft dependencies and static geometry boundary. See docs/INDEPENDENCE.md and docs/TEST_REPORT.md.

## 0.10.101-dev — classic actor and foliage reconstruction boundary

Typed actor placement and foliage source records, legacy-free supported geometry-only map import, original two-map parity and reopening. See docs/TEST_REPORT.md and docs/INDEPENDENCE.md.

## 0.10.102-dev — typed Blueprint defaults and body template migration

See docs/INDEPENDENCE.md and docs/TEST_REPORT.md. Supported UE4 522 Blueprint CDO/SCS and Character body templates are host independent. Integrated Western Frontier and Goblin regressions passed.

## 0.10.103 — complete removal target, independent classic scene path

New `classic_map_records.py`, `reference_identity.py`, `classic_texture.py`, `source_compression.py`, `mesh_description_blender.py` and `classic_material.py` migrate typed map-owned components, legacy 508 skeletal package boundary, classic texture package boundary and modern mesh-description construction. Existing native payload algorithms retained where applicable; their provenance remains subject to audit. Basic UE4 508 material graph reads supported surface outputs, constant/scalar/color and texture expressions from typed property records (MIT UAssetAPI MaterialInputProperties reference and original editor packages); explicit unsupported expression/field diagnostics and fallback remain. Alpha/transmission preview and runtime material fidelity are not equivalent to Unreal. No new source assets. Original Western payload parity: 31 skeletal records and 14 PNG/metadata records exactly match 0.10.102 (canonical report SHA256 9caa50ef83aac0ada52ef70eacb71c360b383a410b1fc973a4248fbda3a90fe4). Actual both-map integrated geometry+material+component test blocks all four inherited modules, including failed import attempts; 2814 mesh objects, 36 rigs, 462 foliage, 10 effective materials and five packed scene images with verified slot identities and save/reopen. Graph status remains graph_imported_unverified. Original mixed Goblin report exact and reopen; modern two-level 94 objects, reopen and rollback pass. Earlier 522 texture parity and unsupported earlier static/Blueprint/texture profiles still evidence-gated.

User's acceptance target is now complete removal of inherited implementation, not merely migration of individual paths. `python tools/audit_inherited_components.py --require-removed` fails until known inherited files and direct/literal production imports are absent; it is not a clean-room certificate or legal clearance. At 0.10.103 four core files remain (uasset.py, umesh.py, umat.py, umap.py), 30 import sites including their internal dependencies, original registration, legacy direct import operators, older profiles, material layers/advanced graphs and wind. Keep the working fallback until equivalent supported features pass. Audit retained algorithms and necessary third-party notices before commercial distribution. No commercial clearance.

## 0.10.104-dev — cold registration and UE4.27 static source

See docs/TEST_REPORT.md and docs/INDEPENDENCE.md. Four original compressed MeshDescription sources matched the prior mesh data exactly; independent direct import and material persistence verified. Legacy compatibility remains.

## 0.10.105-dev — typed advanced material and wind boundaries

Native modern standalone surface/instance routing, typed UE4.27 basic and advanced material graph with bounded local function expansion, effective global parameter resolution and source-specific stale GUID corroboration. Classic source texture bulk offset fixed. Wind profile and shared layer texture binding no longer import inherited modules. Original Goblin chain, three textures and three wind profiles validated against earlier reference; strict/partial modern material and failure rollback, full original mixed Goblin and independent Western maps pass. Runtime visual equivalence remains unverified.

## 0.10.106-dev — native static material entrypoints and classic source LODs

Direct supported static packages now use typed readers for material-bearing and geometry-only import. Classic 522 explicit source model iteration preserves absent LOD identities, bounds and visibility; controlled multi-LOD headers reuse original Rope bulk, not an original multi-LOD package. See docs/TEST_REPORT.md.

## 0.10.107-dev — classic particle surface and native skeletal entrypoints

Two original classic particle surface graphs decoded with explicit 508 expression-input FString layout; partial previews and strict metadata behavior shared with the modern builder. Three original editor skeletal profiles use the direct menu with native skinning and material bindings. See docs/TEST_REPORT.md and docs/INDEPENDENCE.md.

## 0.10.108-dev — typed layer records and detached snapshots

Bounded UE4.27 default layers, detached snapshot GUID and link-state records; controlled independent compositing, scalar GUID replay and rollback; existing legacy graph path retains compatibility. See docs/TEST_REPORT.md.

## 0.10.109-dev — typed scoped material parameters

Independent scoped parameter decoding and native texture identity; controlled four-kind layer replay and malformed-record refusal. See docs/INDEPENDENCE.md and docs/TEST_REPORT.md.

## 0.10.110-dev — typed layer-function compiler

Bounded classic bundle function parser and editable Blender compiler. Three controlled function groups and three CPU render checks passed. See docs/TEST_REPORT.md and docs/INDEPENDENCE.md.

## 0.10.111-dev — typed vector, arithmetic and texture layer functions

Independent layer compiler extension: RGB/vector constants and editable RGBA parameters, five explicit scalar operations (Add, Subtract, Multiply, OneMinus, LinearInterpolate), bounded default-UV color/linear-color texture sampling and parameter nodes. Arithmetic requires serialized defaults for unlinked operands. Native standalone layer-function menu route for the supported 522 subset; packed image/color-space validation and rollback for typed texture overrides. Original Goblin 4096x4096 texture packed byte-identical to reference, controlled graph and override renders exact, vector/math max error 4.768371586472142e-8. Seven additional Python tests; 180 pass, ten skips. Original layer package unavailable; arbitrary vector math, normal sampler, masked/indexed edges, explicit UV, attribute selection, nested calls remain unsupported. Four inherited files/29 literal references remain.

## 0.10.112 — Objective and core workflow focus

Primary objective: a professional, independently implemented direct Unreal UE4/UE5 saved-project and asset importer for editable Blender scenes, without FBX/USD or gameplay emulation. The user's explicit instruction is not to drift into repeated narrow material research while core dependencies remain. Keep ordinary usable workflow and replacement work on development; preserve master and necessary legal notices.

- The primary File > Import > UE Saved Level (.umap) action now runs the existing atomic saved-project native reconstruction transaction, with strict/partial options, explicit cooked geometry profile and light-preview multiplier. Original project descriptor required. Multiple maps must belong to one project; they remain independent levels, not streaming composition. Historical `import.umap` remains explicitly labeled Legacy Compatibility, including its original option contract.
- Actual Blender 4.2.4 acceptance: original ShooterSam TestLevel (32 objects, 10 meshes, 1 armature) and Western Frontier Overview (417 objects, 352 meshes, 30 armatures). All inherited imports blocked, saved/reopened, duplicate and mixed-project refusal, existing camera/world preserved. No claim of general map parity, all legacy option equivalence or commercial clearance.
- Next: use the audit's remaining production callers as a concrete removal queue, starting with older package and geometry compatibility on existing original evidence; consolidate native map and mesh entrypoints and replace legacy map features that are demonstrably required. Unsupported formats must be explicit, not silently substituted. Complete the general material graph fallback in parallel when source-backed or required for previously supported features; do not pursue open-ended controlled layer-expression research as the primary roadmap.
- Exit criteria: no inherited core files or production references, real UE4/UE5 project-level regression including actual editable geometry/rigs/materials, preserved supported functionality, Windows acceptance, independent provenance and dependency rights review. The current known removal gate still fails: four files and 29 import sites. No commercial distribution clearance.

## 0.10.113 — Consolidated native cooked mesh workflow and UE4 dependency inventory

- Main `import.umesh` now uses native static/skeletal decoders for split cooked assets with an explicit profile. Existing specialized entrypoints are unchanged. UE5.6 shared-rig LODs are available via All supported source LODs. Unsupported native profiles fail without automatic inherited fallback; explicit Legacy compatibility preserves the previous split route (not newly certified). Cooked materials are marked unresolved with source slot identities; no shader equivalence claim.
- `project_preflight` recognizes bounded UE4 -7 tagged split headers, inventories their direct non-script package references, filters geometry jobs and reports missing dependencies. Header inventory is not payload validation or soft/runtime dependency completeness.
- Actual original Matya UE4.18/4.27 and UE5.0: six meshes (640 vertices/572 triangles each), three 6-bone rigs. Original UAssetAPI UE5.4/5.5/5.6: three 24-vertex/12-triangle cubes and Quinn three LODs (45993/14865/7421 vertices; 87280/26998/12998 triangles) on one 89-bone rig. Save/reopen, LOD switching, refusal and rollback passed; inherited imports blocked throughout. Preflight verified 16 UE4 original packages, 2 geometry jobs and 6 dependencies in staged 4.27 fixture; missing dependency detected.
- Regression: Python 193 total, 182 passed, 11 fixture-dependent skips, zero failures. Native TestLevel and Western Overview level menu: 449 objects, 362 meshes, 31 armatures, save/reopen and no inherited imports.
- Four inherited files and 29 literal import sites remain; this milestone bypasses the split fallback for native profiles, not physical removal of a core file. Next prioritize remaining production callers (older monolithic package/geometry and map dependencies) with source-backed tests, not material-only research. Windows acceptance, shader reconstruction, unsupported cooked layouts, original project completeness, rights/provenance and commercial clearance remain open.

## 0.10.114 — Native versioned UE4.25 package inventory and unified dependency audit

- `package_records.read_split518` reads the original UE4.25 versioned tagged .uasset/.uexp object maps (19 imports, four exports) with bounded virtual serial offsets, trailer, table extent and overlap validation. The original ABP_SMG_A package identifies two hard Game dependencies (skeleton and animation); geometry preflight excludes the non-geometry package. No Blueprint execution, animation decoding or additional geometry profile is claimed.
- MaterialResolver now uses project_preflight for non-native-monolithic dependency inventory; its direct inherited package reader import is removed. Original Matya UE4.18, UE4.27 and UE5.0 M_Worm packages each resolve three texture dependencies with no inherited imports, report missing textures, and reject absent sidecars. Unknown inventory profiles fail explicitly rather than invoking a second legacy reader; existing older monolithic preflight fallback remains. This is dependency inventory, not cooked shader reconstruction. Older unclassified material formats may now report unsupported dependencies instead of trying legacy parsing.
- Full Python unittest run: 196 total, 185 passed, 11 fixture-dependent skips. Original cooked mesh menu and Quinn LOD regression passed; original ShooterSam TestLevel and Western Overview passed (449 objects, 362 meshes, 31 armatures), save/reopen and inherited import blocking. Isolated Blender 4.2.4 Linux installer: three imports and reopen reuse passed.
- Removal audit: four inherited files, 28 literal import sites (previously 29); no full file deletion or commercial clearance. Next target remaining package-table consumers and older monolithic geometry/maps using real source fixtures. Only one genuine versioned split 518 source was available; no general UE4.25 coverage. Preserve stable master and legal notices.

Reproduce with `UASSETAPI_ASSETS` pointing at UAssetAPI.Tests/TestAssets, `MATYA_ASSETS` at the extracted Matya samples, `python -m unittest discover -s tests -p 'test_*.py'`, and Blender `tests/blender_split_dependency_audit.py`, `tests/blender_native_cooked_menu.py` and `tests/blender_native_level_entrypoints.py`. Use canonical absolute paths for level acceptance.
## 0.10.115 — Native geometry and catalog boundary

- Native file-menu mesh, project geometry gallery/static resolver and dependency inventory no longer automatically invoke the inherited geometry or table reader for unsupported editor mesh profiles. The existing mesh operator retains the same `cooked_profile` property and offers an explicit Legacy compatibility (editor or cooked) option; native decoder rejection is not retried. Unknown older monolithic profiles now have unknown dependency coverage and must be imported explicitly through compatibility if required. This is a deliberate boundary change, not a replacement decoder for those older profiles; automatic gallery/map coverage for such unsupported profiles is reduced until independently validated.
- The typed root-class selector distinguishes known multi-root non-geometry packages from ambiguous geometry, including original UE4.25 split ABP_SMG_A and UE4.27 TestActorBP. Original mixed gallery: three reconstructed meshes (1,298 vertices, 1,176 triangles, six bones), two skipped Blueprints, one controlled unsupported-version refusal; clean rollback and reopen, zero inherited import attempts. Explicit legacy 508 mesh route separately exercised successfully.
- Python: 200 total, 189 passed, 11 fixture-dependent skips, zero failures. Original cooked menu/Quinn and saved-level tests passed (449 objects, 362 meshes, 31 armatures). Both original Western Frontier maps: 2,814 verified mesh-object bindings, 36 rigs, 14 source textures, five packed images and ten materials, reopen and zero inherited imports. Visual material equivalence is not certified. Isolated Blender 4.2.4 Linux installer passed three imports and reopen reuse.
- Inherited removal audit: four files, 25 literal import sites (previously 28). Three direct calls removed, no full file deletion. General older monolithic format replacement still requires genuine fixtures, and native material, Blueprint, texture, foliage and map compatibility callers remain. No commercial clearance. Next prioritize source-backed map/mesh compatibility and actual inherited file removal; preserve master, notices and working native paths.

Reproduce with `tests/test_native_geometry_boundary.py`, `tests/blender_native_geometry_boundary.py` (set `UE_GEOMETRY_BOUNDARY_OUTPUT`), `tests/blender_native_cooked_menu.py`, `tests/blender_native_level_entrypoints.py`, `tests/blender_independent_western.py` and isolated install acceptance. Fixture environment paths are in prior handoff; no source binaries are committed.

## 0.10.116 — Native foliage boundary and atomic texture menu

- Removed the redundant inherited foliage fallback from production: its decoder only accepted the already-native UE4 508 profile. The typed 508 reader and explicit unsupported 522 component records remain; other profiles now raise a clear error. The old reader is retained solely as a test oracle (not packaged in the installer) to verify actual foliage placement and corruption rejection, not represented as new independent code.
- File > Import > UE Texture (.uasset) now exposes the existing native texture operator with multi-file selection and atomic batch rollback, including restoration of previously reused image fake-user flags. Images are packed and persist after reopen. Native editor menu supports bounded 508/522 and UE5 1004/1013/1017 profiles; older unverified editor profiles are explicitly rejected here. Other material compatibility paths still contain the old editor texture reader. Cooked profiles require matching sidecars and explicit version; a batch uses one color/normal interpretation, not inferred material semantics.
- Blender 4.2.4: 11 original packed textures (one Western 508, one ShooterSam UE5.6, nine Matya cooked UE4.18/4.27/5.0); exact packed hashes on reopen, existing-image flag restoration, duplicate/unknown profile/missing-sidecar and non-texture refusal, no inherited import attempts. Original Western foliage: 223+239 linked instances, max local point error 0.000015378 m, eight malformed payloads refused, 462 reopened; historical parity oracle intentionally uses inherited reader in that test alone. Both Western maps pass with 2,814 mesh bindings, 36 rigs, 14 textures, ten materials; original ShooterSam TestLevel + Western Overview: 449 objects, no inherited import attempts. Python 201 total, 190 passed, 11 skipped, zero failures.
- Four inherited core files and 22 literal production import sites remain (25 previously). No physical deletion of a core file; full provenance, unsupported profiles, Windows and commercial clearance remain open. Next prioritize actual source-backed replacement of remaining map/component/Blueprint and material translators; preserve supported workflows and notices.

Reproduce: `tests/blender_native_texture_menu.py` (UE_TEXTURE_BATCH_OUTPUT), `tests/test_native_foliage_boundary.py`, `tests/blender_western_foliage.py` (UE_SOURCE, UE_FOLIAGE_OUTPUT), `tests/blender_independent_western.py`, `tests/blender_native_level_entrypoints.py`; fixture variables as before.

## 0.10.117 — Native map/component/Blueprint boundary and preview transaction

- Native classic layout and component entrypoints now require the independently supported 508/522 profiles. Native Blueprint defaults use typed 522 or modern readers; cooked and unverified older defaults are explicitly unresolved. Six literal inherited production import sites removed (22 to 16). The explicit historical map/mesh compatibility menu remains; this is not a newly implemented older-profile decoder, and automatic older-profile preview coverage is reduced. Four inherited core files remain.
- Static scene preview now rolls back newly allocated Blender IDs if a late stage raises, including the modern route. Controlled failures after real Western Overview and ShooterSam TestLevel allocation restore the exact pre-call ID set, camera and world. Unsupported classic layout and component profiles are refused before allocations. Successful previews: 415 objects for Western Overview (322 reconstructed static actors, one missing); five objects for ShooterSam TestLevel (two missing static actors; supported mesh components present). This is new-ID rollback, not a general undo system for arbitrary modifications of pre-existing datablocks.
- Original UE4 TestActorBP SCS binding passes without inherited imports; original cooked ABP_SMG_A explicitly unresolved. Controlled typed CDO/SCS association, explicit null, ambiguity and cached unsupported/missing records pass. Replaced legacy-parser-specific controlled association tests with native typed tests; original Goblin integration script remains fixture-dependent and was not rerun in this milestone.
- Python 204 total: 193 passed, 11 skipped, zero failed. Original saved-level regression 449 objects (362 meshes, 31 armatures), reopen and zero inherited attempts. Western both maps: 2,814 bindings, 36 rigs, 14 textures and ten materials, reopen and zero inherited attempts. Isolated Blender 4.2.4 Linux installer passed three imports and reopen reuse. No new Windows, arbitrary legacy format, material fidelity or commercial clearance claims.

Reproduce: `tests/test_native_blueprint_boundary.py`, `tests/blender_native_preview_transaction.py`, `tests/blender_native_level_entrypoints.py`, `tests/blender_independent_western.py`, and `tools/run_install_acceptance.py`. Next prioritize remaining actual replacement: texture source compatibility, shared reference identity and general material/mesh/map legacy translators; preserve supported workflow and legal provenance.

## 0.10.118 — Cooked material source catalog and native material boundary

- File > Import > UE Material (.uasset) now has explicit native cooked dependency profiles for UE4.18, UE4.27 and UE5.0. A project Content directory and descriptor are required; original Matya packages were staged under disposable descriptors, not claimed to be complete original projects. Typed root identity and split export ranges are verified, with exact sidecar coverage, overlapping ranges and malformed trailers refused. The UE4.18 and 4.27 header layout is shared, so a header alone does not certify the engine minor; texture decoding requires the explicitly selected profile.
- Original M_Worm packages: three editable dependency catalogs, three packed raw-channel textures each, all nine packed PNGs equal the native decoder output byte-for-byte, reuse within a source revision, missing texture explicitly unresolved, wrong class/identity, absent sidecar, implicit profile and injected allocation-failure refusals; save/reopen passed with inherited modules blocked. UE4.18 filtered root input records identify three exact source expression links by FName (BaseColor to T_Worm_D, Normal to T_Worm_N, Opacity to T_Worm_A) and BLEND_Translucent; nodes are annotated and mappings retained in JSON after reopen. The catalog intentionally does not connect shader outputs or infer color/normal/translucency semantics. UE4.27 and UE5.0 materials retain dependency-only records; arbitrary filtered graphs and cooked shader bytecode remain unsupported.
- Native editor material resolver and menu no longer invoke inherited graph translation implicitly; explicit Legacy material option remains. The unverified intermediate UE4 editor texture fallback was removed; supported 508/522 and existing UE5 paths remain. This reduces fallback coverage for unsupported older textures even under the historical graph option; no original intermediate texture fixture or replacement decoder was available. Two production literal inherited import sites removed (16 to 14); four inherited core files still present. No commercial provenance clearance.
- Python 208 discovered, 197 passed, 11 fixture-dependent skips, zero failures. Original standalone editor material cases (five, four packed images), cooked mesh menu and three Quinn LODs/89 bones, saved-level regression (449 objects, 362 meshes, 31 armatures), Western both maps (2814 mesh bindings, 36 rigs, 14 source textures, five packed images and ten materials), and isolated Linux Blender 4.2.4 installation (three imports and reopen reuse) passed. Original Goblin and Windows were not rerun.

Reproduce: `tests/test_ue4_split_material_tables.py`, `tests/blender_native_cooked_material_menu.py` (MATYA_ASSETS, UE_COOKED_MATERIAL_MENU_OUTPUT), `tests/blender_independent_material_entrypoints.py`, `tests/blender_native_cooked_menu.py`, `tests/blender_native_level_entrypoints.py`, `tests/blender_independent_western.py`, `tools/run_install_acceptance.py`. Next: translate the positively recovered UE4.18 source edges to an explicitly opt-in editable surface with verified sampler/channel handling, consolidate shared package reference identity, and eliminate remaining explicit legacy map/mesh/material backend dependencies with source-backed feature parity. Do not count merely moving or hiding an inherited import as independent replacement. Preserve legal notices and master.

## 0.10.119 — Opt-in cooked UE4.18 direct surface preview

- File > Import > UE Material, profile UE4.18 cooked dependencies, and Allow partial material preview: the positively recovered direct UV0 BaseColor/Normal/Opacity links of original M_Worm now create an editable Principled surface. Default import remains dependency-only; other cooked profiles remain dependency-only. The gate accepts only the bounded direct RGB/DXT1, BC5 normal and linear BC4 opacity case with known tagged source properties and exact sampler/channel records. It refuses missing inputs, unexpected masks, unsupported properties and incompatible color-space evidence before creating preview nodes. UE4 default SRGB true when absent; explicit false required for the BC4/BC5 sample. Separate packed sRGB and reconstructed normal variants preserve the original three raw images; reuse is revision-keyed. Opacity is the linear BC4 red channel; normal Z reconstructed and green inverted as a Blender UV0 convention preview. No rendering equivalence, exact UE translucency lighting, tangent basis or arbitrary shader graph claim.
- Actual Blender 4.2.4 original M_Worm: 14 editable links, exact packed BC5 normal reconstruction, three raw images byte-identical, variant reuse, color-space and missing-source refusal, injected failure rollback and reopen; zero inherited imports. Original raw catalog regression: 3 profiles/9 images. Python 208 discovered, 197 passed, 11 skipped, zero failed; editor material five cases, cooked geometry and Quinn, original saved levels 449 objects, Western 2814 bindings/36 rigs/14 source textures/10 materials and isolated Linux installer passed. No render comparison, original Goblin or Windows rerun. Four inherited files and 14 literal production sites remain unchanged; no commercial clearance.

Reproduce: `tests/blender_cooked_surface_preview.py` (MATYA_ASSETS, UE_COOKED_SURFACE_OUTPUT), `tests/blender_native_cooked_material_menu.py`, `tests/blender_native_cooked_menu.py`, `tests/blender_independent_material_entrypoints.py`, `tests/blender_native_level_entrypoints.py`, `tests/blender_independent_western.py` and isolated install acceptance. Next prioritize actual legacy replacement, including source-backed saved-map/mesh/material feature parity and shared reference identity; do not count relocating imports as removal. Cooked mesh slot binding to opt-in recovered material preview remains a useful integration gap. Preserve master, rights notices and explicit unsupported statuses.

## 0.10.120 — Native cooked mesh material slot integration

- The primary UE Mesh menu now resolves serialized cooked material slot identities using the native catalog for UE4.18/4.27/5.0 assets inside their project Content directory. Materials on is the default; Allow partial cooked material preview is opt-in. A supported UE4.18 mesh with UV0 receives the bounded 14-link surface graph; other profiles retain dependency-only graphs. No project descriptor, unsupported profiles and materials disabled retain slot identities without attempting material recovery. Missing or invalid material packages get an explicitly unresolved placeholder; missing textures stay reported within the catalog. A per-import resolver shares materials within that transaction; no cross-project material reuse. Polygon indices preserved, unexpected exceptions roll back newly allocated IDs. No cooked map-level integration or Unreal render equivalence claimed.
- Original Matya Worm static and skeletal assets staged under disposable descriptors: six meshes (640 vertices/572 triangles each), three six-bone rigs, two editable UE4.18 preview materials and four dependency-only materials. Packed images and slot assignments reopen correctly. Controlled two-slot alternating polygon indices, cache identity, missing materials/textures, materials disabled and injected failure rollback passed with all inherited modules blocked. These are original asset files, not complete original Unreal projects. Python 208 discovered, 197 passed, 11 fixture-dependent skips, zero failed. Cooked mesh (Quinn 3 LODs/89 bones), editor material (five cases), native saved-level (449 objects) and Western (2814 bindings/36 rigs/14 textures/10 materials) regressions passed; isolated Linux installer tested separately.
- Four inherited files and 14 literal production sites remain unchanged. No commercial clearance, Windows/Goblin rerun, arbitrary cooked material graph parity or intermediate older package decoder. Next prioritize source-backed replacement of the remaining shared reference and explicit compatibility backends; avoid counting relocation, hiding or disabling functionality as replacement.

Reproduce: `tests/blender_cooked_mesh_material_slots.py` with MATYA_ASSETS and UE_COOKED_SLOT_OUTPUT, plus prior cooked menu, editor material, native level, Western and isolated installer regressions.
