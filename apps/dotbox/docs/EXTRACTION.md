# Extraction boundary and provenance

The independent engine uses the smaller persistent-play branch at
`59dc4d7ae24e666358a96db9c4acc1789ded5cf8` as its starting point. The original
lead checkout, its uncommitted AGI/walking/HUD experiments and the prior draft PR
remain preserved. A private 119-file source snapshot with hashes was captured
before this extraction. No commercial game data was copied into the repository.

## Reused working components

| DotBox component | Source and treatment |
| --- | --- |
| `native_rpc.py` | Existing fDisBull DOSBox JSON-lines transport, owned process cleanup and protocol checks; extracted with local launch-profile imports. |
| `native_session.py` | DOS-only launch, source attestation and cleanup responsibilities extracted from DebugSession; no Project, analyzer or code database. COM/MZ entry checks are explicitly bounded samples. |
| `screenshot_codecs.py`, `operation_budget.py` | Existing screenshot validation and nested RPC deadline machinery with local imports. Pillow remains a declared dependency. |
| `keyboard_input.py`, `input_macros.py`, `local_auth.py` | Existing keyboard/macro bounds and private credentials, reduced to standalone operations. |
| `backend.py`, `service.py`, `client.py` | Existing persistent-play facade and ownership guards, adapted to the local runtime/store. |
| `harness.py` | Existing immutable keyboard and absolute-mouse control semantics, now backed by the independent store. |
| Native agent base and ownership overlay | Exact pinned working DOSBox-X patches, manifests and GPL notices; DotBox owns preparation without an fDisBull checkout. |

Extracted modules identify their original source path and commit. Python
transport/session/screenshot/budget provenance is fDisBull integration
`9853c99952c2c0b77f2d9e33f99a05f0a242882b`; native base/input-validation
provenance is `ce91c303f2fccd1db9b1e3917ecc8c98473bfdb9`. These are source
identities, not a claim that upstream release qualification transfers to DotBox.

## Deliberate boundary changes

The new store contains executable identity, one original-source version and
immutable authored controls. It stores no mapped executable bytes, proof state,
static analysis or debugger history. Both source and version hashes bind actual
original executable bytes. Old FDB mapped-version identities are not invented
or silently migrated. Existing FDBs are refused before writes; original files
remain usable by their original tools. Legacy keyboard document syntax and the
canonical control-manifest hash scheme remain supported.

Normal desktop input belongs to the outer Codex/WebRTC harness. DotBox enables
the native host input path for both Dot and user desktop events and refuses
parallel direct input/play/pause RPCs. It reports the current outer owner as
unknown. The explicit `--manual-control` diagnostic mode verifies native host /
agent transfer and cleanup without claiming platform event integration.
Execution RPCs lack an atomic ownership parameter; guarded auto-resume rechecks
stop and ownership under the single-native-controller contract.

## Deferred work

The initial standalone extraction did not add an AGI reader or pathfinder. The
`0.1.0.dev5` continuation below adds a bounded static census and offline route
proposals; it does not add an interpreter, live engine-state adapter, movement
executor, rewind command, game route, HUD or audio transport.
Actual Dot cloud deployment, the supported
outer ownership event/provider, Windows support, broad game qualification,
portable native library bundling and release publication remain separate checks.
The native executable used for acceptance is the existing matching build; this
change verifies standalone source preparation and does not claim a fresh native
compilation. No global installation was replaced.

## AGI and navigation continuation — 17 November 2026

The installed fDisBull 0.34.1 package supplied the small reusable modules below.
All six original file blobs were checked against tag commit
[`011f1b8cb281edda208026aee9cdb238b800b2d7`](https://github.com/seeker-cyber-maker/fDisBull/tree/011f1b8cb281edda208026aee9cdb238b800b2d7).
Original source paths use the `src/fdisbull/` prefix. These hashes identify the
original bytes before the documented local extraction changes.

| Original file | Original SHA-256 | Treatment |
| --- | --- | --- |
| `agi_resources.py` | `a2d0cfa228279d4234211487eec81f9daccfe8c9e455ec4be9f5b886a833ea11` | Retain cached uncompressed V2 readers; remove an unused analyzer-side import; bound shared expanded text work and aliases. |
| `agi_layout.py` | `4c81c70c000128141c964cb29a913ded5e9e1a05d9ff1622e9c580afbbf94edb` | Retain ordered layout parsing; enforce its work bound before further decoding; refuse disputed high-bit IF displacements. |
| `agi_scenes.py` | `bb2833c63082204945c79cef2d83239b25b5eb9055cc747f505432de12a54d48` | Retain the census format and finite-value analysis; account for attempted decode work, shared text and bounded report serialization. |
| `spatial_map.py` | `878344201690fb076ffc15f6ab28d86810490c1e6222fc4d7d8f388020ec245f` | Retain geometry/footprint contract; remove Project/FDB persistence and source-verification dependencies; use bounded heading-aware A* and portal exclusion. |
| `scene_geometry.py` | `b742795f9fc4994793d20b87732f0bec562749247f2d31f29832e79ef1d9b30d` | Retain pure geometry validation helpers. |
| `scene_domains.py` | `b37200848be4f2ccaeadb984780e5d33ce3d69c7b8ba16f0743ebd02f02736ca` | Retain only optional coordinate-domain validation and its helpers; omit the broader audit surface. |

The new `agi.py` supplies the narrow private-report CLI and authored self-check.
The new `navigation.py` binds route proposals to supplied scene/state, preserves
long collinear legs and rechecks canonical proposals. It does not import a second
live controller. Existing fDisBull controller, frame timeline and full-state
checkpoint implementations were studied as integration references. Their raw
mutation and lifecycle policies were not copied into the DotBox public API.

This is first-party reuse requested by the project owner. The pinned
[fDisBull README](https://github.com/seeker-cyber-maker/fDisBull/blob/011f1b8cb281edda208026aee9cdb238b800b2d7/README.md)
states that no first-party distribution license has been selected; public
visibility alone does not grant an open-source license. This continuation does
not assign an MIT, GPL or other new license to those Python modules. Original
format-research references remain in their headers. The native DOSBox-X GPL
notices and source obligations are separate and remain included unchanged.

The full analyzer, database, native source writer, AGI interpreter, live memory
adapter, original-game save parser and commercial resources are not dependencies
of the new reader. Additional required third-party dependencies were not added.
The geometry path uses the already-declared Pillow dependency. Read
[engine-aware preparation](ENGINE_AWARE_PREPARATION.md),
[navigation](NAVIGATION.md) and [recovery](RECOVERY_AND_SAVES.md) for the capability
boundaries; prior fDisBull qualification does not qualify DotBox live behavior.
