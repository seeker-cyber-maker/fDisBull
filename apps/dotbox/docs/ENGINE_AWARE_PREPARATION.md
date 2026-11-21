# Fast state discovery with engine-aware readers

Decision: 17 November 2026. Use a known engine's logic and serialized-state
structure to narrow the next question before reaching for machine-code
disassembly. Dot owns this machinery; the player should discuss rooms, objects
and choices rather than selecting a reverse-engineering tool.

Version `0.1.0.dev5` packages a bounded AGI V2 resource/logic census extracted
from the user's fDisBull 0.34.1 work. It reads local files and does not require
an fDisBull installation, database, native interpreter, symbolic solver or
generic code analyzer. The existing x86 inspection tools remain available for
any unresolved state or relationship question, including ambiguity inside a
supported engine. Read [ongoing reverse engineering](REVERSE_ENGINEERING.md)
for cross-context readers/writers, storage reuse and the distinction between
packaged decoding and the still-needed live capture/analysis workflow. Engine
readers are accelerators; the internal model remains engine-neutral.

## What the packaged AGI reader supplies

The selected static profile is **uncompressed DOS AGI V2, interpreter 2.917**.
The caller chooses that profile explicitly; filenames and a successful partial
parse do not independently establish the game's edition or interpreter.

| Available result | What Dot can use it for |
| --- | --- |
| Resource directories and bounded volume inventory | Bind selected bytes, locate LOGIC resources and retain per-resource failures. |
| Ordered conditions and actions | Find tests of variables, flags, inventory, input and actor positions without disassembling the interpreter. |
| State-write sites | Locate assignments, flag changes and inventory operations relevant to one observed effect. |
| Actor setup and room/resource references | Produce candidate room links, pictures, views and interaction targets for subsequent observation. |
| Bounded local value propagation in resolve mode | Narrow some indirect destinations while preserving unknown values and execution barriers. |
| Vocabulary, inventory metadata and optional messages | Help interpret resources and guide reconstruction without asserting current player knowledge. |

The result keeps the existing `fdisbull-agi-scene-census-1` contract and reports
static candidates, with **zero qualified executable interactions**. It does
not name the meaning of every flag, read the live interpreter, decode original
Sierra save files, establish current inventory or generate a playable harness
automatically. `OBJECT` initial-room metadata is not a current possession
report. On-screen actor IDs, inventory IDs and resource IDs stay separate.

Compressed AGI V3, booters/GAL, SCI and unqualified version-specific encodings
remain outside this profile. One failed or unsupported resource stays explicit
instead of discarding useful information from other resources. The outline
retains structural candidates; resolve adds bounded analysis and preserves
unresolved targets. Neither stage promotes a candidate to an observed scene.

## Use a cheap outline before deeper work

After binding the actual game/edition and selecting the profile, use a private
output directory outside Git and outside the game input tree:

```sh
mkdir -m 700 /tmp/dotbox-agi-study
dotbox agi inspect /private/game --profile 2.917 --stage outline --output /tmp/dotbox-agi-study/outline.json
dotbox agi inspect /private/game --profile 2.917 --stage resolve --include-ir --output /tmp/dotbox-agi-study/resolved.json
```

Use a new private directory if that example path exists. The CLI requires a
new report file in an existing owned private directory, refuses overwrites,
and prints a compact result summary. Full game-derived records remain private.
`--include-text` explicitly adds decoded messages to that private report;
message availability is not permission to narrate hidden content.

The limits are global to one census, including attempted work on resources that
later fail. Code spans are admitted before layout parsing, and layout parsing
stops at the remaining instruction allowance. Shared text work includes LOGIC
messages, initial object names and vocabulary; repeated references cannot
silently multiply text decoding or literal report expansion.

| Option | Default | Accepted range |
| --- | --- | --- |
| `--max-updates` | 200,000 | 1–2,000,000 |
| `--max-instructions` | 100,000 | 1–1,000,000 |
| `--max-code-bytes` | 1,048,576 | 1–4,194,304 |
| `--max-message-bytes` | 262,144 | 1–4,194,304 |
| `--max-report-bytes` | 8,388,608 | 16,384–16,777,216 |

