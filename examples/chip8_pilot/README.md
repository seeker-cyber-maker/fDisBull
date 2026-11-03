# fDisBull CHIP-8 instruction-space and corpus pilot

**Status:** executed, bounded prototype. The behavior catalog is a **proposal**, not
an accepted common-UIL profile or a certified CHIP-8 emulator.

**Starting results (2026-11-02):** two independent decoder implementations agreed
on all 65,536 possible 16-bit words in each of three declared profiles, or
196,608 word/profile comparisons. The classic authored interpreter executed
43,938 single-word cases, returned `waiting` for 16 `FX0A` encodings and
recognized another 4,094 words as **opaque** legacy `0NNN` calls. The remaining
17,488 were syntactically invalid under its classic profile. These numbers are
encodings, **not** 43,938 different semantic instructions.

The initial corpus contains nine byte-verified CC0 CHIP-8 Community Archive
programs: **6 CHIP-8, 2 SUPER-CHIP, 1 XO-CHIP**. Only the classic six were run
with the authored interpreter (1,600 instruction-attempt budget, fixed no-key
policy and explicit timer stepping). They exercised **26/34 non-legacy classic
families (76.47%)**, 132 distinct adjacent opcode-family pairs and 244 distinct
triplets. All figures refer to *this workload*, not to the universe of programs.
The synthetic gap-probe set separately checks the eight missed families; those
passes must **never** be added to naturally observed corpus coverage.

## Quick start: standard Python, no native dependencies

From this directory:

```sh
PYTHONPATH=. python -m pytest -q tests/test_pilot.py
PYTHONPATH=. python -m chip8lab.pilot --steps 1600 --out /tmp/fdisbull-chip8-run-001/pilot.json
```

Create the fresh `/tmp/fdisbull-chip8-run-001` directory first. The local run
writes `pilot.json`, `registry_summary.json` and `observations.sqlite` in that
private directory. It refuses to overwrite a prior local database. The source
archive intentionally does not include ROMs, and the corpus-dependent tests are
skipped until the separately fetched bytes are available.

To obtain the pinned public samples when network access is available:

```sh
mkdir -p "$HOME/Downloads/fdisbull-chip8-corpus"
python corpus/fetch_archive.py --dest "$HOME/Downloads/fdisbull-chip8-corpus"
CHIP8_CORPUS_DIR="$HOME/Downloads/fdisbull-chip8-corpus" PYTHONPATH=. python -m pytest -q tests/test_pilot.py
mkdir -p "$HOME/Downloads/fdisbull-chip8-run-001"
CHIP8_CORPUS_DIR="$HOME/Downloads/fdisbull-chip8-corpus" PYTHONPATH=. \
  python -m chip8lab.pilot --steps 1600 --out "$HOME/Downloads/fdisbull-chip8-run-001/pilot.json"
```

The fetcher is **explicit**. It downloads only the nine manifest-listed CC0
programs from pinned repository commit `761e3ffc63f43e6a849e80714122feff2afca208`,
checks SHA-256, Git blob SHA-1 and byte length, and refuses a destination inside
an observed Git worktree. It does not download the GPL-licensed Timendus tests.

If reading this in the **local-results** package, the nine ROMs are included in
`corpus/`, and the saved `results/` directory documents the executed run. The
**source-only GitLab package** intentionally omits ROMs and SQLite files.

## Structure

- `chip8lab/decoder.py`: mask-based decoder and independent branch-based decoder,
  strict malformed-opcode recognition and CHIP-8/SCHIP/XO extension taxonomy.
- `chip8lab/vm.py`: bounded authored classic interpreter; explicit input/RNG,
  timing, memory, stack, display and dialect quirks. Not historically qualified.
- `chip8lab/pilot.py`: full 16-bit enumeration, single-instruction stepping,
  3,000 random short sequences, 3,000 straight-line sequences, dialect probes,
  positive-control mutant, delta-debugging and corpus measurements.
- `chip8lab/gaps.py`: authored single-word probes for the eight families that
  did not appear in the first dynamic corpus sample.
- `chip8lab/registry.py`: local-only SQLite index relating observed source
  address/word pairs, proposed intent labels, originating ROM identity and
  observed edges. **This is not production registry !57.**
- `corpus/manifest.json`: pinned CC0 repository provenance and per-ROM digests.
- `corpus/fetch_archive.py`: opt-in source fetch and identity verification.
- `tests/test_pilot.py`: local tests, independent arithmetic checks, explicit
  negative cases, corpus identity check and index reopen.
- `results/`: example local run receipts; never commit its SQLite or ROM inputs
  to GitLab as part of the prototype.

## What Sandsifter contributes and what does not transfer

Christopher Domas's Sandsifter enumerates/mutates candidate **x86** instructions,
compares an external disassembler with observed processor execution and faults,
clusters anomalies, and reduces failing cases. Its key tunneling method exploits
**variable-length x86 instruction decoding** and boundary/page-fault effects.
CHIP-8's basic instruction words are **fixed 16-bit**; there are only 65,536
possibilities. Exhaustive enumeration is cheaper than length tunneling, and
there is no x86-like hardware-invalid-opcode signal for the VM itself. XO-CHIP's
`F000` is a declared 4-byte extension that must be handled as a profile-specific
exception, not evidence of an unknown classic opcode.

