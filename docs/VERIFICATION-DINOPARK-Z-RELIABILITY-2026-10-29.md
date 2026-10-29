# DinoPark Z reliability follow-up, 29 October 2026

This follows the [initial acceptance](VERIFICATION-DINOPARK-Z-2026-10-29.md).
The changes address normal shutdown receipt loss and add an explicit bank
input-readiness barrier. The historical intermittent bank failure was not
reproduced in the baseline investigation; its exact cause remains unknown.

## Changed mechanisms

Normal `ProcessBackend.close()` now closes the successful worker's input and
waits up to three seconds for clean EOF finalization. Previously it sent
SIGTERM immediately, while the native loop wrote its receipt only after normal
return. A real subprocess regression failed on the old code because its EOF
receipt was never written; it passes with the new close path.

A failed exchange skips EOF grace, terminates the worker with a one-second
bound, then forces cleanup. On POSIX each worker has an owned process group;
cleanup also stops its descendants after worker death. A real-child regression
checks that a crashed worker cannot leave its child holding the output pipe.
No PID-discovery scan is used to select processes for termination.

Native and outer receipts are written initially as unfinished and replaced
atomically. Controlled interruption gets `interrupted`, `complete: false`;
cleanup observations are recorded after cleanup. The outer receipt records
spawn/ready state, pending commands and confirmed purchase commits. A SIGKILL
cannot run a finalizer: its retained record remains explicitly unfinished.
An interrupted transaction is not a clean session or an automatically retryable
action. Source event journals and the original game remain the effect authority.

Bank entry now checks a released pointer, makes a frame/mode-bound move to the
known bank target, executes 150 guest milliseconds, checks stable/released
input, and reasserts the office before one original named press. It does not
retry a timed-out press. Intent is journaled before this preparation. Bank
acceptance reads the existing native result fields, also with the oracle disabled.
The original `TextScene` business class remains source-identical; no money,
loan, food or dinosaur rule was replaced.

## Committed compiler and baseline

The real compiler core is committed 0.23.0 source
`ed89abca061964385b176537bc9fd275dd02afa5`; it was checked clean and matched
remote main. Native tests use that core, replacing the old UDC module snapshot.
The retained genuine native backend SHA-256 is
`1b0ec91f8a97fb34f336f898c3e9e02bf4559f314b2e4f92f3597f0c52c92277`.
The test Python/runtime prefix is retained 0.22.0; this is not an installation
or publication claim for an official 0.23 release.

Luna froze the old PR #19 consumer at `ac254aa` before production edits. Two
fresh original-backed Z bank cycles passed, yet both lacked the inner native
receipt. Their outer receipts showed child exit 0. A separate old direct
original verifier passed. This reproduces the receipt gap independently of the
new implementation and without an optional oracle.

The parent separately ran twelve fresh unstaged office/bank/office cases, plus
six unstaged and six staged cases restored from an owned native office
checkpoint. All passed. The checkpoint probes are assisted diagnostic replays,
not ordinary fresh gameplay. Their first attempt hit the native framebuffer's
documented restore-readiness boundary before any bank trial; the corrected
probe let a frame complete after restore. None reproduced the old General
Ledger/timeout event. Movement/press ordering remains a hypothesis about that
historical event, not a demonstrated root cause.

## Luna's native retest

Luna independently froze the modified provider and player, then drove actual
original-game copies through the committed compiler. Eight fresh bank cycles
passed on the first candidate (four oracle off, four on); another oracle-off
cycle passed after the spawn/ready receipt metadata correction. All nine inner
and outer receipts completed, every native child exited 0, and numeric native
readback showed cash/loan `5000/5000 → 0/0 → 5000/5000`.

The opening route also passed land, dinosaur, fence, guide and food purchases,
park opening, time/status and native save/fresh load. All 20 declared save
fields matched. Its `check inventory` result was the operating summary, as
designed after opening; this is not an additional physical inventory-screen
qualification. All 184 compiler artifacts matched their recorded hashes.

