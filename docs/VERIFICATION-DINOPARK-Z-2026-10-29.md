# DinoPark Z native acceptance, 29 October 2026

This is the initial acceptance record. The later
[reliability follow-up](VERIFICATION-DINOPARK-Z-RELIABILITY-2026-10-29.md)
records fixes, the committed 0.23 compiler retest and current claim limits;
the original observations below remain historical evidence.

Luna (`gpt-6-luna`) independently drove the actual Z player against disposable
original-game copies, through the real v0.23 development UDC. Native memory,
source events and stored screenshots were checked separately from the public
player output. The owner independently inspected the earlier timeout's stored
database and compared the full source-test failure identities to PR #18.

This is a development integration over PR #18, not a release. The UDC owner's
`Inspect fDisBull repo state` chat and current source were inspected: its 0.23
work is separate and uncommitted. Native acceptance used a private, hash-bound
snapshot of those actual modules with the installed 0.22.0 runtime and this
branch's promoted scene modules. It did not use a replacement or mock compiler,
and it did not change the shared installation. A clean, combined v0.23 release
installation still needs its own acceptance.

## Identities and preserved evidence

| Item | SHA-256 |
|---|---|
| Original/emitted DINOPARK.EXE | `2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c` |
| Original/emitted VARS.DAT | `5e4b32d6e4afd060d72da79bfcac27fdca493905a7e19e299729e31431a1d153` |
| Tested native DOSBox-X backend | `1b0ec91f8a97fb34f336f898c3e9e02bf4559f314b2e4f92f3597f0c52c92277` |
| Tested UDC module snapshot | `4910109069aa6f2cf36b8ede6b084c4fb0046fa12b0e2a48223ca4802a875867` |
| Tested UDL block module snapshot | `4d478ddc27c18c5d86b16e6dd7f633d21d6c7f3aca583b16d6b8e77165fad78c` |
| Native scene module | `4a2d3c4059fdbd74ba17273e5ac6928a2ffec6ad521a1c8f21f62bbac49cdc51` |
| Z module, final inventory addendum | `e6596a6eb5b3e9d768cafb6db8bd895e5e5592d7cc26d69026bf56586f8f35fe` |

The earlier full core batch and three bank repetitions used Z module
`b37eb9a15e58bfc653f43941e3df9a71b23cf0a1bdfe1e44ad4348cfba506e7d`;
the final addendum changed only the inventory object's consumer alias. The
native scene implementation remained unchanged. Original adapter/profile
provenance is committed under `src/fdisbull/data/`; private run receipts bind
their input, emitted-file and profile hashes.

Raw artifacts remain outside Git under the locally retained
`luna-z-acceptance-20261029-01` evidence directory. Principal records are
`final-core-batch.md`, `final-core-integrity-audit.json`,
`targeted-addendum-20261029.md`, `consumer-inventory-alias-addendum.md` and
`inventory-alias-comparison.json`. The failed first batch and its screenshots
are retained too. Game assets, raw memory, databases, native saves and personal
host paths are excluded from this PR.

## Native results

| Route or behavior | Observed original-backed result |
|---|---|
| Bank | Cash/debt `5000/5000 → 0/0 → 5000/5000`, then return to office. Independent direct-original baseline matched. |
| Land | $500 purchase: cash `5000 → 4500`. |
| Coelophysis | $1,250 purchase: cash `4500 → 3250`; one dinosaur in the occupied pen. |
| Original inventory screen | At the qualified pre-opening $3,250 state: 1 dinosaur, 1 pen, 1 pen in use. Original event and recognized screen agree. |
| Wood fence | $1,000 purchase and occupied-pen placement: cash `3250 → 2250`. |
| Tour guide | Guide count 1; listed $900 monthly wage; no upfront purchase charge. |
| Food | Twenty small feeders for $500: cash `2250 → 1750`, stock `0 → 20`, food expense `0 → 500`; one confirmation. |
| Opening/time/status | Full batch opened at day 5/cash 2788; one bounded interval reached day 6/cash 3071. Status came from the original game. |
| Operating inventory alias | A separate fresh final run opened at day 5/cash 2410. `check inventory` and `check status` had exactly equal native snapshots: one guide, 20 feeders, one Coelophysis in pen 10. |
| Native save/load | New `zpark` save, fresh guest load and status passed. All 20 declared native save fields matched live state and fresh loader. |
| Existing native save | Read-only `first` fixture loaded; all 20 declared native fields matched. Another private save/fresh-load cycle passed. |

Income and elapsed in-game time depend on the original run. These observations
are not deterministic income guarantees, full calendar/season coverage or a
complete campaign. All eight implemented destinations were reached in these
bounded routes; every possible route pair and every shop item were not tested.

