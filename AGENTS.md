# fDisBull for agents

fDisBull gives an agent persistent program analysis, headless native debugging,
named scene actions, explicit spatial policies, a separate text player, and
bounded source-to-UIL experiments. The analysis project stores discoveries and
evidence between turns. An emulator process is owned by its live server/context;
saved run history does not reconnect it after exit.

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

After each release candidate is packaged, install and activate a fresh shared
prefix locally, then run
`python scripts/check_local_install.py --version <version> --commit <commit>`
from the source tree. A release is not locally complete until the active
payload, version, commit and selector all verify.

## Repository mirrors and CI coordination (GitLab 30-day trial + local Git parity)

- **GitHub (`origin` / `seeker-cyber-maker/fDisBull`) is permanently retired and obsolete.** Never push to, fetch from, or poll GitHub (`origin` push URL is locked to `RETIRED_GITHUB_DO_NOT_PUSH`).
- **Local Git and GitLab (`gitlab` -> `https://gitlab.com/brewster-jennings-group/fdisbull.git`, project `88349936`) are equal representations.** Because GitLab is under a 30-day evaluation trial, agents must update **both** the local Git repository (`local-hub` at `/Volumes/GitHub/GitHub/fDisBull-hub/fDisBull.git` and local branches/tags in `/Volumes/CODEX/Codex_Projects/fDisBull`) and GitLab (`gitlab`), using `python scripts/sync_mirrors.py` or pushing to the `dual` remote (`git push -o ci.skip dual <branch>`).
- Read [CI triggers and status coordination](docs/CI_COORDINATION.md) before starting or observing hosted checks.
- **Anti-abuse CI rules**: `.gitlab-ci.yml` never runs automatic pipelines on feature/topic/archive branch pushes or `Draft:` Merge Requests, and heavy C++ DOSBox-X compilation jobs (`native-debugger-*`) are manual-only (`when: manual` or `FDISBULL_RUN_NATIVE_CI=1`). Always pass `-o ci.skip` when mirroring non-main branches to GitLab.
- Name one CI owner for the repository; other agents consume that owner's dated receipt. Use `scripts/ci_status.py` in cache-only mode by default:
  ```sh
  python scripts/ci_status.py --host gitlab.com --repo brewster-jennings-group/fdisbull --sha "$(git rev-parse HEAD)"
  ```
  Only the named owner uses `--refresh --owner`; the helper permits one repository-wide refresh per five minutes, shared across local worktrees. Do not run parallel job-status loops, `glab ci trace`, `gh run watch`, automatic retry loops, or empty commits to restart CI.

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
parent. Return a read-back draft GitLab MR URL, exact branch/head and target/base,
tests, limitations and verified attachment links to the originating chat.
Commit inspected authored source and eligible target fixtures; attach sanitized
reports separately. Preserve existing MR targets and other agents' work.
Use `scripts/gitlab_handoff.py` for
offline preview and, with existing API access, resumable publication. Chat agents
without write/upload access export the documented handoff and report it pending.
Never invent access, successful uploads, commit identities or completed MRs.
