# Python UDC PoC from real CHIP-8 programs

Status: **experimental tool-first hybrid Python realization**, 2026-11-03.
This is intentionally not a production `fdisbull-uil-*` schema or an independent
proof of historical CHIP-8 correctness. All program bytes are caller-supplied.

## Purpose and the exact boundary

Input is a local CHIP-8 ROM (verified against the existing public corpus
manifest), optional `chip8lab.registry` observations, and a private registry of
reviewed, manually sweded Python opcode rules. The tool constructs observed
source-word/PC records and candidate intent labels, selects registered Python
backings, emits a guarded Python module, and compares each step against the
existing `chip8lab.vm.Machine` under identical host inputs.

This PoC does **not** yet translate to an accepted `fdisbull-common-uil-1`
contract, load arbitrary UDC providers, or register output in the production
MR !57 UDC catalog. The source (`fdisbull-chip8-udl-uil-candidate-1`) is an
**unqualified UDL/UIL candidate**, not an approved semantic model. The generated
module imports the interpreter for missing and dynamically changed operations;
that makes this a *hybrid*, not standalone whole-program native translation.

## Example (from an environment with the public corpus and Python 3.13)

Use the existing pilot as the tool, starting in `examples/chip8_pilot/`:

```sh
# Local private destination, not under a Git checkout.
mkdir -p /tmp/chip8-udc-001

# Register only manually reviewed, trusted templates; deliberately omit two.
PYTHONPATH=. python -m chip8_udc.catalog init \
  /tmp/chip8-udc-001/udc_rules.sqlite --omit CALL RET DRW

# Generate six modules from the existing observed CHIP-8 registry, and check.
PYTHONPATH=. python -m chip8_udc.batch --corpus corpus \
  --observation-db results/observations.sqlite \
  --udc-catalog /tmp/chip8-udc-001/udc_rules.sqlite \
  --output /tmp/chip8-udc-001/stage1

# Agent sweding: source templates for CALL and RET are already reviewed,
# but those families are intentionally not yet admitted into this local index.
PYTHONPATH=. python -m chip8_udc.catalog register \
  /tmp/chip8-udc-001/udc_rules.sqlite CALL RET
PYTHONPATH=. python -m chip8_udc.batch --corpus corpus \
  --observation-db results/observations.sqlite \
  --udc-catalog /tmp/chip8-udc-001/udc_rules.sqlite \
  --output /tmp/chip8-udc-001/stage2

# Register the more complex, reviewed drawing rule and rebuild again.
PYTHONPATH=. python -m chip8_udc.catalog register \
  /tmp/chip8-udc-001/udc_rules.sqlite DRW
PYTHONPATH=. python -m chip8_udc.batch --corpus corpus \
  --observation-db results/observations.sqlite \
  --udc-catalog /tmp/chip8-udc-001/udc_rules.sqlite \
  --output /tmp/chip8-udc-001/stage3
```

Each `batch-audit.json` records specialized and fallback counts per program,
source identities, and next-step sweding work for the remaining opcode families.
The local output contains one Python module and one manifest per program.
No ROM bytes are embedded in generated Python. Each module's `create_machine`
requires the caller to provide a matching source image, checked by SHA-256.

To build from a single source without an observation SQLite database:

```sh
PYTHONPATH=. python -m chip8_udc.cli build --rom corpus/snek.ch8 \
  --output /tmp/chip8-udc-001/snek-single --name udc_snek
PYTHONPATH=. python -m chip8_udc.cli test --rom corpus/snek.ch8 \
  --output /tmp/chip8-udc-001/snek-single
PYTHONPATH=. python -m chip8_udc.cli inspect --rom corpus/snek.ch8 \
  --output /tmp/chip8-udc-001/snek-single
```

`chip8_udc.cli` uses the existing pilot's `run_rom` to obtain observations when
no database is supplied. It never assumes all linear ROM words are executable
instructions; it refuses an empty or truncated observation set. Unobserved,
modified, unsupported and non-admitted instruction sites use the reference VM.
SUPER-CHIP and XO-CHIP are **not** supported as execution/realization targets.
When consuming the observation DB, the generator refuses records marked with
those profiles. Their pilot classification remains separate.

## What was reused automatically versus written manually