Instruction or text exhaustion leaves explicit incomplete resource records.
Report encoding and hashing are incremental and bounded; a report that cannot
fit is refused without creating a destination file. The report limit includes
the CLI's final newline. Raising a limit is an intentional extra investigation,
not permission to exceed the foreground learning deadline. These are work/data
bounds, not a wall-clock timeout or a guarantee about the live game's latency.

Coverage separates logical entries from actual work. Shared LOGIC bytes can
appear under several numbers, so `instructions` and `code_bytes` can exceed a
parse-work limit through cache reuse. `instructions_attempted` and
`code_bytes_admitted` measure the charged work, including failed attempts.
`expanded_text_bytes` charges literal occurrences when text is included, or
unique decryption/hash work in metadata mode. `unique_text_bytes` counts the
processed spans; overlapping suffixes still require their own span work.

Read `dotbox agi inspect --help` for the command arguments. The current census
inspects a bounded resource set; it does not yet offer a per-LOGIC CLI filter.
Retain the manifest and report so subsequent near-term work can consult them
without repeating a broad scan. Do not finish all indirect targets before
using an already qualified action. The learning journal's existing deadline
and probe admissions still apply when this investigation blocks current play.

Example of a useful operational question: after the window opens, which flag
writer runs, which condition later tests it, and when does the input route
become ready again? A small cluster of logic references can answer where to
observe next. It cannot establish that the current window is open by itself.

## Join three sources of evidence

For a candidate state meaning, combine:

1. **Static logic:** the variable/flag writer and consumers, their conditions,
   helper calls and any unresolved effects.
2. **Current observations:** typed before/after values, the actual input and
   its effect phase, followed by readiness observations.
3. **Saved-game contrasts:** unchanged-intent controls, one meaningful action,
   frozen save differences and reconstruction through the real loader when
   a qualified recovery route exists.

For example, a byte changing after taking an item is a lead. An AGI `get`
operation may identify the inventory object, a later `has` condition can show
where possession matters, and a restored observation can confirm retention.
None of those alone establishes every side effect or maps all transient state.
Check the chosen interpreter/edition and preserve indirect or helper-dependent
uncertainty. A state write may occur after response text, and a committed write
may precede the next usable input boundary.

Save/load is particularly useful when the loader reconstructs display or other
derived values. Changing a memory location and looking immediately at a stale
frame is insufficient evidence about that field. Loading through the game's
own mechanism and observing its completed result can test the persistence
contract. Work on isolated copies; original saves and the player's live run
are not a scratch experiment.

See [recovery and saves](RECOVERY_AND_SAVES.md) for the controlled procedure,
mutable-file scope and the native restore integration gate. See
[stateful scenes](STATEFUL_SCENES.md) for current versus historical reports,
internal knowledge, entity identity and input admission.

## Qualified decoding boundary

The first extraction preserves ordered conditions, including stateful `said`
tests, and signed backward GOTO. It refuses state-dependent `trace.on` layout
and branches that do not land on a decoded instruction boundary.

High-bit IF displacements are explicitly unqualified. The pinned ScummVM
implementation reads an unsigned IF skip into an integer instruction pointer;
the AGI Behavioral Specification describes a signed displacement. The common
`0..0x7fff` forward subset is retained. An IF with bit 15 set remains opaque
instead of choosing an unsupported interpretation. This boundary is covered
by an authored regression fixture; exact original-runtime behavior for those
encodings remains a later qualification task.

Primary interpretation references:

- [ScummVM IF handling](https://github.com/scummvm/scummvm/blob/f7403b6efaae2f033e8abea80b3fb6bee5303369/engines/agi/op_test.cpp).
- [ScummVM logic instruction-pointer representation](https://github.com/scummvm/scummvm/blob/f7403b6efaae2f033e8abea80b3fb6bee5303369/engines/agi/logic.h).
- [AGI logic bytecode specification](https://peterkelly.github.io/agi-re/spec/logic_bytecode.html).
- [AGI version profiles](https://peterkelly.github.io/agi-re/spec/version_profiles.html).

These references constrain the partial reader; they do not grant native
execution equivalence or establish current game state. Source attribution and
the retained first-party distribution status are recorded in
[the extraction notes](EXTRACTION.md).
