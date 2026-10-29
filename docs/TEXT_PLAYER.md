# Standalone text player

`player/` is an independent Python standard-library consumer. It does not import
fDisBull or need the debugger. Install it from that directory with
`python -m pip install ./player` or run it without installation from the
`player` directory with `python -m fdisbull_player`. This first slice is a
text projection and a small declarative runtime, not an AGI interpreter, UIL
implementation, original-game emulator, or evidence of game equivalence.

```
python -m fdisbull_player --package slice.json
python -m fdisbull_player --connect localhost:12345
```

Enter commands one per line; `quit` exits. `look`, `inventory`, `help`, and
`examine <object>` are passive projection reads: they neither call `act` nor
advance the local runtime. They are not a game's own potentially time-consuming
look action. Commands such as `go east`, `take key`, and `use key on gate` resolve
against publicly visible labels and aliases. This version requires a visible
target for every action and does not provide conversational parsing. Object
identities must be unique across visible objects and inventory. A target's public
`verbs` declares the allowed verb; availability and semantics remain backend
responsibilities. Ambiguity prompts for a numbered choice without dispatch or
time advancement. An incomplete observation, unresolved target, unsupported
verb, or changed context prevents dispatch. The player reobserves before
sending, compares the context ID and opaque token, and sends that token to the
backend. The backend **must** atomically check it at dispatch and change it when
any relevant observation or action availability changes. Otherwise the player
cannot close the race between its last observation and execution. The backend
also owns any continuously running time policy; this player cannot pause it.

Only the explicitly selected public fields are rendered; private backend
fields are ignored. Public labels, aliases, IDs, descriptions, verbs and action
messages must themselves be safe for the player profile. The backend must not
encode hidden information in those fields or in the token. The public backend
must avoid revealing private guard details through different error messages.
The player reports the returned action status and public message rather than
inferring success from submission. `accepted` does not mean completed.

## JSON-lines backend

The client sends one UTF-8 JSON object per line and expects one JSON response
line, in order, on the same connection. Each line is limited to 1 MiB in UTF-8, including the newline; an oversized or incomplete line ends the connection. `{"op":"observe"}` returns:

```json
{"complete":true,"context":{"id":"room","token":"opaque-revision","title":"Room","description":"A room."},"objects":[{"id":"east","label":"east","aliases":[],"description":"An exit.","verbs":["go"]}],"inventory":[],"coverage":{"partial":true}}
```

`{"op":"act","action":{"verb":"go","target":"east","item":null,"context_token":"opaque-revision"}}`
returns an object with `status` (`success`, `rejected`, `incomplete`, or
`accepted`), boolean `complete`, and public string `message`. It may contain
fresh `observation` and `assistance`; the player displays recognized movement or assisted-travel assistance and does not render the embedded observation.
An incomplete observation or malformed public shape is withheld. Transport
errors terminate the CLI rather than inventing an outcome. Use a trusted local
endpoint: this protocol supplies no authentication or encryption.

## Local declared runtime

The package is a self-contained JSON description of an authored semantic slice.
The `--package` file contains private state, guards, future transitions, and
other authored definitions in ordinary readable JSON. A player or agent with
filesystem access can inspect them; the public projection only limits what is
returned through the player interface. Use a separately controlled backend and
restrict filesystem access when a player must not see the package contents.
No code is executed from it. It has declared public contexts with per-context objects, a shared inventory,
and private state. Dynamic descriptions, arbitrary expressions, randomness,
services and signals are outside this
first runtime. Local checkpoint save/restore is described in [PLAYER_LIVE.md](PLAYER_LIVE.md). State is not automatically exposed. In particular,
the author must not make public descriptions or messages depend on hidden facts
unless that disclosure is explicitly authorized. Each action is matched exactly
by `verb`, `target`, and `item` (use JSON `null` for an unused item). All guards,
steps, scheduled effects and the outcome declaration are checked before any
effects. Missing/unknown definitions produce `incomplete` with no effects.
A false guard rejects without effects or time. The runtime does not dynamically
re-evaluate guards during an action.

```json
{
  "format":"fdisbull-text-slice-1",
  "state":{"position":0,"health":10},
  "context":{"id":"room","title":"Room","description":"A room."},
  "objects":[{"id":"east","label":"east","aliases":[],"description":"An exit.","verbs":["go"]}],
  "inventory":[], "partial":true,
  "actions":[{"verb":"go","target":"east","item":null,"guards":[],
    "steps":[
      {"effects":[{"op":"add","key":"position","value":1}],"ticks":1},
      {"effects":[{"op":"add","key":"position","value":1}],"ticks":1}],
    "status":"success","message":"Moved east."}],
  "scheduled":[{"tick":2,"effects":[{"op":"add","key":"health","value":-2},{"op":"event","name":"hazard"}]}]
}
```

A multi-context package can replace `context`, `objects`, and `partial` with
`initial_context` and `contexts`. The latter maps each public context ID to
`{"context":{"id":"...","title":"...","description":"..."},
"objects":[...],"partial":false}`. IDs must match the mapping keys. An action
may specify its `context` ID; omitted means it is eligible in every context.
`{"op":"context","id":"hall"}` changes to a declared context. The next
observation exposes that context's objects, and its token changes at the action
boundary. Inventory is shared between contexts. Each public object ID must be unique across all contexts and inventory.

A guard is `{"key":"name","equals":value}`; its key must exist and the value
must have the same JSON type as the initial state. `{"carrying":"key"}` tests whether the declared object is in inventory. Each step applies its effects
in order, then advances its nonnegative integer `ticks`, one at a time. At each
new tick, scheduled entries for that absolute tick run in package order, and
their effects run in order. Effects are `set` (existing key, same JSON type),
`add` (existing integer key and integer value), `event` (string name recorded
with the current tick), `context` (move to a declared context), `carry` (move the declared object from the current context into inventory), `drop` (move it from inventory into the current context),
and `stop` (stop immediately with incomplete status;
prior effects and elapsed ticks remain). `runtime.state`, `runtime.tick`, and
`runtime.events` are investigator-side Python inspection, not player output.
A carry or drop whose object is not at the required location makes the action incomplete before effects; the whole sequence is checked on a shadow state. Each scheduled tick is reached at most once. Integer values and arithmetic use
signed 64-bit bounds; overflow is detected on a shadow execution before any
effects. One action may advance at most 10,000 ticks. Unknown fields in action,
guard, step, effect or scheduled definitions are refused as incomplete rather
than ignored; this keeps future semantic extensions from silently changing the
meaning of an older runtime. Extra public projection fields are ignored. A successful message is authored
semantics, so its correctness requires package qualification; loading a package
is not proof it matches a source game. A partial stop never rolls back earlier
effects. Without live mode, local state is in memory and resets when the player restarts.


The optional authored synthetic `player/examples/key-and-gate.json` in a source checkout is a two-room
example: try `go east`, `take key`, `use key on gate`, and `go east`. The
content package is a separate input to this player and its generic interpreter.
A future source-specific parser can produce such content without becoming part
of the player; this example makes no claim of AGI or UIL coverage, original-game
behavior, or qualification against an original.

For automatic checkpoints after model turns and bounded external-agent story play, see [PLAYER_LIVE.md](PLAYER_LIVE.md).
