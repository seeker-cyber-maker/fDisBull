# QEMU spatial policy

Native COM/MZ DOS sessions support the same voluntary host policy as DOSBox:
`spatial_policy(mode=None, fair_play=None)`, `debug-spatial-policy` and the
`spatial-policy` saved-script operation. `Project.debugger(...,
backend='qemu-dos')` also accepts the existing `spatial_mode` and `fair_play`
launch options. Other native machine and non-DOS launch profiles retain their
existing restrictions.

The default is `assisted` with fair play disabled. A launch with `fair_play=True`
and no explicit mode selects `physical`. The session accepts `physical`,
`assisted` and `story`; fair play requires `physical`. Once fair play is enabled,
it cannot be disabled or changed to another mode in that session.

The existing four result fields are preserved: `spatial_mode`, `fair_play`,
`assisted_travel` and `voluntary`. `assisted_travel` expresses policy permission;
it does not establish that an assisted-action adapter exists or grant RAM/source
authority. This slice does not add spatial actions, assisted travel, scene
observations, absolute clicks or completed-frame identity. Ordinary explicit
debugger memory and execution controls keep their own contracts; the policy is
voluntary, as on DOSBox.

## Ownership and persistence

Policy selection checks the exact project, source, selected version and run,
then records the existing `spatial-policy` event. A private host lock serializes
policy changes without acquiring a native lock or calling QMP/GDB. Selection
does not change source bindings, pending input, execution history or selected
CPU/RAM freeze state.

The policy belongs to the Python debugger session. Native owner replacement and
restore of an older machine/process checkpoint preserve the current policy and
fair-play latch. Journal reopening exposes historical policy events without
reconstructing a live session or input authority. A newly launched session uses
its explicit launch options and the documented defaults.

The inherited host deadline bounds admission. A late completed selection raises
`TimeoutError` with its policy result, and the selected restriction remains in
force. Evidence publication failure also cannot undo an enabled fair-play latch.
Neither failure triggers guest execution or native cleanup.

## Script admission and verification

Whole-script admission checks every known literal and prospective policy
transition before executing any step. An earlier literal fair-play selection
therefore rejects a later literal attempt to relax it before an intervening RAM
write. Referenced values retain possible valid states during admission and are
fully checked again when resolved. Validation does not alter the live policy or
observe the guest.

`tests/test_qemu_spatial_policy.py` pairs the actual QEMU public route with the
existing DOSBox host method and tests source/ownership/deadline behavior, script
admission, event reopening and the actual owned-machine loader boundary.
`tests/test_qemu_spatial_policy_native.py` supplies authored COM witnesses for
older native machine and source-process checkpoint restoration after a newer
fair-play latch. The executed Linux baseline witness passed both cases with
QEMU ELF SHA-256 `71bef609647922544bfca23811caa0c08843a09d6b48c70293ab5ebd6cdb1a40`;
both owners were replaced and all owned processes were reaped. The adjacent
host gate passed 203 tests, and an independent host review passed 40 tests,
including two separate lock/deadline and racing-latch probes.
No compatibility campaign or backend-default decision follows from method
availability or these bounded policy checks.
