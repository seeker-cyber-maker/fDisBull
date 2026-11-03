# Pause handoff: CHIP-8 to Python UDC prototype (2026-11-03)

**Status: work paused at the user’s request because chat threads are unstable.**
This records the actual partially completed PoC from the mounted workspace, not
an accepted production compiler or a released fDisBull feature. Resume from
this document and its exact source/receipt identities instead of chat history.

## Context and source identities

- Project: https://gitlab.com/brewster-jennings-group/fdisbull
- Originating CHIP-8 pilot: draft MR !61, branch `agent/chip8-sandsifter-pilot-20261102`, commit `a7eb55cade66e462bcc01b67e16b8ba4494ac12e`.
- Related work: UDC registry draft !57; 1/2/3-block sweding draft !58; 0.31 release-candidate draft !62.
- This handoff is a **stacked documentation/source continuation of !61**, not publication of original ROMs, a release or a merge.
- Correct terms: **UDL = User-Defined Language; UIL = Universal Interaction Language; UDC = User-Defined Compiler.**

## Unpublished work recovered and preserved

The local work tree had four authored PoC files (`generator.py`, `swedes.py`,
`trial.py`, `test_python_udc.py`) plus an `__init__.py`; none was yet in the
GitLab CHIP-8 pilot at inspection time. The private output directory contained
six generated Python modules, six generation receipts, six per-step verification
reports and compiled Python caches. The complete pilot input set, including the
nine pinned public CC0 ROMs and private observational SQLite, was also present.

The only standalone console-style log located was `POC_TEST_RUN.log`.
The current mounted workspace cannot establish whether other chats, agents, Mac
volumes or external local sessions have additional unpublished logs. That is an
explicit outstanding inventory task; absence here is **not** evidence of global
absence.

### What the executable PoC does

1. Reuses the CHIP-8 pilot’s `decode_table` for instruction classification and
   `Machine` for traced reachable PC/instruction pairs and fallback behavior.
2. Scans ROM inputs with two RNG seeds, key sets `[]` and `[5]`, a timer tick
   every 11 operations, and up to 1,600 steps per trace. This is bounded reachability,
   not proof of all executable paths.
3. An agent **manually authored 20 Python opcode-family swedes** in `swedes.py`.
   The tool did not generate their semantics. `generator.py` emits ROM-specific,
   byte-hash-pinned Python functions for eligible observed `(PC, word)` pairs.
4. Generated dispatcher checks live PC and fetched instruction word; it falls
   back to the existing pilot `Machine.step()` for unobserved, unsupported,
   mutated or ambiguous entries.
5. `trial.py` compares exact step outcomes and full `state_digest()` values to
   the **same pilot VM**, across seeds, key schedules, timer intervals and
   bounded steps. It is **not** independent-emulator verification.
6. Original ROM bytes are referenced by local path/digest, not embedded in the
   generated module. Generated modules and their detailed receipts remain local.

This is a trace-specialized **hybrid Python UDC PoC**, not a general source ROM→
`fdisbull-common-uil-1` lifter and not the installed `uil-compile` backend.
The existing common UIL compiler was inspected but had no CHIP-8 ROM importer.
No new production schema, opcode, provider or CLI command is implemented.

## Verification evidence

The local PoC test run is preserved in `POC_TEST_RUN.log`: **28 passed in 1.81s**,
exit code 0, under Python 3.13.5. The six per-ROM JSON reports all say `passed`.
An independent local integrity pass verified every generated module against both
receipt and verification hashes and every ROM against its recorded digest.

| Public CC0 ROM | Compared steps | Sweded steps | Pilot-VM fallbacks | Sweded fraction |
|---|---:|---:|---:|---:|
| `1dcell` | 9,600 | 6,342 | 3,258 | 66.1% |
| `br8kout` | 9,600 | 8,616 | 984 | 89.8% |
| `flightrunner` | 9,600 | 8,658 | 942 | 90.2% |
| `ghostEscape` | 9,600 | 8,826 | 774 | 91.9% |
| `octojam5title` | 9,600 | 7,362 | 2,238 | 76.7% |
| `snek` | 6,198 | 5,780 | 418 | 93.3% |
| **TOTAL** | **54,198** | **45,584** | **8,614** | **84.1%** |

