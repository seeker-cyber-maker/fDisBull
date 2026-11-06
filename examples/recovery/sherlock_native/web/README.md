# Sherlock Replica Lab — browser edition

This browser companion runs the Sherlock replica's puzzle rules, generator,
verifier, game state and hint evidence in plain JavaScript. It starts with a
generated puzzle and built-in symbols, so no original game files are required.
Edit the source and reload the page to try a change; there is no game compilation
step or package installation.

The current reference is the retained native C implementation at
`ee62716e53f84c3f02814db4d7ff3a8884f2f152`. Independent finite comparisons cover
the JavaScript logic, state and proof modules. A separate protocol comparison
checks complete native CLI JSON responses. Browser interaction checks have
also observed edits/undo, hints, pause concealment, clue archiving, a real save
download and reload, and local SHI loading. The continuing UI and delivery
receipt is `research/browser-slice-20261105/ui-review.md` in the accompanying
Knowledge Pack, linked from its `BROWSER-SLICE.md`. This browser slice does not
establish complete
original-game fidelity or macOS AppKit execution.

## Run locally

Open `index.html` with the other files beside it. A browser with BigInt, Canvas
and the File API is required. The app loads local scripts and styles and uses
no CDN, server API or third-party runtime library.

For an ordinary localhost URL during development, run this from `replica`:

```sh
python3 -m http.server 8000 --bind 127.0.0.1 --directory web
```

Then open <http://127.0.0.1:8000/>. Python serves static files only; it is not part
of the game engine. Stop the server with Ctrl-C. Reload after changing a source
file. The current saved board may resume, so choose **New puzzle** or **Restart**
when a check needs a fresh starting state.

To produce the distribution files, run from `replica`:

```sh
node web/build.mjs /tmp/sherlock-browser
```

The output contains the eight runtime files, a self-contained
`sherlock-browser.html`, the `space-embed.html` fragment, and
`build-manifest.json`. The manifest records runtime file hashes and the retained
native reference. This command packages authored browser source; it does not
collect `Resources/`, SHI artwork or the original puzzle table. The embed is
bounded to 256 KiB. The game itself does not need Node.

## Play and inspect a puzzle

Choose **Generated puzzle**, enter an unsigned decimal seed from `0` through
`18446744073709551615`, and press **New puzzle**. **Random seed** chooses a new
seed. Generation installs a puzzle only after the bounded solver proves it has
exactly one solution. Failure to finish is reported explicitly. Generator
`sherlock-native-constraints`, version 1, preserves the native seed mapping;
generated seeds are separate from original puzzle numbers.

Every row contains its six items once, and each clue constrains their columns.
A sole remaining candidate still needs an explicit choice. The game allows
incorrect intermediate marks; it checks the completed board against the public
givens and clues.

| Control | Behavior |
| --- | --- |
| **Eliminate**, **Choose**, **Restore** | Select the action for a normal click on an item. Eliminate is the initial mode. |
| Right-click an item | Choose it, regardless of the selected mode. |
| Shift-click an item | Restore that candidate. |
| Tap a cell on a narrow display | Select it for the larger six-item control below the board. |
| Select a clue | Read its rule; use its inspector to move it within its group or transfer it to the other bank. |
| **Game** / **Other** | Change the displayed clue bank. Archived clues remain logical constraints. |
| **Undo** | Restore up to 25 board or clue-layout actions. Time is not refunded. |
| **Hint** | Offer a frozen, verified move. **Show why** displays sufficient supporting clues and row rules. **Apply hint** performs the move and adds 30 seconds. |
| **Pause** / **Resume** | Stop/resume the logical clock and conceal the board, clue cards, inspector and agent JSON panel. The paused board and clues are also inert. |
| **Restart** | Reinitialize the current puzzle with its current time limit. |

Keyboard shortcuts are **H** for Hint, **U** for Undo, **P** for Pause/Resume,
and **E**, **C**, **R** for the three candidate modes. They are ignored while
editing text inputs or interacting with a dialog. Browser input conventions
are adaptations; the native Mac app has its own documented click/drag controls.

The hint fee is charged on acceptance. Elapsed time continues while the offer
is pending, although its displayed timer is frozen. If acceptance crosses the
limit, timeout takes precedence over a completed winning board. The proof is
relative to the current candidate marks, givens and row rules; it does not
certify that all earlier player edits were correct. Inconsistency or an
exhausted proof budget is reported without inventing a deduction.

## Load local original artwork and puzzle numbers

Expand **Local files and saved games**:

1. Select a `.SHI` file under **Original artwork** to load all 46 images. The
   decoder checks the 23,920-byte size and every image header. Choose **Use
   built-in symbols** to switch back.
2. Select the existing `sherlock_puzzles.bin` under **Original puzzle table**.
   Then choose **Original numbered puzzle**, enter `0` through `65535`, and
   press **New puzzle**. The supplied native table retains the recovered
   numbered mapping. The browser validates its format, index and selected
   record, then discards the stored hidden answer.

