# 0.24 development verification

## Finalization as 0.24.0

The release source promotes the tested candidate to `0.24.0` in core/player
package metadata and `fdisbull.__version__`, and updates release-facing text.
The development receipts below retain their original version labels and hashes.
In particular, the native receipt's `__init__.py` hash belongs to the dev0
version string; it must not be described as the final version bytes. The
functional runtime modules, updated skill and native backend retain their tested
contents. Final package checks and exact-commit ordinary/native Linux CI gate
the release tag. Publication and system activation are separate steps.

The final-version local selection covering output, advanced CLI, skill/index,
source/player packaging and Z/provider integration passed **130 tests**. The
development full-suite/platform limitations below remain recorded unchanged.

The first main-push Linux attempt (`d31c175`) passed the ordinary suite
(1,588 passed, 103 skipped), stable native tests (448 passed) and layers native
tests (759 passed). Its layers offline-kit skill gate failed before spawning
Python: a relative interpreter path was retained while probes changed working
directory. The dependent unified job was consequently skipped, and that attempt
did not qualify a tag. The gate now makes the selected launcher path absolute
without resolving it out of its virtual environment. Two real-venv regressions
cover explicit relative paths and a relative PATH entry. The corrected source
requires fresh exact-commit ordinary/native CI before tagging.

## Development acceptance record

This records `0.24.0.dev0` from the local `codex/v024-output-artifacts` worktree.
The source contains uncommitted candidate changes; its merge-parent HEAD is
`1351e1ce66f944788731260c125a5bf7d1f7dfa0`. Runtime hashes bind the receipts below
to the actual tested files. This is candidate acceptance, not new tag CI,
publication or a system installation.

## Integration inputs

PR #18 head `c107d1576d46d7dc353c8043cb81be5005e8926b` and PR #19 head
`8540429bec52e5ae144ca0076b48256beaeb933c` each had successful ordinary and native
Linux PR/push checks before local integration. They were merged in that order
with ancestry preserved. GitHub PR/main state was not changed by these local
merges. The final combined candidate still needs its own ordinary/native Linux
CI before a release tag.

## Output retention

The same 53,583-byte authored IL input used for the earlier amplification
reproduction completed on the candidate. Its previous stdout was 13,152,686
bytes. The candidate emitted a **475-byte** descriptor and retained all
13,152,685 JSON bytes, exactly equal to the old output without its wire newline.
Its `execution.complete` is true while inline `complete` is false. Fresh-store
readback and a new private export verified its digest. Selecting an oversized
event list returns an incomplete descriptor without a partial value.
See [the sanitized receipt](evidence/output-024/amplification.json).

After the real DinoPark session exited, the core `files` query on its private
UDC project returned **490 bytes** at a 4,096-byte budget, retaining the original
37,545-byte response. A separate installed-candidate process selected the exact
182-resource count in a **304-byte** response. The underlying result had no
execution-completeness field; the marker correctly kept it null. No guest action
or original query was repeated for retrieval. See
[DinoPark output qualification](evidence/output-024/dinopark-output.json).

The tests cover actual wire-byte boundaries, escaped Unicode, invalid
configuration/IDs before mutation, failed serialization/storage, oversized
errors, server recovery, process restart and bounded selections/ranges. A real
private project patch whose reply cannot be retained creates exactly one child
version, preserves its parent and leaves the input file unchanged. The artifact
tests cover quota headroom/stale files, concurrent deduplication, corruption,
private paths, export collisions and unsupported-platform refusal. These are
output/evidence checks, not evidence that the inaccessible ChatGPT conversations
were caused by large replies or have been repaired.

## Fresh native DinoPark

Two actual headless DOSBox-X runs used the frozen candidate source and genuine
Python 3.13.17 on macOS ARM64. Backend SHA-256:
`1b0ec91f8a97fb34f336f898c3e9e02bf4559f314b2e4f92f3597f0c52c92277`.
The original 191-file game directory, including eight prior saves, was checked
before and after and remained byte-identical. UDC emitted 183 byte-identical
artifacts and excluded original saves; its semantic qualification remains
`original_bytes_only` with zero recovered semantic blocks.

The first route completed **21/21** actions: bank repayment/borrowing, land,
dinosaur, fence, guide and food purchases, park entry, status/inventory checks,
time advance and native save. A second new process/directory used the original
native loader; its status and inventory checks passed and all **20 declared
save fields** matched the captured live values. Both session receipts report
clean completion and teardown. Private evidence includes 26 stored screenshots,
player/native observation traces and the native save bundle. The adapter still
keeps a separate open/closed operating status unknown: park-view/time success is
not proof of that independent field or a profitable complete campaign.

The first setup attempt resolved the virtual-environment launcher to base
Python and failed before a native work directory or action existed. Its receipt
was preserved; the corrected run used the exact venv launcher. No uncertain
game action was retried. The sanitized native receipt is
[here](evidence/output-024/dinopark-native.json); raw evidence remains private at
`/private/tmp/d24-dp-etwjx51v`.

## Tests, packages and skill

The required repository command was run with the genuine native backend and
LLVM on PATH: `python -m pytest -q`, with private basetemp and concise tracebacks.
After adapting the signature-catalog CLI test to retrieve a now-oversized result,
the final full rerun reported **1,645 passed, 21 skipped, 2 failed and 23 setup errors**.
The suite is not green on this Mac. The remaining two failures expect ELF output
from the Mac compiler or use Linux linker arguments; setup errors are the same
Linux ELF/platform-call fixture failures observed in the preceding run.
Source/player/test manifests matched at the start and end of the rerun. The log
SHA-256 is `eea3e5346fd52804a08e422fc20e5503a6c7966d21b21a4c13774618fb5d1a9b`;
the private log is `/private/tmp/t24-final-BluHTB/pytest.log`.

After that full run, the source-archive allowlists/guard were tightened to
require exactly the four new sanitized receipts; their focused tests and the
rebuilt archives were checked separately. Runtime source did not change.

The final focused output, advanced-CLI, skill-gate and distribution selection
passed **75 tests**, including a translating-stream wire-budget regression.
Core/player wheels,
source tarball and tool ZIP passed distribution audits. In a separate private
extracted-source check, the output, skill, Z/player and distribution selection
passed **133 tests**. In the installed-package check,
all **141 core and 5 player payload files** matched their wheels
and frozen source. Installed output spill, inspection, selection, range and
export checks passed with verified hashes/private modes. A player-only
environment imports no core package; empty/whitespace backend commands exit 2
without a traceback. The system's published 0.23 installation is unchanged.

The official skill validator passed. The installed-wheel skill gate passed
**8 resources and 15 local links**. A separate fresh Luna exercise used bundled
discovery, retrieved saved state in a new process and, after a hint to export
privately for a missing aggregate, counted 400 events without dumping their
contents. It first encountered a non-private store and recomputed the supplied
pure IL plan after correcting permissions; that was not a native action retry
or a cold gameplay benchmark. Its hidden-pot answer kept the clue unverified
until a search and inventory/state observation. The directed exercise does not
establish that every model will choose an optimal workflow unaided.

Only authored documentation and sanitized metadata receipts are included here.
Original inputs, saves/states, project databases, full outputs, raw native
captures, private environments and backend binaries remain outside Git and tool
packages. Package hashes and full source inventory remain in the private build
receipt under `/private/tmp/b24-final-02`.
