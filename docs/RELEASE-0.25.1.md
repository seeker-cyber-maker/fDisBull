# fDisBull 0.25.1

This maintenance release adds native DOS process termination reporting to the
0.25 line. A rebuilt backend reports `guest_exit` after the selected program's
DOS kernel cleanup and retains that evidence through debugger cleanup and
project reopening. It reports `guest_tsr` separately when the selected program
returns to DOS while remaining resident. A child exiting, an interrupt alone,
a timeout, or debugger shutdown cannot supply this completion evidence.

Both stable and layers complete backend patches include the fix. See the
[debugger contract](DOSBOX_DEBUGGER.md#dos-process-completion-and-debugger-cleanup)
and [candidate verification](VERIFICATION-DOS-TERMINATION.md) for tested cases,
requested return-code semantics and checkpoint identity limits. A Python-only
update cannot add the native kernel notification.

This source cut requires ordinary and complete required-native Linux CI on
its exact commit before tagging. Publication readback and a fresh Dot-launched
task in the republished default cloud environment are separate acceptance
checks. Existing releases, environment snapshots and the independent 0.26
development scope are preserved.
