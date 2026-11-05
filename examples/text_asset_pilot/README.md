# Text-first asset packages and shell connectors

Status: implemented research pilot, 2026-11-04. No core UIL schema or released
fDisBull CLI is changed. The source examples and authored fixtures are public;
all real Zork assets, lowered game programs, cooked applications and checkpoints
are private build products outside Git.

## Purpose

Exercise asset normalization, component packaging, provider selection and replay
using text before adding image/audio providers. Reuse the existing fDisBull
word16 runtime rather than write another Z-machine interpreter.

The user's chip analogy has a concrete mapping:

| Chip concept | Pilot implementation |
| --- | --- |
| Die | Preserved game behavior in the existing word16 reference IR, with its initial state stored separately. |
| Media inside the package | Hash-addressed UTF-8 assets and a typed source-binding component. |
| Socket/pin contract | Versioned command-input and presentation-output contracts. Their canonical definitions are hashed. |
| Connecting wires | A checked link receipt maps each required port to an exact shell-provider port. |
| Shell | Terminal or JSON-lines Python-standard-library host implementation. |
| UDC realization | The cooker chooses the shell, links the same package, and emits a runnable self-contained Python ZIP application. |

This is an asset/package/connector implementation, **not** a newly recovered
high-level Zork UIL model or a native ELF compiler. The retained IR still owns
the game's parser, data layouts, memory, RNG, calls, persistence and logic.
Original-derived bytes remain in its initial memory and byte guards. Removing
the original DAT filename does not remove that provenance or make it public.

## Implemented files

- `asset_package.py`: deterministic container, full member/hash/dependency
  validation and typed connector admission; Python standard library only.
- `pilot.py`: guarded text normalization, the reference-die adapter, shell
  selection, cooking, play and package-bound checkpoints.
- `verify_private.py`: separate recovery and product-verification processes,
  matching turn results and full runtime snapshots against the shipped word16
  baseline; replay and cross-shell restore in fresh isolated processes.
- `tests/test_text_asset_pilot.py`: authored positive and negative fixtures only.
- `FORMAT.md`: exact container and boundary rules.

## Build with an owned story

Use the fDisBull 0.31.1 core and matching player, Python 3.10+ for the standalone
product (the fDisBull compiler itself requires Python 3.12+). The verified host
used Python 3.13.5 on Linux x86-64. Run these from this example directory:

```sh
python pilot.py build /private/ZORK1.DAT /private/zork-text.bundle
python pilot.py inspect /private/zork-text.bundle
python pilot.py cook /private/zork-text.bundle /private/zork-terminal.pyz --shell terminal
python pilot.py cook /private/zork-text.bundle /private/zork-jsonl.pyz --shell jsonl
```

`build` is projectless and refuses existing destinations and destinations inside
Git. It does not execute the installer or the original DOS game. Unpacking an
installer is a separate intake step.

The cooked output needs Python and its standard library, **not fDisBull,
DOSBox, Frotz, ScummVM, the original installer or a separate DAT file**:

```sh
python -I /private/zork-terminal.pyz
printf '%s\n' '{"command":"look"}' | python -I /private/zork-jsonl.pyz
```

The terminal shell displays narrative on stdout and status/non-narrative event
receipts on stderr. JSON-lines mode accepts one `{"command":"..."}` request per
line and emits one complete turn per line. Input text is not treated as host
code. EOF stops the host session without manufacturing a game command.

A normalized presentation turn contains `seq`, `command`, `status`, `text`, a
scalar `values` map and ordered `events` receipts. Source program counters and
instruction counts are private execution diagnostics, not presentation pins.
The reference adapter retains source-specific event receipts; it does not claim
that all game-intent effects have been abstracted. Audio events are explicitly
refused by these text-only shells rather than silently called successful.

For deterministic command playback, pass `--commands commands.json`, where the
file is a JSON array of strings. `--transcript`, `--metrics` and `--checkpoint`
write private receipts. Input/output aliases and symlink output files are
refused. Session receipts and input sizes are bounded.

## Save in one shell, resume in another

