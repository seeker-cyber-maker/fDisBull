# Durable semantic history

See `tools/world_history.py`, `tools/history_provider.py` and
`tests/test_world_history.py`. The history ledger is game-neutral; selected
Syndicate native collectors live in the accompanying research handoff.

Use a dedicated journal. Every event is immutable through the API and each source
occurrence has a distinct identity. The UI can summarize repeated hits, but raw
records and non-damage notices remain separately queryable. Explicit stream forks
keep checkpoint replays from overwriting earlier events. No event read executes
a guest action. History capture and actions still require a shared owning
orchestrator before general live integration.

Player projections are explicitly supplied and default to no disclosure.
Diagnostic knowledge is not ordinary player perception. Terminal health sentinels
and contacts are not numeric damage. See the
[D006 report](https://chatgpt.com/library?file_id=libfile_07414ad9ef808191842d0650969bb02b&account_id=personal)
and [world-event contract](../../docs/WORLD_HISTORY_DAMAGE_CONTRACT.md) for the
original-code evidence and unresolved coverage. The
[D007 mixed-state study](../../research/syndicate-rewind/2026-11-02/README.md)
exercises history forks and explicit intervention records using authored data;
it does not restore a native guest.
