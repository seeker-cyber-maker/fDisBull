# Features that would have helped this replication

These are proposed tool improvements, grounded in this app investigation and
the limitations encountered while constructing the candidate. They are not
implemented capabilities.

| Priority | Proposed feature | Concrete benefit and acceptance check |
| --- | --- | --- |
| 1 | One capability report for the installed tool and its source revision | List decoder, debugger, decompiler and UIL support by architecture, including dependency availability and released versus draft status. On this Mac it must distinguish the installed 0.27 C statement view from PR #83's Ghidra ARM64 decompiler. |
| 1 | Reversible macOS investigation sessions | Capture the exact preference-key presence/value and app running/open state, keep one controller, restore on error or interruption, and require an explicit live-test phase. A language test must restore an absent key as absent and close a test-opened menu. |
| 1 | Display-aware menu-bar and popover capture | Record display identity, global coordinates, backing scale, accessibility tree and screenshot together. Tests on either monitor must target the same control without moving the menu or opening it unexpectedly. |
| 1 | A differential UI/behavior recorder | Replay a named input against original and replica, wait for action completion, then compare control trees, geometry, fonts, pixels, preferences and effect outcomes. Record a no-action control and tolerate declared metric drift. This would replace repeated manual screenshot comparisons. |
| 2 | Swift/Objective-C semantic navigation | Demangle Swift names; follow metadata, protocol witnesses, closures, selectors and dynamic framework calls; join string/resource xrefs to native candidates. A path from a menu label to its handler and UserDefaults key would make replication much faster. |
| 2 | Persistent, inspectable decompiler results | Store C diagnostics with exact source ranges, language/ABI assumptions, unresolved calls and xrefs; provide paging and explicit size/time limits. The current 4 KiB entry diagnostic reaches SwiftUI App.main but does not recover its views. |
| 2 | Preference and resource inventory | Extract domains/key types/default candidates, localized labels, SF Symbol names, font-design calls and capacity-counter identifiers into a source-linked catalog. A candidate default must remain distinct from a value actually observed after restart. |
| 2 | Typed host effects and event completion in UIL | Add a versioned, fail-closed interface for preferences, memory events, IOPM, network, timers and notifications, with correlated requests, result/error/cancel states and ordering. The candidate currently uses text tokens and a separately authored completion protocol. |
| 3 | Richer typed state and presentation contracts | Add enums, records, collections, strings, units, timestamps, bounded numeric comparisons and a consumer-neutral control tree. The current format forces scalar enum encodings and cannot describe histories, asynchronous sensors, fonts or widget geometry. |
| 3 | Source maps and a parity coverage query | Query each UI rule back to source bytes, source files, runtime observations and validation receipts. Report observed, replica-source matched, unresolved and contradicted rules separately. No count of candidate functions or successful JSON checks should imply native parity. |

The most useful implementation order is capability reporting, safe session
capture, and differential recording first; Swift navigation and durable
decompiler/source-map support next; then a small host-effect extension and
conformance fixtures. That order addresses the mistakes and repeated work in
this task before attempting a general automatic GUI-to-UIL exporter.

The existing [macOS ARM64 draft PR #83](https://github.com/seeker-cyber-maker/fDisBull/pull/83)
supplies a useful byte-bound analysis foundation. The pending
[interface-description proposal](https://github.com/seeker-cyber-maker/fDisBull/pull/7)
should be reconciled with any control-tree work. The current executable v1 IL
must continue to reject unsupported required effects rather than acquire host
authority from metadata.
