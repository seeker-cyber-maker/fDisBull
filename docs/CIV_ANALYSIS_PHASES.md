# Civilization analysis phases and slice ledger

Status: active working method. This document adapts the recovery and port phases
recorded by Civ64 and the source/toolchain separation used by civd to the
fDisBull evidence model. It is a process contract, not a claim that the whole
Civilization game has been recovered.

## Purpose

Use civd's reconstructed DOS implementations and Civ64's published analysis
records as a path through the forest: identify a small, reachable question,
carry its edition and authority context, test it, and promote only the part that
survives the gate. A useful draft blueprint may contain guesses. A guess is
explicitly temporary and remains in the ledger until evidence promotes it to
proven, disproves it, or leaves it unresolved.

The process keeps four things separate:

1. **Blueprint:** the current model of systems, records, events, values, and
   likely relationships. It may contain `guessed` and `candidate` entries.
2. **Evidence:** source text, decoded bytes, address-linked facts, runtime
   observations, oracle comparisons, and persisted fDisBull receipts.
3. **Implementation:** the UIL/UDC representation selected for a bounded slice.
4. **Release claim:** the smaller set of behavior that passed its independent
   qualification gate.

A blueprint entry is never silently promoted because it is plausible or because
another Civilization edition uses a similar name.

## Edition and authority boundary

The first two authorities are not interchangeable:

| Authority | Edition / role | Use | Current limitation |
|---|---|---|---|
| `sjmelia/civd` | DOS 474.05 reconstruction | DOS game logic, records, source-shaped behavior, toolchain and byte-verification clues | Reconstructed source; inferred names and declarations remain labeled |
| `Buyukcaglar/Civ64` | Win16 Civilization port and DOS graphics research | Win16 recovery phases, DOS executable/asset documentation, presentation and scene correspondence | Public repository does not publish the recovered game C or full DOS listing inputs |
| fDisBull target artifacts | Exact local binaries and files | Bytes, formats, traversal, xrefs, versions, images, and runtime evidence | Coverage is bounded; unknown indirect or segmented behavior remains unknown |
| Independent oracle | Direct arithmetic/model/runtime comparison | Qualification of a slice without reusing its implementation algorithm | Must be declared per slice; a second implementation by the same route is not automatically independent |

The DOS and Win16 releases can differ in events, values, compiler behavior,
RNG, and data layout. A disagreement first gets an edition check. If both
claims are applicable to the same edition and still differ, it becomes a
priority conflict rather than an averaged rule.

## fDisBull version preflight

Every analysis run must use the active local fDisBull installation, not a
stale source checkout or an agent's cached environment. The active selector is
`/Users/Shared/fDisBull/current/RUNTIME.json`; it records the versioned
installation and interpreter. At the time this workflow was written it points
to fDisBull **0.26.1**, source commit
`f783f2aa43bae779392fd3f6558c980c5e4884b5`, with the qualified interpreter at:

```text
/Users/Shared/fDisBull/releases/0.26.1-f783f2a/venv/bin/python
```

The preflight is:

```bash
python - <<'PY'
import json
from pathlib import Path

runtime = json.loads(Path('/Users/Shared/fDisBull/current/RUNTIME.json').read_text())
print(runtime['version'])
print(runtime['source_commit'])
print(runtime['python'])
PY

/Users/Shared/fDisBull/releases/0.26.1-f783f2a/venv/bin/python \
  -c 'import fdisbull; print(fdisbull.__version__)'
```

The printed package version must equal the active selector's version. If the
selector and a convenience path disagree, stop treating the convenience path
as authoritative, record the friction, and use the versioned interpreter from
`RUNTIME.json`. Agents must not report results from 0.8, 0.18, 0.20, 0.25, or
0.26.0 as results from the active 0.26.1 installation.

When testing a feature branch, use the active 0.26.1 interpreter with that
branch's source explicitly on `PYTHONPATH`. This tests the branch code with the
current runtime/dependency environment without mutating the active installation.