Our adaptation performs:

1. Deterministic enumeration of every word under each dialect; compare two
   independently written classifiers, including syntax/length and unsupported
   legacy/profile-specific cases.
2. One-step execution of every syntactically classic encoding in a controlled
   VM state (supported operations, wait/refusal, faults classified distinctly).
3. Mutation positive control: a deliberately faulty decoder erroneously accepts
   `5XY1` as `5XY0`. The scan detects all **256** wrong encodings and minimizes
   `[6001, 5011, 6102, 1200]` to **`[5011]`**. This is a synthetic test, *not*
   a bug in a third-party interpreter.
4. Differential dialect probes for shift source, `I` adjustment, logical `VF`,
   computed jumps and sprite clipping. Those disagreements are expected profile
   differences and not automatically failures.
5. Repeated randomized sequences with recorded seeds, bounded host policies and
   explicit exception outcomes. Two executions of **our same** authored VM
   matched; this tests repeatability, **not** correctness against an independent
   implementation.
6. Nine public ROMs with exact provenance; raw word scanning is explicitly not
   confused with reachable or executed code. Headless execution is limited to
   the six classic-labeled programs.

**Important:** Neither classifier is an independent historical executable oracle.
The self-authored runtime needs qualification against a mature implementation
(e.g., Octo for XO and the Timendus suite for documented quirks). The GPLv3
Timendus tests should be fetched separately and used with their license.
No claim of discovering a hidden CHIP-8 instruction is made.

Primary references:

- Sandsifter: https://github.com/xoreaxeaxeax/sandsifter (BSD-3-Clause).
- Domas, *Breaking the x86 ISA* (2017):
  https://blackhat.com/docs/us-17/thursday/us-17-Domas-Breaking-The-x86-Instruction-Set-wp.pdf
- CHIP-8 Community Archive: https://github.com/JohnEarnest/chip8Archive (CC0).
- Timendus tests: https://github.com/Timendus/chip8-test-suite (GPL-3.0).
- CHIP-8 quirks catalogue: https://chip-8.github.io/database/

## Coverage is not equivalence

The result has four separate levels:

| Level | What it actually measures | Proof status |
|---|---|---|
| Encoding syntax | Candidate word is admitted by two decoders for a named profile | Exhaustive agreement, not external compatibility |
| Family usage | Families actually visited by our bounded interpreter | Authored interpreter observation |
| Family-pair and -triple novelty | Adjacent executed family sequences under one deterministic policy | Observed trace patterns, not semantic proof |
| Proposed UDL → UIL intent | Byte/offset/operand records with normalized action labels | Candidate only; not accepted core UIL |

The local registry stores **339** `(program, PC, word)` candidates and **367**
observed edges from the six classic runs. It does not infer arbitrary semantic
equivalence from shared mnemonics, and does not grant execution rights. The
original bytes/addresses are verified only against the archive and our own VM;
there is no source-to-original-CPU proof. Full ROM behavior, keyboard release,
font variants, SCHIP/XO execution, vblank, audio playback and original timing
remain unqualified. No third-party agent or independent emulator was run here.

## Corpus growth and holdout protocol

The pinned archive contains **104 programs**: 50 `chip8`, 26 `schip`, 28 `xochip`,
according to the archive's declared metadata. The nine-program pilot is a
small selection, not a random sample. For future saturation estimates:

1. Hold out at least entire programs, preferably by author/repository; do not
   hold out random instructions from the same game.
2. Label the ISA/dialect, game-specific quirks and source license explicitly.
3. Add samples in deterministic batches; record *new qualified family semantics*
   and *new compositions*, alongside mere encoding/trace novelty.
4. After every batch, query existing UDC representations. A missing module
   association means `assess-bind-existing`; a missing backend means `build` or
   `prepare-backend`; an unknown meaning means `recover-contract`.
5. Swede a block only after assessing available implementations, or for an
   explicitly requested alternative. Return the new implementation and **scoped
   evidence** to the registry, never a magic `verified:true`.
6. For unavailable profiles or private/unreviewed source material, retain local
   metadata and a refusal. Never upload licensed game bytes under a new format.

Do not equate synthetic probe coverage (34/34 families) with coverage observed
in the six real programs (26/34). The latter keeps increasing in pairs/triples
while the instruction family count starts to flatten, which is exactly why a
single percentage cannot measure the entire behavior universe.

## Next gate

Integrate the real Timendus test ROMs as explicitly fetched, licensed fixtures;
add an independent mature interpreter oracle, properly qualified SCHIP/XO
execution profiles and timed input traces. Only then consider promoting a
family/idiom into a reusable behavior contract connected to production registry
!57, with each provenance/evidence edge separately qualified.