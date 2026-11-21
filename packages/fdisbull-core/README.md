# fdisbull-core

Shared analysis and transport mechanisms used by fDisBull and DotBox. This package
requires Python 3.12 or later and has no runtime dependencies beyond the standard
library. Importing it does not launch an emulator or capture, store, or change
live memory. Product adapters own live operations and process lifetime.

`fdisbull_core.memory_search` searches caller-supplied immutable memory snapshots,
narrows scalar candidates across compatible observations, and creates non-writing
edit plans. Existing `fdisbull-*` serialized format identifiers remain unchanged.
The calling product owns live observation identity, storage, and any eventual
guarded action.

`fdisbull_core.pipe_rpc` supplies bounded JSON-lines exchange over an already
owned private pipe pair. Both DOSBox adapters use the same framing, deadline,
response-identity and no-replay rules. They retain their public error classes,
request ID prefixes, launch defaults, input ownership and cleanup behavior.
The shared transport does not start a process, acquire a guest, or enable input.

Build independently with `python -m build packages/fdisbull-core` from the shared
repository, or `python -m build` from this directory. Install this package before
installing either product from source; both products pin its version explicitly.
Run its authored-byte checks with `python -m pytest packages/fdisbull-core/tests`.
`PROVENANCE.json` identifies the unchanged initial kernel and the transport
extraction. Applications pin `0.1.0.dev2`, which includes both modules.
