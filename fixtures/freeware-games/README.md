# Freeware game versions: Tic-tac-toe, Five Dice and Snake

The user explicitly approved these three games and their generated variants for repository/review distribution. This corpus contains retained game executables, sources, reusable blocks, reference models and generated browser/native builds. Other games, databases, saved states, external SDKs and emulator payloads are excluded.

Original executable/module bytes are unchanged. Duplicate retained copies are recorded as aliases; intermediate and source-only builds retain their actual qualification status. Historical run receipts are attributed evidence, not new executions performed for this packaging PR.

## Start here

- DOS Tic-tac-toe: `tic-tac-toe/original/learner/ATTT.COM` (the supplied NASM COM adaptation).
- DOS Five Dice: `five-dice/original/learner/DICE.COM`.
- DOS Snake: `snake/original/learner/SNAKE.EXE`.
- Browser Snake: `snake/builds/browser-selectable-rng-final/index.html`. Serve this corpus over localhost, then open that path in a browser with Wasm/WebGPU support.
- Native Snake: the `win32-final`, `win64-final`, `win16-final`, `linux-x86_64-final` and `macos-arm64-final` folders under `snake/builds/`. Win16 needs `INITIAL.BIN` beside `PROGRAM.EXE`; the macOS application is `MemoryGame.app`.

To serve the browser version, run `python3 -m http.server 8000 --directory fixtures/freeware-games` from the repository and open `http://localhost:8000/snake/builds/browser-selectable-rng-final/`. Original and LFSR16 RNG selections remain available. Native operating-system and browser compatibility is limited to the recorded receipts; no new game execution is claimed here.

## Version inventory