File bytes are read with the browser File API and retained in the current tab.
The application does not upload the loaded SHI file or table. Reload those
files after reopening if they are needed. A saved session includes the public
constraints for its active puzzle, but it does not contain the SHI pixels or
the complete numbered table.

Original artwork appears in the browser board and clue pictures. The browser
uses its own layout, typography and relation marks. Loading a SHI set does not
make the view an exact DOS composition, and there is no browser image editor
in this slice. The module's `encodeSHI` API is available for codec checks; no
interactive painting/merge/save editor is exposed.

## Save and reproduce a problem

**Save game** prepares a versioned JSON session containing the public puzzle,
candidate/choice state, clue layout, undo history, timer, pending hint and basic
view settings. The optional `ui.hint_display_ms` field preserves the frozen
timer shown when a hint was offered; it is a decimal uint64 string while an
offer is pending and otherwise `null`. It is validated against the restored
game clock before adoption. Load the session with the JSON file control or
paste it into **Agent JSON
and diagnostics** and choose **Load JSON from the box below**.

The app attempts automatic saving in local storage after actions and during
play. In a compatible Space embed it also attempts the host's widget-state
API when the full envelope fits within 16 KiB. Storage can be unavailable in
embedded or local-file contexts; the footer reports the selected path.
**Save game** provides an explicit JSON copy. If a download is blocked, the
same text remains in the JSON box for copying. Artwork and table bytes are not
part of either save path.

**Capture bug** adds an expected/observed note, the public challenge, session,
recent actions, last hint evidence, source provenance and asset names. This
capture can be loaded to reconstruct the board. It includes the visible puzzle
and note, but excludes original file bytes. Capture JSON from an original
number is a separate user artifact; the source publication does not collect
such captures automatically.

Browser saves use their own versioned format. They are not DOS CFG files or
native Mac profile files. A saved pending hint is proved again on import; an
unverifiable offer causes a restore error rather than being silently applied.

## Agents: export a challenge and submit an answer

In **Agent JSON and diagnostics**:

- **Challenge JSON** exports the same `sherlock-cli-1` public puzzle envelope
  as the native CLI, including source identity and a public fingerprint.
- **Candidate state** exports candidate masks and explicit choices.
- **Check solution** accepts a six-by-six integer matrix, directly or as
  `{"solution": ...}`. It returns the public-constraint verifier's result
  without applying the answer to the board.
- **Check proposed move** proves or rejects a fixed remove/choose target under
  the current board assumptions. It does not perform that move or charge time.
- **Hint evidence** exports the last supporting-premise result. **Analyze
  puzzle** reports unique, multiple, unsatisfiable or unknown with its search
  effort; the UI analysis response omits solution witnesses.

Verification and analysis now use the exact native CLI response envelopes.
A validly formed but incorrect answer returns `ok: true` and `accepted: false`,
with a `violation` containing nullable row, column and clue indices. Malformed
input returns `kind: "error"`, `ok: false` and a structured error; native-compatible
answer grammar errors include a UTF-8 `byte_offset`. Analysis reports
`solutions_found`, `solution_count_is_exact`, decimal-string `nodes` and
`node_budget`. It does not include stored answers or solver witness matrices.

A proposed move has exactly these fields, using zero-based indices:

```json
{"kind":"remove","row":0,"column":0,"item":0}
```

This is a schema example, not a claim that the move is valid on the current
board. The engine determines its status. A proved support set is sufficient
relative to all frozen candidates, givens and row-permutation rules; it is not
necessarily the globally shortest or easiest explanation.

For native CLI interoperability, run from `replica`:

```sh
./Build-CLI.sh
./bin/sherlock-cli generate --seed 42 > /tmp/sherlock-seed42.json
```

Load that JSON into the browser. Conversely, an agent can take the browser's
generated seed identity and submit an answer to the native verifier:

```sh
./bin/sherlock-cli verify --seed 42 --solution answer.json
```

See [the CLI protocol](../cli/README.md) for its schemas and exit statuses.
Clue object IDs are `row * 6 + item`. Large unsigned seeds and clock values are
decimal strings at JSON boundaries to preserve all 64 bits.

### In-page agent API

After startup, the browser exposes `globalThis.SherlockReplica`:

| Method | Observable operation |
| --- | --- |
| `challenge()` | Return the current public CLI challenge document. |
| `state()` | Return owned candidate and chosen matrices. |
| `snapshot()` | Sample elapsed time and return the complete JSON session. |
| `verifySolution(input)` | Return the native CLI verification/error envelope for a matrix or single-field solution object without editing the board. |
| `checkHint(input)` | Check an exact remove/choose proposal without applying it. |
| `analyze()` | Return the native CLI analysis/error envelope, with identity, classification, count exactness and node effort. |
| `move({kind,row,column,item})` | Apply a remove, restore or choose action through the normal state path. |
| `requestHint()` | Request the normal UI hint offer and its evidence. |
| `exportBug(note)` | Sample time and return a reproduction document. |
| `load(documentOrJSON)` | Validate and load a challenge, browser save, session or capture. A pending hint must first be acknowledged. |

