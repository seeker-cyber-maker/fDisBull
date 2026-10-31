# Bounded parity ledger

Original: cpuinfo 1.7.0 build 237, bundle `io.fata.shibata.cpuinfo`, source SHA-256
`ebc5e15fe3b3867c8e72bab1956d584cc640ecce0196243c50757bc3ad1c53f7`.

| Surface | Implemented candidate behavior | Evidence and remaining boundary |
| --- | --- | --- |
| App identity | Separate LSUIElement app and defaults domain | Built/ad hoc signed. Coordinator opened a bounded comparison instance, restored its test-opened menu, then terminated that owned instance. No installation. |
| CPU counters | Host and per-core Mach tick deltas, UInt32 unsigned interpretation, proper memory deallocation | Native two-sample headless check. Retained fDisBull import evidence supports the original's API family, not the algorithm. |
| First/reset/topology sample | Unknown baseline, new topology starts unknown; plausible UInt32 wrap accepted | Authored unit cases. Intentional difference from upstream initial-zero accumulation. Same-count CPU reordering remains unidentified. |
| Per-core bars | 3pt bars, 2pt gap, 2pt inset, 14pt track in 24pt image, 3pt minimum fill | Pinned published-source assistance. Authored pixel checks at 1x/2x/3x. The bounded native 1x comparison found ten 3px colored groups with 2px gaps and matching baselines; dynamic fill heights are not equivalent observations. |
| Load colors | Green below 75%, orange at 75% up to below 90%, red at 90% or above; B/W adaptive color | Boundary and fixture-pixel checks. Live original counters drift and cannot be compared as synchronous values. |
| Overall meter and text | 24pt pill, minimum 8pt fill; optional 36pt text region using menu-bar font | Source-assisted implementation; original font/pixel identity and text-only live menu not verified. |
| Menu | English controls, native checkmarks, interval list and disabled View Mode in per-core mode | Source-assisted labels. Native packets matched seven visible root-row titles/order/enabled states/relative frames: 218×200pt menu, 24pt non-separator rows. Hidden AX submenu labels were inventoried, not rendered or exercised. |
| Preferences | Own UserDefaults keys, source-assisted defaults | No original preferences read/copied/changed by the replica. Restart behavior remains unverified live. |
| Start at Login | Modern own-app registration on explicit selection | Original checkmark was observed enabled, replica off. Registration was not changed or exercised; original uses a bundled helper. Full parity unproved. |
| Activity Monitor/Quit | Native AppKit actions | Not exercised. No external app launch or login change during checks. |
| Other languages/updater | English candidate, no updater | Remaining gap. |

The [sanitized investigation receipt](evidence/source-investigation.json) links
fDisBull facts and the source references. The [native comparison result](evidence/live-comparison.json)
retains hashes and derived geometry only. fDisBull tool commit `ecbe4c5` captured
the original on the main display and replica on a different display with a
negative global origin, without moving their status items. Both test-opened
menus were restored closed with confirmed session receipts. A wrong-label
falsifier is detected by the read-only comparator.

No call count, source hash, successful build or matched root menu establishes
whole-app parity. Fonts, complete pixels, hidden submenu rendering/actions,
live counter equivalence, login registration, localization and restart
persistence remain outside the tested boundary.