## Phases

The phases combine Civ64's staged recovery/port gates with civd's source,
toolchain, overlay, and executable-verification boundaries.

### P0 — Intake, provenance, and the question

**Goal:** choose one question whose answer can unlock a useful next slice.

Record:

- target path, edition, format, size, SHA-256, and load context;
- source/reconstruction commit and the exact file/function/line authority;
- the current blueprint entries touched by the question;
- available tools, runtime backend, and active fDisBull version;
- expected reward, probe cost, and stopping condition.

Do not broaden a question because a nearby subsystem looks interesting. If the
question is already answered by a pinned source implementation, use that path
before starting a wide binary sweep.

**Gate:** the target and claim are unambiguous, and the next observation is
named.

### P1 — Format and address map

**Goal:** make coordinates safe to reuse.

For DOS/Win16 inputs, map MZ/NE headers, load modules, relocations, segments,
entry points, overlays, drivers, resources, and file offsets. Preserve packed
and unpacked files as distinct byte versions. For every recovered address,
retain the coordinate kind: runtime address, project address, segment:offset,
or file offset.

The Civ64 DOS documentation is the model here: its EXEPACK root, overlays, and
driver files are documented separately. `CIV_UNP.EXE`, when available, is a
comparison artifact for the unpacked root, not a substitute for identifying the
packed input or its overlay directory.

**Gate:** every address used by the next slice has a format-aware mapping and a
source-byte/version identity, or is explicitly marked unresolved.

### P2 — Bounded inventory and traversal

**Goal:** establish the cheapest useful static graph.

Follow fDisBull's native-decoder facts and recursive entry-point traversal first.
Then investigate referenced memory and later symbols/exports. Deduplicate
instructions and evidence by address plus code version, never by address alone.
Keep inferred functions as candidates. Preserve xrefs, annotation authorship,
unknown indirect calls, and segmented behavior.

A budget stop is a partial result, not convergence. Prefer a known caller,
writer, reader, or dispatch path over a broad scan. Record why a later seed is
needed.

**Gate:** the chosen function/data path is decoded far enough to state what is
known, what is inferred, and what remains unknown.

### P3 — Blueprint slice and decision tree

**Goal:** turn the current evidence into a bounded model without hiding guesses.

Each blueprint row contains:

| Field | Meaning |
|---|---|
| `slice_id` | Stable identifier, such as `CIV-PROD-001` |
| `edition` | DOS 474.05, Win16, or another exact release |
| `question` | One behavior or representation to settle |
| `claim` | Current plain-language model |
| `status` | `guessed`, `candidate`, `proven`, `false`, `conflict`, `blocked`, or `unknown` |
| `authority` | Source, binary, runtime, oracle, or explicit inference |
| `evidence` | File/hash/address/receipt references |
| `next_probe` | Cheapest observation that can promote or reject it |
| `stop` | Condition for closing the branch |

A real alternative gets a compact decision-tree branch:

```text
question → hypotheses → current evidence/confidence
         → expected reward and probe cost
         → decisive observation
         → stopping condition
```

Guesses are allowed in the draft blueprint. They are not release evidence and
must not be turned into implementation invariants without a gate. When a guess
is proven false, retain the row and its decisive evidence rather than deleting
it.

**Gate:** one slice has a source-shaped behavior, explicit limits, deliberate
non-claims, and a decision tree for its unresolved alternatives.

### P4 — Semantic implementation and independent qualification

**Goal:** implement one slice without collapsing the reference and the test
into the same algorithm.

Build:

1. a source-shaped reference model from the strongest current authority;
2. a separate fDisBull UIL/UDC implementation;
3. typed input/output limits and invalid-input behavior;
4. an independent oracle, original comparison, or runtime observation;
5. normal, boundary, invalid, reset, overflow, negative, and conflict vectors.

