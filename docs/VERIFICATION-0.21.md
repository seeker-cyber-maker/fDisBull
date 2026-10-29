# fDisBull 0.21.0 verification

Finalization date: 28 October 2026. Local host: macOS ARM64, Python 3.13.17.
The source version is **0.21.0**, based on
`ce9dc5e73b6a780fa1bc6dc6601c83e05b90638f`. Ordinary and native Linux CI must
pass on the exact committed release source before tagging. This preparation
record does not claim that those remote gates have already completed.

## Original-game verification

[Machine-readable evidence](evidence/0.21.0/native-transfer.json) records private
PQ1 and KQ1 trials, source identities, measured observations and artifact hashes.
The replay is `examples/agi/verify_progressive_text.py`; it requires the user's
licensed game files, a tested backend and a fresh private work directory. No
executables, original resources, checkpoints or project databases are included.

The tested native backend SHA-256 is
`1b0ec91f8a97fb34f336f898c3e9e02bf4559f314b2e4f92f3597f0c52c92277`.
It is the existing layers backend. This release adds Python controllers rather
than claiming a newly built Mac emulator.

| Matched within-room task | Walking median wall time | Placement median wall time | Walking / placement guest progress |
| --- | ---: | ---: | ---: |
| KQ1 room 1, X 129..131, Y 100 | 828.5 ms | 237.6 ms | 2,060 / 145 ms |
| PQ1 room 6, X 79..81, Y 120 | 871.0 ms | 238.9 ms | 2,130 / 125 ms |

Each cell summarizes three trials from the same native checkpoint, using the
same text resolver and target range. Both the actor direction and the game's
latched control direction must be neutral. Post-restore preparation is outside
command timers. Host load is uncontrolled. These warm, authored route figures
are not an autonomous-discovery or whole-game benchmark and do not compare the
complete start-to-bow task with Dot's reported 49 seconds.

The final room contracts are independently declared landing ranges:

- **PQ1 room 6 to 5:** X 20..24, Y 130, both direction values zero. Walking
  settled at X=21; assistance at X=22 in the recorded run.
- **KQ1 room 1 to 8:** X 0..4, Y 100, both direction values zero.

Assistance places the actor at a qualified portal, then uses original keyboard
input. It never writes the declared room byte. A conditional, once-only cleanup
press stops surviving latched movement. The final `destination_scene` check
requires a complete displayed match as well as the memory outcome. The source
and destination PNGs differ in both games. Destination recognition includes
pixels sampled from the observed visual difference. The ordinary destination
is checked again after two newly completed frames before it supplies a reference.
These checks qualify the bounded route, not all controls or every possible modal.
The within-room placement also sets the engine's position-refresh flag while
preserving the other bits. Its meaning is corroborated by the original adjacent
reposition handler (`81 4D 25 00 04`) and an actual native redraw probe. Both
within-room PNGs differ from their baselines, and the completed frame matches
the observed actor position. Changing coordinates alone had left the old sprite
on screen in an earlier private probe.

### Correction found during finalization

The first development PQ route accepted the room byte changing while the actor
still had the old coordinates `(143,150)`. Its baseline and jump PNGs were
identical. A second probe reached `(20,130)` transiently, but after two frames
moved to X=24 with actor direction 3: actor direction zero alone had not proved
that the game stopped. Those captures are diagnostic, not completed-room proof.
They remain preserved in private recovery evidence; the repository's corrected
corpus contains the final render-qualified replay.

