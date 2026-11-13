# Bounded update behavior fixture

This homegrown MIT fixture supplies a small, known-source comparison target.
The intended native artifact is an x86-64 Windows PE DLL exporting
`bounded_update` and `bounded_core`, with no program entry point and no imports. The builder must
verify those artifact properties; the C source alone does not establish them.
Both functions are marked `noinline` to preserve useful analysis boundaries.

## Caller contract

`bounded_update(uint64_t x, uint64_t limit, uint64_t *out)` has one permitted
caller-visible output effect:

- When `x > limit`, it leaves the caller's output storage unchanged.
- Otherwise, it writes `(x ^ 0x5a) + 7`, reduced modulo `2^64`, to `*out`.

For the projected comparison, the caller supplies valid writable `uint64_t`
storage disjoint from the DLL image and active call stack. Allowing the output
to alias BLA's shadow heap would invalidate the projected wrapper comparison,
including on rejected inputs. The fixture contains no key, secret, flag, allocation, or input/output
API. Unsigned arithmetic defines the wraparound case.

Defining `BLA_PROTECTED` includes the campaign-provided `bla_shield.h` and invokes
`BLA_SHIELD_ANCHOR((uint32_t)x)` before evaluating the guard. This ordering is
intentional: even a rejected input may cause private BLA heap mutations. Those
mutations are excluded from the caller output contract, but the campaign must
measure and report them separately. A match of caller output effects is not a
claim of whole-memory equivalence, identical registers or flags, identical
timing, or identical resource use.

`bounded_update` is the complete caller entry point: it invokes the optional
anchor, then calls `bounded_core`. The separately exported `bounded_core` owns
the guard and output write, giving the regional prover an explicitly named
boundary. Regional comparison of that core must remain distinct from executing
the complete wrapper and observing the protected variant's private heap writes.

Defining `GUARD_MUTATION` changes the core's rejection test from `x > limit` to
`x >= limit`. This is an intentional negative control. At `x == limit`, a
reference call writes while the mutated call leaves the initial output value
untouched. A concrete difference witness must choose an initial output value
different from the reference result; comparing only the final numeric value
can otherwise conceal the missing write.

## Artifact and evidence boundaries

Keep the authored source, build oracle, and expected contract separate from
future blind solver inputs. A blind exercise receives only its declared
artifacts and task context. Record any source, oracle, symbol, or previous
solution exposure when interpreting its result.

Preserve each original build and original BLA output unchanged. The campaign
receipt must identify source and artifact SHA-256 values, the exact BLA payload
and options (including seed and protection settings), the generated header
identity, compiler/linker identities and complete arguments, and which
preprocessor definitions produced each variant. Keep any derived analysis or
modified artifact under a separate identity. No exact BLA invocation or binary
result is asserted by the presence of this source fixture.

The builder and oracle belong to the verification harness. Compilation,
artifact inspection, modeled execution, and execution on native Windows are
separate evidence classes. This fixture does not establish native Windows
qualification, universal semantic equivalence, or training efficacy.

The supplied ASPack, Escargot, FSG, Original, and UPX teaching executables remain
private external teaching samples. They are not included here, have not been
executed as part of this fixture intake, and do not supply a known-source oracle
for this target. Their related names or shared regions do not establish complete
program equivalence.
