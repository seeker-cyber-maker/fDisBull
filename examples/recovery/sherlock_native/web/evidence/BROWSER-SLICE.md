# Browser companion slice — source and delivery record

Prepared from the source snapshot on 2026-11-06. The date in this directory
identifies the work begun on 2026-11-05.

## Intended result

Continue the Sherlock replica while making its game logic and state available
as a JavaScript browser application. A browser reload should be enough to try
a UI or logic change. The same public constraints should let agents retrieve
a challenge, submit an answer or proposed deduction, and have the game engine
verify it. A static browser package and ChatGPT Space embed are delivery
targets for this slice.

The authored implementation is in `replica/web/`. It uses plain JavaScript,
HTML and CSS with no third-party runtime dependencies. The retained native
reference is `ee62716e53f84c3f02814db4d7ff3a8884f2f152`. This work does not replace
the Mac application or change the prior original-fidelity claims.

## Implemented source

| Component | Responsibility |
| --- | --- |
| `engine.js` | Relation predicates, public verifier, exact bounded solver, version-1 uint64 generator, public challenge format, strict challenge admission and fingerprint. |
| `state.js` | Candidates and choices, fixed givens, clue layout, rolling undo, logical clocks, outcomes, frozen hint offers, compact browser saves and strict restoration. |
| `proof.js` | Consistency-first proof of a fixed remove/choose target, supporting-clue reduction, explicit exhaustion and replay. |
| `assets.js` | Local SHI decoding/encoding, original table adapter and bounded raw JSON parsing. |
| `protocol.js` | Exact native CLI verification/analysis JSON, bounded answer grammar and diagnostic offsets, plus strict session/capture envelope admission. |
| `app.js`, `index.html`, `style.css` | Browser board, action modes, clue inspector, hint evidence, timers, local files, saves, bug captures, agent controls and optional host storage. |
| `build.mjs` | Deterministic static-file copy, standalone HTML and bounded Space fragment, with runtime source hashes. |
| `tests/` | Focused boundary tests and the independent compiled-C parity harness. |

Generated puzzles and built-in symbols work without original resources. Local
SHI and puzzle-table loading is optional. Browser file bytes remain in the
tab; automatic host saving contains a public puzzle/session, not the complete
table or artwork.

The browser's interface is an adaptation: explicit Eliminate/Choose/Restore
modes, clue controls, readable supporting premises and a JSON work area.
Original relation semantics remain important, including NOT_BETWEEN's
positive outer-spacing requirement. Native seeds retain their separate versioned
identity and do not become original puzzle numbers.

## Method and evidence

The retained fDisBull reconstruction guidance supplied the approach: define
the seam before porting, preserve widths and ordered effects, pin reference
and candidate sources, test state changes and unchanged-state refusals, and
include a deliberately wrong control. Existing native C was the executable
reference for this seam. No new original executable, Watson backend or emulator
observation was used to claim the browser port's fidelity.

The independent [parity review](parity-review.md) and
full receipt (separate workspace record: `research/browser-slice-20261105/parity-review.json`) establish a finite C → JavaScript result:

- 114 oracle fixtures, 4,376 counted equality assertions including private
  adapter observations; the [resource-free repeat](parity-public-review.json)
  passed 4,360.
- All 1,728 relation truth values; 17 generation/limit cases; 72 rejected
  incorrect generated answers; solver witnesses and explicit budget states.
- 1,116 state transitions covering edits, undo, clue organization, clocks,
  hint acceptance and timeout-before-win ordering.
- Three generated games completed with 455 accepted hints; 458 accepted hints
  across all state traces.
- 19 explanation and 11 replay fixtures, with hidden-answer poisoning and
  unchanged-state controls.
- The deliberately wrong `NOT_BETWEEN = !BETWEEN` rule detected in 168 cases.
- Four private SHI files compared at every decoded pixel, and seven original
  table numbers compared against native CLI public documents.

The additional `protocol-contract.js --native` suite passed **63 boundary
checks and 54 complete native JSON comparisons**. It compares verification,
analysis, identity fields, malformed-answer diagnostic offsets, oversize input
and invalid budgets against a freshly compiled native CLI. It also checks
session/capture wrapper schema, nested hidden-answer rejection, metadata
consistency and unchanged input. These protocol comparisons supplement the
engine/state parity receipt; they do not add original-process evidence.

The adapter review found Buffer `.slice()` aliasing at the table admission
boundary. The owner changed the copy to `new Uint8Array(source)`; mutation of
the caller's admitted Buffer now leaves the table unchanged. Private-input
comparison failures redact input-bearing diagnostics from the report.

Focused implementation notes are [core-note.md](core-note.md) and
[state-note.md](state-note.md). Their tests supplement the independent result;
they are not a second original-program oracle. A defect shared with native C
could still pass a faithful port comparison.

## Exact local commands

From the workspace/repository root, enter `replica` before these commands.

Serve the editable files:

```sh
python3 -m http.server 8000 --bind 127.0.0.1 --directory web
```

Open <http://127.0.0.1:8000/>. The static files can also be opened directly;
local-file persistence and download behavior depend on the browser host.

Build source-only browser outputs:

```sh
node web/build.mjs /tmp/sherlock-browser
```

The documentation pass exercised that build command with output directory
`/tmp/sherlock-browser-docs-final`: eight runtime source files were packaged;
the embed was 190,409 bytes and the standalone HTML was 190,649 bytes. This is
a local packaging observation for that source snapshot, not the final hosted
build identity. Runtime file hashes are in its `build-manifest.json`.

Run the focused checks and source-only C comparison:

