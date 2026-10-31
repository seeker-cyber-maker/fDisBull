# Civ city-screen blueprint slice

Slice ID: `CIV-UI-001`

Status: **draft blueprint; not a qualified UI or UDC claim**.

This is the first UI-oriented slice after the signed city-production contract.
It uses the existing Civ64 DOS scene record and civd city/production
implementations to lay out a narrow route. It intentionally stops before
claiming that fDisBull has recovered or executed the original DOS screen.

## Question

What is the smallest evidence path from a city action to the DOS city screen's
production state, and which visible controls can be bound to the already
qualified `civ.city.shield-completion` semantic slice?

## Edition and conflict gate

The local authorities use different release labels for the same packed-file
identity:

| Authority | Label | File identity | Status |
|---|---|---|---|
| civd `main` | DOS 474.05 | `CIV.EXE`, 305,030 bytes, SHA-256 `22de2748e3089793644c7e501e2a95b553010ddec34a7ff42f4395cf779c9c2a` | source-backed reconstruction and pinned build |
| Civ64 DOS extension | DOS 475.05; `INTRO.TXT` may say 475.01 | `CIV.EXE`, 305,030 bytes, SHA-256 prefix `22de2748` | DOS-listing model and asset/scene documentation |

The matching hash is strong identity evidence, but the release-number mismatch
is not silently resolved here. It is `CIV-EDITION-001`, a priority conflict to
close before treating a DOS UI claim as edition-qualified. The current city
production implementation remains source-backed by civd under its declared
contract; this slice does not broaden that claim to every Civ64 DOS scene.

## Authorities used

1. **civd city model**
   - `book/src/city/production.md`: `civ_economy()` calls
     `city_process(city, 0L)`; `CITYMGT.C` contains both turn processing and the
     interactive city screen, selected by `mode`.
   - `book/src/city/city_struct.md`: 128 records at DGROUP `0x70ec`, 28 bytes
     each; `food_box` at `0x0c`, signed `shield_box` at `0x0e`, `production` at
     `0x09`, `size` at `0x07`, `owner` at `0x0b`, and `name_id` at `0x16`.
   - `src/CITYMGT.C`: the source reset, signed shield accumulation, completion,
     production retargeting, and human/AI completion branches.

2. **Civ64 DOS scene record**
   - `docs/dos/SCENES-PLAY.md`, section 7.1: DOS city screen routine
     `R:0D12:0045(city, mode)`, its callers, layout, inputs, transition to the
     city-view overlay, and Windows counterpart names.
   - The record labels geometry and behavior as **DOS listing**, with inferred
     Windows counterparts kept separate.

3. **fDisBull static route probe**
   - Original Win16 target source SHA-256:
     `a66ec64020f10adb81613964f3d08a11ea278b6a5a060c8e49d1ea1fd3ba1788`.
   - An isolated copy of the existing NE project was traversed with the active
     fDisBull 0.26.1 interpreter, using the numeric packed address `0x140000`
     corresponding to the current candidate segment/offset seed.
   - The traversal decoded 277 instructions and 618 new facts, with 5 pending
     code entries remaining. The stored analysis is `stable=false` with 24
     issues. The seeded function is `sub_140000`, not a proven `ProcessCity`
     symbol. Its far calls remain unresolved (`0:0FFFFh` in the retained
     instruction view).

The static route probe is therefore useful navigation evidence, not a semantic
or UI proof. The first attempted CLI spelling, `--start ne:20:0x0`, was rejected
by the 0.26.1 command parser; the accepted numeric identity was `0x140000`. That
interface friction is recorded separately rather than hidden.

## Draft state model

The city screen can be represented as a state projection over one `townbuf`
record plus map/asset state:

