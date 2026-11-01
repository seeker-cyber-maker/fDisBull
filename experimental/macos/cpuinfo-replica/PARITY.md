# Cpuinfo parity ledger

Original: cpuinfo 1.7.0 build 237, bundle `io.fata.shibata.cpuinfo`, SHA-256
`ebc5e15fe3b3867c8e72bab1956d584cc640ecce0196243c50757bc3ad1c53f7`.
Behavioral source assistance is pinned to revision
`d7f9e846909f9775e1d6d03214796dbaff4d5492`. Its binary correspondence remains
unproved. [Follow-up verification](evidence/parity-followup.json) records the
current scope; earlier evidence remains intact and refers to earlier sources.

| Surface | Current behavior and verification | Remaining boundary |
| --- | --- | --- |
| App identity | Separate native LSUIElement app, own UserDefaults domain. Built/ad hoc signed and explicitly launched for user comparison. | Not installed or registered at login. |
| UI CPU sampling | Zero initial usages, then selected mode's first ratio from zero ticks. Only the selected core/host mode advances its counters; inactive reading is retained when modes change. 39 deterministic core checks and 9 native selected/diagnostic checks. | Same-count CPU reordering is unidentified. Implausible resets/topology changes retain safer unknown baselines rather than source fixed-topology assumptions. |
| Diagnostic CPU sampling | Independent unknown first baseline, followed by elapsed intervals. | Diagnostic policy differs deliberately from the UI's source-compatible startup. |
| Bar rendering | Per-core and overall image/text layouts, color thresholds, Default/B/W, light/dark. All 336 authored frames equal the pinned upstream drawing routine with matched bitmap transport, at 1x/2x/3x. | The upstream lockFocus transport is instrumented; equality is scoped to those static frames. |
| Color | Calibrated RGB now matches source. Earlier renderer had 126/336 mismatches; fixed renderer has 0. A same-display native screenshot also matched opaque green/orange pixels in both running apps. | Red was not observed in that live sample; CPU fills reflect different sampling times. |
| Fonts | Source uses menuBarFont(systemFontSize), 36x20pt text box at y2. Both routines produced identical text pixels; current font is AppleSystemUIFont 13pt. Menus use native menu font. | Original app live text mode was not changed/tested. |
| Menus | Seven root rows match order/enabled state/relative frames; native menus 218x200pt. Submenus/checkmarks/actions exercised headlessly through real NSMenu items. Image/Text cannot both be disabled, matching original bindings. Earlier invalid saved states recover to Image. | Native hidden-submenu appearance remains source/test qualified. |
| Preferences | Same UserDefaults keys as source, separate app domain. Actual menu actions wrote interval, modes and theme; a new process verified values and checkmarks. Temporary test suites removed. | Original settings were never imported or mutated. |
| Start at Login | Modern SMAppService.mainApp registration on explicit selection; original uses bundled helper. | Registration and actual relogin remain unexercised; no login settings changed. |
| Activity Monitor/Quit | Native AppKit actions remain implemented. | Not live-exercised during this follow-up. |
| Updater | Original plist retains old cpumeter updater configuration. No active implementation/menu was located in pinned source or installed symbol strings. | Runtime update behavior is unresolved; no network updater was added. |

fDisBull supplied stored binary evidence, source identity, captures, saved AX
state, comparison and restoration receipts. Most UI semantics still came from
public source; no automatic native-to-UIL reconstruction or measured process
speedup is established.

The initial newly launched replica exposed a stale offscreen AX status frame;
a native menu open synchronized it to the already-visible on-screen position.
The first packet is retained privately; the qualified comparator uses a fresh
synchronized packet. Both tested menus were confirmed closed after capture.
The original kept its process identity. The updated replica is deliberately
left running beside it for the user's comparison.

Current use: the later combined Simple Menu replica replaces the two originals.
The earlier statement that this standalone app was left running describes that
comparison session. Earlier receipts retain their own source/observation scope.
The current standalone scope is English-only; the intervening Japanese
acceptance is historical and is not a current feature or gate.
