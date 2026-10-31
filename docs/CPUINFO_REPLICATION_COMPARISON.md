# cpuinfo replication through fDisBull

The [native AppKit replica](../experimental/macos/cpuinfo-replica/README.md) is
an authored, source-assisted candidate with its own app identity and defaults.
This experiment combines fDisBull's source-qualified binary analysis and
reversible native capture. It does not claim automatic native-to-UIL recovery.

## Identity and evidence

The installed cpuinfo 1.7.0 original has SHA-256
`ebc5e15fe3b3867c8e72bab1956d584cc640ecce0196243c50757bc3ad1c53f7`.
Its private FDB was reopened and 13 entry instruction backings revalidated.
The capsule is incomplete and 311 stored code items remain pending. Retained
imports identify the Mach CPU API family, not the sampler/view semantics.

Rendering/settings assistance is pinned to the public
[v1.7.0 source](https://github.com/yusukeshib/cpuinfo/tree/v1.7.0), revision
`d7f9e846909f9775e1d6d03214796dbaff4d5492`; correspondence to the installed
binary is unproved. The canonical standalone snapshot is
`718136e9c918e124703219891b5450a600ecd814`, tree
`9303bb15a62ca3d64a033b0ab8c233ff212d6e7d`. Production app sources are unchanged
from the observed app at `3994fd9`.

Live capture used fDisBull `ecbe4c577bcd57d7224a5594a8475dda4c412d10` and
native helper source `3b1f00b90785c96cdf1afef3bd235cf92d45ce9573e462677c7bf4cc5428a8c5`.
The later output-path refusal fix does not change that helper. `ORIGIN.json`
pins the snapshot files; `evidence/` contains sanitized receipts. Raw FDBs,
screenshots, AX trees and preference journals stay private.

## Observed comparison

The original was captured on the main display and the replica on the display
to its left. Display identity, global-to-local conversion, PNG dimensions and
menu coverage were checked. Neither menu was moved for comparison. Both
test-opened menus were confirmed closed afterward; the original kept its
process identity and only the explicitly started replica process was stopped.

| Surface | Result | Boundary |
| --- | --- | --- |
| Seven visible English menu rows | Same labels, order, enabled state and normalized frames | Includes disabled View Mode; hidden submenu rendering/actions untested. |
| Root menu | Both 218×200pt, with 24pt non-separator rows | Current Mac/default English surface only. |
| Per-core bars | Ten 3px columns with 2px gaps; relative starts/baseline match | Live captures are 1x; fills reflect different sampling times. |
| Restoration | Confirmed closed after each test-open | No original preference or login mutation was requested. |
| Start at Login | Original checked; replica unchecked | Reflects independent app registrations; no state was copied or toggled. |

The read-only [packet comparator](../experimental/macos/cpuinfo-replica/Tests/compare_captures.py)
reopens stored observations and exports hashes, labels and relative geometry.
It detects a deliberately wrong menu-label mutant. Root independently reran it
and reproduced the sanitized result. The replica's 24 core checks and 26
renderer/native checks passed, including authored 1x/2x/3x geometry that caught
a backing-scale mistake. Physical mixed-scale capture remains untested; both
connected live displays were 1x.

## Process comparison and limits

| Earlier manual workflow | Tool-backed workflow |
| --- | --- |
| Image-local/global positions could be confused. | Display identity and explicit coordinate spaces accompany captures. |
| Language/menu changes could outlive a test. | Write-ahead intents, exact key presence and owned restoration have receipts. |
| An AX error could be mistaken for no action. | Delivery and observed effects are separate; uncertain presses are not replayed. |
| Comparison relied on visual inspection. | Stored AX/PNG contracts and a wrong-label control are repeatable. |
| Plausible names could be overread. | Binary facts, public-source assistance and observations remain separate. |

These are unequal targets: cpuinfo has public source and prior work informed
this attempt. No measured speedup, independent semantic recovery or whole-app
parity follows. fDisBull improved evidence and restoration; public source still
supplied most UI semantics. Swift navigation, durable decompiler/source maps
and a general differential recorder remain missing features.

From the snapshot directory, run `./build-app.sh`, then `./test.sh`.
The build does not install or launch the app. Reopen private packets with:

```sh
python Tests/compare_captures.py --original /private/original-session --replica /private/replica-session --output /private/new-comparison.json
```

Live input is a separate explicit [native session](MACOS_REVERSIBLE_CAPTURE.md).
The candidate's unknown first/reset/topology baseline intentionally differs
from upstream's initial-zero accumulation/since-boot first ratio. Font identity,
full pixels, synchronized counters, Japanese localization, login-helper
equivalence and restart persistence remain unqualified. No original bug has
been causally diagnosed or patched by this experiment.
