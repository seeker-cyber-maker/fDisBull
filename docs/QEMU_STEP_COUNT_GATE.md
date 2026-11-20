# Native counted-step qualification proposal

The opt-in module `tests/test_qemu_step_count_native.py` contains five cases.
It requires `FDISBULL_REQUIRE_QEMU_STEP_COUNT=1`, first-failure mode (`-x`),
serial execution, and a separately reviewed ownership plugin that installs
`_fdisbull_step_count_owned_gate = "fdisbull-step-count-owned-gate-1"` on the
pytest configuration. Setting the environment variable alone is insufficient.
No native result is asserted by this proposal or by the host peer tests.

| Case | Independent observable |
| --- | --- |
| Python `step(count=3)` | INC/NOP/JMP produces three stop PCs and advances the RAM counter from 7 to 8 |
| JSON `debug-step`, count 3 | The same PC/RAM oracle through the public router |
| Saved-script `step`, count 3 | The same oracle, explicit complete/count check and a result-reference assertion |
| Earlier user breakpoint | One ordinary stop followed by the first breakpoint; no third dispatch |
| Earlier write watchpoint | The first watchpoint is terminal; no second dispatch; access stage remains unknown |

Each case creates one fresh authored raw boot image using the existing
`support.qemu_dos_fixture.boot_fixture`. It uses no commercial game, DOS image,
assembler, injected guest opcode, host register write or host memory write.
The native GDB execution wrapper records the actual command/reply without
altering it. Original sequence, JSON/script and partial failure receipts are
retained separately. Source-image hashes and owner reaping are checked.

## Required outer ownership

Run this only under a reviewed controller which pins the exact integrated host
commit, tests, Python/dependencies, selected QEMU/firmware/ELF closure, its own
code/configuration and the ownership helper. Its pending configuration must
remain unadmitted until a separate root review binds those exact bytes.

The controller must reserve a fresh mode-0700 output beneath `/tmp`, outside
Git/symlink ancestry, and set private temporary/cache/config/TargetStore roots.
It must own the actual pytest leader through process-group termination/reaping,
use a subreaper/pidfds for adopted owned descendants, and refuse a pre-existing
selected emulator image. Never select processes for signaling by name.

The owner plugin must hook `QemuMachine.__init__` before startup, record every
actual `on_spawn` Popen, permit exactly one QEMU lifetime per case and five
overall, and verify actual executed-image identity. Install log preservation
before constructor completion: retain `qemu.log` and `boot.log` after reaping
but before the owned temporary directory is removed. Keep primary failures
and secondary cleanup/retention failures distinct.

Proposed bounds are 45 seconds of work plus 10 seconds of cleanup per owner,
275 seconds of aggregate work/owner cleanup, and a 300-second outer worker
budget. Outer preflight and postflight each have 120 seconds; termination,
kill and adopted-child cleanup retain separate 10/5/5-second bounds. Use a
512 MiB monitored output cap, a 256 KiB cap per native log and the retained
40,000,000,000-byte workspace / 512 MiB temporary floors. These are monitored
bounds, not filesystem quotas. Absolute ends cannot be refreshed by a later
step, source observation, postflight check or cleanup attempt.

Success requires exactly five passing cases, zero skips/errors/failures,
exactly five admitted and reaped guest owners, ten complete hash-verified native
logs, all first-stop oracles, unchanged pinned inputs, and no remaining selected
image. The first failure stops the matrix. Preserve it even if later rehash,
cleanup or image observation also fails; do not retry or relabel it.

The initial producer proposal is the separately sealed combined S16+raster
QEMU image with SHA-256
`d4ed54ca5db6088692d29c2e94ceaa3bf654617d5963bb931ff798c6cdc0bb5b`.
Its provenance remains separate from the new integrated Python host revision.

## Scope

These cases establish only the authored raw selected-vCPU composition on the
admitted tuple. They do not establish COM/MZ return or TSR lifecycle,
protected/LE source authority, DOSBox `mode=over`, multi-vCPU/Windows process
stepping, REP/fault retirement, timing or default-promotion qualification.
Host tests separately exercise deadline/input admission, first-stop behavior
and observation/publication failures against deterministic peers.
