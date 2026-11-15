# DOS-to-C decompiler comparison — 2026-10-30

This is a bounded comparison of **Ghidra 12.2**, **Reko 0.12.5** and a pinned
build of **DCC** on authored x86-16 COM/MZ files. It tests process latency and
whether emitted C exposes selected known effects. The generated C was not
compiled and replayed against the original DOS programs. A recognizable C
expression or a successful decompiler exit is not a semantic-equivalence proof.

## Inputs and method

The primary observable case contains `B8 64 4C 40 CD 21`: set AX to `0x4c64`,
increment AX, then invoke DOS `INT 21h` function `4Ch`. Under that DOS exit
convention, the expected exit code is **101**. A companion case starts with the
same AX value, sets CX to 3, increments AX in a `LOOP`, then exits with code
**103**. The exact authored file hashes are:

| Case | COM SHA-256 | MZ SHA-256 |
| --- | --- | --- |
| Exit 101 | `1a78b33f907b35b487436457027cf8cb80023302792583125783961911a05437` | `09f69ed5c43d5fba5cba0426cb0f42451772f04d0df85e74c314e8d9180a3e10` |
| Loop exit 103 | `852a4b779b819eea02562c7d16f2d2df15bb7e50e8db87ec6f6b9895c1c1e661` | `ed486e59926ab00a3e7da790c5f21791fabc37f6150c0b3c2bc7c3b5c2558bcd` |

The MZ files have a 32-byte no-relocation header with CS:IP at the first code
byte. fDisBull identified them as valid, loadable DOS MZ files. Ghidra and
Reko analyzed the COM files at `0C00:0100`; DCC used its own COM loader.
Inputs were kept outside Git. No guest execution or whole-game recovery was
used in this trial.

For the small COM exit case, each tool was run in a fresh process three times
on the same file and host. Ghidra used `analyzeHeadless` with the 16-bit real
mode binary loader, `-noanalysis`, explicit entry disassembly and one
`DecompInterface` call. Reko used its official x64 CLI under Rosetta and an
explicit MS-DOS environment. DCC was built locally from `nemerle/dcc` branch
`qt5`, commit `e0585cc7107e68fad07afd63f90d5eb00f65faee`. These are
**request wall times**, including startup and output generation, under
different runtimes and analysis scopes. They are not isolated algorithm-speed
measurements. The first Reko sample also includes cold Rosetta translation.

| Tool and tested build | Exit-101 COM samples | Median | C exposes DOS exit 101? |
| --- | --- | ---: | --- |
| DCC local Qt5 build | 0.090, 0.036, 0.047 s | **0.047 s** | **No**: emits only an AX-local assignment |
| Reko official 0.12.5 x64 under Rosetta | 5.565, 1.773, 1.562 s | **1.773 s** | **Yes**: `msdos_terminate(101)` |
| Ghidra 12.2 | 4.357, 4.534, 4.468 s | **4.468 s** | **No**: unresolved `swi(0x21)` and bad-instruction warning |

A separate native ARM **partial source build** of Reko took 0.749, 0.679 and
0.597 seconds (median 0.679 s) on the same COM case and emitted the same
termination call. Its upstream build required a local adjustment, so it is
not the official distribution timing. The official x64 release required a
private x64 .NET runtime to run under Rosetta; no system installation changed.

## What the C preserved

For the authored **COM** loop, Reko's C shows three increments and terminates
with the resulting low byte, giving 103. Ghidra shows the loop count but does
not resolve the DOS termination effect. DCC emits a failed loop condition and
omits the termination. For the matching **MZ** exit-101 file, Ghidra still
leaves the interrupt unresolved, DCC still omits it, and Reko emits an empty
`void` function. Reko's result persisted with an explicit `--env ms-dos` on its
official release. These are observations for the tested fixture and import
configuration, not global support or failure rates for MZ files.

Straight-line register-only files tell a different story. Ghidra's native C
recovers the final AX constants and an input-dependent `in_AX + 199` expression
when those bytes are imported in an MZ context. Reko and DCC infer `void`
entry functions for the return-only files and omit unobserved AX changes.
That omission cannot be scored as a wrong whole-program result when the file
has no observable use of AX. Ghidra's C spelling also does not by itself prove
16-bit modular behavior for every input. The fDisBull [restricted ASM-to-C
comparison](GHIDRA_ASM_C_COMPARISON.md) checks a separate normalized statement
view with Z3; it does not prove Ghidra's native C listing equivalent.

We also tested the **13 KiB FIBOS.EXE** bundled with DCC's source examples
(SHA-256 `5c162c99a17d7ea7eb2880867c131e3075e8f95acf7e4f24f6899861e4859aef`).
DCC recognized a Borland v2 small-model binary and loaded its matching
signature file. Its C exposes a main input loop, prompts, Fibonacci recursion,
the `x > 2` guard and `exit(0)`; the inferred result type is signed where the
supplied example source says `unsigned`. Three DCC runs took 0.079, 0.024 and
0.029 seconds. Reko's official release found `_main`, `_fib` and the recursive
calls in 5.972 seconds, but `_main` contains invalid stack expressions.
Ghidra's fresh analysis plus a script selecting one recursive function took
7.215 seconds and yielded a clean Fibonacci function; its startup C has stack
warnings and a distinct main function was not qualified. These times cover
different output scopes and should not be ranked as full-program speed. The
source and EXE are paired by the upstream distribution; an independent rebuild
or byte-to-source mapping was not established.

The installed **Binary Ninja 5.3 Free** exposed no supported headless/API
route for repeatable testing, so its DOS precision and speed remain unknown.
The installed **IDA Professional 9.4** headless process stopped before analysis
with a license error; its local documentation describes the x86 decompiler as
32-bit. No 16-bit C result or timing is claimed for either installed product.

## Decision boundary

Keep the built-in fDisBull renderer as the fast default for its narrow
ASM-to-UIL proof contract. Ghidra remains a useful optional second view for
register functions and detailed inspection. Reko is the strongest candidate
from this trial for **DOS-aware COM C output**; qualify a reproducible native
build and MZ behavior before making it another fDisBull engine. DCC is a fast,
compiler-specific baseline when its signatures match, not a dependable
translator for these handwritten blocks. None of the three has been qualified
for general DOS source recovery or whole-game behavior.

Primary tool references: [Ghidra headless import options](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/RuntimeScripts/support/analyzeHeadlessREADME.md),
[Reko CLI guide](https://github.com/uxmal/reko/blob/master/doc/guide/cli.md),
[Reko 0.12.5 release](https://github.com/uxmal/reko/releases/tag/version-0.12.5),
[DCC source and usage](https://github.com/nemerle/dcc),
[Binary Ninja headless availability](https://docs.binary.ninja/guide/mcp.html),
and [Hex-Rays x86 decompiler limits](https://docs.hex-rays.com/9.0/user-guide/decompiler/limit).
