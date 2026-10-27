# fDisBull 0.18.0

Scenes now share repeated memory reads within one stopped observation, reducing
backend round trips while retaining fresh reads for every later check and poll.
Opt-in compact replies preserve statuses, stop identities, capture counts and
diagnostic references; full observations remain stored and retrievable.

Portable scene ZIPs contain declarative definitions and hash-named clean PNG
snapshots. Import checks original source and complete mapped-byte identity,
remaps local scene/object/artifact IDs and preserves original context/authorship
as provenance. Imports are atomic, reject conflicting names and extra files,
and never treat historical screenshots as current readiness. Automatic rebasing
is not implemented.

Typed relative outcomes compare current memory against fresh pre-action values,
with explicit signedness, byte order, arithmetic and wrapping. Missing required
captures remain incomplete, including inside `any`. Each action gets a new
baseline; execution breakpoints, data watches, hooks and guest errors remain
explicit stops. Numbered overlays add a separate persistent legend from the
same manifest and geometry used for input.

Python, JSON, saved scripts and the bundled investigation skill expose the
changes. Existing full replies and name labels remain defaults. See the
[scene improvements guide](SCENE_IMPROVEMENTS.md) for schemas, limits and usage.

## Verification and release gates

The [sealed development record](VERIFICATION-SCENE-IMPROVEMENTS.md) preserves a
separately installed `0.18.0.dev0` wheel, source hashes, real DinoPark screenshots,
saved routes, bounded traces and stop receipts. A private NEW GAME run exported
three scenes/three PNGs, imported them into an independent project, reopened it,
restored a native checkpoint in a fresh emulator and completed eight named bank
and ledger actions with eight fresh relative baselines. All 192 original files
and 184 copied files remained unchanged; accepted emulator processes exited.

An office observation made 17 memory evaluations through two backend reads.
Its compact reply was 1,233 bytes versus 25,210 bytes for the same retained full
observation. These are bounded local measurements, not general speed guarantees.
The DinoPark relative condition verified an unchanged parking count during menu
navigation; it did not establish a purchase increment. Repeated increments and
wrap behavior have separate regression coverage.

Development qualification passed 54 stable DOS, 335 layered DOS and 33 focused
installed-wheel/package checks with no skips on macOS ARM64 / Python 3.13.14.
The broad Mac run recorded 1,120 passed, 16 skipped, two failures and 23 errors
in Linux ELF fixtures using Apple clang; it is not a green complete-suite or
Linux result. Promotion preserves the recorded scene/runtime modules and driver.

Before tagging, both GitHub workflows must pass on the exact release commit:
ordinary Linux tests/package audits, and native stable DOS, layered DOS (Python
3.13.5), plus installed-wheel unified DOS/boot/PE64 acceptance. Tag CI is a
separate follow-up. Publication and offline-kit delivery are not implied by a
source commit or tag.

## Limits and exclusions

Scene probing remains a direct DOSBox capability. Conditions still require
authored calibration; frame freshness alone does not prove control readiness.
Different mapped views/load segments reject scene bundles. SVG equations,
classifier recognition, automatic learning and deterministic replay are outside
this implementation. The [content/engine/player extension contract](GAME_CONTENT_AND_PLAYER.md)
is a future design, not an implemented AGI/SCI extractor or engine.

Game files, saved games, native checkpoint bytes, project databases and vendor
IDA servers/keys remain excluded from Git and tool packages. The included scene
ZIP contains only its manifest and PNG references. Existing deliveries and
earlier verification receipts remain unchanged.
