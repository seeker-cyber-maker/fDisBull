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

`fdisbull_core.agi_scene` projects the experimental QEMU AGI actor-position
profile from a stopped snapshot and selected scene records. It validates source
and session identity, applies new effects transactionally, and separates current
actor facts from gaps in observed history. It has no QEMU/process dependency;
the optional native experiment adapter owns capture and explicit controls.
See the [consumer contract](https://github.com/seeker-cyber-maker/fDisBull/blob/codex/agi-scene-consumer-20261121/native/qemu-agi/SCENE_CONSUMER.md)
in the shared source repository.

Its pure `plan_literal_position_edit` API binds a captured literal-position
witness to exact source bytes and returns a detached coordinate-edit proposal.
It performs no writes or execution. A fresh candidate replay must establish the
actual outcome because later assignments may override the edited instruction.
See the [edit/replay contract](https://github.com/seeker-cyber-maker/fDisBull/blob/codex/agi-scene-position-edits-20261121/native/qemu-agi/SCENE_EDITING.md).

The distinct `plan_variable_position_override` API deliberately converts one
witnessed variable-position instruction to literals. It preserves variable IDs
and historical read values, makes the changed binding explicit, and leaves fresh
replay to establish placement and downstream effects. See the
[variable override contract](https://github.com/seeker-cyber-maker/fDisBull/blob/codex/agi-variable-position-overrides-20261121/native/qemu-agi/VARIABLE_SCENE_EDITING.md).

`fdisbull_core.agi_view.decode_view_cel(payload, *, loop, cel)` decodes one
effective cel from an uncompressed DOS AGI 2.917 EGA VIEW payload. It returns
row-major indexed pixels, dimensions, transparency, effective mirroring and
payload-relative source boundaries with the resource SHA-256. Transparent
trailing pixels are retained when a row is mirrored. The bounded reader checks
referenced directories, cel headers and RLE streams, permits exact shared
pointers and rejects overlapping structures. It uses only the standard library.

This independently authored decoder follows the
[pinned ScummVM VIEW format and mirroring reference](https://github.com/scummvm/scummvm/blob/f7403b6efaae2f033e8abea80b3fb6bee5303369/engines/agi/view.cpp).
Its source pixels describe a static resource. Current actor visibility,
placement, priority composition, screen palette and rendering state require
separate runtime evidence. Alternate platform layouts, early loop-header
mirroring and AGI256 are outside the explicit profile.

Build independently with `python -m build packages/fdisbull-core` from the shared
repository, or `python -m build` from this directory. Install this package before
installing either product from source; both products pin its version explicitly.
Run its authored-byte checks with `python -m pytest packages/fdisbull-core/tests`.
`PROVENANCE.json` identifies the unchanged initial kernel, the transport
extraction, the independently authored scene consumer/planners and the VIEW cel
decoder. Applications pin `0.1.0.dev6`, which includes all four modules.
