# Passive runtime-memory scenes

The public `scene_check` and `scene_assert` routes now admit explicit `fdisbull-scene-2` runtime-memory profiles. They evaluate bounded Boolean and scalar predicates over caller-witnessed RAM under one stopped owner, capture epoch and deadline. They preserve the existing compact result and persistence behavior while naming the narrower completion scope.

Two authored native cases passed on the corrected Linux QEMU producer: actual IRQ1 make/break observations and full checkpoint restore requiring a fresh RAM witness. Scene evaluation left native CPU state, virtual time and caller input unchanged. The independent host gate passed 55 cases, and the integrated gate passed 618 with 14 explicitly unrun native cases. These selections overlap.

The [verification receipt](verification.json) pins source, native inputs, review results and the original private receipt. Review caught a replacement-owner lock race and verified bounded first-failure behavior. Failed and corrected gate records are retained privately.

Frame-backed scene-1 observations, application readiness, geometry, scene actions, navigation, text and workflows remain separate work. A matched runtime predicate does not certify those contracts or promote a migration campaign.
