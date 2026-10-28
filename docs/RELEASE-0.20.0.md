# fDisBull 0.20.0

0.20.0 integrates PR #12 and the reviewed local corrections. It adds explicit
DOS COM support, owned held-key input, typed movement macros, early blocked-route
results, scene content readiness and game-space geometry, a processor interface,
a partial static AGI 2.917 inspector, watch-only dot-mode, and bounded Z3 model
comparisons. Ordinary headless operation remains the default.

## Input, movement and scenes

[Immutable macro sets](SEMANTIC_INPUT_MACROS.md) bind user-defined names and typed
arguments to exact project/source versions. They preserve expanded operations,
authority labels and input ownership. A latched game can stop with a second
same-direction press; a held-input profile returns and consumes an owned lease.
Atomic keyboard presses retain their make/hold/break semantics.

Movement requires explicit destination, progress, context and settled-state
contracts with bounded guest and host budgets. It rejects pending or held input
without disturbing caller ownership. Stalls preserve an authentic frame before
cleanup and remain failures; a matching geometry model can strengthen their
classification, but unchanged coordinates alone do not prove collision.
Final input, destination, context and geometry are checked again after cleanup.
Unexpected debugger stops remain explicit, and uncertain cleanup closes the run.
Restore invalidates run-scoped runtime memory bindings; addresses must be
resolved and qualified again. Static DOS mapping guards remain intact.

[Scene content](SCENE_NAVIGATION.md) separates family recognition, requested
content, displayed content and readiness. Game-coordinate navigation masks and
actor footprints remain separate from screenshot-pixel action areas. Conditional
colliders, source facts, evidence status, anchors and portals are retained in the
versioned manifest. Missing observations remain unknown or incomplete.

## DOS, processor and proof boundaries

COM import requires explicit structural/context selection; segmented mapping
does not infer an executable from an arbitrary filename. DOS data watchpoints
report stopped CS:IP as the resume PC when available, rather than reporting the
watched data address as code. Optional dot-mode shows the same agent-owned
session while filtering host input; headless use needs no display. Actual
interactive macOS window behavior remains unqualified.

The [processor seam](PROCESSOR_MODULES.md) describes decode facts and successors.
The [AGI inspector](AGI_LOGIC.md) implements a documented partial static subset,
not an AGI runtime or a complete game converter. Unsupported, malformed,
overlapping and budget-stopped paths remain explicit. The local filename test
correction preserves mixed-case coverage and skips only duplicate-case fixtures
when the filesystem cannot represent both files.

[Z3 checks](BOUNDED_PROOFS.md) compare explicit finite-width models under stated
assumptions and retain source/version identities. Counterexamples, vacuous
assumptions, unknown results and an unavailable solver are distinct outcomes.
No automatic C/C++ lifting, source-model correspondence, full UIL evaluator,
ACT interpreter or whole-game equivalence is claimed. The installed Zork
reference/round-trip experiment remains separate from this tool release.

## Offline kit and acceptance

The [Linux x86-64 offline kit](OFFLINE_KIT_0.20.md) now requires genuine
`z3-solver==5.3.2.0`, together with the release wheel, decoding dependencies,
Python 3.13-compatible Pillow, the tested backend and private SDL2_net. Its
installer requires Python 3.13.5, verifies file hashes, creates a new virtual
environment and uses pip with no index and required hashes. A corresponding
pinned-upstream source archive, verified overlay, manifests and license notices
accompany the binary kit. No user project or original file is replaced.

The native workflow builds and installs this kit, then uses an authored DOS
fixture to verify real Z3 queries, keyboard input, memory, screenshot capture,
native restore, post-restore input and project restart. Passing a wheel checksum
or including a solver filename is not installation acceptance.

The local [installed-wheel acceptance receipt](evidence/0.20.0/mac-installed-acceptance.json)
records those authored DOS operations on macOS ARM64 with Python 3.13.17 and
genuine Z3 5.3.2. This checks the acceptance helper and release wheel; it does
not qualify the Linux archive or Python 3.13.5. Focused packaging, AGI and proof
checks passed 36 tests, with one duplicate-case filesystem skip. The unfiltered
final Mac suite passed 1,206 tests, skipped 102, and retained the two failures
and 23 fixture errors from Linux ELF builds on Apple GCC. Full Linux CI remains
the final gate for those fixtures.

The [reconciliation record](RECONCILIATION-0.20.md) retains candidate CI and
fresh Mac/Police Quest evidence. The genuine Mac layers backend passed 415
configured checks without skips. On a private Police Quest I AGI 2.917 copy,
public movement and saved scripts completed, a route blocked at X=34 and settled,
and native restore required rebinding before successful repetition. A numbered
8-pixel overlay and bounded instruction trace were exported privately. Geometry
qualified only the observed baseline point, not a full collision map. Original
game-file hashes remained unchanged.

Final main source must pass both ordinary and native Linux workflows before
tagging. Candidate and earlier-version CI do not substitute for that gate.
GitHub release publication and shared installation promotion are separate from
this source finalization. Game files, saved states, databases, vendor executables
and credentials are excluded from the commit and offline kit.
