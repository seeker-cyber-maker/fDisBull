# Interchangeable ROM-to-ASM modules

`rom-disasm` supplies one bounded SH-2 decoding contract implemented by
Capstone, Ghidra and saturn-recomp. The first profile is **big-endian SH-2
(Saturn SH7604)** with an explicit mapping from payload file offset zero to a
32-bit address. Cartridge bank mapping and other console processors remain
outside this profile. Container inspection remains parsing-only.

These modules return instruction proposals. They do not discover functions,
classify code/data, update the persistent native analyzer, execute a game, lift
UIL or generate C. Unknown words remain explicit; there is no fallback to a
different engine when the requested engine is missing or fails.

## Usage and dependencies

```sh
fdisbull rom-disasm /private/CIV.BIN --base-address 0x06010000 \
  --backend capstone --offset 0 --length 2048 --max-instructions 1024

JAVA_HOME=/path/to/jdk fdisbull rom-disasm /private/CIV.BIN \
  --base-address 0x06010000 --backend ghidra \
  --ghidra-home /path/to/ghidra --mode word-scan \
  --length 2048 --max-instructions 1024

fdisbull rom-disasm /private/CIV.BIN --base-address 0x06010000 \
  --backend saturn-recomp --saturn-recomp-root /private/tools/saturn-recomp \
  --mode word-scan --length 2048 --max-instructions 1024
```

Capstone is an existing package dependency. Ghidra and its compatible Java
runtime must be installed separately; `GHIDRA_HOME` is also accepted. The
packaged Java script uses Ghidra's native SH-2 language, with automatic analysis
disabled. Ghidra input files/projects are temporary and removed after the call;
POSIX timeout handling kills the process group. Tested Ghidra: 12.2 with Java 25.
The report hashes its application properties, SH-2 language and launcher; this
identifies selected components, not every byte of a Ghidra/JVM installation.

saturn-recomp must be obtained separately, at commit
`532fd6054ba3171339c972fab05ebd159f29260d`. `SATURN_RECOMP_ROOT` is also accepted.
The adapter refuses another revision or modified decoder sources, and runs the
upstream decoder through an isolated Python subprocess without a global
installation. Its MIT-licensed SH-2 decoder is not vendored. The optional GPL
renderer in that upstream project is not used.

Python:

```python
from fdisbull.rom_asm import disassemble_rom_path
report = disassemble_rom_path(
    "/private/CIV.BIN", base_address=0x06010000, backend="capstone",
    offset=0, length=2048, max_instructions=1024, mode="word-scan")
```

The bytes API is `disassemble_rom(data, **options)`. The standalone JSON method
is `{"method":"rom-disasm","params":{"path":"/private/CIV.BIN",
"base_address":100728832,"backend":"capstone","length":2048,
"max_instructions":1024,"mode":"word-scan"}}`.

## Shared contract

All backends receive exactly the selected bytes at `base_address + offset`.
Inputs are immutable bytes or one regular file, at most 64 MiB. A range is at
most 65,536 bytes / 32,768 word candidates. Base and offset must be even;
overflow, out-of-file ranges and invalid budgets are refused. Path reads check
file identity before/after reading and bind results to the complete file hash.

`fdisbull-rom-asm-1` reports the full source and selected-range SHA-256, mapping,
backend/version/identity, raw instruction text, original bytes, original file
offsets and addresses, normalized comparison spelling, unknown positions,
timings and explicit completion limits. The default length is bounded by the
instruction budget; `complete_scope` applies only to that selected range.

- `linear` stops before the first undecodable word. It is a sequential listing,
  not recursive control-flow traversal. Ghidra retains its listing context.
- `word-scan` tries every aligned word independently, continues after unknowns,
  and counts attempted positions against the instruction budget. Ghidra uses
  its pseudo-disassembler so a neighbouring branch proposal cannot create
  inherited delay-slot context for an independent candidate.
- Unknown or truncated words and budget stops make the decode partial. In
  word-scan mode `attempted_words` can cover the range while `complete_scope`
  remains false because some words were undecodable.

Normalization changes case, whitespace, number spelling, Ghidra delay-slot
prefixes and delayed-branch aliases. For Ghidra's known rendering, it adds an
omitted immediate `#` and represents a resolved `@(address,pc)` literal address
in the same form as the other engines. It preserves indirect, indexed,
predecrement and postincrement addressing. Raw native text is retained. It
does not repair instruction semantics or mask a backend disagreement.

## Civilization Saturn mapping and sample selection

