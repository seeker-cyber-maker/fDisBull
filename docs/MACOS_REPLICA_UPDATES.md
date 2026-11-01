# Latest macOS replica sources

The review retains both authored native app sources. The combined Simple Menu
replica is the current installed replacement; standalone cpuinfo remains a
comparison/reference implementation. Both snapshots are excluded from normal
fDisBull source/wheel packages, with canonical commits and every copied file
hash recorded in ORIGIN.json. No original app, compiled build, FDB, screenshots,
raw AX trees or preference/power journals are published.

| Snapshot | Canonical revision | Scope |
| --- | --- | --- |
| [Combined Simple Menu replica](../experimental/macos/simple-menu-status-replica/README.md) | 7fdfbb94d2e509dd30b0805b694c0e2f9fe5c454 | Complete authored source, checks, build scripts and earlier bounded UIL experiment. |
| [Standalone cpuinfo replica](../experimental/macos/cpuinfo-replica/README.md) | 9d560c98f9188db04110e975623cc7bef51aa477 | Current English-only scope, including the final sampling/color/menu/persistence work. |

## Combined menu-bar representations

Settings → Icon Display now offers CPU Graph and CPU Graph + Memory Emoji,
alongside the earlier representations. The graph reuses existing per-core
samples at the dashboard's two-second interval, including when the dashboard
is closed. It uses calibrated colors, bounded backing scales and neutral
tracks for unavailable readings. The combined mode adds the existing live
memory-pressure emoji and appends coffee while Prevent Sleep is active. The
choice uses the existing UserDefaults key in the replica's separate domain.

The 93 graph-render checks and 114 combined-button checks cover light/dark,
1x/2x/3x backing, color thresholds, missing data, all four emoji states, unchanged
graph geometry, extra text width and clearing stale text on mode changes.
Existing pressure, metrics, preference, storage, alert and other checks remain
part of test.sh. The entire imported app is rebuilt and checked locally; no
live menu app is launched by those commands.

## Replacement and keep-awake handover

The installed combined app uses the user-local Applications folder. Its
per-user login agent points at that stable location, with only the executable
argument. It does not require the external development volume at login.

An explicit --resume-display-awake launch argument restores an already-active
System + Display assertion during a replacement/restart. It is not saved into
the login agent and ordinary launches do not automatically enable Prevent Sleep.
The native handover observed replacement assertions before releasing the old
ones; finite temporary bridges covered later binary updates and were stopped.

The [sanitized readback](../experimental/macos/simple-menu-status-replica/REVIEW_EVIDENCE.json)
confirms installed/source hashes, the combined view, active system/display
assertions, stopped original/standalone targets and the configured login file.
Actual logout/login is untested. These runtime actions were separately requested
by the user; a future checkout/build does not perform them or modify originals.

## Historical evidence boundaries

The [cpuinfo comparison](CPUINFO_REPLICATION_COMPARISON.md) describes the earlier
source-assisted reconstruction and measured menu/bar subset. Its original
running/login-untouched statements apply to that phase, before replacement.
The standalone scope remains English-only, preserving the later scope change.

The combined source retains experiments/uil/simple-menu-status to keep its
historical source links and earlier authored artifacts intact. That bounded
model predates the graph controls. Its old manifests/verification retain their
original source pins; they are not qualification of these new controls or a
native ARM64-to-UIL lift. The working app and its native renderer checks are
separate evidence. Full original-app equivalence remains unresolved.

## Reproduce the app checks

From experimental/macos/simple-menu-status-replica:

```sh
./build-app.sh
MACOSX_DEPLOYMENT_TARGET=12.0 ./test.sh
```

From experimental/macos/cpuinfo-replica:

```sh
./test.sh
```

The standalone checks rebuild before pixel verification to avoid stale binaries.
Builds remain local and ignored by Git. Earlier sealed review archives remain
unchanged; the current review package has a new manifest and commit identity.
