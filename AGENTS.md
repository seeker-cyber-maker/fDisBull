# fDisBull for agents

**Designed by a human, refined by agents, and operated by agents.**

fDisBull owns the mechanical middle of reverse engineering, live headless
debugging, state discovery, and semantic reconstruction (`UDL` → `UIL` → `UDC`)
across 400+ deterministic CLI/JSON methods (`fdisbull methods`), leaving you
only a small number of bounded judgment points along a
[7-stage automated pipeline](docs/METHODOLOGY_DETERMINISM_AB_PLAN_2026-11-08.md).
To keep your token usage low and your context window clean:

- **Direct output is capped at 64 KiB inline (`fdisbull-output-ref-1`):** larger
  replies are stored automatically as immutable private files (`out-<sha256>`)
  and queried surgically via `output-select` (JSON Pointer), `output-read`
  (byte range) or `output-info`—never dump full artifacts into context.
- **Long reports and discoveries live in searchable SQLite and vectorized DBs:**
  instructions, CFGs, xrefs, structural types, watch hits, Anchor Stones,
  dependency queues (`work-queue`, `operation-goal`) and Z scenes persist in the
  project database (`.fdb`), while source snapshots and logical concepts are
  indexed in the SQLite FTS5 + vector embedding catalog (`source-*`,
  `fdisbull-source-catalog-1`).
- **Live emulators are owned by their server/context:** saved run history does
  not reconnect a guest after exit, and headless launches suppress GUI pop-ups
  by default.

## Start with the user's task

- Reuse the established executable, project and live session. Verify runtime
  identity or required capabilities once on entry with `fdisbull --version-json`,
  `fdisbull preflight --expectations <manifest>` or `fdisbull capabilities`;
  do not repeat discovery or diagnostics before known working operations.
- Three self-contained skills ship inside the installed wheel and work without
  opening a project (`fdisbull agent-skill --list` and `--index`):
  - `fdisbull agent-skill --skill fdisbull --reference SKILL.md` (`fdisbull`):
    top-level router skill for choosing between investigation (`fdisbull-investigate`)
    and guide writing (`write-gamefaqs-guide`).
  - `fdisbull agent-skill --reference SKILL.md` (`fdisbull-investigate`):
    evidence-driven reverse engineering, deliverable framing (`references/task-framing.md`),
    probe selection, memory/event searches, scene/UIL recovery and verification
    gates (consult [the quickstart](docs/AGENT_QUICKSTART.md) and then only the
    needed reference).
  - `fdisbull agent-skill --skill write-gamefaqs-guide --reference SKILL.md`
    (`write-gamefaqs-guide`): turning recovered mechanics, routes, bugs, unused
    code and format specs into an attributed, human-readable guide. Keep
    attributed external findings distinct from recovered and observed game behavior.
- Use `fdisbull --help` or `fdisbull methods` when an interface is unknown.
  Prefer built-in deterministic readers and search surfaces (`media-modules`,
  `media-inspect`, `media-extract` including native Inno 5.6.2 and MADS;
  `dos-sys-inspect`, `desqview-module-inspect`; `debug-search-*` scalar memory
  narrowing; `debug-event-search-*` and `debug-trace-until` execution-event
  isolation; `frame_rgba()` in-memory frame buffers) over ad-hoc scripts.
- Static analysis needs no running emulator. Debugging original DOS/Windows code
  needs the matching separately prepared backend and the user's own inputs.
  The standalone player consumes an authored projection or compatible endpoint;
  it does not automatically recover an entire game's scripts.
- Choose physical, assisted or story policy explicitly. `text-host --fair-play`
  locks physical play for that session. Assistance is useful for investigation;
  record it when reporting how a result was obtained. Live player mode can save
  between model turns; verify the checkpoint receipt before claiming persistence.

For repeated game work, grow a rapid self-building `Z` harness from the startup
menus and global controls onward. Expose each learned control as a named `Z`
action immediately, compose useful routes, automate navigation, add compatible
placement and scene presets, then replace repeated UI work with programmatic
actions as those become available. For rapid QA and patch/edition comparisons,
target isolated code blocks rather than re-running the whole process: rewind
live debugged state via Anchor Stones (`debug-rewind-*`, `debug-delta-*`,
`debug-timeline-*`), compare baseline vs. patched code layers in live
experiments, and export pre/post-patch behavioral diffs through `UDL` → `UIL`
into any supported language (Python, JS, C, ASM, or Z3 proofs). Use the
cheapest acquired capability for the next test. A Z/UIL harness does not
require a UDC build; source/model/output qualification applies when the
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

CI is local-first: branch, merge-request and tag events must not automatically
start provider pipelines. Use the finite local Linux qualification route and
keep its receipts explicitly local. GitLab web/API pipelines require an explicit
user action and a dedicated `fdisbull-local-linux` runner; do not register a
runner, create credentials, or use hosted instance runners as a fallback. Heavy
native work requires a deliberate start. Apply the storage admission rules
before each material growth phase. Local results do not establish hosted CI.


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

## Repository authority, mirrors and CI coordination

- **The original GitHub repository `seeker-cyber-maker/fDisBull` (ID `1431097789`) is the preferred source/review platform.** The user confirmed this exact repository has their reported Trust & Safety exemption. The connected `TiGa-RCE` account has Write access. This is not an exemption for other repositories/accounts. `TiGa-RCE/fdisbull` is a separate partial import; leave it separate.
- **Preserve local-hub and GitLab work.** The guarded service serializes original GitHub ↔ local-hub ↔ GitLab using separate peer histories, volume/storage admission and fast-forward-only updates. Original GitHub is `origin`; local-hub is `/Volumes/GitHub/GitHub/fDisBull-hub/fDisBull.git`; GitLab remains `https://gitlab.com/brewster-jennings-group/fdisbull.git`, project `88349936`. Push ordinary source branches to `origin` or `local-hub`; the service propagates them. Manual GitLab pushes require `-o ci.skip`; never send that provider option to GitHub or local-hub. Do not use the old `dual` push remote.
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
