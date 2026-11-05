# Mixed-state restoration contract study

This authored study composes a historical actor with a current world using
ordinary Python data. It has no guest adapter, debugger transport, native memory
writes or latency measurements. Successful compositions deliberately return
`execution_allowed: false` and `resume_safe: false`.

The [original D007 report](https://chatgpt.com/library?file_id=libfile_17ed165b07fc81918b8941eb8752f216&account_id=personal)
explains the observed v0.30 real-mode/protected-mode boundary and the unimplemented
native integration. This repository preserves the study as research source; it
does not promote its fixture rules into a production selective-rewind API.

## Run the source-free checks

From the repository root, with the Player package available for the related scene:

```sh
python -B -m unittest discover \
  -s research/syndicate-rewind/2026-11-02/tests -v
```

The 32 cases exercise explicit composition, entity/item generations, current
obstructions, unchanged ownership, batch refusal, stale tokens and append-only
history. They import the cumulative example's `world_history.py`. They do not
launch a game or requalify the original native observations.

## Contract preserved by the study

1. Identify the current-world parent, each historical actor source, the selected
   fields and recomputed relationships. A policy name does not discover RNG state.
2. Retain current time, other actors, ammunition, projectiles and RNG unless the
   declared intervention selects them. Rebuild current spatial relationships;
   do not copy historical global list heads or rewind the current CPU context.
3. Refuse reused actors/items, changed ownership, vehicle membership, unresolved
   conditions, terminal health, current blockers, stale tokens and overlapping
   batch requests. Fixture acceptance is not native clearance qualification.
4. Start a new observation epoch and retain prior events. A restored health value
   is an intervention, not erasure of earlier damage or a new healing claim.
5. Keep diagnostic and player projections separate. Historical observation reads
   do not mutate the live world or authorize actions using stale observations.
6. Native integration must honor the actual backend mode, address-range and
   capability contracts. Measure recording cost and restoration pauses separately;
   batching does not establish atomicity, seamlessness or resume safety.

`evidence/authored-example.json` is a synthetic fixture. `evidence/source-review.json`
is the original dated contract review, with no native execution. Historical
test logs and the nested reference archive remain in the
[D007 handoff](https://chatgpt.com/library?file_id=libfile_c767de7b08f08191bab4e8c1c1dc0ce3&account_id=personal).