The totals count repeated dynamic steps over six workloads and do not establish
independent correctness or performance improvement. The locally observed
specialization share is not an instruction-set or behavior-coverage estimate.
All generated artifacts had zero conflicting PC/word pairs for their observed scans.

## Manual work versus existing tools

| Work | Source | Automation status |
|---|---|---|
| ROM identity, static decoder classification, bounded `Machine.step()` | Existing CHIP-8 pilot !61 | Reused; no manual recreation |
| General common-UIL Python codegen | Existing `fdisbull.uil_codegen.compile_program` | Inspected; **not used** because CHIP-8 ROM→common UIL lifter is missing |
| Instruction-family Python transition semantics | `python_udc/swedes.py` | **Manually sweded by agent** (20 family emitters) |
| Trace selection, PC+word guards, Python source output | `python_udc/generator.py` | Agent-authored integration glue; deterministic given inputs/parameters |
| Differential comparison, receipts and hashes | `python_udc/trial.py` | Agent-authored harness over existing pilot VM |
| Source and negative tests | `python_udc/test_python_udc.py` | Agent-authored; 28 passing local checks |
| Production UDC integration, source-to-UIL verification, original emulator oracle | None | **Not performed** |

## Resume commands (only when work resumes)

From fDisBull repository root with the !61 pilot plus these PoC files:

```sh
PYTHONPATH=examples/chip8_pilot python -m pytest -q examples/chip8_pilot/python_udc/test_python_udc.py
mkdir -p /private/fdisbull-chip8-udc
PYTHONPATH=examples/chip8_pilot python -m python_udc.trial \
    --rom /private/chip8-corpus/snek.ch8 \
    --out /private/fdisbull-chip8-udc/snek_udc.py \
    --steps 1600 --tick-period 11
```

`/private/chip8-corpus/snek.ch8` is a placeholder: select an actual existing
private corpus directory and verify samples against `corpus/manifest.json`.
The pilot’s explicit `corpus/fetch_archive.py` can fetch the pinned CC0 samples
into a directory outside Git. It is never invoked automatically by the PoC.
The generated module and per-ROM evidence stay outside the checkout.

## Next work, ownership and blockers

1. **Preserve files first.** The user has paused live development because chat
   threads are unstable. Do not delete generated modules, receipts or source.
2. Review the source and public handoff in the stacked draft MR; inspect the
   private recovery bundle for exact prior outputs and SHA inventory. Do not
   merge or publish automatically.
3. Make a true `CHIP-8 → UDL → UIL` importer for a narrow, formal subset. Where
   the existing common UIL validator/compiler admits a contract, use its actual
   `uil-compile` route rather than pretending this hybrid is common UIL.
4. Independently run test ROMs against a second pinned emulator/oracle, with
   documented quirks and frame/timer policy; the current same-VM differential
   result is not independent confirmation.
5. Explicitly assess memory, display, RNG, draw, BCD, and key-wait families for
   further sweding only when the necessary semantics/contract are admitted.
6. Integrate trusted evidence receipts and capability discovery into the UDC
   registry. Stage as separate source changes; do not make `qualified=true` a
   user-submitted field.
7. Recheck publication policy: generated code derived from an entire ROM and
   the detailed receipts stay private; only authored PoC source, tests and
   sanitized numerical evidence go in GitLab.
8. Local Git hub/Mac mirror sync is pending because those volumes are not
   accessible from this workspace. No hosted CI, release, or system install
   is claimed by the local checks.

## Evidence inventory

The private recovery bundle contains `UNPUBLISHED_LOG_INVENTORY.json` with
SHA-256 and sizes for every recovered source, receipt, generated output,
ROM and local pilot result, plus `POC_TEST_RUN.log`. These file identities
are sufficient to detect later loss or alteration when resuming.

The complete Python PoC implementation is stored in this branch; **per-ROM
outputs are omitted from GitLab intentionally**. If the local download is
unavailable after thread recovery, regenerate outputs using the pinned source
and manifest, but recognize that the original receipts describe the old
observations and cannot certify a newly generated artifact without rechecking.