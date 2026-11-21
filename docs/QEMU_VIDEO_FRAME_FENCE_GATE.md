# Native source-frame control gate

## Recorded acceptance

On 2026-11-20, the twelve selected native cases passed at clean host
`154d6659cba2211eccaeaf73505bd049ad192b20` against the fresh QEMU source-fence
producer identified below. JUnit reports twelve tests, zero failures, errors
or skips, and 11.015 seconds. The complete owned phase took 41.753 seconds.
Thirteen VM lifetimes were admitted and reaped; all 26 complete native logs
were independently reread and hash-checked. Twelve warnings concern the
existing pytest `record_property`/JUnit xunit2 format, not native failures.

This qualifies the explicit `video_frame_advance` control over an existing
`qemu-vga-chain4-scanline-v1` stream for the authored profile and matrix below.
It preserves partial rows, accepts the next source raster, and independently
checks whether its own fence caused the actual stop. Earlier debugger stops
retain their real outcome. An accepted image alone is insufficient for
`advance_completed=True`.

The previous [source-row capture gate](QEMU_VIDEO_FRAME_GATE.md) remains
separate. Neither gate claims application drawing completion, atomic CPU/image
correspondence, DOSBox scanout-phase identity, other video modes, whole-game
compatibility or full debugger parity. `completed_guest_frames` remains false.
DOSBox remains the default and retained fallback; retirement is not allowed.

| Exact input or receipt | Identity |
| --- | --- |
| Tested host / oracle | `154d6659cba2211eccaeaf73505bd049ad192b20` |
| Native fence patch | SHA-256 `cbc65cf87a4356ae09a78dff7cbf99b9997453db854d7229e9715cf5df3fa8f5` |
| Patch manifest at execution | SHA-256 `acca0da4f85c69e131e8e28e4ca1cda736023fe5cfe8c0e1371c8a511d543999` |
| Combined source manifest | SHA-256 `fd35587eea966ddb06d6e2b0261657baf7a4e9be6c040e61cefd9081e5beb0de` |
| QEMU executable | SHA-256 `b42b624f452e19c1560f1af45712fc93f6859ac753bab73a1495c49188cca0af` |
| qemu-img | SHA-256 `b8687f147c9ac6900e840619196abdec4d5f4890d94be6876eae0c9e09985f03` |
| Prefix manifest | SHA-256 `5b5a0727b189a102c60a0bfa63ed9c6731a477ff791385b264d7d74351e1eab9` |
| Full FreeDOS boot image | SHA-256 `552f7cbb0625960c050a3e682a4d2121cc2ffdfa9dc9d592ccd49edf179333dc` |
| Successful native phase | SHA-256 `d061a20f00f929eea2a9c658c98c27831a7321144a40e33e8c4e9dc4b61b3e87` |
| Independent owner/log audit | SHA-256 `d7f7bffe87d7697f45f210f18dfb91ac33789f66a947ae13185ee409ee679782` |
| Frozen test plan | SHA-256 `6d43d80c868a197a717841b556165b33ee56785a9e83de091f441ebf4f876b5c` |
| Root runtime admission | SHA-256 `b30adb9bbfcd7640ec0afff3147af8fb8eae13a23206d00cce0f4ed05aa6618d` |

The successful evidence root is
`/tmp/fdisbull-video-fence-20261120-attempt-02`. Its phase receipt, JUnit,
per-case ownership records, QMP ledgers, full native logs and authored JSON
observations are retained separately from source-controlled files. The audit
is `frame-parity-20261120/native-fence-audit-02.json` in the work workspace.

## Build and host prerequisites

Source preparation copied the sealed source independently and applied the
declared nine-file patch with zero fuzz. It passed in 97.060 seconds; the
86,037-entry source manifest and all input closures agreed. A separately
admitted four-job build of only `qemu-system-x86_64` and `qemu-img` passed in
172.123 seconds. No installation or automatic test successor occurred.
Both phases reaped their owned groups without adopted children or cleanup
errors. The earlier source and runtime prefixes remained unchanged.

The native patch's 34 compiled exact-source helper cases and full QAPI parse
with documentation required passed before integration. The host controller's
391 selected cases passed at component commit
`dba1a5b52f52ebfef923ba367f872d6a1e69e5dd`; its production host code is
byte-identical at the tested integrated head. These are separate evidence
layers, not counts to add to the twelve native tests.

## Finite native matrix

