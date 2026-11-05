# Castles II, original-DOS menu/save/load microharness

**Status:** Tested on a private local copy of GOG Castles II 1.0, using the
fDisBull **v0.31.1** native DOSBox-X binary, Linux x86-64 and Python 3.13.5.
**No commercial game assets, game screenshots, saves or original executables
are in this source bundle.** The script does not implement a game or UIL engine.

The purpose is to give a cold agent a *reusable action surface* instead of
repeating human mouse exploration. The program launches the ORIGINAL DOS game
under DOSBox-X in a private Xvfb display, sends real mouse/keyboard events, keeps
PNG evidence privately, validates title-vs-map frame surfaces, and checks that
an actual `.GAM` save is created and remains unchanged through in-session and
fresh-process loads.

## Prepare a **disposable, private** game directory

1. Extract the user-owned GOG installer using fDisBull's supported native GOG
   adapter, or an already qualified extractor, outside any Git checkout.
2. Copy that extraction to a **fresh writable private test directory**. Never
   point the harness at the purchased originals or production save folder.
3. The unmodified GOG `C2CD.BAT` has `c2cdtool quickfades firsttime` on its first
   invocation. In the disposable copy ONLY, change that first invocation to
   `c2cdtool quickfades startagain`. This skips the introduction during repeated
   tests; the existing batch return-code supervisor remains otherwise intact.
4. Keep `C2CD.ins`, `C2CD.gog`, `C2CDTOOL.EXE`, remaining extracted game files,
   and the user's DOS/ISO inputs together. Do not strip the CD's audio track.
5. Use a **single save file** in the private directory for the `save_load` plan;
   an existing save with the selected basename is refused.

Only the exact GOG executable SHA-256
`512efad4a4d771f6c975702cad9a688aeef10f8d81798b8c7260e37c74e87d43`
is admitted. Other editions require fresh coordinate and runtime qualification.

## Execute

Use an isolated X display not already occupied by another controller:

```bash
/path/to/python3.13 c2_agent_harness.py \
  --game-dir /private/fdisbull-castles2-test-copy \
  --backend /private/fdisbull-0.31.1-offline/bin/dosbox \
  --output /private/fdisbull-castles2-first-test \
  --display :104 --slot BENCH1 --plan save_load
```

Requires `Xvfb`, `xwininfo`, `scrot`, Python Pillow, libX11 and libXtst and the
verified DOSBox-X backend. The script writes its own ephemeral DOSBox config,
spawns and reaps only its owned emulator/Xvfb processes and leaves a JSON receipt
and PNGs in the private output directory. Its forced host shutdown **is not a
successful guest exit certificate**. It does not use DOSBox's faulty
"save before quitting" operation.

The selected `save_load` plan is:
`main.game` -> `game.play` -> `map.opts` -> `opts.save` -> enter filename ->
`save.ok` -> `map.opts` -> `opts.load` -> select sole file -> `load.ok` ->
**stop/restart original DOSBox** -> `main.game` -> `game.load` -> select file ->
`load.ok`. Evidence is maintained separately for every step.

The `menu` plan only checks that the actual original menu and mounted CD appear.
Action names denote observed UI controls; they are **not built-in fDisBull
v0.31.1 methods** and do not prove corresponding UDL/UIL semantics. For an
unmerged fDisBull !82 runtime with `z-controller`, these are candidate actions
to port into its retained original-engine handler vocabulary.

## Test synthetic contract

```bash
python3 -m unittest discover -s tests -v
```

The 12 tests use fake file names and plain colored images only. No game file is
needed to run the synthetic checks.

## What passed / what did not

Three independent private-copy full replays passed, lasting 16.191, 16.751 and
16.208 seconds end-to-end. They created a nonempty 11,733-byte `.GAM`, accepted
an in-session load, then used a **new emulator process** to accept that same
file; save bytes/hashes remained unchanged across loads. A separate manual
original-GUI investigation observed a restored **May 6, 1312** date and
**4,345** score after restart. The automated test proves existence, hash
preservation and a returned map frame but **does not parse/read back all game
state fields** or independently certify save-file semantics.

This is one author's tool development and **not a matched cold-agent comparison
between current skill and draft !82**. See `EXPERIMENT.md` for the defensible
A/B setup and `BENCHMARK_PROTOCOL.json` for objective/acceptance rules.

Earlier failed attempts caught three *harness*, not game, bugs: argument-key
collision in event logs, accepting a black initial frame as a menu, and reusing
`scrot`'s stale first filename rather than its suffixed later captures. These
were corrected before successful reproducibility measurements.