The slice stays out of release until its limits, implementation comparison, and
independent oracle agree. If civd and Civ64 disagree about an event or value,
record that conflict as a priority investigation item and do not merge the
models merely to make qualification pass.

**Gate:** reference/implementation qualification and independent comparison
agree, with all tested limits recorded.

### P5 — UI and scene representation

**Goal:** represent the original DOS UI only after the underlying state/action
contract is bounded.

For each scene or control, keep separate facts for:

- visible: it appears in the captured frame;
- ready: the program has reached the state where it can be used;
- enabled: the program accepts the action;
- action identity: what the input means;
- state/persistence: what changed and whether it survived restart.

Use the Civ64 DOS extension's separation of executable, asset, palette, font,
text, timing, scene, and counterpart evidence. A screenshot or label is a
candidate lead, not proof of dispatch or committed state. A direct state
placement can isolate a mechanism, but it does not prove the ordinary player
route.

**Gate:** the scene has a versioned object definition, a valid action point or
named input route, supporting evidence, and a tested state transition—or an
explicit unresolved ceiling.

### P6 — UDC integration and restart proof

**Goal:** make the qualified slice executable and persistent.

Persist the semantic and native layers. Verify:

- generated host behavior against the independent oracle;
- native image format and selection capsule;
- project close/reopen identity;
- patch isolation and earlier code-version preservation;
- no accidental dependency on a stale fDisBull installation;
- actual runtime execution when the target backend exists.

An emitted Linux ELF is not macOS runtime evidence. A successful input delivery
is not UI success. A completed build is not game compatibility.

**Gate:** restart, isolation, and the declared target-runtime checks pass, with
unsupported host/backend claims kept explicit.

### P7 — Independent review, friction, and release

**Goal:** challenge the slice before promotion.

Use a reviewer that did not author the slice when practical. Recheck:

- byte/hash and edition identity;
- source versus inference labels;
- address and version links;
- release-gate tests and oracle independence;
- competing hypotheses and known conflicts;
- README limitations and documentation accuracy;
- tool friction and missing-capability workarounds.

Friction receives a separate receipt/PR when it affects repeatability or user
workflow. A missing tool is handled by defining the smallest required interface,
implementing it with tests, and recording its evidence boundary; a shell
substitute is not silently treated as equivalent.

**Gate:** promote only the qualified slice. Keep the blueprint, unresolved
conflicts, and next discriminating probe attached to the next phase.

## Initial blueprint ledger

This is the starting ledger for the current fDisBull Civ work. It is deliberately
small; later rows should be added only when they unlock a bounded question.