Luna caught a verifier regression in the first candidate: pointer preparation
was logged before the intent, so direct `--verify` correctly failed despite
the native route, balance comparison, restart PNG and patch-isolation checks
being present. The call was moved after the intent; the gate was not weakened.
The original failed verifier and corrected-run evidence are retained separately.

The corrected direct-original verifier exited 0: native receipt completed with
`ok: true`, ordered `intent → pointer_prepared → result`, source unchanged and
patch-child isolation verified. Its stored/reopened 67,411-byte overlay PNG
has SHA-256 `d27657a137d2cdb507cf1ba10ad93f2eb1dcd7e3493f9ada9d429895bc7f214e`.
One further fresh Z bank cycle on that final scene source passed with both
completed receipts and child exit 0. This makes ten Luna bank cycles overall;
the preceding nine remain attributed to their earlier source snapshots.

Final native scene SHA-256 is
`332e0bb88db316c9a502632ae76b9aa74b81a6306b613d2eac85491ac6d72cb1`;
final Z worker is
`de6896a43764a0b5ee41f88f8b967773ad96c081c44f4a96bb3c5ec5803533da`.
The unchanged player fixes have hashes
`f92d10b2ddc07b6e72320d3a07ad3efc2c3fa9d2eb1bbcd794ebe24d3db47afe`
(`live.py`) and
`1279b110a9c51a47bff54e4261a9ea33f6af462e7be2c4e99e8194a35904a8f4`
(`player.py`). The later scene change only moves preparation after the intent;
the already-tested lifecycle and bank-effect code are unchanged.

Luna's final audit compared every emitted file directly with the canonical
original: 184/184 byte-identical, no added paths. Both full disposable input
copies matched all 192 canonical files. The only omitted compiler inputs were
the eight original saves; all eight remained unchanged in the canonical game
and full input copies.

| Lifecycle case | Observed result |
|---|---|
| Idle SIGTERM after look | Both receipts interrupted/incomplete; child exit recorded; owned group absent. |
| Request timeout with private injected delay | Pending `go bank` retained with unknown effects; both receipts interrupted/incomplete; child and group cleaned. The delay was before the native scene handler, not a native bank click. |
| Worker SIGKILL after ready | Outer `ready` and native `running` receipts remained unfinished. Group cleanup removed the child; the bounded follow-up found no surviving group or pipe holder. |

Raw evidence remains private in `luna-z-reliability-20261029-02`, including
`baseline-report.md`, `final-candidate-results.md`, `final-fix-addendum.md`,
`final-fix/source-oldsave-preservation-audit.json`, the frozen candidates,
original/emitted resource inventories and per-run receipts. No game bytes,
native saves, database files, raw memory, screenshots or personal host paths
are added to Git. The previously failed verifier receipt is preserved too.

## Package and source checks

A private combined candidate is assembled from the exact committed 0.23 tree
and explicitly hash-recorded Z/provider/player files. Its 0.23 core and player
wheels were installed into a new private target. The player ran the original
bank/repay/borrow/office cycle with only that installed target on `PYTHONPATH`,
without source-path or UDC-snapshot overlays. Both native and outer receipts
completed, with owned child exit 0. This is combined-candidate installed native
acceptance for that route, not a published-release or full-game claim.
The final installed run used the exact final scene/worker hashes above and
reported core version 0.23.0. Core/player wheels and the tool source ZIP passed
0.23's archive policy checks with 143/10/444 entries. Packaged runtime files
matched the selected source bytes; checkout-only examples remained excluded.

Affected checks passed 62 tests with one skip. The required full Mac source
suite reported 1,452 passed, 116 skipped, 13 failed and 23 errors; the same
36 failure/error identities match the previous baseline. The local full suite
remains non-green. Final package and remote CI readbacks are recorded in PR #19.

See [0.23 integration and proposed 0.24 priorities](Z_PLAYER_INTEGRATION_0.23_0.24.md)
for the provider lifecycle, effect binding, benchmark and documentation follow-up.
