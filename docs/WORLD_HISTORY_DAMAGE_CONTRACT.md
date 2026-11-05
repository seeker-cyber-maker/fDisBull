# Reusable world-event history and damage-observation contract

This is a proposed integration/skill contract motivated by the original Syndicate
D006 experiment. The bounded research implementation is not a new core API.

| ID | Requirement |
| --- | --- |
| WH01 | Preserve each occurrence with a stream/producer/occurrence identity, monotonic journal sequence and stable event ID. Text equality, same tick and reusable object slots must not merge occurrences. |
| WH02 | Deduplicate transport redelivery, not gameplay. Conflicting redelivery refuses. Persist before guest resume; capacity/write failure holds capture without eviction or automatic action replay. |
| WH03 | Summarize for presentation only. Bound replies; preserve constituent IDs, stable-watermark pagination, independent notice queries and per-consumer explicit acknowledgements. |
| WH04 | Fork histories on restore with explicit ancestry. Old observations remain retained but do not become evidence from the new timeline. |
| WH05 | Keep diagnostic knowledge and player-visible knowledge separate. Unknown/offscreen attackers remain unknown to a normal player. Filtering one log does not certify all other world fields or cursor metadata as fair-play safe. |
| WH06 | Prefer source-qualified recipient damage/condition/health hooks or public events over per-projectile polling. Discover bindings once, validate module/code identity each load, and report uncovered writers. |
| WH07 | Capture direct source, responsible actor when supported, type and committed effect separately. Do not infer source from nearest entity, currently held weapon or a stale last-attacker field. |
| WH08 | Distinguish contact, condition application, numeric loss, aggregate snapshot delta, terminal sentinel, death and completion. Delayed effects need scoped causal links; repeated contacts are not automatically extra HP losses. |
| WH09 | Measure matched original trials separately from authored event-storm tests. Guest ticks, fire requests, projectile count, hits, ammo, HP and host overhead are distinct measures. |
| WH10 | Multiplex watches under one original-session owner. A history subscriber must not consume another action's breakpoints, silently resume a held guest or replay an uncertain movement. |
| WH11 | A current entity reference must be type/lifetime qualified. Slot reuse, equal-value stores and source-kind branches can invalidate a simple owner lookup. Preserve candidate, qualified and unknown attribution. |
| WH12 | Keep original code/memory/checkpoints private. Publish authored code, narrow binding metadata and sanitized observations; do not present consistency checks as authentication or fresh native replay. |

## Minimal workflow

First use the ordinary world projection for context. When a health or condition
change needs an explanation, locate its original writer using an actual CPU stop,
not a mislabeled watched-data address. Recover the smallest recipient-side call
context that supplies source/type. Verify store completion and one counterexample
or alternative source kind. Record the profile with source/load/field semantics.
Subsequent forward play can attach that profile to recipients without rewinding
or tracing all shots. Unknown cases remain event records with unknown cause.

For a black-box player, use only visible feedback or an exposed event API. Native
attribution belongs to a diagnostic projection unless the perception contract
independently permits it. Never manufacture a visible attacker simply because
the debugger knows its address.

Syndicate motivation: immediate Pistol/Mini-Gun health commits carry an effect
owner, laser/flame apply deferred conditions, and vehicle contact skips the same
last-source update. One universal bullet probe or last-attacker field is wrong.
