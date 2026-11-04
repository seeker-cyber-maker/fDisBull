# Kyra / EMC2 ScummVM debugger scaffold (experimental, not native-qualified)

**Status (2026-11-04):** Python-side fDisBull controller, capability/identity gate,
wire-contract specification and **synthetic** regression tests implemented. There
is **no built/qualified Kyra native sidecar** and no original-game execution
result in this change. This work is deliberately stacked on the existing
experimental AGI/Gob ScummVM work (!73); Westwood static media and EMC2 decoding
are a *separate* draft (!83). Do not merge a dependency-specific experiment into
a release until both dependencies and its native patch have been reviewed.

## Rationale

A ScummVM replacement engine is an excellent observation scaffold, but it
cannot prove that original DOS engine code executes or that its behavior is
identical. It is a different runtime from DOSBox, not a substitute CPU debugger.
Kyra is an engine family, not one common behavioral ABI:

* `kyra:kyra1`: Kyrandia I; script containers `.EMC`, scene/room state;
* `kyra:lol`: Lands of Lore I; `.INF`, dungeon level/block/direction;
* Eye of the Beholder and other Westwood releases are **not** silently included.

The common hook boundary is `EMCInterpreter::run()` in ScummVM's
`engines/kyra/script/script.cpp`. It dispatches the 19 shared core opcode IDs.
Each game supplies a separate syscall binding table. In ScummVM's 2026.4.0
sources, `KyraEngine_LoK::setupOpcodeTable()` and
`LoLEngine::setupOpcodeTable()` use different tables. Even opcode address
conventions differ: standard Kyrandia DOS uses ORDR's selected DATA word,
while Lands of Lore commonly begins at ORDR+1. Retain all original DATA words.

## fDisBull launch API (future *instrumented* sidecar only)

```sh
fdisbull debug /private/kyrandia.fdb \
  --backend scummvm-kyra --game-id kyra:kyra1 \
  --executable /private/verified-patched-scummvm --game-dir /private/kyrandia
```

The original `MAIN.EXE` or other project owner must exist directly in that
game directory and hash-match the `.fdb`; all resource members are separately
SHA-256 bound by a complete input manifest. ScummVM must recognize the actual
runtime data layout. An unextracted `GAME.DAT` ISO alone is **not** assumed to
be a launchable ScummVM resource folder. Keep data, SQLite databases, frames,
saves, and compiled third-party engines out of Git.

The selected bridge must be a separately built ScummVM **Kyra** null-backend
executable advertising `fdisbull-scummvm-agent`, version 1,
`kyra-emc2-v1`, an explicitly recognized game variant, and the required
capability set. Stock ScummVM, the existing AGI/Gob sidecars, ambiguous variants,
and unrecognized source revisions are refused before any game operation.

The existing AGI/Gob transport still controls child process ownership, private
config and saves, inherited socket, message budgets, timeout/EOF failure, and
one-shot request refusal. The new subclass adds:

| Surface | Contract | Boundary |
| --- | --- | --- |
| `debug-engine-state` | Typed EMC2 script/generation/DATA word, VM regs, game-specific view | Bridge report is not independently proven original bytes |
| `debug-run`, `debug-step` | Bounded complete-dispatch counts, structured pauses/stops | No original DOS instruction/guest-clock equivalence |
| `debug-breakpoint` | Script name, loaded generation, DATA-byte offset, loaded-data digest | Refuses stale generation, unaligned coordinates, arbitrary CPU breakpoints |
| `debug-watchpoint` | Optional explicitly instrumented register/game-flag accessors | Refuses if capability absent; direct writes not covered |
| `debug-trace` | Capped opcode records, stored external evidence | No full call/return or original CPU trace claim |
| `debug-screenshot`, `debug-frame-probe` | Last committed ScummVM RGB24 frame and revision | No independent original rendering proof |
| `debug-keyboard-*`, `debug-click` | Queued input with identity-checked frame and coordinates | Queued/delivered does not establish consumed input |

**Not available in this phase:** diagnostic memory/state writes, loaded script
patching, exact native checkpoints, savestate rewind, original DOS register
reads, native hooks, exact timers, process controls that would bypass runtime
identity, unknown Westwood-family games, `scummvm-kyra` async run/pause, or
verified scene actions. Those methods must refuse rather than fall back.

## Native ScummVM engineering still required

Pin to upstream `scummvm/scummvm` **2026.4.0**, source
`7d2709da5136866589f7602f5f5a7b17de03420e`, the already pinned Gob
source in !73. Work on a separate clean checkout; do not copy ScummVM source
into fDisBull's normal wheel or repo. The new sidecar is a GPL-derived modified
ScummVM binary: retain upstream license, corresponding source, modifications
and required notices if distributed.

1. Reuse/port the AGI/Gob null-backend inherited-fd transport, display commit,
   virtual clock, input scheduling and shutdown ownership to a new Kyra-only
   build. Reject unknown games or ambiguous detection before advertising a
   successful `hello`.
2. Instrument `EMCInterpreter::load`, `start`, `run`, and `unload`. Increment a
   script generation on every reload. Expose the precise loaded DATA **word**
   position with a loaded-data digest, named resource, VM phase and bounded
   stack/register snapshots. **Do not** treat pointer values as stable IDs or
   re-use a stale pointer after reload.
3. Put stop-before-opcode, step-completion and breakpoint tests at a safe VM
   boundary. Nested EMC execution and callbacks must not mistake an inner
   stop for completion of the outer action. Bounded runs must include host
   deadline, guest-time ceiling when qualified, and finite opcode budget.
4. Instrument game-specific **read-only** state: Kyrandia current room, event
   flags and selected object IDs; Lands of Lore current level/block/facing and
   selected party fields. Trace syscall ID separately from the common core
   opcode. Do not reuse Kyrandia syscall meanings for LoL.
5. Audit non-EMC execution phases such as TIM cinematics, synchronous UI
   dialogs and input-pump waits. A debugger stopped at `backend_yield` is not
   automatically at a safe opcode boundary. Bound modal handling and inspect
   input-consumption evidence independently from queue receipt.
6. Only after a native sidecar builds from that **exact source commit**, run
   Kyrandia floppy v1.0 and CD data, and Lands of Lore CD edition using
   isolated data folders. Compare at least one pause, scripted breakpoint,
   input, frame, scene transition, reload-generation invalidation, and explicit
   negative controls. Repeat against the original DOS executable in DOSBox.

## Verification and stop conditions

Eight synthetic Python tests run on an authored raw-x86 `.fdb` fixture and fake
RPC boundary. They check hello refusals, typed profiles and offset semantics,
symlink/drift guards, project/evidence persistence, control duplication,
source-generation refusal, bounded stepping, PNG integrity, input receipts,
trace persistence, and unqualified mutation refusals. These are **not** a
ScummVM native acceptance test.

Until native hooks and sidecar are implemented, launch of stock ScummVM fails
at the transport/protocol gate. That is a feature, not a regression.

Sources: [existing AGI/Gob MR !73](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/73),
[Westwood readers/EMC2 MR !83](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/83),
[ScummVM Kyra script interpreter](https://github.com/scummvm/scummvm/blob/v2026.4.0/engines/kyra/script/script.cpp),
[Kyrandia callbacks](https://github.com/scummvm/scummvm/blob/v2026.4.0/engines/kyra/script/script_lok.cpp),
[Lands of Lore callbacks](https://github.com/scummvm/scummvm/blob/v2026.4.0/engines/kyra/script/script_lol.cpp).