The three full core runs independently matched **all 184 artifacts** across
source → UDC output → runtime copy. All 192 files in their disposable source
copies matched the canonical original; subsequent inventory/bank copies also
passed preservation checks. The original `first` fixture remained unchanged
(`2600403d5329847c7bc51a5fab6fd07fefe8fb3207a2787c10be9f8b42551194`).
The full opening run's new native save was 4,153 bytes with SHA-256
`638d0c0b6c3621ac8b9cfd1112f639ad7537aff749f021b1f777c22bf8261fdf`.

The independent direct-original verifier also reopened its project, exported a
real scene overlay from stored state and demonstrated that a patched child
version could not reuse the parent scene. Its receipt reported success and
unchanged source; the re-exported PNG was 67,411 bytes.

## Crash and friction ledger

1. **Unresolved bank entry timeout.** The first example-module launch reached
   office normally, then `go bank` raised native `SceneError: Scene operation
   timeout` (observation `53c4f90e02d94f7b91f80099551e844b`). Z returned incomplete,
   effects unknown, and did not retry. Stored-frame inspection showed a zoomed
   General Ledger view, while queued click metadata recorded driver `(102,26)` /
   guest `(51,26)`. This suggests a readiness/dispatch issue but does not prove
   a cause. Native child exited 0; no process crash or outer transport hang was
   demonstrated. A subsequent full core bank pass and **three separate fresh
   repetitions, 0 timeouts in 3**, do not establish a fix. Follow-up: capture
   mouse state, entry readiness and frame/input ordering at the native boundary.
2. **Missing shutdown receipt.** Bank repetition 03 completed every player and
   oracle step and its outer process exited 0, but `z-session.json` was absent.
   A process-table check found no remaining guest/launcher for that workdir.
   Other final runs recorded owned child return codes of 0. Do not treat this
   missing cleanup observation as a confirmed clean inner shutdown. Follow-up:
   investigate the player's one-second termination grace and make receipt
   finalization reliable without extending failed-request execution indefinitely.
3. **Narrow physical inventory qualification.** The inherited count-screen
   path refused after operating income changed the qualified state. The Z
   consumer now resolves `check inventory` after opening to the existing native
   operating report; Luna verified exact report equality on the final module.
   Broad post-opening physical inventory-screen coverage remains open.
4. **Modal notice coverage.** The bridge exposes a recognized quarter popup as
   a context with only its acknowledgment. Protocol tests cover that selection,
   but no quarter notice appeared in the native acceptance routes. The parking
   hint and unknown modals remain unqualified; do not force a guessed handler.
5. **Vegasaurus funds.** The cold catalogue listing and encyclopedia commands
   are connected; the available park funds were below $25,000. This batch did
   not test sufficient-funds purchase/refund behavior.
6. **v0.23 dependency.** The tested compiler is a named development snapshot,
   not a published release. This PR intentionally fails without those APIs.
   Re-run the combined installed-package native gate when the compiler lands;
   opaque byte reconstruction must not become a semantic equivalence claim.
7. **Provenance test portability.** The first Linux CI run had one new failure:
   Python 3.12 and 3.13 serialize empty AST fields differently. On the Mac,
   `ast.dump(..., show_empty=True)` reproduced the Linux hash exactly. The
   provenance test now checks the exact original class source with a stable
   SHA-256 instead; it was independently compared with the retained original
   adapter. The Python 3.13 AST hash remains labeled in provenance metadata.
   Native scene and Z worker code are unchanged by this correction.

The separate crashed-chat investigation reported conversation-history HTTP 429s
and incomplete local history. That evidence does not establish an fDisBull
process crash or explain the bank timeout; no crashed chat was repeatedly
reopened as part of acceptance.

## Source and package checks

All 12 new protocol/provenance tests passed. They test interface guards and
event interpretation; they are not substitutes for the native results above.
The full `python -m pytest -q` run reported **1,445 passed, 116 skipped, 13 failed
and 23 errors**. All 36 failure/error test identities exactly match the PR #18
baseline; there are no new failure identities. The local full suite remains
not green. The existing failures include host-incompatible ELF fixture setup,
unavailable optional managed support and the pre-existing CLI case.

The ready local launcher additionally passed the fresh bank/repay/borrow/office
cycle without the optional oracle enabled, in 7.55 host seconds including
startup and compilation. This is one observed smoke run, not a timing guarantee.

Built the core wheel, standalone player wheel and tool source ZIP offline.
`scripts/check_dist.py` passed with 139, 10 and 412 tool-only entries,
respectively. Both promoted modules and all six profile/data files matched
their source bytes in the core wheel and source ZIP. Imports from the extracted
core wheel loaded the packaged recognition profiles successfully. The excluded
examples directory is not a runtime dependency. These are package-content and
import checks, not combined v0.23 installed-native acceptance. Remote CI and
combined v0.23 release acceptance remain separate gates.
