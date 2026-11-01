# Visiting fDisBull with Claude

Read [AGENTS.md](AGENTS.md) for the shared project contract and
[the agent quickstart](docs/AGENT_QUICKSTART.md) for executable entry points.
These are the same maintained guides used by Codex and other agents.

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
authored fixtures, including the explicitly approved three-game freeware corpus
described in AGENTS.md. Other original games, saved states and project databases
stay private.