```sh
node web/tests/core-boundaries.js
node web/tests/state-contract.js
node web/tests/proof-contract.js
node web/tests/assets-test.js
node web/tests/protocol-contract.js --native
node web/tests/parity.js --skip-private --report /tmp/sherlock-parity-public.json
```

Add the privately held original inputs only when checking the adapters:

```sh
node web/tests/parity.js --private-resources /absolute/path/to/Resources --report /tmp/sherlock-parity-private.json
```

The optional folder contains `sherlock_puzzles.bin` and the four original SHI
files under `Images/`. The harness compiles with
`-std=c11 -O2 -Wall -Wextra -Wpedantic -Werror`, records source hashes and exits
nonzero on a discrepancy. Public fixtures contain authored data only.

## Import, verification and persistence boundaries

The UI exports the native `sherlock-cli-1` challenge format. Answers are checked
against public row, given and clue constraints, without editing the live
board. Verification and analysis return the complete native CLI JSON contract
through `SherlockProtocol.verify` and `analyze`, including public identity,
nullable violations, count exactness, budgets and structured error envelopes.
An incorrect but well-formed answer is an `ok: true` verification with
`accepted: false`; malformed input is an error. Answer errors retain native
UTF-8 diagnostic offsets, and analysis omits solution witness matrices.
Proposed remove/choose actions are checked against the current frozen
candidate assumptions. Proof outcomes remain proved, refuted, inconsistent or
unresolved; budget exhaustion never becomes a successful certificate.

Raw JSON rejects duplicate keys after escape decoding, NUL, trailing content,
excess structure and noncanonical or unsafe numeric tokens. Challenge and save
loaders then check schemas, shapes, ranges, identity and game-state consistency.
Large unsigned seeds/clocks cross JSON boundaries as decimal strings. Import
works on an owned candidate game and adopts it only after validation. Pending
hint offers must still be applicable and provable on restore. The optional
`ui.hint_display_ms` preserves the frozen visible clock separately from the
elapsed total; canonical decimal/range and clock consistency are checked before
adoption. Older sessions without the optional field remain admitted.

`SherlockProtocol.unwrap` validates the complete browser session/capture
wrapper, including metadata, recent actions and captured challenge consistency.
It rejects nested hidden-answer fields, accessors, cycles, sparse arrays and
unknown wrapper fields. A structurally valid historical hint-evidence record
is not accepted as proof; the pending offer is recomputed from the admitted
game.

The public fingerprint is a content identifier, not authentication. The UI
regenerates native-source challenges and checks their fingerprint. Imported
original constraints are checked against a loaded local table when available;
otherwise the provenance label remains imported public constraints.

Browser sessions and reproduction captures are separate browser formats.
Automatic saving attempts local storage and, when supported and under the
16-KiB envelope limit, the Space host's widget state. Explicit JSON export is
also available. The source implementation of these adapters is not a receipt
that every host can restore or download the data successfully. The separately
observed download/reload case is recorded below.

## Publication manifest

`browser-source-manifest.json` (separate workspace record: `research/browser-slice-20261105/browser-source-manifest.json`) is a local
allowlist with byte counts and SHA-256 values. Paths are workspace-relative;
the publisher must map them to the intended source repository prefix. This
record authorizes no network mutation and claims no remote publication.

The allowlist contains:

- Authored `replica/web/` runtime source, build script, contract, README and
  focused/parity test sources.
- The focused additions to `replica/README.md` and
  `replica/docs/FEATURE-COVERAGE.md`.
- Source-only browser notes and the bounded parity receipts in this research
  directory.

The publication set excludes `replica/Resources/`, original SHI/table/executable
bytes, original screenshots/audio/manuals, temporary compiled helpers, private
reproduction captures and generated distribution directories. The static
browser build manifest separately identifies the eight files packaged for
delivery. It does not certify a remote deployment.

The source manifest is a snapshot. Any later source, documentation or QA-note
change requires refreshing its hashes before publication. The manifest does
not include its own hash, avoiding a recursive identity claim.

## Remaining replica work

Browser editor/merge/SHI-save interaction, audio, player profiles, tournaments,
original menus and background settings, original victory animation and human
difficulty grading are not implemented in this slice. The browser codec can
read/write SHI programmatically; that is distinct from an interactive editor.
The original's answer-dependent hint repair is still deliberately absent, and
some hint-family ordering remains native policy.

The browser comparison does not close the Mac acceptance gate. AppKit has
still not been compiled with an Apple SDK or exercised on a Mac in this work.
The [native feature ledger](../../docs/FEATURE-COVERAGE.md) retains
those obligations and adds a separate browser extension.

## UI and delivery acceptance — observed checks and continuing review

The UI owner reports the following direct browser-interaction observations,
separate from the C/Node results:

| Interaction | Observed result |
| --- | --- |
| Candidate edit and Undo | The candidate change and its reversal were visible. |
| Seed-42 hint | Show why displayed the evidence, followed by acceptance and the hint fee. |
| Pause | No candidate or clue buttons remained visible; the agent panel was hidden. The earlier board-only cover was corrected to conceal the clue pane, inspector and cell controls as well. |
| Clue archive | The selected clue moved into the Other bank. |
| Save and reload | A real 10,420-byte JSON download was obtained; reload resumed the saved bank and undo state. |
| Original SHI load | The UI loaded all 46 images from a supplied original SHI file. |

The continuing [UI review](ui-review.md) will pin the actual tested surface,
source/build identity and detailed observations. Its final delivery record
will also identify the preview and Space and state remaining host limitations.
Further QA is ongoing at this update: these completed checks should not be
read as universal browser compatibility, suspended-tab timing qualification
or durable Space widget-state synchronization.

A source-only package, a browser interaction receipt and a stored Space page
are separate evidence. Mac/AppKit execution remains unperformed.