The lower-level modules are `SherlockCore`, `SherlockState`, `SherlockProof`,
`SherlockAssets` and `SherlockProtocol`. They also expose CommonJS exports for
Node checks. The core/state/proof interface is documented in
[CONTRACT.md](CONTRACT.md). Direct mutation
of live game fields is outside the application's admitted boundary.

`SherlockProtocol.verify(puzzle, input)` and
`SherlockProtocol.analyze(puzzle, budget?)` are read-only CLI response adapters;
their host must bind the puzzle to its intended source. `unwrap(documentOrJSON)`
validates a session/capture envelope and returns `{incoming, ui}` for the
core/state semantic loader. It checks wrapper fields and captured challenge
consistency, rejects hidden-answer fields even in nested metadata, and rejects
accessors, sparse arrays, cycles and extended object shapes. Admitting a stored
evidence record's structure does not accept its claimed proof result: the host
recomputes the actual pending hint from the admitted board.

### Import rules and provenance

The UI's raw JSON reader rejects duplicate keys, including aliases written
with Unicode escapes, decoded NUL, trailing documents, excessive structure,
fractional/exponent numeric tokens and unsafe integer Numbers. Use ordinary
integer tokens and decimal strings for large unsigned values. JSON file imports
are limited to 1 MiB. Core challenge and state loaders additionally validate
their closed schemas, sizes, ranges and identities; failed admission preserves
the current game.

A public fingerprint establishes content identity, not authentication. The
shell reconstructs native-generated challenges from their seed and limits and
checks the fingerprint. An original challenge can be checked against a locally
loaded table. Without that table, a well-formed imported original challenge is
explicitly labeled **Imported public constraints**. Its current constraints can
still verify an answer, but its historical provenance has not been established
by the browser.

## Run the focused checks

From `replica`:

```sh
node web/tests/core-boundaries.js
node web/tests/state-contract.js
node web/tests/proof-contract.js
node web/tests/assets-test.js
node web/tests/protocol-contract.js --native
node web/tests/parity.js --skip-private --report /tmp/sherlock-parity-public.json
```

The first four commands run focused JavaScript checks. The final two also
require a C11 compiler: they build the existing native reference and compare
its actual outputs with JavaScript. The protocol suite passed **63 boundary
checks and 54 complete native JSON comparisons**, including malformed answers,
exact diagnostic offsets, invalid budgets and identity fields. Run it without
`--native` for its JavaScript-only checks.

The recorded public parity run passed 114 oracle
fixtures and 4,360 counted equality assertions; the private adapter run added
16 comparisons, for 4,376 total. Coverage includes all 1,728 relation tuples,
seed boundaries, 1,116 state transitions, three complete hint-driven generated
games with 455 accepted hints, budget/refusal paths, proof replay and
hidden-answer poisoning. All state traces together include 458 accepted hints. A
deliberately wrong `NOT_BETWEEN = !BETWEEN` rule differs in 168 tested cases.

Optional private adapter checks use the existing native resource folder:

```sh
node web/tests/parity.js --private-resources /absolute/path/to/Resources --report /tmp/sherlock-parity-private.json
```

The recorded run compared every decoded pixel in four SHI files and public
documents for original numbers 0, 1, 235, 32767, 32768, 65534 and 65535. The
receipts retain hashes and observations, not original payloads. Full details
and exact source identities are in the Knowledge Pack's
`research/browser-slice-20261105/parity-review.md` and JSON receipts.

## Remaining work

This browser slice provides the playable logic and debugging/agent seam. It
does not yet include the native image editor and image transactions, audio,
player profiles, tournaments, original menus/background configuration,
original victory animation or a human difficulty rating. Its browser save
extension is separate from original persistence behavior.

The C comparison does not qualify browser rendering, pointer/keyboard events,
focus, suspended-tab timing, downloads or durable Space storage. Separate UI
checks have observed candidate edit/undo, the seed-42 hint explanation and fee,
pause with no visible candidate/clue buttons and a hidden agent panel, clue
archiving to Other, a 10,420-byte save download followed by reload with bank
and undo restored, and loading all 46 images from an original SHI file.
Further browser/host qualification is tracked in the UI review. These
observations do not establish every browser or durable Space storage.
This work also does not repeat original-program recovery or
close the still-open macOS build and interaction gate. The retained native
differences include answer-free hint repair and native ordering for some hint
families. See [the feature ledger](../docs/FEATURE-COVERAGE.md) for native
coverage and the separate browser extension.
