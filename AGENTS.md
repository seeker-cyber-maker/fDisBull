# fDisBull for agents

fDisBull gives an agent persistent program analysis, headless native debugging,
named scene actions, explicit spatial policies, a separate text player, and
bounded source-to-UIL experiments. The analysis project stores discoveries and
evidence between turns. An emulator process is owned by its live server/context;
saved run history does not reconnect it after exit.

## Current resource and release policy (2026-11-14)

Fixed disk reserves and mandatory storage admission have been removed. Prefer
mounted external project/cache destinations for bulk outputs, validate actual
mount identity and report real I/O failures. Preserve unique data and require
exact approval for irreversible deletion; ordinary allocation needs no approval.
Heavy local model/GPU/VM jobs retain shared-memory guard policy; routine commands
and ordinary tests run directly. n8n owns the current VPS CI/release sequence.
0.35.0 installation and activation are authorized after full release checks,
with the previous prefix retained for rollback. DotBox is a separate user project.

## Start with the user's task

- Reuse the established executable, project and live session. For first use or
  an unfamiliar operation, consult [the quickstart](docs/AGENT_QUICKSTART.md)
  and `fdisbull agent-skill --reference SKILL.md`, then only the needed reference.
  The bundled skill is available from an installed wheel without a project.
- For a human-readable review of established game knowledge, read
  `fdisbull agent-skill --skill write-gamefaqs-guide --reference SKILL.md`.
  Use `agent-skill --list` to discover both bundled skills. Keep attributed
  external findings distinct from recovered and observed game behavior.
- Use `fdisbull --help` or `fdisbull methods` when an interface is unknown.
  Check capabilities after a relevant environment change or capability failure;
  do not repeat discovery or diagnostics before known working operations.
- Static analysis needs no running emulator. Debugging original DOS/PE64 code
  needs the matching separately prepared backend and the user's own inputs.
  The standalone player consumes an authored projection or compatible endpoint;
  it does not automatically recover an entire game's scripts.
- Choose physical, assisted or story policy explicitly. `text-host --fair-play`
  locks physical play for that session. Assistance is useful for investigation;
  record it when reporting how a result was obtained. Live player mode can save
  between model turns; verify the checkpoint receipt before claiming persistence.

For repeated game work, grow a reusable Z harness from the startup menus and
global controls onward. Expose each learned control as a named action immediately,
compose useful routes, automate navigation, add compatible placement and scene
presets, then
replace repeated UI work with programmatic actions as those become available.
Use the cheapest acquired capability for the next test. A Z/UIL harness does
not require a UDC build; source/model/output qualification applies when the
requested deliverable includes a replacement or target implementation.

Keep one bounded question per worker and batch compatible tests in one scene
visit. Reuse a shared frame/memory snapshot; distinct in-range test values can
identify several HUD fields together. Split only ambiguous results. Useful
guesses and guide claims may drive probes immediately when marked as hypotheses.
Return compact findings and existing artifact IDs, not duplicate hash/log ledgers.
Preserve actual unknowns and distinguish visible, ready, enabled and committed.

Give each worker only the relevant dossier claims, evidence, recipe and expected
result. Publish useful partial findings and newly unlocked questions promptly.
A blocker belongs to its dependent work; retain it and continue other ready work.
One controller owns each live guest; other workers consume immutable evidence.

## Storage policy override — 2026-11-14

The user removed fixed free-space reserves and mandatory storage admission for
this project, including mirrors, VPS CI, packaging and release. Do not stop work
or request confirmation solely because a 40 GB/20 GB threshold would be crossed.
Routine allocation is authorized. Use suitable mounted destinations and actual
job requirements; preserve unique work and report genuine I/O failures. Do not
replace reserve stops with new permission gates. This does not authorize automatic
deletion or loss of existing work. The global agent guidance records the same rule.

## Working in this repository

The [README](README.md) introduces the product to people. Technical contracts,
API examples and scope limits belong in the linked docs and bundled skill.
Preserve that audience split when adding features. Testimony from users/agents
must be attributed and scoped to what they actually tested.

Except for the target exemption below, keep original game/story files, emulator
states, byte-retaining project databases and raw private deliveries out of Git
and review uploads. Use a private workspace outside the checkout for runtime
inputs and UDC outputs.
Export authored scripts and sanitized verification evidence separately.

The user authorizes freeware and homegrown targets as repository fixtures and
PR/MR attachments, including binaries, assets, source/reference modules, generated
variants and target archives. This is not limited to Tic-tac-toe, Five Dice and
Snake. Preserve included license/provenance notices, original identities and
variant distinctions. The existing three-game corpus remains under
`fixtures/freeware-games/`, with `fixtures/freeware-games.zip` as its companion;
other eligible targets can use separate fixture inventories.
Commercial/private game deliveries, saves, emulator states, project
databases and external object stores remain excluded. Target fixtures stay out
of tool-only wheels, source distributions and tool source ZIPs.

Use the repository's test/build commands. A release commit needs ordinary and
required-native Linux CI on its exact SHA before tagging. Publishing a release
or changing a system installation is a separate user-authorized action.
For 0.35.0, the user explicitly approved installation and activation after all
release checks pass, preserving the previous prefix for rollback. Older
"do not install" directions do not block that approved, gated completion.
n8n owns this release/installation continuation; do not activate a provisional
candidate or bypass exact-source qualification.

