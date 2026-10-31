# Cpuinfo Replica

A local native AppKit replica candidate for the installed cpuinfo 1.7.0 menu
bar meter. The app uses its own identifier, `local.codex.cpuinfo-replica`, and
its own macOS UserDefaults domain. It is built locally and has not been
installed or set to start at login. After the initial headless construction,
the coordinator explicitly opened it for a bounded fDisBull comparison,
restored its test-opened menu to closed, and terminated that owned app process.

```sh
./build-app.sh
./test.sh
```

The build is `build/Cpuinfo Replica.app`. Starting it explicitly shows one
vertical bar per logical CPU by default. Its menu offers the original English
intervals, image/text modes, themes, per-core toggle, Activity Monitor and Quit.
Start at Login uses modern `SMAppService.mainApp` only after a user selects it;
that behavior has not been exercised, and it differs from the original bundled
helper. Defaults are never imported from or written to the original app.

Offscreen authored rendering and read-only CPU sampling are available without
creating a menu item:

```sh
'build/Cpuinfo Replica.app/Contents/MacOS/CpuinfoReplica' --fixture Tests/bars.fixture.json --output /private/tmp/cpuinfo-authored.png --scale 2
'build/Cpuinfo Replica.app/Contents/MacOS/CpuinfoReplica' --diagnostic --sample-count 2 --interval-ms 500
```

The fixture renderer refuses an existing output. Scale 1, 2 and 3 correspond
to explicit pixels per logical point. The native sampler returns a baseline
first, then busy-time ratios from elapsed Mach counters. Initial or reset
readings remain unknown. A core-count change invalidates the per-core baseline.

This is a **source-assisted candidate**, not a recovered binary translation.
fDisBull reopened the existing private Mach-O analysis, confirmed exact app and
slice identity, retained CPU sampling imports, and revalidated 13 entry
instruction backings. That entry capsule remains incomplete; 311 stored code
items are pending. The rendering rules, settings and labels were independently
implemented with assistance from the public
[v1.7.0 source](https://github.com/yusukeshib/cpuinfo/tree/v1.7.0), pinned to
`d7f9e846909f9775e1d6d03214796dbaff4d5492`. Its correspondence to the installed
binary is unproven.

[PARITY.md](PARITY.md) distinguishes implementation, source checks, tests and
the observed native comparison. [Evidence](evidence/source-investigation.json)
contains source identities and a sanitized fDisBull receipt. No original
binary, resources, screenshots, raw instruction bytes or database are included.

The first-sample and counter-reset policy deliberately avoids displaying a
since-boot average as a current interval. This differs from the published
upstream sampler's initial-zero behavior and must be kept visible in the
comparison rather than described as exact parity. Japanese localization,
login-helper equivalence and full original pixel identity are not qualified.

The first native comparison used fDisBull's committed reversible-session tool
(`ecbe4c5`) on two physical displays, including a display with a negative global
origin. Both packets passed display/global/local-coordinate and PNG-dimension
checks. The observed default English root menus matched all seven visible
labels, order, enabled states and relative row geometry; each root menu was
218×200 logical points. The ten colored meter groups matched 3-pixel widths,
2-pixel gaps and their status-item baseline in these 1x captures. Dynamic fill
heights are different observations of CPU activity and were not asserted equal.

[The sanitized result](evidence/live-comparison.json) contains only packet
hashes, labels, relative geometry and the coverage boundary. Screenshots and raw
AX trees stay in the private session directories. The comparator is read-only
and contains a deliberately wrong menu-label falsifier that must be detected:

```sh
python3 Tests/compare_captures.py --original /private/original-session --replica /private/replica-session --output /private/new-result.json
```

The original's Start at Login checkmark was observed enabled while the
replica's was off; registration was left untouched. Font identity, full-pixel
equivalence, hidden submenu rendering/actions, counter synchronization,
localization and restart persistence remain unqualified.
