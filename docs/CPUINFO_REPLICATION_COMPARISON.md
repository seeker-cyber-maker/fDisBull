# cpuinfo replication through fDisBull

The [native AppKit replica](../experimental/macos/cpuinfo-replica/README.md) is
an authored, source-assisted candidate with its own app identity and defaults.
This experiment combines fDisBull's source-qualified binary analysis and
reversible native capture. It does not claim automatic native-to-UIL recovery.


## Current parity follow-up

The authored Sources in this branch are the current scope. Hash-pinned snapshot
identities in earlier receipts predate the removal of incidental Japanese
strings. The initial comparison below is historical, scoped to its older heads.

The follow-up fixes calibrated RGB colors, prevents disabling both overall
modes, adds stable action identifiers and English labels, and matches
the public source's zero-start and selected-mode sampling histories. It keeps
bounded counter reset/topology handling and independent diagnostic baselines.

Fresh checks passed: 39 deterministic core, 9 native sampler, 25 real NSMenu and
settings, 26 renderer/diagnostic. Separate processes verified saved interval,
mode/theme values and checkmarks using isolated temporary preference suites.
A hash-pinned source renderer oracle found 126 mismatched frames before the
color fix and 0 afterward, across 336 authored frames: all modes/themes/appearances
at 1x/2x/3x. It confirms AppleSystemUIFont 13pt and text geometry under the same
instrumented bitmap context. This does not claim full original screen pixels.

The follow-up fDisBull native sessions used tool `e1b6f164` and unchanged native
helper source `3b1f00b9`. Both apps were captured on the same negative-X display.
The seven root menu rows and ten bar groups matched; the wrong-label control
was detected. A single same-display screenshot also found identical opaque
green/orange pixels in both meters, despite different sampling times.

A newly launched status item initially reported a stale offscreen AX frame;
a menu open synchronized that frame to the already-visible item. The earlier
packet is retained privately; the fresh synchronized packet passes comparison.
The comparator no longer asserts a hardcoded tool revision absent from packet
metadata. The run receipt separately pins the actual tool source.

Both menus were confirmed closed after tests; both apps are deliberately left
running for user comparison. The original process/binary/preferences and all
login settings remain untouched. Actual login/relogin, original live text-mode
pixels and physical mixed-scale capture remain unqualified. Original updater
configuration is residual/unresolved; no network updater was introduced.

See [the current parity ledger](../experimental/macos/cpuinfo-replica/PARITY.md)
and [sanitized follow-up receipt](../experimental/macos/cpuinfo-replica/evidence/parity-followup.json).

## Initial comparison identity and evidence

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
The initial candidate's unknown first/reset/topology baseline intentionally differed
from upstream's initial-zero accumulation/since-boot first ratio. Font identity,
full original pixels, synchronized counters, login-helper equivalence and
actual relogin remain unqualified. Japanese localization was removed from the
scope as an incidental original artifact, not a parity target. No original bug
has been causally diagnosed or patched by this experiment.
