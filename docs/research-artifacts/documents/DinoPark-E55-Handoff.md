# DinoPark E55 continuation

## Current outcome

The current artifact is E55. Start with `REPORT.md`, then
`docs/GAME-STORY-MAP.md` and `research/uil-input/ABOUT-STORY.json`.
The user wants the game's behavior recovered independently of implementation
language, ready to rewrite in **Universal Interaction Language**. Preserve
that objective; do not start a competing UIL grammar or claim these research
JSON files are canonical UIL.

The existing fDisBull UIL boundary and interface RFC were retrieved read-only
at heads `bdebd9d877c2402722130fc6b1254fd54ef7bda0` and
`82ab246c7e4e6959957329f2b564c7db45c7f2c6`. Both were proposals at retrieval,
and the second was draft. Their owner still determines canonical grammar,
serialization and evaluator. No remote writes/comments were made.

## Newly established

- ABOUT.ACT: one 74-byte program, 20 instructions, 14 opcode values. It is
  supported by the typed `ACTRuntime` alongside the unchanged DinoMart subset;
  the union is 16 opcode values across nine selected programs.
- Fresh original ABOUT actor comparison: eight profiles, 1,059 ticks, 982
  draws, complete 234-byte actor records and 64-byte signals, zero mismatches.
  Draw/pump remain authenticated adapters; no actual ABOUT pixels claimed.
- Native host: 83 unique calls across init, shared init, navigation and UI
  reset; all DS bytes and ordered writes checked, no adapters. Shared init
  clears 32 signal words then calls 3619:0EE5, which assigns signal 0 = 1.
  Those routines preserve all 16 actor records. Full page-service preservation
  is not established.
- Connected host/actor fixture: six original initializers feed the same actor
  for 190 ticks/189 draws; native bank is not replaced before actor updates.
  Writes during a running sequence coalesce in the latch; they do not enqueue
  another gesture. Fixture event times are not recovered physical timings.
- Current DinoMart runtime replays all 2,491 retained E54 original inputs and
  13,718 draws. These are reused observations, not new original executions.
- Six-file research packet: 122 source-linked ACT rules, six ABOUT story
  nodes, 22 broader mechanics cards, 14 prior sources, 26 native anchors,
  15 spans and five exact bounded receipt families.
- Public tests: 117 pass, no failures/errors/skips. The final delivery check
  separately repeats these from a freshly extracted archive and regenerates
  the packet/ABOUT CLI outputs.

## Keep these distinctions

Committed park state, transaction drafts, continuing session state, scene and
control state, presentation and external artifacts have different lifetimes.
Input acceptance, semantic effect, control readiness, rendered observation and
persistence are separate boundaries, not a universal five-stage pipeline.
Arithmetic width, signedness, wrap, truncation, cached values, shared RNG order,
pause ownership, exact signal values and update phases are part of semantics.

F3 starts at cursor FF and can read the neighboring 234-byte record at C3/C2.
The declared portable bank has 16 records, with inactive bytes zero; unsupported
out-of-bank access raises. Render/cycle runs before wait release/scheduling.
Wait release advances the retained command once and resets the frame deadline.

The ABOUT trigger is established at initialization. Do not invent an audio
completion trigger. A second signal-writing helper at 3619:0E57 has an
unresolved caller. Initial shared-scene scheduling is statically known but
the joined fixture explicitly uses regular update-then-scheduler ordering.

## Next useful work

Map this packet through the existing UIL owner's accepted representation and
run a bounded UIL consumer against the same actor/host observations. Start
with ABOUT and DinoMart, preserving unknowns, source hashes and evidence scope.
If no canonical contract exists yet, keep this as a requirements/semantic
handoff rather than silently choosing a new syntax.

For further recovery, close one connected story: complete ABOUT page services
and presentation readiness, or an ordinary purchase's reservation, arrival,
placement and commit/cancel timeline. Use the existing 22-card map and preserved
work plan; do not rediscover settled economics from scratch.

Outstanding work includes full page/resource/control paths, background
restoration/palette/text, audio event/driver/completion contracts, broader ACT
runtime subsets, backing-store eviction/reload, allocator resize/shutdown,
fatal cleanup, session/load continuation, startup/demo and `INTRO.DMO`, and the
remaining indirect/data ledger. Counts are not completion percentages.

## Integrity and reproduction

All 485 protected source/baseline files and the exact 191 original-file entry
set remain unchanged. `baseline/E54` retains the complete saved E54 payload
and manifest. Prior inputs and milestones were never edited.

One host test log was found truncated after its initial receipt had been
written. That rejected evidence is preserved under
`evidence/about-host/calibration-pre-export`. The unchanged verifier's complete
rerun is in `evidence/about-host/qualified` and independently audited by
`evidence/review-host`. Do not use the old receipt as current acceptance or
count the rerun's identical 83 fixtures as new unique coverage.

Originals stay external. The standard-library runtime/processor tool uses the
included pinned fDisBull wheel. Native verification needs Unicorn 2.1.4 and
Capstone distribution 5.0.9. See README for commands, always writing new output
directories. `scripts/export_story.py --verify` regenerates and compares exact
packet bytes. `scripts/verify_delivery.py` is the final archive gate.

No whole-game equivalence, canonical UIL execution, earned campaign or new
Z3 proof is claimed by this milestone. The source and evidence maps are the
starting material for those later, specifically scoped claims.
