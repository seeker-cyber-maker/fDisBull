# fdisbull-core

Shared deterministic analysis kernels used by fDisBull and DotBox. This package
requires Python 3.12 or later and has no runtime dependencies beyond the standard
library. It does not launch an emulator or capture, store, or change live memory.

`fdisbull_core.memory_search` searches caller-supplied immutable memory snapshots,
narrows scalar candidates across compatible observations, and creates non-writing
edit plans. Existing `fdisbull-*` serialized format identifiers remain unchanged.
The calling product owns live observation identity, storage, and any eventual
guarded action.

Build independently with `python -m build packages/fdisbull-core` from the shared
repository, or `python -m build` from this directory. Install this package before
installing either product from source; both products pin its version explicitly.
Run its authored-byte checks with `python -m pytest packages/fdisbull-core/tests`.
`PROVENANCE.json` identifies the unchanged initial kernel extraction.
