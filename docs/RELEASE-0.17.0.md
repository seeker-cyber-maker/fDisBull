# fDisBull 0.17.0

Persistent scene definitions let an agent reuse named controls without repeatedly
interpreting a full screenshot. One saved manifest supplies the visible overlay,
the action mask, a valid click point, recognition predicates and the bounded
outcome of real guest input. Object IDs, trigger/state context, original geometry,
supporting clean snapshots, revisions and observations persist in the project
database. Renames preserve IDs and old names as aliases.

Action regions support rectangles, polygons, unions, intersections and subtraction,
including holes and disconnected areas. Separate visible, ready and enabled
predicates prevent a scene match from automatically authorizing a click. Unknown,
missing or conflicting observations stop with diagnostic evidence. Optional named
popup handlers require explicit use. Input is bound to the checked native frame
and video mode; checkpoint restoration requires fresh observations.

The updated complete DOSBox patches add sparse native RGB sampling without PNG
encoding or transfer. Python, JSON and saved-script operations expose scene
checks, assertions, bounded waits and named mouse/keyboard actions. Breakpoints,
watchpoints, hooks and guest errors remain stops rather than being silently
resumed. The [scene guide](SCENE_FRAMEWORK.md) specifies formats, budgets and limits.

The packaged [fdisbull-investigate skill](../src/fdisbull/skills/fdisbull-investigate/SKILL.md)
is available through `fdisbull agent-skill`, without a project or global skill
installation. It adapts the relevant user-supplied reverse-engineering principles
and makes expected reward and probe cost explicit priorities alongside confidence.
Its scene reference connects those principles to the actual API.

## Verification and release gates

The [development verification record](VERIFICATION-SCENES.md) preserves the
installed `0.17.0.dev0` DinoPark run, source hashes, screenshots, bounded traces
and both backend patch manifests. That private NEW GAME run verified named bank
and ledger actions, sale-popup cancellation, mask holes, availability rejection,
collision evidence, restart/checkpoint invalidation and breakpoint/watch/hook
preservation. Original and copied game files remained unchanged. The release
promotion changes version metadata and release documentation; the verified
scene/runtime modules and backend patches retain their recorded identities.

Before tagging, both GitHub Linux workflows must pass on the exact release commit:
ordinary tests/package audits and native stable DOS, layered DOS (Python 3.13.5),
plus installed-wheel unified DOS/boot/PE64 checks. Native tests use
`--require-native` so unavailable backends cannot manufacture acceptance through
skips. Tag CI is a separate follow-up. Publication and offline-kit delivery are
not implied by a source commit or tag.

## Limits and exclusions

Native pixel probing currently targets direct DOSBox. PE64/Wine/IDA scene probing,
SVG/expression masks, graphical scene authoring, classifier-based recognition,
automatic learning and deterministic replay are not implemented. Scene readiness
is authored and must be calibrated; a new frame alone does not prove controls
exist. The DinoPark dispatch-selector condition is explicitly a calibration,
not a universal control-registration flag.

The original macOS full-suite result was 1,102 passed, 17 skipped, 2 failed and
23 errors. The failures/errors came from unchanged Linux ELF fixtures rejected
by Apple clang; that run is not presented as a passing complete suite. Its
focused native and installed-wheel checks passed, as recorded in the report.

Game files, saved games, native checkpoint bytes and project databases stay out
of Git and tool packages. Repository examples contain authored scripts, selected
screenshots/traces and verification receipts; the game and emulator checkpoints
remain private. The separately built native backend is distributed through its
complete source patches and CI artifacts, not inside the Python wheel.
