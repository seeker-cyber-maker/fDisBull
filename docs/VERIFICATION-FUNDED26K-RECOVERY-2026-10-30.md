# funded26k return and provider recovery: original-game verification

Initial accepted runtime `668ea794577f4fb0fa10acae28e4cbb38975c44d`, private
core/player 0.24.0 packages. The final 0.25 integration and repeated native
acceptance are recorded below. The [interface contract](DINOPARK_FUNDED_RECOVERY.md) explains
the confirmed-purchase continuation and recovery-only state. This resolves the
exercised funded26k failure preserved in the [earlier record](VERIFICATION-Z-BATCH-RECOVERY-2026-10-29.md);
the earlier failed run remains unchanged evidence.

## Root cause and correction

The last failed frame, 3852, shows an End of spring quarter notice over the
street. Its image SHA is
`3f4b0ff04418e396e6bbddcfc2b69af4a0752eb366bf8f50bf64f3914c94a91b`.
All 23 existing quarter probes match it. The street guard correctly rejects
that obscured view. The food return code did not request a quarter interruption,
and the shared shop observer explicitly suppressed quarter notices.

The backing now opts into quarter/parking interruptions only at the proven
post-commit return boundary. It reports accepted, applied-confirmed and pending
follow-up, exposes `food-return.quarter-notice`, and offers only acknowledgment.
One new notice input completes the street return; no BUY is repeated. The street
samples, tolerances, modal rejection and original game code are unchanged.

The portable regression retains 156 actual RGB probes, bound to the original
frame/image identity. It fails the previous observer with an unqualified-view
error and passes with an explicit known-quarter continuation. Missing pixels
raise rather than becoming invented evidence. Full game images remain private.

## Native installed acceptance

Luna used the exact older funded26k bundle, native SHA
`94bad1065e7dfc00be6c6e4deb84074b55c9f8b7f0f7f1e6d2aaa083d37b82a9`.
Its saved values are cash 26,638, loan 4,411 and 13 small feeders. The later zpark
seed was not substituted. All 150 source/wheel/installed payloads and actual
imports matched the manifest in a fresh isolated environment.

| Requirement | Fresh original-game observation | Result |
|---|---|---|
| Natural funded26k return | One original 20-feeder/$500 commit returned accepted with confirmed effect and pending quarter context. A further run sent nothing; one declared acknowledgment qualified street without another purchase. | Pass |
| Real provider error boundary | A private one-shot wrapper raised inside installed shop_observe at food-committed, after the original protected commit and 6000 ms return execution. The original worker and native PIDs remained alive. | Pass |
| Durable failure/effect | Exactly one incomplete reply retained applied-confirmed and recovery_required. Its diagnostic and recovery-required receipt were already on disk at the raw response boundary. | Pass |
| Recovery-only input gates | Run/resume sent no purchase; two raw travel probes were refused, a new checkpoint save was refused, and the native event journal was byte-identical across those checks. | Pass |
| Explicit existing-checkpoint restore | All 20 saved/restored ranges equal before 100 ms input-free frame preparation; Dino Diner requalified, same native process, mode cleared and old context token refused. | Pass |
| Continue after restore | One new normal food intent and one quarter acknowledgment completed. No purchase was replayed before explicit certified rewind. | Pass |
| Native save/load | Dynamic public name zpark; original native save/readback and named fresh load matched all 20 fields, with a verified session handoff. Reopening the load journal did not reload. | Pass |
| Lifecycle/preservation | All 13 final audit checks passed: both native children and worker zero, completed receipts/cleanup, no owned survivors, silent actual startup/logs, original assets/seed/prior evidence unchanged. | Pass |

The failure injection was inside the provider, not a discarded client response.
The test wrapper/marker hashes and one-shot classification are retained. It did
not patch game bytes, native fields, RNG, calendar or saves. A separate marker-
absent run establishes the natural regression fix. This does not establish
recovery from a crashed or unreachable emulator.

All three original commit records have cash **27,021 -> 26,521**, feeders
**10 -> 30**, expense **0 -> 500**, unchanged protected calendar and one
confirmation. The first natural branch and injected-error branch were explicitly
rewound; the retained park contains the final purchase. Income, feeding and
calendar changes outside those protected boundaries remain original behavior.

The final native backup SHA is
`0c37e8a6edb3e2dab0fd23d04ac34e2517f16eb2eee037eee94dc9a53e571653`.
The loaded park has cash 26,436, loan 4,290, food 29, one guide, one Coelophysis
and hunger zero. Food was 30 at commit and 29 at save/load after original
simulation continued.

Two native guests were used: worker 6182 with native 6184 through natural play,
error and both explicit restores; native 6274 only for the named disk load.
Accounting is 11 player commands (eight current and three superseded), plus
three rejected raw action probes: 14 public attempts and 13 provider act calls.
There were 92 total provider requests including passive observations and
checkpoint controls. No model-performance ranking is claimed.

## Packages and source checks

| Artifact | SHA-256 |
|---|---|
| Core wheel | `ddeef2cf2d5bfb5ee1ef4e00aa72a6f3c1c14f5dbac45e5cfc19737e1a4a56b9` |
| Player wheel | `09616891fe38938b7162f90fc75211a48695b0a826ac93357d648761247940e7` |
| Native backend, retained 0.22 prefix | `1b0ec91f8a97fb34f336f898c3e9e02bf4559f314b2e4f92f3597f0c52c92277` |