| State | Current evidence | Status |
|---|---|---|
| city identity/name | civd `name_id` and Civ64 title `name (Pop:n)` | source-backed plus DOS-listing model |
| population | civd `size`; Civ64 title and citizen row | source-backed plus DOS-listing model |
| production choice | civd non-negative unit ID or negative improvement ID | source-backed |
| stored food | civd `food_box`; Civ64 food-box region | source-backed plus DOS-listing model |
| stored shields | qualified signed `shield_box` contract | qualified semantic slice |
| required shields | caller-computed cost times scale | qualified contract input; cost lookup outside slice |
| worked map | 21-square city-centered map, worked-square outlines | DOS-listing model |
| supported units | city-record/garrison and unit-panel evidence | candidate; unit projection not yet qualified |
| improvements | bitmask and page-2 icon list | source-backed record, UI binding candidate |
| production controls | `CHANGE`, `BUY`, `RENAME`, `EXIT`, plus keyboard shortcuts | DOS-listing model; dispatch not yet verified in fDisBull |
| tabs | `INFO`, `HAPPY`, `MAP`, `VIEW` | DOS-listing model; action readiness unknown |

## Geometry blueprint

Logical DOS coordinates are 320x200. The current scene record gives the
following candidate object identities:

| Object | Rectangle / anchor | Action or projection | Status |
|---|---|---|---|
| Header | `(2,1)-(208,21)` | title and citizens | DOS-listing model |
| Resources | `(2,23)-(124,65)` | food, shields, trade, luxury/tax/science rows | DOS-listing model |
| City map | `(127,23)-(208,104)` | 21 squares centered on the city; worked outlines | DOS-listing model |
| Supported units | `(2,67)-(124,104)` | unit/garrison projection | DOS-listing model |
| Food box | from `(2,106)` | food storage projection | DOS-listing model; height rule partly read |
| Tabs | y `106..114`, x from 95 | `INFO`, `HAPPY`, `MAP`, `VIEW` | DOS-listing model; ready/enabled unknown |
| Improvements | `(211,1)-(317,97)` | six-pixel rows and `MORE` | DOS-listing model |
| Production box | from `(230,99)` | `CHANGE`, `BUY`, production state | DOS-listing model; semantic binding partial |
| Rename | `(231,190)-(272,198)` | city-name action | DOS-listing model; dispatch unknown |
| Exit | `(284,190)-(316,198)` | leave city screen | DOS-listing model; ordinary route unknown |

`VIEW` is documented as calling `O19:0000(city, -1)`. The city-view overlay is
kept as a separate future slice because its 19x12 seeded grid, asset placement,
palette, timing, and exit route have different evidence and state boundaries.

## Decision tree

```text
Q: can the production box be bound to qualified shield completion?
├─ H1: city-screen state reads the same townbuf shield_box and production fields
│  ├─ verify static field reads/writers in the DOS root/overlay or Win16 target
│  ├─ compare the screen's displayed values with a controlled state change
│  └─ promote only if the field offsets and transition agree
├─ H2: the UI displays a derived/cached value with a different update boundary
│  ├─ trace the first writer and the screen refresh boundary
│  └─ keep display state separate from committed townbuf state
└─ H3: Civ64's DOS scene and civd source refer to different releases
   ├─ resolve exact `CIV.EXE` hash/version before merging claims
   └─ keep the conflict open and do not qualify the UI binding
```

Stopping condition: one hypothesis has a format-aware address path, an
independent state/display check, and a reproducible action or the route is
explicitly recorded as unresolved. A successful screenshot alone is
insufficient.

## Next probes, in order

1. **Resolve `CIV-EDITION-001`.** Verify the supplied raw DOS image's full hash
   and release metadata, then compare the Civ64 DOS listing target with civd's
   474.05 pinned build. Do not use the Windows NE file for this question.
2. **Import the DOS target through the active fDisBull 0.26.1 DOS profile.**
   Confirm MZ/EXEPACK/root/overlay identity before using `R:0D12` addresses.
3. **Trace the city route.** Start from a verified caller or overlay entry and
   follow reads/writes of the city record fields through the city-screen routine
   and the `CHANGE`/`BUY`/`VIEW` dispatches.
4. **Use runtime only if the matching DOS input/backend is staged.** Drive the
   ordinary city action, capture a baseline and one controlled change, and
   distinguish visible, ready, enabled, committed, and persisted results.
5. **Only then extend UIL/UDC.** Add a UI/state layer that references the
   already-qualified production contract; do not encode the current geometry
   draft as executable behavior yet.

## Release boundary

This document does not add a UI implementation or change the release gate for
`CIV-PROD-001`. It is a temporary blueprint and decision tree. Its guessed,
candidate, conflict, and unknown rows remain out of release until the probes
above qualify them independently.