| Slice | Current status | Evidence-backed claim | Next useful probe |
|---|---|---|---|
| `CIV-BASE-001` | `proven` for bytes only | The packed DOS `CIV.EXE` can be retained as an original-backed byte-preserving UDC baseline | Supply a verified DOS image when overlay/runtime analysis is required |
| `CIV-PROD-001` | `proven` for the declared contract | civd city shield storage is signed, values outside `0..999` reset before production, and the fDisBull implementation matches an independent oracle | Extend only through the next caller/record boundary, not by guessing purchase policy |
| `CIV-ROOT-001` | `proven` for the pinned DOS byte identity | The clean-room EXEPACK decoder produces the published `CIV_UNP.EXE` size/SHA and preserves the 23-overlay tail | Trace the root/overlay manager and keep packed/unpacked versions distinct |
| `CIV-DOS-ADDR-001` | `proven` for the loader mapping | Civ64 `R:0D12:0045` is load-module-relative and maps to fDisBull runtime `1D12:0045` at the default MZ load segment | Confirm the same translation for callers and overlay entry points |
| `CIV-DOS-CITY-001` | `proven` for the static trace | `0D12:0045` decodes to a `townbuf`-indexed routine; five reloc-backed root callers exist in four functions; the signed 999/negative `shield_box` reset is present at `0xD244`; the input-loop dispatch is fully enumerated in segment `0A99` (fifteen compares: `A`, `-1`, `b`, `c`, `i`, `h`, `m`, `v`, `a`, `s`, `1`..`9`, `p`, `M`, `r`), with the `b` buy path, the `a` unit-list cursor (`0A99:7785`) and the `s` sell-building cursor (`0A99:799E`) decoded and civd source agreement | Bind the observed tab/overlay display changes to `townbuf` fields at a breakpoint; the display-level comparison is recorded in `CIV_CITY_RUNTIME_OBSERVATION.md` |
| `CIV-WIN16-001` | `candidate` | The local original Win16 `CIV.EXE` is a distinct NE target; the active 0.26.1 traversal remains partial and does not prove semantic names | Build the NE inventory and select one function/data family with exact address evidence |
| `CIV-EDITION-001` | `conflict` | civd labels the `22de2748…` DOS image 474.05 while Civ64's DOS documentation labels the same-size/hash image 475.05 | Verify the supplied raw DOS image and reconcile release metadata before merging DOS UI claims |
| `CIV-UI-001` | `candidate` / partial fixture | The city-screen geometry, controls, and state candidates are now represented by a partial `fdisbull-il-scene-1` inventory in `examples/civ/civ_city_scene.json`; the input dispatch and one original-runtime route are qualified. A DOS 474.03 install reached the city screen from cold boot with keyboard-only input; `h`, `m` and `v` produced content-area, map-view and full-screen-overlay deltas (876 / 9,449 / 63,973 pixels), and the overlay exit restored the baseline to 5 pixels. `a` had no unit to list. A later run with a settled city screen opened the production chooser with `c` in keyboard-only mode (`What shall we build in Rome?`, Settlers/Militia/…), and the debugger overlay matched that transition; an earlier `c` attempt failed only while the founding note or banner was up | Bind one display change to committed `townbuf` state at a breakpoint; exercise `a` with a unit, and bind `c`'s chooser selection to the production byte |
| `CIV-UDC-BUY-001` | `candidate`, natively observed on macOS arm64 across eight states | The whole buy path is recovered: cost/10 from the unit table `+0x18` and the improvement table `+0x18`, `base = ClampInt(10*cost10 - shield_box, 0, 999)` (`R:1DC4:007C` = `ClampInt`, port `11C8:0063`), unit price `2b + i16(b*b)/20`, building price `2b`, the two doublings, the signed guard and the commit | A live observation of one purchase to bind the two table reads to the runtime values; the exact Yes/No dialog call is still unidentified |
| `CIV-UDC-BUY-002` | `proven` by the corrected decode | The earlier trace had the two cost branches inverted: production `>= 0` is a unit and reads the 34-byte unit table, production `< 0` is a building and reads the 30-byte improvement table, and only buildings take the `k > 21` doubling (the unit branch `jmp 0x7459` skips it). The 34-byte values `4,1,2,2,3,3,2,4,...` are Civ1 unit costs / 10, not an unexplained board | — |
| `CIV-UDC-UI-001` | `candidate`, original-code/UIL/ARM64 agreement over 70 finite cases | A retained `1D12:0045` snippet is bound to a typed sanitized shield-step module; the macOS arm64 build runs natively and reports `$shield_box: 3` for the default state. The separate source oracle compares original reset/update spans, UIL and ARM64 on 70 cases; shared-IL proof scope remains model-only | Keep the Linux ELF unrun until a Linux runtime exists; extend the differential sweep when the model grows beyond the shield step |
| `CIV-EXE-ATLAS-001` | `proven` for static metadata | `civ_exe_atlas.py` joins `CIV.MAP`, 42 `*.COD` listings and the pinned unpacked image: 97 segments, 23 overlay images, 1,188 publics, 430 C functions and 5,951 calls. All 430 entry opcodes and all 5,951 call opcodes/targets match; 428/430 C entries equal a public-map address; 21/21 Civ64 DOS anchors resolve to a civd function (15 entries, 6 inside) | Add resident-assembly/runtime symbols and use the atlas to seed fDisBull projects; retain the Windows byte-equivalence gap |
| `CIV-PATH-001` | `proven` for static mapping | The six `PATH.C` functions occupy `F1E31:0000..118D`; `_unit_goal` computes `600h*player + 0Ch*unit` and reads `goto_x/goto_y` at `81DA/81DB`; Civ64's DOS-profile text agrees; `_wrap_x` matches its source branches byte-for-byte; all path call opcodes/targets verify | Bind one live `goto` step to the unit record and returned direction; do not promote runtime pathfinding until then |
| `CIV-GAME-UIL-001` | `candidate` / partial scene graph, setup axes source-bound | `examples/civ/civ_game_scene.json` represents 23 DOS contexts and 95 objects with 47 shared-IL programs: title, load, customize, Birth, setup, world, city, production, units, city view, reports, Civilopedia, diplomacy, spaceship, Hall of Fame, game over, newspaper, palace and audience. All 51 screen anchors resolve to civd functions (43 entries, 8 inside). Five difficulty objects write `$difficulty` from `cur_tier` (DGROUP:6B86); five competition objects write `$competition` (DGROUP:D2F4) and the derived `$players` mask (DGROUP:6B8A); the tribe menu maps both row groups through `NEWGAME.C:113-117` into `$human_civ` (DGROUP:D7EE) and `$tribe` (DGROUP:D7F4); the city auto-build action toggles `status` bit 10h at DGROUP:70EC + city*1Ch + 06h; unit-list next/previous clamp `choice_f` to `unit_count_i-1` and select stores it at [0x70DC]; city buy computes unit and improvement rush prices from original-table costs (Settlers 4, Militia 1, MarketPlace 8; the improvement branch doubles the raw, doubles past index 21 and doubles an empty shield box), charges the treasury and sets `shield_box = 10*cost`; `$rule_options` is bound to DGROUP:E3C4. The scene walks through the Z player and shared IL validator. A live 474.03 founding read binds the first city record (Palace, size 1, Militia production 1, empty garrison, shields 0) and `money[1]=50`; the scene starts from that state | Read `shield_box`, money and status from a live city-screen state before and after one buy, and add a matched buy observation before promoting beyond `partial: true` |

