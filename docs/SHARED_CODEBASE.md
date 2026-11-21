# Shared codebase, distinct products

This policy implements the user's direction to share reversing machinery while
keeping fDisBull and DotBox, their operating priorities and their Agent BBS
projects separate. This development integration is not a release or a
QEMU parity decision.

## Product responsibilities

| Product | Primary goal | Sufficient result for the task |
| --- | --- | --- |
| **fDisBull** | Program recovery and recompilation through **UDL → UIL → UDC**, across supported formats and architectures | The recovered contract or emitted implementation meets the semantic and equivalence checks required by that deliverable, with source, assumptions, coverage and unknown effects explicit. |
| **DotBox** | **Rapid self-harness development** that makes an original game usable promptly | A useful observation/control slice works for the selected intent, with a bounded outcome check and minimal reasonable delay. Complete recovery or recompilation proof is not a prerequisite for play. |

DotBox favors the earliest useful harness. Use a known applicable control for
the selected intent immediately. Learn only what blocks the next interaction;
retain partial world models, approximate predictions and useful hypotheses,
distinguished from current observed game state. Improve the model during play.
Optional naming, full structural analysis and UDL–UIL–UDC conversion do not
belong on the foreground play path. Existing latency profiles are evaluation
settings, not guaranteed response times or mandatory waiting periods.

fDisBull also investigates cheaply and reuses partial findings. Its stronger
verification applies when promoting a recovered contract or recompilation
result, not before every debugger query. Preserve its existing harness and
debugging capabilities as useful parts of that workflow.

Both products retain exact byte/address identity, honest uncertainty, bounded
operations and correct live ownership. Speed does not turn a candidate into a
fact, a queued input into its effect, or historical evidence into a fresh input
token. Reconcile unknown delivery before replay. Each product applies its own
acceptance policy to the same evidence; no global fast mode disables identity
or correctness checks.

## Source and package boundaries

| Location | Responsibility | Distribution |
| --- | --- | --- |
| `src/fdisbull/` | Analysis persistence, recovery/recompilation, architecture adapters and UDL–UIL–UDC workflows | `fdisbull` |
| `apps/dotbox/` | Cooperative play, game/world profiles, observations, action admission and latency policy | `dotbox` |
| `packages/fdisbull-core/` | Reusable deterministic mechanisms independent of either application's orchestration | `fdisbull-core` |
| `player/` | Standalone authored projection/text player | `fdisbull-player` |

The applications depend on the shared package; the shared package imports
neither application. DotBox does not need the full fDisBull application or its
Project database. The player remains independently installable. Keep separate
application environments when decoder or optional dependency versions differ.

The first extracted component is scalar memory search. Its implementation moves
unchanged into `fdisbull_core.memory_search`. The existing
`fdisbull.memory_search` import remains a compatibility adapter. DotBox exposes
the same kernel through a frozen-buffer API/CLI. Existing `fdisbull-*` search
and snapshot markers remain stable: they describe the data contract, not a
requirement to install the complete application.

Search candidates are locations satisfying a supplied comparison. Their game
meaning, liveness and suitability for control still need evidence. This slice
adds no live capture, live writes, automatic field naming or general harness
generator. Runtime capture, persistence, live admission and decoder wrappers
remain application responsibilities. Move another component when both
consumers benefit and explicit adapters preserve its contract. Do not keep a
second maintained copy after moving a kernel.

The shared package also owns bounded private-pipe JSON-RPC exchange in
`fdisbull_core.pipe_rpc`. Both DOSBox clients use that framing/deadline kernel.
Product adapters retain launch profiles, public error types, request prefixes,
EOF diagnostics, input ownership and process cleanup. The common exchange does
not start a process or transfer control. Both applications pin shared development
version `0.1.0.dev7`, which also carries the experimental AGI scene consumer,
position edit planners, bounded VIEW cel decoder and validated VIEW topology;
earlier memory-only and transport-only wheels cannot satisfy that package.

`fdisbull_core.agi_scene` is a deterministic snapshot/delta consumer for the
bounded AGI position profile. It does not import a product, launch an emulator
or change guest state. A thin adapter under `native/qemu-agi/` brackets stopped
capture and refreshes current actors when observation coverage is incomplete.
The history gap remains explicit; a fresh snapshot does not recreate missing
source witnesses. This shared mechanism is not a new default DotBox or fDisBull
runtime. See the [scene consumer contract](../native/qemu-agi/SCENE_CONSUMER.md).

