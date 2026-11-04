---
name: dos-target-media-rip
description: Prepare compact private DOS analysis targets using catalog-first batch or single-game intake, format-aware media framing, companion indexes and decoder/runtime validation while preserving original executables. Use for target intake and media rips, not ordinary video editing or executable patching.
---

# Compact DOS analysis targets

Keep original executable bytes and source provenance while reducing storage spent
on disc overhead, duplicated audio and selected nonessential animation. Header
recognition, structural parsing, complete decoding and original-game playback
are separate results.

## Start with catalog-backed intake

Use the caller-selected fDisBull executable. Check its `--help` for
`intake-inventory`, `format-modules` and `file-identify`; use an explicitly supplied
candidate when needed. Updating a shared installation is a separate action.

```text
fdisbull format-modules --catalog /private/formats.sqlite
fdisbull intake-inventory /private/game --catalog /private/formats.sqlite
fdisbull intake-inventory /private/game-a /private/game-b --catalog /private/formats.sqlite
fdisbull file-identify /private/selected-file --catalog /private/formats.sqlite
```

Batch and single-game intake use the same per-file checks. Read
[catalog intake and recovery](references/catalog-intake.md) for report scope,
unsupported-format routing, archive boundaries and FLI/game-specific variants.
Inspect the available modules before web research or writing another parser.
A filename suffix and a header-only module do not authorize media rewriting.

Preserve the source archive/installer and its full hash; sampled identities from
intake are not whole-file hashes. Identify actual game programs and hash them
before and after any media work. Prefer links and copy-on-write working trees
over repeated large disc copies. Never patch an executable to compensate for a
media edit. Follow the caller's storage and placement rules, including explicit
task-scoped overrides; tool read/output budgets are not storage authorization.

## Select a qualified media route

- **Unknown, unsupported or malformed input:** keep it unchanged, retain its
  recovery-queue entry and qualify the missing format/profile first. A partial
  inventory or unreadable source is not a complete intake.
- **ISO, raw BIN/GOG, CUE or mixed-mode disc:** read
  [disc and audio handling](references/disc-audio.md). Inspect the volume directly
  before extracting it. The bundled helper inventories ordinary ISO9660 from
  ISO/2048 or MODE1/2352 and can create a verified data-only ISO:

  ```bash
  python3 scripts/disc_data_track.py SOURCE --report REPORT.json
  python3 scripts/disc_data_track.py SOURCE --iso NEW.iso --report REPORT.json
  ```

  Run bundled helper commands from this skill directory or use its absolute
  helper path. Paths are caller-selected. Existing ISO outputs and unsupported layouts refuse.
  For a mixed-mode disc, `--data-sectors N` preserves a verified complete data-track
  sector count, including MODE1 padding beyond the ISO volume. Derive N from the
  original CUE so following audio tracks keep their absolute positions; never use
  an arbitrary whole-BIN sector count. This helper does not rip audio or rebuild
  arbitrary filesystems.
- **Native SMK2 cinematics:** read
  [Smacker framing](references/smacker.md) and use `media-inspect --adapter smacker`
  followed by `smk-frame`. Unsupported profiles refuse. Preserve original audio,
  logical frames and duration; qualify original-game consumption separately.
- **Old Interplay MVE or Castles II SLB:** read
  [MVE framing and SLB playback](references/mve-slb.md). Preserve codec family,
  original chunk-size bounds, audio and explicit ending-reference recovery;
  SLB timing uses a recovered consumer profile, not guessed kHz.
- **Coktel IMD in ITK/LTK:** read
  [format-aware framing](references/imd-itk-ltk.md). Recover and rebuild every
  linked archive/index/cache. The established Italian CD profile does not qualify
  every floppy or localized variant.
- **FLI/FLC or game-specific sprites, pictures, sound and music:** use the actual
  catalog profile and its scoped reader. DinoPark ACT/PIC/ABT/XMID resources are
  separate formats, not standard FLI. Header recognition or extraction is not a
  qualified animation rewrite. Inspect dependencies and consumers before changes.
- **Ordinary small game data:** retain it. An executable-only analysis ZIP can
  omit media without changing the working game's resources.

## Transform and qualify selected movies

Inventory sizes, logical frames, codecs and script references before selecting
nonessential cinematics. Prefer conservative framing: preserve geometry, palette,
frame numbering, useful opening/final imagery and native hold records. For delta
formats, keep the last independent full frame and all following deltas needed to
reproduce the ending. Frame preservation can retain the original wait time.

Rebuild all affected lengths, offsets, cached headers and companion indexes.
Renaming a file, arbitrary truncation or an unrelated modern codec does not
establish validity in the original decoder. Leave interactive, inventory,
subrectangle and unexplained assets unchanged until their usage is understood.

Keep a manifest of source/derived identities, retained frame positions, the
transformation and companion updates. Completely decode original and derived
media with a compatible independent reader. Compare promised pixels, palettes,
frame counts, audio samples and timing. A native check must consume the exact
changed media and demonstrate completion, not just open its filename. Label
prepared-state assistance and keep seeking, audible output, return paths and
whole-game behavior separate from decoder success.

## Delivery and roster maintenance

Keep one canonical source, a minimal working layout, a separate derived-media
layer and concise receipts. Share a full compressed audio working track by
relative symlink when the backend supports it; preserve source audio and CD
layout/timing. Keep licensed programs, media, states, databases and archives out
of public source repositories and tool packages. Do not follow cyclic runtime
aliases such as `SWARS -> .` while archiving.

For the private package at
`/Volumes/CODEX/Codex_Projects/fDisBull-targets-private`, run from that directory
after each executable-roster addition:

```bash
python3 tools/update_target_executables.py
python3 tools/update_target_executables.py --check
```

The ZIP contains original selected programs, not installers, disc images or
movies. Review unusual guest-code selections in `EXECUTABLE-ROSTER-CONFIG.json`.
For a media-only layer, check executable/archive integrity without inventing a
new program version. Package-local `AGENTS.md` owns its maintenance contract;
other projects use their own equivalent commands.

Retain inventory coverage, recovery gaps and decoded/native scope with the
variant. Earlier receipts remain dated evidence. Lost in Time's single-movie
example does not establish a full reduced-game playthrough; Syndicate Wars'
prepared ending tests do not establish campaign or credits compatibility.
