# Offline native RPC census input

`agent_server.upstream.cpp` is the exact complete
`src/agent/server/agent_server.cpp` from DOSBox-X baseline
`029bd65c5dcc7cdc7f2e14e35278620d9707d969`. It is 160,141 bytes, not a complete
emulator checkout. Its byte identity and retained corresponding-source archive
provenance are pinned in `upstream.json`. The upstream license is preserved in
[`../COPYING`](../COPYING); the source file is copied without alteration.

The ordinary source check is fully offline:

```sh
python scripts/dosbox_rpc_census.py
python -m pytest -q tests/test_dosbox_rpc_census.py tests/test_dos_migration.py
```

The helper replays each profile's complete patch against this one member in
memory. It verifies the baseline, patch hash, resulting server hash and size
against the current stable/layers source manifests. It then enumerates the
complete `IsKnownMethod` filter and every `parsed.method` comparison/dispatch
use. Unknown grammar, undeclared dispatch names and declarations without a
reviewed dispatch fail closed. Literal names are not filtered by namespace.

`input.mouse.state` is the existing non-mutation fallback of the shared mouse
prefix handler. Its explicit provenance entry requires the corresponding
declaration, prefix and `AGENT_MouseGetState` statement; a new method cannot be
classified merely because its name shares that prefix. This remains a source
interface check, not a proof of native handler behavior.

The complete source exposes unchanged upstream diagnostics
`debug.output.read` and `debugger.execute_command`. They occur outside all
stable/layers diff hunks, so the former patch-text-only inventory check missed
them. The current census is 36 stable and 37 layer-profile methods. The latter
adds `layers.configure`; all 37 migration rows remain unqualified.

When a complete patch changes, update its ordinary source manifest as usual.
The census reconstructs and checks the new result automatically; there is no
generated method list to refresh or accept blindly. A different baseline or
dispatch grammar requires a separately inspected upstream member/provenance
update and corresponding tests. No network fetch, full upstream archive,
compiler, native executable or user game is needed by ordinary tests.
