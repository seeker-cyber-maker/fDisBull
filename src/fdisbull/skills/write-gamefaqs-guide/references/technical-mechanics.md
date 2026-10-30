# Technical mechanics without unsupported precision

## Contents

- [Explain the decision first](#explain-the-decision-first)
- [Specify an exact calculation](#specify-an-exact-calculation)
- [Describe randomness and timing](#describe-randomness-and-timing)
- [Label code and models](#label-code-and-models)
- [Check examples and boundaries](#check-examples-and-boundaries)
- [Compare builds and interfaces](#compare-builds-and-interfaces)

## Explain the decision first

State what a mechanic changes for the player, when it applies, and which choices
depend on it. Then expose the detailed rule and evidence at the depth needed to
audit that explanation. The technical FAQ exemplars show that exact formulas,
exception lists and honest unknowns can coexist with useful readable guidance.

Distinguish a recovered rule from strategic advice derived from it. A higher raw
damage field may not imply a better unit when firing delay, accuracy, cost,
armor, overkill and target availability differ. Identify the objective and
assumptions behind advice; do not silently turn a table into a universal ranking.

For a partially known system, explain the established part and leave named
unknowns. Do not import a familiar game's formula merely because it would fill
the missing section. Avoid presenting a plausible closed-form expression as the
game's implementation when the actual rule is stateful or branch-dependent.

## Specify an exact calculation

Record these details when they affect the claim; mark any missing detail instead
of inventing it:

| Element | What the reader needs |
| --- | --- |
| Variables | Meaning, units, scope, source field and admissible range. |
| Numeric model | Relevant integer width, signedness, fixed-point scale or floating behavior. |
| Order | Evaluation stages, intermediate values and branch-dependent sequencing. |
| Rounding | Floor, truncation toward zero, nearest or ceiling, at the actual stage. |
| Limits | Minimums/maximums, saturation or wrap, and whether they occur before or after modifiers. |
| Conditions | Guards, early returns, exceptions, overrides and side effects. |
| Random term | Domain, endpoints, weighting and conditional draw behavior when known. |
| Version | Original build, port/mod/settings and any tested correspondence. |
| Evidence | Locator and actual derivation or observation, with the remaining limits. |

Use explicit parentheses and define operators that could be ambiguous. Do not
replace truncating integer division with algebra over real numbers. Preserve
overflow and signed comparison only where the source supports them; an invented
16-bit cast is no more exact than omitted relevant wrap behavior.

A purely illustrative arithmetic example shows why order matters:

```text
A = 5, multiplier = 3, divisor = 2, defense = 4
floor(A * multiplier / divisor) - defense = 3
floor((A * multiplier - defense) / divisor) = 5
```

These are different rules. This example is not a recovered game formula. A guide
should show the rule supported by the actual target and label a demonstration
calculated from that rule separately from an observed in-game result.

Do not conceal a missing term behind precise downstream numbers. If a formula's
input scale is unknown, report that limitation or a justified range. A derived
example can verify internal arithmetic without verifying that the game uses the
formula.

## Describe randomness and timing

Distinguish a stored threshold from a probability and an observed frequency from
a theoretical distribution. For a claimed probability, determine the draw
domain, inclusive endpoints, comparison (`<` versus `<=`), weighting, rejection
rules and conditional draws. Do not assume successive draws are independent or
uniform just because a function is called random. Preserve RNG state or seed
limitations when reproducibility matters.

If estimating from observations, state sample size and relevant conditioning;
do not present a small sample as an exact rate. If the generator or mapping is
unresolved, keep the rate qualified. A byte reduced modulo a range does not
automatically produce a uniform distribution, and two such coordinate draws do
not establish Gaussian scatter. Check that distribution names agree with the
described algorithm.

Identify the clock: simulation tick, frame, turn, animation update, wall time or
event-driven decrement. Record pause/menu effects, speed settings, calls per
update and extra decrements caused by actions when known. Converting a counter
to seconds requires a qualified update cadence. A counter of 450 does not alone
establish 15 seconds; a displayed frame rate does not establish its update rate.

For asynchronous or delayed effects, distinguish admission, visible feedback,
state commit, later events and persistence. A failed command can consume time or
resources. Preserve order-sensitive effects and cancellation rather than
rewriting them as one atomic function. Route advice depending on these details
must retain their qualification.

## Label code and models

Use one of these descriptions for each implementation or algorithm listing.
Label player commands, console transcripts and extracted data listings by their
actual purpose and source instead:

| Label | Required context |
| --- | --- |
| Actual disassembly | Target identity, mapped/file address convention, instruction region and tool evidence. |
| Decompiler output | Tool/version, input/region, known analysis limits and any manual edits. |
| External source excerpt | Project/author, pinned commit/path, relevant configuration and attribution. |
| Reconstructed pseudocode | Which recovered facts it expresses, analyst-added names and omitted details. |
| Illustrative model | Its teaching purpose and explicit statement that it is not recovered implementation. |

Do not imply that a clean function name existed in the original binary. Keep
external source identifiers attributable. A matching name or similar control
flow is a lead, not a complete original-to-port correspondence proof.

Write short pseudocode only when it clarifies a supported mechanism. Use named
unknown operations or branches when necessary. State whether omitted state,
I/O, timing and exceptional paths matter. A pure model of one calculation does
not prove the whole original interaction is atomic, equivalent or playable.

Use source snippets sparingly with attribution; prefer original explanations
and concise reconstructed models. Do not reproduce extensive guide text or
source-port code just to make a technical appendix look substantial.

## Check examples and boundaries

Choose checks that discriminate plausible interpretations. For an exact rule,
verify a normal example and relevant boundaries: equality at a threshold, just
below/above a cap, zero/negative values if allowed, minimum/maximum random draw,
or an exceptional item/status. A worked example does not cover branches it never
enters. Derive expected results independently of the code being checked when
practical.

Check three kinds of consistency separately:

1. **Internal:** do prose, table fields, formula and pseudocode say the same
   thing, with the same units, conditions and ordering?
2. **Evidence:** does each asserted step follow from the actual artifact or
   cited observation? Which steps remain inference?
3. **Target behavior:** where executed, do recorded inputs/outcomes agree for
   the relevant build and state, and what remains outside the observations?

Run small arithmetic or formatting checks when useful. Do not treat their success
as a native-game test, an exhaustive proof, or a new independent source. Do not
require a full emulator setup merely to report an honestly scoped static result.

Preserve counterexamples. If most cases agree but a threshold does not, narrow
or correct the rule and identify affected advice. A solver result applies only
to its encoded model and assumptions; report unsolved or missing semantics.

## Compare builds and interfaces

Use an explicit comparison table for release differences: source, field or
behavior, interpretation, applicable build/settings and evidence. Check data
changes separately from engine changes. A guide hosted under one platform may
describe another version; read its own scope and validate target correspondence.

Compare raw fields to raw fields before comparing displayed quantities. Keep
scaling, cooldowns, damage aggregation and per-shot/per-second distinctions
visible. Source-port fixes and optional enhancements can change behavior even
when the same game data is loaded.

Treat a conflict as a question to resolve, not a reason to relabel one source as
the original truth. Pin the compared source and preserve the particular mismatch.
If the target's relevant bytes or runtime evidence are unavailable, state that
the comparison is limited to the documents/implementation inspected.
