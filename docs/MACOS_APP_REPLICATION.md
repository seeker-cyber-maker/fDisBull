# macOS app replication: observed gaps and a bounded UIL candidate

The Simple Menu STATUS replication investigation needed to connect native
code, menus, live metric counters, preferences and OS effects. The source-bound
Mach-O ARM64 work supplies a useful analysis foundation, including selected
Ghidra C diagnostics and one-stop LLDB observation. It does not yet recover a
native app as UIL or establish interface/functionality parity.

## Current executable model

The separate local `SimpleMenuStatusReplica` repository contains the authored
experiment at `experiments/uil/simple-menu-status/`. Its source commit is
`d427292` and its strict `fdisbull-il-1` canonical program digest is
`648336648e498f8950d7e4b1c75f46d7503ad4450ab023298e20d243445a9fa3`.
The local review bundle retains the experiment and its file manifest as
supplementary evidence, rather than silently making it a core format extension.

It models preset selection and one selected checkmark, section flags, memory
mood/emoji, dashboard/settings/detail selection, Sleep's Additional options
disclosure, and authored sleep/preference request-completion state. Request
identities reject stale acknowledgements and refuse counter exhaustion.
Network has no compact details pullout, matching the supplied observations.

The original app is identified by hashes in a sanitized sidecar. Its entry C
diagnostic reaches SwiftUI `App.main`; this is not a recovered view definition.
The semantic rules are assisted by replica source and supplied screenshots,
with original native correspondence explicitly unresolved. Host requests are
text tokens, not actual preferences or sleep operations. The model does not
enforce the complete native focus, enabled-state or widget lifecycle.

The experiment's verifier evaluates the model, compares five preset and four
memory projections with an extracted Foundation-only Swift source harness,
checks failures/stale completions/state reopening, and detects a deliberately
wrong warning emoji. Its 184-check receipt has a narrow claim ceiling:
executable candidate and selected replica-source correspondence, not original
app equivalence. JSON state reopening does not qualify macOS disk persistence.

Metrics, graph histories, timers, process tracking, alerts, network/VPN,
storage scans, sharing, localization, launch registration, typography and
geometry remain residuals. The DOS UDC cannot compile this model into a Mac app.

## Features exposed by the work

| Priority | Feature | Acceptance evidence needed |
| --- | --- | --- |
| 1 | One capability report | Separate code support, dependency discovery, source identity and runtime evidence. This PR implements the initial report; embedded build-commit/release certification remains unavailable. |
| 1 | Reversible investigation sessions | Snapshot exact preference-key presence and value, running/menu state and one controller. Restore an absent language key as absent and close a menu opened only for a test, including on failure. Require an explicit live-test phase. |
| 1 | Display-aware capture | Bind display identity, global coordinates, scale, accessibility tree and stored screenshot. Exercise controls on either monitor without targeting a different display or reopening unexpectedly. |
| 1 | Differential behavior recording | Apply one named input to original and replica, observe action completion, and compare control trees, geometry/fonts, pixels, preferences and OS effects. Retain a no-action control and declared live-metric drift. |
| 2 | Swift/Objective-C navigation | Follow demangled names, metadata, protocol witnesses, closures, selectors and framework calls. Demonstrate a source-linked path from a visible label to a handler and a preference key. |
| 2 | Persistent decompiler evidence | Store bounded C results, exact source spans, ABI assumptions, unresolved calls and xrefs with paging. Keep C diagnostics distinct from authoritative native facts and UIL. |
| 2 | Preferences/resources catalog | Record domains, key types, default candidates, localized labels, SF Symbols, font calls and metric-counter definitions. Distinguish a candidate default from a value observed after restart. |
| 2 | Typed UIL host effects | Define versioned request/result/error/cancel states, correlated identities and ordering for preferences, IOPM, timers, notifications, sensors and network. Unsupported required effects must refuse execution. |
| 3 | Richer state and presentation | Specify enums, records, collections, strings, units/time, bounded comparisons and a consumer-neutral control tree. Do not silently add these to the current scalar/block schema. |
| 3 | Source maps and parity queries | For each rule, retain source bytes/files, observations and verification receipts, distinguishing observed, replica-source matched, unresolved and contradicted behavior. |

Capability reporting is the first implementation slice. Safe session capture
and differential recording should follow before more live UI comparisons;
Swift navigation and durable decompiler/source maps follow next. Any host-effect
or control-tree amendment requires compatibility and conformance review through
the [UIL RFC process](UIL_RFC_PROCESS.md). No general automatic exporter is
implemented by this case study.

## Related work to reconcile

- Preserved PR #83 supplies the direct native-analysis stack dependency.
- PR #49's Ghidra/Reko/DCC x86-16 work and #64's resource gates are separate
  unmerged changes; they are not installed engines in this source.
- PR #52's macOS ARM64 output/reconstruction work is distinct from native
  input analysis and C decompilation.
- PR #7's interface-description proposal must be reconciled with future
  control-tree contracts. It is not an adopted current schema.
- PR #75 and #80 also change investigation/provenance guidance; retain their
  independent requirements when integrating shared README/skill surfaces.

Original executables, app resources, byte-retaining FDBs and full captures stay
in private analysis storage. The review evidence contains authored semantic
files, identities and receipts, with no original binary payload. No original
or replica UI is opened by this PR's checks.
