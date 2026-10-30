# DOS decompiler investigation — 2026-10-26

The initial recommendation was to evaluate **Reko first** for 16-bit DOS, use
**Ghidra as an independent comparison**, and treat **DCC as a historical
baseline**. That was a candidate review against the fixed 0.17.0 source tag;
it did not alter that release or qualify a decompiler against a private game.
The current [bounded C route](UDC_DOS.md#c-route) adds an optional Ghidra-backed
renderer for the existing straight-line register profile. It does not provide
general function decompilation, source recovery or native parity. Its Ghidra C
listing remains diagnostic evidence distinct from the normalized restricted C
statements used for UIL comparison.
The [measured Ghidra comparison](GHIDRA_ASM_C_COMPARISON.md) records this
integration's authored-block behavior and its observed startup cost.
The later [cross-decompiler trial](DOS_C_DECOMPILER_COMPARISON.md) compares
Ghidra, Reko and DCC on the same authored DOS COM/MZ inputs and one upstream
compiler-generated sample. Its measured scope supersedes the candidate-order
recommendation below for those exact cases.

## Hex-Rays and the older Windows tools

The official Hex-Rays documentation explicitly lists unsupported 16-bit
functions, and its x86 product is documented for 32-bit code. This agrees with
the user's recollection of the limitation. An IDA version being able to load
and disassemble a DOS program does not establish that its Hex-Rays plugin can
decompile the same program. See [documented failures](https://docs.hex-rays.com/core/decompiler/failures)
and [decompiler architecture limits](https://docs.hex-rays.com/core/decompiler/overview).

The supplied older-tool directory contains installers named `idafree50.exe`
and `idademo_windows62.exe`. This was a file inventory, not an installation or
decompilation test. Their filenames do not qualify a 16-bit decompiler. Existing
tools and license files were not changed or included in the delivery.

Keep **16-bit real-mode DOS** separate from **32-bit DOS-extender code**. The
latter may be a suitable x86-32 decompiler input after the executable format,
loader, memory model and entry points are handled correctly. That possibility
is an inference from the supported architecture, not a tested claim about the
user's older installations. Changing a 16-bit function's declared bitness to
obtain output would change instruction and stack semantics.

## Candidate comparison

| Candidate | Primary evidence | Proposed role and qualification gap |
| --- | --- | --- |
| **Reko** | The project's support table identifies 16-bit real mode as its original target and lists DOS MZ support. Its guide exposes a command-line client and a library interface. | First controlled trial: segmented DOS is an explicit target. The project's maturity labels are its own claims; our near/far, compiler-ABI and actual-game cases still need testing. |
| **Ghidra** | Its official processor specification contains a real-mode segment operation, and the framework supplies a decompiler and headless scripting. | Independent comparison engine and source of useful IR/structuring techniques. Correct decoding alone does not qualify recovered far pointers, calling conventions or C output. |
| **DCC** | The DOS-focused project's README documents compiler-library signatures and old source/test distributions, while retaining concrete examples of incorrect large-model and variable-width recovery. | Historical baseline and algorithm reference. Compile a pinned source revision and qualify output; do not assume an old supplied executable matches its source. |

Sources: [Reko support table](https://github.com/uxmal/reko/wiki/Supported-binaries),
[Reko guide](https://github.com/uxmal/reko/blob/master/doc/guide/reko.md),
[Ghidra project](https://github.com/NationalSecurityAgency/ghidra),
[real-mode processor specification](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Processors/x86/data/languages/x86-16-real.pspec),
[DCC README](https://github.com/nemerle/dcc/blob/qt5/Readme.md).

The Ghidra project also contains reports concerning segment propagation across
far calls and x86-16 emulation. Those are specific reported mechanisms, not a
claim that every current decompilation is wrong. Emulation and decompilation
must be qualified separately. They identify useful regression cases for our
comparison: [far-call segment context](https://github.com/NationalSecurityAgency/ghidra/issues/765)
and [x86-16 emulator segment/far-transfer report](https://github.com/NationalSecurityAgency/ghidra/issues/9677).

## What useful C/C++ output must preserve

The goal is a readable, testable reconstruction. Original local names, comments,
class structure, build options and exact source formatting cannot be assumed
recoverable. A C-looking expression is not a semantic proof or a promise of a
rebuildable game.

For our DOS targets, an evaluation must preserve:

- The distinction between file offsets, project addresses, and observed runtime
  segment:offset addresses, including relocation and overlapping segment aliases.
- Near/far/huge pointer meaning; DS/ES/SS assumptions; far-call/return stack
  effects; Pascal/C argument order and cleanup; compiler-specific conventions.
- Integer widths, signedness, flags and carry-dependent arithmetic. A host C
  promotion must not silently replace 16-bit wraparound behavior.
- Jump-table evidence, mixed code/data, indirect targets and unresolved calls.
  An unresolved edge stays explicit rather than becoming an invented function.
- The selected temporal byte interpretation. Original, self-modified and
  execution-layer bytes need distinct inputs and provenance.

The existing analyzer and persistent database remain authoritative for byte
versions, address identity, decoder facts and evidence. An optional external
decompiler result should retain engine/version, configuration, input hashes,
function identity and output diagnostics. It should be revisable alongside the
disassembly, with confidence and unresolved assumptions exposed. The native
debugger can then test a narrowly scoped interpretation against actual accesses
and transitions. This is a design recommendation, not an existing API.

## Smallest useful evaluation

1. Pin a candidate source/release and run an authored tiny/near-code example with
   known arithmetic and branches. Record real output, diagnostics and elapsed cost.
2. Add focused far-call/return, DS-change, pointer-alias, signed-width and
   argument-cleanup examples with independently known expected effects.
3. Compare Reko and Ghidra on the same byte/context inputs. Keep DCC as a bounded
   baseline where it can build and run; preserve counterexamples.
4. Select one already-understood original-game routine. Check the candidate's
   explanation against a byte-verified breakpoint, a bounded trace and its
   observed memory effects before expanding coverage.

Prioritize decision value per cost alongside confidence. A small far-pointer
counterexample is more useful than a full-game pseudocode dump that has not
been checked. Automatic type recovery and bulk reconstruction can follow only
after the address/width/ABI cases earn confidence.

## Police Quest may have a second code layer

Identify the exact edition and its executable/resource hashes first. ScummVM's
official AGI detection table includes the original Police Quest. A different
edition may use SCI; the current investigation has not identified the user's
copy. [AGI detection source](https://github.com/scummvm/scummvm/blob/master/engines/agi/detection_tables.h).

For an SCI edition, SCI Companion already decompiles script resources and
documents recovery of higher-level control flow plus class/instance/property
and method names retained in those resources. That is a script-language view,
not C/C++ decompilation of the x86 interpreter. For AGI, investigate the logic
resource format and an appropriate AGI toolchain instead.
[SCI Companion decompiler documentation](https://scicompanion.com/Documentation/decompiler.html).

For room objects, triggers and interactions, script-level evidence may have
higher reward than reconstructing the interpreter's C. It can inform authored
object context and expected transitions. Pixel-sampling presence checks still
need positive/negative frames from the actual DOS game, including occlusion,
animation and modal cases; script names alone cannot establish visual presence.
