# Reversible macOS sessions and display-bound capture

This unreleased native adapter observes running apps and captures one explicitly
selected display region. It records the state before acting and restores only
changes owned by that session. It is distinct from stored FDB disassembly/image
exports and from the one-stop LLDB adapter. It neither launches nor quits apps.

macOS 14 or later and Apple's Swift compiler are required. On first use the
shipped Swift source is compiled into a private, hash-identified cache. Source,
compiler identity and executable hashes are retained. Accessibility and Screen
Recording checks never request a permission prompt or change privacy settings.
Missing permissions or ambiguous menu state produce a refusal, not a click
guessed from a screenshot. Discovery and compilation do not establish capture
permission or successful app behavior.

## Inspect before a live action

```sh
fdisbull macos-snapshot com.example.authorized-app
fdisbull macos-session com.example.authorized-app /private/new-observation --display-id 1 --rect '{"x":-1200,"y":0,"width":300,"height":300}'
fdisbull macos-session com.example.authorized-app /private/new-live-observation --live --status-index 0 --display-id 1 --rect '{"x":-1200,"y":0,"width":300,"height":500}'
fdisbull macos-session-recover /private/interrupted-observation
```

Example coordinates and IDs must be replaced with current snapshot values.
`macos-snapshot` is read-only. A session without `--live` observes and optionally
captures the current display; it cannot open a menu or change preferences.
`--live --status-index` permits one selected target status-menu operation.
Only a menu observed closed is opened. A menu initially open is left open.
The session observes the result and later closes only a menu it opened.
Unknown accessibility/window evidence is not a closed-menu observation.
AXPress delivery and observed menu state are retained separately: an AX error
can occur after a menu opened. The helper observes effects rather than replaying
that input. Dismissal uses an advertised menu cancellation action or one Escape
pair sent to the exact target PID, followed by a closed-state observation.

Use a new output directory outside Git and symlink ancestry. Captures and
journals may contain private application text and preference values; they are
not publication artifacts. The session records a PID and launch date, which
must still match before a mutation or restoration. It never changes the
previous Simple Menu Status replica as a side effect of investigating cpuinfo.

## Coordinate and capture contract

The snapshot records active display IDs/UUIDs, CoreGraphics global bounds,
physical pixel dimensions, per-axis scale, target windows, status-item frames
and a bounded accessibility tree. Global logical coordinates use a top-left
origin; displays to the left or above the main display can have negative
coordinates. AppKit view coordinates and PNG pixel coordinates are different
spaces and must not be substituted for these values.

The native adapter selects the matching ScreenCaptureKit display, subtracts
its global origin to obtain the display-local source rectangle, and requests
explicit scaled pixel dimensions. A region must fit entirely in the selected
display. Crossing a display boundary, stale/inactive IDs or an unexpected PNG
size is refused. The PNG receipt retains display identity, global/local
rectangles, scales, dimensions, backend and cursor policy. Accessibility and
pixels are sequential observations, not an atomic sample of live metrics.
The adapter uses Apple's [ScreenCaptureKit source rectangle](https://developer.apple.com/documentation/screencapturekit/scstreamconfiguration/sourcerect)
and screenshot APIs; it does not move a menu to make capture convenient.

## Preferences and restoration

`--keys` snapshots specified preference keys. Optional `--preference-changes`
is a JSON object mapping keys to Base64 binary-plist wrappers (`{"value":...}`),
or null to remove a key. Changes require `--live`; every changed key is included
in the exact presence/value snapshot. An absent original key is restored by
removing it, not by inventing a default or writing null.

This first adapter addresses current-user/any-host CFPreferences domains.
Sandbox-container coverage and a running app's cached interpretation are
unverified. Do not infer that a disk/key restoration immediately restored the
app's rendered language or every effect. Preference mutation acceptance uses
an authored fixture; original-app comparisons need no preference writes.

The journal is written before each requested mutation. Restoration compares
the observed value with both the original and the session's expected value.
An external change becomes a conflict and is left untouched. Capture failure,
Python exceptions, Ctrl-C and handled termination all enter cleanup. The native
child is terminated and reaped before cleanup. Locks prevent two cooperating
controllers from acting on the same target simultaneously.

A hard kill or machine failure cannot run cleanup. `macos-session-recover`
explicitly reloads the journal, reinspects the target and checks owned changes
before restoring them. Stale process identity, conflicting values, unknown
menu state or missing observations remain unresolved. There is no background
watcher or promise of automatic rollback after SIGKILL.

Receipts distinguish `confirmed`, `failed` (forward failure with confirmed
cleanup), and `partial` (unresolved restoration/durability). A JSON reply is
not itself proof of rollback: inspect the cleanup result and retained journal.
CLI session commands exit nonzero unless the result is `confirmed`.

## Verification boundaries

Unit checks exercise absent-key restoration, external conflicts, stale process
identity, controller exclusion, capture failure, interruption and explicit
recovery. Transport tests cover refusal envelopes and child cleanup. The
shipped authored Swift fixture supports native acceptance without mutating an
original app. Native display/AX/capture results and original comparisons are
recorded separately with their exact source hashes and host permissions.

These capabilities do not recover Swift semantics, generate UIL automatically,
establish visual parity, or guarantee restoration of undeclared app/OS effects.

For an explicit native acceptance run from the source checkout:

```sh
PYTHONPATH=src python scripts/check_macos_capture_native.py --output /private/new-authored-acceptance
```

The script starts only its uniquely identified authored fixture, verifies real
menu and preference restoration, captures each connected display, then stops
that exact fixture. It performs live UI actions and keeps its PNGs private.
Ordinary pytest does not start this native acceptance script.
