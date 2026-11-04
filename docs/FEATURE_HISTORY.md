# Versioned capability map

This page maps capabilities to source/release lines. A version label does not
make a proposal, open merge request, local experiment or prepared runtime part
of a published package. The
[GitLab release inventory](https://gitlab.com/brewster-jennings-group/fdisbull/-/releases)
records publication; the linked version notes define scope and limitations.
Exact qualification and package hashes belong to the release's source identity,
not to a moving branch or this table.

The 0.32.0 row describes the reviewed source scope without asserting that its
tag, upload, installation or final CI has completed. Earlier release receipts
remain in [release status](RELEASE_STATUS.md).

## Versions and source cuts

| Version | Capability added or emphasized |
| --- | --- |
| [0.10.0](https://gitlab.com/brewster-jennings-group/fdisbull/-/tags/v0.10.0) | Persistent native DOSBox state, editable checkpoint forks, bounded debugger scripts and CPU data watches. |
| [0.11.0](https://gitlab.com/brewster-jennings-group/fdisbull/-/tags/v0.11.0) | Reversible runtime code layers, breakpoint actions and precise screenshot-to-click workflows. |
| [0.12.0](https://gitlab.com/brewster-jennings-group/fdisbull/-/tags/v0.12.0) | Native PE64 debugging through Wine/QEMU, with analyzed-address stops, guarded memory edits, traces and window input. |
| [0.13.0](https://gitlab.com/brewster-jennings-group/fdisbull/-/tags/v0.13.0) | PE64 memory watchpoints, reversible code layers and editable native machine states. |
| [0.14.0](https://gitlab.com/brewster-jennings-group/fdisbull/-/tags/v0.14.0) | Shared Linux/QEMU machine lifecycle for DOS and Windows debugging, raw x86 boot and optional IDA/DOSBox adapters. |
| [0.16.0](https://gitlab.com/brewster-jennings-group/fdisbull/-/tags/v0.16.0) | Saved baseline-versus-layer experiments, standalone DOS analysis, bounded observations and guest keyboard input. |
| [0.17.0](https://gitlab.com/brewster-jennings-group/fdisbull/-/tags/v0.17.0) | Persistent named scenes with saved action geometry, visibility/readiness checks, context and revisions. |
| [0.18.0](https://gitlab.com/brewster-jennings-group/fdisbull/-/tags/v0.18.0) | More portable and auditable scene debugging, compact replies backed by stored evidence, and portable scene definitions. |
| [0.19.0](https://gitlab.com/brewster-jennings-group/fdisbull/-/tags/v0.19.0) | Guarded DOS aliases for supported MZ launches, saved screenshot preparation/cleanup and corrected DOS continuation. |
| [0.20.0](https://gitlab.com/brewster-jennings-group/fdisbull/-/tags/v0.20.0) | Typed input macros, bounded movement and scene geometry/readiness; DOS COM support; processor modules; bounded Z3 checks; a **partial static AGI 2.917 inspector**. |
| [0.21.0](https://gitlab.com/brewster-jennings-group/fdisbull/-/tags/v0.21.0) | Progressive scene workflows, separately packaged text player, live-turn checkpointing and qualified assisted travel. |
| [0.22.0](https://gitlab.com/brewster-jennings-group/fdisbull/-/tags/v0.22.0) | Bounded Z-machine v3 story harness, source-linked interaction blocks, native-coordinate maps and explicit physical/assisted/story policies. |
| [0.23.0](https://gitlab.com/brewster-jennings-group/fdisbull/-/tags/v0.23.0) | Original-backed DOS UDC and the first qualified ASM-to-UDL/UIL-to-native-backing route. |
| [0.24.0](https://gitlab.com/brewster-jennings-group/fdisbull/-/tags/v0.24.0) | Bounded core replies with private artifact handles, shared-IL Z scenes and the separate text player, plus original-backed DinoPark recovery. |
| [0.25.0](https://gitlab.com/brewster-jennings-group/fdisbull/-/tags/v0.25.0) | Qualified Zork behavior recovery, safer DinoPark continuations, static DOS/4GW LE analysis, native GOG extraction and packaged investigation skills. |
| [0.25.1](https://gitlab.com/brewster-jennings-group/fdisbull/-/tags/v0.25.1) | DOS selected-process termination reporting, distinguishing `guest_exit` from a resident TSR or debugger shutdown. |
| [0.26.0](https://gitlab.com/brewster-jennings-group/fdisbull/-/tags/v0.26.0) | Recovery of stopped original-backed investigations, bounded Z-machine v3 code inspection and more cautious data-watch stop reporting. |
| [0.26.1](https://gitlab.com/brewster-jennings-group/fdisbull/-/tags/v0.26.1) | Read-only batch reconciliation, DOS process-exit evidence and a broader evidence-based game-guide skill. |
| [0.27.0](https://gitlab.com/brewster-jennings-group/fdisbull/-/tags/v0.27.0) | Private external storage for schema-9 source bytes; safer checkpoint/reply reconciliation and named DinoPark actions; provenance-preserving structural types; bounded Win16 NE analysis and refusal of changed LE/NE declarations before source-layer binding. The release includes its qualified integrations and Linux x86-64 offline kit; Win16 execution remains out of scope. |
| [0.28.0 candidate](RELEASE-0.28.0.md) | Projectless capabilities, macOS ARM64 investigation, bounded CI coordination, DinoPark Coelophysis recovery, static DOS/audio inspection and Syndicate spatial scenes. This candidate's scope was carried into 0.29.0; the source cut is not a claim of a separate published release. |
| [0.29.0](RELEASE-0.29.0.md) | Carries the 0.28 candidate and adds Civilization I world snapshots, the Z world language and Zork map, offline dependency delivery and native backend source companions. |
| [0.30.0](RELEASE-0.30.0.md) | Common indexed UIL contracts; console intake, synthesis and bounded game projections; direct AGI/KQ1 native alignment; Anchor Stones, debugger/frame timelines and Wine CPU/RAM deltas; multi-target memory shells and Cortex-M Thumb; trial-safe GitLab CI. |
| [0.31.0](RELEASE-0.31.0.md) | Verified keyframe/XOR frame-state delta storage; bounded typed-C to UIL; Windows runtime preflight; CHIP-8, UDC registry and swede examples; cold-agent benchmark and skill refresh. Full state capture still occurs at each automatic timeline point. Example/research scope is preserved. |
| [0.31.1](RELEASE-0.31.1.md) | Native CI repair and complete macOS Swift capture resources in tool source ZIP, wheel and sdist; no new analysis feature. |
| [0.32.0 source scope](RELEASE-0.32.0.md) | Captured PE/Galaxy import recovery; context-aware format/media intake and restricted SMK2 framing; Win32 PE32 and experimental Win16 runtime controls; protected-mode DOS RAM/checkpoints; exact frame codecs and direct RGBA consumption; experimental ScummVM AGI/Gob backends; headless quit-popup, signed-return and package-completeness fixes. Publication and final qualification are recorded separately. |
| [0.33.0rc1 local candidate](RELEASE-0.33.0.md) | Carries the 0.32.0 source line and adds Boat CI handoff, built-in GOG Inno intake, Westwood media/EMC2 readers, experimental ScummVM Kyra and AGI-to-UIL pilots, and investigation-skill guidance. Local candidate only; not a published release. |

The historical inventory had no `v0.15.0` release; the corresponding local tag
inventory also has no such tag. This is not a claim about an unpublished branch.
The Z-scene work progressed through saved scenes (0.17), progressive scene
knowledge and a separate text player (0.21), the story harness and spatial
policies (0.22), then shared-IL Z scenes (0.24). These are bounded interfaces
and authored projections; they do not recover every game's script or establish
whole-game equivalence.

## AGI capability boundaries

The partial static AGI 2.917 inspector began in 0.20.0. The later 0.30.0 source
line carries direct decoder/lift, control/effect and original-DOS host work,
with bounded KQ1 native alignment. These are source- and edition-bound
investigation paths, not a general recovered AGI engine or whole-game proof.
See [0.30.0 scope](RELEASE-0.30.0.md) and
[native host verification](VERIFICATION-AGI-HOST-2026-10-31.md).

The 0.32.0 [ScummVM AGI backend](SCUMMVM_BACKEND.md) is a separate experimental
replacement-engine path. Its script state, scene controls, game-save slots and
stored frames retain engine/resource identity. A successful matched scene does
not make ScummVM an exact checkpoint or timing equivalent of original DOS.

### Historical AGI review snapshot — 2026-10-31

The following preserved notes describe the old GitHub proposal stack and its
then-current 0.27.0 baseline. Their "current main", "open" and "unshipped"
statements are historical, not current integration status. GitHub PR numbers
below are separate from GitLab merge-request numbers; GitHub #67 here is not
the captured-PE alternative GitLab !67 excluded from 0.32.0.

The shipped AGI capability begins with v0.20.0's partial, read-only static
2.917 logic inspector. Published v0.27.0 and current `main` still contain that
inspector (`src/fdisbull/agi.py`) but do not contain `src/fdisbull/agi_host.py`
or the proposed `src/fdisbull/decoder_modules.py`. Thus v0.27.0 did publish,
while the original-DOS host adapter and stacked AGI interpreter work remain
proposals. The original-DOS host adapter described in
[PR #78](https://github.com/seeker-cyber-maker/fDisBull/pull/78) is not part of
the published build. The PR states its own limits: an exact-edition KQ1 DOS
logic-103 invocation profile, not a general AGI engine, scheduler, natural
player route or whole-game recovery.

The AGI PRs form an open, stacked proposal from `main` toward that profile:

| PR | Proposed step | State checked 2026-10-31 |
| --- | --- | --- |
| [#67](https://github.com/seeker-cyber-maker/fDisBull/pull/67) | Direct guest decoder modules and bounded AGI UDL/UIL lifts. | Open; based on `main`. |
| [#71](https://github.com/seeker-cyber-maker/fDisBull/pull/71) | Scalar conditions, branches and direct logic calls. | Open; stacked on #67. |
| [#72](https://github.com/seeker-cyber-maker/fDisBull/pull/72) | Shared continuations and compact KQ1 control-flow topology. | Open; stacked on #71. |
| [#76](https://github.com/seeker-cyber-maker/fDisBull/pull/76) | Typed object/resource effects and resumable host requests. | Open; stacked on #72. |
| [#78](https://github.com/seeker-cyber-maker/fDisBull/pull/78) | Original DOS host observations and bounded KQ1 logic-103 comparison. | Open; stacked on #76. Exact head `7922a1a81104f7211d492b2f7c9b633e4b6e38fd`. Ordinary run `41205770548` passed (2,291 passed, 118 skipped). Native run `41205770530`: stable and layers jobs passed (989 and 1,307 tests); the unified installed-wheel job was cancelled by runner shutdown during setup before PE64/DOS/boot acceptance, so full native CI remains incomplete. These results are for the unshipped PR head, not the released v0.27.0. |

The v0.27.0 release notes identify the frozen PR #55 integration at
`90e748c8bc6a4f068f9136f4d4ec989672421a03`; they explicitly exclude later
experimental feature PRs. Do not attribute the separate, still-open AGI PR
stack to v0.27.0. The current working tree also contains an authored
source-linked AGI Z-scene builder; it is a local development artifact, not a
published AGI scene engine or a versioned release feature.

The #78 job retry returned 404; a fresh dispatch of its native workflow was
rejected with HTTP 422, "Actions has been disabled for this user." This is an
external CI availability gate. It does not erase completed DOS backend checks
or establish that the skipped installed-wheel checks passed.

## Sources and status

The [GitLab release list](https://gitlab.com/brewster-jennings-group/fdisbull/-/releases)
and [tag list](https://gitlab.com/brewster-jennings-group/fdisbull/-/tags)
record remote publication identities. The
[main branch](https://gitlab.com/brewster-jennings-group/fdisbull/-/tree/main)
and [merge requests](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests)
are moving source, not substitutes for release receipts. Retired GitHub PR
links in the dated snapshot preserve the origin of that historical evidence;
they are not instructions to access GitHub or restart its CI.
