# fDisBull 0.26.0

The 0.26.0 release source concentrates on recovery and trustworthy observation.
It includes the reviewed recovery and processor work plus PR #30's definitions
and contract roadmap. Ordinary and complete required-native Linux CI must pass
on this exact source commit before tagging. GitHub publication and changing the
shared installation are separate actions; the published and installed version
remains 0.25.0 at this source-finalization cut.

- **Original-backed recovery:** PR #26's reviewed `17bc719` amendment retains a
  reachable stopped DinoPark provider after an action failure, records confirmed
  or unknown effects before replying, blocks new actions/checkpoints and allows
  explicit restoration of a prior qualified checkpoint. A confirmed food order
  and a pending notice return remain separate; acknowledgment does not buy
  again. Running or unreachable guests retain the fatal path.
- **Z-machine inspection:** PR #28's `bfcdfe8` adds a bounded v3 processor,
  source-order listing and recursive analysis through `zmachine-disasm` and
  `zmachine-analyze`. Source identities, frontiers, unresolved transfers and
  overlaps remain explicit. This is static inspection, not a new VM, persisted
  guest analysis database or native/guest debugger address mapping.
- **Truthful DOS watch stops:** the generic observation now reports
  `registers_stage="after-access"` and `instruction_completed=null`. A partial
  REP can stop with work remaining; a different PC alone also does not certify
  completion. Native records, causing/resume PCs and registers remain intact.
- **One definitions map:** documentation PR #30 reconciles UDL executable
  backings, UIL's shared editable vocabulary and UDC implementation selection.
  It separates the Z scene interface from Z-machine bytecode, identifies
  semantic/binding revisions and maps interface, readiness, geometry, effects,
  proofs and projection proposals. It retains #29 and historical acceptance
  ledgers without turning proposals into implemented features.
- **Agent/package gates:** the investigation skill routes the new inspection
  commands and explains partial-watch and recovery-only boundaries. Both native
  profiles include the new processor, recovery lifecycle and REP checks. Source
  packages explicitly retain the authored RFC 0002 vectors and replay summary.

The [verification record](VERIFICATION-0.26.md) separates executed checks from
pending qualification. Game/story inputs, generated retaining packages,
native states and project databases stay private and outside Git/tool packages.

## Recommended work after this scope

The next reusable investment is the hash-bound runtime-resource resolver from
#6, then #8's semantic conditions over those identities. Persistent guest
instruction facts and trace-informed seeds would extend #28 without conflating
guest offsets with native addresses. Content-readiness and KQ1 arrival cases
from #9/#16 should retain separate, target-qualified acceptance.

The linked interface/world contracts (#7/#10), broad proof adapters (#11),
synthetic HUD (#22), and generic Rosetta/compiler/editor work (#29) need their
own bounded vertical slices. They are not promises for 0.26. No original PR is
closed merely because its definitions or some of its requirements appear here.
