# Zork I text-screen adapter for fDisBull 0.20

This local prototype connects the original DOS interpreter to a terminal or a
small scripted scene check. It uses the installed fDisBull Python API and a
compatible DOSBox backend. It was exercised with the supplied GOG Zork I story,
revision 88 / serial 840726; other editions and video configurations are not
qualified. No game files are included here.

Use a private copy of the game directory containing `_ZORK1.COM`, `SETUP.INF`
and `DATA/ZORK1.DAT`. Set the paths below to the user's actual files. The
project path must not already exist; it retains private runtime data. The
provided 0.20 installation includes the Python dependencies.

```sh
/Users/Shared/fDisBull/releases/0.20.0-4f7791b/venv/bin/python examples/zork_text/play.py \
  --game-dir /path/to/private/game \
  --backend /Users/Shared/fDisBull/releases/0.20.0-4f7791b/backend/native-macos-arm64/dosbox-x \
  --project /path/to/new-private-project.fdb
```

Type Zork commands normally. `:exit` closes the session without sending that
command to the game. The terminal shows the complete visible screen, including
earlier lines, on each turn; it is not a complete transcript, because the DOS
screen scrolls. Commands are restricted to at most 63 printable US-layout ASCII
characters. Timeouts and unexpected stops leave the action outcome unknown.
The adapter invalidates its ready state before delivery; never blindly retry an
uncertain command. Save/restore, `MORE`, dialogs, quitting through the game and
other input modes have not been qualified and may stop at the observation
budget rather than return a prompt.

`pilot.py` creates a fresh project, times the opening and performs an
evidence-checked route: open mailbox, look, send an unknown word, move north,
try blocked south, return west, and look again. It emits a JSON record containing
the exact screen observations and file identities and stores a screenshot in
the private project. Use the same arguments as `play.py` with a different new
project path, and add `--journal /path/to/new-private-journal.jsonl`.
Use `--receipt /path/to/new-private-receipt.json` to retain the
JSON; it contains game text and paths. Project creation and backend launch are included in the
reported start-to-action time; setup, extraction and code authoring are not.

For a named-action scene interface, run `scenes.py` with the same game,
backend, project and journal options, then send one action name per line:
`open_mailbox`, `look_west`, `unknown_word`, `go_north`, `try_south`, or
`go_west`. `:exit` closes the session. The contract is pinned to the two
game-file hashes below and checks them before every action. Scene identity is
derived from the displayed status and a mismatched or unknown scene refuses
input. It does not reveal hidden state or infer that every visible action is
enabled. `open_mailbox` specifically expects the first-opening response; other
outcomes remain unexpected or unknown, rather than being called success.

The journal records a flushed intent before input, followed by an observed
result, refusal or indeterminate outcome. An intent without a later result can
also mean interruption; never replay it automatically. The result distinguishes
queued input, unknown handler acceptance, displayed output, and unknown
persistence. The new screen must retain enough overlap to identify the command
echo as fresh; otherwise the result is unknown. JSONL contains visible game
text, so keep it private. This is an authored, bounded observation contract,
not canonical UIL, a reconstructed world model, or proof of game equivalence.

## E55 handoff review and application

The reviewed archive `DinoPark-E55-UIL-Research-Handoff.zip` has SHA-256
`e6f9da13a3ab1d1de485a496f5d807121bcd929ba67bd87256b449870aa718ea`.
Its 295 manifest payloads match their recorded sizes and hashes, with no extra
or duplicate entries. This verifies package consistency, not the underlying
experimental claims. Its `REPORT.md` and `docs/GAME-STORY-MAP.md` distinguish
input dispatch, semantic changes, control readiness, rendered content and
persistence; their order is action-specific. They also distinguish static,
bounded original, connected, live and artifact evidence. E55 reports bounded
ABOUT/DinoMart comparisons with named adapters and unresolved services; it does
not claim complete game or canonical UIL execution.

Those lessons shaped the named-action layer: exact source identities, separate
intent and result, scene and prompt guards, fresh response attribution, explicit
unknown acceptance and persistence, and durable partial records on failures.
No DinoPark-specific actor, signal or timing semantics were transferred to
Zork. This prototype leaves modal input, save/restart, true semantic memory,
scene package merging and complete text transcripts unresolved.

On 28 October 2026, the updated seven-command pilot passed on the original game.
One local run measured 0.753 s from import to first observed expected response
and 1.215 s to finish the route (including project import and launch, excluding
setup and authoring). Another actual named-action session refused `go_west`
while in West of House without sending input, then completed the mailbox,
north, blocked south, west and look actions. Its private journal is
`/tmp/fdisbull-zork-analysis.rBn9QZPl/scenes-e55.jsonl`, SHA-256
`fdc22562a5b591811710768e6f84614ea388de4701a54b15b3d729f34e537175`.
Temporary evidence can be removed by the operating system. The named-action
test is a bounded live observation, not independent proof of the E55 model.

The final code was rerun with seven expected observed responses; its ordered
15-event journal is `/tmp/fdisbull-zork-analysis.rBn9QZPl/pilot-e55-final.jsonl`
(SHA-256 `86955432d63ee898342a7e15effad7f0238cd56c61eae56a4de2e0ba8a2275d6`).
Its receipt is `pilot-e55-final.json` in the same temporary directory (SHA-256
`c97987c2a712caecf0e211117ae54ccb2c077661dbde84870442097763cf71ae`). This
run took 0.749 s to first observed expected response and 1.203 s for the route;
the same measurement boundaries and limitations apply.

## Observation boundary

The adapter reads the BIOS display metadata and the color text page from the
stopped guest. It accepts only 80x25 mode 3, page zero at offset zero. The
screen is CP437 text with per-cell attributes excluded from the returned text;
the screen hash covers the full character-and-attribute page. Prompt readiness
requires a bare `>` under the BIOS cursor, an empty input queue and two identical
samples separated by bounded guest execution. After a command, it also requires
a changed page. This is a useful *display heuristic*, not proof of an internal
Z-machine input opcode, and it cannot rule out every misleading display. Native
stops, unreadable memory, changed modes, uncertain delivery and exhausted budgets
are errors, not game success. The pilot separately checks command echoes and
fresh output plus room status; it does not infer hidden game state.

## One local measurement, 2026-10-28

With the installed 0.20.0 release and Apple Silicon backend, one successful
pilot imported the project in 0.200 s, launched in 0.409 s, reached a qualified
opening prompt in 0.065 s, and verified `open mailbox` in a further 0.093 s.
Total from project import start to first verified action was 0.768 s; the whole
seven-command route completed in 1.216 s. This was one local fast-forward run,
not an authoring-time, repeated-run or cross-machine benchmark. A preceding
route failed because `south` was assumed to return from the north side; the
actual game correctly reported boarded windows, so the qualified route uses
`west`. A captured after-frame was exported successfully after project reopen.

The exact game interpreter SHA-256 is
`2a6f366349be71ef4a164e3fc9c31a4a3d8c24ee6ddac93ed345c993c3562514`, story is
`0ae5ac229e79094ff368b6669356444af0f35e21d862a1baaa546989085c15fd`, and
backend is `1b0ec91f8a97fb34f336f898c3e9e02bf4559f314b2e4f92f3597f0c52c92277`.
The private run ID was `2ab0c89f0a5544f48ac34eeb586cc38d`; the after-frame
artifact `de546f04df784194b35e347215e2f6d2` has SHA-256
`690927f885ac489269b46dca1ecb3413c36c625281b6d4c19cd55f50523672c9`.
