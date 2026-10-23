# Agent protocol

`fdisbull serve --project FILE.fdb` reads UTF-8 JSON lines and writes one JSON response per line. There is no network server. `fdisbull request '{...}'` performs one request. All commands also have CLI equivalents.

Request: `{"id":"caller-chosen","method":"status","params":{}}`.
Response: `{"id":"caller-chosen","ok":true,"result":{...}}` or `{"id":"caller-chosen","ok":false,"error":{"type":"ValueError","message":"..."}}`.

Include `project` in params when there is no session default, or to override it. Paths are local to the process. Addresses accept integers or integer strings (`0x...` hexadecimal recommended). Returned addresses are hex strings so JSON clients cannot lose 64-bit precision. Counts/version IDs require integers. Non-finite JSON numbers are rejected.

| Method | Required params beyond project | Optional params |
|---|---|---|
| import | path | arch, bits, base, entry |
| status | | version |
| analyze | | version, start, max_instructions (1–1,000,000; default 10,000) |
| functions | | version, limit (1–10,000), offset |
| disasm | | version, address, lines (1–500) |
| xrefs | address | version, direction (`to`/`from`), limit |
| rename | address, name | version, author |
| comment | address, text | version, author |
| patch | address, data (hex bytes) | version (parent), label, origin |
| versions | | |
| issues | | version, limit |
| render | output | version, address, lines (1–200), format (`png`/`svg`) |
| help | no project required | |

One binary, architecture, bitness and little-endian decode context per project. All decoded/reference/annotation keys include code version and context. `version` defaults to the numerically newest version. The work queue persists after a budget-limited run. Reanalysis preserves annotations. Function records are candidates, not proven boundaries; xrefs retain their decoded evidence source. `issues` exposes pending/invalid/outside work and unresolved indirect flow.

`disasm` returns stored rows ordered by address, including labels, comments, incoming xrefs and the snapshot digest. Gaps do not imply code was decoded. `render` uses that same stored snapshot and fails if there are no rows; it does not trigger analysis. Exporting over the active database or its SQLite sidecars (including aliases) is rejected.

Limits: 64 MiB original input and mapped image; patch 1 byte–1 MiB within one region; annotation 1–4096 characters; name at most 256 characters without controls; JSON line at most 1 MiB. An oversized request closes the stream; ordinary malformed requests return errors and the session continues. SVG escapes annotations. Render bounds prevent unbounded image allocation. Imports never run guest code.