The private Japanese Saturn intake is product T-2003G, version V1.003.
`CIV.BIN` is 867,988 bytes, SHA-256
`53d23f5e878ad86938aeca2e0701549870b1cbc4f080a6ddb8f49041ea382ebd`.
The prior CUE/ISO verification matched its bytes to the ISO file at LBA 28.
The first-read directory record identifies this same file; the Saturn IP header
at F0 declares transfer destination `0x06010000`.

[Sega ST-TECH-1-41](https://forum.jo-engine.org/upload/files/SEGA/ST-TECH-1-41.pdf)
defines F0 as first-read transfer destination, F4 as a size ignored for CDs, and
F8/FC as reserved. It distinguishes the Initial Program from the first-read
file, which the BIOS transfers but does not itself execute. Therefore
`0x06010000` is a justified **transfer mapping**, not an established application
entry. The mapped transfer extent ends at `0x060D3E14` if the entire file is
transferred. It is not an all-code claim. A loader's heuristic `main` label
does not strengthen this evidence.

Before comparing engines, the pilot fixed four 2,048-byte windows at file
offsets `0`, `0x10000`, `0x40000`, `0x80000`: **4,096 aligned word hypotheses**.
The offsets are a deterministic spread through the file, independent of any
engine's discovery. They include data and literal pools. This prevents an
engine's own function discovery from selecting its favourable benchmark.

## Measurement and accuracy methodology

`scripts/benchmark_rom_asm.py` runs five rounds, serially, rotating engine order
by round/sample. Each engine receives the same bytes, address, SH-2 profile and
1,024-word budget per window. Each Ghidra call starts a new headless process and
project; each Saturn call starts an isolated Python decoder process and verifies
the checkout; each Capstone call constructs a native decoder. OS and Ghidra
script caches are not flushed, so these are repeated fresh-invocation timings,
not controlled cold-cache measurements.

The report retains every observation, median, min, max and nearest-rank p95.
There are 20 calls per engine and five observations per distinct window. Treat
pooled timing statistics as descriptive for this fixed workload. They do not
estimate whole-game analysis time or universal engine throughput.

Three timing boundaries are separate:

1. API wall time includes the common validation, source hashing, normalization
   and result construction, plus the backend call. Source loading and final
   result-file serialization are outside the measured API interval.
2. Backend wall time includes engine setup, subprocess launch where applicable,
   import/identity work, decoding, output exchange and cleanup.
3. Engine-loop time is diagnostic: Capstone native decode plus Python row
   construction, Ghidra pseudo-disassembly plus Java rendering, or Saturn Python
   decode plus row construction. These loops do different work; they are not a
   pure decoder-kernel contest.

The harness checks every result's source/range hashes, mapping, budget and
static-only flags. It refuses changed facts across repeats, and changed adapter
or harness source during measurement. Raw reports retain game bytes and must
be written outside every Git worktree. Only the sanitized summary is committed.

Accuracy has two distinct checks:

- Hand-authored vectors derived from the Renesas SH-1/SH-2 manual test signed
  immediates, branch targets, PC-relative alignment, control registers, return,
  invalid words and truncation. A later-CPU instruction probes SH-2 profile
  leakage. These are explicit instruction cases, not a whole-ISA proof.
- On the real samples, compare validity, mnemonic and operand agreement at
  matching addresses. Unknown/unknown is reported separately from successful
  agreement. Agreement is corroboration, never a majority-vote correctness
  oracle. Data words that happen to decode do not become recovered code.

The committed benchmark and accuracy receipts are in
[`docs/evidence/rom-asm-2026-10-30/`](evidence/rom-asm-2026-10-30/).

## Results (2026-10-30)

Host: Apple M1 Max, macOS 27.2 arm64, Python 3.13.13. Capstone's installed
distribution is 5.0.9, while its binding reports 5.0.7 and native API reports
`(5, 0, 1280)`; all are retained rather than conflated. Ghidra is 12.2;
saturn-recomp is 0.1.0 at the pinned revision above. Source and selected-engine
hashes are in the benchmark receipt.

Each timing observation processes one 2,048-byte / 1,024-word window. The table
pools 20 calls per engine (four fixed windows, five rounds). Times are seconds.

| Engine | API median | API min–max | API p95 | Backend median | Engine-loop median |
| --- | ---: | ---: | ---: | ---: | ---: |
| Capstone | 0.012386 | 0.010746–0.051757 | 0.036041 | 0.009380 | 0.003866 |
| saturn-recomp | 0.066965 | 0.057529–0.143301 | 0.077600 | 0.064536 | 0.003772 |
| Ghidra | 3.681690 | 3.232121–7.002894 | 4.374768 | 3.678280 | 0.076598 |

For this invocation pattern, median API latency was about **5.4 times lower for
Capstone than Saturn** and **297 times lower than Ghidra**. Ghidra's result
includes a new JVM/headless project per request; a persistent or batched Ghidra
service was not measured. Engine-loop timings include different language and
rendering work and should not be used as a CPU-decoder speed ranking.

All five rounds produced identical instruction facts. Per round, across the
4,096 distinct positions:

| Comparison | Both decoded, mnemonic and operands agree | Both unknown | Left-only decoded | Right-only decoded |
| --- | ---: | ---: | ---: | ---: |
| Capstone / Ghidra | 3,871 | 224 | 1 | 0 |
| Capstone / saturn-recomp | 3,871 | 224 | 1 | 0 |
| Ghidra / saturn-recomp | 3,871 | 225 | 0 | 0 |

The sole validity difference is at file offset `0x806FA`. Capstone decodes it as
`RTV/N R2`, although the requested SH-2 profile lacks that instruction.
[Renesas SH-2A/SH2A-FPU manual, section 6.3.32](https://www.renesas.com/en/document/mah/sh-2a-sh2a-fpu-software-manual)
identifies RTV/N as new for SH-2A/SH2A-FPU. Ghidra and Saturn reject the word.
An independently authored encoding of that instruction reproduces the issue;
the Capstone test is a **strict expected failure**, retained visibly. The
adapter does not silently rewrite or filter native decoder output.

All three engines pass the 22 baseline manual-derived cases, including invalid
and truncated input. With the additional SH-2A rejection probe, the observed
case outcomes are **22/23 for Capstone, 23/23 for Ghidra and 23/23 for Saturn**.
These are case counts, not statistical accuracy estimates. The 3,871 agreed
decodes are not necessarily executable code; code/data precision remains
unmeasured without independent execution or code classification evidence.

Initial pilot comparisons exposed two adapter issues, now covered by checks:
Ghidra operand separators must be retained to preserve indirect/predecrement/
postincrement syntax, and independent word hypotheses must not inherit a
previous candidate's branch-delay listing context. The final measurements use
the corrected adapters. Earlier partial/pilot measurements are excluded.

## Verification

- Real Ghidra and pinned Saturn enabled: **26 passed, 1 strict expected failure**
  in the engine/API/CLI and harness checks. The expected failure is the visible
  Capstone SH-2A acceptance described above.
- Focused console media, public API and distribution checks: **96 passed,
  6 optional-engine skips, 1 strict expected failure**.
- Full macOS suite: **2,161 passed, 127 skipped, 1 strict expected failure,
  2 failed, 23 errors**. The remaining failures/errors are unchanged Linux ELF
  fixtures: the macOS compiler emits Mach-O or rejects Linux linker options.
  This local full-suite result is not green and does not substitute for Linux CI.
- Source and evidence review checked bounds, source identity, cancellation,
  private output placement, raw operand preservation and package declarations.
  It found no additional material issue after the recorded fixes; it is not an
  independent runtime/whole-ISA qualification.

The wheel, source distribution and tool source ZIP include the new module
resources and pass the distribution guard. Original game media, extracted
payloads, complete disassemblies and external tool checkouts are excluded.
An isolated wheel installation matched all four Python modules and the Java
script byte-for-byte with source. Its public CLI read the same private
Civilization payload through all three engines: each attempted 32 words in the
same 64-byte range, returned 26 decoded words, and retained the same source and
range hashes. The packaged result is a static decode check, not target execution.

## Reproduction

Keep input files and outputs private, use the pinned Saturn revision and the
recorded Ghidra/Capstone identities, then run from the checkout:

```sh
PYTHONPATH=src JAVA_HOME=/path/to/jdk python scripts/benchmark_rom_asm.py \
  --source /private/CIV.BIN --base 0x06010000 \
  --ghidra-home /path/to/ghidra \
  --saturn-root /private/tools/saturn-recomp \
  --output-dir /private/new-rom-asm-benchmark --repetitions 5

GHIDRA_HOME=/path/to/ghidra SATURN_RECOMP_ROOT=/private/tools/saturn-recomp \
  JAVA_HOME=/path/to/jdk python -m pytest -q tests/test_rom_asm.py
```

Console C decompilation, emulator execution, application entry discovery,
whole-file code/data recovery and semantic equivalence remain separate work.
