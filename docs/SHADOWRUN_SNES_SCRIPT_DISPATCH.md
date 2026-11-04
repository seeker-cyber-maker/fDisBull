# SNES Shadowrun: direction, task dispatch and title investigation

The subsequent [title-to-morgue initialization study](SHADOWRUN_SNES_OPENING.md)
extends this historical prepared-state result.

Date: 2026-11-03. Follow-up to the [live actor handoff](SHADOWRUN_SNES_LIVE_HANDOFF.md),
starting from `08525acefde3d72f695261fcb37c3d846eba5888`. GitLab draft !75 is
the continuing review. Prior inputs, apps, captures and immutable local refs
are preserved.

The new `scripted-intro` profile composes the source task scheduler, a bounded
script interpreter, NPC direction/action setters, movement and animation
completion. Its selected actor/task fields match across **60 consecutive original
main-loop checkpoints** from a prepared intro state. This extends past both prior direction-change
refusals. It is an actor/task projection, not a complete live scene: original
graphics, the scene collision rebuild, other actors' motion, APU playback,
room transitions and player input are outside this profile.

The title-menu controller is also available as a separate UIL component. The
NEW GAME transition was traced into presentation and APU transfer work. The
continuous title-to-player-ready-morgue route remains unimplemented; the build
does not substitute a jump to a later prepared state for that missing route.

## Running the bounded native study

```text
fdisbull shadowrun-snes-build --profile scripted-intro \
  --rom /private/source.sfc \
  --ram /private/checkpoint-002000-00.bin \
  --save-ram /private/save_ram.bin --output /private/new-scripted-study
```

The required seed is **before opcode `80:962E`**, checkpoint serial 920 in the
qualified run, SHA-256
`e4cf82bc4d2d58d28cda9ae9d90d51cf4287e9e8bf0d3c860097a1a5ce2f0ca9`.
The post-video-frame-2000 snapshot used by `npc-intro` is a different input.
The factory checks the exact ROM, seed and save identities. It seeds once;
later original checkpoints are comparison evidence only.

Space starts/pauses; R resets; Esc closes. Cyan and orange markers represent
actor slots `44` and `46`. Host ticks advance logical main-loop passes, not
original video frames. The app requests 60 Hz for the study view; that does
not establish original display timing or gameplay performance. It stops after
60 successful updates. That cap is an analysis policy, not a recovered game
timer. Unsupported input, callbacks, actor families, task states or physics
also stop transactionally. The complete native state is preserved on refusal;
direct `GameMachine.call` users must snapshot and restore the containing
transaction themselves.

The existing `static-morgue`, `live-morgue` and `npc-intro` profiles remain
available. `npc-intro` retains its 30-update reference boundary. The new
profile is separate because its seed phase, clock and actor/task contract
differ from the existing collision/movement profile.

## Recovered producer chain

| Source edge | Implementation and boundary |
| --- | --- |
| `80:AA3C` direction setter | Direction-table adjustment, animation phase/pending state and supported action-reset branch |
| `80:A912` action setter | Source-bound supported actor/action records, including idle and observed one-shot completion |
| `80:C7DC–C8E2` controller | Coordinate target, axis/direction selection, countdown, velocity, arrival and task signal |
| `80:C9B0` selector | Selects actor control branches; **it is not the script interpreter** |
| `80:C399` wait/readiness | Countdown and matched wait flags, including the actual return value used by script continuation |
| `80:C1C9` scheduler | Seed-derived active linked task list; bounded validation, readiness, callback yields and supported termination |
| `80:F342` interpreter | Real ROM bytecode, task-local frame/PC/stack, a bounded opcode whitelist and explicit callback/resume protocol |
| Native callbacks | Source entity flags, target/stop setters, supported action/direction, reads and semantic audio events; unsupported calls refuse |

All 26 active tasks in the qualified seed are visited in source list order.
Task and actor identities are separate byte offsets. The principal motion
projection is slots `44`, `46` and `4E`; slot `42` additionally receives its
observed action-zero setup and subsequent animation projection. The earlier
unset-action animation of `42` is excluded. Other actor effects and complete
source sorting/presentation are not projected.

The task chain matters: task `10` sets an entity flag consumed and cleared by
actor `4E`'s task `08`. Its one-shot animation produces a completion signal;
task `08` then resumes into an audio command. Clearing the flag automatically,
acknowledging a callback without its actor effect, or freezing other ready
tasks would omit source behavior. The integrated comparison executes the
active scheduler and derives these effects instead.

Audio callbacks produce typed semantic events and the modeled source counters.
They do not synthesize sound or implement APU port handshakes, delivery timing
or all sample-loading paths. Long native-only diagnostic continuations were
used to find missing operations; they do not extend the 60-update original
qualification or the public build's analysis budget.

## Comparison method and results

