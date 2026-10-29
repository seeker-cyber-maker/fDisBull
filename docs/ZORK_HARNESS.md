# Z-machine live harness

The Zork harness runs a user-supplied raw Z-machine version 3 story through an
explicitly selected Python interpreter with Jericho 3.3.1 installed. It does
not include or redistribute a story. Select an existing suitable environment;
do not install into or modify a shared Python environment merely to use this
feature. The worker is a separate process, with bounded messages and deadlines.
Its recorded identity includes the story, interpreter, Jericho and native library
hashes. A failure or timeout requires reset or restore before continuing.

```sh
fdisbull zork /path/to/story.z3 --python /path/to/python \
  --checkpoint /path/to/private-checkpoint.json
```

The CLI accepts `--resume STATE`, `--checkpoint STATE`, `--timeout-ms` and
`--seed`. It exchanges one JSON object per line on standard input and output:

```json
{"op":"observe"}
{"op":"command","text":"look"}
{"op":"save","path":"/path/to/private-checkpoint.json"}
{"op":"restore","path":"/path/to/private-checkpoint.json"}
```

`observe` returns the most recent captured observation without advancing the
guest. `command` sends an actual command to the guest; `look` is consequently
an actual guest action, not passive observation. If `--checkpoint` is set,
a successful command is followed by an autosave. Checkpoints contain private
game state and transcript data. They are tied to the recorded identity and
seed; their hash detects accidental changes but is not authentication. Treat
checkpoint files as trusted local inputs, not as proof that a state is safe or
authentic. Current mode reporting remains `unknown`; no per-model-turn format
or full input-mode detection is promised.

`inspect_story`, the partial v3 decoder, and Z-text decoder are inspection
facilities, separate from execution. The initial and repeat mailbox source slice
has been investigated at story offsets `0x80a3` (attribute 11) and `0x80a6`
(attribute 3), with native observation at `0x17ab`; see the bounded verification
example at `examples/zork/verify_harness.py` for the exact conditions and
results. This qualifies only the described slice. The parser, turn loop and
remaining story behavior are outside that recovered IL; this is not whole-game
reconstruction or parity.

`fdisbull story-info STORY` inspects structure without starting a game.
`fdisbull zork-recover STORY` returns the packaged recovery profile's IL and
qualification metadata. Its `initial_story_state` is not an action-entry RAM
witness; execution requires the original parser's object binding and the
declared conditions. See [the fresh verification record](VERIFICATION-ZORK-2026-10-29.md).

The Python `NamedZorkHarness` accepts an authored finite mapping from scene names
to public-text matchers and actions with exact commands/expected response
substrings. It checks a single-use freshness token before dispatch. An unexpected
response latches the route until explicit reacquisition. This is a bounded
observation contract; a matching substring does not prove hidden game state or
readiness in an unqualified modal input mode.

For the separate live text host, `text-host --fair-play` declares assisted
travel disabled at startup. Its projection omits assisted-travel actions and
its travel entry point refuses them; ordinary movement remains available. The
policy is voluntary and is not a tamper-proof anti-cheat boundary. It cannot
prevent manual memory changes or debugger operations.