| Layer / action | Existing tool | Added / manual work |
| --- | --- | --- |
| ROM identity | `corpus/manifest.json` and SHA-256 | Select explicitly shareable programs; no acquisition or license invention |
| Instruction decoding | `chip8lab.decoder.decode_table` | No game-specific disassembler was authored |
| Address/word observations | `chip8lab.registry.observations.sqlite` or `chip8lab.pilot.run_rom` | Select bounded no-key/clock/RNG observation policy |
| Candidate intent | `chip8lab.pilot.instruction_candidate`, `SEMANTIC_ROLES` | No claim that the resulting labels are accepted common UIL |
| Reusable UDC selection | `chip8_udc.catalog.RuleCatalog` indexed by opcode family and exact reviewed template digest | Agent must author each new opcode template in `chip8_udc.swedes` and register it |
| Python source construction | `chip8_udc.compiler` uses verified observed sites and reviewed rules | Generator and rule-catalog adapter authored once as PoC code, not per title |
| Unhandled semantics | Existing `chip8lab.vm.Machine.step` | Agent must decide whether to swede or keep the fallback |
| Qualification | `chip8_udc.verify.drive` + original pilot VM, per-step state digest + traps | Oracle scope and adversarial fixtures must be decided; an independent historical emulator remains pending |
| Public contribution | Existing repository source and provenance policy | Reviewing distribution rights, tests, profile boundaries and any exported data remains a separate decision |

An `agent-swede` is **not** adding an arbitrary Python snippet to SQLite. For
this bounded PoC, it adds a reviewed `SWEDES` template to an authored Python
source module; registration stores and checks only its exact hash and family.
The compiler never dynamically evaluates arbitrary database text.
Changing an existing registered template invalidates its current identity and
requires a new registry revision; earlier observations remain historical.

## Observed cumulative result

The controlled experiment uses **six public classic CHIP-8 programs**,
1,600 attempts each at most, no keys and one 60 Hz timer tick every nine
instruction attempts. All comparisons are against the same authored pilot VM.

| Rule catalog | Specialized sites / 339 | Generated-Python attempts / 8,978 | Interpreter fallback attempts |
| --- | ---: | ---: | ---: |
| 19 agent-authored rules, `CALL`/`RET`/`DRW` omitted | 255 | 7,075 (78.8%) | 1,903 |
| + `CALL` and `RET` (21 rules) | 295 | 7,750 (86.3%) | 1,228 |
| + `DRW` (22 rules) | 327 | 8,800 (98.0%) | 178 |

No game-specific implementation files were hand-edited between stages. The
rule catalog and generated modules were rebuilt deterministically. The six
source identities and the 339 observed PC/word candidates remained fixed.
`DRW` was responsible for 1,050 previously interpreted instruction attempts
and required manual modeling of sprite XOR, VF collision, clip/wrap behavior
and memory bounds; the `CALL`/`RET` additions contributed 675 attempts and
required matching call stack and underflow/overflow traps.

The 12 remaining observed sites are grouped into six next-step sweding tasks:
`SUBN` (66 observed attempts), `AND` (65), `SUB` (33), `SHL` (10), `LOAD` (2),
`BCD` (1). Those counts describe the selected deterministic observation runs,
not global application usage. A missing rule means interpreter fallback, not
missing ISA semantics: the existing VM already implements these families.

Two programs (Ghost Escape and Octojam 5 Title) executed their complete **1,600
attempt budget** using only generated specialization. This does *not* mean the
whole programs are recovered, all control paths were reached, or a complete
historical emulator can be replaced by the generated modules.

## Verification and boundaries

- 54 local tests passed with the original pilot suite and this PoC's suite.
- All six pinned CC0 programs passed full-state per-step differential runs.
- A further 36 controlled runs (six programs × three RNG seeds × two quirk
  configurations, scripted key events) matched the original pilot VM.
- Tests cover source hash refusal, byte modification fallback, unobserved
  addresses, arbitrary candidate rejection, SQLite tamper detection, stack
  traps, draw collision/clipping and bounds, and output outside Git.
- Historical CHIP-8 timing, device behavior, keypad release, SUPER-CHIP/XO,
  original runtime equivalence and full interactive completion remain untested.
- No performance-speedup claim. The emitted Python is an explicit guarded
  branch chain and may run slower than the interpreter.
- The true `fdisbull` installed tool/CLI is absent in this workspace; this PoC
  reuses its separately delivered CHIP-8 pilot tool, not the production CLI.
  The missing accepted CHIP-8→common-UIL adapter must not be fabricated.

## Future integration and selection

A next integration stage can connect these candidate records to the production
UDC sidecar registry proposed in MR !57. It must preserve separate identities
for behavior, source mapping, compiler definition, realized Python, evidence,
source digest, dialect and observer scope. `source catalog` and `UDC catalog`
are distinct. An imported template or user-submitted claim never grants runtime
execution or publication permission.

For a genuine generalizable compiler, the next test should use an independently
qualified CHIP-8 VM or Timendus-style test corpus as a second oracle, migrate
small accepted pure opcode contracts into `fdisbull-common-uil-1` where admitted,
then prove that previously unseen programs can reuse the registered UDC blocks.
