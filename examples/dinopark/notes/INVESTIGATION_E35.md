# E35 investigation example: keyboard, leaderboard persistence and save padding

Read from the user's Space/Library on 26 October 2026. The latest visible
investigation packet was **DinoPark-fDisBull-0.16-E35-Keyboard-and-Saves.zip**,
alongside these two source documents:

- [START_HERE.md — Resume DinoPark after E35](https://chatgpt.com/space/file/libfile_67a0361f628c8191b89fc275c5b0cc65)
- [REPORT(6).md — keyboard, original leaderboard persistence, and save padding](https://chatgpt.com/space/file/libfile_70591e7e36a8819193869ed337e0f7ac)

This note summarizes those reports. The external Linux runs and save-padding
audit were **not independently rerun for this commit**. The linked
[Mac replay and its receipts](../../../docs/VERIFICATION-DINOPARK-LEADERBOARD.md)
are a separate, directly observed acceptance track. Library source links require
the user's account; this public summary retains the useful example without
copying the private packet, game files, score table, native states or databases.

## Current reported state

| Investigation | Reported observation | Claim boundary |
|---|---|---|
| Guest keyboard and first score | Linux x86-64 CPython 3.13.5, tagged fDisBull 0.16.0 `e1e3fb4`: typed `TIGA26` and Enter; original game inserted rank 7 at 9,168 | Existing PMM save, not an earned victory from NEW GAME |
| Persistence and next insertion | A new DOSBox process read the first score file, then inserted `RELOAD` at 9,308, retaining `TIGA26` at rank 8 | Two original-program runs in private copies, as reported in E35 |
| Save-file trailer | Final 100 bytes at offset 4,053 of the 4,153-byte DINOSG format were zero in eight supplied saves; original writer clears/writes them and reader reads/discards them | Pinned original build only; remaining save fields still need writer/consumer evidence |
| Remaining work | A profitable NEW GAME route; meaningful unknown save-field writers and consumers; rendering/audio later | The leaderboard acceptance does not establish a complete economic strategy |

The report records 52 focused tests passed and six skipped. That is its selected
test result, not a full-suite or complete native-coverage result. Both reports
identify original EXE SHA-256
`2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c`.

## A useful example of observation discipline

E35 describes a failed late checkpoint whose screenshot resembled the name
dialog, but queued keyboard input did not update it. A trace later entered BIOS
text output and the Enter path reached a DOS shell. The report does not establish
the root cause. Its working route instead restores an earlier sale-confirmation
state, stops at the reported valuation return `38FF:55A7`, advances about 250
requested guest milliseconds, then types and confirms with Enter.

That is a practical example for [bounded observation waits](../../../docs/OBSERVATION_WAIT.md):
use an explicit, verified return breakpoint or readiness predicate; do not treat
a screenshot, scene name, consumed input queue or elapsed delay as proof of
application readiness. No universal readiness address is supplied here, and the
E35 address has not been newly byte-verified by this note.

Our companion [mouse-OK replay](../verify_leaderboard.py) starts from a fresh
process and uses the original OLD GAME and office UI. Its tested Mac route ends
the modal text editor with Ctrl+O, confirms the preserved name in guest memory,
then clicks OK. Its second process compares all 250 leaderboard bytes after the
game's actual reader returns, before another write. The two routes provide
different examples of crossing the same input/persistence boundary; neither is
a timing-portability or deterministic-replay claim.

## Release status clarification

The E35 report's statement that 0.16.0 had no separate release page reflects its
earlier check. A fresh GitHub read for this handoff confirmed that
[v0.16.0 is published](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.16.0),
at `e1e3fb4913d6d8fae7893c2c9b8edf364d144953`, published
`2026-10-26T22:07:12Z`, with seven assets including the updated Linux DOS offline
kit. The release tag and assets are unchanged by this evidence commit.
