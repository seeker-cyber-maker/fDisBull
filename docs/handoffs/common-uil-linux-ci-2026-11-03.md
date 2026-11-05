# Common UIL Linux CI recovery handoff — 2026-11-03

The resumed verification now establishes a completed green ordinary Linux suite
for frozen source `5a55bc0`: **2,942 passed, 135 skipped, zero failures and zero
errors across all 3,077 cases**, in 456.648 seconds. All 2,012 source files and
22 frozen UIL files remain unchanged. The owned test container stopped normally
and its host transport was reaped. The original interrupted run's two error
markers remain causally unattributed; its missing tracebacks were not recreated
by this success.

This is a documentation handoff. It changes no UIL contract, production code,
native template or game executable. It does not build, publish or activate a
package or system installation.

## Project state and the exact verification target

- [GitLab MR !24](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/24)
  is already merged. Its recorded merge commit is
  `bc18e882d82c7d57ff8f06687c7e9aae3b26b9a5` (2026-11-02).
- This handoff starts from current main
  `3dc5c50d35f310a3ba39b1cf0cf82a20b8df69f7`, whose package metadata is `0.30.0`.
  That integration state is separate from a test qualification.
- The interrupted verification work deliberately retains target
  `5a55bc00a5b4298a1483a2760f288c035ee9a291`, in the clean analysis checkout
  `/Users/tiga/.codex/worktrees/common-uil-contract/fDisBull`.
- Its canonical Git/PAX source archive is 70,645,760 bytes, SHA-256
  `7ade003f480655f2f0c9975e40109f534b65a3751827f8740e3bf3b1f6289a82`.
  All **2,012 staged source files** were freshly rehashed on resumption and match
  the saved source proof. All **22 frozen UIL code/document/template files in
  that analysis checkout** also match their baseline.
- The older QEMU experiment uses source
  `1c909fcfb8187ec53cbdec44d5132cbf9d57b113`, archive SHA-256
  `9c0281c5b3968ce024df9a5b45f15f94277be61a99e705e4c5c68851209d8889`.
  Do not label an old-source result as a full-suite result for current main.

The common program identity remains
`8e59ebfa9b2535e5ef11c1b144a4fc18b5eb83dd32a647f4162db005b9ff8500`.
The presentation, catalog and orchestration identities and complete receipt
hashes are in the [sanitized handoff record](../evidence/common-uil-linux-ci-2026-11-03/handoff.json).
The [desktop contract](../COMMON_UIL_DESKTOP.md) and
[common contract](../COMMON_UIL_CONTRACT.md) describe the implementation; this
handoff does not redefine them.

## What was actually verified

Run names below refer to the private artifact roots listed later. Counts are
final result/report counts unless explicitly described as partial markers.