After each release candidate is packaged, install and activate a fresh shared
prefix locally, then run
`python scripts/check_local_install.py --version <version> --commit <commit>`
from the source tree. A release is not locally complete until the active
payload, version, commit and selector all verify.

## Repository authority, mirrors and CI coordination

- **The original GitHub repository `seeker-cyber-maker/fDisBull` (ID `1431097789`) is the preferred source/review platform.** The user confirmed this exact repository has their reported Trust & Safety exemption. The connected `TiGa-RCE` account has Write access. This is not an exemption for other repositories/accounts. `TiGa-RCE/fdisbull` is a separate partial import; leave it separate.
- **Preserve local-hub and GitLab work.** The guarded service serializes original GitHub ↔ local-hub ↔ GitLab using separate peer histories, mounted-volume identity checks and fast-forward-only updates. Original GitHub is `origin`; local-hub is `/Volumes/GitHub/GitHub/fDisBull-hub/fDisBull.git`; GitLab remains `https://gitlab.com/brewster-jennings-group/fdisbull.git`, project `88349936`. Push ordinary source branches to `origin` or `local-hub`; the service propagates them. Manual GitLab pushes require `-o ci.skip`; never send that provider option to GitHub or local-hub. Do not use the old `dual` push remote.
- Do not overwrite differing tags or delete/recreate refs to obtain parity. Historical `v0.27.0` has two preserved annotated tag identities pointing to the same commit. The exact configured exception and archive aliases are described in `docs/GITHUB_RESTORATION.md`; changes outside that mapping must hold for review. Working checkouts are not advanced by the service.
- **n8n owns CI.** The manual GitHub → OVH bootstrap passed on 2026-11-13 (run `43512305780`, attempt 1). Actions is enabled for the manual-only `ovh-bootstrap.yml`; legacy workflow IDs remain disabled. n8n alone dispatches and observes finite workers under the shared OVH executor lock. Ordinary pushes, PRs and tags do not automatically start this workflow. The bootstrap qualifies infrastructure and artifact handoff only; ordinary/native candidate qualification and offline package acceptance remain separate. Other workers must not change Actions settings, register runners, dispatch pipelines or duplicate status polling.
- Read [CI triggers and status coordination](docs/CI_COORDINATION.md). Preserve GitLab's deliberate triggers and `ci.skip` mirroring. Heavy native compilation remains an explicit CI-owner action. Use `scripts/ci_status.py` in cache-only mode by default; only the named owner refreshes within the shared cooldown. No automatic retry loops, empty commits or parallel job-status loops.

## Game files and target identity

Outside the freeware/homegrown target exception above, do not upload original
or modified game binaries, assets, story images, saves, emulator states or
byte-containing databases/archives to GitHub, GitLab, local hubs or packages.
Semantic UIL/game representations are allowed pending sanitation; embedded
original files are not. Read [external targets](docs/EXTERNAL_TARGETS.md).
New FDBs store size/SHA-256 references and loader provenance; keep their private
external object store outside Git. For divergence, obtain explicit user approval
of the exact project/base/candidate receipt before `bind-source`; an agent must
not manufacture consent by echoing `source-candidate.approval`. Without approval,
leave it unattached and create another analysis only on explicit caller choice.
Hash equality means recorded byte identity, not publisher authenticity or rights.

## Engineering contract

Build a usable local agent-first disassembler. Native decoders provide instruction facts; our analyzer owns traversal and the persistent database. Screenshots must come from stored state without operating a GUI.

- Start with recursive entry-point traversal, then investigate referenced memory and later symbol/export seeds. Deduplicate work and facts; a budget stop must never be called stable.
- Resolve entry names and representations from shared address identity in every query/export. Keep raw operands and evidence intact.
- Preserve original byte identity and every earlier code version; new FDB payloads remain in the private external store. Do not key an instruction by address alone.
- Label inferred functions as candidates; preserve xref evidence and annotation authorship. Keep unknown indirect/segmented behavior unknown.
- Do not substitute a mock disassembly, web landing page, decompiler framework, or runtime harness for the working tool.
- Keep `README.md` limitations and verification aligned with the final packaged source. macOS is unverified until actually run there.
- Use `python -m pytest -q` from this directory. Demonstrate restart, patch isolation, and real image exports for changes to those seams.

## Contribution handoff

For an authorized contribution, follow [agent contribution and file handoff](docs/AGENT_HANDOFF.md).
Use a stable originating chat/task ID, a unique branch and the intended stack
parent. New contributions target original GitHub `seeker-cyber-maker/fDisBull`.
Return a read-back draft GitHub PR URL, exact branch/head and target/base,
tests, limitations and verified attachment links to the originating chat.
Commit inspected authored source and eligible target fixtures; attach sanitized
reports separately. Preserve existing GitLab MR targets and other agents' work;
do not duplicate or retarget existing reviews merely to change providers.
Use the connected GitHub tools or reviewed Git/CLI publication for new PRs.
`scripts/gitlab_handoff.py` remains the preview/resumable publisher for existing
GitLab contributions. Without write/upload access, export a documented handoff
and report the exact remaining action. Never invent access, successful uploads,
commit identities or completed reviews. CI dispatch remains with n8n.
