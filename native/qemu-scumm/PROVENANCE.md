# Provenance

The core is independently authored from bounded encoding and behavior facts.
No ScummVM implementation is copied into the GPL-2.0-or-later overlay. ScummVM
is GPL-3.0-or-later; implementation imports need a separate compatibility review.
Source inspection does not independently qualify original interpreters.

## Pinned v2 runtime reference

ScummVM tag `v2.9.0`, tag object
`509833d62bd3f766f1d44114ab652956339a4d8e`, resolves to commit
`38af1883a2eb7a622c31bfc3708888bbcc47db48`. Git resolution and HTTPS downloads
were checked on 2026-11-24. [reference_sources.json](reference_sources.json)
records immutable raw URLs, lengths and SHA-256 for the consulted runtime,
verb and navigation files.

- [Opcode/control semantics](https://github.com/scummvm/scummvm/blob/38af1883a2eb7a622c31bfc3708888bbcc47db48/engines/scumm/script_v2.cpp): resource actions, cursor flags, cutscene state.
- [Resources](https://github.com/scummvm/scummvm/blob/38af1883a2eb7a622c31bfc3708888bbcc47db48/engines/scumm/resource.cpp): old-bundle lengths, room resolution, locks, mapper ordering.
- [Variables](https://github.com/scummvm/scummvm/blob/38af1883a2eb7a622c31bfc3708888bbcc47db48/engines/scumm/vars.cpp): v2 variable indices.
- [Script lifecycle](https://github.com/scummvm/scummvm/blob/38af1883a2eb7a622c31bfc3708888bbcc47db48/engines/scumm/script.cpp): child entry and freeze/scheduling prerequisites; scheduling is not implemented here.
- [Camera](https://github.com/scummvm/scummvm/blob/38af1883a2eb7a622c31bfc3708888bbcc47db48/engines/scumm/camera.cpp): why end-cutscene requires actor/camera/room effects.
- [Verb state](https://github.com/scummvm/scummvm/blob/38af1883a2eb7a622c31bfc3708888bbcc47db48/engines/scumm/verbs.cpp): slot lookup, deletion and the distinction between authored state and rendered rectangles.
- [Room layout](https://github.com/scummvm/scummvm/blob/38af1883a2eb7a622c31bfc3708888bbcc47db48/engines/scumm/room.cpp): whole-resource v2 header, box and matrix extents.
- [Box geometry and routing](https://github.com/scummvm/scummvm/blob/38af1883a2eb7a622c31bfc3708888bbcc47db48/engines/scumm/boxes.cpp) and [v2 actors](https://github.com/scummvm/scummvm/blob/38af1883a2eb7a622c31bfc3708888bbcc47db48/engines/scumm/actor.cpp): stored next-hop matrix, integer endpoint adjustment, boundary projection and restriction flags.

Platform branches and game-specific repairs are not generalized. The isolated
context's 256-variable/32-actor bounds, nesting rejection, strict resource-index
fault, UI revision and immutable bank are explicit processor design choices,
not original engine limits. Earlier v0 facts used moving/distribution source;
they do not gain original-v0 qualification from this v2 work. Intake detection
tables still need a pinned detection reference before a release claim.

The 100-verb bound follows the pinned reference's `resource_v4.cpp` allocation;
it is not evidence of an original interpreter's exact allocation. Native verb
execution is restricted to the declared Amiga-v2 profile. Canonical v1/v2
decoding shares the reference's encoded-string extent rules.

[NAVIGATION.md](NAVIGATION.md) records the independently authored host planner's
source/state binding, table policy, integer rounding, caller-declared flags and
limits. It uses SCUMM's own room format rather than duplicating DotBox's generic
AGI map search. Reference-informed proposals are not a comparison against
original-engine movement traces.

## QEMU and authored validation

Lifecycle/registration scaffolding was adapted from the project's GPL-2.0-or-later
AGI overlay at `5c59c9a03e8992149fcc2643dcf15298faa14816`. QEMU 10.0.13 archive
SHA-256 is `4a59b74dac7ead8b162a7c4595dcbbeebe989b90c89cfe6bb4dec5447342f6fa`.
Architecture bit 26 is an isolated-source proposal; combined AGI/SCUMM native
builds remain unqualified. QEMU's local `include/system/reset.h` documents the
explicit resettable registration now used by the machine.

The clean upstream target builds and runs in the recorded Debian 13 cloud
environment. Authored fixtures cover portable semantics, QMP/TCG, resource
admission and reset. Private original-game probes retain source hashes and
explicit boundaries. Shared-core agreement and increased instruction progress
do not establish full game equivalence. Original data and resource banks remain
outside Git and public packages.