```sh
python -I /private/zork-terminal.pyz --commands prefix.json --checkpoint /private/progress.json
python -I /private/zork-jsonl.pyz --resume /private/progress.json --commands suffix.json
```

The checkpoint binds the complete runtime continuation, RNG and game-save slot
to the exact asset-package identity. It does **not** bind to terminal formatting
or the selected shell, so equivalent shell bindings can exchange state. An
asset-package change invalidates the checkpoint instead of silently reusing it.
The game's own SAVE/RESTORE remains the existing word16 modeled game-save slot,
not a claim of original DOS `.SAV` interoperability.

## Text is media, but some text also participates in computation

Constant source text and object names become ordinary UTF-8 payloads. Payloads
are content-addressed and duplicate payloads share storage. Source offsets,
short-name limits, abbreviation-pointer dependencies and byte-read spans remain
in the **source-binding adapter**, not in the shell contract or text payload.

Every cached read checks its complete recorded dependency spans against the
initial image. Changed text or abbreviation pointers must not return stale text.
An unbound/changed request uses the explicitly retained original text codec;
`--strict-text` instead refuses it. Metrics separate top-level misses from all
legacy decoder invocations, including abbreviation recursion.

This is intentionally not an all-path codec-removal claim. A conservative
instruction candidate set is not a list of reachable text sites. Invalid static
text candidates are recorded and not admitted; their code remains in the
reference die and can still reach an explicit fallback/refusal.

Tabs, sentence-spacing controls and newlines are preserved in the UTF-8 asset.
They are not normalized at recovery time: the existing runtime must still
convert them correctly when text is routed into a Z-machine memory stream.
Presentation expansion happens only after the output destination is known.
Dictionaries, runtime formatting and parser state are not reclassified as
immutable display assets merely because they contain characters.

## Reproducible qualification

From the repository root, synthetic tests require pytest plus the matching compiler/player:

```sh
python -m pytest -q tests/test_text_asset_pilot.py
```

Actual game acceptance deliberately separates the large recovery heap from the
process that launches products:

```sh
python verify_private.py prepare /private/ZORK1.DAT /private/commands.json /private/acceptance
python verify_private.py products /private/acceptance
```

The first stage builds twice, checks package/cooked determinism, and compares
output, events and full snapshots at every supplied command boundary. The
second launches both products with Python `-I`, compares their transcripts and
final states, then restores a terminal checkpoint in a new JSON-lines process.
The output directory must be new. Reports contain no asserted original-runtime
qualification: the fresh oracle is the unchanged shipped word16 baseline.
Original DOS/Frotz comparison is a separate unfinished edge.

## Remaining scope

- The target output is a Python application, not a machine-native Linux ELF.
- Full Zork game-intent recovery and removal of residual word16/data-layout
  machinery are not part of this package-seam proof.
- All-path text binding closure, full-score routes and other story editions
  need separate acceptance; no command route is an all-path proof.
- PNG/composite-picture, animation, audio, binary timelines, native ABI providers
  and target-specific media compression are future providers, not implemented
  capabilities hidden behind this pilot's format name.
- ZIP assets use STORE and the program member has explicitly declared gzip-JSON
  encoding. Determinism is checked under the pinned Python/tool payloads, not
  asserted across arbitrary compressor versions.

## Primary technical references

The Z-machine Standard 1.1 sections 3, 7 and 13 define text encoding, output
streams and lexical analysis. In particular, stream 3 makes text a computational
result as well as presentation. These rules explain why normalization cannot
silently erase control bytes or the mutable source dependency boundary.

- https://inform-fiction.org/zmachine/standards/z1point1/sect03.html
- https://inform-fiction.org/zmachine/standards/z1point1/sect07.html
- https://inform-fiction.org/zmachine/standards/z1point1/sect13.html

The existing implementation and its previous qualification boundaries are in
`docs/ZORK_UIL.md`, `docs/VERIFICATION-ZORK-UIL-2026-10-29.md` and
`player/fdisbull_player/word16.py`. Earlier receipts are not claimed as new runs.
