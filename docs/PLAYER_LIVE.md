# Live turns and bounded story play

The independent player can restore the latest checkpoint before its first model
turn and save after each turn. This persistence is outside the commands supplied
by the model: the model does not need a save command. A turn may contain several
commands. A partial action can have real effects; the post-turn save includes
those effects. An incomplete action or unavailable outcome stops the remaining
commands in that turn; self-play stops after the incomplete turn. Check the returned checkpoint status: an incomplete save is not a
saved game, and the session stops accepting further turns after a save failure.
An invalid, corrupt, incompatible, or otherwise incomplete checkpoint stops the
session; only a reported missing checkpoint starts a fresh game.

For a local package, checkpoints are private JSON files in the user data
location under `fdisbull-player/<package hash>` by default. On macOS this is
`~/Library/Application Support`; elsewhere it is `$XDG_DATA_HOME` or
`~/.local/share`. Use `--save-dir` to select an explicit directory. Existing
files there may contain private game state, so protect the directory. The
runtime checks package identity, state types and values, context, entity
locations, tick, and events before applying a restore. A restore changes the
context token epoch and discards any pending clarification. It writes a temporary
file and atomically replaces the checkpoint, syncing the file and directory.
A failed durability operation is reported as incomplete even if a replacement
may have occurred. Checkpoints are JSON data, not executable pickle files.

```
python -m fdisbull_player --package slice.json --live --save-dir /private/path
```

Each standard-input line is one JSON object, for example
`{"commands":["look","take key","inventory"]}`. The output is one JSON
object with the restore result, public command/outcome pairs, and checkpoint
result. EOF exits. `--max-actions` limits the number of commands per turn.
Without `--live`, the original interactive one-command-per-line interface remains
available and local state is not persisted automatically.

The same mode supports `--connect host:port` if that backend implements
`{"op":"save","slot":"live"}` and
`{"op":"load","checkpoint":"live"}`. A save response must include
`status: "saved"`, `complete: true`, and a nonempty opaque `checkpoint` ID.
A load response has status `restored`, `missing`, or `incomplete` and boolean
`complete`; only complete `restored` or complete `missing` permits play. The
backend is responsible for its own checkpoint durability, identity, validation,
and token invalidation. The client cannot verify those properties remotely.
The protocol has no authentication or encryption; use a trusted local endpoint.

## External story agent

```
python -m fdisbull_player --package slice.json --live \
  --agent-command 'python /path/to/agent.py' --max-turns 20 --max-actions 8 \
  --wall-seconds 60 --agent-timeout 10 --transcript /private/story.json
```

The command is split into arguments and launched without a shell. The persistent
process receives one JSON line per turn with `turn` (zero-based), a public
`observation`, and `last_outcomes` from the preceding turn. It responds with a
JSON line containing `commands` (an array of player commands), `narration`
(a string), and `done` (a boolean). Narration, selected commands, and observed
outcomes are printed; narration is authored by the agent and does not determine
game state. A structured transcript is optional and created privately without
overwriting an existing file. It contains public observations only indirectly
through outcomes and may still contain sensitive narration or commands.

Limits bound turns, commands per turn, response size, time spent waiting for an
agent response, and the time at which new turns are started. The wall limit is checked again
after observation and after the agent response, before dispatching a turn. A
blocking backend operation itself cannot be preempted by this wall limit. The external program
is trusted code and inherits the user's environment and filesystem access; the
player does not provide an isolation boundary. It makes no model API or network
call itself and includes no model credentials. A supplied agent is responsible
for its own model, if any. A synthetic scripted agent demonstrates the protocol;
that is not evidence of autonomous LLM play or source-game equivalence.

Voice is planned future work. Qwen TTS is available locally according to the
user; speech recognition availability and suitability remain unqualified.
Both sides and their combined interaction still need qualification. No built-in
voice or speech-to-text capability is provided here.
