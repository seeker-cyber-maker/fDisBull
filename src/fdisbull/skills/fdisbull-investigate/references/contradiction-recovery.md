# Recover from a contradiction

Use this when a reader, explanation or reconstructed operation works on some
cases but fails on others, or produces plausible output that conflicts with a
separate observation. This is a local repair loop, not a requirement to audit
every unrelated subsystem.

## Preserve the question and the counterexample

Keep one successful control, one failing case, the exact discrepancy and the
last working implementation. State the affected claim precisely. Failure in
one required case blocks that claim; it need not invalidate unrelated findings.
Do not relabel the case unsupported solely because it breaks the explanation.

Distinguish two situations:
- An operation cannot observe the needed fact: qualify its state, capability or
  failure separately. Use the ordinary recovery paths in [next steps](next-steps.md).
- The observation is valid but disagrees with your interpretation: revise the
  interpretation. Retrying the same successful command adds no discriminator.

## Find the first difference that changes the decision

1. Reduce the successful and failing cases to the same relevant inputs and
   observation boundary. Keep edition, units, state and source identity explicit.
2. Find the first mismatch, not just a later exception or final checksum.
   Inspect a bounded region or transition on each side of it.
3. Name at most two live explanations. Examples: wrong representation versus
   actual state change; wrong data boundary versus optional content; missing
   prerequisite versus target rejection. List the fact each predicts differently.
4. Choose one cheap available probe that separates them. Follow a consumer,
   compare an independently measured value, vary one relevant input, or inspect
   the unexplained field that predicts where the discrepancy begins.
5. Update only the assumption the result changes. Retain unresolved alternatives
   rather than silently choosing the one that makes more cases pass.

Unexplained bytes, counts and states are evidence. Before discarding them, test
whether they belong to the preceding component, the next component, a different
representation or an independently justified optional region. Useful checks
include units, widths, signedness, encoded versus decoded extents, addressing
contexts and version-dependent fields. Choose from the live alternatives;
do not mechanically try every possible explanation.

## What makes a repair a repair?

An assertion that fails is a diagnostic witness, not an obstacle to remove.
Relaxing it can be justified only by a new supported contract. Preserve what
changed, why the old assumption was wrong, and a check that would detect the
original mistake. A larger output buffer, truncated result or ignored remainder
can hide the symptom without explaining it.

Use a check independent of the assumption being repaired. Examples:
- A reported count versus the independently identified start of the next item.
- A decoded value versus the actual consumer's arithmetic or a controlled change.
- A generated output versus a separately derived small hand calculation.
- A transition result versus an observed state change under the same inputs.

Array lengths, valid JSON, a successful return code and agreement between two
functions sharing the same assumption are useful structural checks. They are not
independent evidence for field meaning or correct values.

First verify the previously failing case at the original point of disagreement;
then rerun the successful control and the relevant contrasting cases. Do not
require a large test suite for a cheap local probe, but do not claim a general
reader from a single easy example. Keep failures visible when reporting coverage.

## Worked decision: a counter appears to go backwards

Suppose a captured one-byte counter changes from 250 to 4, while a separate
observation records ten events. A signed subtraction reports -246. Do not delete
that sample or clamp the negative result to zero just to satisfy the report.

- A: the counter wraps modulo 256; ten increments predict (250 + 10) mod 256 = 4.
- B: the counter resets for another reason, so the wrap explanation is accidental.
- Next probe: inspect the updating instruction or observe one event on each side
  of the boundary with the same state. A broad restart that also changes the
  counter's owner would confound this comparison.
- If wrap is supported: qualify the update width and apply the rule to the old
  failing case. Check an ordinary interval, such as 20 to 30, too.
- Remaining limit: two snapshots alone cannot exclude multiple wraps. If elapsed
  events are not bounded independently, preserve that uncertainty.

The check is not merely that the new subtraction is nonnegative. It must agree
with an independent event count or the qualified update behavior. This example
supplies a reasoning pattern, not a default counter width for other targets.

## Stop honestly

If the required discriminator is unavailable within the budget, return the
supported subset, the concrete counterexample, remaining alternatives and the
next specific observation needed. Do not convert an unresolved contradiction
into completion language. If the repaired claim is sufficient for the user's
outcome, stop; do not use the anomaly to expand into an unrelated rebuild.
