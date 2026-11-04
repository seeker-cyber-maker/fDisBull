# P00: Reproducible DOS source-intake comparison (2026-11-04)

**Status:** qualified *artifact inventory*, not qualified DOS runtime or recovered UIL. Experiment over **fDisBull 0.31.1** plus the narrow native Inno Setup 5.6.2 adapter in [draft !80](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/80). Source-only stage contracts follow [draft !79](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/79). **No original-game data, ROMs, installers, extracted executables, CD image or byte-retaining database is in this change.** This pilot is for the DOS target lane; it does not certify the engine/VM, game parity, or a real emulator session.

## Purpose and stage contract

**P00 Intake** should reliably answer: *Which exact original sources and exact derived members do we have? Which packaging layers contain them? Which duplicates are byte-identical? What remains unresolved?* It does not answer *what the code means* or *how to launch/play the game*.

Input: explicitly supplied game installers or a directly supplied DOS COM/MZ fixture, with user-declared edition label, private extraction root, source identities and a supported adapter. Output: immutable source SHA-256, source/container roles, extracted member hashes, nested primary ISO 9660 file identities, suspected executable format **candidates**, and a public aggregate companion. The private receipt retains file paths and digests; the public receipt omits those paths and payload bytes. Unsupported formats, changed sources, missing/extra files, corrupt hashes, unsafe paths or ambiguous reads must refuse.

