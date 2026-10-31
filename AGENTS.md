# fDisBull for agents

fDisBull gives an agent persistent program analysis, headless native debugging,
named scene actions, explicit spatial policies, a separate text player, and
bounded source-to-UIL experiments. The analysis project stores discoveries and
evidence between turns. An emulator process is owned by its live server/context;
saved run history does not reconnect it after exit.

## Start with the user's task

- Read [the agent quickstart](docs/AGENT_QUICKSTART.md) for the workflow chooser,
  concrete commands, backend requirements and portable project setup.
- Read `fdisbull agent-skill --reference SKILL.md`, then retrieve only the
  reference needed for the next question. The bundled skill is available even
  from an installed wheel, without opening a project.
- For a human-readable review of established game knowledge, read
  `fdisbull agent-skill --skill write-gamefaqs-guide --reference SKILL.md`.
  Use `agent-skill --list` to discover both bundled skills. Keep attributed
  external findings distinct from recovered and observed game behavior.
- Use `fdisbull --help` for commands, `fdisbull methods` for JSON methods and
  `fdisbull doctor --help` to choose environment checks. Verify capabilities in
  the actual backend before planning a native operation.
- Static analysis needs no running emulator. Debugging original DOS/PE64 code
  needs the matching separately prepared backend and the user's own inputs.
  The standalone player consumes an authored projection or compatible endpoint;
  it does not automatically recover an entire game's scripts.
- Choose physical, assisted or story policy explicitly. `text-host --fair-play`
  locks physical play for that session. Assistance is useful for investigation;
  record it when reporting how a result was obtained. Live player mode can save
  between model turns; verify the checkpoint receipt before claiming persistence.

For a scene task, prefer named actions, sparse pixel/memory predicates and
bounded waits. For a writer question, use a watchpoint and a short trace. For a
theory, restore a saved experiment and compare a baseline with one declared
layer change. For UDC work, qualify each source/model/output edge separately;
preserved file bytes and a narrow Z3 result do not establish whole-game recovery.

Keep one active question and choose probes by expected reward, cost and
confidence. Return compact values and artifact IDs for routine success; expand
the evidence on failure, ambiguity or first qualification. Preserve missing
observations as unknown. Distinguish visible, ready, enabled and committed.

## Working in this repository

The [README](README.md) introduces the product to people. Technical contracts,
API examples and scope limits belong in the linked docs and bundled skill.
Preserve that audience split when adding features. Testimony from users/agents
must be attributed and scoped to what they actually tested.

Keep original game/story files, emulator states, byte-retaining project
databases and raw private deliveries out of Git and tool packages. Use a
private workspace outside the checkout for runtime inputs and UDC outputs.
Export authored scripts and sanitized verification evidence separately.

Use the repository's test/build commands. A release commit needs ordinary and
required-native Linux CI on its exact SHA before tagging. Publishing a release
or changing a system installation is a separate user-authorized action.

## Game files and target identity

Do not upload original or modified game binaries, assets, story images, saves,
emulator states or byte-containing databases/archives to GitHub or packages.
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