| Run / target | Outcome | Qualification boundary |
| --- | --- | --- |
| Original `fdb-uil-ci-04` / `1c909fc`, QEMU | Last complete progress marker was 79%; retained stream has two `E` markers. The 1,800-second supervisor limit ended in escalation; pytest was reaped with exit -9 and QEMU with exit 0. | No final JUnit or traceback. Marker counts are not a completed suite result. The two causes remain unknown. |
| `ci05/collect-01` / `5a55bc0` | 3,077 cases collected; exit 0. | Collection only. |
| `ci05/focused-01` / `5a55bc0` | Two inferred native-desktop candidates plus the adjacent sealer control: three passed. | Isolated current-runtime non-reproduction. |
| `ci05/full-01` / `5a55bc0` | External recorder internal error after reported 1,123 passes and 74 skips; 1,881 nodes pending. | Recorder used a shared clock that a test replaces. This is not the cause of the older two `E` markers. |
| `ci05/focused-02` / `5a55bc0` | Actual finite-clock problem node plus the three native/control checks: four passed. | Corrected recorder regression and focused product checks. |
| `ci05/full-02` / `5a55bc0` | All 3,077 completed: 2,940 passed / 136 skipped / 1 failed / 0 errors; 506.862 seconds; no pending nodes. | Completed, **not green**. Sole failure requires two case-distinct filenames on a case-insensitive host share. Source and frozen UIL unchanged. |
| `ci05/focused-03` / `5a55bc0` | The sole filesystem-dependent failure passed on an ext4 temporary directory. | Focused fix to the environment; no test skip or product edit. |
| `ci05/full-03` / `5a55bc0` | Resource-stopped at 176.692 seconds. Retained ledger has 919 completed `test_end` records and no failed phase. | **Incomplete**: no final result, JUnit or session-finish report. |
| `ci05/full-04-20261103` / `5a55bc0` | **All 3,077 completed: 2,942 passed / 135 skipped / 0 failed / 0 errors**, 456.648 seconds, no pending nodes. | Accepted final result; exact prior collection; source/UIL unchanged; matching event mirror; normal owned stop and transport reaped. |
| `fdb-ci04-focus-01` / `1c909fc`, exact historical image | Same three selected native/control tests passed in 102.338 seconds; QEMU exit 0/reaped; source/image/kernel unchanged. | Does not recreate preceding full-suite state. |
| `fdb-ci04-full-01` / `1c909fc`, historical replay | External entry path omitted source root; four tests were skipped at module import and collection was 3,065 instead of expected 3,069. Before controlled cleanup, 94 tests started and 93 completed. | Unqualified replay-harness failure. No candidate setup errors established. |
| `fdb-ci04-full-02` / `1c909fc`, corrected historical replay | Source-root import/autoload/core-limit preflight passed. Controller review deadline expired; pytest never started. QEMU exit 0/reaped. | No full-suite result. The guest cannot be resumed after shutdown. |

Platform and optional-backend skips remain visible. A full ordinary-suite result
does not replace hosted CI or the separately required native debugger/boot release
gates. The older nine-cell native Snake study and package receipts are historical
evidence of their own scope; they were not rerun by this handoff.

## Diagnosed failures and unresolved original errors

### Recorder isolation

`tests/test_ida_trace.py` deliberately replaces
`fdisbull.ida_trace.time.monotonic` with a finite iterator. The original external
recorder used that shared module function and consumed the test's mock, producing
`StopIteration` and a pytest internal error. The corrected observer captures real
clock/IO primitives and private JSON encoders before tests execute. Its SHA-256 is
`6092acab2ab7b8d26e7892fe42e8df66ecf93959cc5651f1961f400db87a7583`.
Authored checks exercised shared time/IO/JSON/Path replacements, and the actual
problem node passed with the corrected observer. The product source was not
patched to accommodate instrumentation.

### Filename case sensitivity

`test_resource_ambiguity_and_directory_bounds` creates `VOL.2` and `vol.2` and
expects the media reader to reject two matching candidates. On the CODEX share,
the second write names the same file. The retained fixture has only `PICDIR` and
`VOL.2`; both spellings resolve to inode `4958986` and the same five-byte payload.
The intended ambiguity was therefore absent. The same unchanged test passed
with ext4 temporary storage. Do not hide this coverage with an added skip.

### Historical replay startup

Launching an external `full-entry.py` is not automatically equivalent to
`python -m pytest` from the source directory. The external script initially put
its job directory at `sys.path[0]`, so
`pytest.importorskip('examples.udc.verify_native')` omitted four tests. The
corrected entry sets the source working directory at `sys.path[0]` before pytest
imports, explicitly imports that module, restores
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, and inherits the original zero core-file limit.
The corrected preflight passed, but its full replay did not start before the
review deadline. Preserve the 3,065-case failed attempt; do not treat it as a new
canonical count or use it to remap the original error markers.

### The original two `E` markers

The two native-desktop test identities remain an inference from the original
progress stream. Their original exception reports were not retained. Both tests
and the control pass in isolation on current Linux and the exact old QEMU image.
The old image also contains the directly required X11 headers and linker library.
Neither the recorder bug nor the later case-insensitive fixture failure explains
those original markers. Original full-suite accumulation, interruption effects
and other causes remain unqualified; no source defect has been established.

