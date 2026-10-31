# Linux x86-64 scaffold and C realization

The Linux target emits a static ELF64 program using the same private x64 module
ABI and scalar lowering as the Win64 PE target. The shell owns the Linux
process entry, a System V entry adapter, syscalls, presentation and process exit.
The shared plan, UIL and math implementation remain independent of those parts.

## Measured result

The original Win64 pilot's plan and module definitions produced a Linux ELF
whose complete math slot and shared program-function slot were byte-identical
to the PE. Rebuilding the PE also reproduced its previously native-tested bytes.
The ELF ran as a Linux process under the existing QEMU/Linux runtime, printed
`Win`, exited with code 0 and retained left/right/scratch=65535/2/12345 with sum=1.
This demonstrates the private ABI boundary for that program. It does not imply
that arbitrary DOS machine code runs directly in a 64-bit process.

An optional C backend realizes the same scalar UIL as freestanding C. The
compiler targets a small System V function receiving compact input/output word
arrays; an adapter marshals those ports from the program's arena. Physical
program offsets belong to the adapter. The compiled C function can therefore
remain identical when the surrounding binary's state placement changes.

For the Colonization food projection, the same contract/UIL was emitted using
the direct machine-code lowering and the C backend. Both ran on 64 original
comparison inputs: **128 Linux process executions**, all matching the retained
DOS/Windows instruction receipts. The C food body is 111 bytes in the recorded
compiler build; size alone is not a performance result. Its code stayed identical
when general-register-only compilation was made explicit.

A composite program with C addition and C food modules also ran on both targets.
Linux printed `Win` and exited with code 0. The Windows program displayed and acknowledged
its MessageBox and exited with code 0 under Wine/QEMU. Both produced sum=1 and food=4 and
preserved caller state. Both C module slots were byte-identical across the ELF
and PE. These are generated native programs, not wrappers around the DOS game.

The food C is derived from the recovered UIL. It is another realization, not an
independent source oracle. Finite native comparisons, supplied-model proofs and
original-source fidelity remain separate claims. Full game recovery, original
Win16 process execution and unrestricted C translation remain unqualified.

## Public build interface

`build_selection_shell` and JSON `build-udc-shell` preserve their Windows default.
The additional options are:

| Option | Meaning |
| --- | --- |
| `target="linux-x64"` | Static ELF64 with Linux syscalls; default remains `windows-x64` |
| `service_adapters` | Explicit mapping for every selected notification provider |
| `capture_state=True` | Linux analysis observation on descriptor 3; default is false |
| `c_compiler` | Explicit Clang path when a `c-uil` implementation is selected |

```python
from fdisbull.udc_layers import build_selection_shell

build = build_selection_shell(
    project, selection_id, plan, new_private_directory,
    target="linux-x64",
    service_adapters={
        "present": {"backend": "linux-stdout", "acknowledgment": "none"}
    },
    capture_state=True,
    c_compiler="/explicit/path/to/clang",
)
```

The plan and selected logical modules can stay fixed while the target adapters
change. Linux's stdout provider emits the text and requires no acknowledgment;
this is a declared presentation change from MessageBoxA. Title/icon rendering
and UI acknowledgment are not claimed equivalent. Extra service-profile
obligations refuse instead of being silently dropped. Native file/media
services remain outside this profile.

The builder validates the target before emission and reserves a new directory
outside Git. It never executes the generated program. A selected C backend does
invoke the explicitly supplied compiler. The capsule records plan/module IDs,
qualification receipts, target bindings, compiler identity/flags, generated C,
object/text hashes and output identity. A compile result is not native execution
qualification.

## Calling conventions and state

The shared private ABI is RCX=arena and EDX=status. UIL module returns use
RAX with the declared scalar type: i16 values are sign-extended to 64 bits;
unsigned and boolean values remain nonnegative. This allows checked caller
stores to preserve negative i16 results. Program function results retain their
raw u16 carrier in EAX. Linux's
public function adapter takes the arena in RDI and returns
`(status << 32) | u16_result` in RAX. It establishes the stack alignment/shadow
space expected by the existing private functions. Function locals initialize
per activation and only declared outputs commit, as in the selected PE profile.

The freestanding C function uses RDI=input-word-array, RSI=output-word-array and
the same packed RAX result. Its wrapper preserves the additional Win64
nonvolatiles while bridging to this System V function. Generated C supports the
existing word scalar types and pure set/add/subtract/if/require nodes. Logical
wrapping, signed bit tests and assignment-range refusal remain explicit. Output
arrays are committed only on success.

Compilation uses Clang's x86-64 Linux target without a CRT, builtins, red zone,
FP/SIMD registers or external calls from the generator. Native object relocations
and oversized function/adapter slots refuse. Arbitrary supplied C, general
C parsing, other languages, foreign library calls, callbacks and unwinding are
outside this backend. The independent source/object/native qualification edges
must remain visible when those capabilities grow.

## Explicit Linux observation

With `capture_state=True`, run the authored executable in Linux x86-64 with
descriptor 3 open:

```text
./program 3>frame.bin
```

The binary frame is `UDC1`, status/u32, raw return/u32, arena-byte-count/u32,
then the word-carrier arena, all little-endian. `decode_observation(frame, build)`
validates completeness and converts logical signed/bool values. A failed or
partial observation export exits with code 4; an incomplete frame is never a result.
The caller must separately bind the process and executable identity.

The common status values are 0 for success, 1 for qualification/range refusal,
2 for loop budget and 3 for provider failure after state commit. Observation export is
an analysis profile, not an additional game action. Linux process tests cover
native state, success, atomic refusal, bounded loops and signed values. The
ordinary Linux CI runs these directly; macOS skips those host-specific cases
and the private pilot instead ran real processes under a Linux kernel/QEMU.

Process startup blocks SIGPIPE so a closed output pipe returns through the
write adapter: stdout failure reports status 3, and observation failure exits
with code 4. Failure to establish that signal policy exits with code 5 before
calling the program. Closed-reader pipes are included in native validation.

## Replicas and observation

Lineage identifies the original DOS file and each reconstructed artifact.
Behavioral equivalence asks whether an observer with a specified interface can
distinguish their admitted behavior. The math observer saw the same tested
results; the UI observer can distinguish a message box from stdout. A hash can
identify an artifact while saying nothing about its behavioral correctness.

A synthetic program assembled from compatible original and rewritten blocks
has explicit multiple-source lineage. Its correctness depends on the declared
contracts and qualified adapters, not on choosing an original/replica label.
Broader inputs, effects, timing or hardware observations can expose differences
outside the current qualification boundary.
