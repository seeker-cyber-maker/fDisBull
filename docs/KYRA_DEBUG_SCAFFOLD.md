# Kyra replacement-engine debugger scaffold

## Status and purpose

**Stage 1 prototype, not a runnable ScummVM Kyra backend.** The Python boundary,
native C++ control core and opt-in EMC instrumentation are implemented. The
native JSON dispatcher, process-launch routing, frame/input integration and
real-game acceptance are still missing. `--backend scummvm-kyra` is deliberately
**not** registered. Nothing in this contribution establishes engine execution,
whole-game recovery, original-DOS parity, or a release qualification.

This is a replaceable execution scaffold for Kyrandia I and Lands of Lore I
while the in-house runtime develops. It follows MR !73's separate ScummVM process
approach without inheriting AGI-specific state, resources or save semantics.
It builds on the PAK/CPS/WSA/EMC2 readers in MR !83.

## Reviewed dependencies

- fDisBull Westwood base: `08f67edb7e3ea782f0dd2b55acf9e820e7cd86ae`, MR !83,
  branch `codex/westwood-media-emc2-20261104`.
- AGI/Gob transport reference: MR !73 at
  `72d535be6c3c8889a3362fb53f82c7e051e429c1`, branch
  `codex/scummvm-execution-backend`. This draft remains separate and unchanged.
- Native source pin: ScummVM 2.8.1,
  `750f2373fb100efe08c6444e36b68c01387fc307`, the AGI bridge's upstream baseline.
- Reviewed EMC interpreter blob: `63dbc824fa739bd9bb2f3b008fff1e4cb7142382`.
  The hook preparation tool requires the exact upstream HEAD and exact blob,
  not an assumed matching version string.

The AGI class cannot simply be renamed: it fixes 256 byte variables, 256 flags,
AGI LOGDIR/VOL addressing, cycle-boundary saves and 256 MiB manifests. Kyra has
named archive members, EMC word offsets, game-specific native callbacks and,
for Lands of Lore, a distinct TIM sequence interpreter. The full original
Lands of Lore CD alone exceeds that AGI manifest limit. The future launcher
needs explicit larger streaming budgets, not blanket removal of safeguards.

## Architecture and ownership

1. `ScriptBinding` binds one caller-selected original EMC/INF resource and an
   explicit `kyrandia1-dos` or `lol1-dos` entry profile. Duplicate archive names
   remain distinct source candidates; choose the actual member/index explicitly.
2. `KyraScaffold` speaks the experimental `kyra-emc2-debug-1` contract through
   an owned `call`/`close` peer. It verifies the peer identity and complete
   canonical DATA/ORDR load snapshots before installing source-bound controls.
3. The separately built C++ `Controller` owns resource generations, bounded
   before/after dispatch events, breakpoints, syscall traps, completion budgets,
   pause requests, host deadlines and trace-loss accounting. It does not emulate
   EMC instructions or any game engine.
4. `scummvm_hooks.h` connects EMC load/unload/init/run boundaries to that core.
   The owner callback and JSON dispatcher must still be connected to the MR !73
   socket transport. The core refuses silent execution when a pause callback
   returns without an explicit finite resume.
5. ScummVM performs replacement-engine execution. DOSBox remains the independent
   original executable runtime. An in-house provider can later implement the
   same observation boundary; it must pass its own qualification gates.

The transport owns exactly one process, one reader and one execution controller.
The new Python class does **not** spawn, attach to or persist an engine session.
No existing live AGI/Gob process is reused. No network service or automatic
runtime selection is introduced.

## Implemented scope

- Immutable original identities and separate file-byte, DATA-byte and DATA-word
  coordinates. LoK DOS uses `ORDR[n]`; LoL uses `ORDR[n] + 1` words. Korean LoK,
  PC-98, FM-Towns and other games are outside this initial native hook profile.
- Full DATA and ORDR snapshot comparison in bounded chunks. TEXT contents,
  archive search precedence, native syscalls, source authenticity and whole-file
  live-memory identity are **not** established by this comparison.
- Native instruction-word guards on every observed dispatch, including a second
  operand word when needed. A changed word or live extent refuses observation
  against the old load snapshot. Unexecuted words are not reverified each step.