The verifier now observes the control-direction byte as well. Its semantic
name follows [ScummVM's AGI variable definitions](https://github.com/scummvm/scummvm/blob/master/engines/agi/agi.h),
while its DOS address comes from the observed `get.pos` variable-array mapping;
a host-side ScummVM structure is not used as a DOS-memory address. The corrected
ordinary and assisted routes remain inside their declared ranges, neutral after
further frames, and show the destination. This is why matching an early room
number is insufficient.

### Shared implementation and isolation

The same workflow, player, projection and travel API serve both games. Hashes,
bootstrap keys, qualified waypoints and landing contracts are content-side
recipes. KQ's original COM launcher loads its interpreter; the runtime writer is
located after launch instead of applying PQ static addresses to KQ.

Menu and stale-context probes withhold input without guest progress. Resource
inventory checks also withhold actions after a relevant file changes. Restoring
the original resource bytes requalifies the same source contract. Native states
invalidate runtime bindings, which are explicitly recreated and verified.
Original and final working game manifests match.

The independent player and host are also exercised in separate processes. The
client environment contains no fDisBull module; original execution remains on
the host. Explicit post-restore guest preparation creates a fresh framebuffer
and reports measured guest time. A passive text observation does not advance it.

## Automatic turn persistence and story protocol

The installed core and independent player wheels passed
[`verify_live_turns.py`](../examples/agi/verify_live_turns.py) on both games.
Each game used three fresh host/client process pairs. The first model turn
selected within-room assistance and a qualified room exit, then checkpointed
automatically without a save command. The second process pair bootstrapped the
original baseline, restored that checkpoint, and observed the neighboring room.
The third restored again and ran an external scripted agent that narrated its
choice, selected `look`, recorded the actual outcome and checkpointed.
The [public receipts](evidence/0.21.0/live-turns.json) include checkpoint IDs and
outcomes; native state artifacts and private project contents are excluded.

This verifies the external agent protocol with an authored fixture, not an
autonomous LLM playthrough. The standalone authored runtime separately exercises
new-process restore of inventory, context, state, ticks and events. Regressions
cover corrupt/incompatible refusal, partial-effect persistence with no following
command dispatch, stop preservation, failed saves and agent deadlines. A native
synthetic restart also restores an owned watchpoint and runtime memory binding.
Every captured binding is revalidated after fresh-frame preparation. A failed
restore blocks all projection handles on that debugger session.

Live checkpoints use native experiments and retain their debugger controls, but
do not roll back mounted host files. Changed resources or unknown scenes fail
qualification rather than silently starting a new game. Voice input/output is
planned future work; Qwen TTS is available locally according to the user, while
speech recognition and combined interaction remain unqualified.

## Local native tests and release gates

The final local native selection passed **530 tests, zero failures/errors/skips**,
in **76.729 s**, using the layers matrix plus the source-companion regression.
The existing development environment supplies declared test dependencies,
including setuptools. The shared runtime installation was not changed.

Local native log SHA-256:
`fdfd34485064c53021911e2ab6e0141a10682a7f84cea39a2e923e0ac13ea4b8`.
JUnit SHA-256:
`78958fdb9bcb2ac68ead241a965997be8454aafc23b236f03e4b3f1b79f38d45`.
The private logs are in the `release-0.21.0/mac-live-final` recovery directory.

The earlier full ordinary Mac attempt reported **1,277 passed, 103 skipped,
2 failed and 23 setup errors**. The failures concern Linux ELF fixtures: this
host produces Mach-O or rejects GNU linker options. They are not a green Linux
result. The ordinary and required native Linux workflows are separate release
gates on the final pushed commit, including both DOSBox profiles, installed-wheel
unified backend tests and the offline kit with genuine Z3 and the separate player.

## Packages and evidence

Core and player are separate, matching-version wheels. Source distributions and
the tool ZIP include the independent player source through explicit whitelists.
Archive checks reject game/state/database files and foreign player-wheel roots.
Repeated player builds were checked after preserving an older generated build
tree outside the checkout. Byte-reproducible wheels are not claimed.

The offline kit and corresponding-source notice derive their release version
from project metadata. The source companion archives only the pinned upstream
Git tree and verified patch overlay. No publication or shared-system activation
is implied by this release preparation.

Repository images and traces are derived native observations. Trace copies
replace only local backend/game paths; private originals remain intact. This
corpus is repository evidence and is omitted by tool-only package whitelists.

- PQ1: [baseline](evidence/0.21.0/pq1-baseline.png),
  [placement](evidence/0.21.0/pq1-within.png),
  [completed room jump](evidence/0.21.0/pq1-jump.png),
  [menu refusal](evidence/0.21.0/pq1-menu-blocked.png),
  [trace](evidence/0.21.0/pq1-verified-original-trace.json).
- KQ1: [baseline](evidence/0.21.0/kq1-baseline.png),
  [placement](evidence/0.21.0/kq1-within.png),
  [completed room jump](evidence/0.21.0/kq1-jump.png),
  [menu refusal](evidence/0.21.0/kq1-menu-blocked.png),
  [trace](evidence/0.21.0/kq1-verified-original-trace.json).

The [release notes](RELEASE-0.21.0.md) and [implementation scope](UNRELEASED-0.21.md)
retain the limits: no complete AGI/UIL runtime, full-game reconstruction,
arbitrary jumps into unknown rooms, deterministic replay or whole-world equivalence.
