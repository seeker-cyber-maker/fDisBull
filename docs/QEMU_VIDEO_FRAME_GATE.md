# Native source-row video gate

## Recorded execution

The eight authored cases in `tests/test_qemu_video_frame_native.py` passed at
clean host commit `eb0e8753dc3df0aac8bdef929a9cc69884186bcd` against the exact
new QEMU producer below. JUnit reports eight tests with zero failures, errors
or skips. The serial pytest worker took 6.24 seconds; the complete owned phase,
including input postflight, took 19.08 seconds. Eight native VM lifetimes were
admitted and reaped, with sixteen complete independently rehashed native logs.

The separate host/source selection passed 480 cases at the same commit in
8.85 seconds, with sixteen selected input hashes unchanged. It includes 39
compiled exact-source helper checks and the pure independent RGB oracle.
These overlapping host/helper counts are not additive. The full QEMU schema
parser also passed with documentation checks enabled.

This records acceptance of `qemu-vga-chain4-scanline-v1` on the finite profile
below. It does not qualify DOSBox sampling phase, other video modes, a frame
execution fence, legacy public consumers, application drawing completion or
whole-debugger parity. `completed_guest_frames` remains false and DOSBox
default/fallback/retirement policy is unchanged.

| Preserved identity | SHA-256 or source revision |
| --- | --- |
| Integrated host and fixture | `eb0e8753dc3df0aac8bdef929a9cc69884186bcd` |
| Native patch | `01ab5ded06a8ab432b49fafa64ee133358a396aa7fec3bbd9f1bf43a36254723` |
| Native patch manifest | `3c2c23f80513f015f2d8e2d3f80042b18293d5120b11361e3746531954e7f5bc` |
| Prepared combined source manifest | `0e3bc73a14a401730c176b4fd2240768e398b155987480867aa6e02bb5684664` |
| QEMU executable | `253830eeedb2608da7b09a9527692332266488bd4abfef37a239c011e59dd592` |
| qemu-img | `08c6ecc4fd0c94e3ceaf5d2e5cd9157eac679c4c7f31130f422fc990b26aeb85` |
| Executables/firmware prefix manifest | `f4f853c89f19b441da6f5311ddbd4d793857c0fb9648415dc7757f230586c24b` |
| Full FreeDOS boot image | `552f7cbb0625960c050a3e682a4d2121cc2ffdfa9dc9d592ccd49edf179333dc` |
| Successful native phase result | `49910f91cf1f6e03cfe1124529a287b4993d80f56947be1d47b7d551c3340347` |
| Independent receipt/log audit | `f72acd60730bc311830fa1865de8c0d4241675e03887a3a5c255efd4a44bd50b` |

The source was copied independently from the sealed earlier combined producer,
patched with zero fuzz, and checked against all declared file hashes and the
complete source inventory. Preparation passed in 71.21 seconds. A separately
admitted four-job configure/build/stage phase passed in 152.75 seconds. It built
only `qemu-system-x86_64` and `qemu-img`, with no installation or automatic test
launch. The previous binary/source prefix remained unchanged.

The first test attempt is retained as failed, with phase result SHA-256
`c07e5a41ba91b5f175840742aa72493c0e3c67efcd8b6b5e15ba280baab44d1d`.
The pure oracle passed, but project creation for the first native case rejected
a target-object directory beneath a Git ancestor. No QEMU owner was created;
six later cases were unexecuted. The corrected test-only controller moved all
test output to a fresh private directory beneath `/tmp`. Product source,
native source, fixture/oracle bodies, binary, test matrix and bounds were
unchanged. The storage guard was not weakened.

## Finite test matrix

The source fixture in `tests/support/qemu_video_frame_fixture.py` assembles an
authored COM program. It sets mode 13h, writes known indices and DAC entries,
records its raw VGA timing registers, and exposes short controlled mutations.
The expected physical-line/period arithmetic comes from that guest-read
register tuple. Expected full RGB comes from authored indices and independent
six-bit DAC replication; candidate frame/proof output never constructs it.

| Case | Independent observable |
| --- | --- |
| Pure oracle discrimination | Mid-row split differs from final-state snapshot, QEMU surface DAC conversion and split rows 99/101 |
| Identical rasters and passive reads | Exact full source RGB; successive identical rasters have distinct accepted ordinals; query/probe/export leave stopped clocks/registers and artifact count unchanged |
| Mid-raster DAC and VRAM | Entire mutation runs between independently predicted source rows 99 and 100; rows 0–99 retain old DAC, rows 100–199 use new DAC, and the authored final-row VRAM marker matches |
| Geometry/blanking/panning/ABA | Each guest mutation invalidates partial and retained current pixels; old token/frame export and probe refuse; explicit recovery and restart produce new authority |
| Stop and restart | Stop discards partial rows but retains the last accepted frame; later guest time does not advance a stopped stream; restart cannot reuse old authority |
| Public checkpoint replacement | Saved state restores the guest mutation counter; the old VM is reaped; replacement has no live source pixels; old identity refuses; a newly accepted raster is required |
| Public Python probe/PNG | `video_frame_start/observe/probe/stop` and `capture_video_frame` agree with the full authored RGB; ordered duplicate points, exact PNG bytes/metadata and passive clocks/registers are checked |
| Missing precise profile | Native start refuses without explicit precise retrace, leaving the stopped clock unchanged |

