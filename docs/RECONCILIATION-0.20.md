# 0.20 continuation and Library reconciliation

Historical reconciliation, verified 28 October 2026 before the authorized merge and finalization. See [0.20 release finalization](RELEASE-0.20.0.md) for the later scope. The implementation candidate is PR #12 at
`cadf491f3fba92b82c028b38943ca5a67d05845e`. Main remains at `d2063bc`, with
0.19.0 published and installed. No 0.20 tag, release, merge or installation
promotion was performed during this reconciliation.

## Library snapshots

Version text alone cannot select the right development build. Two different
wheels are labeled `0.20.0.dev0`:

| Artifact | Identity | Comparison with PR #12 |
| --- | --- | --- |
| Standalone wheel | SHA-256 `23922b2b79f53dfa75596b416478ff4082eb69c95103564523982f45dd1cede2` | Older: 75 packaged files agree, 32 differ; processor and AGI modules are absent. |
| Wheel inside `fdisbull-0.20.0.dev0-linux-x86_64-offline.tar.gz` | SHA-256 `74655dee308f60ae7fd6cc8bcb44fec4fe31e93054916d09648fa23611d3195a` | All 109 packaged files agree byte for byte. The supplied provenance identifies source `001901d`; the later candidate commit adds a handoff document. |
| Loose `fdisbull.zip` source snapshot | SHA-256 `636ccdff680334168effe3948ac10cf9542aa8c1a5d436af4aa28314db45e7b1` | Same older payload boundary: 75 agree, 32 differ, no additional implementation files. |

The offline archive is 22,890,831 bytes, SHA-256
`fcf53a97b38e4ae59f479105cd4617a23d8e28856f7529bd8948811feaa01106`.
All 14 payload checksums matched. Both source-companion archive checksums
matched; its 29-file overlay matches all 29 hashes in the candidate layers
manifest. Archives were inspected as data, not installed or executed.
The kit omits optional Z3 wheels; solver support in that specific offline
delivery remains unavailable until its genuine optional dependency is installed.

The Library ACT assessment correctly distinguishes decoder instruction facts
from an interpreter, scheduler and rendering host. Its newly proposed ACT
processor and playback interfaces are not implemented fDisBull APIs. PRs #11,
#13 and #14 remain separate proof/world/intent-pipeline proposals; their synthetic
acceptance cases are not reports of executed runtime conformance.

## Current candidate CI

Checks were read for the exact `cadf491` commit, rather than inferred from the
older accepted head named in the PR description:

- [Tests and tool packages](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40739228814): 1,231 passed, 98 skipped; build and archive guards succeeded.
- [Native acceptance](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40739229021): 109 stable DOSBox, 415 layers, 16 PE64 and 13 DOS/boot checks passed; native test summaries contain no skips.

These are branch candidate results, not tag CI or release publication evidence.

## Fresh Mac and Police Quest checks

The current layers patch was applied to upstream
`029bd65c5dcc7cdc7f2e14e35278620d9707d969`; all 29 source hashes matched.
The private arm64 build SHA-256 is
`1b0ec91f8a97fb34f336f898c3e9e02bf4559f314b2e4f92f3597f0c52c92277`.
Its focused native suite passed 133 checks, and the complete configured layers
profile passed 415, with zero skips in both. Interactive dot-mode display was
not qualified on macOS.

The unfiltered Mac suite initially reported 1,202 passed, 101 skipped, three
failures and 23 fixture errors. Two failures and the fixture errors came from
Linux ELF compiler fixtures on Apple GCC; one failure came from a duplicate-case
filename fixture on a case-insensitive filesystem. The latter test was split so
mixed-case acceptance still runs and only the impossible duplicate-file case
skips. After that test-only correction, the Mac-compatible suite with the Linux
ELF fixture builders excluded passed 1,282 tests, with 20 platform skips and two
explicit deselections. This does not replace full Linux CI.

The reusable `examples/police_quest/verify_navigation.py` was run against a
private copy of the identified Police Quest I AGI 2.917 build and the freshly
built backend. The interpreter SHA-256 was
`29ddd3f3b91d65b6eade156608d7915e3c8b7f47701cb226ff119b717f3e8bd7`.

- A byte-verified execution breakpoint at project `1000:7c06` resolved the live
  ego record through stopped DS:DI; subsequent reads used an explicitly bound
  runtime view, rather than a guessed static BSS address.
- The public movement API reached `(48,120)` and `(61,120)` and consumed the
  second same-direction stop press, leaving direction neutral and input clear.
- A saved movement script succeeded. A separate leftward route toward X=10
  returned `blocked_unknown` at X=34 after 2,505 guest milliseconds, before its
  10,000-millisecond budget; stop cleanup settled. Its authentic diagnostic
  screenshot was captured without screenshot hooks.
- Native restore invalidated the old runtime binding. Fresh writer resolution
  and rebinding allowed both routes to succeed again, settling at `(48,120)`
  and `(60,120)`.
- Clean screenshots, a numbered 8-pixel overlay and a complete bounded
  32-instruction trace were exported privately. The scene separates explicit
  requested-context admission, ten displayed-content pixel samples and neutral
  direction readiness; this does not establish universal control readiness.
- The geometry checks qualify only an observed 1×1 baseline point on
  X=34..118, Y=120. They do not establish the actor footprint, a complete
  walkable region, conditional obstacles or the cause of the stall.

All 27 original game files and the 28-file private copy (which adds a
byte-identical `AGI.EXE` launch copy) matched their before/after inventories.
Earlier verifier failures were retained and identified as verifier errors.
No game data, native state or project database is included with the reusable
script or this document. The occupied original checkout and its 930 preserved
unrelated files were not overwritten.

At this reconciliation boundary, the local additive changes after `cadf491`
were documentation, the reusable verification script and the
case-sensitive-fixture correction. They had not yet been committed or submitted
to hosted CI. The later release finalization also adds final version metadata,
offline-kit packaging with genuine Z3, and installed-kit native acceptance.
