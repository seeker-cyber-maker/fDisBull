# Cpuinfo Replica

A local native AppKit reconstruction of the installed cpuinfo 1.7.0 menu-bar
meter, assisted by its pinned public source and fDisBull observations. Its own
identifier/defaults domain is `local.codex.cpuinfo-replica`.

Build and verify:

```sh
./build-app.sh
./test.sh
```

`./test.sh` rebuilds the app before its render checks, so a stale build can
neither hide nor create a pixel failure. The app is
`build/Cpuinfo Replica.app`. The build does not launch or install it.
It was explicitly launched after verification for the user's comparison with
the original. Start at Login changes registration only after an explicit menu
selection; it was not enabled or exercised during this work.

The menu offers the original intervals, per-core toggle, overall image/text
modes, themes, Activity Monitor and Quit. The replica is English-only: Japanese
labels were incidental to the original and are deliberately not a parity target.
The overall menu prevents disabling the last visible mode.
Settings use the original key names through UserDefaults in a separate domain.
The replica never imports or writes the original's settings.

The UI follows the source's initial-zero and selected-mode sampling history.
Only the active core/host mode advances its counters, so switching modes keeps
the previous reading until the next update. Counter reset/topology bounds retain
safer unknown baselines. Read-only diagnostics have an independent unknown first
baseline and then return elapsed intervals:

```sh
'build/Cpuinfo Replica.app/Contents/MacOS/CpuinfoReplica' --diagnostic --sample-count 2 --interval-ms 500
```

Authored offscreen rendering needs no status item:

```sh
'build/Cpuinfo Replica.app/Contents/MacOS/CpuinfoReplica' --fixture Tests/bars.fixture.json --output /private/tmp/new-cpuinfo-fixture.png --scale 2
```

The renderer check can also compare 336 authored static frames against a
separately supplied, hash-pinned upstream CpuinfoImage.swift:

```sh
python3 Tests/verify_upstream_render.py --upstream /private/upstream/CpuinfoImage.swift --output /private/new-render-report.json
```

That check replaces upstream bitmap transport to compare equal 1x/2x/3x contexts;
it preserves drawing expressions, fonts, geometry and theme lookup. It found a
real color-space gap, now fixed with calibrated RGB. It does not recover code
from the original binary or claim full original screen-pixel equivalence.

The source is cpuinfo v1.7.0, revision
`d7f9e846909f9775e1d6d03214796dbaff4d5492`,
[published by Yusuke Shibata](https://github.com/yusukeshib/cpuinfo/tree/v1.7.0).
Binary correspondence is unproved. [NOTICE.md](NOTICE.md) retains MIT attribution.
[PARITY.md](PARITY.md), [evidence/parity-followup.json](evidence/parity-followup.json)
and [evidence/live-language-followup.json](evidence/live-language-followup.json)
separate implementation, static source tests, native observations and unknowns.

fDisBull revalidated original identity and stored instruction backings, and
provided reversible native capture and a read-only AX/PNG comparator:

```sh
python3 Tests/compare_captures.py --original /private/original-session --replica /private/replica-session --output /private/new-comparison.json
```

The private FDB is incomplete; import/candidate counts do not establish native
semantic recovery. Earlier receipts remain attributed to their original source
revisions. Only authored source and sanitized derived receipts are committed;
original binaries/resources, FDBs, screenshots, raw AX trees, preference journals
and compiled builds remain outside Git. No installation, actual login/relogin,
physical mixed-scale capture or whole-app equivalence is claimed.
