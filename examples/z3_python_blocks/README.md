# Z3 to direct Python blocks, before semantic UIL

Implemented research continuation of the text asset pilot. This target translates
an owned Z-machine v3 story to ordinary Python functions and separate media and
memory containers. It does not recover the original author's source code or
claim that mechanical translation has already recovered high-level game intent.

## Design

The old pilot ships an executable word16 node graph and an interpreter for that
graph. This backend uses the same audited decoder/lowerer **at build time only**,
emits Python assignments, conditions, calls and continuation functions, and
removes the runtime `_nodes`, `_expr` and generic `_library` dispatchers. Its
product contains no node graph and imports no fDisBull/player package.

A small scheduler selects the next already compiled Python continuation. It
never fetches a source instruction or interprets a node's operation field. The
Python interpreter still runs the resulting Python, naturally. This is not an
ELF compiler or a claim that all source-machine services have vanished.

The intended sequence is:

```text
owned .z3/.DAT
  -> existing v3 decoder and mechanical semantic expansion at build time
  -> generated Python blocks + reusable primitive/state/media services
  -> tested behavior and explicit state boundaries
  -> later grouping and abstraction into semantic UIL
```

The existing front end calls its intermediate representation a word16 UIL
profile. Here it is only a temporary compiler input. The generated product does
not execute it, and this work does not introduce any new semantic UIL operations.

## Product structure

```text
zork-python/
  play.py                 small terminal / JSON-lines entry point
  game_code/b*.py          generated, independently inspectable Python functions
  primitives.py           numeric blocks: wrapping, signed arithmetic, booleans
  runtime.py              function scheduler, media bindings, typed memory views
  state_services.py       retained parser, object, stream and save services
  program.json            continuation IDs, function headers and identities
  media.zip               UTF-8 strings and guarded text binding index
  memory.zip              initial mutable storage, read-only backing and layout
  product.json            exact code/data hashes
```

Game-generated code, media, storage, saves and transcripts remain private.
Only the generic compiler/runtime, authored fixtures and aggregate receipts
belong in the repository.

### Media container

Reuses the prior deterministic, data-only package reader. It holds 1,796 unique
UTF-8 payloads for the tested Zork edition, with 2,150 static bindings. Source
coordinates and byte-dependency checks are adapter metadata, not semantic text
identities. Changed or unresolved text uses an explicit, counted legacy text
codec; strict mode refuses it. No route-based dynamic training was used to build
the catalog. A string's content and encoding are not guessed from its use count.

### Memory container

`state.dynamic` owns the initial writable bytes, `state.readonly` retains
read-only data and source identity backing, and `state.layout` describes their
meaning and bounds. The live instance exposes:

```python
machine.state.globals[7] = 42
assert machine._read(machine.layout['globals'] + 14, 16) == 42
machine.state.set_flag(object_number, attribute_bit, True)
```

Globals and attributes are **views**, not duplicate dictionaries. Direct byte
writes, word writes, global-variable writes and object-attribute writes must see
one authoritative value. Unknown global/bit meanings retain numeric identities;
no invented names like `door_is_open` are asserted.

A `.memory-state.json` checkpoint contains only mutable memory plus the complete
continuation state: local frames, evaluation stack, pending input, random state,
stream state, pending output and the modeled game-save slot. It binds to the
exact product, media and memory identities. Restoring validates everything before
mutating the live instance. Read-only backing is reconstructed from the locked
container rather than duplicated in each checkpoint.

The original-derived read-only backing can still contain packed text and source
code bytes. They are retained for arbitrary data reads, decoder fallback and
self-modification guards, **not opcode execution**. Proving that those bytes can
be discarded or relocated is a separate analysis obligation. Keeping semantics
correct takes priority over cosmetically deleting a byte array.

### Repeatable code blocks

`primitives.py` is reusable across targets of this source numeric profile.
Generated functions use ordinary Python branches and calls to specific helpers
such as `attribute_test`, `property_get`, `tree_insert` and `text_decode`.
Source-specific parser, object layout, formatting, output streams and game-save
semantics remain explicit service implementations. They can be replaced one at
a time behind tested contracts in the subsequent UIL phase.

The generator retains a conservative set of legal instruction-start candidates,
including unreachable/alternate decodes, to preserve indirect control targets.
55,891 generated blocks are **not** 55,891 confirmed reachable game behaviors.
Modules are loaded on demand; no source opcodes are decoded on that path.

## Build and run

Build requirements: fDisBull 0.31.1 plus its matching player, Python 3.12+ and the
preceding `examples/text_asset_pilot` sources. The validated environment used
Python 3.13.5 on Linux x86-64. Standalone products use the Python standard library.

```sh
python examples/z3_python_blocks/transpile.py /private/ZORK1.DAT /private/zork-python
python -I /private/zork-python/play.py
```

The output directory must not exist and must be outside Git. To inspect code,
open the generated `game_code/b*.py` files; `program.json` maps continuation IDs
and source provenance without embedding an executable JSON operation graph.

```sh
python -I /private/zork-python/play.py --commands /private/commands.json \
  --checkpoint /private/progress.memory-state.json
python -I /private/zork-python/play.py --resume /private/progress.memory-state.json
```

Keep checkpoint/transcript/metrics paths outside the immutable product directory
and outside Git. `--jsonl` accepts `{"command":"look"}` lines and returns complete
turn objects. `--strict-text` diagnoses unresolved media bindings rather than
implicitly invoking the retained codec.

## Verification

```sh
python -m pytest -q tests/test_z3_python_blocks.py tests/test_text_asset_pilot.py
python examples/z3_python_blocks/verify.py /private/ZORK1.DAT \
  /private/zork-python /private/routes.json /private/result.json
```

`routes.json` is an array of objects with `name`, `seed` and `commands`. The
harness compares complete turn output/events and complete runtime snapshots to
the unchanged word16 reference, including RNG and modeled SAVE state. It also
round-trips the separate live-memory container. This is not an independent
original-interpreter comparison. See ACCEPTANCE.md for actual counts.

## Boundaries and next work

No visual programming editor, semantic-label inference, full-score walkthrough,
all-path reachability proof, native ELF, graphics or audio provider is claimed.
The next abstraction step is to identify larger contracts over these explicit
Python data/control blocks, validate them, and then express them in UIL. That
step may change the die's internal organization while preserving admitted
behavior, aliases, numeric rules and external interface contracts.

Primary specifications consulted: Z-machine Standard 1.1 section 2 (16-bit
signed arithmetic, division and remainder), section 6 (variables, indirect stack
access, calls, saved state) and section 7 (output streams including memory).

- https://inform-fiction.org/zmachine/standards/z1point1/sect02.html
- https://inform-fiction.org/zmachine/standards/z1point1/sect06.html
- https://inform-fiction.org/zmachine/standards/z1point1/sect07.html

Implementation provenance: `state_services.py` is generated by retaining exact
support-method ASTs from the installed `fdisbull_player.word16`, with its SHA-256
in the generated header. It excludes the generic evaluator methods. The source
project's terms continue to apply to those retained methods.
