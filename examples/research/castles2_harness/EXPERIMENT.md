# Castles II: recovered original-game loading and menu → Save → Load harness

**Date:** 2026-11-04. **Scope:** Original DOS interactive runtime, not an
original→UDL→UIL→UDC equivalence test. Original GOG game source was acquired
from the user's authorized upload and kept in private isolated test folders.

## Story, not an inventory dump

Castles II begins as a batch-driven supervisor. GOG's DOSBox configuration
mounts C: plus D: from `C2CD.ins`; its text CUE names one Mode1/2352 data track
and an audio track. `C2CD.BAT` starts `C2CDTOOL.EXE` with `firsttime` or
`startagain` and branches on DOS `ERRORLEVEL`, with additional tutorial modes.

The authentic initial route played a movie; the deliberately changed **private
copy** used the documented `startagain` argument to reach a working main menu.
By hovering and clicking in the original program, the first four menu icons
were labeled **Reference**, **Designs**, **Game Tutorial**, **Game**, and the
left-side buttons **Options**, **Quit**. The third icon exposed tutorial topics
including Basic Overview and Castle Building. The fourth opened game settings
such as Play as Albion, Difficulty: Easy, Plots: On, and **PLAY / LOAD**.

Loading with no file produced the original **No Saved Games** modal. Clicking
PLAY created an active green map. The `OPTS` tab on that map sits beside
`STOCK`, `ARMY`, and `RELAT`; it exposes **SAVE / LOAD / PAUSE**. Saving requires
a DOS filename. The real game created a 11,733-byte `TEST1.GAM` from the
manual exploration. After closing DOSBox and launching a different process,
opening Game→Load found TEST1; its returned map visibly restored the saved
**May 6, 1312** and score **4,345**.

This establishes a useful human/agent interaction path: the game accepts real
mouse clicks, typed names and persistence across DOS process restarts. It does
**not** establish why the game's resource loader uses any particular file, nor
whether the game's entire strategic state round-trips faithfully. A separate
manual-visible negative probe found Escape did not open a save menu in that
particular map state; no universal keyboard mapping was inferred. External
control references suggest right mouse may affect the clock, but that was not
proved here.

The 55-page GOG manual is scanned. Pages 35–36 (PDF pages 36–37) independently
place Options over the message window and describe Save/Load filename input.
That was read visually, not OCR. Its instructions were used to discriminate a
cheap button-location hypothesis, then verified with genuine original input.

## Actual measured runs (three independent disposable game copies)

| Replay | Initial menu | Save file | Same-process load | Fresh-process load | Full elapsed |
| --- | ---: | ---: | ---: | ---: | ---: |
| B | 4.096s | 8.552s | 10.782s | 16.180s | **16.191s** |
| C | 4.024s | 8.448s | 10.694s | 16.711s | **16.751s** |
| D, final pinned-source version | 4.026s | 8.496s | 10.746s | 16.197s | **16.208s** |

All three completed actual original guest Save/Load UI operations and returned a
map screenshot, with corresponding `.GAM` files intact and content-hash stable.
The image classifier detects *only* maroon menu versus green map; it is not a
trained recognizer, text decoder, scene ontology or a full state comparator.

**12/12** source-only synthetic tests passed. Three earlier live development
attempts failed on harness implementation errors; the fixes are documented in
README. Timing is wall time inside this sandbox, includes two DOSBox launches,
Xvfb and named-action replay, and excludes manual game discovery, coding, failed
iterations, original media extraction and narrative/report writing.

## What this says about skill optimization

The successful 16-second *replay* is not the time for an agent to **discover
controls and build** the harness. This conversation had one analyst with
cumulative history, not two independent cold agents. No causal "current main vs
!82" score can be computed from it. The error/debug cycle is part of the cost
and must remain in the benchmark denominator for cold agents.

The more important process result is the deterministic-first choice:
*read the available exact BAT/CUE/manual and previous !77 media research before
breaking on a guessed loader function*. Once the main menu was visible, probe
one icon or tab and capture the result before exploring another. Retain each
working action as a named handler. The smallest relevant probe often advances
faster than a broad decompiler session.

Draft !82 provides `z-controller`, `capture-action`, original-call capture and
formal operation goals, but **none of those PR-only methods were installed in
the v0.31.1 release used in these runs**. This test uses its real DOSBox-X
binary with Xvfb and an authored external Python named-action adapter. It shows
what can be automated over the original, not a performance claim for !82's
runtime or its skill. A proper controlled cold-agent comparison must hold the
runtime and original inputs constant and vary only the frozen skill bundle.

## Correct experimental comparison (not yet executed)

* **Arm A:** stock `main` fdisbull-investigate skill at pinned hash + installed
  v0.31.1 methods, identical private original source, source BAT/CUE and manual.
* **Arm B:** skill from draft !82 commit
  `04ce7880f779177b3a6096a70b482532cb3f047b`, but the **same v0.31.1
  runtime**, identical source, equal time/call budget and access to !77/!81.
  Suppress use of new !82 commands when unavailable from installed methods.
* **Isolation:** two fresh model-context workers, distinct private game copies,
  no path to the finished harness or run logs, separate X displays, single
  controller for each original guest; randomize arm order and repeat.
* **Identical objective:** establish exact four menu icon names; identify one
  valid mouse navigation path into active game, one no-saves refusal, manually
  create and reload a `.GAM` file, demonstrate fresh-process state adoption,
  then author a replayable named action layer with evidence and clean refusal.
* **Acceptance:** raw visual/source evidence must support actual claims;
  existing `C2CDTOOL.EXE` identity remains verified; Save file exists and is
  hash-retained; Game→Load works in new original guest; a reviewer compares
  distinct saved state (date, score, and one more controlled field) before/after.
* **Measures:** wall time from packet receipt until first useful original-backed
  claim and full harness acceptance; test/code errors, tool requests, context
  tokens if observed by runner, cost to repair, unsupported claims and cold
  replay with only the handoff. One helpful explanation is not a causal speedup.
* **Held out:** AITD internal Life/PAK engine behavior, Castles I secondary
  route and any unpublished game mechanics; use only after freeze.

This is a research handoff, not an attempt to merge or release a production
interface. Original games, screenshots, full saves and binary artifacts remain
private. Public files contain code, metrics and scoped source hashes only.
