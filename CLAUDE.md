# Visiting fDisBull with Claude

Read [AGENTS.md](AGENTS.md) for the shared project contract,
[CI coordination](docs/CI_COORDINATION.md) for dual local-Git/GitLab mirror
updates and trial-safe CI rules, and [the agent quickstart](docs/AGENT_QUICKSTART.md)
for executable entry points. These are the same maintained guides used by Codex
and other agents.

- **GitHub (`origin`) is permanently retired and obsolete.** Never push to or poll GitHub.
- **Keep Local Git (`local-hub` and local branches/tags) and GitLab (`gitlab` at `brewster-jennings-group/fdisbull`) in equal sync** via `python scripts/sync_mirrors.py` or `git push -o ci.skip dual <branch>`.

Start with the requested outcome, inspect the target/context, then choose the
cheapest decisive observation. The installed tool can supply its investigation
skill without a project:

```bash
fdisbull agent-skill --reference SKILL.md
fdisbull agent-skill --reference references/workflows.md
```

The first command supplies the technique; the second routes between analysis,
native debugging, scenes, spatial policies and text-player workflows. Retrieve
`references/udl-uil-udc.md` for block recovery and bounded compiler experiments.

Use the [README](README.md) when explaining the product to a person. Use the
quickstart, command help and the relevant skill reference when operating it.
Keep game-specific knowledge in the user's project evidence, with source,
version, runtime and claim boundaries. The repository ships the tool and
authored fixtures; original games, saved states and project databases stay
private.
