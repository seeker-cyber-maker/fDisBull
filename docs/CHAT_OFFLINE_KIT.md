# Linux chat offline kit assembly

`scripts/build_chat_offline_kit.py` assembles a Linux x86-64 kit from explicit,
hash-bound prepared inputs. It does not download, build, install or qualify
those inputs. Run storage admission for the staging directory and archive before
assembly; both coexist during packaging. ZIP is the default and the default
maximum output is 500,000,000 bytes. An oversized archive is retained as an
unqualified candidate and the command fails. XZ and gzip tar are optional.

```
python scripts/build_chat_offline_kit.py --inventory /absolute/inventory.json \
  --output /existing/external/parent/chat-kit.zip
```

Inventory schema is `fdisbull-chat-offline-inventory-v1`. Set `profile` to
`shared` for the space-saving delivery. `identities` contains full lowercase
hexadecimal `source_commit` and `test_source_commit`, `version`, `python`
(exactly `3.13.5`), `qemu` (exactly `9.2.4`) and `wine`. `files` is an array
with absolute `source`, relative `destination`, integer `size`, SHA-256 and
`role` for every input file. Each input is an ordinary non-symlink file and
each destination is unique. Preserve the full portable Python prefix and its
installed packages, metadata, standard library and native extensions. The
interpreter destination is `python/bin/python3.13`, and private libraries go
in `lib/`. Copy symlink targets to regular files at each required name.

Provide these roles once each: `python`, `loader`, `dosbox`, `qemu`, `kernel`,
`source_companion`, `closure_receipt`, `python_receipt`, `dosbox_receipt`,
`qemu_receipt`, `wine_receipt`, `pe_fixture` (project-authored, non-private),
`verifier`, `wheel_core`, `wheel_player`, `wheel_z3`, `runtime_base`,
`runtime_recipe`, and `runtime_preparer`. The runtime preparer must be at
`tools/preparer.py`. One or more `firmware` and `license` entries are required;
use `payload` for remaining files. The shared base and recipe describe the
local reconstruction of Wine and DOS initramfs images. The recipe and output
identities must be independently verified by the preparer and consumer. The
optional `prebuilt` profile replaces the three runtime roles with
`wine_initramfs` and `dos_initramfs` and carries wheel files in the archive;
it is still subject to the size cap.

All wheel inputs have destinations in `wheels/` and remain build-side inputs
for `shared`; their names, sizes and hashes are recorded, but their contents
are not delivered twice. `wheel_versions` pins exactly these normalized names:
`fdisbull`, `fdisbull-player`, `iced-x86`, `capstone`, `lief`, `pillow`,
`z3-solver`, `unicorn`, `dnfile`, `dncil`, `pefile`, `tree-sitter`,
`tree-sitter-c`, `pycparser`. The builder checks metadata and compares each
wheel's installed library members against the inventoried prefix; generated
scripts and RECORD are excluded. Independently verify distribution compatibility
and requirement constraints. Never include games, saves, states, private
fixtures, project databases or credentials.

The closure receipt has schema `fdisbull-elf-closure-v1`, `complete: true`, and
`objects`, an array of `{ "path": "destination", "needed": { "soname":
"lib/soname" } }`. It lists every ELF object in the inventory with each
resolved private library. This is a preparer assertion, not proof of closure;
the consumer must independently verify it. All ELF objects must be 64-bit,
little-endian x86-64. Hashes bind bytes, not provenance or licensing.

The root is `fdisbull-chat-offline/`. Entrypoints are `bin/python`,
`bin/fdisbull`, `bin/player`, `bin/dosbox`, `bin/qemu`, and in shared profile
`bin/prepare-runtimes --cache /writable/private/cache`. The latter runs the
bundled preparer using bundled Python with safe-path and user-site controls and the kit root. Runtime setup
is explicit and `--help` must not create images. Entrypoints use the private
loader, inhibit its cache, clear inherited Python/loader variables and disable
user site packages. `MANIFEST.json` records identities, delivered file hashes,
wheel input hashes and `not-qualified-by-builder`; it omits original paths and
is not self-hashed.

The source companion is operational source evidence, not a representation that
all upstream source required for redistribution is supplied. Review component
licenses and source obligations separately. A kit is unqualified until the
independent clean, offline Linux extraction and native consumer checks pass.

The generated archive README describes its portable Python, local runtime setup
and entrypoints. This shared chat kit carries its operational dependencies for
the stated Linux profile. The separate legacy offline kit is DOS-focused and
requires an installation step and additional host dependencies.
