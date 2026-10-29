# Z integration against v0.23.0

The base is the annotated `v0.23.0` tag, peeled to
`ed89abca061964385b176537bc9fd275dd02afa5`. PR #18 merges that source into the
shared Z player. PR #19 includes the updated #18 and the DinoPark provider.
Both PRs target main; merge #18 first so its prerequisite is reviewed separately.
Neither PR is merged by this readiness task. Final installed acceptance and
remote CI readbacks are recorded on [PR #18](https://github.com/seeker-cyber-maker/fDisBull/pull/18)
and [PR #19](https://github.com/seeker-cyber-maker/fDisBull/pull/19).

## Source and documentation integration

The README conflict was resolved by retaining v0.23's human capability chooser
and adding concise Z/DinoPark routes. The agent quickstart and packaged workflow
reference now describe the matching player/service environments, private game
inputs, finite requests and persistence boundaries. The old release-oriented
landing page was not restored over v0.23's overview.

The branches contain the actual v0.23 compiler, rather than a private source
overlay. DinoPark remains `original_bytes_only`, with zero recovered semantic
blocks. The native input adapter does not replace financial or game rules.

## Portable source-package tests

An extracted PR #18 source distribution initially failed the shared-IL scene
test with `FileNotFoundError`: its authored input was under the intentionally
excluded examples directory. The authored scene and quiet-process probe now
live in `tests/fixtures_z_scenes.py`; tests write private scene inputs and the
archive policy requires the helper. The fixture equals the unchanged checkout
example. No original game asset was added to the package.

The affected archive tests passed **51 tests** from the extracted PR #18 source
distribution and **71 tests** from the extracted PR #19 distribution. Archive
policy checks cover core/player wheels, source tarball and tool ZIP. Runtime
wheel payloads are separately compared byte-for-byte with the final source;
test-fixture changes do not change the installed runtime.

## Fresh installed acceptance and the borrow finding

Luna created separate new virtual environments without system site-packages,
installed the branch-built wheels and genuine dependencies, and checked every
accepted project import and wheel payload. Core/player metadata report 0.23.0.
All **135 PR #18** and **143 PR #19** initial payload files matched the wheels;
no project import came from a checkout, old installation or UDC snapshot.

The installed shared-IL example passed passive reads, guarded refusal, key
pickup, unlocking, navigation and checkpoints. The first installed DinoPark
phase passed four fresh Z bank cycles, all eight destinations, purchases,
opening/time/status, native save/fresh load and all 20 declared save fields.
EOF, SIGTERM, injected request timeout and SIGKILL records/cleanup also passed.
The canonical 192-file game, including eight old saves, remained unchanged;
each of eight emitted closures matched 184 actual original files.

That phase's direct-original verifier nevertheless timed out at **borrow**
after repayment. It recorded no completed borrow result, so that run remains
failed and the borrow effect unknown. No retry was sent. The immutable stored
diagnostic frame matches the paid-in-full popup (32/32 profile samples), while
the queued borrow click reports driver coordinates `(100,187)`; the previous
repayment click was `(438,187)`. This is a concrete wrong-view observation, not
a proof of the exact internal dispatch mechanism.

The correction extends separate movement/press realization to **every named
bank control**, including repayment, borrowing and return. `BankInputSession`
resolves the point from the saved scene definition, checks released input,
moves with frame/mode identity, runs 150 guest milliseconds, verifies stable
input and reasserts the source scene before one original press. Other native
operations delegate to the owned debugger. `TextScene` remains exactly the
original business class; original code owns all effects.

The parent direct-original verifier passed after this correction, including
the ordered preparation events, numerical bank states, restart PNG export and
patch-child isolation. The original failed run is preserved. A further installed
gate was allocated four fresh direct verifiers, two Z bank cycles and an
opening/save/fresh-load route; its exact wheel binding and observed outcomes
are recorded on PR #19. A plan or the initial partial pass is not a final pass.

The corrected runtime source is based on
`beae05bfe584db9498789352532771d645006d7b`. Its native scene module SHA-256 is
`6e5e55e5ee4e238d49fff698307b61c58b65e2483f706373c556706dee456f98`.
Subsequent documentation commits are checked not to change runtime payloads.
The worker and lifecycle modules retain their earlier tested code identities.

## Local source results

All three full runs used the same Mac Python environment and the required
`python -m pytest -q` command. The baseline is a fresh export of the v0.23 tag.

| Source | Passed | Skipped | Failed | Errors |
|---|---:|---:|---:|---:|
| v0.23.0 tag baseline | 1,442 | 118 | 13 | 23 |
| PR #18 after integration | 1,468 | 118 | 13 | 23 |
| PR #19 including bank adapter | 1,488 | 118 | 13 | 23 |

The same 36 failure/error identities match the tag baseline. They include
host-incompatible ELF fixture setup and unavailable optional support in this
environment; the local full suite remains non-green. Final remote checks are
reported separately, bound to the published PR heads.

Raw native files, stored images, databases, private environments and reports
remain outside Git. The first installed phase used ten native instances; its
failure led to a separately bounded eight-instance retest allocation. Original
game bytes and old saves are checked before/after each phase. The historical
office-entry timeout's exact cause and untested quarter/Vegasaurus cases retain
their prior uncertainty; successful tested routes do not establish full-game
equivalence.
