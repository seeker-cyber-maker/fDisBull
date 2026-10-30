# Optional Ghidra ASM-to-C comparison — 2026-10-30

The built-in `asm_to_c` renderer and the optional `engine='ghidra'` renderer
accept the same bounded x86-16 register block lift. The Ghidra path imports the
source bytes inside a recorded synthetic DOS MZ header with a `RET` terminator,
disassembles them independently,
and invokes Ghidra's decompiler. It returns both a restricted C statement view
derived from Ghidra instruction facts (`text`) and the native decompiler listing
(`ghidra_c`). Only `text` is accepted by the existing `lift_c_block` reader.
The header and terminator are excluded from the source digest and instruction
coverage.

## Reproducible method

[`benchmark_asm_c_engines.py`](../examples/recovery/benchmark_asm_c_engines.py)
uses authored bytes, the same register bindings and declared AX output for both
engines. It runs one unmeasured validation call per engine and then records
three wall-time samples. Each timed call's normalized output is checked against
the validation call after its timer stops; a change leaves the measurement
unknown. The built-in renderer is called in the warm Python
process. Every Ghidra sample launches `analyzeHeadless`, imports a fresh
synthetic MZ project, obtains instruction facts and decompiler C, and shuts
down.
Each normalized view is parsed back into UIL, then compared with the source
model by `verify_block` under its stated 16-bit register assumptions. A
decompiler failure leaves the comparison unknown, with no latency ratio.

The local run used macOS 27.2 arm64, Python 3.13.13, Ghidra 12.2, OpenJDK
25.0.5.0.2 and Z3 5.3.3. The installed Ghidra path was
`/opt/homebrew/Cellar/ghidra/12.2/libexec/support/analyzeHeadless`. The command
was:

```sh
PYTHONPATH=src python examples/recovery/benchmark_asm_c_engines.py \
  --analyze-headless /opt/homebrew/Cellar/ghidra/12.2/libexec/support/analyzeHeadless \
  --java-home /opt/homebrew/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home \
  --repeats 3 --output /private/asm-c-benchmark.json
```

`/private/asm-c-benchmark.json` is a representative private output location;
the report records source hashes, exact generated text, per-call samples,
Ghidra version, decompiler C and proof statuses. No game bytes or Ghidra
project are committed to the repository. The final local report's SHA-256 is
`4b29c459cecc1a81dcabd1cef28283c2324522e04e75891c4953a9864cb3a1a3`.

## Observed result

| Authored block | Built-in median, warm in process | Ghidra median, fresh process | Bounded proof | Observed request latency ratio |
| --- | ---: | ---: | --- | ---: |
| `MOV AX,100; INC AX` (2 instructions) | 0.167 ms | 5.157 s | Both equivalent under assumptions; normalized text identical | 30,947× |
| `MOV AX,100;` then 15 `INC AX` (16 instructions) | 0.399 ms | 4.904 s | Both equivalent under assumptions; normalized text identical | 12,286× |
| `ADD AX,200; DEC AX` (input-dependent AX) | 0.212 ms | 4.955 s | Both equivalent under assumptions; normalized text identical | 23,410× |

Ghidra's native C simplifies the initialized cases to constant returns
(`0x65` and `0x73`) and renders the input-dependent case as
`return in_AX + 199;`. The normalized `text` preserves each supported
instruction as a statement. The earlier raw-binary import of the
input-dependent case produced a Ghidra decompilation error; a synthetic MZ
import of the same source bytes completed. Import context therefore matters
for this case. The native C spelling is diagnostic and was not itself parsed
or proved as C source by `lift_c_block`.

The ratio is **fresh Ghidra request time divided by warm built-in request
time**. It measures this adapter's deployment cost and is not a pure
decompiler-algorithm speed comparison. Three samples and tiny authored blocks
do not establish large-program throughput, output quality on general DOS
functions, or analyst time saved. A long-lived Ghidra process could change the
cost and has not been benchmarked. The completed Z3 checks cover only declared
register outputs at block exit; they do not prove flags, memory, ABI, timing,
native game behavior or source correspondence.

The focused block, backend and benchmark tests passed locally with Z3
(20 passed). The package wheel built and contains the Python backend and
Ghidra script. The repository-wide macOS run with the local Z3 path reported
2,085 passed, 126 skipped, 12 failed and
23 errors. Its failures were confined to Linux ELF fixtures compiled with
macOS `gcc` and managed-code tests missing the optional `dnfile`/`dncil`
dependencies; none were in this ASM-to-C change. This local full-suite result
is not a green gate.

For now, the default remains the built-in renderer. The optional Ghidra path
adds independently decoded facts and native C for inspection. Its per-call
startup cost and the difference between native C and the restricted UIL input
make a default switch premature. The [DOS C route](UDC_DOS.md#c-route) shows how to select and verify
the alternate engine.