The ROM is SHA-256
`e6bc0a595d5c7c4bc0bbb61ffe35a70288a77eb78544ed74682d489a9e6f07f4`.
The reference uses pinned official SNES9x commit
`fae2fea08f74180759ef540ee94259213f503480`, ordinary controller input and no
memory patches. `snes9x_checkpoint_adapter.py` adds bounded WRAM/register
observations at instruction entry. The observer's final system RAM, serialized
state, RGB frame, PNG frame and save RAM all match the unmodified baseline
for the paired 2,063-video-frame run. The selected checkpoint series has
63 captures and zero dropped observations.

The original sometimes spans more than one video frame between main-loop
updates. A comparison driven once per `retro_run` first diverged around video
frame 2043. Paired runs with and without the late START pulse had the same
full WRAM at the observed frames 2042–2062; that pulse did not change those
observations on this paired route. The qualified model instead
advances once per consecutive `80:962E` checkpoint serial. No observed skip
schedule, later poses, script PCs or task flags are fed back into the model.

| Check | Result and scope |
| --- | --- |
| Composed source comparison | 60 consecutive logical updates; 17,920 selected original actor/task fields; no mismatch |
| Compiler edge | 4,300,506 complete native/UIL state elements match, including seed and refusal readbacks |
| Refusal | Update 61 and its repeat preserve complete native state |
| Active scheduler component | 104/104 selected task fields match the first coherent source pass; separately source-seeded |
| Existing NPC reference | 30 original updates, then direction refusal at 2031 with repeated native rollback |
| Public CLI / app | Program, seed, generated C and native core match the independent integrated check; offscreen run accepts 60 updates and stops on 61 |
| Title controller component | Three source-fed, instruction-boundary selection cases match original and native/UIL; input production and display excluded |

Selected source comparisons cover actor pose, target, controller, velocities,
direction/action, task binding and animation metadata, plus relevant physics
flag bits; task PC/SP, wait/link/flags/delay/frame/callback, active list order
and the dependent entity flag are checked. This is not whole-WRAM equality.
Complete native/UIL equality establishes the compiler edge, not completeness
of the source projection. Sanitized receipts are in
[`docs/evidence/shadowrun-snes-dispatch-2026-11-03/`](evidence/shadowrun-snes-dispatch-2026-11-03/).
Full-suite and exact-source package results are retained in the local PR record.

Reproducers under `scripts/`: `check_shadowrun_snes_scripted.py`,
`check_shadowrun_snes_task_first_pass.py`, `check_shadowrun_snes_menu.py` and
`check_console_udc.py` with `--snes-checkpoint-pc` / `--snes-checkpoint-frames`.
The task-only `check_shadowrun_snes_task_vm.py` supplies arrival signals and
acknowledges actor callbacks as component inputs; it is not a scene replay.

## Title menu and attempted intro

The actual selection is the direct-page word `$0E`, initialized at `81:E195`;
the title caller supplies three choices. `$1CD2`, initially correlated with
the cursor, was an NMI stack copy of Y. `81:E274–E30C` reads the already computed
button-edge word `$01EA`: START/B (`9000`) confirms first, UP (`0800`) moves up,
then DOWN/SELECT (`2400`) moves down. Selection wraps across the three choices.
The source tests UP then DOWN when confirmation is absent; combined nonzero
direction masks were only established statically because the tested core
suppressed the requested opposite directions. Nonzero disabled-entry cases
are source-derived and bounded by policy, not original-run qualified.

`shadowrun_snes_menu.menu_machine` exposes that component: set `menu_pressed`
to the source edge word, then call `shadowrun_snes_menu_control`. It does not
claim to produce the edge word from a raw controller, reproduce cursor drawing
or execute a selected menu continuation. The observed DOWN is consumed during
video frame 850; its displayed cursor changes in the following frame.

NEW GAME was observed at frame 840, returning selection zero through
`81:E1A2 → E22A → E315`. Transition/presentation work continues through frame
872; the caller returns at frame 888 into `81:EF24/F053`. Those routines reach
APU-port transfers at `$2140–$2142`; they are not established task creation.
Eight separately source-seeded, single-pass diagnostics in the early intro
matched selected task fields (seven checks of 108 fields and one of 104).
They are sparse diagnostics, with no frozen model/checker hashes at execution,
and do not form a continuous trajectory or qualify initialization.

The next probe is the task-list and scene-creation writers immediately before
the first original `80:962E` pass. Coarse five-frame samples found no checkpoint
at 900–1045; frame 1050 contained serial 2. The exact first pass, source creation
writer and producer-to-scheduler state edge remain open. Recover those before
widening the modeled intro, followed by actor/camera/presentation/audio
dependencies and the transition to player-ready morgue state.

## Friction captured in the skill

The bundled investigation skill now directs agents to distinguish source
input consumption from displayed response, video frames from simulation passes,
and durable variables from register copies on the stack. The handoff also
records the mistaken `C9B0` interpreter label, the need to execute other ready
tasks that produce dependent entity flags, actual callback effects rather than
acknowledgements, and source-fed components versus replay seeded once.
Each comparison names its clock, boundary, source dependencies and exclusions.

Original ROMs, RAM, save files, states, screenshots and generated private apps
remain outside Git and tool packages. No hosted CI, release, merge, global
installation, complete intro or whole-game equivalence is claimed.