## Storage and service boundary

The supported Apple container stop/start recovery was verified on 2026-11-01,
including an actual execution in the owned prepared container and a normal stop.
The original prepared `fdisbull-linux` container was preserved. Testing used a
separate `fdb-common-uil-ci05` container with an APFS copy-on-write filesystem copy.
The recorded clone checks prove the operation, distinct inode, equal logical size
and sampled content; a full 550 GB logical-file SHA was not computed.

The ext4 scratch attempt exposed a resource-estimate error. At the stop, physical
CACHE growth was **811,433,984 bytes**, exceeding the **805,306,368-byte** estimate,
although the reported guest scratch files occupied only about 93 MB. Filesystem
journaling and host copy-on-write allocation were not bounded by that file count.
Shutdown flushing left CACHE about 1.7 MB below the 20 GB floor at that time.
Admission is not a quota, and final dirty flushing must be included in the reserve.

An attempted CODEX APFSX sparse-image alternative was created but its custom mount
was refused. Its file and failure receipt were retained; no ownership or security
settings were changed to force it.

## November 3 continuation

The stopped owned test disk has been relocated to CODEX. The CACHE disk slot now
resolves to `NOV3/container-rootfs/rootfs.ext4`; the original prepared
`fdisbull-linux` container's disk and metadata remain unchanged. Normal guarded
startup accepted the alias. Actual GCC ELF execution, case-distinct file creation,
a SQLite transaction and source imports passed before the new run.

The source disk contains **16,448,045,056 data bytes in 9,298 extents**, with a
**550,829,555,712-byte logical size**. CODEX allocated additional padding, so a
strict allocation-map comparison correctly stopped the first copy before the
alias was published. The final verification rehashed every source-data interval
against its destination, checked every destination-only allocated interval for
zero bytes, and accounted for the remaining implicit zero holes. This establishes
logical byte equivalence without reading or hashing all 550 GB. The negative
control rejects both a changed source-data byte and a nonzero padding byte.

The finalization receipt is
`NOV3/finalize-rootfs-20261103T165159Z-85207/receipt.json`, SHA-256
`29c74cf3266f1f5d64010f6f163757fc2bbf580cbfdb9c5c159e1b08accc5941`.
The initial failed copy and all verification maps remain private and preserved.
The retained base-disk backup and thirteen closed offline dependency wheels were
also copied, hashed and replaced with links at their original paths. No content
was discarded. These relocations recovered CACHE to approximately **20.071 GB**;
that is above the minimum, with little room for further CACHE allocations. CODEX
passed fresh admission against its 40 GB target. Future startup requires both
external volumes mounted and the CODEX disk identity verified.

The new full run is `NOV1/ci05/full-04-20261103`, with host controls at
`NOV3/source-ci04-control`. It retains exact source `5a55bc0`, the corrected
observer, all 3,077 cases and native compilation. Case-sensitive temporary files
are in the owned ext4 filesystem whose backing disk now lives on CODEX. Physical
CODEX growth and reserve are observed separately from CACHE controls. The
controller is finite and stops its owned container in its cleanup path.

The full run completed successfully: **2,942 passed / 135 skipped / 0 failed /
0 errors**. Independent readback checked 3,077 JUnit cases, 15,288 ordered events,
9,130 phase reports, an identical event mirror and no pending nodes. Every source
file and frozen UIL file was rehashed unchanged. No skips were added; the former
case-sensitive AGI fixture skip now executes successfully.

- Guest result SHA-256: `1700319f23f271e94fbf21b0d943e1c3c5a6cad5034c5e58d88bee7216692dc9`.
- JUnit SHA-256: `768b13ea76394e5349698abe67b9c08e5eaf19c3c70c0bf55b4faba82f5d6177`.
- Host/cleanup receipt SHA-256: `cfcb28bdfac7e6b8918c15881ab161059e0b85f0cb9ef27160e6ea651cf484db`.
- Independent audit SHA-256: `2735d3d8947e266a67f9ee57dfc292ec2edb4d309b7cd8a3559e0adb6c1e8940`.

