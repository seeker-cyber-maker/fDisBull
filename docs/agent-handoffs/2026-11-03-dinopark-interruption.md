# DinoPark interruption recovery and handoff — 2026-11-03

This handoff continues the original-backed DinoPark Z investigation. The initial
documentation contribution records a fresh project audit and a bounded analysis
of the remaining purchase presentation issue. A subsequent user-requested native
screenshot experiment adds optional lossless encodings; its separate qualification
is linked below. The historical recovery sessions remain expired, and neither
contribution changes purchase acceptance or completes the binary/asset investigation.

## Source and delivery state

| Surface | Verified state on November 3 |
| --- | --- |
| GitLab `main` used for this contribution | `3dc5c50d35f310a3ba39b1cf0cf82a20b8df69f7`; source version `0.30.0` |
| [GitLab !18 / local PR #41](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/18) | Merged November 2 at 11:33:01 UTC; source head `8c7fc4c8a725471e65d879393f9be69a45d4f61d` is an ancestor of the audited main |
| [Standing-probes !31](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/31) | Merged November 2 at 11:33:08 UTC; RFC and skill guidance, not a durable cross-run probe API |
| Installed selector | `/Users/Shared/fDisBull/releases/0.31.0-a12441b`; installation metadata identifies a local `0.31.0` candidate from `a12441b3a6ba9d6816721d59a3d94727bea1eb3b` |

The installed source is not an ancestor of the audited main. Keep the installation,
main checkout and historical qualified source distinct. Reading the installation
record does not independently rerun its reported qualification gates.

A later [installed shutdown-hotfix check](../VERIFICATION-DINOPARK-INSTALLED-SHUTDOWN-2026-11-03.md)
resolves the active selector to `0.31.1-27b388d` plus the user's local headless
`dosbox quit warning=false` host addition. Luna verified eight original DinoPark
entry/title starts and shutdowns, with no reproduced closing popup or crash
report matching those PIDs. A delayed crash from a pre-existing unowned process
is recorded separately. This result does not promote the installed local patch
to tracked !72 runtime source or qualify visible-window/running-park shutdowns.

Between the historical PR head and this main, the selected Park scene/purchase
implementation and Park-return tests are unchanged. The DinoPark Z bridge adds
a witness to successful checkpoint saves as well as restores. The old native
qualification is not promoted to a new native qualification of the full main or
installed candidate.

GitLab's global MR listing returned HTTP 408 twice, including a narrowed DinoPark
search. Direct reads verified !18, !31 and main. This audit does not claim a complete
census of unrelated or duplicate MRs.

## What survived the interruption

The original worktree was clean at `8c7fc4c8a725`. Its source and prior delivery
remain preserved; this contribution uses a new branch based on the audited main.

The recorded Native08 controller/worker/emulator PIDs **95357 / 95403 / 95412**
are absent. The recorded Native07/05/06 controller and worker PIDs are also absent;
the process scan found no Python or DOSBox processes tied to the retained
`park-return-fix` paths. Old `STATE.json` files are historical receipts, not live
session handles. Do not enqueue requests into those old control directories or
claim their breakpoints are currently armed. No ownership transfer, hot reload,
restore or action replay was attempted.

All **60 sealed files** in the Park-return evidence snapshot still match their
manifest. The manifest SHA-256 remains
`9d4e96a028798cf061d25cd71c26da211670474e6b1c8f86a92999db072047e0`.
The canonical `DINOPARK.EXE` still hashes to
`2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c`.
Both supplied research ZIPs remain present at the private paths below with their
previous hashes unchanged. They were read, not extracted or uploaded.

The retained 0.27.0 DOSBox-X binary and the current 0.31.0 candidate's DOSBox-X
binary both hash to
`bcf318de2a22d49d1b28888a312e12b774cf1f041fdd8862fc4ab3335ea59b60`.
This establishes backend byte identity; it does not establish whole-provider
compatibility or a resumed machine state.

## Last qualified result and fresh checks

The [November 1 Park-return record](../VERIFICATION-DINOPARK-PARK-RETURN-RECOVERY-2026-11-01.md)
remains the native qualification: source-bound prepared save, 20 loaded fields,
one normal return, one real matched return followed by a diagnostic readback
failure, wrong-root refusal, failed witness/read-only retry, and idempotence.
Normal/faulted calls took **17.980 / 17.253 seconds**. The successful read-only
retry took **0.0513 seconds**. Four reconciliation calls had zero execution,
input, input-read and restore deltas. These are dated results, not new runs.

Fresh checks on the audited main: **275 DinoPark tests passed in 1.74 seconds**:

```sh
PYTHONPATH=src:player python -m pytest -q tests/test_dinopark*.py
```

No full repository suite, hosted CI, installation gate or new native trial was
run for this documentation contribution. The older full-suite baseline remains
2,256 passed, 133 skipped, 12 failed and 23 errors at its recorded source; it is
not a current full-suite result.

## Continued investigation: Coelophysis presentation

Native07's retained order `cbae002c1697cc02ee0bfadf84a3c488` has a confirmed
$1,250 purchase: cash/working cash $4,500 to $3,250, loan $5,000, one species-4
dinosaur in pen 10, and the matching expense. Root
`17c366b9e6a22d5ac592122a24f84c8a` retained that proof while presentation stayed
unqualified. The original guest is now gone; the receipt does not authorize a
new purchase.

This continuation re-read the actual retained original-game frame, SHA-256
`d77c6bf1bd96810336d3be44085060066421c1c9d402048e9297baa35695f750`,
using the unchanged current predicates:

| Predicate | Exact samples matched | Required | Result |
| --- | ---: | ---: | --- |
| Original `after` content profile | 19 / 26 | 25 | Rejects |
| Initial `mart` content profile | 16 / 32 | 29 | Rejects |
| `toolbar` | 48 / 48 | 48 | Matches |
| `mart_surface` | 48 / 48 | 48 | Matches |

Both successful guards use tolerance zero. None of the quarter, parking-advice,
game-menu, save-dialog or load-dialog profiles matches the retained image. The
frame visibly contains the catalogue and toolbar. The mismatch is therefore
narrowed to a content-sensitive post-purchase witness, while the existing strict
catalogue-surface witnesses survive. The exact rendering cause is still open.

`dinopark_purchase.qualify_purchase` tests `after` before reading pointer release
or publishing the catalogue. This explains why a confirmed commit can remain
held at that boundary. A surface match alone is insufficient to certify selector
readiness, released input or completed recovery. No threshold was lowered and
no production acceptance changed in this continuation.

The next fix should evaluate a proof-qualified catalogue destination: preserve
the native commit proof, retain exact stable surface/toolbar requirements, check
the live selector and released input, exclude known modals, and publish from the
actual committed host head. Prove this against a fresh original-game case and
negative/transition cases before replacing the existing acceptance condition.
Do not replay the confirmed purchase to obtain another screenshot.

## Remaining code and asset work

The last dated actual inventory, Native08 **0031**, contains the **97 selected
caller/producer-unresolved entries**, all enabled execution probes with
`once=False` and no captured first hit. There are 217 total native breakpoints
in that receipt; those totals describe different sets. They do not imply current
bindings after process exit or prove code unused. The last reported inventory PC
union is **47/201** in the [Employment follow-up](../VERIFICATION-DINOPARK-EMPLOYMENT-RECONCILIATION-2026-11-01.md);
this handoff does not rebuild that union.

The **13 asset candidates** remain unresolved: `BUS.ACT`, `PEOPLE.ACT`,
`OFFICE.ACT`, `MECC.PIC`, `CLICK11.ABT`, `DINO1.ABT`, `EARSQK.ABT`, `NEONA1.ABT`,
`NEONB1.ABT`, `RICOCHE2.ABT`, `SQUEAK.ABT`, `TING1.ABT` and `SBP1FM.ADV`.
See the [caller/producer record](../VERIFICATION-DINOPARK-CALLER-PRODUCERS-2026-10-31.md)
and [visitor-gate record](../VERIFICATION-DINOPARK-VISITORS-2026-11-01.md).
Neither a valid resource header nor a no-hit run establishes use or non-use.

For BUS/PEOPLE, the strongest existing next probes are the attendance/actor
chain's meaningful fields: BFDF[4], BFBF[2], 452C/452E, BA90, BF9B/BF9D and
selected ticket price under the documented mapping guards. Actor creation
`23C5:153F` still needs an explicit filename/open/read/render link to establish
either candidate's use. Distinguish host time, game calendar, actor updates and
DOS date/time. A weekday-only branch remains a hypothetical rare-trigger example.

The merged [standing-probe RFC](../STANDING_PROBES_RFC.md) separates existing
breakpoint/watchpoint primitives from the proposed durable cross-run service.
The bundled skill now recommends selective unknown-code probes and meaningful
value watches, with capture/latch/rearm handling. Arbitrary null padding is not
a useful default target. Recreate and verify actual bindings in every new run;
do not claim persisted definitions reattach a dead native session.

## Native screenshot follow-up

The user-requested follow-up implements and tests optional exact indexed PNG
and raw RGBA8 plus Zstandard in the real native screenshot path. See the
[implementation, original-game measurements and friction record](../VERIFICATION-DINOPARK-SCREENSHOT-CODECS-2026-11-03.md)
for the separate source/backend identities and measured scope. The original PNG
remains the default. Luna's finite original-game trial verifies pixel equality,
paused-state neutrality, sound-off settings and process shutdown. Indexed PNG
improves the measured title-screen transport and stored-artifact path; raw
Zstandard's faster compression does not produce an end-to-end speedup in that
same compatibility path. These trials do not resume historical recovery
sessions or advance the unresolved 97-entry / 13-asset investigation.

## Direct RGBA consumer follow-up

The subsequent [direct-consumer verification](../VERIFICATION-DINOPARK-DIRECT-RGBA-2026-11-03.md)
adds `debug.frame_rgba()` for validated in-memory pixels without PNG conversion,
screenshot hooks or artifact writes. Luna verified the unchanged client source
against a fresh original DinoPark guest: 360 timed direct calls, exact RGBA,
native probes, unchanged paused-state metadata, zero direct-phase database
writes, sound off and clean shutdown. The direct Zstandard path was about
35–36% faster than the Zstandard-to-stored-PNG path on the sampled title frames;
direct indexed PNG remained faster. The final affected/native suite passes 426
tests. No native rebuild, package or installation was performed for this step.

## Indexed PNG in scene observations

The [scene-check follow-up](../VERIFICATION-DINOPARK-INDEXED-SCENE-CHECKS-2026-11-03.md)
wires direct indexed PNG into six pixel-only observation sites, including Z
modal reads. Durable scene publication/recovery/save/action captures and native
sparse probes remain explicit. Luna's single fresh muted Office → Bank → Office
→ Street guest verified exact RGB, native predicates and unchanged paused-state
identity across 180 timed complete checks. Complete-check medians fell 12–21%;
capture medians fell 39–42%. The affected/native suite passes 437 tests. This
route does not newly qualify modal/status/inventory/shop gameplay branches or
advance the 97/13 investigation. No package or installation was made.

## Next owner: evidence and acceptance

1. Start from current source and pin the chosen backend, original files and a
   **new** private external work directory. Query capabilities. Set SDL dummy
   audio, mixer `nosound=true` and MIDI `none`; do not package or reinstall.
2. Recreate a qualified park through ordinary controls or use the supported
   hash-checked native-save load path. Compare its recorded fields. A native
   disk load is a separate prepared state, not restoration of a lost guest.
3. Before target exploration, install the selected 97 probes at the observed
   runtime mapping and verify the actual native inventory. Batch unrelated safe
   observations in that one owned context; preserve unknown outcomes and action
   identities. Capture/latch unexpected hits and investigate before rearming.
4. Fix and natively verify the confirmed-purchase presentation boundary, then
   continue visitor/actor/filename tracing. Advance 97/13 claims only with the
   corresponding entry or asset evidence. Keep null-padding watches excluded.
5. On each material result, preserve receipts and publish a scoped delta. A
   successful acknowledgement is not an original-action completion certificate.

Private locations are local selectors, not portable or public downloads:

| Evidence | Location |
| --- | --- |
| New state/image analysis and test log | `/Volumes/CACHE/fDisBull-handoff-20261103/` |
| Historical sealed 60-file packet | `/Volumes/CACHE/fDisBull-native-validation-20261101/park-return-fix/verified-receipts-20261101-park-return/EVIDENCE-MANIFEST.json` |
| Actual 97 inventory | `/Volumes/CACHE/fDisBull-native-validation-20261101/park-return-fix/native-08/PROBE-STATUS-0031.json` |
| Original 97-entry selector | `/Volumes/CACHE/fDisBull-native-validation-20261101/park-exit-fix/private-harness-f6/harness/frontier97.json` |
| Coelophysis proof and retained frame | `/Volumes/CACHE/fDisBull-native-validation-20261101/park-return-fix/native-07/coelo-held-readonly/` |
| Previously qualified native park save | `/Users/tiga/Conversions/DinoParkTycoon/luna-z-merge-ready-20261029-01/phase2/cases/opening-save-load/work/saves/zpark` |
| Full E55 research archive | `/Volumes/PATRIOT/Downloads/DinoPark-E55-UIL-Research-Handoff.zip` |
| Recovered KQ1/PQ1/Zork archive | `/Volumes/PATRIOT/Downloads/GOG-KQ1-PQ1-Zork-Recovered-Files.zip` |

The source PR now includes the authored native screenshot implementation, client
support, regression checks and this documentation. Original game files, retained
frames, saves, FDBs, raw traces and ZIPs stay private. No background run or
automatic monitoring is implied by this handoff.
