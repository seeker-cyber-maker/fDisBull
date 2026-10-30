# Civilization I: reverse-engineering and patch leads

Research notes captured 2026-10-30 from the [My Abandonware Civilization page](https://www.myabandonware.com/game/sid-meier-s-civilization-1nj). These are **external claims and catalog descriptions**, not fDisBull observations or verified equivalence. No game files, patches, or binaries were obtained or committed.

## Civ64: author's reported method

In comments dated 2026-10-18 and 2026-10-24 on the source page, Buyukcaglar describes [Civ64](https://github.com/Buyukcaglar/Civ64), a native 64-bit port of the Windows 3.1 game. The author says the original machine code was reverse-engineered and ported function by function, with Anthropic's Claude assisting under their direction and the result tested by them. They claim the original rules, AI, map generator and save compatibility were retained. The later comment describes Windows and macOS builds, and says portable C/SDL 3 source was planned. It also says an independently obtained Windows copy is required and no game files are included.

These comments do not describe the full pipeline, coverage, or equivalence tests. A function-by-function port does not by itself establish whole-game equivalence. Check the [project](https://github.com/Buyukcaglar/Civ64), [releases](https://github.com/Buyukcaglar/Civ64/releases/latest), and [user guide](https://github.com/Buyukcaglar/Civ64/blob/main/docs/USER-GUIDE.md) for current status before relying on these historical statements.

## Patch and edition catalog

The source page describes these DOS patches:

| Listing | Page's description |
| --- | --- |
| 474.03, dated 1992-04-01 | Error and balance corrections; city renaming among additions. |
| 474.04, dated 1992-07-21 | Page says to install after patch 3.0. |
| 474.05, dated 1992-10-13 | Page says it fixes an advisor hover bug; listed patch is a beta and the final version did not work. |

The download list separately labels an English 474.03 patch “Patch 3.0,” an English 474.04 patch “Patch 3.0,” and an English 474.05 beta “Patch 5.0.” Preserve that apparent naming inconsistency as an open question; inspect the actual patch packages and their instructions before assuming their order or applicability.

Other listed extras include an OPL-3/General MIDI sound update, an official Sound Blaster Pro / Pro Audio Spectrum sound patch, English manuals and technical supplements, a tech tree and an official guide. The Windows 3.x section lists a 1.2 patch, a DOS tiles patch, a manual and a technical supplement. The page lists several DOS editions, including 474.01, 474.03, 474.04 and 475.01; language and distribution differ. Catalog labels alone do not establish binary identity or patch compatibility.

## Debugger lead

A 2026-09-27 comment by devback claims a DOS treasury value can be inspected and edited using DOSBox-X at `32A3:B1D8`, with a 16-bit little-endian value. The comment's wording about its byte position is ambiguous. This address is an unverified lead, not a portable offset: executable version, load segment, game state and runtime configuration may change its meaning.

## Follow-up experiments

1. Obtain authorized copies and patches separately; keep original game files and byte-retaining databases outside Git.
2. Record edition, language, file hashes, executable format, patch origin and instructions. Compare pre/post-patch files and identify changed code and data, without assuming labels prove ancestry.
3. In a controlled DOS session, compare treasury values across distinct states and restarts, resolve the active segment and use a bounded watchpoint to identify writers. Record negative results and version-specific conditions.
4. For Civ64, inspect its published documentation and any available source or release evidence. Test a small set of deterministic, version-matched scenarios and save exchanges before making compatibility claims.
5. Keep external reports, hypotheses, static evidence and native observations distinct; report unsupported behavior as unknown.
