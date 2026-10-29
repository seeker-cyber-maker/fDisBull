# Native spatial verification — 29 October 2026

Status: local **0.22.0.dev0 development candidate**, uncommitted source work.
No release tag, publication or shared installation update is implied. The
machine-readable [receipt](evidence/spatial-2026-10-29/verification.json) records
source identities, outcomes and hashes. Licensed resources, states, project
databases, full native traces and game-derived images remain private.

This is the retained development verification snapshot. Version finalization
and subsequent CI are covered by [release verification](VERIFICATION-0.22.md).

## Actual original-game checks

The tested native macOS ARM64 DOSBox executable has SHA-256
`1b0ec91f8a97fb34f336f898c3e9e02bf4559f314b2e4f92f3597f0c52c92277`.
The checks used genuine Python 3.13.17 and its installed native dependencies.
This is not a Linux or Python 3.13.5 qualification of the new candidate.

Each replay copied the supplied game to a fresh private directory, resolved the
live interpreter's object-zero `get.pos` writer, corroborated the actor pointer
and reposition-refresh instruction, and bound observations in the paused session.
State restoration invalidated and re-established the bindings. Original source
files and the private game copy both matched their complete initial manifests
after backend teardown, including removal of the temporary DOS launch alias.

### KQ1 room 1

Interpreter SHA-256:
`5ab189ebd9822739962767afe0113853e23797ef16dd4784d2dc93423934fb74`.
Picture 1 is a 2,752-byte payload in VOL.1 at offset 1,636, SHA-256
`65f0bfee93044b42eaca6ce11c35d8db108d0af79d1d213e78ebf40167fa8258`.
Its complete visual/priority decode uses a 160 × 168 plane; this room does not
exercise brush commands. The six-unit horizontal ego footprint is corroborated
by view-zero cel headers and the observed native actor record dimensions.

The stored map links the picture bytes, a native frame, a pinned scene with
static picture witnesses and a separate composite object-approach zone. It
conservatively excludes barrier, trigger and water pixels, and leaves upper
unqualified coverage unknown. It is not a fully recovered room simulation.

| Probe | Actual result |
| --- | --- |
| Clear route from `(125,100)` | Original walking reached the declared X=144–149 range, stayed at Y=100, and settled with both direction fields neutral |
| Tree approach from `(125,125)` | Original walking stopped at `(127,125)`; the six-unit footprint reaches the first trunk boundary on the next step; classified `blocked_known_boundary` |
| Water landing `(118,150)` | Map excludes it as a hazard |
| Map-aware route from `(106,150)` toward `(125,150)` | `destination_blocked` before the start macro; position stayed `(106,150)` |
| Deliberately unguarded moat diagnostic | Original walking entered a fatal moat sequence and ended at `(122,166)` with the crocodile message; this is a hazard counterexample, not a successful route |
| Upper point `(110,40)` | Remains `unknown` |
| Startup fair play and restore | Physical mode remained locked; assisted travel and story policy were refused after native state restoration |

The successful walking probe uses an explicit target tolerance of three units
and a bounded arrival range. Actual position must still be clear and satisfy
the arrival predicate after stop input settles. An earlier exact-target probe
honestly reported overshoot as incomplete; it was not promoted to success.

### PQ1 room 6

Interpreter SHA-256:
`29ddd3f3b91d65b6eade156608d7915e3c8b7f47701cb226ff119b717f3e8bd7`.
LOGIC 6 has payload SHA-256
`5b83ca6f597788d2a57ed4fd5f5409a7cac4fc91e4dd0b57dc76f1f6222320c1`.
Its immutable code prefix is 2,650 bytes, SHA-256
`b440d760c266e307649022d9bf87271d7ee2a6db7132088ce5cecd8229712da1`.
The native memory binding matched that entire code prefix, not just a fingerprint.

