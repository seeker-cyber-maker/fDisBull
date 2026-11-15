# Civilization repository intake

This receipt records the source boundaries used by the first executable city
production slice. It is evidence, not a claim that the complete DOS game has
been reconstructed.

## Public repositories and PRs

- `Buyukcaglar/Civ64` was checked at local intake commit
  `4e46572d727544722d90c24dc2ce51a9c6d22f15` (release 1.2.5). The GitHub PR
  listing for all states returned **zero pull requests**, so there were no
  Civ64 PR bodies to read. The repository has one main line and no published
  reconstructed C source.
- The Civ64 technical material that is available locally was read from
  `docs/README.md`, `docs/dos/EXECUTABLE.md`, `docs/dos/CORRESPONDENCE.md`,
  `docs/dos/OFFSETS.md`, `docs/dos/FORMATS.md`, `docs/dos/DOS-PROFILE.md`,
  scene/timing/driver documents, and the public issue metadata. It explicitly
  says that the recovered C is a reading aid, not a buildable source release.
- The fDisBull GitHub PR inventory returned **47 PRs**. The executable
  Rosetta/UDL/UIL/UDC specifications and Civilization research were read from
  PRs #29, #38, #39, #40, #42, and #47, with the remaining PRs indexed by
  title/state. The relevant contract decisions are preserved in
  `docs/INTERACTION_IL.md`, `docs/UDC_LINUX_AND_C.md`, and the selected-shell
  capsules rather than copied into a second format.

## Local Civd intake

`/Volumes/CODEX/Codex_Projects/Civd-intake` is present. The main repository is
its 474.05 reconstruction; its `VERSIONS.md` and `civ.sha256` identify
`CIV.EXE` as:

- size: 305,030 bytes;
- SHA-256:
  `22de2748e3089793644c7e501e2a95b553010ddec34a7ff42f4395cf779c9c2a`;
- civd repository commit observed locally: `d9214fcd36aa6003d28aae60c3974b665f752280`;
  the static-intake metadata separately records fDisBull source commit
  `2b8d4db9fda90edc11dfedf77b8acab1e4d1474c`.

The same intake contains 474.01 and 474.03 source branches, three static fdb
snapshots, and a runtime readback. The `book/` technical documentation and
`src/CITYMGT.C` are the DOS authority used by
`docs/CIV_PRODUCTION_UDC.md`.

## Binary boundary

The Civ64 PE64 intake contains `civ64.exe` with SHA-256
`99dc7c589f85c82c565f9a1b5a2edf9dfe7773d30ed7e8b4b7f906b77e5a079d`. The local
Civ64 static fdb is bounded and candidate-oriented; it is not a source dump or
runtime proof. The local Civd/DOS executable and the Civ64 documentation both
identify the DOS executable hash above, but Civ64's public documentation does
not provide 64-bit code snippets that can be copied into a compiler.

Therefore the first UDC uses the exact civd C rule as its semantic authority
and uses Civ64's correspondence tables as a secondary cross-check. It does not
claim PE64 function equivalence where the public corpus supplies only an
inferred Windows counterpart. A future byte/function correspondence must bind
explicit PE64 addresses and complete analysis evidence before replacing this
boundary.

## fDisBull observation

A disposable fDisBull project imported the pinned DOS `CIV.EXE`. Its bounded
entry traversal decoded 17 instructions and reported a stable completed entry
because the input is an EXEPACK-packed root. Civ64's documentation says that
the original has 23 overlays and that the unpacked `CIV_UNP.EXE` is the
listing input; that unpacked file was not present in the local intake. This is
an explicit coverage limitation, not a reason to treat the 17-instruction root
as the whole game. The separate friction PR records the resulting UX issue
and the first compatibility-preserving improvement.
