# 0.26.1 integration verification

This record accompanies the 0.26.1 source candidate. The intake baseline is
main `f159252761150ca2dd95eb12e16e515ce33f74fd`, which already contains PR #34
(`9e36da70ffd59dd3484a391b8132b809ef9bf87c`) and PR #35
(`ff4f08a6d4b337070b6e23ba403391366fb1e3e9`). PR #33 is integrated with its
reviewed head `8655d1c30a318323e5e1de8488bd92899e3ef96c`.

## Required acceptance

1. Preserve the main implementation of read-only reconciliation, unknown and
   partial original effects, selected DOS process termination and conservative
   access-stop interpretation.
2. Run focused combined source checks and both installed skill gates. Build
   and inspect core/player wheels, source archive and tool ZIP from the frozen
   candidate; check source/payload identity and private-input exclusions.
3. Qualify the current layers backend against its exact upstream baseline and
   applied source manifest, then verify the combined candidate on an owned
   private DinoPark copy. Keep original inputs unchanged, bind runtime/backend
   identities, and retain failed, unknown or budget-stopped results explicitly.
4. Require ordinary and all three native Linux jobs on the exact final source
   commit before creating the release tag. The layers offline-kit check must
   use genuine dependencies and Z3, and both bundled skill gates must pass.

## Source and evidence boundaries

Earlier PR reports remain attributed evidence at their recorded source/runtime
identities. They are not substituted for a fresh combined native check. Native
checkpoint restoration and journal reconciliation have separate obligations:
restore may change the game state, while the reconciliation interval must be
read-only. Matching observations do not recover a missing reply or certify a
partial original action.

## Fresh combined source and package checks

The frozen runtime cut is `85ea5264f658db15ee75af8c279212e36fd0880c`, with
core and player version 0.26.1. Later evidence, archive requirements and README
wording do not replace that identity; final package checks must confirm every
core/player package file remains identical to the tested runtime cut.

- The combined required-native selection passed **208 tests, zero skipped**.
  It covers reconciliation, durable recovery, continuations, DOS guest exit,
  conservative watch stops, skill/discovery, packaging and output behavior.
- An independent immutable-source review selection passed **98 tests**.
  It did not substitute for native execution or package checks.
- All four runtime-cut archive guards passed; the source ZIP's **568 files**
  matched Git. All **161 core and nine player package files** matched the
  source and installed wheels. Installed skill gates passed: investigation
  **10 resources / 27 links**, guide **8 resources / 13 links**.
- A fresh Mac ARM64 layers backend was built from upstream
  `029bd65c5dcc7cdc7f2e14e35278620d9707d969` and the current PR #35 layers
  patch. All **33** source-manifest files matched. The binary SHA-256 is
  `bcf318de2a22d49d1b28888a312e12b774cf1f041fdd8862fc4ab3335ea59b60`.
  Its separate authored exit/watch/state/layer selection passed **13 tests**.
  These selections overlap; their counts are not added together.

## Original DinoPark qualification

One actual native guest completed all ten planned phases and the 19-check
final audit in **88.97 seconds**. It used the frozen packages, genuine native
dependencies, the new backend above, a private copy of the original game and
the unchanged funded26k input. Actual worker imports and all **170 package
payloads** were checked against the installed wheels and source. This was an
assisted checkpoint investigation, not a new-game campaign.

The run recorded **77 provider requests: 65 observations, eight actions, three
loads and one save**. Eight Player commands include current and superseded
branches. A confirmed purchase followed by a declared client readback failure
remained journaled; one-observe reconciliation preserved its effect without
another BUY. Only a later explicitly requested ACK completed the pending
return. A durable restore certificate survived the following client read
failure; the CLI branch performed exactly one LOAD, and reconciliation finished
the local rewind without another. A completed-restore consumer read error also
reconciled without a new load or history branch. Lost and incomplete replies
remained unknown/unresolved and were not retried as purchases.

All **ten** reconciliation intervals forwarded exactly one provider observation
and preserved native20 saved ranges, frame and guest ticks, state revision,
worker/native identities, run and session. Four distinct confirmed purchases each changed cash by -$500 and small-food
stock by +20, with one confirmation. Explicit restores separated the test
branches. An independent parent audit checked the raw wire/native windows,
these deltas and original input inventories without replaying the game.
Three separately requested certified restores passed their native20 proofs before 100 guest milliseconds of
input-free preparation. Four original orders succeeded and later office travel
worked with the same guest. A journal reconciliation after that intervening
action returned `not-needed` / `no-unresolved-readback`; it did not perform a
new old-checkpoint load or certify an earlier restore again.

The declared read/lost/incomplete-reply faults were verifier injections outside
the actual JSON transport. Game effects, captures and native restoration used
the original executable. This is bounded recovery acceptance, not general
deterministic replay, whole-game equivalence or a new original-intent completion
certificate. The guest ended through explicit controller cleanup; worker and
emulator exit codes were zero, receipts/cleanup completed and no owned process
remained. Natural DinoPark program termination was not tested. PR #35's actual
guest-exit contract was exercised by the separate authored native cases.

## Preserved initial environment failure

The first attempt used a package-audit environment whose system-site setting
did not inherit the managed runtime's Pillow dependency. The worker failed
while importing `PIL.Image`, before starting DOSBox or sending a game action.
Its unanswered observation and unknown journal were preserved. No original
action was retried in that journal and no native guest was consumed.

A separate isolated environment installed the same candidate wheels and the
declared genuine dependency wheels offline. Module origins, dependency versions
and payloads, PNG encode/reload and Z3 were checked before the successful new
trial. The package-audit helper was corrected and rehearsed in a new directory;
the original failure record and environment were not rewritten.

## Final acceptance readback

The [sanitized summary](evidence/integration-0261/verification.json) records
runtime identities and claim limits. Raw game copies, save inputs, native
states, transcripts and project databases stay private outside this checkout.
Final source/package checks and exact-final-SHA ordinary and complete required-
native Linux CI are separate post-evidence gates. GitHub Actions and the
annotated tag record their final readback after the commit exists. Publication
and a shared installation update are outside this task.
