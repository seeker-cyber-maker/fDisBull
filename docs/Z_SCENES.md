# Z: a small scene consumer over shared IL

Integration candidate on v0.23.0, 29 October 2026. **Z** is shorthand for the Zork-like
text testing interface, not another rule language. This candidate connects
existing shared IL to the standalone player without starting a debugger.
The published v0.23.0 tag predates this addition.

UDL maps original code into UIL; a UDC realizes UIL as executable code. This
adapter consumes already available `fdisbull-il-1` operations and public scene
metadata. It uses the existing pure IL evaluator as its backing. Version 0.23
supplies an original-backed DOS UDC separately; a native scene provider connects
that output to the same player. Generic DOS generation remains separate work.

## Play a scene

From this source checkout, using Python with fDisBull dependencies installed:

```sh
PYTHONPATH=src:player python -m fdisbull_player \
  --backend-command "python -m fdisbull.il_scenes examples/z/key-and-gate.json" \
  --backend-timeout 3
```

The supplied scene is authored synthetic content, not a recovered game:

```text
Courtyard
An iron gate stands in the north wall.
Visible: brass key, gate.

> n
Rejected: Action refused.
> take key
Success: You take the brass key.
> inventory
Carrying: brass key.
> use key on gate
Success: You unlock the gate.
> n
Success: You pass through the gate into the garden.
> look
Garden
You stand among quiet flower beds. The courtyard is south.
Visible: south.
```

The parser, descriptions and public observations stay in the player interface.
The IL programs own taking the key, checking the guard, unlocking and changing
rooms. `look`, `examine`/`x`, `inventory`/`i` and `help` are passive reads. Compass
names and `n/ne/e/se/s/sw/w/nw/u/d` resolve to `go` against visible targets and
aliases, with the same freshness checks. Unsupported targets cause no action.
An interactive terminal displays `> `; piped and model protocols have no prompt.

## Scene content envelope

`fdisbull-il-scene-1` is a small projection envelope, not a new UIL core version.
It contains exactly `format`, `programs`, `contexts`, `objects` and `partial`.
It admits at most 1 MiB, 128 programs, 64 contexts and 256 objects.

- `programs` maps private names to existing, unchanged `fdisbull-il-1` documents
  or `{"revision":"immutable-project-IL-id"}` references. Programs share the
  same typed variable declarations. The legacy `udl`/`uil` roles keep their
  existing meaning; no role rewrite is needed.
- `contexts` contain public `id`, `title`, `description` and a private `when`
  condition in the existing IL condition vocabulary. Exactly one must match.
- `objects` contain public `id`, `context`, `label`, `aliases`, `description`
  and private `bindings`. Each binding names `verb`, `program` and optional
  `item`. Optional `visible_when` and `inventory_when` reuse IL conditions.
  Inventory membership takes precedence over the object's original context.
- `partial` declares coverage. Missing or ambiguous context coverage gives an
  incomplete observation, not an invented room.

All conditions/programs are validated before play. Numeric widths, wrapping,
requirements and effect order are those of the existing evaluator. State is
held once, in the backend; the player owns no duplicate simulation. Public
responses omit programs, state variables, source evidence and failure details.
Authors must still qualify public descriptions and labels: validation cannot
establish their truth or stop a package's author from deliberately disclosing
hidden knowledge. The complete private package must not be given to a model
whose knowledge is restricted to the public interface.

A project-backed scene can be served as follows:

```sh
python -m fdisbull.il_scenes /private/scene.json \
  --project /private/source.fdb --version 1 --state /private/entry-state.json
```

Revision references are loaded with the existing immutable source-span/hash
checks, then the project closes before play. Reopening and checking a stored
revision requires no debugger. `--state` is an explicitly supplied typed
witness; the adapter does not infer a parser object or repair an unqualified
source entry. Inline evidence remains a claim unless checked against a project.
The automated source example uses authored v3 bytecode, not retail story data.

## Execution and failure boundaries

Only pure IL state/text effects execute. A false `require` gives a generic
refusal. Unsupported media/input or other evaluation failures are incomplete
and commit no proposed state. A confirmed pure-IL commit remains confirmed if
its destination falls outside scene coverage; the next observation is incomplete.
No native host action, original input, autonomous clock, random stream or full
UDC compiler is supplied by this adapter.

Action text is conservatively capped at 32 KiB of UTF-8 output across all text
nodes and branches before dispatch. Existing IL node/depth/size limits also
apply. Interactive commands are limited to 4096 bytes. The process transport
has a 1 MiB response limit and a deadline covering the whole request, including
partial replies and blocked writes. A failed exchange closes the owned process;
an uncertain action is not retried or relabelled rejected.

`--backend-command` executes a caller-selected local program without a shell.
It is a trusted content service, not executable authority supplied by a scene.
`--backend-timeout` defaults to 60 seconds and admits finite values up to 60.
For existing TCP `--connect`, it bounds connection and socket inactivity, not
the absolute duration of a continuously trickling response. Generic caller-owned
`JsonLineBackend` streams retain their caller's blocking policy.

## Model testing

The same service works with the existing live-turn/external-agent interface:

```sh
PYTHONPATH=src:player python -m fdisbull_player \
  --backend-command "python -m fdisbull.il_scenes examples/z/key-and-gate.json" \
  --backend-timeout 3 --live \
  --agent-command "python /private/model-driver.py" \
  --max-turns 20 --max-actions 8 --wall-seconds 60 \
  --transcript /private/new-transcript.json --quiet
```

The model driver receives `turn`, public `observation` and `last_outcomes`, and
returns `commands`, `narration` and `done`; see [live player](PLAYER_LIVE.md).
`--quiet` keeps the full transcript in the private file and prints only session
status, so a long benchmark does not flood the calling chat with narration.
The backend supplies **in-memory** save/load slots for bounded sessions. These
are not durable saves: restarting the service starts from the declared state.
`--save-dir` belongs to local `--package` mode and is rejected with a content
service. A future durable service owns its own persistence contract.

For comparisons, start a fresh service per run; pin the scene/package digest,
source IL revisions, initial witness, parser/observation policy and model budget.
Record verified goals, commands, refusals, incomplete results, wall time and
output size separately from narration. This candidate demonstrates protocol
compatibility and repeatable content, not a model ranking, a complete benchmark
suite or whole-game equivalence. Timing here is authored state/text behavior;
it must not be advertised as original continuous gameplay.

## Release probes and remaining work

[Verification](VERIFICATION-Z-SCENES-2026-10-29.md) records the installed 0.22.0
output-amplification and silent-peer probes, candidate protection and debugger-free
play. They are reproducible without proprietary assets:

```sh
python examples/z/verify_release.py --python /path/to/installed-0.22-python \
  --output /private/new-probe-output
```

Raw large output stays in the private directory; the checker prints only counts.
These observations do not identify the cause of the two damaged ChatGPT chats.
Follow-up for core maintainers: give `il-run`/other tool responses explicit
output budgets or artifact references. This candidate bounds the Z path, while
the installed core CLI's repeated-event serialization remains a separate seam.