The same module can plan a literal position edit from exact code bytes and a
captured witness. It returns a detached source proposal; a separately owned
candidate run establishes the actual resulting placement. A later unchanged
assignment may override the edited instruction. See the
[edit/replay contract](../native/qemu-agi/SCENE_EDITING.md).

The explicit variable-position override replaces one witnessed `position.v`
binding with literal coordinates while retaining its historical variable reads.
Unchanged source assignments do not imply unchanged final variables or other
actors: later `get.posn` can propagate the new position. The bounded
[variable override contract](../native/qemu-agi/VARIABLE_SCENE_EDITING.md) keeps
that consequence visible through separate candidate replay.

`fdisbull_core.agi_view` supplies a pure, standard-library-only decoder for
uncompressed DOS AGI 2.917 EGA VIEW cels. The independently authored Python code
uses the [pinned primary ScummVM reference](https://github.com/scummvm/scummvm/blob/f7403b6efaae2f033e8abea80b3fb6bee5303369/engines/agi/view.cpp)
for the resource format and effective-loop mirroring. It retains indexed source
pixels, transparency, effective orientation and exact resource boundaries and
identity. These static resources remain separate from observed actor state:
visibility, placement, priority composition and screen palette require runtime
evidence. The decoder does not launch a game or select either product's backend.

The shared initializer's development version also changes its identity in the
legacy DOSBox-in-QEMU Python guest. Prepared images containing the earlier
initializer must be regenerated before that legacy deployment is reused.
This AGI experiment does not rebuild or boot-qualify those images.

## Spectator presentation

fDisBull's preferred CLI spelling is `--spectator`; `--dot-mode` and `--window`
remain aliases for the existing `window` option. Python arguments, JSON methods,
metadata and artifact identities remain compatible. The native DOSBox view is
passive and belongs to the existing debugger-owned session. Supported Windows
backends retain their stopped-frame HTTP spectator. Opening a viewer does not
launch DotBox, enable host input, or change a backend's support/default policy.

DotBox retains its own visible play service and cooperative input policy.
Sharing transport does not route fDisBull through `dotbox serve` or merge their
project stores. A common native binary remains a separate qualification from
sharing the byte-identical base source.

## Independent builds and installations

The shared development package must be supplied explicitly until released.
From the repository root, install the product needed in its own environment:

```sh
# fDisBull environment
python -m pip install ./packages/fdisbull-core .

# Or, in a separate DotBox environment
python -m pip install ./packages/fdisbull-core ./apps/dotbox
```

Build the distributions independently:

```sh
python -m build packages/fdisbull-core
python -m build
python -m build apps/dotbox
```

For a built application wheel or sdist, supply the matching `fdisbull-core`
wheel explicitly or through a controlled wheelhouse. Do not assume an unpublished
development dependency is on a public index. The shared wheel contains common
mechanisms only. Ordinary sdists must build outside Git without reaching into
sibling directories. Native source-build helpers have separate checkout
requirements. The DotBox Mac helper records repository and product identities
and consumes an explicit shared wheel; it is not a generic no-Git sdist installer.

## Native lifecycle and backend direction

The stable DOSBox-X base patch, manifest and GPL text are maintained once under
`experimental/dosbox-x/`. DotBox's source resolver verifies those exact inputs
against its existing native recipe. Its wheel, sdist, exported kit and Mac source
staging materialize ordinary copies at the original product resource paths;
those deliveries need no sibling checkout. The cooperative-input overlay remains
DotBox-specific. Moving the base source does not change native bytes or qualify
a new native binary.

DOSBox-X and QEMU remain separately built components. Rebuild for changed native
source, patches, dependencies, configuration, toolchain or platform. An unrelated
Python or documentation commit does not invalidate a native artifact. Reuse its
recorded identity when those inputs are unchanged; client/contract checks may
still be needed. Preserve separate per-backend manifests and qualification.

The legacy DOSBox-in-QEMU Python guest now includes the shared transport module
and package initializer in all resource identities. Its prepared initramfs must
be regenerated for these changed Python resources; an older image correctly
fails identity validation. This does not rebuild DOSBox-X or modify the separate
native DOS QEMU parity implementation.

Backend protocols may share concepts while retaining different address spaces,
clocks, input delivery and checkpoint formats. A producer advertises only its
own demonstrated capabilities. Fallback reports which backend executed the
operation and any changed semantics; it does not silently replay uncertain
execution or assume checkpoint portability.

| Stage | fDisBull | DotBox |
| --- | --- | --- |
| During QEMU migration | Preserve current defaults, alternatives and open qualification work | DOSBox-X |
| **After QEMU parity is qualified** | **QEMU primary**, DOSBox-X as explicit fallback | **DOSBox-X** |

This merge does not qualify parity, promote a backend, remove fallback or close
a retirement campaign. It does not start native compilation or hosted CI.

## Active QEMU work

The integration branch `codex/shared-dotbox-core-20261121` starts from main
`829453ecae3fb0de236dbdd95be85a554efd1fb7`. At coordination time, the separate
`codex/qemu-parity-20261120` branch was observed at
`da36709d757f54bc9d0b70e39a8b54bf7f460ad2`. These are pinned inputs, not a claim
that a moving branch has stopped there.

The memory-search kernel and existing tests are identical in those inputs, so
the first shared component can proceed from main without importing unfinished
QEMU work. Preserve the QEMU branch, its review target and all ongoing changes.
Do not reset, rebase or overwrite transport, pause/frame, process or parity work.

When the branches meet, reconcile packaging changes deliberately. Preserve QEMU
native inventory and DOS guest assembly additions to `pyproject.toml`,
`MANIFEST.in`, release builders and package checks. Retain the compatibility
import consumed by QEMU's memory-search runtime. Re-run relevant consumer
checks against the then-current merged source; a textual merge is not
qualification.

## Separate Agent BBS projects

Keep **`fdb`** and **`dotbox`**, their roles, goals and historical tickets. This
code consolidation does not merge boards or reassign old records.

One owner implements a shared slice. Each affected product records acceptance
against the same canonical source and evidence. Link tasks rather than creating
competing implementations. One project's result does not close the other's
acceptance. Routine progress stays on BBS; review descriptions explain the
change, tests and limits.

First integration tasks:

- `fdb`: `e-2978aede-8739-4282-9b28-cacb7067aea2`, owner `fdb-shared-core`.
- `dotbox`: `e-2a790853-3b58-4551-94b0-5e365d08fa5d`, owner `dotbox-dev`.
- QEMU coordination: `e-fbdbbcfb-fb6f-4193-b47a-d6fb55d26bae`.

## Source preservation and publication

DotBox's 250 tracked files were imported intact at `apps/dotbox/` from
`ca818054a1ce66183906f9d6d281623e158a1e77`, tree
`3f4b4706820550a24e9e4bb62377b7153d934a74`. Local import
`4f040ee36b4e10c624f847de7178295b9f6a1220` has both the fDisBull base and original
DotBox commit as parents. Subsequent edits are separate from this exact import.
Native notices, resource manifests and product-relative paths stay in the subtree.

Original `seeker-cyber-maker/fDisBull` is the canonical source/review repository
for this integration, under its existing GitHub/local-hub/GitLab policy. Preserve
both independent DotBox repositories and histories with transition notices.
Do not overwrite their trees with the combined repository or maintain duplicate
shared kernels there. A review branch does not replace main or a qualified
installation before integration is accepted. If a publication route cannot
transfer original Git ancestry, state that limit and retain the exact local
history in a verified Git bundle; a tree-only preview is not a history transfer.

Retain pre-integration packages as a rollback boundary. This checkpoint does
not migrate game data, databases, harness revisions, live sessions or installed
emulators. Source publication, merged review, package release and installed
runtime qualification remain distinct outcomes.

## Acceptance and benefit claims

Check unchanged kernel behavior, both consumer routes, malformed/bounded inputs
and matching distribution contents. Install each product with the shared wheel
in an isolated environment outside the checkout; verify imports and installed
RECORD entries without source-path injection or the other application. Keep
the player independent. Record source inputs, distribution hashes, commands
and results. Preserve native identities and ongoing QEMU work.

The immediate benefit is one shared implementation with preserved behavior.
Faster end-to-end harness construction is a separate measurement, not a result
inferred from this extraction.
