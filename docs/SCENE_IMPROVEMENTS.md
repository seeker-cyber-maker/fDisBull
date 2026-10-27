# Scene improvements — 0.18.0

The [release notes](RELEASE-0.18.0.md) distinguish development verification,
the exact-commit Linux gates required before tagging, and later publication.
The existing [scene contract](SCENE_FRAMEWORK.md) still governs availability,
geometry, ambiguity, real input and bounded debugger stops.

## One observation, one capture of each memory range

All predicates in one paused observation share reads by normalized project
linear address and exact length, including equivalent segment:offset spellings.
Different lengths remain separate reads. This applies to scene competition,
visibility, readiness, enabled conditions and outcomes. Failed captures are
also shared, and remain unavailable evidence. `read_statistics` records predicate
read evaluations, unique reads and cache hits; `memory_captures` records each
range once and predicate evidence points to those captures. Typed baseline
capture/evaluation also contributes to these counters.

The cache ends with the observation. The next check, action or wait poll reads
again. A second frame/context probe still rejects observations spanning different
native frame, mode or state revisions. No availability cache survives input,
camera movement, code layers, checkpoint restore or a new session.

## Compact replies, retained evidence

```python
result = debug.scene_check(revision, object="office.bank", compact=True)
full = project.debug_scene_observation(result["observation"])
```

`compact=True` is opt-in on check/assert/wait/click/act, their scene handle APIs,
JSON methods and saved-script operations. It omits repeated predicate evidence,
memory payloads, RGB samples, individual polls and baseline values from the
reply, while retaining counts, status, completeness, availability, conflicts,
stop/input identities and diagnostic references. The full result is persisted
before presentation. Failures use the same option through `SceneError.result`.
Retrieval is explicitly historical; it never certifies current guest state.
Existing clients receive full replies by default.

## Relative outcomes

An action can require a counter to increment without a new literal definition
after each successful operation:

```json
{"compare":{
  "left":{"memory":{"address":"0x471ac","type":"u16"}},
  "op":"eq",
  "right":{"add":[{"before":{"memory":{"address":"0x471ac","type":"u16"}}},1]}
}}
```

This is a schema example, not a verified DinoPark purchase route. Scalar memory
types are `u8/i8/u16/i16/u32/i32/u64/i64`, with explicit `endian` (`little` by
default, or `big`) and optional `cs`. Relations are `eq/ne/lt/le/gt/ge`.
Expressions support integers, current typed memory, `before` typed memory,
two-operand `add`/`sub`, and `wrap: {type, value}`. Arithmetic is mathematical;
wrapping and signed interpretation are explicit, never inferred C promotions.

`before` is allowed only in an object or popup-handler outcome. The runtime
captures required values before sending input and binds them to run, byte
version, scene revision and frame/state identity. Every action captures a new
baseline, including after checkpoint restoration. Polls retain that baseline.
Before and current values remain in the full observation. Missing captures are
incomplete, including inside `any` with another true operand. The existing
initially-false postcondition check still prevents credit for a prior outcome.
Use `all` to combine relative state evidence with independent destination pixels.

## Portable scene bundles

```python
project.debug_export_scenes([office_revision, bank_revision], "office-scenes.zip")
result = other_project.debug_import_scenes("office-scenes.zip")
new_revision = result["scene_map"][office_revision]
```

Bundles contain only `manifest.json` and hash-named clean PNG snapshots.
References, aliases, composite masks, contexts, original bounds and origin
authorship are retained; local artifacts, scene revisions and object IDs are
remapped. Import returns all three ID maps. Origins are bundle provenance, not
authenticated assertions about who authored the input.

Compatibility requires the same original source hash, format, architecture,
bitness and complete mapped-byte-view hash (including region addresses and
permissions). A different load segment or patched version is rejected; automatic
rebasing is not implemented. Target object names must be unused. Import never
overwrites a local scene, launches an emulator or performs input. Imported
snapshots are historical; a live action requires fresh scene recognition.

The importer checks member names, counts, expansion budgets, hashes and PNGs,
rejects extra payloads, and rolls back the complete import if a later definition
is invalid, including inside a caller's transaction. Maximums are 64 scenes,
1,024 snapshot records, 4 MiB manifest, 16 MiB per PNG and 64 MiB total. Game
files, native states, databases, arbitrary files and executable extension modules
are outside this format.

CLI equivalents are `debug-export-scenes PROJECT OUTPUT SCENE...` and
`debug-import-scenes PROJECT BUNDLE`. JSON methods use the Python keyword names.

## Numbered overlays

```python
overlay = project.debug_scene_overlay(revision, labels="numbers", grid_step=8)
project.debug_export(overlay["artifact"], "office-numbered.png")
project.debug_export(overlay["legend_artifact"], "office-legend.json")
```

Names remain the default. Numbered labels reduce crowding and have a stored JSON
legend linking marker, persistent object ID, name/aliases, point and area hash.
Markers follow object order within that exact revision; they are not permanent
identities across a reordered manifest. The overlay, legend and action all use
the same saved geometry. Calibration and recognition use clean source frames.

See [the DinoPark verification record](VERIFICATION-SCENE-IMPROVEMENTS.md) and
[replay driver](../examples/dinopark/verify_scene_improvements.py). The separate
[content/engine/player proposal](GAME_CONTENT_AND_PLAYER.md) describes later
script-language recognition and adapter work; it is not an implemented engine.
