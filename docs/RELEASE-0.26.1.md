# fDisBull 0.26.1

The 0.26.1 candidate combines current main's PR #34 and PR #35 with the
expanded guide skill from PR #33. It concentrates on recovering a stopped
investigation without repeating an original action, reporting actual DOS
process termination, and writing useful guides from recovered knowledge.

- **Read-only batch reconciliation:** `BatchSession.reconcile()` and the
  `reconcile` operation can repair local bookkeeping from a durable complete
  result and a matching fresh session/context/state witness. They send one
  observation and no action, ACK, save/load or guest-time request. They never
  dispatch the next batch step. A bound restore certificate can finish the
  local rewind after readback failure without loading again. Missing or
  incomplete replies and partial original intentions remain unresolved.
- **Selected DOS program exit:** both complete backend patches preserve
  PR #35's selected-PSP identity and report `guest_exit` after DOS termination
  cleanup. Child exits and debugger shutdown do not complete the selected
  program. TSR evidence is separate. The observation retains process evidence
  while final target registers and the terminating instruction stay unknown.
- **Broader game-guide skill:** the guide covers unused code and resources,
  defects, secrets, conditional access, alternate routes, category/timing rules,
  completion inventories, file/media specifications and qualified engine reuse.
  Externally sourced game facts remain in explicitly selected references, with
  an information-policy warning. Both installed skill gates remain required.
- **Combined acceptance:** both required-native DOS profiles now run the
  reconciliation tests alongside guest-exit, conservative REP-stop and recovery
  tests. Full ordinary and complete required-native Linux CI on the exact final
  source commit are required before tagging.

The [verification record](VERIFICATION-0.26.1.md) binds each executed check to
its source and backend. A green branch check is not combined acceptance, and a
matching witness does not certify an incomplete original intent.

Original game/story files, saved machine states, project databases and raw
private deliveries remain outside Git and tool packages. Authored scripts and
sanitized evidence can be exported separately. Publishing a GitHub release and
updating the shared installation are separate from this source/tagging task.

## Scope retained from 0.26.0

The Z-machine v3 processor remains bounded static inspection. Native/guest
address mapping, persisted guest instruction facts and whole-game recovery
are not introduced by this maintenance scope. The current data-watch contract
continues to report after-access registers with unknown instruction completion;
a different PC alone does not establish completion.
