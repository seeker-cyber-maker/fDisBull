# SNES Shadowrun hardware inputs and NPC conversations

This study extends the source-bound, title-seeded `opening` profile with an
explicit environmental-input module. It separates exact comparisons conditioned
on recorded hardware readings from repeatable seeded local play. Neither mode
recovers the original SNES display clock, original artwork or APU playback.
The [room-transition study](SHADOWRUN_SNES_TRANSITIONS.md) retains the preceding
milestone and its original RNG refusal; the [keyword audit](SHADOWRUN_SNES_KEYWORDS.md)
explains the three names with no teaching site in the audited catalogues.

## Input contract

The source `$80:C530` routine mixes a cartridge table, its own byte seed at
`$7E:1D04`, two separately sampled bytes of the NMI counter and the latched
horizontal/vertical beam readings. Reading `$2137` latches the counters; its
returned byte does not enter the arithmetic. The input module receives only
the four actual read bytes, a caller class and a task context. The original
seed, RNG return, later RAM and decoded responses are never gameplay inputs.

The standalone `shadowrun_snes_rng` fragment computes the source transform.
`shadowrun_snes_hardware` supplies its external inputs and owns their ordering.
The opening composition retains the title's game seed and derives every later
seed from the recovered calls. It includes the ambient `$FEDE` caller and
`$C4EF` rejection sampler, as well as script-native `$63`. Rejection retries
consume additional raw observations rather than reusing a previous draw.

| Mode | Input source | Claim |
| --- | --- | --- |
| `disabled` | Previous guarded behavior | Unsupported timing-dependent gameplay refuses |
| `recorded` | Ordered private raw observations | Exact comparison under those declared external inputs |
| `seeded` | Nonzero 32-bit xorshift state | Repeatable adapted local randomness; original timing is unqualified |

A recorded public update receives a finite batch of at most 128 rows, including
an empty batch when no draw occurs. Caller, task context and global ordinal must
match. Missing, extra or misordered rows refuse the whole update. Queue position,
derived game seed, local PRNG and every other exposed state field belong to the
native transaction. The `fdisbull_step(context, pad)` ABI is unchanged; the
declared hardware fields are input ports, populated before each update.

The longer street route also recovers actor target release (`$5B`), player
following (`$21`), velocity clear (`$4D`), facing the live player (`$6C`) and
metadata reset (`$AE`), plus the source's 16-bit increment/decrement operations.
Horizontal collision now accepts the querying NPC and retains source self-owner
and selected-player exceptions. Its two-cell traversal differs from the vertical
query's early-stop behavior; the first actual NPC query and the source branch
rules were checked separately.

The Python `input_batch` helper accepts exactly `caller`, `context`, `nmi_low`,
`nmi_high`, `beam_h` and `beam_v`. It rejects seed/result metadata. Generic script
reads of unrecovered timing state remain guarded; supplying one typed reading
does not make the entire hardware counter memory authoritative.

## Original-game observations

The supplied 1 MiB USA ROM remains pinned to SHA-256
`e6bc0a595d5c7c4bc0bbb61ffe35a70288a77eb78544ed74682d489a9e6f07f4`.
The original runs use SNES9x revision
`fae2fea08f74180759ef540ee94259213f503480`. The new observation-only core is
`7a06f2d790a3ce8ba3766e580f3e86f79c379a11a93f6f5a7d044ad4551fd248`.

The adapter observes the actual bus reads at `$C53C`, `$C542`, `$C549` and
`$C54F`, after the latch at `$C536`. Counter bytes remain separate observations
because an interrupt can occur between them. Source stack returns and task
identity independently qualify the caller labels. The raw journal keeps
seed/result metadata in a verification-only section. The checker recomputes
that metadata and verifies seed continuity without loading it into gameplay.

Two uninterrupted controller routes retain the previous original reference
identities. All 4,045 and 3,993 main-loop checkpoint digests, registers and frame
metadata agree with the earlier typed observer. Controller journals match
byte-for-byte. The selected 15/16 WRAM images, screenshots and five final hashes
per route also agree with the unmodified core recordings. These are neutrality
checks within one emulator family, not independent console-hardware evidence.

The routes contain 320 and 313 complete draws: each includes 230 ambient calls
and 71 bounded-sampler calls, plus 19 or 12 VM calls. There are no pre-title
draws, missing reads or dropped rows. Both chains start from the title seed
`$55`; no intermediate seed is substituted. No RNG draw occurs during the modal
controller boundaries in these two recordings. Their 407/466 private modal RAM
snapshots qualify the selector context, logical windows, response text and
persistent keyword effects while the world scheduler is suspended.

The first route asks about HitMen (`$17`) and exits. The second uses Talk to
learn Firearms (`$10`), asks about it through the source fallback response,
reopens Ask and uses SELECT to cancel the entire conversation. All IDs here
are hexadecimal. These bounded routes do not establish arbitrary NPC access,
every keyword, dialogue child-script behavior or whole-game equivalence.

## Reproduction

Build a private seeded local app from the caller's pinned ROM, title WRAM and
save RAM:

```sh
fdisbull shadowrun-snes-build --profile opening \
  --rom /private/original/Shadowrun.sfc \
  --ram /private/captures/title-000839.bin \
  --save-ram /private/captures/save_ram.bin \
  --hardware-mode seeded --hardware-seed 1 \
  --output /private/new-shadowrun-app
```