Each accepted frame retains exactly 200 row receipts. The fixture independently
checks every intended deadline, actual sample lateness of less than one
physical line, dimensions/stride, DAC interpretation, generation/epoch,
first/last sample times and the full pixel hash. Completion occurs immediately
after the final source row. The tested mixed raster cannot be satisfied by one
full VRAM/palette render at the end of a period.

The native profile is one x86 vCPU, CPU 486, 32 MiB, headless pipe transport,
floppy DOS boot, explicit virtual clock, audio off and precise retrace except
for the deliberate refusal case. It uses the complete pinned FreeDOS image,
private NASM/mcopy, and the exact candidate executables/firmware. The minimal
shell image is not an equivalent input.

## Required execution ownership

Every future native run needs a fresh reviewed plan binding the exact host
commit, tests, controller code, development runtime, tool/dependency closure,
complete source and firmware manifests, native executables and media. A
successful previous build or test does not authorize a new attempt by itself.
Preparation, build and tests are separate finite phases with no automatic
successor or retry.

The successful test controller pinned 11,368 file records and six complete
trees, plus original/candidate source and new prefix manifests. Preflight and
postflight agreed. The failed prior receipt was itself pinned and required to
remain failed. The actual worker leader/group was reaped, no adopted children
remained, and final exact-executable process observation was empty.

Keep all mutable test state, generated media, target objects, caches and logs
inside one fresh mode-0700 private root outside Git and symlink ancestry. The
monitored output cap must include the entire root. Neither the host repository
nor an immutable producer/source prefix is an output directory. Preserve
complete capped owner logs before temporary VM directories are removed.

The exact lifetime counts per test are `0,1,1,1,1,2,1,1`. Normally only one VM
may be alive. The public checkpoint replacement case alone may briefly keep
two stopped owners: native `query-status` must prove the original stopped,
the replacement must launch paused and report stopped, and no guest execution
may occur during overlap. The exact passive HMP `info registers` read required
by public restore is permitted. Both owners must be reaped at case end.

| Boundary | Maximum |
| --- | ---: |
| Preparation worker | 180 seconds |
| Configure/build/stage worker | 600 seconds, four jobs |
| Serial eight-case worker | 480 seconds |
| One case work / cleanup | 50 / 10 seconds within original ends |
| Initial DOS startup | 15,000 ms, additionally limited by remaining case time |
| Group TERM / KILL-reap | 10 / 5 seconds |
| Adopted-child cleanup | One shared 5-second allowance |
| Metadata preflight / postflight | 120 / 120 seconds |
| Preparation / build / test output | 3 GiB / 4 GiB / 512 MiB |
| Worker or build log / each native log | 16 MiB / 2 MiB |

These are observed resource caps, not filesystem quotas. Do not reinstate a
historical disk-free admission floor. The first failed case or ownership,
deadline, integrity or output boundary ends that attempt; emergency cleanup
does not turn a failed attempt into successful acceptance.

## Scope remaining after this gate

The model always starts at the next strict native phase-zero boundary and
samples row `r` at `B + floor(H/4) + 2*r*H`. Legacy DOSBox can carry its row-step
phase between rasters, and its vertical origin, blanking and timing arithmetic
also need paired disposition. Fresh setup, steady subsequent frame and
re-enable/load must be compared with a raster-sensitive authored guest before
legacy phase equivalence is claimed.

A source raster records samples taken at different times. A separately stopped
CPU boundary does not make those pixels atomic with CPU/RAM, and neither
backend's complete source raster proves the application finished drawing.
The source stream is not serialized into checkpoints; a historical image may
remain an artifact after restore, but it cannot become a live frame again.

The next control gate must prove exactly-next-raster stop ownership, earlier
breakpoint/hook/tracker stops, partial-row preservation, source failure,
input acknowledgement versus consumption, controller exclusions and cleanup.
Legacy probe/RGBA/status/coherence/history and JSON/script adapters remain
separate consumers. In particular, legacy 4,096-point probes cannot silently
inherit the native source command's 256-point cap, and QEMU nanoseconds cannot
be presented as legacy PIC ticks or a general state-mutation revision.
