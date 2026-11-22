# Native AGI runtime provenance and execution contract

`overlay/target/agi/runtime.c` and `runtime.h` implement context-owned native
semantics. They use `decode.c` for every instruction and condition extent;
there is no second host opcode parser. `runtime_actor.*` and `runtime_scene.*`
have their own detailed Sarien provenance and retained GPL version 2 notices.
The sound sequencer has [separate behavioral-source provenance](RUNTIME_SOUND_PROVENANCE.md).
The complete [runtime interface contract](RUNTIME.md) records the supported
device, clock, snapshot and compatibility policies.

The command, predicate, parser and engine-cycle behavior was checked against
[Sarien commit aaef5e667757385b5b3650cc1f7365908720f7e6](https://github.com/cmatsuoka/sarien/tree/aaef5e667757385b5b3650cc1f7365908720f7e6),
particularly `src/op_cmd.c`, `src/op_test.c`, `src/cycle.c`, `src/words.c` and
`src/text.c`. The new implementation replaces engine globals, recursive LOGIC
execution, implicit main-loop work and device calls with explicit bounded state
and resumable requests. Format and operand facts also use the immutable
ScummVM references recorded in `OPCODE_COVERAGE.md`; no ScummVM implementation
code is included in the GPL version 2 native engine.

## Explicit profile

The profile is `agi-2917-runtime-1`, the repository's nominal fixed catalog of
actions 0–173, predicates 0–18, IF and GOTO. It does not select AGI 1, AGI 3,
platform-specific remaps, AGI256 or mouse extensions. Runtime `trace.on` selects
the nominal zero-operand layout. Existing raw pilot profiles retain their
context-dependent refusal rather than silently changing interpretation.

Byte variables wrap for arithmetic and saturate for increment/decrement.
Invalid resource references, malformed input, division by zero and bounded
capacity exhaustion are explicit stopped faults, not undefined host behavior.
The xorshift32 RNG is deterministic and snapshot-owned; it is not represented
as bit-identical to Sierra's original platform RNG.

## CPU state and external services

The native state owns LOGIC/PC, 64 call frames, per-LOGIC scan starts, variables,
flags, 256 actors, strings, parsed words, inventory, controllers, resource load
membership and retention order, picture planes, text cells and saved windows,
menus, per-channel sound sequencing and script replay pairs. Resource bytes
are immutable and independently hash-bound.
Actor preparation, LOGIC execution and actor completion form explicit phases;
no wall clock is substituted for guest time.

Interactive/device instructions stop with an identified request containing
the exact instruction source, continuation, operand bytes, reply type and
formatted prompt. A wrong, stale or invalid response changes nothing. An
accepted completion retires exactly once. Input, menu selection, restart,
quit, save/restore and platform devices require their declared service, not a
generic success fallback. Native instruction support and an available device
implementation are distinct capabilities.

Snapshots contain no pointers and bind the exact resource-package hash. The
current snapshot wire contract is explicitly **same native ABI**, with magic,
size, version and endian fields; it is not Sierra's original save-file format
or a portable cross-version format. A snapshot taken at `save.game` records the
post-save continuation. Restore validates it before committing and starts a
new observation epoch. Request identities do not rewind on restore/restart.

## Evidence

The authored interaction suite compiles the production C modules and supplies
resources through a small bridge with no executor or decoder. It checks nested
calls and scan starts, room unwinding, arithmetic aliases, parser short-circuit
side effects, inventory, native picture/actor output, pending/resume ordering,
menus/input, sound/ticks, save/restore and full-state equality across all four
observation masks, including journal overflow.

These tests are necessary local evidence. They do not establish complete-game
compatibility, original-DOS parity, hosted CI success or release readiness.
The QEMU control surface and resource-package adapters are qualified separately
against the actual rebuilt binary. Private PQ1/KQ1 resources stay outside Git;
SQ1/LSL1 remain held out.
