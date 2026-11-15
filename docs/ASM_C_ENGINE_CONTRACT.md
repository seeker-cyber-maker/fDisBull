# Interchangeable bounded ASM-to-C engines

`asm_to_c` accepts a `lift_asm_block` result and selects `builtin`, `ghidra`,
`reko`, or `dcc`. Every successful public call returns
`fdisbull-asm-c-view-2` with the same source identity, register interface,
restricted statement text, native C evidence slot, and diagnostics. The
external tools are optional and selected by path; fDisBull does not install or
bundle them. A failed engine call raises an error and never substitutes another
engine's output.

```python
from fdisbull.udl_blocks import asm_to_c, lift_asm_block

lift = lift_asm_block(bytes.fromhex('05c80048'), {'ax': '$result'},
                      inputs=['ax'], outputs=['ax'])
view = asm_to_c(lift, engine='dcc', tool_path='/path/to/dcc',
                require_equivalence=True)
assert view['text'] == 'ax += 200;\nax -= 1;'
assert view['qualification']['status'] == 'equivalent_under_assumptions'
```

Use the same `lift`, `engine`, `tool_path`, and optional `runtime_path` argument
names for each engine. `runtime_path` is a Java home for Ghidra, a `dotnet`
executable for a Reko DLL, and omitted for DCC. Ghidra's earlier
`analyze_headless`/`java_home` names remain accepted for compatibility. The
native C is in `view['native_c']` for external engines; the built-in renderer
sets it to `None`. Extra engine-specific fields can be inspected, but callers
can rely on the common keys:

| Key | Meaning |
| --- | --- |
| `format`, `engine` | Contract version and selected tool |
| `source_sha256`, `source_kind` | Original block identity, excluding import wrappers |
| `bindings`, `inputs`, `outputs` | Same declared interface as the source lift |
| `text` | Restricted `uint16_t` register statements accepted by `lift_c_block` |
| `native_c`, `native_c_status` | Unmodified tool C listing, or `None`; always marked unverified or not applicable |
| `evidence`, `diagnostics`, `assumptions` | Instruction facts, coverage and provenance |
| `qualification` | Present only after `require_equivalence=True` succeeds |

`require_equivalence=True` parses `text` back to UIL and requires
`verify_block` to establish `equivalent_under_assumptions` for every declared
output. A counterexample, solver unavailability, timeout, malformed output,
source mismatch or incomplete instruction coverage cannot qualify the view.
The proof covers this register-only model. It does not prove the external
tool's native C listing, DOS interrupt effects, memory, flags, control flow,
ABI or execution in an original game.
The ASM reader accepts up to 256 source bytes; rendering can cover that
envelope, while the separate proof-expression budget can refuse long expanded
arithmetic chains. Such a refusal is unqualified, not a failed equivalence
proof.

| Engine | Source of restricted `text` | Native C status |
| --- | --- | --- |
| `builtin` | The same bounded decoder used to lift the ASM | No separate listing |
| `ghidra` | Ghidra instruction facts from a synthetic MZ import | Kept separately |
| `reko` | Address and byte annotated Reko assembly | Kept separately; unobserved register changes may be omitted |
| `dcc` | DCC assembly listing with exact byte coverage | Kept separately; may omit effects despite a complete listing |

The DCC adapter repairs **the normalized restricted view** of a missing `DEC`
by using DCC's own listing. It does not rewrite DCC's native C or infer DOS
termination. `INT 21h` is outside this block contract and causes the adapter
to fail closed. A native DCC patch is a separate qualification problem; the
current [DOS decompiler trial](DOS_C_DECOMPILER_COMPARISON.md) records its
observed omissions.

A private source-patch experiment against DCC commit
`e0585cc7107e68fad07afd63f90d5eb00f65faee` tested constant propagation
and DOS exit liveness. Its first form retained more arithmetic but incorrectly
treated termination as a `char` function return, so it was rejected. A revised
register-state-only form produced no change in native C on the exit, ADD/DEC,
unknown-AH, mixed-exit or FIBOS fixtures. No DCC source patch is included here.
An explicit DOS-exit statement prototype then rendered the exit-101 case but
dropped `DEC` or read an uninitialized alias on ADD/DEC and byte-register
cases; mixed exits and the loop condition remained invalid. That prototype
was also removed. Native C parity requires alias-aware AX/AH/AL values and
control-flow merging before a high-level DOS termination operation can be
qualified. The original DCC executable used by the adapter is unchanged.

Run the [four-engine benchmark](../examples/recovery/benchmark_all_asm_c_engines.py)
with explicit tool paths. It accepts timing only after each engine's initial
and timed normalized outputs pass the same bounded proof. The measurements
include each tool's process startup and extraction path, so they compare
configured requests rather than isolated decompiler algorithms. See the
[Ghidra comparison](GHIDRA_ASM_C_COMPARISON.md) for the earlier two-engine
method and result.

## Local four-engine result, 2026-10-30

The authored blocks and declared AX interface were identical across engines.
Each engine had one unmeasured call and three measured calls per block; every
returned normalized view passed the bounded Z3 proof and was identical across
the four engines. Median request times were:

| Block | Built-in, warm Python | DCC, fresh process | Reko, fresh process | Ghidra, fresh process |
| --- | ---: | ---: | ---: | ---: |
| `MOV AX,100; INC AX` | 0.188 ms | 0.0438 s | 1.566 s | 4.974 s |
| `MOV AX,100;` then 15 `INC AX` | 0.568 ms | 0.0451 s | 1.520 s | 4.932 s |
| `ADD AX,200; DEC AX` with input AX | 0.189 ms | 0.0472 s | 1.559 s | 4.883 s |

The Reko run used official 0.12.5 x64 under Rosetta. DCC used the original
local Qt5 build (binary SHA-256
`163b8669a3d328389b2fbc0d99752f559f31fb95dab6c8e0a5c053d55fc78258`);
the native DCC patch investigation was excluded. Ghidra was 12.2. The
private JSON report SHA-256 is
`fcd14095f138493cdb006a37b6468fa858a2fbd337f0a73599b62f3edf63dab0`.
These medians show that speed can be compared **after** the normalized
register-output gate passes. They say nothing about whether the three native
decompiler C listings are equivalent to those statements.