The display identifies seeded randomness. Arrows move/target, B opens actions
and confirms, Up/Down select menu entries, and Tab maps to source SELECT. Return
confirms New Game. R resets the complete model, including the seeded source.
The app requests 60 Hz; its updates include suspended input polls and are not
original video frames. Live keyboard and onscreen operation have separate
qualification from offscreen/programmatic replay.

Recorded comparisons use `scripts/check_shadowrun_snes_interactions.py` with
`--hardware-reference` selecting the new private hardware-observer run. The
ordinary `--reference` can retain the earlier raw checkpoint files because
their digests match. The checker validates both observer identities, every
checkpoint, controller journal, raw read phase and modal snapshot before using
the readings. `--require-room 1 --require-keyword` requires a real street load,
learned-list change, keyword confirmation and source conversation return.
The second route additionally uses `--require-conversation-cancel`.

## Verified results and friction

Both input-conditioned routes pass against the frozen runtime. The counts
below overlap and must not be added as unique game coverage.

| Check | Result |
| --- | --- |
| Ask HitMen and Exit | 4,045 main-loop checkpoints, 407 modal snapshots, 320 raw draws; source return to exploration |
| Talk, learn Firearms, Ask and SELECT-cancel | 3,993 main-loop checkpoints, 466 modal snapshots, 313 raw draws; source return to exploration |
| Native/UIL compilation | All 150,436 exposed elements at each declared sample; 50 and 56 complete-state readbacks, not a complete interpreted trajectory |
| Live NPC follow state | Separate continuous audit of control and both target words for every active actor: 183,993/181,809 word comparisons, zero mismatches |
| Retained conversation body | Four original decoder/layout cases; 664 retained boundaries / 55,601 bytes across both recorded and both seeded routes; 25 further complete-state compiler samples |
| Seeded local play | Seeds 1 and 2 complete Talk, Firearms/HitMen questions and Exit/cancellation; 4,102/4,109 updates including title; complete reset/replay equality |
| Seeded input arithmetic | Two seeds, ten calls each; 795,900 native/UIL element comparisons against a separate arithmetic prediction |
| Atomic refusal | Seven cases, twice each; 2,106,104 unchanged element comparisons, including a seeded diagnostic failure after ten draws |
| Valid ten-reading transaction | Accepted; 150,436 native/UIL elements agree |
| Adapted app | Offscreen keyword menu, both responses and return to the street; exact native core matches the independent seeded driver |
| Earlier interaction regressions | Patch 1,973; Scalpel 1,928; repeat 2,128; door response 2,363 checkpoints |
| Earlier profiles / disabled mode | Opening 1,615; scripted 60; disabled prefix 3,764 and expected RNG refusal with complete rollback |
| Focused checks | 89 runtime/helper tests; 1,084 distribution, checker, input-contract and keyword-audit tests |
| Broad macOS suite | 4,290 passed, 142 skipped, 3 failed, 23 setup errors; same 26 baseline cases and normalized exception lines; source unchanged during the run |

The refusal tests include a missing final reading after nine draws and an extra
unused reading after ten. A deliberately invalid later task frame verifies that
the native PRNG also rolls back after being consumed. That corrupted-state case
is a diagnostic intervention, not an ordinary gameplay route.

The prior task-filtered observer missed 260 draws before the first failing
street update. Recording every producer call from title made the seed chain
checkable. A second trap was choosing a trace endpoint by the preceding video
frame: the relevant logical update finished early in the next checkpoint's
frame, so the shorter trace missed NPC motion. Bus-write filters also needed
the CPU's low-bank memory mirror. Wait callbacks do not always return through
the ordinary native return PC; incorrect global-stack pairings were excluded.

An initial seeded test selected Exit while intending Talk because its driver
assumed a different menu order. The runtime had already reached dialogue. The
corrected readiness-driven test uses the recovered Exit/Talk/Ask order and
checks the learned list and subsequent response/return. The investigation
skill now records these decision and probe lessons, alongside the keyword
audit's actual-directory and validated-instruction traversal rules.

The selector overwrites `$21A0` with its marker text, so scratch-buffer equality
alone did not qualify the retained body. A separate live UI-buffer audit found
an unqualified fourth pointer, `$5FD2`. Fresh original decoder/layout captures
qualified its 114-byte processed body before the integrated audit continued.
The four distinct bodies total 334 bytes including terminators. All four routes
then matched the retained text, length, pointer and body-window cursor/subpixel
positions. These retained input boundaries are not counts of internal draw calls.
The investigation skill records this distinction and the failed coverage probe
is preserved privately.

The [sanitized evidence](evidence/shadowrun-snes-hardware-2026-11-04/) separates
original neutrality, input-conditioned source checks, local seeded behavior,
rollback diagnostics, the static keyword audit and broader regressions.
The broad suite remains non-green: the pre-existing Linux/ELF fixture failures
and media-module failure are retained. This milestone does not assert hosted
Linux/native CI or release readiness.

Original ROMs, RAM, states, save files, decoded dialogue, images and generated
apps stay private. Tool packages contain authored reconstruction code, checks,
methodology and sanitized counts/hashes only. Local source/runtime verification,
exact-commit packages, hosted CI, merge, release and system installation remain
separate delivery gates.
