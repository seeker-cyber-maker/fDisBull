# RFC 0001 executable examples

These are authored, redistributable **synthetic** compiler-definition seeds and
an opt-in original-code research replayer. They are not a general UIL compiler.
See [the RFC](../0001-shared-intents-and-compiler-definitions.md) and
[findings](../../UDL_UIL_EFFECT_ISOLATION_FINDINGS.md).

## One intent, four backings

With existing Python, Node.js and Rust installed, run from the repository root:

```sh
python docs/uil-rfcs/0001/check_examples.py --output /path/to/new-private-output
```

The checker installs nothing. It compiles the authored Rust definition into the
new output directory, runs the authored JS and Python definitions, and compares
them with an unchanged `fdisbull-il-1` UDL program. Role rewriting is optional
metadata, not a required compilation step. No game, emulator or private save
is needed for these source examples.

The contract is deliberately small: with a qualified prepared order, copy the
pending stock, post a 500-unit u32-wrapping expense, then commit reserved cash.
The common admission adapter requires a ready flag, a 500-unit cash reservation
and a 20-unit stock increment. The fixture flag is not a real authorization token.
All five numeric fields are u32; decimal strings cross the process boundary.
The source functions take only admitted operands and a readiness result.

Literal vectors include a normal commit, expense wrap, missing readiness,
missing reservation and wrong quantity, plus malformed inputs. They assert
intermediate checkpoints and event order as well as final state. The original
DinoPark uses a richer nine-bin/native-state contract; these examples do not
claim its full numeric layout or game semantics.

A selection example uses invented cost scores. It excludes an implementation
with the wrong event order even though its final state matches, and selects a
cheaper eligible alternative. This is a mechanism example, not a benchmark or
an automatically learned optimizer. Rust/JS/Python sources were separately
authored rather than automatically propagated. The checked receipt is
[source-definition-observation.json](source-definition-observation.json).

## Original-code research replayer

`native_probe.py` requires trusted operator-owned native checkpoints and the
matching private game working directory, backend and fDisBull installation:

```sh
python docs/uil-rfcs/0001/native_probe.py \
  --project /private/captured-scene.fdb \
  --game-dir /private/matching-game \
  --backend /path/to/qualified-dosbox-x \
  --output /private/new-effect-study
```

The published native observation used fDisBull `0.21.0-a253600` and its pinned
macOS ARM64 backend; the script checks the executable/backend digests. Repository
source inspection and shared-IL checks used 0.22.0. This does not newly qualify
the original game's native runtime under every 0.22.0 backend.

The input project must contain `office.sav` and `prepared.sav` states from the
identified original: the former captured after actual office qualification,
the latter at `2d0a:2810` after a real food order was prepared. Input must be
quiescent before checkpointing. The original native context, file inventory
and loaded address mapping remain required. The public repository contains
none of these private inputs.

The replayer clones the SQLite project through its backup interface, creates
explicit data/register/argument-frame forks, and stops at `2d0a:283d`. It never
claims to return into the office caller, to finish a purchase, or to merge the
experimental state into live gameplay. The input checkpoint database is opened read-only and cloned. The native runtime
requires the exact disposable game working-directory path recorded at capture;
copying that directory to another path correctly refuses restore. Use the
captured disposable directory, not an original installation or a live session.
The replayer verifies its file hashes before/after. Raw snapshots and derived
artifacts stay outside Git.
The output retains complete private evidence. The published
[native observation](native-observation.json) contains only selected facts,
identities, trace digests and limits.