| Case | Observed requirement |
| --- | --- |
| Compare-and-set, passivity and release | Stale identities refuse without mutation; query/cancel are passive and idempotent; a real stopped reset retires the old clock-owned fence |
| Next raster and partial rows | Identical complete rasters advance sequence; arming preserves 100 pre-arm rows and the authored palette transition, with exact independently expected RGB |
| CLI plus HLT | The accepted raster stops the halted machine without a later virtual-time warp; a distinct independently calculated later clock target avoids a simultaneous timer tie |
| Earlier breakpoint and hook | Real user stops retain their actual result and prevent a false frame-completion success |
| Displaced hook instruction | A real pending hook steps over the invalidating OUT; no later continue hides the resulting source stop |
| Displaced internal tracker | An authored internal tracker breakpoint and actual displacement preserve the first stop; no DESQview provider-discovery claim is made |
| Running page ABA | A configuration ABA aborts the armed source; explicit restart admits a new stream and clean raster |
| Controller exclusion | Both arm orders refuse conflicting clock, renderer, input and checkpoint work; asynchronous snapshot-load reaches its concluded fence error, is dismissed, and leaves guest state unchanged |
| Keyboard acknowledgement versus consumption | Stopped make/break delivery and fence completion are distinguished from the actual IRQ journal; CLI prevents consumption until interrupts are deliberately enabled |
| Inactive-fence stop/restart regression | Partial rows are discarded and old stream identity cannot be borrowed |
| Public checkpoint replacement regression | The guest counter rewinds, the original owner is reaped and the replacement requires a new source stream |
| Public probe/PNG regression | Ordered source pixels and decoded PNG match the complete authored RGB |

The source fixture is authored COM code, with raw VGA register journals,
known indices and non-endpoint DAC values. Expected pixels and row deadlines
are calculated independently of candidate frame replies. The host outcome
retains the actual debugger result; image acceptance, stop ownership and
input consumption are separate facts.

## Preserved failure and correction

The first fence runtime attempt ended with seven passing cases, one failed
case and four unexecuted cases. All eight VM owners were reaped and sixteen
logs were independently checked. Its phase SHA-256 remains
`a4d56925d0c0fe2fa43ed86cf88add94fb4cf811d8bc2eff8874b01e3b409944`.

The failed oracle supplied a raw UUID as a snapshot job ID; the selected UUID
began with a digit, while QEMU job IDs require an alphabetic first character.
Source review also established that instrumented snapshot-load acknowledges
creation synchronously and reports its fence refusal through an asynchronous
manual-dismiss job. The worker checks the fence before `vm_stop` or snapshot
loading. An immediate QMP-error assertion was therefore the wrong oracle.

The correction uses a prefixed job ID, observes the exact concluded
`snapshot-load` job and retained fence error, dismisses that job, and verifies
its absence plus unchanged source/fence/clock/register/frame-key/input state.
Creation, polling and dismissal share two seconds, with at most sixteen total
`query-jobs` calls. In the successful run the job concluded on the first poll.
The failed receipt remains immutable. The native source, binary, matrix and
resource limits were unchanged; no production code was weakened or rebuilt.

## Ownership and remaining work

Preflight and postflight agreed on 11,396 file records, six complete trees,
and original/source-stream/fence source and runtime-prefix closures. The
worker group and leader were reaped, no adopted child remained, and final
exact-executable process observation was empty. The case owner counts were
`1,1,1,1,1,1,1,1,1,1,2,1`.

Only case eleven permitted two owners briefly. The original reported
`running:false,status:debug`; the replacement reported
`running:false,status:prelaunch`. Guest execution during overlap was forbidden;
only the existing exact passive `info registers` restore observation was
allowed. Both owners were reaped. Each case retained the original 50-second
work and 10-second cleanup bounds; the serial worker had 480 seconds, a
512 MiB complete-output cap, 2 MiB per native log and 16 MiB worker log caps.
The whole output tree remained outside Git and symlink ancestry.

Native simultaneous completed-raster/debugger-stop precedence, pending-stop
reset retirement, nullable genuine-exit envelopes, actual DESQview discovery
and paired DOSBox phase observations still need their own witnesses. Broader
probe/RGBA/JSON/script consumers subsequently passed their separate
[one-owner native witness](DOS_QEMU_SOURCE_FRAMES.md#native-consumer-witness).
Stopped state coherence and legacy API adapters remain separate increments.
The 143-row inventory and seven campaigns
are not promoted by this bounded gate.
