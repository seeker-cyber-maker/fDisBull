# Sherlock native agent example

An authored six-by-six logic engine and JSON CLI, with an AppKit host for the
owner's private Sherlock 1.50 reconstruction. The portable C code contains a
shared answer verifier, exact bounded solver and deterministic native puzzle
generator. It has no emulator, Python or external solver runtime dependency.

## Build and use the CLI

```sh
./Build-CLI.sh
./bin/sherlock-cli generate --seed 42 > puzzle.json
./bin/sherlock-cli verify --seed 42 --solution answer.json
./bin/sherlock-cli analyze --seed 42
./bin/sherlock-cli hint --seed 42
./bin/sherlock-cli check-hint --seed 42 --move move.json
```

`answer.json` is a six-by-six integer array or an object whose only field is
`solution` containing that array. Each row contains its row-local item IDs
0–5 exactly once. Use `--solution -` for standard input. The challenge JSON
contains givens, clue predicates, object mappings and identity, without the
answer. Verification reconstructs the canonical challenge before checking the
submitted grid. See [the CLI contract](cli/README.md) for complete schemas,
identities, fingerprint semantics, budgets and exit statuses.

Generated puzzles use `sherlock-native-constraints` version 1 and the full
unsigned 64-bit seed. Seeds/counters are decimal strings in JSON. The solver
must prove exactly one solution before generation returns a puzzle. UNSAT,
MULTIPLE and UNKNOWN remain distinct; exhausting a budget does not certify a
puzzle. Human difficulty grading and a guaranteed human deduction sequence
are outside this version's contract. The generation distribution is not
claimed to be uniform over all possible puzzles.

## Original numbered puzzles and the Mac app

Original mode supports numbers 0–65535 through a separately supplied private
typed table. It never substitutes the native random generator for a missing
original record. Use `puzzle --number 235 --data /private/sherlock_puzzles.bin`
or set `SHERLOCK_PUZZLE_TABLE`. The number and native seed are different source
identities. The native generator works without this table.

The AppKit host targets macOS 11 or later on the current Mac's architecture.
Its completed-board verdict calls the same constraint verifier as the CLI.
New Random Puzzle runs generation in the background; Copy Puzzle Identity
uses the same canonical identifier formatter as JSON. Completing a native
random puzzle does not advance original numbered progress.

After the owner supplies the complete private `Resources` directory, run:

```sh
bash Build-and-Run.command
"build/Sherlock Native.app/Contents/MacOS/SherlockNative" --cli generate --seed 42
```

That resource pack includes the 128-byte `PatternPresets.bin` (sixteen eight-row
background patterns, bit 0 at the left), the 2304-byte `SherlockFont.bin`
(256 advance-plus-eight-row glyph records), `Menu*.png` artwork, and the table
and image/audio resources. Original pixels are loaded from private files and
are not embedded in this source. GUI startup rejects missing or malformed
pattern/font data.

The bundle dispatches `--cli` before creating `NSApplication`. Its standalone
CLI is built separately and needs only a C runtime. Apple Command Line Tools
are required to compile the Mac host. The app has been source-reviewed here,
but **has not been built against an Apple SDK or run on a Mac**. Original hint
ordering/wording, exact victory RNG initialization/pacing, and remaining
tournament and editor presentation details are still fidelity gaps. This example is not a
claim of complete original equivalence.

### Presentation and clue inspection

The canvas uses the recovered bitmap font for small ASCII text, with Unicode
and native-dialog fallbacks. Default-color menu artwork comes from the private
resource pack; custom colors use role-based drawing. MENU retains the board
behind the left control panel, while TIME pause and tournament handoffs hide it.
The original solved-board acknowledgement leads into native tile trails and
sixteen-particle bursts, preserving their original movement rules and sound.

`sherlock_victory` is a bounded, allocation-free event iterator with an explicit
32-bit RNG state. Each event is a clear, full-tile stamp, sixteen-tile burst
frame, bounded selection wait, or done. The host owns clipping, accumulation
and pacing. The native starting state is derived from the challenge identity;
it is not the unexported original post-generation RNG state. Skip finishes the
current burst. A stationary tile never blocks the event loop.

Left-clicking a clue opens an authored, non-mutating explanation using current
SHI thumbnails and stable row/item IDs. This Watson-inspired aid adds no time
penalty; ordinary elapsed time continues. Right-click archive and drag gestures
retain their original roles. Undo, Hint, Pause and clue-bank switching also
have state-aware native menu commands and keyboard equivalents.

### Verified hint support and original timing

The selector first follows the displayed bank's vertical/horizontal slots.
Its local SAME, NOT_SAME and LEFT_OF priority has bounded original matches;
other tuple checks and the stronger all-public-clue fallback remain native.
The original's hidden-answer repair pass is deliberately replaced by explicit
consistency failures. This is not a claim to reproduce all original hints.

A selected target is frozen before support extraction. The new proof module
first establishes consistent candidates/givens/row rules/clues, then proves the
exact opposite move impossible. It greedily removes redundant clues under one
shared node budget, considering the selector's direct clue last. Completed
reduction is deletion-minimal relative to the frozen background, not globally
smallest or a human deduction trace. A partial reduction may still retain
proved sufficient support. Inconsistent premises never certify a move.

