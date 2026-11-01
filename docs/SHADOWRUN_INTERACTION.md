# Shadowrun opening interaction: bounded source and target paths

This investigation applies to the exact reviewed Genesis Shadow Run (U)
cartridge. The original-core ordinary-input route reaches the opening field's
Stoker doorway with UP. The captured contact produced raw collision `$FFC2`,
two negative corner samples, and event index `2`. A separate continuation
from an original-core checkpoint displayed the sign, advanced with A to the
manager's choices, selected the later-conversation response with B, and used A
to leave; the original field view returned. These are bounded observations,
not qualification of every interaction or dialogue choice.

`shadowrun_interaction.c` contains independently compared procedural slices:
the four-corner gate, collision-word projection, context/target resource
selector, event-target branch, and the transition writes after a carry-set
return. The separate `shadowrun_request_stoker` composes a conservative subset:
scene 2, event mode 0, context 2, phase 0, collision `$FFC2`, the observed
actor and latch gates, and at least two negative corners. It refuses other
cases rather than substituting a generic event. It requires **carry set from
the original activity dispatcher as an explicit external assumption**. The
side effects inside the original `$1651E` activity routine are not implemented
or claimed by this request. Returned resource offsets identify the source
prompt and portrait; they are not bundled original data.

The five source boundaries were checked on the pinned Genesis core against
the typed UIL for 920 controlled cases: 271 resource-selection cases, 262
collision projections, 257 corner gates, 128 event-target branches and both
carry outcomes for transition writes. Controlled entry does not by itself
prove a full game route. The exact identities, observation scope, and
limitations are in [interaction.json](evidence/shadowrun-uil-2026-11-01/interaction.json).

The NES modal controller is a **target presentation adapter**, not a lift of
the original dialogue interpreter. For the observed phase-0 path, it advances
sign → choices on a new A press, choices → farewell on a new B press, then
farewell → field after A and release. It reports other action choices as
unsupported. It does not model inventory, debt, other quest branches, the
original dialogue timing, or every original dispatcher side effect. Native NES
integration and its rendered result require separate testing.