The `guessed` and `candidate` rows are navigation aids only. They become
`proven` or `false` through a later slice gate; they are not release claims.

## Conflict priority

When two implementations or editions disagree about an event or value, create a
conflict row before changing either model. Prioritize by:

1. same-edition applicability;
2. reachability in the selected target;
3. effect on persisted state or user-visible action;
4. low-cost decisive observation;
5. number of downstream slices blocked.

The first probe should normally be the cheapest one that distinguishes the
hypotheses: exact source context, caller/reader/writer trace, boundary vector,
original runtime observation, or a saved-state comparison. If it does not
reduce uncertainty, reassess target identity, readiness, timing, and harness
assumptions before repeating it.

## Evidence labels and promotion

Use the following labels in receipts and reports:

- `source-backed`: present in the cited reconstruction/source text;
- `binary-static`: decoded from the exact target bytes;
- `runtime-observed`: observed through the target's own interface or debugger;
- `oracle-compared`: independently compared against an authority not reusing the
  implementation algorithm;
- `inferred`: reasoned from evidence but not directly established;
- `guessed`: temporary blueprint hypothesis;
- `conflict`: competing claims remain live;
- `unknown`: the current evidence cannot answer the question;
- `false`: a prior hypothesis was disproved, with the decisive evidence retained.

A later label does not erase an earlier one. Promotion records the new evidence;
demotion records the counterexample. This keeps the forest path visible and
prevents a plausible draft from becoming an accidental specification.