The host receipt records normal owned-container stop and transport reaping; an
additional open-file check found no open disk descriptor. After shutdown CODEX
had **49,016,127,488 bytes** free and CACHE **20,071,321,600 bytes** free. The
CACHE minimum is restored, but its 40 GB target is not. Keep future bulk test
writes on an admitted physical backing pool and include dirty-flush growth in
estimates.

This qualifies the frozen `5a55bc0` ordinary source suite. It does not qualify
current main, replace the earlier game/runtime correspondence boundaries, or
supply missing historical exception reports. The controller's `--go` mode has
already been used for this run. Preserve its occupied paths and receipts;
do not repeat the relocation or rerun the invocation blindly.

## Private artifacts and future qualification gates

Keep these roots outside Git and tool packages:

| Alias | Local path |
| --- | --- |
| `NOV1` | `/Volumes/CODEX/Codex_Projects/active/fDisBull-local-studies/Common-UIL-Linux-CI-2026-11-01` |
| `NOV3` | `/Volumes/CODEX/Codex_Projects/active/fDisBull-local-studies/Common-UIL-Recovery-2026-11-03` |
| `ORIGINAL04` | `/Volumes/CODEX/Codex_Projects/active/fdb-uil-ci-04` |
| `OLD_FOCUS` | `/Volumes/CODEX/Codex_Projects/active/fdb-ci04-focus-01` |
| `OLD_FULL1` | `/Volumes/CODEX/Codex_Projects/active/fdb-ci04-full-01` |
| `OLD_FULL2` | `/Volumes/CODEX/Codex_Projects/active/fdb-ci04-full-02` |

1. Read `NOV1/UIL-FREEZE.json`, `NOV1/ci05/source-proof.json`, and the saved run
   receipts. Recheck the selected target, the 2,012 source hashes and the 22 UIL
   hashes. Do not replace that baseline with current main merely to make an old
   receipt appear current.
2. Inspect live processes and service state without dumping complete container
   inventories or environments. Read the actual November 3 recovery receipt.
   Apply `storage_admit.py` to the real physical backing pool with a conservative
   new-allocation estimate; do not add sibling APFS free-space figures.
3. Before another full run, prove that the root filesystem is backed by the
   admitted destination, that `VOL.2` and `vol.2` are distinct in the selected
   temporary directory, and that compiler execution/normal dependency imports
   work. Retain an owned external XDG root and the actual flat `player/` path.
4. The frozen-source run above is complete. To qualify another revision, inspect
   the controller, select fresh exclusive run paths and establish that revision's
   actual collection; do not inherit the old count as a universal invariant. Run
   the full **unfiltered** ordinary suite for the selected exact source with
   native compiler scratch enabled and the corrected observer. The repository
   command is `python -m pytest -q`; external observation, JUnit and temporary-path
   arguments must not add exclusions. Do not blindly reuse `run_pipeline03.py`:
   its physical CACHE guard and failed 768 MiB allocation model need reconciliation
   with the actual new backing pool. Preserve every prior attempt.
5. Accept only a final exit 0, zero failures/errors, all expected cases accounted
   for, no pending nodes, matching event mirrors, reaped process, source/UIL
   readback and owned-runtime cleanup. Report all skips and keep required-native,
   hosted, package, release and installation gates separate.
6. If continuing historical diagnosis, use a new finite reviewed controller,
   equivalent startup/import context, the real historical collection before the
   first test, independent durable logs and sufficient graceful-finalization
   time. A completed current-source suite does not retroactively supply the lost
   original tracebacks.

Only authored explanations, test names and aggregate hashes belong in this
handoff. Raw container inventories, inherited environments, VM disks, private
logs, game inputs and captured bytes stay private. Diagnostic inventories must be filtered before saving or display. Do not copy
raw inventory transcripts into reports or MRs.

Publication and attachment readback follow [agent contribution handoff](../AGENT_HANDOFF.md).
This source document is not evidence that a report attachment was uploaded or
that a new MR was successfully filed.
