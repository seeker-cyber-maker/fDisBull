# Visiting fDisBull with Claude and Coding Agents

**fDisBull** (`0.34.1`) is an agent-first reverse-engineering, native-debugging,
scene-automation and semantic-reconstruction (`UDL` → `UIL` → `UDC`) pipeline—designed
by a human, refined by agents, and operated by agents. The tool automates the
mechanical middle across 400+ deterministic CLI/JSON methods (`fdisbull methods`),
leaving you only a handful of bounded decisions along a
[7-stage pipeline](docs/METHODOLOGY_DETERMINISM_AB_PLAN_2026-11-08.md) while
protecting your token budget:

- **64 KiB bounded inline output (`fdisbull-output-ref-1`):** oversized replies
  are saved automatically as private `out-<sha256>` artifacts; inspect them
  surgically with `fdisbull output-select <id> <json-pointer>` or `output-read`
  instead of reading megabytes into context.
- **Searchable SQLite project (`.fdb`) & vectorized source/concept DB
  (`source-*`):** disassembly, CFGs, types, watch hits, `operation-goal`
  coverage, `work-queue` state, and FTS5 + vector-indexed source/concept cards
  stay in SQLite so turns and subagents query only what they need.
- **Selective `<2 KiB` skill loading:** use `agent-skill --list` and `--index`
  to load only the single reference file required for the active stage.

Read [AGENTS.md](AGENTS.md) for the shared project contract,
[CI coordination](docs/CI_COORDINATION.md) for mirror synchronization and
trial-safe CI rules, [the agent quickstart](docs/AGENT_QUICKSTART.md) for
executable entry points, and the
[methodology determinism review](docs/METHODOLOGY_DETERMINISM_AB_PLAN_2026-11-08.md)
for the 7-stage deterministic workflow.

- **Keep Local Git (`local-hub` and local branches/tags) and GitLab (`gitlab` at `brewster-jennings-group/fdisbull`) in equal sync** via `python scripts/sync_mirrors.py` or `git push -o ci.skip dual <branch>`.
- **GitHub (`origin` / `seeker-cyber-maker/fDisBull`) is an active public peer mirror**; GitLab and `local-hub` remain the release and CI authority.

Start with the requested outcome, verify runtime/capability expectations once,
and choose the cheapest decisive observation. Three self-contained skills ship
inside the installed wheel and work without opening a project:

```bash
fdisbull --version-json
fdisbull agent-skill --list
fdisbull agent-skill --skill fdisbull --reference SKILL.md
fdisbull agent-skill --reference SKILL.md
fdisbull agent-skill --reference references/workflows.md
fdisbull agent-skill --skill write-gamefaqs-guide --reference SKILL.md
```

- `fdisbull` (`--skill fdisbull`) is the top-level router skill for choosing between investigation (`fdisbull-investigate`) and human-readable guide authoring (`write-gamefaqs-guide`).
- `fdisbull-investigate` (default) supplies deliverable framing (`references/task-framing.md`), evidence-driven static analysis, media/archive extraction (`media-*`), persistent scalar memory searches (`debug-search-*`), execution-event searches (`debug-event-search-*`, `debug-trace-until`), scenes, spatial policies and `references/udl-uil-udc.md` for block recovery and bounded compiler experiments.
- `write-gamefaqs-guide` turns verified mechanics, routes, bugs and format specs into an attributed, human-readable guide.

Use the [README](README.md) when explaining the product to a person. Use the
quickstart, `fdisbull methods`, command help and the relevant skill reference
when operating it. Keep game-specific knowledge in the user's project evidence,
with source, version, runtime and claim boundaries. The repository ships the
tool and authored fixtures, including the explicitly approved freeware/homegrown
target exception described in [AGENTS.md](AGENTS.md). Commercial/private games,
saved states and project databases stay private.
