# Native asynchronous DOS return and paired pause gates

The production lifecycle implementation is `86a5fdb49d17452f9eda8af9380897f4a92ea7cc`.
Its affected host selection passed 401 cases, with no failures, errors or skips.
The separately selected timing witness/oracle checks passed 33 cases. Subsequent
changes in this checkpoint affect authored witnesses and documentation; production
`src` remains byte-identical to that reviewed host implementation.

## Public asynchronous return behavior

An active DOS process may resume while retaining only its exact private,
launch-bound parent-return breakpoint. Original helper bytes, READY report,
nonce, PSP identities and the control record must agree. Ordinary user controls,
unsupported input, hooks or changed preparation still refuse. Generic machine
resume keeps its existing breakpoint restriction.

The pending run stays attached to its original VM, process, project and native
channels. A stopped observation through `status`, `pause`, `resume` or
`dos_process_info` reconciles actual QMP state before another continue. At the
original helper return address, memory and UART reports, nonce/PSP identity,
registers, allocations and vectors establish the observed DOS outcome. An actual
return invalidates the old source lifetime, retires the exact private control and
persists the termination once. It preserves an unknown native stop trigger when
there is no original GDB stop packet; it never fabricates `T05`.

Each public operation retains its original admission and channel deadline. The
asynchronous interval between public calls is not given a new global run deadline.
Uncertain dispatch or owner replacement closes/quarantines the original owner,
without issuing operations through the replacement. Pending-run guards also fence
automatic tracking and other non-observer operations.

## Native one-resume return: accepted attempt 02

The exact integrated witness ran at
`c978253ae88c1496f895df8ecb68fe0ca2bf53d9`. One original QEMU owner executed the
authored five-byte `b82a4ccd21` COM. The experiment made one public resume and one
status poll, observed normal DOS exit code 42, and issued no extra pause, step,
second continue or guest observation after the terminal result.

The full independent validator matched inner native evidence to the original
external dispatch ledger, checked the post-continue stopped QMP state and actual
GDB/HMP register replies, and decoded the register layout from the original
constructor XML. Original helper memory/UART, nonce and PSP identity, source
invalidation, private-control removal and stable single-event persistence agreed.

| Evidence | Result |
| --- | --- |
| Pytest | 1 passed; zero failures, errors or skips |
| Public / inner native-helper / external calls | 5 / 63 / 151 |
| Native owner | One QEMU, exit 0 and reaped |
| Preflight and postflight | 11,808 pinned files and nine trees unchanged |
| Aggregate / owned worker elapsed | 49.008706989 / 5.531043820 seconds |
| Raw witness | 617,381 bytes, `58b56fc396e6e18ce1923ac92aa10181779b36464734fa34c801c28f63bfec2e` |
| Phase receipt | `1d7e7ab11b3f05d633e226f86e4d4c16ef22c9e02d2e277778575f997c58fb3e` |

Worker/group cleanup and adopted-child checks passed; the final selected-image
scan was empty. The ownership helper's final group signal is retained in the raw
receipt. Fixed limits were 45 seconds owner work plus 10 cleanup, 60 case, 70
worker and 180 aggregate; 4 MiB witness, 128 MiB total output and 256 MiB reserve.
See the [return plan](DOS_QEMU_ASYNC_RETURN_PLAN.md) for the exact node and oracle.

## Paired strict pause: accepted attempt 04

The exact snapshot-corrected strict witness passed at
`77c716beda9d62e178f74b6ff04bad51d3e9244c`. DOSBox and QEMU each completed all
eight episodes and all four immediate brackets per stop. Exact stopped equality
and resumed progress held in every episode; independent finalization accepted
all original public/native evidence and actual QMP continue/stop acknowledgements.

| Evidence | Result |
| --- | --- |
| Pytest | 1 paired case passed; zero failures, errors or skips |
| Original owners | DOSBox and QEMU, each exit 0 and reaped; no overlap |
| Public calls | 229 DOSBox and 211 QEMU |
| Inner QEMU / whole external calls | 763 / 1,096 |
| Preflight and postflight | 11,836 pinned files and nine trees unchanged |
| Aggregate / owned worker elapsed | 72.297788235 / 22.404954012 seconds |
| Full paired receipt | 4,468,699 bytes, `2effec094e2c7966d180d301f081033ca99e19e35ab376bbe34a43c9ff73f605` |
| Phase receipt | `d0620a2372cb63d048acecd96515b52b818206802a1b91cf0856a6f96c034a80` |

