# DOS-to-Civ64 correspondence crosswalk

The public Civ64 corpus supplies a **Win16 NE correspondence table**, not a
PE64 source dump. The Windows addresses below are therefore the exact NE
addresses documented by Civ64, not guessed PE64 virtual addresses. The labels
and evidence wording are copied as a semantic crosswalk from
`docs/dos/CORRESPONDENCE.md`; they are not byte-equivalence claims.

## Evidence-labeled anchors

| # | DOS address/role | Civ64 Windows counterpart | Label in Civ64 docs | Use in this project | Byte status |
| ---: | --- | --- | --- | --- | --- |
| 1 | `R:1AEA:03BA` city layer | `DrawMapTile 1110:04D0` city marker | proved | city overlay/UI | unresolved |
| 2 | `R:0D12:0045` city screen | `ProcessCity 1030:0000`, `DrawCityScreenTitle 1030:8B39`, `CityScreenWndProc 1030:9C17`, `ShowCityScreen 1170:05AF` | proved | city screen boundary | unresolved |
| 3 | `R:0D12:7045` building icons | `DrawImprovementIcon 1030:8529`, `DrawImprovementIconLogical 1030:84BE` | proved | improvement presentation | unresolved |
| 4 | `R:0D12:710D` city panel background | `DrawCityPanelBox 1030:895C` | inferred | city panel frame | unresolved |
| 5 | `R:1F4D:04F7` truncate to width | `TruncateStringToLogicalWidth 11D0:02E4` | inferred | city-name presentation | unresolved |
| 6 | `R:1459:08C6` city name | `AppendCityName 1038:0BBA` | inferred | city labels | unresolved |
| 7 | `R:0ADE:03EA`, `R:0ADE:0093`, `R:1459:0597` city callers | `ShowCityScreen 1170:05AF` and ProcessCity callers | inferred | caller graph | unresolved |
| 8 | `O19:0000` city view | `ShowCityView 11B0:0000` | proved | city-view transition | unresolved |
| 9 | `O19:13A1..145F` houses/roads and `O19:14FB..1536` buildings | `LoadCityViewSprites 11B0:1653` | proved | city-view resources | unresolved |
| 10 | `POP.PIC` citizens | `DrawCityViewCitizens 11B0:1316` | inferred | population projection | unresolved |
| 11 | `O19:167B` invaders | `PlayCityCaptureAnimation 11B0:1B63` | proved | capture animation | unresolved |
| 12 | `O19:18C1` civil disorder | `PlayCivilDisorderAnimation 11B0:1FAC` | proved | disorder animation | unresolved |
| 13 | `O19:1AE1` celebration | `PlayCelebrationAnimation 11B0:237C` | proved | celebration animation | unresolved |
| 14 | `O22:0EAF` city founded | `ShowCityFoundedAnimation 11B8:14E5` | proved | founding flow | unresolved |
| 15 | `R:0ADE:0421` production menu | `ChooseCityProduction 1170:05CA` | inferred | production choice UI | unresolved |
| 16 | `O20:0540` disasters and city events | `ProcessCityDisaster 1040:068E` | proved | city event boundary | unresolved |
| 17 | `O20:047C` founding caller | `FoundCity 1040:0000` | inferred | founding state transition | unresolved |
| 18 | `R:0238:107E` status panel | `DrawStatusCivPanels 1088:13D5`, `RedrawStatusWindow 1218:0801` | proved | tax/science/luxury projection | unresolved |
| 19 | `R:0403:35CE`, `R:0403:36B9` rate menus | `MoveCivUnits 11F0:3BF5..3E7A` | proved | rate-selection UI | unresolved |
| 20 | `R:1DC4:02CD` population | `ComputeCivPopulation 11C8:0334` | inferred | population display | unresolved |
| 21 | `R:0403:4060` unit panel | `DrawUnitInfoPanel 11F0:468C` | proved | city-adjacent unit display | unresolved |

The first 17 anchors are the Civ64 city section; anchors 18–21 are the
city-adjacent economy/status surfaces used to scope the first UIL expansion.

## Address-resolution pass (2026-10-31)

`examples/civ/civ_exe_atlas.py` parsed `CIV.MAP` and the 42 `*.COD` listings and
resolved all 21 DOS addresses to the civd function that contains them:
15 at a function entry and 6 inside a function. The per-row result is in
[CIV_EXE_ATLAS.md](CIV_EXE_ATLAS.md#civ64-anchor-resolution).

This pass changes the **address** status, not the byte-equivalence status. It
proves that each DOS anchor lands in a named, map-verified function; it does not
pair that range with a Windows/PE64 range. The table's byte-verification count
therefore remains **0/21**.

## Why byte verification is still open

The exact DOS target available locally is the packed 305,030-byte
`CIV.EXE`, SHA-256
`22de2748e3089793644c7e501e2a95b553010ddec34a7ff42f4395cf779c9c2a`. Civ64's
own `EXECUTABLE.md` says that its address listings were generated from a
separate `CIV_UNP.EXE` whose load module is byte-equal to the unpacked runtime
image and whose file also carries the overlays. That unpacked input is not in
the local intake. The PE64 intake contains `civ64.exe` but no reconstructed
source or symbol map that turns the NE addresses into PE64 virtual addresses.

Consequently the reproducible byte-verification count for this table is
**0/21**. A future pass can promote rows only after it records, for each row:

1. the authenticated DOS file/overlay byte range and decoded instruction span;
2. the authenticated PE64 virtual/file range and decoded instruction span;
3. a compiler/port invariant stronger than role similarity; and
4. the comparison result, including a refusal when the generated code differs.

The Civ production UDC intentionally uses `sjmelia/civd` source and its
technical book as the DOS semantic authority. Civ64's table narrows the UI and
call-boundary correspondence, but does not silently supply missing PE64 code.
