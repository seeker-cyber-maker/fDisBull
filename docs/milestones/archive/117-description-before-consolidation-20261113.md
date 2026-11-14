# Historical !117 description — before shared-engine consolidation

Captured on 2026-11-13 from [!117](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/117), source head `e0b323022a9e8ecdac602517628d8bfeb30b1732`. This is an immutable historical snapshot, including superseded milestone wording. Current status belongs in !117 and the maintained handoff. Statements here are historical evidence, not current instructions or fresh qualification.

---

<!-- fdisbull-handoff:6405e801b85c5f849d01529f21ad124009fb23e5e5eda71485f503364aacfb91 -->

<!-- codex-dos-milestones:start -->
## Latest milestone progress — 2026-11-13

Current source: [`e0b32302`](https://gitlab.com/brewster-jennings-group/fdisbull/-/commit/e0b323022a9e8ecdac602517628d8bfeb30b1732). **Bounded CHIP-8 G2 original-source mapping and typed UDL candidates are implemented and locally verified.** G0/G1, trials, selected CPU/RAM undo, lossless histories, frame keys, RAM/code layers, hooks, RNG, checkpoints and IRQ support remain retained. DOSBox-X stays default and retained; no CI.

| Migration milestone | Current evidence and remaining gate |
| --- | --- |
| 1. Core | Classic/native v6 source retained. G0/G1 pins feed original PC/word/span and typed read/write/effect candidates; common UIL and independent semantics still require G3/G4. |
| 2. DOS process/drivers | COM/MZ, FreeDOS, driver/save work retained. Three process rows and broader vendor/real driver behavior remain pending; component04 boot qualification open. |
| 3. Trace/events | G2 static PC/return-stack contexts correlate with actual authored v6 stepping. Conditional candidates, indirect/key/range/source-write frontiers remain distinct from observed execution coverage. |
| 4. Clock/media/input | Exact environment definitions and native preservation retained, with typed display/key/timer/RNG candidate effects. DOS timing/frame/input compatibility still has nine pending rows and material partial-contract gaps. |
| 5. Checkpoints | Unchanged v6 full/format3 delta recovery retained. G2 info survives experiment recovery and selected-undo freeze without native mutation; VMState6/state6 unchanged. |
| 6. Layers/block services | RAM/fetch layers, hooks, DOS task-private/file layers, save keeps and IRQ support retained. G2 maps original words even when a live execute layer changes fetched code; source/package/producer publication guards fail closed. |
| 7. Histories | Comparative trials, frozen selected CPU/RAM undo and full/lossless frame DAGs retained. Full storage stays default; partial resume and deterministic replay unavailable. |
| 8. Workflows | G0/G1-bound Project/CLI/JSON source-map build/info added with immutable private maps and cold validation without decoder calls. All 17 DOS legacy workflow rows remain pending. G3 common UIL admission is next for CHIP-8. |
| 9. Qualification | 1,141 passed across 79 files, no failures/errors/skips/exclusions; 1,243 Python hashes match committed source. DOS promotion still requires 141 unqualified surfaces plus seven unqualified campaigns. |

**CHIP-8 conversion:** bounded G0 identity, G1 declared compatibility and G2 original-source mapping/candidate UDL implemented. G3 admitted common UIL semantics, G4 independent original→UIL qualification, G5 provider/build, G6 target execution, G7 held-out semantic reuse and G8 end-user delivery remain open.

G2 retains exact source words and hashed file spans, typed operands, may-read/write ports, ordered writes, control and effect candidates. CALL/RET preserve abstract return-stack context without an invented call fallthrough. Both skip successors remain candidates. Unsupported/truncated/non-source/odd/out-of-range fetches, indirect jumps, stack/budget limits, key waits and symbolic I boundaries remain explicit. A source write requires nonfaulting-write/unchanged subsequent fetch assumptions; unclassified spans remain unknown. Worklist exhaustion is not whole-program or executed coverage.

Typed candidates include VF aliases/prestate capture, bounded 8-bit SP and cleared 16-bit popped return slot, guarded I transfers, framebuffer/key/timer/RNG and separate current versus successor-fetch faults. They are not executable common UIL or independent semantic proof. Active overlays, asynchronous effects and native administrative counters remain outside this original-source view.

Canonical private maps are immutable, capped at 8 MiB and bound to G0/G1, options and producer hashes. Cached/cold inspection verifies decoded/typed fields, source spans and graph reconstructed from stored facts without calling the decoder or guest. Ordinary analysis/G1 analysis pins remain unchanged. Corrupt/stale/missing bindings refuse.

**83 new G2 cases pass: 46 typed-candidate, 27 map, nine public and one native.** All prior G1 preservation cases remain selected, including native DOS IRQ/task-private/checkpoint and 323 DOSBox-X history/undo/trial cases. Final capability/skill/package/migration/policy selection: 68 passed (overlapping). Results are bounded to local macOS arm64.

The native fixture matches source PCs/words/return stacks with actual nested-call stepping and RNG, distinguishes original versus live execute-layer fetch, and preserves active RAM/code layers/hooks/held keys, a lossless frame-delta child, paired trials, selected undo/freeze and full recovery. Cold G0/G1/G2 inspection passes. Snek maps 28 instructions (56/65 source bytes; nine unknown) with two possible I-range faults and one key-wait frontier; Ghost Escape maps 67 (134/135; one unknown) with five possible I-range faults. Both worklists exhaust under their budgets, with unresolved conditions. Partial one-instruction maps remain inspectable. These corpus ROMs were not executed.

Independent audit verifies all 13 listed original G0/G1 files/objects, copied-project hashes, unchanged ordinary tables, four full/partial maps and canonical private object/request/source/closure/producer/export hashes. Twelve native binaries, six native packages and shared selector/payload retain identity. Native v6 remains `4c06e9426b581dc889f35f980b3bced1b92742e2b23cd28f8118924469f08ee5`.

**DOS parity remains separate:** 141/141 surfaces are unqualified (108 partial, 31 pending, one retained-host-code, one planned-addition). Pending rows include 17 legacy workflows, nine clock/media/input, three DOS process, one layer service and one qualification row. These unequal contracts do not give an engineering-completion percentage or ETA. All seven campaigns remain unqualified: native DOS/resident/TSR; QEMM/protected-V86; DESQview switching; real-game comparison; Windows shared-core regression; cold restore/epoch; explicit DOSBox fallback rehearsal. G2 does not reduce this inventory. The historical DOSBox-X startup stack-buffer abort and component04 boot qualification remain open.

User storage waiver retained; bounded new outputs stay on CACHE. Private ROMs/FDBs/states/source-word maps/RAM-bearing reports/stores remain outside Git/packages. Both working/MR refs synchronized on local-hub and GitLab with CI skipping. No CI, native rebuild, release/tag, merge, installation or default change.

[Acceptance log](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/117#note_4226341632) · [G2 contract](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/e0b323022a9e8ecdac602517628d8bfeb30b1732/docs/CHIP8_SOURCE_MAP_UDL.md) · [DOS parity inventory](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/e0b323022a9e8ecdac602517628d8bfeb30b1732/src/fdisbull/data/dos-migration.json) · [Maintained handoff](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/e0b323022a9e8ecdac602517628d8bfeb30b1732/docs/DOS_QEMU_HANDOFF.md). Earlier dated evidence remains preserved.
<!-- codex-dos-milestones:end -->

## Why

The DOS analysis path relies on patched DOSBox-X. The native QEMU alternative needs equivalent analysis capabilities, explicit execution and source identity, and retained backends for regressions found later.

This draft includes the native core, real DOS COM/MZ process loading, source-bound traces and event searches, and the implemented portion of slice 4: physical input, explicit instruction and native virtual-clock observations, native virtual timer budgets, stopped display captures, retained synchronous renderer publications, bounded PC-speaker PCM windows, one-shot native virtual-time input scheduling, virtual-clock joins for source-bound traces, explicit precise VGA retrace observations with timing generations, one-shot retrace waits, cooperative fixed 1:1 host/native clock auto-sync, generation-checked native input at a modeled retrace edge, callback-relative native keyboard presses, bounded US-layout text, timed physical mouse-button pairs, sparse probes of retained renderer publications, and current/published VGA configuration identities.

## Current behavior

- Keep `dosbox` as the default and retain both `dosbox` and `dosbox-qemu` as explicit alternatives. Select `qemu-dos` explicitly. Uncertain operations never replay automatically in another backend.
- Preserve owned QEMU startup/stop, isolated disks, physical/virtual RAM and registers, break/watchpoints, bounded execution and paused memory investigation.
- Use the real DOS EXEC loader for original COM/MZ inputs, with source/PSP/MCB verification, ordered relocations and observed entry/stack state. A verified parent callback distinguishes selected-process exit from TSR residency while retaining ownership of the machine.
- Bind stopped traces and persistent event searches to the original real-mode module, source bytes, relocation/startup writes, allocation and capture epoch. Preserve actual linear/segmented/project addresses, foreign stops, the observed stepping policy and unknown instruction retirement after faults or partial REP.
- Under the explicit virtual profile, bracket each qualified initial COM/MZ source stop with stable native clock samples and retain the shared run/host-epoch/native-epoch identity. Query half-open `virtual-time-range` predicates through live traces, stored event queries and saved scripts. Preserve the final count endpoint separately as `endpoint_clock`; temporal ordering does not establish input causation or a completed frame.
- Queue physical keyboard make/break and relative PS/2 mouse/button edges under machine-owned leases. The default immediate path dispatches at most one batch during the same owned GDB continue and preserves its original stop packet. QMP acceptance is distinct from guest consumption; early stops can leave input pending. Uncertain dispatch or failed input evidence closes the machine without replay.
- Optionally arm that pending physical batch with `input_schedule(delta_ns)` on the explicit native virtual profile, then choose one bounded `run()` or `clock_advance()`. Observe callback/sync completion at native virtual time with `input_schedule_observe()`. Earlier stops cancel unfired timers; explicit reschedule/cancel is required before another run. Reached clock budgets win even at equal deadlines. Device acceptance, guest consumption and completed frames remain unknown.
- With the additional precise profile and fifth native patch, `input_schedule_retrace(edge="enter"|"exit")` passively arms the pending batch for one strictly next modeled edge. The callback checks the pinned generation and original absolute window immediately before delivery. Timing changes or a missed window cancel for explicit resolution; earlier and equal-deadline stops still win. Historical arm/check evidence stays immutable.
- With the sixth native patch and `virtual_keyboard_press`, the existing `keyboard_press`/`keyboard.press`, JSON and script routes passively arm one timed chord. Modifier edges use 2 ms spacing and the main hold uses its requested duration, with every next deadline based on the actual preceding callback. An early stop retains the delivered prefix and held leases; explicitly cancel the suffix and release remaining holds. No partial replay or implicit execution. The existing clock-sync controller can drive the chord at an explicit cooperation point.
- With the seventh native patch and `virtual_keyboard_type`, the existing text API, JSON and script routes passively arm 1..64 US-layout ASCII characters plus CR/LF/Tab. Each character has fresh key/Shift lifetimes; subsequent characters begin `gap_ms + 2 ms` after the preceding actual final release. Future reservations remain separate from active holds. Delivered-prefix receipts, per-edge stop precedence and explicit interruption recovery also apply to text. One explicit clock-sync step can drive a short plan.
- Keep stock `standard` and `instruction` clock profiles and add opt-in `virtual`. The latter requires the versioned native QEMU extension, reads `QEMU_CLOCK_VIRTUAL` directly, and keeps instruction counts, virtual nanoseconds and host time distinct. `clock_advance(delta_ns, timeout_ms=...)` arms one timer and issues one GDB continue; actual stop causes and token-bound requested/fired/stopped times are retained.
- Use opt-in `clock_sync_start/observe/step/stop` for a persistent fixed 1:1 host/native mapping. One explicit step freezes one target and chooses one bounded guest catch-up or host-only wait. All host elapsed time counts; actual guest progress is deducted. Excess drift or other observed stops latch the mapping until explicit stop/start, with no background execution, implicit rebase or replay.
- Capture PNG pixels with a unique observation ID, stored provenance and a stopped selected-CPU/clock bracket. A surface capture does not establish a completed guest frame, freshness, input consumption or UI readiness.
- Observe completed synchronous renderer updates at an explicit virtual cadence, retain a copied publication and export it without refreshing. Guest frame completion and VBlank remain unknown.
- Observe the explicitly selected precise VGA model at a stopped native virtual time, with raw/cache provenance and write-time timing generations. The observation stays passive. A separate `retrace_wait()` uses one budget and verifies the strictly next absolute transition window with unchanged identity/generation, preserving unsupported timing, missed windows and other stops without retry. Guest-frame completion remains unknown.
- Capture bounded PC-speaker PCM through an explicit virtual-clock audio profile, with callback timestamps, token ownership and overflow accounting. Sample duration remains distinct from elapsed guest time. Host clock sync does not establish media resampling, device queue drain or playback alignment.
- Expose the new operations through Python, retained JSON and saved scripts. Preserve one script deadline through native I/O, including lock admission. The takeover fixes the legacy `screenshot` wrapper so it cannot start a fresh 10-second lock wait after its script budget has expired.
- Refuse existing Windows native checkpoints while machine-level physical input is pending or held, because those state formats do not restore its Python ownership. This is a preflight refusal that preserves the live owner.

- With the eighth native patch and `virtual_mouse_click`, `mouse_button_click(button="left", hold_ms=80)`, JSON `debug-mouse-button-click` and script `mouse.button-click` passively arm separately synchronized down/up edges. Down is due after 2 ms; release is due `hold_ms` after the actual down callback. There is no movement request or implicit execution. Partial clicks retain a delivered hold until explicit cancellation/release; one caller-selected clock-sync step can drive a plan. Coordinate/frame click routes remain pending.

- With the ninth native patch and `renderer_probe`, `display_probe(points, *, window=None, update_id=None, timeout_ms=1000)`, JSON `debug-display-probe` and script `display-probe` read up to 256 ordered RGB samples from one retained renderer publication. The optional window/update pair requires an exact match. Sampling preserves the stopped clock and does not refresh, run, export an image or synchronize time. Legacy frame probes and coordinate clicks remain pending.

- With the tenth native patch and `vga_configuration`, `vga_configuration_observe(*, timeout_ms=1000)`, JSON `debug-vga-configuration` and script `vga-configuration` distinguish current VGA configuration from the configuration observed at a retained renderer publication. Write-time generations preserve A-to-B-to-A history even when raw hashes or dimensions match. The stopped query does not render, run or synchronize time; raster coherence, guest modes and cursor mapping remain unknown.

The inventory accounts for 35 DOSBox RPC methods, 83 public routes and 9 supplemental surfaces. Working partial implementations remain distinct from parity qualification; all 127 default-switch entries remain open.

Stacked on !113 with the original target and handoff marker preserved.

## Current and published VGA configuration identity — 2026-11-09

Continued from `55c549c3c3bf714ee150c1b29fa93a3cc51fd2e5` on
`agent/qemu-sunset-284eb73c`, retaining draft MR !117 and target
`agent/execution-event-search-284eb73c` /
`089c1841c415eb2b5cdfa90d03b6291a07f73919`. The preceding sparse renderer-probe
slice was already fully published. Its authored history and retained failures
remain intact. Work began on 2026-11-09; final verification and publication
continued after midnight UTC on 2026-11-10. The existing private runtime survived
this interruption and was
verified before reuse; no previous test result is treated as a new execution.

### Public contract and identity

The optional tenth native extension adds
`vga_configuration_observe(*, timeout_ms=1000)`, JSON
`debug-vga-configuration` and saved-script `vga-configuration`, advertised
separately as `vga_configuration`. It requires an owned stopped machine, the
existing explicit virtual/precise profiles, all native clock/display/retrace
commands, the new `x-fdisbull-query-vga-configuration` command, and a project
outside a caller-owned transaction. Nine-layer executables retain their earlier
operations and refuse this helper; the default retrace profile does not
advertise it. No new launch option or legacy DOSBox stub is introduced.

The atomic native response contains existing `display` metadata, current
configuration, and an optional frozen configuration observed alongside the
retained renderer publication. API1/model
`qemu-vga-configuration-fdisbull-v1` identifies the exact VGA device,
console/head, native clock epoch/time, positive process/device-local uint64
generation and a bounded raw vector. Public results use
`fdisbull-vga-configuration-1` and persist
`machine-vga-configuration-observe` events.

The raw vector conservatively includes both stored sequencer banks, graphics
and CRTC registers, attribute controls 0x10..0x14, display enable,
miscellaneous/feature output, ten VBE words, derived origin/pitch/bank/size,
DAC width and framebuffer byte order. Palette contents, VRAM/fonts, ordinary
selectors/flip-flops, status/latches, renderer caches and dimensions are excluded.
The exact fields and native sources are documented in the new patch README.

Generation advances once after each complete mutator whose final vector
changes. Hooks cover ordinary and protected legacy writes, VBE normalization,
QEXT and QOM byte order, and initialization/reset. MMIO aliases delegate to the
same handlers. Reset always advances; overflow never wraps and unsupported
post-load invalidates identity. A query compares fresh raw state to the
committed vector and refuses unexplained changes without repairing their
history. A-to-B-to-A writes advance twice even without an intervening query.
Window replacement and stopping do not reset generation.

`configuration_sha256` hashes canonical raw JSON only. Equal values or image
dimensions do not establish equal generation. Current/published identity also
requires the epoch, exact device, model and consistent raw values. A paused
QOM change can advance generation at the same virtual nanosecond; equal
timestamps do not order such changes.

### Publication semantics and bounded history

The native display callback captures its already pinned selected VGA under
BQL alongside the RGB copy, before publishing the timestamp/update ID. Capture
does not depend on a previous public configuration or retrace query. A new
window clears the stamp; stopping retains it. Missing selected publication
stamps refuse instead of receiving current state retrospectively. Ordinary
display query/export/probe schemas remain unchanged; unsupported PCI-VGA
targets have explicit snapshot stubs.

The stamp means `configuration_observed_at_publication`. Transient invalid text
layouts or blanking can leave older surface pixels in place. Even
`configuration_matches=True` does not establish raster coherence or a guest
frame. `raster_coherence`, `completed_guest_frame`, `guest_frame_id` and
`cursor_mapping` remain unknown. The display dimensions describe the retained
image; no current dimensions, BIOS mode, INT33 mapping or application readiness
are inferred.

Host validation retains one current snapshot and the last actual publication
stamp. Equal generation requires equal raw values; generations and strict time
order cannot regress or contradict prior observations. Empty windows return
`published=None` and `configuration_matches=None` while preserving the last
actual publication frontier for later validation. Historical reads never
replace current history. A stamp is immutable under one window/update pair.

This observation performs no guest execution, rendering, guest I/O/memory
read, input, sleep/wait, image export or implicit clock synchronization.
Direct signature and strict integer timeout validation precede locking/I/O.
Scripts preflight capabilities, visible values and transaction ownership before
earlier effects, then validate resolved timeouts before clamping. One shrinking
deadline, default 1000 ms and range 1..600000, covers admission, native queries,
unchanged clock brackets, validation, journal persistence and final return.
Tighter caller/script bounds intersect it. Malformed, contradictory, control,
persistence and late-result failures close ownership without retry and retain
available raw evidence and completed clock brackets on `error.result`.
Reopened journals restore history, not a live machine owner.

### Native and host witnesses

The new staged authored COM fixture reads port-visible sequencer, graphics,
CRTC, attribute and VBE values independently of the host response. It discovers
the real PCI VGA device/BAR through guest configuration reads and briefly loads
a private flat FS descriptor for genuine QEXT/MMIO access, preserving the
firmware-assigned BAR. Distinct fences delimit each complete guest mutation.
Original COM bytes and the prepared FreeDOS disk remain hash-unchanged.

All 15 new native cases passed. They cover:

- Passive clock/register/file/artifact invariance and preservation of a pending
  attribute-controller data phase.
- Same-extent page origin, pitch, panning and line-compare changes; unobserved
  A-to-B-to-A with equal raw hash and a generation increase of two.
- No-op and ignored protected CR0 writes versus writable CR7 bit 4; selector
  exclusions versus tracked display enable.
- Palette/VRAM changes that alter actual retained RGB markers while configuration
  remains equal.
- VBE 8-bit and 32-bit configurations with equal 320x200 dimensions; guest-read
  offsets/bank/DAC values and independently expected derived pitch/start/bank.
- Stopped QOM byte order and guest QEXT writes, including repeated/invalid writes;
  genuine MMIO VGA/VBE and monochrome/color-port aliases.
- Publication capture before the first public configuration query, frozen stamps
  after stop, and an empty replacement window followed by a fresh publication.
- A one-cell invalid text configuration: publication IDs advance and configuration
  matches while retained dimensions and two RGB marker samples stay unchanged.
- Armed-budget refusal without consuming the budget; reset invalidation; old
  nine-layer/default-profile refusal with existing renderer probing retained.
- JSON and saved-script dispatch, persisted receipts and reopening without live
  ownership.

The 244 focused host/public cases passed: 172 protocol/history/deadline cases
and 72 routing/capability/script cases. Success sentinels in routing tests qualify
forwarding and persistence only; real native cases separately exercise the
configuration responses. Host tests use production QMP envelopes and real
project persistence for exact schemas, bounds, null/malformed responses,
immutable frontiers, equal-time changes, shrinking deadlines and failures.

### Private runtime and build identities

Fresh reuse checks verified the previous 1063 runtime inputs, all 26 members of
the nine-layer native source union, 388 generated QAPI files, prior receipt/XML
and package hashes, and the recorded private Python distribution/RECORD payloads.
Those are input-identity checks, not new test executions. No shared installation,
dependency download, new runtime image or credential was required.

The tenth patch applied to the exact nine-layer source with zero fuzz/offset.
An independent private forward/reverse proof matched all 27 resulting source
members and restored all 26 preceding members, removing the new schema.
The root incremental `x86_64-softmmu` TCG/Pixman build regenerated 396 QAPI
source/header files and compiled successfully in 19.911 seconds. All 27 native
source identities were rechecked after compilation; older binaries and all
nine earlier patch bytes remain unchanged.

| Identity | SHA256 |
| --- | --- |
| Official QEMU 10.0.13 source archive | `4a59b74dac7ead8b162a7c4595dcbbeebe989b90c89cfe6bb4dec5447342f6fa` |
| Tenth native patch | `960a2cee1ffc95705760d1af314f7081d94db4b7f70c96bbd7b73845451a5ad7` |
| Tenth source manifest | `35a32909614f1135f2b3edf70096dc735d8024ee0209b96616cd5fad48704ec1` |
| Ten-layer native executable | `4a8b7bfbdf7815d8ce330d9068ea7b74fd51e44b89eb8ebbfbab6954339f1c71` |
| Retained nine-layer executable | `d42afdd33876a3bef38b45dae8787e9a83ad5838c3d82b1dd9ec5f8ce41dc4a2` |
| Prepared FreeDOS 1.4 disk | `0c1d6e413102e66059fbf9820d796b5c94e73bf5279e2413f87fd302eb32cdbf` |
| Retained DOSBox executable | `795df754019b5e9876d68067cb8d91314b001f28c9c6964502dd57ef21adf79d` |

The immutable runtime inventory now contains 1064 files, including the new
candidate and all required five-through-nine-layer legacy witnesses. Firmware,
DOS media, compiled binaries, logs and project databases remain private.

### Fresh finite local verification

Root was the sole build/test owner. Every material phase admitted 3 GiB growth
with at least 20 GiB reserve. Commands had finite deadlines, separate result
directories, before/after source and runtime identities, retained output and
JUnit receipts. No provider pipeline was started.

| Lane | Result | Elapsed |
| --- | --- | --- |
| Focused new host/public | 244 passed; 0 skipped | 3.577 s |
| New native configuration witnesses | 15 passed; 0 skipped | 12.531 s |
| Source host regression selection | 2805 passed; 5 skipped | 239.394 s |
| Combined source native selection | 147 passed; 0 skipped | 124.186 s |
| Fresh installed-wheel host selection | 1882 passed; 5 skipped; 2 deselected | 200.424 s |
| Fresh installed-wheel native selection | 147 passed; 0 skipped | 126.297 s |
| Installed retained-DOSBox selection | 5 passed; 0 skipped | 7.650 s |

The focused and new-native cases are also included in the larger source and
installed selections; these rows are not disjoint test totals.

The five source/installed host skips are the existing raw-machine opt-in cases
requiring `FDISBULL_MACHINE_QEMU`; none of the required 147 native cases skipped.
Installed host selection excludes the two source-only gate files and two
source-only nodes. Installed execution uses a fresh private wheel target,
copied tests/support and a separate Python environment without system packages;
import receipts verify that product modules come from that target. Package
privacy/payload checks keep external inputs out of the delivered tool.

Core wheel SHA256: `3d9a37a708318af646f31c4b73a22060ea1273dfed6dda808238521f846308ad`.
The installed payload contains 642 exact runtime files and
635 copied test/support files. Source archive checks additionally
bind the completed handoff and every changed authored file to the final bytes.

### Retained failures and corrections

Three initial seam assertions failed because the direct method, JSON catalog
entry and script operation did not yet exist. Independent review then identified
same-generation publication contradictions and loss of the last publication
frontier across empty windows. A previous-current cross-check and retention of
both clock brackets were also required. Four deterministic regressions failed
before those fixes and passed afterward; the expanded final suite preserves
their coverage.

The first expanded focused run had 236 passes and eight failures. Its earlier
write-memory fixture omitted required `expected_hex`, so static preflight
stopped before reaching the intended invalid-timeout case. The fixture now
supplies the guard and accepts it in the forwarding sentinel; all 244 cases
then passed. The same correction ensures bad VGA signature cases cannot pass
on an unrelated earlier-write signature failure. No product workaround was
introduced. Original failing receipts and outputs remain unchanged.

### Remaining boundaries and next slice

This supplies conservative configuration identity, not full video-mode or
renderer-raster identity. Overflow and post-load guards were compiled and source-reviewed, but not
executed. Non-PCI-VGA stubs have source review only; they were not compiled
or executed in this standard-VGA build. Reset testing proves owner invalidation, not a successful
post-reset generation observation. Arbitrary VGA variants and protected/V86
game/driver campaigns remain unqualified.

Coordinate/frame clicks still need an explicit pixel-to-guest-pointer mapping,
cursor ownership and stale-publication policy. BIOS/INT33 mode semantics,
completed guest drawing, VBlank, text consumption, additional audio devices,
input-to-source causality and DOSBox timing parity remain open. The existing
clock auto-sync controller remains explicit and cooperative; this passive query
does not invoke it. General `timed_input`, `absolute_mouse`, `guest_time_control`
and `completed_guest_frames` stay false.

All 127 default-promotion qualifications remain open and DOSBox remains the
default. The next bounded slice can establish a declared guest mouse-coordinate
contract using these independent publication/configuration observations as
prerequisites. Checkpoints, histories and dependent scene/player consumers
still require their own acceptance. macOS mirrors are not mounted here; hosted
CI, merge, release and shared installation are not claimed.


### Final source and package readback

All four package privacy and byte-payload checks passed. Both final source archives contain all 23 changed authored files, including the completed handoff. The 642 installed runtime files, 635 copied test/support files and 1064 private runtime inputs still match their recorded identities. Installed import checks remained inside the fresh target.

| Verified artifact | SHA256 |
| --- | --- |
| fdisbull-0.33.0-py3-none-any.whl | `3d9a37a708318af646f31c4b73a22060ea1273dfed6dda808238521f846308ad` |
| fdisbull-0.33.0-tool.zip | `1e86a9ee6cbeb088fb85fd1de9b1bd6288fd52ad231675723406b59c77e79d8d` |
| fdisbull-0.33.0.tar.gz | `33f694de415c8e5eb3ffbab886bf1ced4ea721d751af85f34775cd3189bef788` |
| fdisbull_player-0.33.0-py3-none-any.whl | `dc3ceb2365bff3beecd8eb38def8e4f40362994f7fd7a7b47360953b30e0c045` |

These are finite local Linux results. They do not qualify a release or a hosted pipeline.

## Sparse retained-renderer pixel probes — 2026-11-09

Continued from `fd46fbe8fa4c7819aff3bd19c08415566f8df0db` on
`agent/qemu-sunset-284eb73c` and the same draft MR !117, retaining target
`agent/execution-event-search-284eb73c` /
`089c1841c415eb2b5cdfa90d03b6291a07f73919`. The interruption had removed the
temporary checkout and private runtimes. The published source was restored
first; the test environment was then recreated from pinned inputs. The earlier
mouse-button slice and its historical evidence remain intact.

### Public contract and retained image identity

The ninth optional extension adds
`display_probe(points, *, window=None, update_id=None, timeout_ms=1000)`, JSON
`debug-display-probe` and saved-script `display-probe`, advertised separately by
`renderer_probe`. It requires an owned stopped machine, the explicit virtual
clock, all existing native clock/display commands, the new
`x-fdisbull-probe-display` command and a project outside a caller-owned
transaction. Precise retrace is unnecessary. An eight-layer executable keeps
`renderer_capture` and its existing input operations while refusing this helper.

Accept a list of zero through 256 two-coordinate points. Coordinates are strict
integers in `0..8191`, with booleans rejected, and must lie inside the retained
publication's dimensions. Preserve order and duplicates. Empty points still
require an existing publication. The optional expected `window` and positive
uint64 `update_id` must be supplied together and match exactly; with both unset,
select the latest retained publication under the machine lock. IDs restart in
each new window, so an ID alone is insufficient. The native request always
carries the selected owned token and exact update ID.

The result is `fdisbull-renderer-probe-1`, with ordinary renderer publication
metadata, requested `points`, ordered `pixels` containing `{x, y, rgb}`,
`pixel_format="RGB24"`, `coordinate_domain="retained_renderer_pixels"`, both
stopped clock brackets and the full native response. It samples the existing
private packed RGB copy under BQL. The entire native point list validates
before allocating the result or reading samples; a bad suffix cannot produce
a partial successful prefix.

There is no image artifact, temporary PPM, file export, screen refresh, guest
execution, input, sleep, implicit wait, clock-sync step, retry or fallback.
VRAM, palette or mode changes can appear in a freshly captured current surface
while the probe still returns older retained pixels and dimensions. A stopped
observer retains that image even after the guest leaves its mode. Publication
time and observed age describe this distinction. Only explicit caller-selected
execution, including an explicit cooperative clock-sync step, can permit a
later observer callback; the probe does not wait for or manufacture one.

The host compares the full native display receipt with its stopped prequery,
checks exact sample count/order/coordinates and RGB byte types/ranges, and
requires unchanged native epoch, instruction counter and virtual time across
the clock bracket. Duplicate samples must agree. At most the immediately
previous probe's 256-point map is cached for overlap contradiction checks;
this is neither an accumulated image history nor a proof of unseen pixels.
No full-raster hash is invented. `capture_display()` remains the full-image
pixel-hash route, and native witnesses compare probe samples with its pixels.

### Admission, bounded failure and historical evidence

Direct signatures and complete values validate before lock/deadline admission.
Whole-script capability, signature, transaction and visible-literal checks
precede earlier effects; resolved values validate again before sampling and
timeout clamping. References may name whole lists, list points or individual
list coordinates. Tuple points with references are refused during preflight;
direct integer tuple points remain accepted.

One allowance, default 1000 ms and bounded to `1..600000` ms, covers lock
admission, native reads, validation, clock brackets and event persistence.
Tighter caller, script, machine and channel deadlines are preserved and
restored. Missing publication, stale expectation and outside coordinates refuse
before native sampling while leaving a valid stopped owner available.

Malformed native evidence, broken read/control channels, failed persistence or
a late accepted result closes ownership without replay. Available responses
are attached to `error.result`; an explicit received flag preserves a native
JSON `null` rather than confusing it with no response. Prequery failure also
closes, including a completed QMP error with a healthy transport. A journal
committed before expiry remains historical evidence. Successful
`machine-display-probe` entries survive project reopening; reopening does not
restore the observer, live owner or VM.

### Fresh local verification

| Completed local lane | Recorded outcome |
| --- | --- |
| Focused host/public/display integration (`focused-host-03`) | 142 passed; 0 skipped |
| New native renderer-probe matrix (`native-probe-01`) | 7 passed; 0 skipped |
| Source host regressions (`source-host-01`) | 2561 passed; 5 optional machine-QEMU skips; 0 failures/errors; separately adjudicated |
| Source combined native (`source-native-01`) | 132 passed; 0 skipped; 124.799 seconds |

| Installed local lane | Recorded outcome |
| --- | --- |
| Fresh installed host regressions (`installed-host-01`) | 1638 passed; 5 optional machine-QEMU skips; 2 source-only nodes deselected |
| Fresh installed combined native (`installed-native-01`) | 132 passed; 0 skipped |
| Installed retained DOSBox (`installed-retained-01`) | 5 passed; 0 skipped |

The installed host selection contains 50 files, excluding the checkout-only
`test_distribution.py` and `test_package_payloads.py`, and deselecting the
source-derived DOS-method census and isolated source discovery nodes. Those
files and nodes are covered by the source lane. Import receipts verify that
all loaded fDisBull modules came from the fresh installed target. The retained
DOSBox cases cover chord/text input and restore, protected/paged mouse queue
versus guest consumption and explicit release, scene action/outcome/restart,
and an execution-event stop before effect.

Each completed lane recorded unchanged source and runtime inputs during its
execution. The first seven-case native run preceded only package-selector,
ledger/reference and distribution-test updates; the complete native lanes run
those same seven cases again against the final implementation. The source
host selection contains 52 files. Its five skips all request
`FDISBULL_MACHINE_QEMU` for optional raw-machine runtime checks. The wrapper
initially expected nine skips inherited from a different selection; the four
kernel/initramfs cases in `tests/test_dos_qemu.py` are absent from this selection
and are not qualified here. The original rejected wrapper receipt remains
unchanged. `source-host-01-adjudication.json` binds that receipt, enumerates the
five actual skips and accepts the test result without rerunning or relabeling
the original attempt.

The seven native tests use authored DOS programs and actual QEMU/FreeDOS:

| Witness | Established boundary |
| --- | --- |
| Partial and completed authored drawing | Probe/export pixel equality, ordered duplicates, empty and 256-point requests; retained black pixels remain distinct from refreshed partial drawing, then explicit execution publishes red/green changes |
| Palette mutation | A current surface changes red to blue while the older publication remains red; a later explicit publication changes the sampled RGB |
| Mode change and new window | A stopped publication keeps old dimensions and pixels while the current surface changes; a fresh window restarts at update 1 and refuses the old token and outside points |
| JSON, saved script and reopen | Both public routes identify the same publication; probes create no screenshot artifact; three journal entries survive reopen without a live debugger |
| Invalid native requests | Wrong/missing identity, count, coordinate, type and extra-field requests preserve the publication and clock; no partial success |
| Armed budget and reset epoch | Native sampling refuses an armed budget without changing it, and reset invalidates old publication ownership |
| Eight-layer runtime | New helper refuses before QMP I/O while ordinary retained display capture and existing timed-mouse capability remain available |

The authored program's drawing fences do not establish a generic guest-frame
boundary. Renderer completion, current VGA state, guest drawing completion and
mouse input consumption remain distinct observations.

### Review corrections and retained unsuccessful attempts

The initial missing-public-behavior witness produced three intended failures
before implementation. Independent read-only review then identified three
concrete host gaps: initial clock-journal/prequery failures bypassed closure,
JSON `null` lost available raw evidence, and tuple-contained script references
passed validation without resolving. The implementation now covers initial
reads, uses received flags and refuses tuple-contained references in preflight.
Focused regression cases exercise these conditions. Subsequent source review
found no remaining concrete mismatch in the reviewed host/public contract,
documentation, native manifest, package selectors or capability ledger.

Retain the separate environment/build/test failures rather than rewriting them:

- Initial private `pkg-config` flags inspection failed because the extracted
  GLib development package required `sysprof-capture-4`. Extracting the pinned
  private `libsysprof-capture-4-dev` dependency made the second inspection pass.
- The first ninth-layer build stopped during full QAPI generation with
  `unexpected de-indent (expected at least 4 spaces)`. The command's QAPI
  documentation lacked a blank `#` separator before `Since` after a multiline
  `Returns` entry. Only that documentation was corrected; native C stayed unchanged. The corrected patch
  passed forward/reverse source checks, QAPI generation and native compilation.
- `focused-host-01` recorded 140 passes and one test failure: the new journal
  assertion used nonexistent `debug_events.kind` instead of `operation`.
- `focused-host-02` recorded 141 passes and one test failure: the assertion
  expected an exact 50 ms script allowance, whereas the existing integer floor
  yielded 49 ms and then 29/9 ms transport allowances. The assertion now checks
  that existing bounded behavior; production deadline semantics were retained.
- `source-host-01` completed without test failures but its wrapper rejected the
  five-versus-nine skip count. The separate adjudication above retains both
  that rejection and the actual result.

### Recreated native runtime and package identity

The official QEMU 10.0.13 archive was recovered again: 141,718,608 bytes,
SHA256 `4a59b74dac7ead8b162a7c4595dcbbeebe989b90c89cfe6bb4dec5447342f6fa`.
The private environment uses Python 3.12.14, Meson 1.7.0, Ninja 1.11.1,
GLib 2.84.4, Pixman 0.44.0, PCRE2 10.46, FFI 3.4.8, zlib 1.3.1,
NASM 2.16.03 and mtools 4.0.48, with 21 extracted Debian packages and 75
firmware files. Builds used private `x86_64-softmmu`, TCG/Pixman and finite
`ninja -j6`; material growth used 3 GiB estimates plus a 20 GiB reserve.
No shared/system installation or hosted CI was performed.

All eight earlier patch files retain their bytes. The ninth patch changes only
`qapi/fdisbull-display.json` and `system/fdisbull-display.c`; it adds no timer,
event handler or publication state. Its corrected SHA256 is
`d4dc9a87a9c00e807da66339bc8cf055779de754a937ce727b0baa143300f5aa`.
Current native outputs and media have these identities; old binary hashes are
historical evidence and are not substituted for these rebuilt files:

| Input | SHA256 |
| --- | --- |
| Nine-layer candidate | `d42afdd33876a3bef38b45dae8787e9a83ad5838c3d82b1dd9ec5f8ce41dc4a2` |
| Eight-layer probe-legacy witness | `fe840b3513b867020c1af4a80be7662b974b347f3993c55c2101924621edcb00` |
| Seven-layer mouse-click-legacy witness | `cbba1af399b834a1e2d6215fc46bfbc2dd0431526db9efa725b5e49950493b0c` |
| Six-layer standard DOS/type-legacy witness | `9f152f65a5c7affd7dbb4a08150bd9e921765b478da2e2603686d20cd55a2b92` |
| Five-layer press-legacy witness | `806cc8b65ef02a2e361b3efafaec6e08a14585cbd381f800428255a0d825bffa` |
| Original FreeDOS boot image | `552f7cbb0625960c050a3e682a4d2121cc2ffdfa9dc9d592ccd49edf179333dc` |
| Current private prepared FreeDOS image | `0c1d6e413102e66059fbf9820d796b5c94e73bf5279e2413f87fd302eb32cdbf` |
| Retained offline-kit DOSBox-X executable | `795df754019b5e9876d68067cb8d91314b001f28c9c6964502dd57ef21adf79d` |

The fresh private core wheel contains 641 exact core files and has SHA256
`e49c311a96deb917232ad6af2a40acef268e647daba0f8fc89af94b8d83c6986`.
The isolated installed lane received 630 exact copied tests/support files plus
one support script. The tracked source-payload inventory has 1612 entries.
Wheel build/install, CLI, import-origin and bundled-skill checks completed;
the final installed/native outcomes and source-archive acceptance are recorded
with the remaining qualification evidence.

The final source-distribution/tool-ZIP gate compares all 1612 tracked payload
entries and all 24 changed authored files, including this handoff. Publication
requires the privacy and exact-byte checks across both wheels, the sdist and
the tool ZIP, plus final installed-package, copied-test and 1063-input runtime
identity checks. Separate qualification receipts retain archive hashes and
actual imported module paths. The source selectors include the new native
README, manifest and patch. No private runtime, vendor media, project database
or original game bytes enter those authored source artifacts.

### Remaining boundary and continuation

This slice supplies sparse evidence tied to a retained renderer image. It does
not implement legacy `frame_probe`/`video.probe`, `click(x, y)`/`click-frame`,
scene readiness, a full guest-mode epoch, completed guest frames or INT33 mouse
mapping. Equal image dimensions do not establish equal modes; relative PS/2
state does not establish guest cursor coordinates. Preserve those unknowns
when selecting the next coordinate/mode/frame slice. `timed_input`,
`absolute_mouse`, `guest_time_control` and `completed_guest_frames` stay false.
DOSBox remains the default and all 127 promotion qualifications remain open.
Vendor inputs, native binaries, raw logs, runtime databases and emulator states
remain outside Git/packages. The configured macOS mirrors are unavailable here;
this local Linux work does not establish their synchronization or hosted CI.

### Final source and package readback

All four package privacy and byte-payload checks passed. The final source archives contain all 24 changed authored files, including the completed handoff. The 641 installed runtime files, 630 copied test/support files plus their support script, and 1063 private runtime inputs still match their recorded identities. Installed import checks remained inside the fresh target.

| Verified artifact | SHA256 |
| --- | --- |
| fdisbull-0.33.0-py3-none-any.whl | `e49c311a96deb917232ad6af2a40acef268e647daba0f8fc89af94b8d83c6986` |
| fdisbull-0.33.0-tool.zip | `ded17828089685713110c20bc48bb92272e28de687b204b4ebf717fbb091072a` |
| fdisbull-0.33.0.tar.gz | `d473d1c717ab29c5f94984f2e44e6ef70d4f4962416ba7bd1d56dac5b65e2195` |
| fdisbull_player-0.33.0-py3-none-any.whl | `befd84ae231f0cbd6ce8a58e91158cde9cf41cf4e44975afd7db99256928b515` |

These are finite local Linux results. They do not qualify a release or a hosted pipeline.

## Timed native mouse button clicks — 2026-11-09

This continuation adds a physical mouse-button pair on the native virtual clock, extending the earlier physical mouse input. It preserves the existing screenshot-coordinate click contract for later qualification.

### Behavior and recovery

- Python: `mouse_button_click(button='left', *, hold_ms=80)`; JSON: `debug-mouse-button-click`; script: `mouse.button-click`; capability: `virtual_mouse_click`. Exact left/middle/right and integer 1..1000 ms holds validate before deadline/lock admission or I/O. No `GuestMouse` facade or legacy `DebugSession` stub is added.
- One stopped, empty-queue/no-held-lease admission prepares two separate one-event PS/2 batches. Down is due 2 ms after arm, and the actual down callback/sync completion creates the release deadline `hold_ms` later. No requested movement, trailing timer, sleep, run/resume, rebase, subdivision or replay occurs inside the helper.
- The API1 `click` descriptor retains the immutable pair and observed prefix, mutually exclusive with press/type/retrace. The public `fdisbull-mouse-click-1` receipt binds both edges to one paired lease with per-edge timing. Whole-plan lateness is `None`; top-level dispatch appears only after both edges complete. Accepted modes clear prior descriptors; refused native arms preserve evidence and proposed token.
- Pending stops and reached/equal clock budgets win before either edge. First-stop cancellation preserves a delivered down. Another run or schedule is refused while the suffix remains bound. `input_cancel_pending()` discards only unsent edges; the caller explicitly `mouse_button_up(lease)` and chooses release execution.
- One 1000 ms host arm bound includes lock admission, native I/O and persistence, intersecting tighter bounds. Accepted/uncertain late arms, malformed evidence and failed persistence retain evidence and close ownership without replay. Whole-script admission precedes earlier effects, and resolved values validate before arm.
- The existing cooperative 1:1 controller can drive the pair through one explicit `clock_sync_step`. It never extends a budget to complete input or automatically repeats a correction. One native HLT witness exercises the default 80 ms click through that path.

### Fresh local evidence

| Local lane | Passed | Skipped |
| --- | --- | --- |
| Focused integration | 210 passed | 0 |
| New native click matrix | 16 passed | 0 |
| Source host regressions | 2328 passed | 9 |
| Source combined native | 125 passed | 0 |
| Fresh installed host regressions | 1405 passed | 9 |
| Fresh installed combined native | 125 passed | 0 |
| Installed retained DOSBox | 5 passed | 0 |

The nine source/installed skips are the declared optional machine/kernel prerequisites. Installed checks exclude two checkout-only files and deselect two source-only nodes, which run from source. Every selected native and retained DOSBox case runs with zero skips. Source/runtime inventories remain unchanged across every accepted lane; these are local Linux results, with no hosted pipeline claim.

The independent IRQ12 fixture resets a fresh PS/2 mouse, explicitly enables stream mode and verifies a polled zero-state packet. It then observes separate down packets (`09 00 00`, `0a 00 00`, `0c 00 00`) and release (`08 00 00`) in busy and HLT loops. The matrix covers original stops before down and after a complete down packet, explicit release recovery, equal-budget ordering, old seven-layer refusal with ordinary input retained, JSON/scripts/journal/reopen, and transitions among click/press/type/ordinary/retrace modes. The down boundary tests both actual timer insertion orders; release covers both command-arm orders because that timer is created only after down. Raw invalid arguments, owner tokens and hold endpoints are checked too.

Callback completion is narrower than arbitrary device FIFO acceptance, guest consumption, pointer position, INT33 behavior, application click recognition or frame completion. Prior motion accumulators and external button state can affect arbitrary packets. Dynamic handler replacement between the two edges remains a code-inspected path, not a click-specific native runtime qualification.

Installed retained DOSBox checks cover keyboard chord/text/restore, protected/paged mouse queue versus program consumption and release, scene action/outcome/restart, and execution-event stop-before-effect. DOSBox remains the default.

### Reproduction and packaging

- Eighth patch: `23f38d65391587b0be11af021fc3858872475d25a03719844b486719eee154d9`. All seven earlier patches retain their bytes. Forward/reverse application uses zero fuzz/offset; the complete 26-member native state and full schema generation are verified. The keyboard dispatcher remains byte-identical.
- Fresh eight-layer binary: `daac51e3d63d24dad8e39b8df5d1c6c843411d962fa1d37527fa25a11dbf50f5`. The retained seven-layer refusal binary is `07322555c94ac7acfb6e5fcf0fcc6af42c4742fe169095854fa8f86bf68b9368`; existing six/five-layer legacy witnesses remain selected. The existing private toolchain, firmware, prepared FreeDOS image and retained DOSBox provenance are preserved.
- Fresh wheel: 641 exact core files; 626 byte-identical copied test/support files. Installed checks run outside the checkout with import-origin assertions. The final source distribution and tool ZIP contain all 26 authored changes, including the final handoff, and pass the repository payload/distribution checks.
- Verified final source tree: `ee3aaa373bd6dc98b9143a70f8ee771420bc4d66`. Published head: `fd46fbe8fa4c7819aff3bd19c08415566f8df0db`; parent: `54c4df083d44d6070722fa1298eebbca6ef85d68`. The API publication uses per-file revision preconditions and is fetched back for full-tree equality. No source is inferred from a nearby revision.

Retained attempts: the initial public/host gaps fail for missing behavior. The first host lane had one pass and 108 setup errors because its private target store was under Git-managed `/workspace`; correcting that store to a protected `/tmp` directory and expanding the selection to include the public tests yielded 147 passes. Independent review found invalid direct values reaching lock admission; four busy/expired regression cases failed before pure mouse validation moved ahead of admission, then the integrated 210-case lane passed. The first broad source lane had 2311 passes and no assertion failures, but its wrapper rejected 17 unexpected native prerequisite skips (26 total) because runtime variables were omitted. The corrected full source lane executes those cases and leaves only the nine declared skips. All original receipts remain; none of those incomplete attempts is relabeled as a pass.

The full slice remains partial. `timed_input`, `absolute_mouse`, `guest_time_control` and `completed_guest_frames` stay false, coordinate/frame click APIs remain pending, and every one of the 127 promotion qualifications remains open. No merge, release, shared install, hosted CI or unavailable Mac mirror synchronization is performed.

## Timed native keyboard text — 2026-11-09

Continued the next bounded input slice from `16d115769c027e02427c24fa60b1b12496c8be47`. The previous native extension implemented a single chord while the existing text routes still refused. The seventh patch now supplies `keyboard_type(text, hold_ms=40, gap_ms=40)`, `GuestKeyboard.type`, JSON `debug-keyboard-type` and script `keyboard.type` under the optional `virtual_keyboard_type` capability. It requires the native virtual clock and input command set; precise retrace is unnecessary. The six-patch binary still supports press and correctly refuses type.

### Behavior and ownership

- Validate the entire 1..64-character string and strict 1..1000 ms hold/gap values before one stopped arm. Accepted characters are printable US-layout ASCII plus CR, LF and Tab. CRLF produces two Enter chords. Uppercase and shifted punctuation use fresh Shift chords. Empty text, unsupported controls, non-ASCII suffixes, embedded NUL and invalid timing refuse atomically.
- Prepare up to 256 edges and pin each native one-event batch before consuming the token. The first edge and other make/Shift-break edges wait 2 ms; main breaks wait hold_ms. A later character's first edge waits gap_ms + 2 ms from the preceding character's actual final release. Every deadline is callback-relative, with no trailing gap timer.
- Reserve up to 128 distinct key lifetimes separately from active leases. Only a fully validated delivered prefix changes the private candidate ledger, and only delivered makes enter the active ledger. The plan holds at most two keys; the existing 64-active-lease and 256-pending-edge limits remain.
- Preserve native input API1 and add mutually exclusive `typing` metadata. Public `fdisbull-keyboard-type-1` steps retain character index, lease, sequence, key/qcode, delay, deadline, dispatch and lateness. Top-level dispatch exists only on full delivery, and whole-plan lateness remains None. Terminal evidence freezes; accepted switches among press/type/ordinary/retrace modes clear incompatible descriptors.
- Every edge honors pending stops and reached/equal clock budgets. The first actual stop cancels the suffix. Another run or reschedule refuses until explicit `input_cancel_pending` discards unsent steps/reservations; callers explicitly release retained holds and choose their execution. Cancellation does not replay or synthesize releases.
- Arming never executes, sleeps, rebases or subdivides input. One explicit `clock_sync_step` drives a halted text witness while preserving fixed host/native anchors. Maximum legal timing can span 127,384 ms, beyond one 60-second clock advance; a shorter budget cancels the suffix.
- Script literal/capability/transaction checks precede earlier mutations, resolved arguments revalidate, and one 1000 ms direct-arm allowance includes lock admission and persistence while respecting tighter incoming bounds. Accepted/uncertain late arms or malformed/unpersisted evidence retain known evidence and close without replay.

### Verification and retained corrections

All 20 new native cases passed on the first feature run and again in the source and fresh installed combined selections. Independent US-map/scancode and delay oracles cover busy/HLT mixed strings, repeated key/Shift lifetimes, CR/LF/Tab/punctuation, the 64-uppercase maximum, original breakpoints before make and after Shift IRQ, explicit recovery, between-character cancellation, legacy refusal, JSON/script/journal/reopen, descriptor clearing, and one-step auto-sync. Equal-budget boundaries cover first make, release and the next character in both command-arm orders. Only first make exercises both actual timer insertion orders; later timers are created after the already queued budget.

| Local evidence | Result |
| --- | --- |
| Focused type/press/physical/ordinary/retrace host contracts | 323 passed, zero skips |
| Public press/type routes, scripts and deadlines | 57 passed, zero skips |
| First native typing feature lane | 20 passed, zero skips |
| Broad affected source selection | 2,177 passed, 9 prerequisite skips |
| Combined source native selection | 109 passed, zero skips |
| Fresh installed host selection | 1,254 passed, 9 prerequisite skips, 2 source-only nodes deselected |
| Fresh installed combined native selection | 109 passed, zero skips |
| Retained DOSBox chord, text/script/restore and event-predicate witnesses using the installed wheel | 3 passed, zero skips |

Selections overlap. The stock skips remain five separately configured raw-machine cases and four legacy Linux-hosted DOS/QEMU shim cases missing their kernel/initramfs selection. The first source driver omitted the latter skip category: pytest had no failures/errors, but the driver retained its failed classification result. A separate review classifies those known prerequisites without rerunning or counting them as passing. Installed stock excludes the checkout-only package/distribution files and two source-only inventory/discovery nodes; those checks passed from source. The installed driver explicitly fixes rootdir for exact deselection. Import guards verified all loaded fdisbull modules originated in the fresh installation (129 host, 114 native), with copied tests outside the checkout.

The pre-change host and script gaps remain captured. The first public implementation run had 45 passes and 12 failures: eleven identified the omitted script-operation advertisement, and one identified cleanup after an accepted arm exceeded its outer deadline. Both seams were corrected and the 57-case public selection passed. No timeout inflation or automatic retry was used. The earlier press slice's installed retrace observation deadline failure remains an unresolved historical observation; these fresh passes do not establish its cause.

### Runtime and package identity

The reset workspace recovered the published source and rebuilt private runtimes from the pinned official QEMU 10.0.13 archive. All six earlier patch bytes remain unchanged. The new patch passed zero-fuzz/offset forward/reverse verification against that baseline, with all 26 native members matched/restored, complete QAPI validation/generation and successful native compilation. The default IRQ1 fixture's busy/HLT bytes and symbols are unchanged; only the text witnesses request capacity 256.

Fresh validation used Linux and Python 3.12.14. The candidate seven-patch clock binary is SHA256 `07322555c94ac7acfb6e5fcf0fcc6af42c4742fe169095854fa8f86bf68b9368`. Standard DOS and the type-legacy witness select the separately built six-patch binary; the press-legacy witness selects a five-patch binary. The optional four-patch retrace-legacy secondary VM was not restored. Fresh FreeDOS preparation has newly generated DOS directory timestamps and SHA256 `ad852960ff1fd1355c28ac6295924c90ae88a0e23d66586f6c0ad6dff173a0af`; it is not presented as the lost prepared image. The retained DOSBox executable keeps SHA256 `795df754019b5e9876d68067cb8d91314b001f28c9c6964502dd57ef21adf79d`.

| Artifact | SHA256 | Verified payload |
| --- | --- | --- |
| Seventh native patch | `d680d253af93b60d3101ef74c1243e19e887b1cabdf0df194fdec0aafed23cc5` | Manifest, native source and built candidate agree |
| Core wheel | `14fd94d362c967e189197fc9dfb4cbdf06916da0927f7f835366dacc18331675` | 640 core members match source/wheel/install; 645 total members; 622 copied test/support files match source |
| Source distribution | `0bdbd90b1199319b02258b1fe2f57c03f1f3a64574375b160bab08441cf07dc3` | 2,223 members; exact 1,597-file source payload and all 23 authored changed files |
| Tool source ZIP | `2d8cadededb2ef5124d0720b8b523503244813648ca0dcd7edba88bc1485a774` | 2,205 members; same exact payload and all 23 authored changed files |

The actual wheel and both source archives passed the repository distribution/privacy checker. The source archives contain the completed handoff entry. Vendor media, native executables, runtime databases and states remain outside Git and these packages. Each lane retained its exact inputs and exclusive local receipts; material growth admitted 3 GiB plus 20 GiB reserve. This is the bounded slice package verification, not the complete release package-smoke route or hosted CI.

The tested and packaged Git tree is `3b6cfde67d766f28c097113f3863a10f1f625423`. The local author commit `0f55da0fb079e27ecea220641976cde654575463` is retained on `recovery/qemu-keyboard-type-0f55da0fb079`. Direct Git push lacked write credentials and left the remote unchanged. The authenticated connector published `54c4df083d44d6070722fa1298eebbca6ef85d68` with 16 checked file-level update revisions and seven creates; its parent is the expected `16d115769c027e02427c24fa60b1b12496c8be47`. Fetch/readback proved the entire published tree equals the verified author tree. The local source branch now tracks that published head with a clean worktree. The original stacked target and historical handoff/MR sections remain intact.

## Timed native keyboard presses — 2026-11-09

Continued from `b6011c68042918942a1d52ff0d8c17ff42343501` on the same draft MR and target. Published head `16d115769c027e02427c24fa60b1b12496c8be47` has full tree `ac6457457e539d2b244a2b7d3ee6705389567435`, identical to the locally verified author tree. The 21 authored paths include implementation, native patch/manifest, witnesses, package rules and the maintained guides/log. The local author commit `7b39e1196411f7d8972036162f379a95fe6bb298` is preserved on its recovery branch.

### Existing public workflow, passive native timing

`keyboard_press(key, modifiers=(), hold_ms=40, gap_ms=40)`,
`GuestKeyboard.press`, JSON `debug-keyboard-press` and script `keyboard.press`
now share the optional `virtual_keyboard_press` capability. It requires the
explicit virtual clock, existing clock/input command set and the new
`x-fdisbull-arm-keyboard-press` command. A precise retrace profile is unnecessary.
Older native binaries retain their existing capabilities and refuse this route.

One stopped admission requires an empty owned queue and no active owned leases.
It prepares a chord of two through eight edges without executing the guest:
caller-order modifier makes, main make, main break, reverse modifier breaks.
The first edge and every later make/modifier break waits 2 ms; the main break
waits hold_ms from the actual main make. Each next deadline derives from the
preceding actual callback, so late dispatch cannot shorten the requested hold
or collapse later release spacing. Strict hold_ms/gap_ms bounds are 1..1000.
gap_ms is validated and retained without effect for a single press, matching
the retained DOSBox contract; it belongs to that backend's separate text queue.

The caller chooses one later bounded run, clock advance or cooperative
clock-sync step. Input never runs or rebases the clock itself. The native
acceptance witness drives a halted chord with exactly one explicit
clock_sync_step while preserving the controller's fixed host/native anchors.

### Prefix evidence and explicit recovery

The sixth native patch adds an optional press descriptor to the existing input
API1 receipt and retains the existing query/cancel commands. It copies and
pins each one-key batch before committing the arm/token. The descriptor binds
the key/modifiers/timing, immutable step order, each assigned deadline, actual
callback/sync timestamps and a delivered-prefix count. Only the immediate next
deadline is assigned; later edges are not placed on a predicted absolute grid.
Ordinary/retrace accepted arms clear press metadata, and press arms clear
retrace metadata. Shared bounds, token history and migration restrictions remain.

Every edge preserves pending debugger/native-stop and reached/equal
clock-budget precedence. The first actual stop cancels the undispatched suffix;
completion itself does not stop the VM. Both actual timer insertion orders are
witnessed for the first make. The release witness covers both command-arm
orders, while accurately retaining that its timer is created only after make,
so its clock budget is already queued in both cases.

The host validates the full plan, callback-relative recurrence, prefix
monotonicity/freeze, epoch/token, terminal times and every edge's owned-budget
cutoff before changing leases. It applies only a newly proven prefix to a
private lease ledger. Top-level dispatch_ns is absent for cancellation even
when makes were delivered; inspect press.dispatched_count and leases.
Top-level lateness_ns is None for a chord; each public step reports its own
lateness against its assigned deadline. This avoids counting the requested
hold duration as lateness.

A cancelled press remains bound and cannot run again or be converted into
ordinary/retrace scheduling. Explicit input_cancel_pending discards unsent
steps while retaining dispatched holds and clearing their pending releases.
Callers then explicitly key_up each retained lease and choose its execution.
There is no automatic suffix replay or synthetic cleanup release.

Literal/capability/transaction script checks precede earlier script mutations;
resolved values are revalidated before arming. One 1000 ms direct-arm host bound
covers lock admission, I/O and persistence, intersecting tighter incoming
bounds. Pre-arm admission expiry leaves a valid owner available. Accepted or
uncertain late arms, malformed/native-failed evidence and failed persistence
retain available native/stop evidence and close without replay. Failed scripts
that touched input close the owner. Terminal native step evidence stays frozen.

### Native witnesses, compatibility and retained corrections

The original press refusal and script-grammar failure were retained before
implementation. The new focused host selection has 75 press cases and the
existing physical/ordinary/retrace input checks: 228 passed, zero skips. Public
routing/admission/deadline checks add 26 cases, also exercised in the full lanes.

All 16 new native cases passed on the first feature run and again in the source
and installed combined selections. Busy/HLT × plain/shift/full chords inspect
actual IRQ1/scancode bytes and an independent delay recurrence. The busy full
chord demonstrates a late main-break callback followed by a deadline based on
that actual time. Other witnesses retain original breakpoints before/after
make, demonstrate held-lease cancellation/release, verify equal cutoffs, refuse
the older five-patch executable, preserve JSON/script/journal/reopened evidence,
compose with clock auto-sync and reject invalid native command arguments
without consuming their token. The fixed gap value of 1000 ms does not create a
tail timer: each admitted chord completes well before that interval.

Three early host-test assertions attempted a public state read after their
intentionally expired deadline; they were corrected to inspect retained private
invalidation state. Compatibility checks exposed a minimal unsupported owner's
missing configuration producing AttributeError; the guard now returns the
established unsupported guest-time ValueError. The first broad source lane had
1302 passed, one failure and five optional skips: the operation correctly
refused before an earlier script step, but its error text lacked the retained
"guest clock" wording. The wording was restored, that regression passed, and
the full final source lane passed afterward. All failed receipts remain retained.
No native implementation change or rebuild was needed after its first build.

The first installed combined native attempt retained 88 passes and one failure
in the unchanged retrace-input budget-first witness. Its initial stopped
retrace bracket completed six QMP calls, then locally refused the final clock
query because the shared host deadline had expired, before any input or clock
arm. The request's default allowance is 1000 ms, intersected with incoming
bounds; the failed log does not establish where time was consumed or whether
an inherited bound shortened it. An observation-only isolated repeat passed
with the same wheel, binary and production bounds. Independent comparison
found no change to the observation path or its effective default. The one
finite full installed-native repeat passed all 89 cases without changing code
or increasing timeouts. The original failure and isolated timing records remain
retained; no root cause is assigned from the successful follow-up.

### Exact reproduction and local qualification

The unchanged five prior patches and new sixth patch reproduced from the
pinned official QEMU 10.0.13 archive using 92 required regular source/QAPI/parser
inputs. Forward/reverse application had zero fuzz/offset; both changed native
members matched the built source and reverse restored all 26 prior native
members. QAPI schema validation and generation passed. The private x86_64
TCG/Pixman build configured in 15.751 s and compiled in 90.197 s, with no source
change during either phase. Runtime inputs, databases and vendor media remain
outside Git.

- Sixth patch SHA256: `0098d4301d8703d7d740b58ae0f048d0a73ec6e9c9ce10cec04457bebb1c4ed0`.
- Native executable SHA256: `b09fa87715cd0c7826fcd03ce8537b9b95ae2e209f15c677ffbc579ad261a78a`.
- Private wheel SHA256: `2498503d9580c0fac926b60cc01aa05cc0eeb3b2ab719f4efc321722840928bd`.

| Local selection | Result | Elapsed |
| --- | --- | --- |
| Affected source regressions | 1303 passed; 5 skipped | 159.977 s |
| Combined source native selection | 89 passed; 0 skipped | 72.562 s |
| Fresh installed-wheel regressions | 1292 passed; 5 skipped | 127.405 s |
| Fresh installed-wheel native selection | 89 passed; 0 skipped | 319.924 s |
| Retained DOSBox chord and trace witnesses | 2 passed; 0 skipped | 17.354 s |

Selections overlap. The five skips in each broader lane are the existing
optional raw-machine session cases with FDISBULL_MACHINE_QEMU unset; they are
not counted as native passes. Both required native lanes include all 89 cases
with zero skips. The retained DOSBox lane exercises actual timed chords,
pending-input checkpoint restoration, and the earlier source predicate/hook
boundary. This does not establish native QEMU checkpoint support.

The wheel's 639 core members and 619 copied test/support members are verified
against source, with installed import-origin checks outside the checkout.
Final source artifacts bind 1590 tracked payload files and all 21 authored paths;
their hashes and the exact tested tree are retained in the MR publication
receipt. Package payload/distribution checks are mandatory before publication.

The source ledger now includes the previously implemented fifth-layer witness
set as well as this press increment. Its press routes change from pending to
partial; all 127 promotion qualifications remain open. DOSBox remains default
and both selectors remain available. Native callback completion still leaves
FIFO acceptance, arbitrary guest consumption and completed drawing unknown.
Text/click helpers, renderer/frame/VBlank semantics, coordinate mapping,
input-to-source causality, broader audio, real QEMM/DESQview/game campaigns and
checkpoint/history dependencies remain open. No hosted CI, merge, release or
shared installation is claimed; the configured Mac mirrors remain unavailable.


| Private package artifact | SHA256 |
| --- | --- |
| Wheel | `2498503d9580c0fac926b60cc01aa05cc0eeb3b2ab719f4efc321722840928bd` |
| Source distribution | `9889bd449f8cc79f9b174d1f04c3a141d8eadfca6b9ba5d21d966d104dd68a89` |
| Tool source ZIP | `f2999621fbd53637b665eb3d762b544e89ed6c17cb7b239a1504e56718eb09ef` |

Exact source/package/native identities and local test receipts are retained privately. Publication uses `[skip ci]` and preserves the existing draft state.

## Generation-checked retrace input — 2026-11-09

Continued from `67a6c40d91de383f3986bc1902932a0a7dca16c2` after verifying the previous timing publication. This increment is published as `b6011c68042918942a1d52ff0d8c17ff42343501`; its full Git tree is `8b8c8748ef9fd9742b08e0fb4403912f254ae578`, exactly matching the locally tested author tree. The 23 authored paths include implementation, native patch/manifest, witnesses, package rules, guides and the maintained handoff. The prior local author commit `20b7fe31178f65f2e4bacc3d58e5ffe00090300c` remains recoverable.

### Behavior and ownership

- Python `input_schedule_retrace(*, edge='enter', timeout_ms=1000)`, JSON `debug-input-schedule-retrace`, and saved-script `input-schedule-retrace` share one owned operation. Admission requires explicit virtual/precise profiles and the complete native command set. Arming is passive and uses the existing pending batch, input timer, batch bounds and token/lease ownership.
- The new native command checks exact expected epoch/device/model/generation/time and computes its own strictly next target and exclusive window. A private BQL-held snapshot of the already admitted VGA supports the stopped arm and running callback without admitting an owner, touching guest I/O, rendering or refreshing timing. The public passive query keeps its stopped/no-active-budget guard.
- Pending stops and reached/equal clock budgets win before phase sampling in both timer insertion orders. To permit delivery, the caller explicitly runs beyond the input target. Timing-generation changes, including ABA/VBE transitions, cancel as `retrace-timing-changed`; arrival beyond the unchanged original window cancels as `retrace-missed-window`. These cancellations do not add a stop or automatically retarget.
- Success requires the historical check, dispatch and terminal timestamps to match inside the original absolute window. The host independently validates arithmetic, identity, generation and chronology before accepting leases. Later observations cannot relabel the frozen check. Pending input requires explicit reschedule/cancel; a cancelled release retains its earlier hold.
- Whole-script literal/capability/transaction preflight and resolved-option validation precede arm. The remaining deadline includes lock admission, native observations, mutation and persistence. Failed scripts close an armed owner, including a batch queued before the script. Lost/late replies and journal errors preserve available evidence and close without replay.

The qualified boundary is native modeled-phase PS/2 callbacks and final sync. Full VBlank, completed guest frames, arbitrary guest consumption, legacy timed-helper parity and whole-game timing remain separate qualifications. The earlier cooperative host auto-sync controller and retrace waits remain available.

### Verification and repaired boundaries

All results below are local Linux; selections overlap and should not be summed as unique tests.

| Selection | Result |
| --- | --- |
| Focused host contracts (81 new cases plus existing schedule/retrace checks) | 272 passed; 0 skipped |
| Public routes, script parameters and ownership | 22 passed; 0 skipped |
| Affected source regressions | 1190 passed; 5 skipped |
| Combined source native selection | 73 passed; 0 skipped |
| Fresh installed-wheel regressions | 1179 passed; 5 skipped |
| Fresh installed-wheel combined native selection | 73 passed; 0 skipped |
| Retained DOSBox native witness | 1 passed; 0 skipped |

Each combined native lane includes all 13 new cases with zero skips: busy/HLT × enter/exit; actual guest IRQ1/scancode/status-port fence evidence; ABA and VBE cancellation; original earlier breakpoints; both equal-deadline insertion orders; retained release ownership; ordinary-arm descriptor clearing; JSON/scripts/reopened records; stale arm expectations; and the optional retained four-patch executable. That older executable explicitly lacks the new capability while ordinary delta scheduling still succeeds. The five skips in each broader lane are the existing optional raw machine-session tests with `FDISBULL_MACHINE_QEMU` unset, not native passes. Missed-window behavior has deterministic host receipt adversaries; no artificially forced native missed-window result is claimed.

Retained failing witnesses identified and repaired: final-wrapper expiry leaving a live arm, referenced timeouts normalized before validation, reserved cancellation reasons on inconsistent states, and callback evidence lost on validation/persistence failure. Two host assertions were corrected to compare the input ledger rather than observation metadata. The initial new native run was 12 passed/1 witness failure: explicit clock cancellation correctly returned `cancelled`, while the test expected `stopped`. The corrected witness verifies the actual stopped receipt first, then proves cleanup changes only budget state and leaves input evidence unchanged. Both complete native lanes passed afterward; native implementation bytes did not change after the first successful build.

The fifth patch applies after the four unchanged exact layers and modifies six native members; the combined manifests identify 26 final source paths. A strict full-archive extraction first stopped at an unrelated absolute EDK2 link. The retained follow-up reproduced the 92 required regular source/QAPI/parser inputs from the same pinned official archive. Final patch application/reversal had zero fuzz/offset, all six output hashes matched the built source, all 25 prior members were restored, and QAPI schema validation passed. The private x86_64 TCG/Pixman build configured in 16.668 seconds and compiled in 110.166 seconds. Its executable is `744270aeecfbe1a05da6b170b7c1be3a634476444f4cf7ef3f583cb3c16819b7`; the final fifth patch is `5d80203da6c395aa987c8bdde80bb04db1badd169ce3bea258f50e0cdb6cdc80`.

The wheel matches all 638 core files and the installed selection uses 616 copied test/support files with import-origin checks. Source distributions match all 1,583 tracked payload files and all 23 authored paths. Distribution checks passed and private runtime media remain outside Git.

| Artifact | SHA256 |
| --- | --- |
| Private wheel | `0d63772ae777196586dc5ad8c04cd78df00d367059e410b085151a15735f65ef` |
| Source distribution | `8caafd4c22139410e127df81167bd9aea6166aa92a1b110d64162adeb150658a` |
| Tool source ZIP | `6d17a74b05e2809d0dc845a51462718cef1bd909f410dcf43ec7de7ff4084558` |

The exact source/package/tree and publication receipts are retained privately. DOSBox remains the default, both retained selectors stay available, and all 127 promotion entries remain open. This source publication used `[skip ci]`; no hosted CI, merge, release or shared installation was performed.

## Cooperative clock synchronization and retrace waits — 2026-11-09

The latest request authorizes timing auto-sync, superseding the deferral in the
earlier dated entries. This continuation adds a cooperative host/native clock
controller and one-shot precise retrace waits on top of the existing clock,
media, input and retrace patch chain. No additional native patch is needed.

### Behavior and stop policy

- `clock_sync_start/observe/step/stop` bind a fixed 1:1 mapping between native
  virtual time and host monotonic elapsed time. Original anchors persist across
  calls. Python/helper work, I/O, persistence, debugging and caller idle all
  count; actual intervening guest progress and prior timer overshoot are deducted.
- One explicit step freezes one target and automatically chooses no action,
  one bounded native catch-up, or one host sleep with the guest stopped. The
  receipt preserves actual residual drift. Excess lag/lead latches
  desynchronization; explicit stop/start chooses fresh anchors. There is no
  background execution, implicit rebase, repeated correction loop or rate change.
- `retrace_wait(edge='enter'|'exit')` plans the strictly next occurrence from
  the selected precise VGA model, uses one native budget and verifies the
  stopped result. Synchronization requires unchanged run/epochs/device/model/
  timing generation, an ordinary timer stop and the exact absolute target
  window. Unsupported/full-period timing does not execute; changed timing,
  missed windows and other stops do not retry or retarget.
- Early/coincident debugger stops and DOS lifecycle results remain original
  evidence. Scheduled input retains first-stop cancellation and explicit
  resolution, with no automatic release/re-arm/replay. Explicitly queued input
  still follows its existing delivery path during a sync advance.
- Python, retained JSON and saved scripts share capability, signature, literal
  parameter and transaction checks. One intersected deadline covers lock
  admission, observations, correction, cleanup and persistence. Late storage
  and final wrapper expiry retain known results and latch the mapping.

### Verification and repaired witnesses

| Selection | Passed | Skipped |
| --- | ---: | ---: |
| Focused host clock-sync contract | 57 | 0 |
| Retrace wait plus existing passive contract (62 new + 78 existing) | 140 | 0 |
| Public routes and script preflight | 40 | 0 |
| Affected source regressions | 1,087 | 5 |
| Combined source native selection | 60 | 0 |
| Fresh installed-wheel regressions | 1,076 | 5 |
| Fresh installed-wheel combined native selection | 60 | 0 |
| Retained DOSBox native witness | 1 | 0 |

Selections overlap. The five source/installed skips are the existing optional
machine-session checks requiring `FDISBULL_MACHINE_QEMU`; both required combined
native lanes have zero skips. Installed tests assert imports from the fresh
isolated wheel, with no fallback to the checkout.

The first new native lane was 13 passed / 1 failed: the script witness compared
raw stored numeric DOS addresses with JSON-formatted hex strings. Timing values
matched. It now compares the full formatted report and independently checks raw
artifact-to-journal equality. The host-wait witness additionally records exactly
one real positive bounded sleep and unchanged native time/counters.

Focused failure/pass evidence also covers ordinary DOS stops carrying active
process metadata, final wrapper deadline expiry, and the checked host timestamp
after sleeping. The last case initially accepted a 20 ms wait inside a reported
10 ms interval; the fixed controller invalidates that regressed sample while
retaining its evidence. Native cases cover busy/HLT/PIT behavior, actual CR10
A-to-B-to-A writes, an early breakpoint, input cancellation, DOS exit, failed
SQLite persistence and saved evidence after reopen.

The wheel matches all **638 core files**. Source distribution and tool ZIP
match **1,576 tracked payload files** and all **21 authored paths**; distribution
checks pass. Wheel SHA-256:
`f065776953cb0a6ba76a5d96468773d8da54d873df25c009a8ae1d5886f037e1`.
Tested source tree: `b1b6e7fee86a9b43d5b2c934b70ba3334c6e319f`.

The reused QEMU 10.0.13 binary is
`5d202d2ec57d596351381d7fc1df67211c4d0727ad667119183d41b450c96565`.
The unchanged four-patch reproduction still matches all 25 final native source
paths with zero offset/fuzz. Local commands, JUnit, input hashes and failure
receipts remain under the private `takeover-validation/autosync-*` prefix.

This qualifies explicit cooperative synchronization and modeled transition
waits. Full guest frames/VBlank, hardware-cycle/DOSBox timing parity, timed
helpers, frame-edge input, audio drain/playback alignment, QEMM/real games,
checkpoints and later migration slices remain open. All **127** default-promotion
entries remain unqualified; DOSBox stays the default. Results are local Linux
evidence. No hosted CI, merge, release or shared installation was performed;
the configured macOS mirrors remain unavailable.

## Precise VGA retrace continuation — 2026-11-08

The requested publication retry first confirmed that the earlier source-clock commit `652394fd313a0c33e7b8c30bf9b138928b0d2773` and its handoff were already present. This continuation publishes `5d15ff9acb3ab0d87d1c829f3ec8fd505da69c69` on the same branch and target. Its full tree `e03b9b5ba4e5639aa752d0696cd80bf3dc4fcfe3` matches the tested local author tree.

### Behavior and limits

- Select `qemu_clock='virtual', qemu_retrace='precise'` for a fresh paused PC boot. Python `retrace_observe(timeout_ms=...)`, JSON `debug-retrace-observe`, saved-script `retrace-observe` and CLI `--qemu-retrace` are integrated. The standard profile remains the default.
- The passive native `x-fdisbull-query-retrace` command reports the exact primary VGA identity, native epoch/time, raw timing registers, cached model tuple, monotone timing generation and a supported phase or explicit unsupported reason. The host independently validates the formulas and a stable before/native/after clock bracket, then persists one `machine-retrace-observe` event.
- The explicit property `VGA.x-fdisbull-retrace=on` makes timing inputs coherent at completed writes, including CR10 and VBE/effective-SR1 transitions. Separate A→B→A writes advance identity even without an intervening query. Ordinary VGA and ordinary precise VGA without this property retain their prior behavior.
- Uninitialized timing, VBE and invalid/wrapped legacy intervals return valid unsupported evidence. Some ordinary text modes do not qualify. Capability availability does not promise a supported phase in every mode.
- Querying does not advance time, resume the CPU, read guest `3DAh`, change the attribute-controller flip-flop, render, repair the cache, arm a timer or wait for an edge. Admission pins the exact primary VGA and blocks migration for the process lifetime. Reset/epoch loss, malformed evidence or incoherent identity fail closed.
- One absolute deadline spans lock admission, native observation and persistence, intersecting existing script/session/channel limits. Whole-script preflight precedes earlier writes. A late synchronous evidence write can retain its receipt in `error.result`; execution is never replayed.
- This observes `qemu-vga-precise-fdisbull-v1`, including its approximations. It does not establish physical VGA accuracy, the full VBlank interval, guest frame completion, input consumption, historical pixel alignment or a full display-mode identity. Timing auto-sync remains deferred.

### Local verification

| Lane | Result |
| --- | --- |
| Focused host/public retrace selections | 78 and 23 passed, zero skips |
| Final affected source stock/public/process/script/deadline/inventory/package selection | 928 passed, 5 skipped |
| Source combined native source-clock/input/clock/audio/display/retrace selection | 46 passed, zero skips |
| Isolated installed wheel: applicable stock/public selection | 917 passed, 5 skipped |
| Isolated installed wheel: combined native selection | 46 passed, zero skips |
| Isolated installed wheel: retained DOSBox predicate/hook/reopen witness | 1 passed, zero skips |
| Core source/wheel/installed identity | All 637 package files match |
| Source distribution and tool-source ZIP | All 1570 tracked payload files and all 22 changed authored paths match; tool-only checks pass |

Selections overlap. The eight new native witnesses are included in each 46-case combined selection and also passed separately. They compare actual guest `3DAh` reads, preserve the attribute flip-flop, observe CR10 and unobserved A→B→A changes, handle VBE/invalid transitions, preserve distinct source/clock/renderer provenance through reopen, retain ordinary DOS use, and refuse armed budgets or lost epochs.

The five skips in each stock selection are the optional raw-machine boot/watchpoint/foreground tests gated by unset `FDISBULL_MACHINE_QEMU`. Unix socket creation is restricted in this executor; required native witnesses use pipes and had zero skips. The previous-wheel gap witness first failed on the absent `qemu_retrace` argument. Runtime lanes were serialized and tested input bytes remained unchanged. Independent native and public-surface reviews found no concrete blocker.

The former thread's scratch tool paths were absent. A separate private Python 3.13.5 environment, verified NASM/mtools and retained DOSBox runtime restored local checks. The FreeDOS baseline is a surviving prepared earlier-test image, not a recovered original distribution image; firmware came from the verified QEMU archive. No runtime inputs are committed.

The new native QEMU build applies the exact clock, media, input and retrace patch chain to QEMU 10.0.13. All four patches applied with zero fuzz/offset and all 25 final native source paths matched the built tree.

- Wheel SHA-256: `ca0038152f6ca6ea47fb4ca9d6aa836270f33481fd8fda0553519b1e0cfb67db`.
- Native QEMU SHA-256: `5d202d2ec57d596351381d7fc1df67211c4d0727ad667119183d41b450c96565`.
- Retrace patch SHA-256: `9647eb1c7afc14aeea3e1fb826a389c3865e5d3ab420b060a8d3d45319044a1c`.

A later bounded gate can qualify retrace-edge barriers or an explicit renderer-publication association. Neither is implemented here. All 127 default-promotion entries remain unqualified. The earlier parallel-startup, large-MZ and DOSBox idle timeout observations remain unresolved. These results are local Linux integration evidence; hosted CI, releases, real-game/QEMM/V86 campaigns, Windows and macOS remain separate qualifications.

## Native virtual-time source-trace continuation — 2026-11-08

Continued from `341847d48f55c877b4db645c3c98a9c72beeafe8`. Published head: `652394fd313a0c33e7b8c30bf9b138928b0d2773`; complete tree: `d886e7ac75a5079c71b3fe605a1cf3ecb471ab8e`, verified byte-for-byte against tested local author commit `90b224cb470468f050ca3a8700fb3667a7317dbc`. This increment contains **23 authored paths** and reuses the existing native runtime. **Timing auto-sync remains deferred.**

### Behavior and failure evidence

- Add the `source_trace_clock` capability to the initial verified real-mode COM/MZ adapter under the explicit `virtual` clock profile. Each stopped source event retains `fdisbull-source-clock-1`: the run, host clock epoch, native epoch, virtual nanoseconds, separate instruction counter and compact before/after samples. These samples surround ownership, register/address and source qualification; changed time/counter/native epoch is rejected and closes the owner. The private snapshot helper does not add two redundant clock-observe journal entries per event.
- Add exact `virtual-time-range` predicates with a half-open integer interval `[start_ns, end_ns)` bound to the same run and both epochs. Live traces reject unsupported or foreign identities, including nested predicates, before execution. Saved scripts validate literal clock identities before earlier writes and recheck at trace admission. Trace-until interpolation remains unsupported; obtain the identity in an earlier request. Matching happens at observed debugger boundaries, not at a newly installed exact timer cutoff.
- Validate clock provenance and ordering when normalizing and storing traces: no mixed timed/untimed rows, native-epoch mismatch, regressing clock/counter or overlapping sample sequences. Offline missing/foreign clock evidence evaluates as unknown; malformed clock evidence rejects even register-only queries. Event rows and search witness samples retain their clock, while candidate code-site identity stays independent of time.
- Keep `trace(count=N)` at N preceding snapshots and retain its final endpoint separately in `collector.current_stop.clock` and optional public `endpoint_clock`. The endpoint is not another event or candidate. A temporal predicate may match a final unbound runtime boundary; its source remains unknown and the source window stays open, so it cannot narrow the source search.
- Establish one absolute trace-operation budget before lock admission and retain the minimum host/script/session/VM/channel deadline through qualification, stepping and evidence persistence. Saved scripts now keep their original deadline across preflight and route-artifact work. A late synchronous write may already have committed; failure preserves the known stop and available artifact IDs rather than implying rollback or replaying execution.
- Preserve native stop evidence if an ordinary run fails later in register acquisition or journal persistence. Preserve verified DOS exit/TSR classification when return cleanup or persistence fails. The source collector retains nested known-stop evidence when stepping itself raises after a native response.

### Final verification

| Lane | Result |
| --- | --- |
| Final source stock/API/storage/script/process/trace selection | 809 passed, zero skips; 114.28 seconds |
| Source native source-clock/input/clock/audio/display selection | 38 passed, zero skips; 30.77 seconds |
| Isolated installed wheel: applicable stock/public selection | 798 passed, zero skips; 103.51 seconds |
| Isolated installed wheel: native selection | 38 passed, zero skips; 35.06 seconds |
| Retained native DOSBox predicate/hook/reopen witness | 1 passed, zero skips; 1.33 seconds |
| Core source/wheel/installed identity | All 636 package files match |
| Source distributions | Both archives match all 1,562 tracked payload files and all 23 authored changed paths; all distribution checks pass |

The lanes overlap and must not be summed as unique tests. The native selection contains 10 new source-clock witnesses, 9 physical-input witnesses, 11 clock-budget witnesses, 5 audio witnesses and 3 display witnesses. The stock lanes include 36 hostile source-clock cases. Native emulator runs were serialized, required-runtime gates were enabled, and the isolated installed import path was asserted. The installed stock lane omits 11 repository-dependent migration/package checks.

Two deadline baselines first reproduced writes after the original script deadline; three native stop-evidence baselines first reproduced loss after a completed native step, a persistence failure or a verified DOS return. Both production defects were corrected and the focused checks pass. Earlier broad runs also exposed stale test expectations for retained guest-exit evidence, an existing refusal message and a timeout that can occur after artifact publication; those assertions were corrected without increasing timeouts. Final lanes above have zero failures. Earlier unrelated parallel startup, large-MZ and retained DOSBox idle-trial observations remain unresolved.

- Tested wheel SHA-256: `323ab20264e568333faf249c2162c028a7b6407e618d69f4da944cfb27f9feeb`.
- Source archive SHA-256: `33823f328277506d1b0ce49bbe0af9081875c660df1e4316711dd9deac97753c`.
- Tool ZIP SHA-256: `fccf84f1d2f4022a742c71a4e6e0ca2bd096e83dc305583d4109c8785729fa40`.
- Reused native QEMU SHA-256: `5b8b6c5df2602a34ea284a3efa7048bfacf68b3a1b83f2b9e793cac9c10480cb`; the clock/media/input patch chain is unchanged.

Independent review found no remaining material issue in the implemented scope and checked the final handoff for consistency. These are local Linux/pipe integration results. Standard/instruction and raw-machine traces remain clockless. Temporal ordering does not prove device acceptance, guest consumption, input causation, completed frames, instruction retirement, natural instruction latency or callback order at equal timestamps; the actual GDB IRQ/timer masking policy remains recorded. All **127** default-switch entries remain unqualified and DOSBox remains the default.

The next video timing gate is an explicit precise-retrace profile with timing-generation identity and separate renderer-publication semantics. It must not infer a completed guest frame from a surface refresh or from the stock VGA status toggle. Timing auto-sync remains a later change.

## Native virtual-time input continuation — 2026-11-08

Continued from `5085371a57629d3102b1b3d51860b5af227249b8`. Published head: `341847d48f55c877b4db645c3c98a9c72beeafe8`; complete tree: `87d720deed5bd049e43bec8da06d7524b31d8503`, verified against tested local author commit `dc6f75c0f51378c4b478bd5b86b8ec10e4187cd7`. This increment contains **23 authored paths**. **Timing auto-sync remains deferred.**

### Behavior and failure evidence

- Add `input_schedule(delta_ns)` and `input_schedule_observe()` through Python, retained JSON and saved scripts. The optional input API-1 patch applies after the exact current clock and media patches to QEMU 10.0.13. Arming and observing are passive; the caller chooses one explicit bounded run or native clock budget.
- The native virtual timer dispatches the validated owned batch through the exact selected PS/2 handler callbacks and one final sync. Its receipt records token, epoch, requested start/deadline, actual terminal/dispatch time, lateness and event count. It does **not** prove FIFO acceptance, guest consumption, held-key recognition or a completed frame.
- An ordinary virtual timer participates in HLT idle warping. A pending stop or reached clock budget wins before input; equal deadlines are independent of timer insertion order. The first actual stop cancels an unfired timer, with explicit reschedule under a fresh token or cancellation required before another run. Pending releases preserve already dispatched holds when cancelled. No hidden continue, retry or synthetic release is added.
- Batch bounds are 1..256 events, one edge per mouse button, relative X/Y in -32767..32767, delay 1..60,000,000,000 ns and 4096 successful unique tokens per process. Handler identity, legacy queue state, mappings and mouse arithmetic are checked before the first callback. Reset/profile/epoch loss invalidates the owner; first successful arm blocks migration for the process lifetime.
- Independent review findings were reproduced and fixed: post-stop deadline loss, forged dispatch at an owned clock cutoff, failed scripts leaving a newly armed pre-existing queue live, invalid UTF-8 reason bounds and incorrect first-stop timestamps. Scheduled execution, reconciliation and persistence now share one host/script deadline; the current budget is bound before lease transitions.
- Clock cleanup, DOS-return logging and late-persistence failures now retain the already-known original stop and any validated input receipt in `error.result`, then close. A register-read failure retains raw stop evidence with incomplete classification. Ordinary unscheduled GDB timeout recovery is preserved.

### Final verification

| Lane | Result |
| --- | --- |
| Affected source, required stock QEMU/FreeDOS, lifecycle, trace contracts, I/O, deadlines, inventory and payload checker | 328 passed, zero skips |
| Focused final scheduled-input and clock host boundaries | 80 passed, zero skips |
| Frozen isolated installed wheel: applicable stock/native I/O and public boundaries, serial | 317 passed, zero skips |
| Frozen isolated installed wheel: native input, clock, audio and display, serial | 28 passed, zero skips |
| Core source/wheel/installed identity | All 635 package files match |
| Source-distribution and tool-source ZIP | All 1557 tracked payload files and all 23 changed authored paths match; distribution-content checks pass |

Selections overlap. The 51 new host scheduling cases are included in source and installed stock selections. The native selection contains nine input, eleven clock, five audio and three renderer cases. Authored native witnesses inspect actual make/break bytes, PS/2 packets, IRQ1 wake-up from HLT, early/equal-budget cancellation, explicit rescheduling, held releases, reset, DOS exit/TSR, renderer observations, retained JSON/scripts and reopened historical evidence.

The pinned official archive → clock → media → input patch chain reproduces all **18 unique affected source paths** exactly, with zero fuzz. Native build and installed test identities:

- Native input patch SHA-256: `11ace3ccd39b2a2e507917197980b0b9181b5de3901161b2362be6ea53cbe6bb`.
- Tested QEMU executable SHA-256: `5b8b6c5df2602a34ea284a3efa7048bfacf68b3a1b83f2b9e793cac9c10480cb`.
- Frozen tested wheel SHA-256: `5d09079d3c63f3220fdacd791787c3623606ffa05dceaf1e4677f68b972463c6`.

Evidence is local Linux with owned disposable pipe-transport VMs and the explicit test-only FreeDOS 1.4 baseline. No production timeout increase or automatic retry was introduced. Earlier parallel startup, large-MZ and DOSBox idle timeouts remain unresolved and are retained below. The previous tested media executable and its build receipt are preserved.

All 127 default-switch qualifications remain open; DOSBox stays the default. Guest-frame/VBlank semantics, legacy timed helpers, INT33/pixel mapping, broader sound devices, source-trace causality, checkpoints, histories, QEMM/game campaigns, Windows and macOS remain separate work. See the [native input contract](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/341847d48f55c877b4db645c3c98a9c72beeafe8/native/qemu-input/README.md) and maintained handoff.

## Native renderer and PC-speaker continuation — 2026-11-08

Continued from `0edf5a81496e780b1a1f89bd6bd1289dc1e47326`. Published head: `5085371a57629d3102b1b3d51860b5af227249b8`; complete tree: `0b312d68cb71ca77b15c04788d86756421ff4443`, verified against tested local author commit `5af5e3c3fe232ea18429ee2ad1b2f0ef38850ab7`. This increment contains 29 authored paths. **Timing auto-sync is deferred at the user's direction.**

### Behavior and clock correction

- Add `display_start`, `display_observe`, `display_stop` and `capture_display` through Python, retained JSON and saved scripts. An explicit virtual timer completes the admitted synchronous VGA renderer, copies pixels under QEMU's big lock, then publishes an ID/time. The latest bounded RGB copy is exported passively; `after_update` refuses stale publications without running the guest.
- Renderer completion does **not** establish guest frame completion or VBlank. An authored partial-drawing witness proves that a stopped surface refresh can change while the retained publication stays unchanged, and that the next renderer update can still contain incomplete guest drawing. `completed_guest_frame` and `guest_frame_id` remain unknown.
- Add explicit `qemu_clock='virtual', qemu_audio='pc-speaker'` and `audio_start`, `audio_observe`, `audio_stop`, `capture_audio`. Native callbacks retain bounded 32 kHz mono U8 PCM with contiguous indices and virtual delivery times. Inactive intervals do not synthesize silence; callback time is not sample onset. Stop never flushes or advances the guest. Overflow retains a known prefix, counts dropped frames and refuses complete WAV export.
- Tokens, epochs, stopped-field freezing, exact payload sizes and repeated byte hashes bind the media evidence to the owned machine. Reset invalidates both windows; migration after use is blocked. Whole-script preflight and one operation deadline remain enforced, including owner closure on an overrun after a start/stop mutation.
- A strict new regression exposed an additional idle-warp defect: ordinary GDB continue with no budget armed could advance roughly 54.9 ms on an authored one-NOP path. The guard now covers stopping/stopped CPUs after explicit native-clock admission whether or not a budget is armed. Real HLT advancement remains supported; the new short-path, PIT/IRQ and existing clock tests pass.

### Verification and unresolved startup observations

| Lane | Result |
| --- | --- |
| Affected source, stock QEMU/FreeDOS, lifecycle, I/O, deadlines, inventory and payload checker | 276 passed, zero skips |
| Final public media/routes and hostile boundaries | 138 passed, zero skips |
| Final source native media and clock | 19 passed, zero skips |
| Isolated installed wheel: stock/native I/O and public boundaries, serial | 154 passed, zero skips |
| Isolated installed wheel: native media and clock, serial | 19 passed, zero skips |
| Core wheel/source/installed identity | All 634 package files match exactly |
| Actual sdist and tool ZIP | Full 1,550-file tracked payload plus all 29 changed paths match; 2,175 and 2,157 archive members respectively |
| Tool-only archive checks | Wheel, sdist and tool ZIP pass |

Selections overlap. Native cases cover programmed speaker frequency, inactive output, overflow, simultaneous audio/display epochs and clocks, reset/token ownership, partial rendering, mode dimensions, freshness, passive exports and persistent scripts/evidence. These are local Linux/pipe results with explicit authored FreeDOS fixtures.

**Retained failures:** the first installed suites ran concurrently and finished **153 passed / 1 failed** (stock/public) and **18 passed / 1 failed** (native media/clock). Both exhausted the existing startup deadline before a media operation: QMP greeting in the first, DOS loader report during fixture setup in the second. The reset test did not reach reset. Serial runs on the same wheel and binaries with unchanged deadlines passed as shown above. Resource contention is possible but unproved; parallel startup reliability remains unresolved. No automatic retry or larger production budget was introduced. The older large-MZ and retained-DOSBox idle timeouts remain separate unexplained observations.

Independent review verified the pinned archive base hashes, new-file absences, the 14-path clock→media source chain, packaging recipes and README/native-contract consistency. Separate native-video/client boundary review prompted stricter unsolicited-window refusal, stopped-field freezing and exact snapshot length/identity checks; those corrections are included.

- Clock patch SHA-256: `2127b71b7e45cc0e1a0351a405aed3b0a016e98af8d0540f74633c37b6b4dd4b`.
- Media patch SHA-256: `ad20d1d0670dc5eae166dee1b6be58f6d0a9f8d2386646f12007f342dbcb15a6`.
- Tested native executable SHA-256: `2c60e112a1ea4e48a44f6250a0a1f4b209b78d3fa425f55105dde7662c43918e`.
- Tested wheel SHA-256: `7732b3472ef950cfeaa42c31408d0f4d98601e043ee209b48ab3c0221c3fec96`.

The [media protocol/build contract](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/5085371a57629d3102b1b3d51860b5af227249b8/native/qemu-media/README.md) and maintained handoff retain the reproduction steps and limits. No QEMU binary, DOS image, FDB, state or raw private runtime log is committed. SB16/FM, guest-frame/VBlank semantics, timed input, coordinate/trace joins, checkpoints, histories, real games/QEMM, Windows/macOS and legacy timing parity remain unqualified. All 127 default-switch entries remain open. No host pacing, auto-sync, release, merge, shared installation or hosted pipeline was requested or performed.

## Native virtual-clock continuation — 2026-11-08

Continued from takeover head `16bafd40dd89a23f5bfc31130aae1a495e272c74`. The new head is `0edf5a81496e780b1a1f89bd6bd1289dc1e47326`, with complete Git tree `ed33223aed2d887a0759c1422b12ca0a24a2662b` verified byte-for-byte against the tested local source. The local author commit `d2f00ccd238298a426d18a139cc1189018ed219b` is preserved on a recovery branch. This publication adds 23 authored paths/updates, including the pinned six-file QEMU patch, public API, witnesses, package recipes and maintained handoff.

### Behavior and fixes

- Explicit `qemu_clock='virtual'` requires the API1 extension on the qualified QEMU 10.0.13 build, one TCG CPU and fixed `shift=7,align=off,sleep=off`. Stock executables refuse this profile while still paused. The existing profiles remain available.
- Python `clock_advance`, JSON `debug-clock-advance` and script `clock-advance` use one native virtual timer and one existing GDB continue. Receipts retain start, requested deadline, firing, stopped time, elapsed time and overshoot. Earlier debugger stops, DOS exit/TSR and physical-input delivery remain visible. There is no exact arbitrary-nanosecond or cycle-accuracy claim.
- A distinct native pause signal prevents a timer stopped at a matching PC from fabricating a breakpoint or reserved DOS return. One host deadline covers lock admission through cleanup and persistence, including existing shorter script/channel bounds and DOS completion callbacks.
- Unknown arm, execution, cleanup or evidence closes the owner without replay. Cancellation proves both timer and deferred stop request are gone. Reset/unsupported states invalidate the native epoch; migration after budget use is blocked.
- Stopped surface captures now bracket both native virtual time and instruction count. They still do not establish a completed guest frame.

The first native run was **6 passed / 2 failed**, with both failures at early break/watchpoints. They preserved the correct debugger cause but advanced virtual time to the armed deadline before the native stop finalized. Exact QEMU source review identified an idle warp between the CPU's debug-stop flag and main-loop request handling. The corrected native predicate suppresses that warp while an armed budget has a stopping/stopped CPU, while preserving ordinary HLT advancement. The original early-stop assertions remain strict and now pass, including a later run past the cancelled deadline with no phantom stop.

The reset witness explicitly enables reset only inside that probe because the normal production `-no-reboot` policy exits QEMU. Production launch options were not changed to satisfy the test.

### Fresh verification

| Lane | Result |
| --- | --- |
| Affected source + stock QEMU/FreeDOS + I/O/lifecycle/deadline/inventory checks | 205 passed, zero skips, 98.96 s |
| Final public routes and hostile clock-boundary checks | 68 passed, zero skips, 6.22 s |
| Corrected native virtual-clock suite | 10 passed, zero skips, 34.91 s |
| Isolated wheel: public/deadline/surface/doctor/stock native I/O | 103 passed, zero skips, 50.44 s |
| Isolated wheel: corrected native virtual-clock suite | 10 passed, zero skips, 37.83 s |
| Package payload checker tests | 5 passed, zero skips |
| Wheel/source identity | All 632 package files match |
| Source distributions | Actual sdist and tool ZIP each contain the native README, patch and manifest with exact bytes |

These lanes overlap and must not be summed as unique tests. Native witnesses cover busy execution, CLI/HLT virtual time independent of instruction count, PIT interrupt wakeups, early execution/data stops, cancellation before execution and wrong-token rejection, reset invalidation, DOS exit/TSR, public JSON/persisted scripts and stopped virtual-clock/surface brackets. The isolated import path was asserted before execution.

Independent review found no remaining blocking issue in the reviewed host deadline/stop attribution and native warp-guard scope. Archive review independently verified each of the four modified upstream members, both new-file absences, all six patched hashes, and source-package selection.

- Final QEMU patch SHA-256: `d28b9bff0be0d996084ecb52387ac7292064ab1edde2d233fa6c1156b33e96ad`.
- Corrected QEMU executable SHA-256: `7e4692ce38bcbab38809c48fb8a8fa9a386fa3b46c76b3207b9cc2318e4747c9`.
- Tested wheel SHA-256: `e9716f31c8c62e7224196979bd2018e7bbc27999d5c87b533a36f44cd0867131`.

The [native build/protocol contract](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/0edf5a81496e780b1a1f89bd6bd1289dc1e47326/native/qemu-clock/README.md) and source manifest make the private runtime reproducible. Vendor images, QEMU binaries, runtime FDBs and raw private receipts remain outside Git. This is local Linux/pipe evidence, not hosted CI or release qualification. The migration ledger retains all 127 default-switch entries as unqualified.

## Takeover and recovered publication

On 2026-11-08, takeover readback found GitLab at `ed1746e2525e9239be174a80c873167e52929eeb`, while the previous clean checkout contained unpublished slice-4 commit `6434474b0318bf9ee6d7d3d1b2ea094a3a81629d`. Its publication receipt was only `prepared`.

The recovered implementation was reviewed and tested, then the screenshot deadline correction and maintained handoff were committed locally as `d5f51027e42d81449bd48f7e9da1cb1b97ae63c3`. Command-line push could not authenticate; the existing GitLab connector published the 29 authored paths with per-file optimistic update guards. The remote commit below preserves the previous source head as its parent.

The complete published Git tree `e36735da0416d2b202797498e497f94fedea4fbf` is checked against the tested local tree. Original game/vendor images, runtime FDBs, machine states and raw private receipts are excluded from publication.

## Fresh takeover verification

| Lane | Result |
| --- | --- |
| Source/API/clock/input/surface/deadline/checkpoint-guard/GDB/migration selection | 141 passed, zero skips |
| Required native QEMU/FreeDOS I/O witnesses | 9 passed, zero skips, 31.01 seconds |
| Isolated wheel outside the checkout: native I/O, doctor and deadline checks | 29 passed, zero skips, 38.70 seconds |
| Wheel/source identity | All 632 package files match; zero extra, missing or mismatched paths |
| Independent review of the screenshot correction | No concrete issue found; review only, no tests run by reviewer |

The new deadline regressions first demonstrated two failures against the recovered implementation: an already-expired screenshot attempted lock admission, and a 50 ms script requested a 10-second lock wait. Both pass after the fix. The source 141-check selection includes the earlier 93-check follow-up; installed tests repeat selected source cases, so counts must not be added into a unique total.

Native tests use QEMU 10.0.13, pinned firmware, FreeDOS 1.4, mtools and NASM with required-runtime gates enabled. The I/O fixtures retain their explicit `SWITCHES=/F` baseline and original startup/operation budgets. Tests observe BIOS/IRQ consumption separately from later drawing, verify saved evidence after reopening, and reap the owned VMs.

Private test wheel SHA-256: `b5574934b839deb87d2298ec6c9db5f746e1490511c65fc1a8127dbf6cdef8d9`. The isolated import path was checked before execution. This is local integration evidence, not hosted CI or release qualification.

## Remaining scope and retained observations

- Slice 4 remains in progress. Native virtual-clock read/control now has independent busy, HLT, PIT/IRQ, early-stop and cancellation witnesses. Renderer publications and PC-speaker callback windows now have explicit ownership and clock observations. Source-bound clock joins and temporal event queries are now available for the initial real-mode virtual profile. Explicit precise VGA observations qualify supported stopped model phases and timing generations. One-shot retrace waits now verify a strictly next modeled transition, and cooperative clock auto-sync now makes one bounded correction against persistent host/native anchors. Full guest-frame/VBlank semantics, additional audio devices, media playback alignment and input-to-source causality require further qualification. One-shot virtual input dispatch now has independent keyboard/mouse/HLT and stop-precedence witnesses. Generation-checked retrace input additionally qualifies modeled-phase PS/2 callback timing, with independent guest IRQ/status witnesses for the selected cases. This does not establish arbitrary consumption or guest-frame edges. Native single-chord presses now implement the retained modifier/make/hold/break ordering with actual callback-relative timing and explicit partial recovery. Bounded native US-layout text now adds per-character key lifetimes, callback-relative gaps and the same explicit recovery. Timed physical button pairs now add separate down/up syncs, actual-down-relative holds and explicit interrupted-hold recovery. Sparse probes now return ordered samples from one immutable retained renderer publication; the image identity remains distinct from a guest mode, cursor or completed frame. Conservative VGA configuration now has write-time generation identity and a frozen publication-time observation. Equality remains separate from raster coherence, guest BIOS modes and cursor mapping. Legacy guest_ms scheduling parity, coordinate/frame-bound clicks, guest keyboard layout/text consumption, frame-edge input, pixel/INT33 mouse mapping and input-to-source-trace causality remain unqualified.
- Native checkpoints/Anchor Stones, RAM/fetch layers and UDL/UIL host services, histories and dependent scene/player workflows remain later slices. Default promotion and DOSBox removal remain blocked.
- Original real-mode COM/MZ source mapping does not qualify patched launch, secondary stubs, protected/V86 task mapping or live overlay rebinding. Actual QEMM/DESQview scheduling, arbitrary driver I/O, real games, Windows timing and macOS require separate campaigns.
- Preserve the previous isolated large-MZ 15-second startup timeout and retained DOSBox idle-trial timeout as unresolved observations. Successful follow-ups did not establish their causes. The separately diagnosed instruction-profile FreeDOS boot-key wait is documented in the handoff and is not retroactively assigned to those earlier failures.
- The configured Mac Git mirrors are still inaccessible here and are not reported synchronized. A Mac-side fetch can update them without requiring this executor to mount the volumes.
- No hosted pipeline, merge, release or shared installation was performed. Source publication carries `[skip ci]`; this draft remains open.

Origin: `chat:284eb73cc1a1/task:dosbox-qemu-sunset`  
Takeover: `chat:54d0a46c7daf`  
Source: `agent/qemu-sunset-284eb73c`  
Head: `804c507d652312fb160bb027e0cdcfe38ac7ecb6`  
Target: `agent/execution-event-search-284eb73c`  
Base: `089c1841c415eb2b5cdfa90d03b6291a07f73919`

See the [maintained migration plan and handoff](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/804c507d652312fb160bb027e0cdcfe38ac7ecb6/docs/DOS_QEMU_HANDOFF.md), [migration guide](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/804c507d652312fb160bb027e0cdcfe38ac7ecb6/docs/DOS_QEMU_MIGRATION.md) and [capability inventory](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/804c507d652312fb160bb027e0cdcfe38ac7ecb6/docs/DOSBOX_QEMU_CAPABILITY_INVENTORY.md).

The [timing synchronization contract](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/804c507d652312fb160bb027e0cdcfe38ac7ecb6/docs/DOS_QEMU_TIMING.md) documents the APIs, persistent anchors, drift limits, exact retrace windows and failure semantics.

The [native retrace-input contract](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/804c507d652312fb160bb027e0cdcfe38ac7ecb6/native/qemu-input-retrace/README.md) pins the fifth patch, command, callback window and explicit cancellation rules.

The [native keyboard-press contract](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/804c507d652312fb160bb027e0cdcfe38ac7ecb6/native/qemu-keyboard-press/README.md) pins the sixth patch, relative edge timing, prefix receipts and explicit held-key recovery.
The [native keyboard-type contract](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/804c507d652312fb160bb027e0cdcfe38ac7ecb6/native/qemu-keyboard-type/README.md) pins the seventh patch, bounded text mapping, callback-relative gaps, future reservations and explicit interruption recovery.
The [native mouse-click contract](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/804c507d652312fb160bb027e0cdcfe38ac7ecb6/native/qemu-mouse-click/README.md) pins the eighth patch, separate syncs, actual-down-relative timing, prefix evidence and explicit recovery.
The [native renderer-probe contract](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/804c507d652312fb160bb027e0cdcfe38ac7ecb6/native/qemu-display-probe/README.md) pins the ninth patch, exact publication identity, passive RGB sampling and failure semantics.
The [native VGA-configuration contract](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/804c507d652312fb160bb027e0cdcfe38ac7ecb6/native/qemu-vga-configuration/README.md) pins the tenth patch, raw configuration vector, write-time generation and publication stamp semantics.