Worker/group and adopted-child cleanup passed, with no timeout or cleanup errors.
The final selected-image scan was empty. All full native logs and the ownership
helper's recorded final group signal remain in the raw evidence.

The unchanged finite experiment uses literal `b83412bb78564043ebfc`, eight running
intervals of 25, 35, 45, 55, 65, 75, 85 and 95 requested host milliseconds, and four
immediate observation brackets after every actual stop. Each bracket includes
clock, status, complete registers, ten source bytes and five BIOS tick bytes.
No settling, tolerance, extra execution or numeric cross-backend clock comparison
is allowed. Exact stopped stability and progress between resumed episodes are
separate requirements. This is sampled stability, not indefinite quiescence.

The 8 MiB per-receipt cap, 128 MiB total output, 256 MiB reserve and fixed
50+10-second owner / 120-second case / 130-second worker / 240-second aggregate
limits remain. DOSBox and QEMU have serial original lifetimes with at most one
live native owner. See the [strict-pause plan](DOS_QEMU_STRICT_PAUSE_PLAN.md).

## Retained failures and witness corrections

Every old source/controller, frozen plan, raw reply, log and phase result remains
unchanged. No diagnostic or later successful attempt reclassifies these failures.

| Attempt | Failure boundary | Original phase SHA-256 |
| --- | --- | --- |
| Strict pause01 | Late DOSBox libudev mapping outside the old 209-member loader set; QEMU never admitted | `0dac0fc78c1e798153253e8d475441eeb36f5088b4496f5ebb431ae6adcb54f7` |
| Strict pause02 | QEMU evidence exceeded the 4 MiB receipt cap during episode 5 | `b205c8e1760273fd1da1e5275a5e0fb29a8c057ca269f296e7ab0de97f756b5c` |
| Strict pause03 | Full bodies retained, but live metadata aliases changed stored public observations before final comparison | `1c70a0e15e1558fd1d995e2161adf0d7228f26ca512ebc98576786b861170199` |
| Async return01 | Body observed exit42; live metadata aliases changed entry/resume/poll snapshots | `01cdaf9854a5e3223815723151919be35e783736112c3394d85da9966c4d5d24` |

The loader correction preserved all original records and added observed libudev
plus potential libidn2/libunistring dependencies. The reviewed graph contains
212 ELF members, 55 loader metadata records, ten optional-path absences and no
preload. The IDN pair was not observed and its executable reachability was not
established. This extension does not retroactively qualify older runs.

Lossless compact JSON alone still projected more than 4 MiB for the complete
pause receipt, so the reviewed revision explicitly raised that one cap to 8 MiB.
The complete pause03 aggregate was 4,467,660 bytes. No raw fields or duplicates
were dropped, and over-cap writes still fail before replacement.

The immediate call journal had already copied each reply correctly. The witness
adapters also needed to copy the public return before retaining it in named
observations: production status exposes its live metadata, and process return or
session close later updates `mapping.process`. The two final corrections each
change one public return line to `deepcopy`; native operations, strict comparisons
and the independent validators remain unchanged. Old receipts were not repaired.

## Runtime identity and limits of qualification

The gates reused the retained QEMU
`b42b624f452e19c1560f1af45712fc93f6859ac753bab73a1495c49188cca0af`,
DOSBox-X `bfdacbed027ae16f48256abc5d0309cc8984569a2946dabea2f4d43907d43e71`,
and 1,474,560-byte FreeDOS boot input
`552f7cbb0625960c050a3e682a4d2121cc2ffdfa9dc9d592ccd49edf179333dc`.
Full source, tool, firmware and runtime pin sets, owned process identities,
complete after-reap logs and fixed deadlines are retained in their private
controller/evidence archives. No new emulator build or replacement sandbox was
created. Native output directories have no Git ancestor and are outside inputs.

These witnesses do not qualify arbitrary DOS children, TSR/protected programs,
games, exact trap attribution, cross-host packaging or whole migration. The
[revised raster timing attempt](DOS_QEMU_PAIRED_TIMING_REVISION.md) remains failed:
four quiet rasters matched, but paired pulse-phase qualification is incomplete.
All 143 surface, 18 workgroup and seven campaign promotion obligations remain
open. Source coverage remains 72 of 83 public operations; `completed_guest_frames`
remains false. DOSBox stays the default and retained fallback.
