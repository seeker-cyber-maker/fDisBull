# Simple Menu STATUS: bounded UIL candidate

This experiment is an executable **candidate**, using fDisBull's existing
`fdisbull-il-1` format and `uil` role. It is authored from the observation ledger
and selected replica source. It is not a machine-code lift of the Store app.
The source role, evidence and unknown original correspondence are retained in
the program and its sidecar contract.

The original app is Simple Menu STATUS 1.8, build 19. `original-identity.json`
pins the installed universal executable and selected ARM64 slice. A fresh,
read-only Ghidra 12.2 probe produced a 238-character C diagnostic for its entry
function, which calls SwiftUI App.main. That establishes an entry path, not
the behavior of the controls modeled here. The private C listing and binary
analysis database remain outside this export.

## What the candidate can execute

The actual fDisBull reference evaluator handles these transitions:

| Action | Input `$arg` | Modeled result |
| --- | --- | --- |
| 0: render projection | unused | Current memory emoji and sleep-status text |
| 1: toggle dashboard | unused | Open/closed state |
| 2: select layout | 0 Simple, 1 Developer, 2 Battery, 3 Local AI, 4 Custom | Section flags and exactly one checkmark |
| 3: toggle section | 0 GPU, 1 Storage, 2 Battery, 3 Network, 4 Processes, 5 details | Toggle flag, select Custom, request preference write |
| 4: memory pressure event | 0 unknown, 1 normal, 2 warning, 3 critical | ❔, 😊, 😐, 😰 when Memory emoji is selected |
| 5/6: request/complete sleep start | completion: 0 failure, 1 success | Request first; active only after a matching success input |
| 7/8: request/complete sleep stop | completion: 0 failure, 1 success | Request first; failed stop preserves active state |
| 9: toggle Additional options | unused | Disclosure state |
| 10: select sleep mode | 0 system, 1 system + display | Allowed only while inactive with no pending request |
| 11: select detail | 0 none, 1 CPU, 2 GPU, 3 Memory, 4 Storage, 5 Sleep | Detail state; reopening Sleep collapses Additional options |
| 12: select icon | encoded in `contract.json` | Selected icon preference; other native icon rendering unresolved |
| 13: toggle Settings | unused | Settings visibility state |
| 14: complete preference write | 0 failure, 1 success | Clear dirty state only for the matching current revision |

`$ack_id` must match `$sleep_request_id` or `$preferences_revision` for a
completion. These counters are an authored experiment protocol, rather than
a claim about the original app's internal protocol. Exhaustion is refused.
Local AI and the memory-emoji mapping are replica behavior; the original's
precise layout rules and pressure thresholds remain unknown.

The v1 evaluator has no macOS effect interface. Resources named
`effect.sleep.*` and `effect.preferences.*` are **declarative text tokens**.
They do not acquire an IOPM assertion or write preferences. Completion inputs
are supplied by the verifier. The model records a request without treating it
as a successful native action. UI text events do not draw a popover or install
a menu-bar item.

Actions are dispatched directly by the test driver. Visible-panel reachability,
focus and enabled-widget state are not qualified: selecting a layout while
the modeled menu is closed is still possible. `$menu_open` records projected
state rather than enforcing the complete native widget lifecycle.

## Run and inspect

Run from the replica repository, in a Python environment containing fDisBull:

```sh
fdisbull il-check experiments/uil/simple-menu-status/candidate.uil.json
fdisbull il-run experiments/uil/simple-menu-status/candidate.uil.json --state experiments/uil/simple-menu-status/sample.state.json
python experiments/uil/simple-menu-status/verify.py
```

`sample.state.json` selects Local AI. `sample.run.json` is a real CLI result,
including the resulting flags, checkmark and declarative events. To regenerate
the candidate after an intentional source change, run `build_candidate.py`
and then `verify.py`. The compact JSON stays below the CLI's 64 KiB input
budget; the builder is its readable construction.

The verifier compiles a temporary Foundation-only Swift harness containing
the exact replica `applyPreset` method and the actual `MemoryMood.swift` file.
It compares five layouts and four memory inputs against UIL results. It also
checks invalid inputs, atomic refusal, request completion identities, failed
sleep operations, disclosure reopening, JSON state reopening, and a deliberately
wrong warning emoji. That falsifier must be detected.

No app is opened, no defaults are changed, and no network, notification or
sleep operation is performed. JSON state reopening is only a model test; it
does not qualify macOS app restart or disk persistence.

`verification.json` records the bounded result, evaluator identity and
canonical UIL digest. `manifest.json` lists the exported file hashes. Source
digests and selected line ranges are checked separately because `il-check`
only validates the shape of evidence claims.

## Remaining boundary

This covers a small control-state slice. Metrics sampling, graph history,
startup memory estimation, timers, process tracking, alerts, network/VPN,
storage scans, image sharing, localization, login registration, fonts and
geometry are explicit residuals. Host bindings and original native event
traces would be required to qualify these state rules against the installed
app. The current DOS UDC target cannot compile this candidate into an ARM64
Mac app.

The practical improvements exposed by this attempt are listed in
[FEATURE_RECOMMENDATIONS.md](FEATURE_RECOMMENDATIONS.md).
