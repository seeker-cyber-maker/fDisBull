# 0.25.0 integration verification

This record distinguishes the combined source from earlier PR evidence.
Game/story files, native checkpoints, generated story-retaining packages,
private replay directories and project databases stay outside Git. Only
sanitized summaries and authored tests belong in the repository.

## Required gates

Before main is updated, the final integration SHA must pass ordinary Linux CI
and the complete required-native Linux workflow. The latter includes both
DOSBox profiles, installed offline-kit checks and the unified Wine/QEMU,
DOS-in-QEMU and boot-context acceptance job. Earlier green PR heads are intake
evidence, not a substitute for these combined-source checks.

The local source/package and native evidence will be recorded here after the
combined candidate is frozen. Tagging, GitHub publication and replacing the
system installation are separate actions.

## Contract under test

- Keep the previous Zork converter, Word16 consumer and legacy tests intact.
  Recover only the qualified semantic slice and retain unhandled IR explicitly.
- On an execution fault, preserve actual effects, report completed calls and
  interrupted-effect uncertainty, keep the prior successful checkpoint and
  return failure. Transcript delivery failure must not hide the original fault.
- In DinoPark, preserve a confirmed transaction across a later incomplete UI
  transition. Do not repeat native input merely because a reply or observation
  is incomplete.
- Ship one discoverable investigation skill with valid packaged references.
  Keep research hypotheses, authored benchmarks and native findings distinct.
- Check source, wheel and player archives for excluded inputs. No game files,
  saves, emulator states, databases or raw private deliveries are permitted.

## Limits retained

Static LE analysis is not protected-mode native debugging. GOG unpacking needs
a real optional extractor and does not run the installer. Zork's bounded
recovery is tied to its exact edition. A short text/checkpoint comparison does
not establish full memory, RNG, scheduler or whole-game equivalence. The
[backlog audit](PR_BACKLOG.md) records remaining requirements without treating
historical PR closure as complete implementation.