- Resource IDs and generations instead of serialized host pointers. Unload or
  replacement invalidates breakpoints. A source bound to one session cannot
  silently authorize a different session or resource generation.
- Source-bound instruction breakpoints and native syscall-ID traps. The Python
  boundary does not yet expose syscall traps or data watchpoints. These IDs have
  game-specific semantics, not one universal Westwood gameplay API.
- Explicit begin/end span identities, including nested dispatches. Completing a
  nested dispatch is not completing its caller. Truncated completion history
  leaves a missing caller's completion unknown instead of falsely returning no.
- Exact bounded trace-drop counts. A full ring with zero drops is not truncated.
  A lossless retained window is not a complete run or whole-game trace.
- Finite dispatch/host budgets, cooperative backend-yield control points and
  refusal after ambiguous transport failures. No uncertain execution retry.

The C++ control core is tested independently. The hook header and complete
ScummVM build have **not** been compiled or run together in this environment.
The current kernel tests do not exercise actual game calls, media waits, native
ScummVM pause behavior or transport installation.

## Intentionally absent

No TIM stepping, LoL combat/party watches, LoK room/inventory watches, native
memory/register claims, resource patches, typed-state writes, input replay,
framebuffer capture, FDB debug-run persistence, exact checkpoints or save/load
are implemented in this first stage. Do not infer them from the AGI backend.

In particular, EMCState initialization does not initialize every register and
stack slot. Blindly dumping the entire structure could expose indeterminate
host data and invent guest values. Typed-state work must track initialized/live
fields and qualify externally supplied callback arguments before exposing them.
Do not add zero-initialization to the engine merely to simplify debugging; that
would change the behavior being observed.

A native game save is also not an exact EMC/TIM/host-stack/audio checkpoint.
Until those distinctions are implemented and qualified, save/checkpoint APIs
must refuse rather than claim rewind parity with DOSBox Anchor Stones.

## Python boundary usage

This is an API usage example, not a runnable stock-ScummVM launch command:

```python
from fdisbull.kyra_scaffold import KyraScaffold, ScriptBinding

# owned_peer must implement the Kyra protocol. MR !73 currently only launches
# AGI/Gob and does not yet supply this Kyra peer.
script = ScriptBinding.from_bytes(
    "ROOM.EMC", original_resource_bytes, profile="kyrandia1-dos")
session = KyraScaffold(owned_peer, profile=script.profile)
resources = session.resources()
# Select the actual observed loaded-resource ID, not the first matching name.
bound = session.bind(script, selected_resource_id)
point = session.breakpoint(bound, script.entries[selected_function])
result = session.run(max_instructions=1000, timeout_ms=5000)
# result distinguishes stopped reason, nested completion and budget exhaustion.
session.close()
```

`ScriptBinding.instruction()` is static decoding at an aligned word. It does not
prove that the word is reachable or an instruction boundary. Runtime breakpoint
hits and instruction-word guards provide separately scoped execution evidence.

## Native hook preparation

Use a caller-owned, isolated ScummVM checkout at the pin above. This utility
has no download, compile, launcher or implicit package-install behavior:

```sh
python experimental/scummvm/kyra-scaffold/apply_hooks.py /private/scummvm
# Review the dry-run diff and this document before requesting source changes.
python experimental/scummvm/kyra-scaffold/apply_hooks.py /private/scummvm --apply
```

It adds the headers under `backends/platform/null/` and instruments the one pinned
EMC source file. Hooks are compile-time opt-in with `FDISBULL_KYRA_HOOKS`.
ScummVM's no-exceptions integration must also define
`FDISBULL_KYRA_NO_EXCEPTIONS`, and these headers require C++17. Merely applying
these hooks is not a complete build recipe. A bridge owner must install the
controller before `FDISBULL_SCUMMVM_FD` is used. Otherwise launch refuses. A
non-agent build has no enabled instrumentation and no behavioral replacement.

The native sidecar uses the ScummVM GPL boundary. Preserve upstream source and
license requirements when distributing a patched binary. The first-party
licensing/provenance review already tracked by MR !83 remains pending; this
contribution is not legal clearance or an engine-binary redistribution.