| Version | Role | Format | Artifact |
| --- | --- | --- | --- |
| tic-tac-toe/original | full-game | dos-com | [ATTT.COM](tic-tac-toe/original/learner/ATTT.COM) |
| five-dice/original | full-game | dos-com | [DICE.COM](five-dice/original/learner/DICE.COM) |
| tic-tac-toe/text | full-game | dos-com | [ATTT.COM](tic-tac-toe/variants/text/ATTT.COM) |
| tic-tac-toe/misere | full-game | dos-com | [ATTT.COM](tic-tac-toe/variants/misere/ATTT.COM) |
| tic-tac-toe/misere-text | full-game | dos-com | [ATTT.COM](tic-tac-toe/variants/misere-text/ATTT.COM) |
| five-dice/lcg16 | full-game | dos-com | [DICE.COM](five-dice/variants/lcg16/DICE.COM) |
| five-dice/xorshift16 | full-game | dos-com | [DICE.COM](five-dice/variants/xorshift16/DICE.COM) |
| five-dice/block-lcg16 | block | x86-16-block | [lcg16-ax.bin](five-dice/blocks/lcg16-ax.bin) |
| five-dice/block-xorshift16 | block | x86-16-block | [xorshift16-ax.bin](five-dice/blocks/xorshift16-ax.bin) |
| tic-tac-toe/reference-clean | reference | uil-module | [tic_tac_toe.py](references/scalar-uil/examples/udc/game_variants/tic_tac_toe.py) |
| tic-tac-toe/reference-compact | reference | uil-module | [tic_tac_toe.py](references/scalar-uil/examples/udc/game_variants/tic_tac_toe.py) |
| tic-tac-toe/reference-verbose | reference | uil-module | [tic_tac_toe.py](references/scalar-uil/examples/udc/game_variants/tic_tac_toe.py) |
| five-dice/reference-clean | reference | uil-module | [five_dice.py](references/scalar-uil/examples/udc/game_variants/five_dice.py) |
| five-dice/reference-compact | reference | uil-module | [five_dice.py](references/scalar-uil/examples/udc/game_variants/five_dice.py) |
| five-dice/reference-verbose | reference | uil-module | [five_dice.py](references/scalar-uil/examples/udc/game_variants/five_dice.py) |
| five-dice/reference-binding-lcg | reference | python-reference | [demo.py](five-dice/original/oracle/demo.py) |
| five-dice/reference-binding-xorshift | reference | python-reference | [demo.py](five-dice/original/oracle/demo.py) |
| snake/original | full-game | dos-mz | [SNAKE.EXE](snake/original/learner/SNAKE.EXE) |
| snake/dos-source-revision-1 | reference | source-reference | [SNAKE.ASM](snake/original/source-revisions/revision-1/SNAKE.ASM) |
| snake/dos-source-revision-2 | reference | source-reference | [SNAKE.ASM](snake/original/source-revisions/revision-2/SNAKE.ASM) |
| snake/dos-source-revision-3 | reference | source-reference | [SNAKE.ASM](snake/original/source-revisions/revision-3/SNAKE.ASM) |
| snake/win16-final | full-game | windows-ne | [PROGRAM.EXE](snake/builds/win16-final/PROGRAM.EXE) |
| snake/win32-final | full-game | pe32 | [program.exe](snake/builds/win32-final/program.exe) |
| snake/linux-x86_64-final | full-game | elf64 | [program](snake/builds/linux-x86_64-final/program) |
| snake/win64-final | full-game | pe64 | [program.exe](snake/builds/win64-final/program.exe) |
| snake/macos-arm64-final | full-game | macho-arm64 | [program](snake/builds/macos-arm64-final/MemoryGame.app/Contents/MacOS/program) |
| snake/intermediate-05-browser-wasm-webgpu | full-game | browser-bundle | [index.html](snake/builds/intermediate-05-browser-wasm-webgpu/index.html) |
| snake/intermediate-06-browser-wasm-webgpu | full-game | browser-bundle | [index.html](snake/builds/intermediate-06-browser-wasm-webgpu/index.html) |
| snake/intermediate-07-browser-wasm-webgpu | full-game | browser-bundle | [index.html](snake/builds/intermediate-07-browser-wasm-webgpu/index.html) |
| snake/intermediate-08-windows-x86 | reference (source only) | source-reference | [native-shell.json](snake/builds/intermediate-08-windows-x86/native-shell.json) |
| snake/intermediate-11-windows-x86-16 | full-game | windows-ne | [PROGRAM.EXE](snake/builds/intermediate-11-windows-x86-16/PROGRAM.EXE) |
| snake/intermediate-12-windows-x86-16 | reference (source only) | source-reference | [native-shell.json](snake/builds/intermediate-12-windows-x86-16/native-shell.json) |
| snake/intermediate-13-browser-wasm-webgpu | full-game | browser-bundle | [index.html](snake/builds/intermediate-13-browser-wasm-webgpu/index.html) |
| snake/intermediate-14-browser-wasm-webgpu | full-game | browser-bundle | [index.html](snake/builds/intermediate-14-browser-wasm-webgpu/index.html) |
| snake/intermediate-15-browser-wasm-webgpu | full-game | browser-bundle | [index.html](snake/builds/intermediate-15-browser-wasm-webgpu/index.html) |
| snake/intermediate-16-arm64 | full-game | macho-arm64 | [program](snake/builds/intermediate-16-arm64/MemoryGame.app/Contents/MacOS/program) |
| snake/intermediate-17-arm64 | full-game | macho-arm64 | [program](snake/builds/intermediate-17-arm64/MemoryGame.app/Contents/MacOS/program) |
| snake/intermediate-19-arm64 | full-game | macho-arm64 | [program](snake/builds/intermediate-19-arm64/MemoryGame.app/Contents/MacOS/program) |
| snake/intermediate-20-browser-wasm-webgpu | full-game | browser-bundle | [index.html](snake/builds/intermediate-20-browser-wasm-webgpu/index.html) |
| snake/intermediate-21-browser-wasm-webgpu | full-game | browser-bundle | [index.html](snake/builds/intermediate-21-browser-wasm-webgpu/index.html) |
| snake/intermediate-22-linux-x64 | full-game | elf64 | [program](snake/builds/intermediate-22-linux-x64/program) |
| snake/intermediate-23-windows-x64 | reference (source only) | source-reference | [native-shell.json](snake/builds/intermediate-23-windows-x64/native-shell.json) |
| snake/intermediate-24-linux-x64 | full-game | elf64 | [program](snake/builds/intermediate-24-linux-x64/program) |
| snake/intermediate-26-windows-x64 | full-game | pe64 | [program.exe](snake/builds/intermediate-26-windows-x64/program.exe) |
| snake/browser-nested-final | full-game | browser-bundle | [index.html](snake/builds/browser-nested-final/index.html) |
| snake/browser-selectable-rng-final | full-game | browser-bundle | [index.html](snake/builds/browser-selectable-rng-final/index.html) |
| snake/browser-baseline-final | full-game | browser-bundle | [index.html](snake/builds/browser-baseline-final/index.html) |