The layout scanner verified all 518 instruction boundaries and branch targets.
At payload offset `0x282`, condition `0b00375c5564` is a non-negated ego position
test: X=55–85, Y=92–100. It computes flag 227. The source GET RADIO branch
(`said` word groups 14/268) checks that flag, then retains its inventory and
character-state conditions. Its original `get(4)` and one-time `addn(v3,2)`
remain guest code. The temporary guard widens only this rectangle to the room,
using `0b0000009fa7`, then restores the original bytes with checked readback.

| Trial from matched checkpoint | Actual result |
| --- | --- |
| Physical action at `(60,120)` | Refused before input as out of reach |
| Original parser command at `(60,120)` | No radio award; score remained 0 |
| Physical action at qualified `(67,98)` | Original pickup completed; score 0→2 |
| Assisted action from `(60,120)` | Qualified placement to `(67,98)`, then original pickup; score 0→2 |
| Story action at `(60,120)` | Original pickup completed; score 0→2 with the same observed X/Y throughout the bounded polls |
| Repeat original pickup after restoration | Score stayed 2; the one-time award was retained |
| Separate player command `take radio` | Same story outcome through a private workflow/projection; public reply included `Spatial policy: story.` and no guard details |

The route types, submits and acknowledges the game's original pickup message.
Submission is held for 250 guest milliseconds in this qualified profile; queue
drain alone was insufficient to guarantee that the message had appeared. This
is a calibrated input sequence for these exact inputs, not general modal detection.

A real score-write watch stopped at original native instruction `0824:72DA`
after its byte write to runtime `0x1219C`. The action reported the debugger stop,
restored its guard and did not run through it. An explicit subsequent 32-event
native trace began at `0824:72DE`; the score continuation retained score 2.
Full traces and frames are preserved in the private replay directory.

## Regression and packaging boundaries

The complete local suite produced **1,429 passed, 104 skipped, 2 failed and 23
setup errors**. Both failures and all setup errors are existing Linux ELF
fixture incompatibilities with the macOS compiler: one fixture emits Mach-O,
another uses an ELF-specific linker setting, and assembler fixtures use syntax
unsupported by the Apple toolchain. The complete local suite is therefore not
green. No new spatial, player, script or context-qualification failure remained.
Ordinary and native Linux CI have not been run for this uncommitted candidate.

Focused regressions exercise mask composition/empty coverage, footprint and
clearance, conditional unknowns, bounded route budgets, immutable restart,
snapshot tampering and version checks, same-room scene changes, input ordering,
nonspatial failure, debugger stops, guard restoration/poisoning, decoded condition
boundaries, rejection of arbitrary execution guards, fair-play restore and
private/public projection separation. Native replays supply the original-game
checks; synthetic tests do not substitute for them.

The source archive builder and archive checker enforce tool-only contents.
Generated distributions and installation smoke receipts remain under ignored
private verification storage. The shared 0.21 installation is unchanged.
Core and standalone-player wheels were installed to a new private target. All
111 tool and five player Python files matched their source bytes. Native PQ/KQ
replays also passed through that isolated package installation; genuine installed
dependencies supplied decoding and images. No replacement dependency modules were used.

## Reproduction and claim ceiling

From a checkout with both the tool and separate player available:

These helpers are checkout-only; tool-only source archives exclude `examples/`.
Use the [tagged AGI example directory](https://github.com/seeker-cyber-maker/fDisBull/tree/v0.22.0/examples/agi),
including `spatial_trial.py` beside `verify_spatial.py`.

```sh
PYTHONPATH=src:player python examples/agi/verify_spatial.py \
  --game pq1 --game-dir /private/licensed/PQ1 \
  --backend /private/tested/dosbox-x --work-dir /private/new-pq-spatial-run
```

Repeat with `--game kq1` and the qualified KQ1 edition. Each work directory must
be new and separate from the source. Keep it outside Git and deliveries. The
helper uses bounded raw backend inspection to qualify its edition-specific
bindings; it is not an autonomous general AGI resolver.

The verification establishes these named actions and boundaries on these exact
inputs. It does not prove whole-room geometry, complete AGI semantics, prevention
of all between-poll hazards, arbitrary-game position-free interactions,
deterministic replay, reverse execution or a fair-play end-to-end campaign.