## Protocol handoff for the next implementation

Reuse `scummvm_rpc.py` from !73 for socket framing, deadlines, strict response
IDs and process cleanup, but add an explicit Kyra routing/handshake path. Do not
subclass `ScummVMAGISession` and accidentally inherit its AGI state semantics.

The native JSON dispatcher must implement these operations, matching the Python
validation and C++ core's actual behavior:

| Operation | Boundary |
| --- | --- |
| `hello` | Protocol, exact provider SHA-256, provider kind, Kyra game/profile, explicit capabilities, `original_x86_executed:false`. |
| `state.get` | Confirmed pause, monotonic revision, phase and optional six-field VM position. No original CPU registers. |
| `resources.list` | Up to 256 resource IDs/generations with word counts, advisory names and canonical encoding. |
| `resource.read` | Explicit DATA/ORDR byte slice, max 4096 bytes, echoed identity/range/revision, canonical BE16 load-snapshot bytes. |
| `run` / `step` | Positive completion and host budgets; structured stop, exact completed count and bounded completed-span tail. |
| `break.add` / `break.remove` | Owned IDs, current generation, DATA word offset and exact expected instruction bytes. |
| `trace.get` | Up to 2048 paired-kind events and explicit drop count. A retained prefix may begin/end mid-call. |

The six VM fields are `resource_id`, `generation`, `word_offset`, `context_id`,
`span_id`, `parent_span_id`. Map C++ field names explicitly. Never serialize
pointer keys. A `backend_yield` can be inside an unfinished native callback, not
at a completed opcode. Its pause does not authorize arbitrary state mutation.

Native std::function callback waits, backend event polling, display updates and
media delays must cooperate with the owner. Long native computations that never
yield still require the transport's hard timeout and process teardown. A pause
acknowledgment alone is not proof the engine stopped.

## Next acceptance gates

1. Build the exact pinned ScummVM source with the JSON owner and hook wiring;
   record source/patch/binary hashes and install failure cleanup. No mock peer
   or standalone kernel pass substitutes for this native build.
2. Boot **original, unmodified** English Kyrandia DOS v1.0 and LoL CD 1.02d data
   independently. Keep extracted data, saves, runtime files and FDBs outside Git.
   Do not use the experimental no-voice CD rip as a gameplay oracle.
3. Reach title/new-game using shared queued input and committed-frame capture;
   qualify one loaded EMC breakpoint, one single/nested step, a host-budget stop,
   resource identity, EOF cleanup and no leftover process for each game.
4. Add typed EMC state, guarded mutations and game-level watches, preserving
   unknown/uninitialized values. Introduce TIM as a distinct context and trace
   boundary instead of counting its work as EMC instructions.
5. Bind small UDL/UIL contracts to original DOS observations and compare the
   scaffold provider on the same declared inputs. Keep `original -> UIL` and
   `UIL -> selected runtime` as distinct checks. Replacement-engine agreement
   alone does not qualify the in-house implementation.

## Local verification

Run the authored suites from a source checkout with a C++17 compiler and pytest:

```sh
python -m pytest -q tests/test_kyra_scaffold.py tests/test_kyra_debug_core.py
```

The C++ suite uses `-Wall -Wextra -Werror -fsanitize=undefined` and has an explicit
compiler-missing skip. It compiles **only** the independent control kernel, not
the ScummVM hook header, a JSON owner or a game runtime. Tests use invented
program words and clearly named protocol doubles, without game assets.

## Primary references

- [AGI/Gob backend MR !73](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/73)
- [Westwood reader/EMC2 MR !83](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/83)
- [Pinned EMC interpreter](https://github.com/scummvm/scummvm/blob/750f2373fb100efe08c6444e36b68c01387fc307/engines/kyra/script/script.cpp)
- [Pinned EMC data/state definitions](https://github.com/scummvm/scummvm/blob/750f2373fb100efe08c6444e36b68c01387fc307/engines/kyra/script/script.h)
- [Pinned Kyra base and game flags](https://github.com/scummvm/scummvm/blob/750f2373fb100efe08c6444e36b68c01387fc307/engines/kyra/kyra_v1.h)