## What the variants mean

Tic-tac-toe has four DOS builds: baseline, terminal text (`GG!!` / `TIE!`), misère outcome, and combined misère/text. The text-only variant keeps winner logic; the misère variant intentionally changes the awarded player. Five Dice has its original fixed-seed game plus selected LCG16 and xorshift16 provider splices. The standalone AX RNG bodies and supplied Python provider demo are separate partial/reference artifacts. The later clean/compact/verbose scalar UIL examples are partial handlers or an authored seed-step example, not complete modern game ports.

Snake has 31 retained manifest-bearing roles represented by 26 distinct build snapshots after exact alias grouping. This includes baseline, nested-cut and selectable-RNG browser generations; native macOS ARM64, Linux x86-64, Win64, Win32 and Win16; and retained intermediate/source-only attempts. Original/LFSR16 behavior is intentionally different. Recommended finals are identified in `manifest.json`; unqualified intermediate builds are archival evidence.

## Source and learner/oracle boundary

The `original/learner/` files are the supplied starting targets. `original/oracle/` contains source and ground truth; opening it breaks a blind learner exercise. The two-title upload is preserved under `intake/`. Snake was a later locally authored fixture, with its source/archive SHA recorded in the manifest. Its original ASM revisions are retained separately.

The compact Tic-tac-toe oracle omitted its documented NASM adaptation, native test script, JSON evidence and screenshots. The adaptation is recovered under `original/recovered/` from 20 verified supplied patch hunks and independently agrees with the supplied converter. NASM was not available in the bounded local environment, so this PR does not claim a fresh assembly-to-binary check. The missing test/evidence/screenshots remain missing.

## Licensing and notices

Tic-tac-toe retains its supplied Unlicense; Five Dice retains its supplied CC0 dedication. Snake fixture code is CC0-1.0, with the supplied exclusion of external tools. The generated Snake initial memory also contains a captured external BIOS font: its exact bytes match the pinned DOSBox-X font array, whose source states GPL-2.0-or-later. The font source, copyright notice and GPL COPYING are in [snake/runtime-font/](snake/runtime-font/README.md). This font is not presented as CC0 fixture code. Generated game C, header, Objective-C, Wasm/WGSL and model inputs are retained with their builds. External compilers/emulators are not included.

## Integrity and maintenance

Run `python3 scripts/check_freeware_games.py --root fixtures/freeware-games` from the repository. After adding an approved retained version, update the manifest file/variant records, then run `python3 scripts/check_freeware_games.py --root fixtures/freeware-games --write-archive fixtures/freeware-games.zip --archive fixtures/freeware-games.zip`. This validates all bytes, lineage, notices, archive members and executable permissions. A hash confirms identity, not behavior.

The companion ZIP is a separate game corpus. Tool wheels, sdists and tool source ZIPs exclude this entire directory and companion archive. Private workspace paths in a few non-runtime metadata/helper copies are redacted and their original SHA values retained. Runtime manifests, game executables, Wasm/WGSL modules and initial game data retain their original bytes. The archive root of one old browser package is normalized without changing its file contents.
