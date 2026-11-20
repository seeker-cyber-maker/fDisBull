# DotBox contracts useful to QEMU

Review date: 20 November 2026. The user assigned future DOSBox maintenance to
DotBox after the split. QEMU parity work therefore develops and verifies QEMU
contracts independently while preserving the existing DOSBox compatibility path.

## Source checkpoint

The connected repository readbacks identified the following immutable source:

| Repository | Branch | Commit |
| --- | --- | --- |
| [seeker-cyber-maker/DotBox][primary] | `codex/keen-platformer-20261119` | `ea3471d46bf14bc9b658f00cbf2215e498255e16` |
| [TiGa-RCE/DotBox][mirror] | `codex/keen-platformer-20261119` | `1407f1250b6e41b1e64fb921e1e9496eed073185` |

Both commits have tree `0405932f6967a7a8d639f9a56e54fda2357eecb0`. This is a
branch checkpoint, not a claim that the changes are merged into `main`.
The review read 15 immutable source/receipt files and eight BBS reports,
verified their identities, and did not rerun DotBox's reported tests or guests.

## Transfer order

| Priority | Useful DotBox contract | QEMU application | Evidence boundary |
| --- | --- | --- | --- |
| 1 | Checkpoint identity, fresh observation authority, retained failures and a later ordinary action after restore. | Admit the existing four full-process checkpoint script verbs through whole-route validation, one inherited deadline and the existing verified owner replacement. Require a post-restore instruction/effect canary. | Dune's research restore protocol and its disk semantics are not QEMU checkpoint formats. [Batch recipe][batch] and [recovery contract][recovery]. |
| 2 | Immutable named control plans and a consumable intention checked against fresh readiness. | Define a small named keyboard action profile with native ownership/epoch fencing and separate accepted, completed and observed-effect receipts. | The RTS controller's offline contracts do not qualify a live provider. The current DOSBox backend can report input accepted/queued while `transition_verified` remains false. [Harness][harness], [controller][actions], [backend][backend]. |
| 3 | Completed-frame authority and phase-qualified observations. | Qualify native frame stepping/capture before using a game-phase hook or predictive navigation policy. Preserve stop precedence, actual guest advancement and unknown feedback. | Keen's narrower, younger feedback does not imply earlier input consumption or general navigation. [Loop][keen-loop] and [timing receipt][keen-receipt]. |

The first slice is the explicit `qemu-dos` full native process checkpoint script
profile: `save-state`, `load-state`, `save-anchor-stone` and `load-anchor-stone`.
These public methods already exist; admitting their script verbs does not add
four methods to the public-route denominator. Raw-machine, entry-only,
owned-machine and LE checkpoint profiles remain separate.

## Lessons that change acceptance criteria

### Restore must survive an ordinary later operation

The retained [Dune VGA audit][vga-report] reports that immediate CPU/RAM agreement
and an initial image missed stale VGA page mappings. A later visible operation
exposed the defect. Its exact graphics-primed DOSBox workaround was qualified;
a durable repair and arbitrary cross-mode restore were not. QEMU should reuse
the post-restore action/effect invariant, not the emulator-specific workaround.
For the first COM script gate, a real increment after restoration checks that
execution continues on the verified replacement owner.

DotBox's research memory rewind preserves current mounted host files. QEMU must
continue reporting its own machine/disk/workspace restoration semantics rather
than implying that both backends restore the same state. DotBox's current
recovery guide still states that it has no qualified player-facing rewind.

### A request is not execution authority

`RtsController` consumes its intention token before a fresh observation and
admission. An immutable binding/control change refuses execution; uncertain
provider failure latches uncertainty and causes no automatic replay. The
provider must enforce the atomic final ownership/readiness fence. A serialized
request or reusable script is not itself a valid live token.

QEMU's passive scene schema must not gain action authority merely by exposing
an alias. Readiness, input acceptance and observed effects need distinct
evidence, including explicit unknown values after interrupted delivery.

### Feedback age, input timing and presentation are separate

The [Keen receipt][keen-receipt] reports 15 isolated guests, seven endpoint cases
within a predeclared two-pixel tolerance, and 98 model-update matches. Its scope
is one layout and a short flat corridor. Paired traces reached the input-read
return at identical absolute guest ticks even when a phase-qualified sample
exposed a change about one update earlier. Reported missed deadlines remain
part of the evidence.

The new optional display scale is presentation only. Four visible trials
reported 2x, maximized-2x, 3x and 4x content with the native image remaining
320x200 and corresponding controller traces equal. This does not qualify
arbitrary pointer fitting or improve guest input latency. [Scaling report][scale].

The callback-only [bounded wait helper][wait] retains raw slices and one
remaining allowance without automatic input or retry. Its DOSBox-specific
no-overshoot assertions must not erase QEMU's measured clock overshoot.

## Migration accounting

DotBox evidence establishes its own reported scope. It does not qualify QEMU,
change the 143-row retirement ledger, promote any of the seven open campaigns,
or authorize removing the existing fallback. QEMU host-peer checks and native
receipts must identify their exact producer, source and input boundaries.

[primary]: https://github.com/seeker-cyber-maker/DotBox/commit/ea3471d46bf14bc9b658f00cbf2215e498255e16
[mirror]: https://github.com/TiGa-RCE/DotBox/commit/1407f1250b6e41b1e64fb921e1e9496eed073185
[batch]: https://github.com/seeker-cyber-maker/DotBox/blob/ea3471d46bf14bc9b658f00cbf2215e498255e16/scripts/experiments/dune_probe_batch.py
[recovery]: https://github.com/seeker-cyber-maker/DotBox/blob/ea3471d46bf14bc9b658f00cbf2215e498255e16/docs/RECOVERY_AND_SAVES.md
[harness]: https://github.com/seeker-cyber-maker/DotBox/blob/ea3471d46bf14bc9b658f00cbf2215e498255e16/src/dotbox/harness.py
[actions]: https://github.com/seeker-cyber-maker/DotBox/blob/ea3471d46bf14bc9b658f00cbf2215e498255e16/src/dotbox/rts_actions.py
[backend]: https://github.com/seeker-cyber-maker/DotBox/blob/ea3471d46bf14bc9b658f00cbf2215e498255e16/src/dotbox/backend.py
[keen-loop]: https://github.com/seeker-cyber-maker/DotBox/blob/ea3471d46bf14bc9b658f00cbf2215e498255e16/scripts/experiments/keen_loop.py
[keen-receipt]: https://github.com/seeker-cyber-maker/DotBox/blob/ea3471d46bf14bc9b658f00cbf2215e498255e16/docs/evidence/keen-input-timing-2026-11-20.json
[vga-report]: https://agent-bbs-native.tiga-rce.chatgpt.site/api/download_report?report_id=report-225c7cc9-a3df-4159-a8f3-3f4e83624280
[scale]: https://agent-bbs-native.tiga-rce.chatgpt.site/api/download_report?report_id=report-14d9478f-395d-44ec-87c7-9e273e482de1
[wait]: https://github.com/seeker-cyber-maker/DotBox/blob/ea3471d46bf14bc9b658f00cbf2215e498255e16/src/dotbox/bounded_wait.py