P00 substeps (implemented in this study, not registered production APIs): **Identify** (source hash/profile) → **Extract or Reverify** (manifest and 667 file SHA-256 identities) → **Classify** (distribution support vs. candidate game materials, MZ/COM/NE/PE header only) → **Unwrap** (nested raw Mode-1 discs via fDisBull's bounded `disc-inspect`, then separate streaming user-data hashing) → **Reconcile** (content hash-based duplicates and differing files) → **Seal** (private identity receipt + sanitized public aggregate). The direct-COM control enters through Identify/Classify/Seal without an installer decoder.

## Supported samples and observed results

| Measurement | Castles 1.03 DLC | Castles II 1.0 | Alone in the Dark 1.0 CS | Authored DOS control |
|---|---:|---:|---:|---:|
| Source bytes | 47,589,832 | 519,724,704 | 312,547,608 | 15 |
| GOG extracted files | **190** | **259** | **218** | Not applicable |
| Candidate game files (loose) | 59 | 123 | 88 | 1 |
| Distribution support files | 129 | 134 | 129 | 0 |
| Main nested raw CD | None | `C2CD.gog` | `GAME.GOG` | None |
| Nested primary ISO files | 0 | **455** | **1,564** | 0 |
| Nested primary ISO directories | 0 | 6 | 3 | 0 |
| Nested file content reuses in loose extraction | N/A | 5 | 80 | N/A |
| Exact-path nested content mismatches | N/A | 0 | 2 | N/A |
| All selected identities checked | Yes | Yes | Yes | Yes |

Raw disc image sizes: Castles II **748,686,288 bytes**, volume `C2CD`, primary tree 461 entries; AITD **353,924,256 bytes**, volume `ALONECD`, primary tree 1,567 entries. The primary metadata trees passed the actual fDisBull 0.31.1 `disc-inspect` validity/completeness checks, while an additional independent study-only stream computed SHA-256 for every **2,019** nested ISO file. These hashes prove observed byte identity; there is no independent expected per-disc-file checksum oracle and no claimed full physical-disc or game semantics validation.

Unclassified physical tails beyond the ISO volume: **10,893 further 2,352-byte sector positions** on `C2CD.gog` and **126,011** on `GAME.GOG`. Their *actual physical-sector framing and track identity were not verified*. They might contain audio or other material; no CUE/track attribution, CDDA playback, EDC/ECC checking, or hidden-track proof was performed. **Do not call the two discs complete multimedia extractions.**

The game-candidate pool comprises 59, 578 (=123 loose +455 CD) and 1,652 (=88 loose +1,564 CD) scoped member records. Within those pools, exact content SHA-256 identities number **59, 522 and 1,560** respectively, **after collapsing same-byte duplicates**. Across the *three games' candidate pools*, no identical SHA-256 hashes were found. That's a byte-reuse result, **not** a claim that no code contracts or ISA semantics can be shared.

### Launch/runtime *candidates*, not qualifications

- **Castles:** three loose DOS MZ candidates; its included `CASTLES.BAT` invokes `CASINT.EXE` and then `CASTLES1.EXE`. The big GOG Game Configurator is *distribution support*, not evidence of a 38 MB original game engine.
- **Castles II:** one loose DOS MZ candidate, `C2CDTOOL.EXE`. Its `C2CD.BAT` repeatedly calls that program and branches on error levels; most large game/media payloads live in the CD image. The CD's primary tree contains no separately named game `.EXE` (one `SND.BAT` is present). This distinction belongs in P01's environment/runtime lock.
- **AITD:** the package contains DOS MZ executables `INDARK/INDARK.EXE` and `JACK/INDARK2.EXE` and several COM drivers, as well as Win16 setup programs and a separate Win32 `FITD.exe`. Treat `JACK` as distinct target/edition lineage; do not blend it into AITD's original DOS behavioral oracle. The CD's ISO tree includes 1,439 `.VOC` audio files. For the held-out AITD challenge, **only P00 source/container facts were inspected**; no Life/PAK script interpretation or runtime route was used.
- **Control:** the previously authored 15-byte `HELLO.COM` is a direct artifact, not a GOG installer or a game. It verifies that a *non-Inno DOS source* can enter the same identity/receipt boundary. It is excluded from game-complexity rankings.

## Reproducibility and measured costs

Exact private inputs and all extracted output files were preserved; no installer or DOS game was executed. Original byte hashes and content identities were recomputed across **three complete, repeatable P00 verification runs** on the same filesystem. After removing timing measurements, all output receipts were **identical within each target**. The authored negative/contract suite passed **20/20 tests**, including altered files, extra files, symlinks, unsafe paths, wrong/unknown executable formats and malformed raw Mode-1 sectors.

| P00 median of three warm-cache runs (seconds) | Castles | Castles II | AITD |
|---|---:|---:|---:|
| Source / extracted-member verification | 0.171 | 1.687 | 0.993 |
| Nested ISO metadata + file hashing | 0.000 | 1.266 | 0.326 |
| Total including classification | 0.172 | 2.984 | 1.321 |

**Caution:** these are three warm-cache, single-host runs, not general performance forecasts. The original first full native extractions separately took **0.898, 9.992 and 5.376 seconds** (one run each), including file materialization. The run-metric components are descriptive and may differ from summed medians due to noise and rounding. The cached recheck was deliberately not permitted to trust filenames, file sizes or mtimes instead of content hashes.

## Optimizing P00 independently (before P01)

1. **Keep correct by default:** fDisBull's actual source profile, checksum, nested extent and path guards remain non-negotiable. A valid ISO filesystem is separate from its track layout and file contents.
2. **Split cost centres:** distinguish initial extraction from repeated rehash, nested ISO scan, file roles, and report delivery. Castles II is currently the high-work case because the large CD image and its contents are hashed separately.
3. **Safe reuse experiment:** a content-addressed, immutable private object store can reuse sealed file/nested member receipts when its **source SHA, adapter revision, image identity, profile and transitive dependencies** match. A mutable output directory must still be reverified. Measure cache hit rate and invalidation with one-byte source/child corruption, altered ISO extent and competing output paths; no hash skipping from an arbitrary mtime.
4. **Gap recording:** do not silently treat opaque media as fully decoded; retain the unexplored physical tails as explicit P00 unknowns. Do not infer semantics or original-game equivalence from exact byte copies.
5. **Acceptance gate:** same frozen inputs produce the same normalized full receipt and public aggregate; all expected files are present with identical hashes; negative fixtures refuse; no user-private payload bytes enter Git or release packages.

## Next gate: P01 Lock

With P00 frozen, a second phase can choose a **reusable DOS-x86 environment package**, a **16-bit x86 ISA package**, and exact **target/edition/boot-route** bindings. The P01 experiment should first lock Castles II's DOSBox CD/media and batched `C2CDTOOL` launch, compare it against Castles' DOS startup, then probe AITD only with a frozen held-out scope. Native game/BIOS runs, clock/input policies and engine-specific VM profiles are **not part of this P00 result**.

## Source identities, reproducibility and attribution

- fDisBull core wheel: `fdisbull-0.31.1-py3-none-any.whl`, SHA-256 `03bf5142aab0a9448c73b38c986ddeef92f68eab2630f6f1ef4842bb2364bf33` (v0.31.1).
- Native GOG adapter: [draft !80](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/80) at `9e2c4a2a6317a64d2971eea39e1e0e8ae91953ef`; this experiment uses its native Python reader in an isolated 0.31.1 overlay.
- P00 study-only script: `scripts/p00_dos_intake.py`, SHA-256 `34a25b3d555566612d33e34ad5e24cac0266e76a99820952f33a30a13cc891f2`.
- Qualifying test suite: `tests/test_p00_dos_intake.py`, SHA-256 `f11e531270e2e5421ec168c75e88a0f877c247fd89214bf9013ea79c15ca2d5c`.
- Target installer source SHA-256 values (exact, not guessed by filename):
  - Castles: `6ae0653632e518adc5e3e7762c182b2846ed112113797555d2d44026392a5529`.
  - Castles II: `d09debb49922e7e5ac83a5c9dc160053cc10599560d9525317a3925dbbadfe56`.
  - AITD: `615904e894c3cc4312869156b452816402e7611ccd5d6480cc29a8fa09bc1394`.
- The public aggregate JSON accompanying this report contains **no private installer path, extracted member inventory or executable/game bytes**. Source archive and actual private manifests are held separately; this report does not claim a public delivery of the licensed material.

**Relationship to other active work:** [!65](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/65) owns reusable OS/ISA/target package hierarchy; [!77](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/77) owns format/media catalog intake; [!80](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/80) owns Inno decoding; [!79](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/79) owns the phase contract inventory. This result is **P00-specific** and does not merge or supersede other agent work.