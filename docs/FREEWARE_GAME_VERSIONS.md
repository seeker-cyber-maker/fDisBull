# Approved freeware game versions

The repository now retains the user-approved Tic-tac-toe, Five Dice and Snake
inputs and generated outputs in `fixtures/freeware-games/`. The separate
`fixtures/freeware-games.zip` is a deterministic companion delivery. The
exception is limited to these three named games and their title-specific
sources, assets, blocks and reference models. Other games, databases, external
object stores, emulator states, SDKs and tool distributions remain private.

The collection is available in the repository's
[fixture directory](https://gitlab.com/brewster-jennings-group/fdisbull/-/tree/codex/freeware-game-versions-20261101/fixtures/freeware-games)
and as the
[companion ZIP](https://gitlab.com/brewster-jennings-group/fdisbull/-/raw/codex/freeware-game-versions-20261101/fixtures/freeware-games.zip).
These repository fixtures are intentionally absent from tool-only wheels,
sdists and tool source ZIPs.

## Contents and scope

| Game | Retained executable versions | Additional material |
| --- | --- | --- |
| Tic-tac-toe | Original NASM COM adaptation; terminal-text; misère outcome; combined text/misère | Supplied learner/oracle packages, upstream assembly, adaptation patch, mechanically recovered NASM source, clean/compact/verbose partial UIL examples |
| Five Dice | Original DOS game; LCG16 provider splice; xorshift16 provider splice | AX RNG bodies and assembly, Python provider/binding demo, clean/compact/verbose partial seed examples |
| Snake | Original DOS MZ; browser Wasm/WebGPU generations; native macOS ARM64, Linux x86-64, Win64, Win32 and Win16 builds | Retained source revisions, intermediate/source-only builds, per-build sources/objects/configuration, initial data and model/recovery snapshots |

The inventory has 47 version entries. Snake's 31 retained build roles are
represented by 26 distinct manifest/asset snapshots after byte-identical alias
grouping. Version entries distinguish full game builds, individual blocks,
references and source-only attempts. A filename or hash does not establish that
an intermediate build was executed successfully; its retained qualification
status stays with that version.

The original Tic-tac-toe file is the supplied NASM COM adaptation of Ancient
TicTacToe, not an upstream TASM/TLINK EXE. Its text variant changes `GG!!`/`TIE!`
resources while retaining the winner; misère intentionally changes the awarded
player. The Five Dice Python demo and later scalar UIL examples are partial
references, not complete modern-platform game ports. Unrelated arithmetic or
Colonization scaffolds are not relabelled as versions of these games.

The compact Tic-tac-toe oracle omitted some files it described. The missing NASM
source was recovered from the supplied patch and checked against the supplied
converter. NASM was unavailable locally, so no fresh assembly-to-executable
identity claim is made. Missing native-test/evidence/screenshots remain listed
as missing. Existing native behavior receipts are historical evidence; this
packaging change freshly verifies the retained bytes and catalogue, not every
past game execution.

## Licenses and preserved bytes

The supplied Tic-tac-toe Unlicense and Five Dice CC0 dedication are retained.
Snake's authored fixture is CC0-1.0, excluding external tools. Generated Snake
initial memory also contains an external runtime font. Its 2,048 bytes exactly
match `int10_font_08` in the
[pinned DOSBox-X source](https://raw.githubusercontent.com/joncampbell123/dosbox-x/029bd65c5dcc7cdc7f2e14e35278620d9707d969/src/ints/int10_memory.cpp),
which identifies GPL-2.0-or-later. The extracted font source, copyright/license
notice and matching GPL COPYING are included separately under
`snake/runtime-font/`; the external font is not represented as CC0 fixture code.
Generated C/header/Objective-C/Wasm/WGSL and model data are kept with their builds.

Original executable, module and runtime-asset bytes are preserved. The manifest
records SHA-256, size, ancestry, role and executable mode. A small number of
non-runtime metadata/helpers have private workspace paths redacted, with their
source hashes retained. One browser archive's outer directory is normalized
without changing its payload bytes. Learner and oracle files stay separated;
opening the oracle exposes the ground truth for a blind reconstruction task.

## Validate and maintain the collection

From a repository clone containing the fixture corpus:

```bash
python3 scripts/check_freeware_games.py --root fixtures/freeware-games
python3 scripts/check_freeware_games.py --root fixtures/freeware-games \
  --write-archive fixtures/freeware-games.zip \
  --archive fixtures/freeware-games.zip
```

Add a retained variant deliberately, with its game, role, parent, actual
qualification and hash/size records. Update the catalogue and rebuild the ZIP.
The validator rejects missing/extra files, changed bytes, unsafe paths, links,
case collisions, cross-game/cyclic parents, unbound notices, private state files
and inconsistent archive bytes or permissions. ELF/Mach-O and explicit launcher
permissions are retained. It performs no game execution.

The companion corpus is allowed in Git/review by the explicit exception.
`scripts/check_dist.py` still rejects these fixtures and the companion ZIP in
tool packages, including extensionless binaries. No broad binary exclusion was
removed.
