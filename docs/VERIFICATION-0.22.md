# 0.22.0 source finalization and verification

This record accompanies the 0.22.0 release source: the qualified Zork harness,
shared UDL/UIL interaction blocks, spatial masks and policies, and their replay
and regression evidence. Version metadata is 0.22.0 for both the tool and the
separate player. Publication of GitHub release assets and updating the shared
installation are separate operations.

## Evidence identities

The dated [Zork development record](VERIFICATION-ZORK-2026-10-29.md) and
[spatial development record](VERIFICATION-SPATIAL-2026-10-29.md) retain their
original scope, development versions, input identities and test counts. Their
JSON receipts are preserved rather than relabeled as final-release runs. In
particular, the spatial receipt's source hash for `src/fdisbull/__init__.py`
identifies the earlier `0.22.0.dev0` file; finalization changes its version string
to `0.22.0`. A development receipt is not an exact-release-commit CI receipt.

The original-game work established bounded DOS Zork mailbox correspondence,
fresh initialized interpreter/worker checkpoint restoration, KQ1 tree and moat
observations, and a stationary PQ1 radio interaction retaining original game
logic. The guards require fresh scene qualification, verified resource bytes
and structurally decoded position conditions. These checks do not establish
whole-game equivalence or arbitrary-game position-free interaction.

Game files, story resources, native states, project databases, full private
traces and game-derived screenshots remain in ignored local verification
storage. Public receipts contain identities and bounded observations. The
checkout-only examples reproduce the tests with separately supplied inputs;
tool-only source distributions deliberately exclude `examples/`.

## Local and package checks

The retained development full-suite result is 1,429 passed, 104 skipped, two
failed and 23 setup errors on macOS. The failures and setup errors concern
Linux ELF fixture assumptions and the Apple compiler. It is not a green full
suite and does not substitute for ordinary Linux CI.

Finalization checks the final version strings, focused regressions, real native
policy/checkpoint/map behavior with a self-authored DOS fixture, archive contents
and source/wheel identities. Release archives contain tool/player sources,
tests, documentation, source-backed backend code and sanitized verification
receipts. They exclude licensed games, saved states and project databases.

Before the release commit, the focused final-version checks passed 161 tests
without skips. The self-authored native spatial fixture passed separately on
the tested Mac DOSBox backend. It exercises the real VGA frame, pinned scene and
map, guarded runtime room change, invalidation/rebinding after native restore,
retained fair-play policy and stored screenshot export. This fixture supplies
portable native acceptance without licensed inputs; it does not replace the
original-game evidence or Linux runs.

## Exact-commit Linux gates and tagging

Both of these workflows must succeed on the exact commit pushed to `main`
before creating `v0.22.0`:

1. **Tests and tool packages** — complete ordinary Linux suite, core wheel and
   sdist, standalone player wheel and isolated player smoke, tool ZIP and
   distribution exclusion audits.
2. **Native debugger acceptance** — stable DOSBox on Python 3.12, layers DOSBox
   on Python 3.13.5, offline-kit/source-companion acceptance, and the installed
   wheel's PE64, DOS-in-QEMU and boot-context acceptance. The matrix also runs
   the new spatial/AGI/interaction regressions and the self-authored native
   spatial fixture without licensed game inputs.

This file is prepared before those CI runs. The annotated `v0.22.0` tag is
created only after both gates pass and records their run URLs, tested commit
and acceptance summary. Inspect it with `git show v0.22.0`; the run pages remain
the authoritative job outcomes. Subsequent tag-triggered workflows are distinct
from these pre-tag runs and must not be represented as already passed.

No automatic change is made to the published 0.21.0 packages or selected shared
installation by committing or tagging this source.
