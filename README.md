# Blender UE4 Importer
Blender addon to import Unreal Engine 4 asset files. [Download the latest release](https://github.com/Waffle1434/Blender-UE4-Importer/releases/latest).

![image](https://github.com/Waffle1434/Blender-UE4-Importer/assets/8021358/cc2a6f1a-957f-47ad-8f1b-ccce553deb89)
![import_umesh](https://github.com/Waffle1434/Blender-UE4-Importer/assets/8021358/a46d7258-902c-45dc-8d0e-00f106bc34b0)

## Development branch

Current development candidate: **0.10.93-dev**. Objective: direct native UE4/UE5 saved-scene transfer into Blender 4.2.4, with explicit supported profiles and no FBX/USD conversion. Stable branch: `master`; active branch: `development`. [Handoff](docs/HANDOFF.md) · [Project state](docs/PROJECT_STATE.json) · [Roadmap](docs/ROADMAP.md) · [Tests](docs/TEST_REPORT.md) · [Dependencies and installation](docs/DEPENDENCIES.md).

For verified native UE4/UE5 reconstruction profiles, limitations and setup, see [DEVELOPMENT.md](DEVELOPMENT.md). The original upstream feature table below is historical. UE5.6 saved lighting/marker import is an approximate preview, not Unreal rendering parity.

## Features
- Directly reads Unreal Engine project files, no exporting in Unreal Editor required
- Import full `.umap` scenes
- Import individual mesh & material `.uasset` files
- Pixel-perfect material recreation for supported nodes
- Blender equivalent material graph with labels and comments
- Cubemaps & irridance volume placement for Eevee
- [umodel.exe](https://www.gildor.org/en/projects/umodel) for texture extraction
- Normal map format correction

| Saved with Engine | UMap | Static Mesh | Skeletal Mesh | Material | Material Instance | Skeleton | Animation |
| :--- | :--: | :--: | :--: | :--: | :--: | :--: | :--: |
| 4.16 | ✔️ | ✔️ | ⚠️ | ✔️ | ✔️ | ❌ | ❌ |
| 4.27 | ✔️ | ✔️ | ⚠️ | ✔️ | ✔️ | ❌ | ❌ |
| 5 | ❓ | ❓ | ❓ | ❓ | ❓ | ❌ | ❌ |

## Known Issues
- Unreal's binary files are a painful history of microchanges that lead to tons of branching paths that need to be supported. I might be fighting a losing battle. It is particularly hard for me to follow Unreal's source code, I can't promise anything in the future.
- Most testing has been performed on Unreal Engine 4.27 using free assets from the asset store. Assets saved with UE5 *might* work, but its unlikely. UE4 assets should still import into Blender from UE5 projects. If something isn't importing, I might be able to support it if you send a copy.
- Due to their complexity, materials are the most likely to fail to import. The importer will attempt to power through, but nodes may be missing or materials left unassigned.
- Skeletal meshes import as rigid meshes. The vertex groups are correct, getting the correct orientation of the bones is tripping me up so I'm excluding the armature for now.
- BSP and terrain is MIA, I may support this if requested enough.

## UMap Support
| Element | Support | Notes |
| :------ | :-----: | :---- |
| Static & Skeletal Meshes | ✔️ |
| Blueprint Instances | ⚠️ | Only Static Meshes for now |
| Point, Spot, Directional Lights | ✔️ | Eevee 128 light limit |
| Box & Sphere ReflectionCapture | ✔️ |
| Cameras | ✔️ |
| Material Overrides | ✔️ |
| Hierarchy Folders | ✔️ |
| BSP, Terrain | ❌ |

## Material Support
| Node | Support | Notes |
| :--- | :-----: | :---- |
| Add, Subtract, Multiply, Divide | ✔️ |
| Sin, Cos, Tan, Arcsin, Arccos, Arctan | ✔️ |
| Power, Log2, Log10 | ✔️ |
| Frac, Fmod, Round, Ceil, Floor, Truncate | ✔️ |
| Abs, Sign, 1-x, Min, Max | ✔️ |
| Step, Smoothstep, Clamp, Lerp | ✔️ |
| Distance, Dot, Cross, Normalize | ✔️ |
| Constants, Parameters | ✔️ |
| Switch, If | ✔️ |
| Texture2D (& Parameters), TextureCoordinate | ✔️ |
| TwoSidedSign, VertexColor, VertexNormal, WorldPosition, ObjectPosition | ✔️ |
| CameraPosition, CameraVector, CameraDepthFade | ✔️ |
| ScreenPosition, PixelDepth | ✔️ |
| Desaturation, Contrast, BlackBody | ✔️ |
| Append, ComponentMask | ⚠️ | vec1+vec1, TODO |
| MakeMaterialAttributes | ⚠️ | TODO: multiple nodes |
| Transform | ❌ | TODO |
| LightmassReplace | ❌ | N/A |
| Texture3D, BumpOffset, CustomExpression | ❌ | Blender unsupported |
| Material Functions | ✔️ |
| Comment, Reroute | ✔️ |

## Tested Assets
| Asset | Support | Notes |
| :---- | :-----: | :---- |
| [Modular SciFi Season 1 Starter Bundle](https://www.unrealengine.com/marketplace/en-US/product/modular-scifi-season-1-starter-bundle) | ✔️⚠️ | Parallax mapped snow, Blender unsupported |
| [Modular Scifi Season 2 Starter Bundle](https://www.unrealengine.com/marketplace/en-US/product/modular-scifi-season-2-starter-bundle) | ✔️ | Personal favorite |
| [FPS Weapons Bundle](https://www.unrealengine.com/marketplace/en-US/product/fps-weapon-bundle) | ✔️ |
| [Vehicle Variety Pack](https://www.unrealengine.com/marketplace/en-US/product/bbcb90a03f844edbb20c8b89ee16ea32) | ✔️ |
| [Vehicle Variety Pack Volume 2](https://www.unrealengine.com/marketplace/en-US/product/9a705589d1994c6e8757fdbedaf698af) | ✔️ |
| [Military Supplies - VOL.1 - Tents](https://www.unrealengine.com/marketplace/en-US/product/military-supplies-vol-1-tents) | ✔️ | $ |
| [Military Supplies - VOL.2 - Clothing](https://www.unrealengine.com/marketplace/en-US/product/military-supplies-vol-2-clothing-and-bags) | ✔️ | $ |
| [Military Supplies - VOL.3 - Checkpoint](https://www.unrealengine.com/marketplace/en-US/product/military-supplies-vol-3-security-checkpoint) | ✔️ | $ |
| [Military Supplies - VOL.4 - Furniture](https://www.unrealengine.com/marketplace/en-US/product/military-supplies-vol-4-furniture) | ✔️ | $ |
| [Military Supplies - VOL.5 - Devices](https://www.unrealengine.com/marketplace/en-US/product/military-supplies-vol-5-machines-and-devices) | ✔️⚠️ | $, Trailer materials swapped (*why*) |
| [Military Supplies - VOL.6 - Crates](https://www.unrealengine.com/marketplace/en-US/product/military-supplies-vol-6-crates) | ✔️ | $ |
| [Military Supplies - VOL.7 - Containers](https://www.unrealengine.com/marketplace/en-US/product/military-supplies-vol-7-containers) | ✔️ | $ |
| [Military Supplies - VOL.8 - Supplies](https://www.unrealengine.com/marketplace/en-US/product/military-supplies-vol-8-field-supplies) | ✔️ | $ |
| [Twinmotion Construction Vehicles 1](https://www.unrealengine.com/marketplace/en-US/product/twinmotion-construction-vehicles) | ❌ | Compressed (*fml*) |
| [Toolset Collection - Vol 1](https://www.unrealengine.com/marketplace/en-US/product/toolset-collection-vol-1) | ❌ | Compressed (*fml*) |

### Physics asset preview (development)

Select a native imported armature in Object mode, then File > Import > UE Physics Asset — Collision Preview (.uasset). Requires the original referenced skeletal mesh. Editable bone-parented capsule meshes and joint frames are hidden from renders; simulation is not enabled. See docs/0.10.45-physics-preview.md.

### Native vehicle collision previews (0.10.46-dev)

In the Unreal project sidebar, enable **Attach native physics previews** before **Import Native Geometry Folder**. Matching project-local physics assets are resolved from serialized package references. Missing or unsupported physics dependencies are recorded in the gallery report without discarding the mesh. Supports source capsules and bounded UE4.27 unindexed convex hulls with identity transforms. No rigid-body simulation.

### Project batch workflow (0.10.47-dev)

The Unreal sidebar supports dependency preflight and cooperative batch import of selected/all maps or geometry folders. See [workflow and limits](docs/0.10.47-project-batch.md).

### Saved-scene batch recovery (0.10.48-dev)

Refresh the job list, optionally check individual jobs, preflight, then **Run / Resume Batch Import**. Save the .blend after stopping. Completed jobs with unchanged source and settings are reused; stale ownership is blocked. An optional pre-batch recovery copy is available. See [workflow and limitations](docs/0.10.48-project-sessions.md).

### 0.10.49-dev

Selected map geometry imports only known reachable geometry into a resumable gallery. UE5 1012 tagged soft package/object paths and export dependency indices are inspected; Blueprint class ancestry is resolved conservatively. See [development notes](docs/0.10.49-ue5-dependencies.md).

### 0.10.50-dev

Native UE5.0 cooked static meshes, skinned meshes and reference skeletons for the bounded Matya split-package profile. Explicit UE5.0 selection in import menus and project gallery, with native hard dependency inspection. Cooked material graphs and arbitrary UE5 editor/Nanite/IoStore geometry remain unsupported. See [development notes](docs/0.10.50-ue5-cooked-geometry.md).

### Development 0.10.51: modern UE5 cooked assets

Explicit UE5.4, 5.5 and 5.6 static render-geometry profiles, UE5.4/5.6 cooked material-instance parameter recovery, and UE5.5 BC1 texture mip-chain import are now available. These are bounded sample-validated profiles, not general UE5 support. See [acceptance and limitations](docs/0.10.51-modern-ue5.md).

### Development 0.10.52: UE5.6 skeletal mesh

The tested Quinn-style cooked fixed-weight skeletal profile supports all three native inline render LODs. Select UE5.6 and the source LOD (0–2) in the individual skeletal import command; the project browser imports LOD0. See [acceptance](docs/0.10.52-ue5-skeletal-lods.md).

### Shared native skeletal LODs and cooked material dependencies (0.10.53)

Opt-in UE5.6 shared-rig LOD import, manual or user-defined camera-distance switching, and recoverable project batches. Cooked UE5 material dependencies recover exact available UE5.0/5.5 texture images as raw, unconnected nodes; compiled shaders remain unresolved. See [workflow and limitations](docs/0.10.53-shared-lods-material-dependencies.md).

### UE5.7 editor dependency inventory (0.10.54)

Preflight reads the tested tagged 1018 dependency tables, including custom-version-driven UTF-8 soft subpaths. This is dependency inspection only, not native UE5.7 mesh or Blueprint execution support.

### UE5.6 editor source reconstruction (0.10.55)
Original monolithic 1016/1017 static and skeletal source LOD0 MeshDescriptions and root StaticMeshActor placements (including World Partition external actors) are supported for the tested ShooterSam layout. Configure the separately built payload decoder; see [editor source development notes](docs/0.10.55-ue56-editor.md). Editor materials remain unresolved placeholders with original package identities.

### UE5.6 editor textures and material previews (0.10.56-dev)

Native single-layer BGRA8 UEDELTA source textures and bounded editable PBR graphs are now available through the native texture and project browser workflows. Enable **UE5 editor materials** and optionally **Keep incomplete surface previews** for partially translated shaders. Original source pixel/hash checks and material limitations are described in [the acceptance notes](docs/0.10.56-editor-materials.md). The separately built editor payload decoder remains required.

### UE5.6 editor FK animation (0.10.57-dev)

Use **File > Import > Import native UE4.27 / UE5.6 editor animation** with an unanimated native armature selected. The tested UE5.6 editor profile decodes 30 Hz dense single-section FK transform channels into editable Blender Actions. Enable **Allow same-skeleton track subset** only when omitted controls are acceptable. Root motion is preserved as authored local transforms, not evaluated using Unreal extraction or retargeting. See [acceptance and limitations](docs/0.10.57-editor-animation.md).

### Extended editor animation curves (0.10.58-dev)
Dense direct FK tracks now support bounded variable control counts and sparse scalar channels. The native animation operator can optionally apply the source playback-rate multiplier. Source scalar curves become editable object-property F-curves with constant, linear and unweighted cubic segments; no Unreal runtime IK is executed. See [validation and limitations](docs/0.10.58-editor-animation-curves.md).

### Full editor skeleton and authored animation previews (0.10.59-dev)
The native reference skeleton operator accepts tested UE5.6 editor USkeleton assets with full double-precision reference bones, socket definitions and named retarget reference poses. The editor animation operator can explicitly preview additive/retarget-source authored transforms, preserving metadata but not applying Unreal runtime retarget or additive rules. See [acceptance and limits](docs/0.10.59-editor-skeleton-preview.md).

### Saved UE5.6 Blueprint components and live sockets (0.10.60-dev)
Enable **Include Blueprint and skeletal components** in the project browser to reconstruct supported saved Blueprint static components, exact CDO/SCS defaults and attachment hierarchies. Native C++ defaults and construction execution remain unverified; unsupported component instances are reported. Use **UE Create Live Socket Anchors** on a native armature with socket metadata, or select its matching reference armature and make the target active. The available-bones-only option explicitly reports omitted sockets on simplified rigs. See [acceptance and limits](docs/0.10.60-editor-components.md).
Use **File > Import > UE5.6 Blueprint Character Preview** to reconstruct an explicitly referenced character CDO body on a native rig, optionally recovering editor materials and available live socket anchors. This is an authored preview, not native constructor or Blueprint execution.

### Corrected UE5 editor textures and decoder portability (0.10.61-dev)
All 51 inspectable ShooterSam Texture2D source payloads decode with extent-aware restart intervals, including the irregular opaque skull-mask regions. Material previews retain source sampler settings and AO data branches; unsupported engine functions remain explicitly named. A Windows x64 MinGW-w64 CMD helper build and cross-platform payload acceptance script are provided. See [setup, tests and limitations](docs/0.10.61-editor-texture-regions.md).

### Legacy UE5 editor source compatibility (0.10.62-dev)
The three previously excluded ShooterSam object-version 1004 packages now support bounded import-table inspection, original PNG source recovery and material-instance parameter preservation. Legacy summary soft references and procedural grid shader equivalence remain unverified. See [acceptance and limitations](docs/0.10.62-legacy-editor.md).

### Local editor material functions and saved construction components (0.10.63-dev)
Bounded function expansion, shared global parameter overrides and guarded numbered component resolution. See [scope and acceptance](docs/0.10.63-editor-functions-components.md).

For 0.10.85-dev, check map rows and use **Import Checked Levels (Separate)** to transfer independent levels atomically. **Show Selected Imported Level** switches visibility within the imported set. The per-level report includes saved partition ownership; this does not evaluate Unreal streaming or level-instance transforms. See [details](docs/0.10.85-level-sets.md).

For 0.10.86-dev, unified UE5.6 saved-level transfer preserves supported inline additive/subtractive BSP brush operands in a separate non-rendering wire collection. The source polygon vertices, saved transforms and CSG roles are editable; they are not the compiled BSP result and are excluded from reconstructed scene mesh counts. See [details](docs/0.10.86-brush-operands.md).

0.10.87-dev imports supported saved compiled BSP polygon buffers with original surface/lightmap UVs and source render normals, plus non-rendering editable original volume bounds. [Details](docs/0.10.87-compiled-bsp.md).

0.10.88-dev preserves the complete finest-mip source landscape RGBA atlas, derived texel-center corner UVs, component face IDs, and saved component material instance ancestry. [Details](docs/0.10.88-landscape-atlas.md).

0.10.89-dev adds bounded operation-local UE5 package table reuse, per-stage timings, synchronous progress and actionable source dependency reports. [Details](docs/0.10.89-workflow.md).

0.10.90-dev adds exact-identity missing source recovery, automatic visible anchor selection, level-local repair overlays, between-map atomic cancellation and adjustable package cache memory budget. [Details](docs/0.10.90-source-recovery.md).

0.10.91-dev reduces temporary terrain allocation, excludes validated saved-map redirectors from the world selector, and includes an all-original-map acceptance harness. [Details](docs/0.10.91-landscape-memory.md).

0.10.92-dev prioritizes the direct level import controls, retains advanced tools in collapsible sections, and validates actual Linux desktop clipboard, modal cancellation/retry and source restoration confirmation. [Details](docs/0.10.92-desktop-workflow.md).