Focused recovery/continuation/player/bridge/distribution/offline-kit checks:
**163 passed**. The quarter-observer and confirmed-return regressions were
observed failing before the observer fix. Boundary checks also cover paused-only
eligibility, action/new-checkpoint refusals, one response per failure and native
field mismatch refusal.

Required `python -m pytest -q`: **1,605 passed, 118 skipped, 13 failed,
23 errors**. All 36 failure/error identities match the recorded fresh 0.24
baseline; no identities were added or removed. The local whole suite remains
red. Remote checks are reported against the actual PR head.

Private acceptance and seals are under
`Conversions/DinoParkTycoon/luna-z-funded-recovery-20261030-01`; package/source
receipts are under `Conversions/DinoParkTycoon/dinopark-z-funded-recovery-20261030-01`.
No original assets, saves, full images or databases are included in this PR.

## Final 0.25 integration and repeated native acceptance

The branch integrates published main `85503c0e895842424faa7db62f020b879d08568a`.
README/batch-guide conflicts were resolved while retaining main's provider-and-
plan continuation authorization, canonical action identity and alias replay
refusal. Partial/unknown original effects still cannot be upgraded by a successful
acknowledgment. This food case starts with an original protected, confirmed
purchase, so its separately authorized acknowledgment can complete the return.

Luna repeated the bounded installed original-game test on runtime
`b074aef2e9e65ce38dc200d4f9bb02ed786d41ea`, with fresh core/player 0.25.0
packages and a separate private environment. All **165** source, wheel, installed,
source-tar and tool-ZIP runtime payloads agree. Actual canonical action recording
and provider/plan authorization were checked in the native batch journals.

| 0.25 artifact | SHA-256 |
|---|---|
| Core wheel | `367d03bcb64f4b6fd4853e29bb102965a193f78b98684ccdbce4119d0d4d64bb` |
| Player wheel | `e086d0088a2749eccdf0e7bb4f247623a29caa352efeeace8a0f2c428d6668ea` |

The exact funded26k seed and retained native backend are the same identities as
above. The natural quarter return, no-repeat run/resume, one-shot provider-side
error, durable recovery-only response, refused ordinary input/new checkpoint,
same-process explicit restore and final order/save/load all passed again. Worker
12666 and native 12668 survived the failure and checkpoint recovery; native 12774
was used only for the final named disk load. Each restore matched all 20 native
ranges before 100 ms input-free preparation and requalified Dino Diner. The
provider failure and its confirmed effect were present in immediate on-disk
receipt/diagnostic snapshots before another operation.

The three protected commits each had cash **26,864 -> 26,364**, feeders
**10 -> 30**, and exactly one purchase confirmation. The natural and faulted
branches were explicitly rewound and retained in history; only the last order
remained in the saved park. The dynamic native name was `zpark`, SHA
`fb6aa90340e192e4608e93ca9008f5be5ffbee1f71105dc99c408b6d7aa00385`.
Save/readback/fresh-load matched all 20 fields. Loaded cash was **26,233**, loan
**4,290**, food **29**, one guide, one Coelophysis and hunger zero. Absolute
balances are observations from this run; the initial 0.24 run above is retained
separately, without a deterministic replay claim.

Accounting remained **11 Player commands** (eight current, three superseded),
**three rejected raw probes**, **13 provider act requests** and **92 total
provider requests** including observations/checkpoint controls. All 13 final
checks passed: native/worker exit zero, completed native/service cleanup receipts,
no owned survivors, silent actual launches/logs and unchanged originals/seed.
The initial 0.24 acceptance environment and sealed evidence were preserved.
Parent readback independently verified all 165 installed payloads, both restore
witnesses, native save/load equality and four 184-resource closures against the
original game (UDC output, compiled game and both native working directories).

The 0.25 focused checks passed **176**, both from the checkout and extracted
source tarball. Required `python -m pytest -q`: **1,876 passed, 118 skipped,
13 failed, 23 errors**. A fresh main-85503c0 run in the same environment had
**1,868 passed, 118 skipped, 13 failed, 23 errors**. All 36 failing/error test
identities agree; none were added or removed. The local whole suite remains
red. Core/player wheels, source tar and tool ZIP pass the tool-only archive guard.

Repeated native evidence and its seals are under
`Conversions/DinoParkTycoon/luna-z-funded-recovery-v025-20261030-01`;
parent package/test/closure readbacks are under
`Conversions/DinoParkTycoon/dinopark-z-funded-recovery-20261030-01/v025`.
The native scope exclusions below continue to apply.

## Friction and remaining boundaries

- The initial controller proposal counted only 40 total requests. Freshness
  observations made that too small; the bound was declared before native launch
  as 180 total/40 non-observe, with a separate 20-command/probe ceiling. Actual
  totals were 92 and 14 respectively. Tool budgets should distinguish passive
  reads, state controls, attempted actions and superseded branches explicitly.
- Opaque provider handles and public checkpoint labels are still separate. The
  verifier used the real journal mapping and immediate receipt copies; no label
  or native save-name sequence was guessed.
- Recovery retains only a reachable stopped guest. Existing checkpoint identity,
  mounted-file and restored-field checks remain mandatory. Failed restores do
  not unlock actions or authorize a new checkpoint.
- Unresolved-recovery EOF, running/unreachable fatal paths and multiple distinct
  failures in one session were not separately native-tested. Portable eligibility
  and refusal checks cover relevant boundaries; normal EOF after recovery was
  verified natively.
- Known notice/layout only. Original-backed UDC qualification remains
  original_bytes_only with zero recovered semantic blocks; no full-game or
  synthetic-reconstruction claim is made.
