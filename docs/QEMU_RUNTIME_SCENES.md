# Passive QEMU runtime scenes

`QemuDOSProcessSession.scene_check(scene, *, object=None, compact=False)` and
`scene_assert` accept an explicit `fdisbull-scene-2` runtime-memory observation
profile. This is a separate passive contract. It does not qualify the existing
frame-backed scene campaign, grant completed-frame identities, or change the
default DOS backend.

```json
{
  "format": "fdisbull-scene-2",
  "observation_profile": {"kind": "runtime-memory", "version": 1},
  "context": {"state": "authored key released", "triggers": ["guest IRQ1"]},
  "match": {"runtime_memory": {"binding": "scene-state", "offset": 8, "length": 1, "hex": "00"}},
  "objects": [{
    "name": "actor",
    "context": {"state": "observed actor state", "triggers": ["explicit byte witness"]},
    "visible": {"constant": true}, "ready": {"constant": true},
    "enabled": {"constant": true}, "outcome": {"constant": false}
  }]
}
```

Save it with `Project.debug_save_scene`. Storage supplies the actual original
source hash, selected byte-version ID/hash and stable object IDs. Each read
revalidates the canonical manifest hash, its source identity, and object ownership.
A revision chain cannot switch between scene-1 and scene-2. Existing scene-1
storage defaults and its screenshot/evidence requirements are unchanged.

Predicates support constants, `all`, `any`, `not`, runtime-memory byte/mask
comparisons and typed scalar `compare` expressions with integers, `add`, `sub`
and `wrap`. Every branch is validated. Source-address reads, pixels, engine
references, `before` baselines, actions, geometry, navigation, handlers and
coordinate domains are rejected. A profile requires at least one explicit RAM
reference. Limits are 1 MiB per definition, 64 objects, 4,096 expression/predicate
nodes across the selected scene and all competing matches, depth eight, 64 KiB
combined distinct requested RAM extents, 64 candidate scenes per exclusive group
and 256 stored scene roots per selected version. Runtime capture receipts are
bounded to 256 unique reads and 4 MiB; predicate evidence, including repeated
cached reads, is bounded to 1 MiB. Every predicate checks the inherited wall
deadline. The first failed read or exhausted limit stops evaluation and prevents
further native reads. Its result is unavailable/incomplete; an expired deadline
preserves partial evidence on the exception without late publication.

Binding names or IDs in a saved scene are references, not capabilities. The caller
must first bind the actual live RAM with an explicit expected-byte witness. Full
restore advances the runtime epoch; the saved scene remains inspectable, but its
old RAM binding is unavailable until an explicit fresh witness is admitted.
These bindings do not infer task ownership, allocation lifetime or source mapping.
Selected CPU/RAM undo similarly invalidates bindings whose frozen-state identity
changed. A fresh permitted read-only witness can inspect the frozen state.

The adapter requires the explicit native virtual-clock profile and a stopped
single-vCPU owner. One owner, restore epoch, lock and inherited host deadline cover
all RAM reads and persistence. CPU/address context and the native virtual clock
must remain unchanged across a completed observation. A failed early observation
has `capture_context_verified: false` and no claimed final clock bracket. It performs no guest execution,
input dispatch, frame capture or RAM mutation. Existing leases remain untouched.

Results use `fdisbull-scene-observation-2`, include `observation_profile` and
`completion_scope: "declared-runtime-predicates"`, and omit `frame`. The shared
status meanings remain `matched`, `mismatch`, `ambiguous` and `unavailable`;
`complete` is true only for matched/mismatch within this declared profile.
`scene_assert` raises `SceneError` unless matched. Both methods persist the exact
observation in `debug_scene_observations`; compact replies retain the observation
ID for retrieving full evidence. Saved observations are historical, not fresh
authority. A late publication timeout preserves any already committed receipt.

The saved-script operations are `scene-check` and `scene-assert`. Every known
literal is validated before earlier script effects; a result reference defers
only its own unknown scalar value and is revalidated at actual dispatch. Whole
scene references cannot prove unknown content during script admission.

Frame/action consumers reject this profile, including ordinary `SceneHandle`,
click/act/wait/navigation, movement scene contexts, assisted travel, spatial map
contexts, workflow actions and text projections. Screenshot overlays, coordinate
domain audits and scene-1 bundle import/export also refuse it. QEMU exposes no
generic scene handle or action methods through this extension.

Host contracts are exercised in `tests/test_qemu_scenes.py`; native optional
witnesses in `tests/test_qemu_scenes_native.py` use the authored IRQ1/BIOS-tick COM
fixture to observe real make/break state and full native restore invalidation.
Those native cases require the existing explicitly selected private QEMU runtime,
FreeDOS boot image, firmware, mcopy, NASM and checkpoint tool. Authored tests are
not evidence of execution until a pinned receipt records their run.
