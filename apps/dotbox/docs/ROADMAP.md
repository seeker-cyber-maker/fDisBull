# Standalone engine milestone

The current order supersedes the earlier proposed gameplay sequence below:

1. Extract the working DOSBox runtime and minimal storage/validation components;
   no fDisBull runtime installation or source-tree dependency.
2. Verify the existing Codex/WebRTC ownership integration surface. Preserve the
   native input guards, but do not substitute native handoff for the harness UI.
3. Verify a clean wheel install, actual native input/frame operation, ownership
   isolation, persisted controls and owned-process cleanup.
4. Resume harness ergonomics and game-specific work only after the independent
   framework is working. Audio remains deferred.

Prior AGI/walking/HUD development is preserved in the original checkout and a
private source snapshot. It is not required for this cut.

---

# Initial work plan

This is a proposed sequence, not completed implementation. Keep each slice
small enough to demonstrate through the visible original game.

1. **Establish the target runtime and reuse material.** Inspect Dot's actual
   computer through supported tools. Record runtime versions and display/audio
   capabilities; test access to takeover state. Locate the existing King's Quest
   harness and evidence. Identify the smallest reusable fDisBull components.
2. **Retain one visible DOSBox-X session.** Keep it alive between agent calls;
   observe frames and exercise ordinary controls. Demonstrate user takeover,
   release, held-input cleanup and fresh observations after user play.
3. **Prepare a bounded starting harness.** Establish common controls and a
   few useful starting Z scenes. For a supported AGI edition, read interpreter
   state directly. Measure first useful input and total cold preparation time.
4. **Learn while playing.** Capture a new action, validate its outcome, persist
   it and reuse it without restarting the game. Prepare updates while the user
   plays; publish between live actions. Track observed user progression and
   harness coverage separately in the optional Z HUD.
5. **Reuse and adapt packages.** Restart with the learned harness, import it
   into a fresh project and skip rediscovery. Adapt one nearby edition using
   only the included operational notes and bounded validation. Exercise updates,
   conflicts, incompatible editions and interrupted actions.
   For native menu/state machinery, first consult the
   [DinoPark reuse map](DINOPARK_REUSE.md): preserve its recovered mechanics,
   transaction phases and existing control evidence, then bind the smallest
   needed route to DotBox. A complete new DinoPark playthrough is not a gate.
6. **Run the next Dune transfer test.** Freeze the general mechanisms and AGI
   work before Dune-specific adaptation. Record the earlier assisted CD opening
   trial and other exposure; this is not an untouched or blind holdout. Follow
   [the validation plan](DUNE_VALIDATION.md) through menus, selected entities,
   travel and one delayed strategic order. Use ongoing reverse engineering at
   actual ambiguities, then compare adapted results with the frozen baseline.
7. **Qualify installation and the Showcase experience.** Build a tailored
   offline DOSBox-X package for the measured Dot runtime; test a clean install
   through the release portal. Demonstrate cold start, user participation,
   incremental learning, warm reuse and sharing. Validate the secondary usage
   scenario separately.

Record timings for agent thinking/dispatch, local execution, preparation,
new-context pauses and warm reuse. Count failed attempts. Existing fDisBull
execution benchmarks do not establish DotBox preparation or end-to-end latency.
