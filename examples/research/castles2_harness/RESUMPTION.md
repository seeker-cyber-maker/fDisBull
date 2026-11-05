# Resumed Castles II harness: observable restoration, not merely a green map

Date: 2026-11-04. This follow-up preserves the earlier experiment and corrects its automation claim. The earlier 16-second runs are evidence for their recorded script and broad screen checks, not strong automated proof of state restoration.

## What the resumed experiment found

The original `OPTS` tab is a toggle. Entering an action with Options already open can close it, causing later fixed-coordinate clicks and typed filenames to miss their intended control. The old `save()` refused when no file appeared; this failure was retained.

More importantly, the old `load()` can report success while still in a dialog, because the left-hand green map remains visible. In this reproduction, a Load dialog, an advanced-date map and a restored-date map all scored **0.87109375** under the old green-map classifier. The saved file remaining unchanged also does not prove it was read. These are harness assertion weaknesses, not evidence of a broken game.

## Stronger original-game result

A manual diagnostic saved a visible **May 13, 1312**, observed the game advance to **May 19, 1312**, then confirmed the actual Load Game dialog and loaded the saved file. The original display returned to **May 13, 1312**, both in-session and in a fresh emulator process. The 11,733-byte save was unchanged. A selected gold-glyph mask matched; no OCR, guessed save-layout parser or guest-memory edit was used.

The right-hand panel also slides vertically while redrawing. Raw rectangle hashes therefore differed despite identical date text. `state_checks.py` trims translation within a fixed, edition-bound date region before comparing glyph shape, and includes a changed-glyph negative control. This proves only the selected visible date, not all game state.

## Reusable guarded route

`guarded_c2_probe.py` uses the existing real DOSBox-X/XTest harness but waits for specific, source-qualified panel fingerprints. It reuses already-open Options rather than toggling, waits for Save/Load dialogs, waits for the returned stock/date panel, and requires saved date restoration.

Each complete replay deliberately begins Save with Options already open; creates a fresh save; lets the visible date change; rejects that actual changed state as an omitted-load negative; loads and verifies the original date; restarts DOSBox; and loads/verifies again.

| Fresh private copy | Full guarded replay | Result |
|---|---:|---|
| 1 | 26.196 seconds | All declared checks passed |
| 2 | 29.493 seconds | All declared checks passed |

The source suite passes **21 tests**: the original 12 plus nine new image/negative controls. All owned emulator and Xvfb processes were reaped. Shutdown remains host-forced, not a claimed clean DOS exit. Original `C2CDTOOL.EXE` hashes remained unchanged in the source and all three new working copies.

These timings include deliberate state advancement, readiness checks and two process starts. They are **replay times**, not cold-agent discovery/build times, and cannot be compared as a speed win/loss against the weaker old script. No independent current-skill versus !82 cold-agent A/B was performed. AITD remains behaviorally held out.

## Reproduction

Prepare a private source-correct working copy as described in the existing README, with its BAT selecting `startagain`. Use a new output directory and exactly one test save. From this source folder:

```sh
python -m unittest discover -s tests -v
python guarded_c2_probe.py --game-dir /private/castles2-copy \
  --backend /private/offline-kit/bin/dosbox \
  --output /private/guarded-run --display :109 --slot GUARD1
```

Choose an unused X display. GUI fingerprints are restricted to the exact admitted executable, language, 640x400 surface and palette. Unknown scenes refuse. The source package contains no original files, save payloads, screenshots or captured memory.

## Skill lesson

A learned action needs an entry condition, an observed completion condition and a discriminator against no effect. Record the reusable control only at that scope. Do not infer Load success from a map that remains visible behind the dialog. A longer correct test is preferable to a fast non-discriminating one.