Show why uses current SHI pictures and pages through retained clues without
changing candidates, card organization or the selected move. The host requires
a proved result before offering the hint. Candidate marks remain explicit
player assumptions; earlier edits have not thereby been verified. The C replay
API rechecks stated premises, and external callers must additionally bind them
to the intended challenge. CLI check-hint does so using canonical constraints;
it accepts an exact remove/choose target, not supplied clues or proof claims.

The original fee timing is now corrected: acknowledgement applies the move,
then adds 30 seconds; the clock display stays frozen while elapsed time counts.
Expiration is deferred until acknowledgement and takes priority over final
success. The host samples monotonic time immediately before terminal edits so
a between-callback deadline is not lost. Undo never refunds the fee. Native
no-hint/contradiction/unresolved notices remain free, whereas the original also
charged its no-hint message. AppKit behavior still requires a Mac run.

### Image editing and file persistence

The image editor separates working artwork from file persistence. **Done**
keeps edits in memory; **Save** writes the complete SHI file. Save or Load,
followed by Done, accepts that filename for the player. Abort restores the
overview entry images and association, while leaving a completed file Save
intact. Dirty state follows accepted editing operations, including painting
the same color. Opening and accepting an untouched pixel editor stays clean.

Merge supports a selected source/destination row or only the empty image.
Other images and clue markers are preserved. Players > Done reloads the
associated SHI even when the player stays the same; a profile with no filename
inherits the current working set. PLAY and RESUME retain working artwork.

Version-2 native preferences store player metadata and selected filenames,
excluding newly accepted session pixels. Existing version-1 artwork is kept
as a migration fallback until an explicit replacement is accepted. Unsaved
edits should be saved before quitting or returning from Players.

Native Abort deliberately restores all 46 records, correcting the original's
37-record rollback hole for loaded clue markers. Failed/canceled saves retain
dirty state, and Merge does not change the selected filename. These data-handling
corrections are explicit differences from original behavior. The portable
transaction core is independently original-matched for 43 normal operations;
native profile migration and file-panel interaction still need a Mac run.

## Test scope and private resources

```sh
./check-portable.sh
```

This builds with strict C11 warnings and runs SHI, image-transaction, bitmap-font, clue-description,
victory-event, state, hint-support replay, solver/generator and CLI tests. The CLI tests use an
independently implemented public-JSON solver.
Python is needed to run that test harness, not to run the product. With an
owner-supplied table, additional tests exercise hint deductions and every one
of the 65,536 recovered initial states and accepted original answers. Without
it, the private corpus tests are explicitly skipped.

No original executable, table, SHI artwork, manual, pause image, audio,
font/menu pixels, screenshots, save files, runtime states or byte-retaining database is included
in this directory. Do not add those resources to Git or tool packages.
The SHI fixture bytes in tests are authored synthetic vectors.

The original title, manual and artwork remain attributed to Everett Kaser and
the authors identified in the owner's supplied files. Watson and Bombe were inspected as
prior art; no upstream code or assets were imported. The new generator extends
the constraint machinery authored during this reconstruction. This source
example was written directly in C/Objective-C, not generated by a UIL compiler.

## Browser companion and agent JSON

The authored [browser companion](web/README.md) runs the retained puzzle rules,
native generator, verifier, game state and hint evidence in plain JavaScript.
Generated puzzles and built-in symbols work without any original resources.
Open `web/index.html` with the neighboring files, or serve the editable source
from this example directory:

```sh
python3 -m http.server 8000 --bind 127.0.0.1 --directory web
```

Open <http://127.0.0.1:8000/> and reload after editing source. Python serves
static files only. The game has no compiler, emulator or server dependency.
An optional packaging command creates standalone HTML and a Space fragment:

```sh
node web/build.mjs /tmp/sherlock-browser
```

The browser supports candidate edits and restoration, clue organization,
25-action undo, timers, verified hint offers and supporting-clue inspection.
Local SHI artwork and the private numbered table can be selected through file
controls; those original bytes are neither bundled nor uploaded by the game.
Browser sessions and bug captures preserve public puzzle/state information.
They exclude original artwork and complete table payloads.

The Agent JSON panel exports public challenges, checks proposed answers and
deductions, and exposes a read-only analysis result. Verification and analysis
use the native `sherlock-cli-1` response format. The in-page `SherlockReplica`
API follows the same state and verification paths as the UI. A malformed input,
rejected answer, inconsistent premise set and exhausted budget remain distinct.

Run the browser boundary and independent native comparisons from here:

```sh
node web/tests/core-boundaries.js
node web/tests/state-contract.js
node web/tests/proof-contract.js
node web/tests/assets-test.js
node web/tests/protocol-contract.js --native
node web/tests/parity.js --skip-private --report /tmp/sherlock-browser-parity.json
```

The resource-free parity receipt records 114 oracle fixtures and 4,360 counted
equality comparisons, including all 1,728 relation tuples and 1,116 state
transitions. Three complete generated games use 455 accepted hints; all traces
contain 458. The protocol suite adds 63 boundary checks and 54 complete native
JSON comparisons. Authored notes and receipts are under
[web/evidence](web/evidence/README.md); the separate
[browser extension ledger](docs/FEATURE-COVERAGE.md#browser-companion-extension)
keeps implementation and execution claims distinct.

This is finite native-C-to-JavaScript evidence, not renewed original-program
qualification. Browser UI/host results are recorded separately. Browser image
editing, audio, profiles, tournaments and original presentation remain gaps.
The native AppKit build and interaction gate is still open. The complete
original/private resource pack remains excluded from this public source tree.
