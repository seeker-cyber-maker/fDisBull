# QEMU scene-1 retained-frame wait

The opt-in native test `tests/test_qemu_scene1_frame_wait_native.py` passed on
2026-11-25: **1 passed in 1.23 seconds**. It used the existing pinned QEMU
clock/boot fixtures and ran under the local QA memory guard. The final guard
receipt records exit code 0 with no guard events.

The test authored a VGA witness, captured its completed QEMU source raster,
saved a scene-1 definition with three pixel samples, and waited on that saved
scene. The immediate match returned with zero virtual time elapsed and no clock
runs. The same VM then checked a deliberately mismatching scene: one virtual
clock slice stopped at the authored dispatch breakpoint, and the wait result
contained exactly one mismatch poll and the breakpoint stop. The test asserted
that no later probe replaced the first native stop.

Three earlier invocations are retained in the private local work area:

1. Fixture resolution failed because `clock_runtime` was not registered in the
   new test module; no VM launched.
2. A raw QMP stream start did not register its token with the Python frame
   contract owner, so capture rejected the stream identity before scene wait.
3. After switching to the public stream API, immediate match passed, then
   preparing the stop case failed because it reused a scene name without the
   required revision parent. A distinct scene name fixed this setup issue.

The test and verification hashes are recorded in `verification.json`. A
separate private manifest, containing local paths and detailed fixture
inventories, remains outside the repository. No media or private runtime files
are included here.

This is a bounded authored QEMU VGA scene-wait result. It does not establish
DOSBox frame-phase parity, application-frame completion, general game-state
parity, or behavior beyond the declared pixel predicate and first-stop case.

After this native pass, the adapter gained owned fixed-input first-slice
coalescing and poisoned-channel failure cleanup. The affected local host
selection passed 400 tests with two optional native skips. A guarded rerun of
the native scene-1 test on that later source was refused for macOS warning
memory pressure before VM launch. That later native recheck was pending at that
point; the passed native evidence was tied to the earlier adapter source.

The current-source recheck at commit `10f09206922256559c07bc51be7f1bcd48f10725`
then passed under the QA guard: **1 passed in 1.62 seconds** with no guard
events. It exercised the same authored VGA immediate match and first-breakpoint
stop on the adapter that includes the fixed-input and failure-cleanup changes.
The private `private-recheck-manifest.json` has SHA-256
`f806086ef1d79afac13d80a804df0193fbc5b98ca718d410bec66d81acd54f0d`
and inventories nine private output files. The recheck establishes no DOSBox-X
frame-phase match or broader scene/game parity.
