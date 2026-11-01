# Source-linked AGI diagnostic Z scene

For a scene exported from ordinary gameplay, use the
[normal goat encounter replay and exporter](AGI_NATURAL_GOAT.md), with the
[troll-bridge continuation](AGI_TROLL_BRIDGE.md) as a third guarded action. The example
below preserves the earlier independent diagnostic probes and their limits.
The [qualified lake routes](AGI_GOAT_BRANCHES.md) add regular water refusal and
room-exit retirement, and explain why the diagnostic invisible-wander branch
has no normal-command witness under the recovered guards.
The [mushroom-island route](AGI_MUSHROOM_CROSSING.md) adds an independent
three-action scene with a native river crossing, physical approach and
source-bound score/inventory pickup. It uses authored responses and the same
separate player, with explicit partial-coverage and checkpoint limits.

`examples/agi/build_z_scene.py` creates a private, partial Z scene from the
owner's KQ1 AGI 2.917 logic 103 and the checked-in diagnostic host receipt. It
checks the source resource identity and instruction bytes at offsets 413, 427
and 450, extracts messages from the source, and requires the matching completed
native print and erase cases. It also hashes the private erase trial against the
receipt and checks object 13's native drawn flag before and after offset 427. It exports a separate provenance record binding
the scene hash, source identity, offsets, cases and a canonical JSON receipt
hash. The original messages and generated scene must remain private.

```sh
PYTHONPATH=src:. python examples/agi/build_z_scene.py \
  --source /private/kq1 --receipt docs/evidence/agi-branches-2026-10-31/receipt.json \
  --erase-trial /private/native-erase/trial.private.json --output /private/new-z-scene
PYTHONPATH=src:player python -m fdisbull_player --backend-command \
  "python -m fdisbull.il_scenes /private/new-z-scene/scene.json"
```

The scene starts with the diagnostic object 13 drawn flag set. The departure
probe clears that flag and refuses a repeated action; the water probe does not
change it. This state models the recorded flag transition, not sprite visibility.
The in-memory scene checkpoint does not survive a new process.

The scene offers two independent probes, `use water` and `use departure`, through
the separate Z player and shared IL scene backend. These are authored investigation commands, not claims about the original
parser. They display source message resources; the latter includes an authored annotation of the observed object 13
erase. The private source and native receipt are checked at **build time**;
the standalone scene is not a live binding and cannot itself revalidate them.
The two probes do not model a player route, a general AGI interpreter, or a
sequence of native calls. The erase used a second deliberately prepared native
invocation. The receipt reports handler returns, not visual verification of the
print, and does not establish ordinary reachability. The separate
[native qualification](AGI_NATIVE_COVERAGE.md) now exercises blocking dialogue;
this scene binds the checked diagnostic receipts and performs no automatic
native execution.

Run the portable tests with `python -m pytest -q tests/test_agi_z_scenes.py`.
Set `FDISBULL_KQ1_SOURCE` to the owner's private game directory and `FDISBULL_AGI_ERASE_TRIAL` to the private native
trial to additionally exercise real source decoding and receipt binding. This is a separate authored
projection; it is not a replacement for the native backend or full-game recovery.

To produce a hash-only player receipt without exporting message text:

```sh
PYTHONPATH=src:player python examples/agi/check_z_scene.py \
  /private/new-z-scene/scene.json --output /private/new-player-check.json
```

The receipt exercises the commands, the drawn-flag change, repeat refusal and
an in-memory save/load. It does not claim restart persistence.

## A connected clover-and-diamonds cave slice

The [leprechaun-cave example](AGI_LEPRECHAUN_ROUTE.md) uses a fresh ordinary-input
preparation and a separate seven-action scene. Its exporter checks all eight
recorded anchors, carried inventory, score changes, completed source messages
and the original shield writer/return trace. It rejects missing, extra or
contradictory evidence before emitting the authored projection.

The text actions are `use hole`, `use bag`, `use tunnel`, `use rat`, `use throne`,
`take shield` and `use exit`. They update the declared projection; they do not
issue native calls or run an AGI interpreter. The final scene still needs its
private original inputs at build time. Exported scene text is authored, and
checkpoint checks cover in-memory restoration and token invalidation.

## A checkpointed gnome, tree and chest segment

The [gnome/key and giant's chest example](AGI_GNOME_GIANT_ROUTE.md) starts from
the prepared shield checkpoint at score 14. Its resume command copies the
project, performs one supported native restore, verifies the saved CPU and
initial state, and records all eight actions in a single subsequent session.
The capture declares `fresh_game: false` and its checkpoint-load intervention;
no observations from different runs are spliced.

The exporter binds the donor capture/result, checkpoint hash and time, CPU,
source identities, completed messages, inventory writers, original handler
returns and command-time distance observation. It rejects missing or
contradictory evidence. It emits `use trail`, `use gnome`, `take key`,
`use tree`, `use door`, `use stairs`, `use giant` and `take chest` into the
separate player, guarding all 40 projected state fields plus the phase.

This is an authored partial projection of observed outcomes. Movement and
NPC timers remain outside that model. The native segment uses original
keyboard input after the declared restore; the text actions update the
projection. A separate cold-start attempt failed in the rat preparation and
remains a failed observation. Model checkpoint checks cover in-memory restore
and token invalidation, with no inherited checkpoint in a fresh process.

## A fresh well, dragon and mirror segment

The [dragon and mirror example](AGI_DRAGON_MIRROR_ROUTE.md) starts from the
original game's fresh room 1, acquires the dagger and bucket, descends the well,
uses water, takes the mirror and returns to room 22 at score 28. It records
eight actions in one native session, exports two private diagnostic checkpoints
and performs no state loads. The earlier incomplete attempts remain separate.

Its exporter requires all nine main boundaries, water and mirror launch
observations, completed messages, native inventory/score writer evidence,
original handler returns and two separately framed repeat controls. Original
PIC52 priority classes explain why the physical flag-0 observation is false at
the recorded underwater pose. Missing, extra, contradictory or incomplete
captures are rejected before a scene is emitted.

The authored commands are `take dagger`, `take bucket`, `use rope`, `use water`,
`use passage`, `use dragon`, `take mirror` and `use exit`. Every edge checks
44 typed native fields and its phase before applying the declared changes.
They consume an authored partial projection; they do not operate DOSBox or
simulate AGI's autonomous movement, air counters or enemy timing. The original
source, native captures and generated scene/provenance stay private. Player
qualification checks direct and separate-process use, all nine boundary states
and inventories, stale/repeat refusal and in-memory checkpoint behavior.

The exporter also automatically annotates the active dragon object/context
with a [derived last-row exception](AGI_BOUNDARY_EXCEPTIONS.md). A reusable
auditor derives terminal complement bands from declared point rectangles;
the AGI adapter obtains the original predicate and matching negation from
source. The diagnostic preserves all eight actions and 44 fields plus phase.
Its independent restored-checkpoint pair is separate from the fresh route,
and the scene does not gain arbitrary walking or a silently altered action.
