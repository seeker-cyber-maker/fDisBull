# fDisBull 0.19.0

DOS targets can now launch from extensionless, long or otherwise non-8.3 host
filenames, and screenshots can use persistent preparation and cleanup scripts.
Both DOSBox backend patches also correct continuation at a native BIOS callback,
which could previously return a stale keyboard value and invent a guest action.

## DOS launch names and source identity

[DOS target eligibility](DOS_INPUT_NAMES.md) follows executable structure and
the imported source hash. Safe DOS names retain their existing behavior. Other
supported MZ targets receive a deterministic private DOS filename while the
project retains the original source name, path and bytes.

Direct DOSBox uses an exclusive temporary alias beside the original resources;
DOS-in-QEMU includes alias bytes in upload preflight limits. Native checkpoint
reopening recreates the same guest filename. Collisions refuse launch, and
cleanup retains detected changed or replaced aliases rather than discarding
them. The direct route requires write access to the game directory. External
writes through already-open alias handles during teardown are unsupported; the
temporary alias is a disposable launch input, not a user-output location.

## Persistent screenshot preparation and cleanup

[Screenshot hooks](SCREENSHOT_HOOKS.md) store immutable, version-scoped policies
in the project database. Python, live JSON requests and saved scripts can select
layers to suspend, bounded pre-capture steps, and post-capture cleanup. This
allows a rendering layer to be removed for a screenshot and restored afterward
without repeating the policy at every call.

The capture can require a completed frame after the last preparation-layer
change. Unexpected stops remain explicit, cleanup runs after failures, and the
original ordered layer stack is restored. An uncertain restoration closes the
session. Post-capture steps cannot execute the guest; this preserves click-frame
association. A new frame alone does not prove a control is ready or clickable.
These policies currently support DOS sessions, not PE64 or raw-machine sessions.

## Continuation and stop handling

The [DOSBox continuation correction](DOS_CONTINUE_CALLBACK_FIX.md) returns
execution to the emulator's normal decoder/callback loop without consuming a
callback in an unhandled debugger pre-step. A forced INT 16h boundary test fails
on the original backend and passes on both corrected patches, including native
checkpoint restoration. Resuming with no key input no longer increments the
authored keyboard counter; one key increments it once.

The final pause in a bounded run also preserves a terminal stop that wins the
race with the budget pause. It reads the existing operation's result without
issuing another continue. The callback correction covers continuation; explicit
low-level stepping across native callbacks remains unqualified.

## Investigation skill and reviewed integration

The bundled investigation skill includes scene, methodology and runtime-navigation
references. Package checks require all four skill resources. Expected reward,
probe cost and confidence remain separate decision criteria. Keyboard regression
coverage includes same-process and fresh-process mid-dialog restoration and
delayed modifier sampling; input-duration defaults are unchanged.

UIL producer/consumer ownership, UI completion phases, PQ1 runtime-resource layers
and the navigation capability ladder are documented proposals. This release
does not implement a UIL exporter, runtime-resource resolver, AGI/SCI adapter,
semantic navigation engine, C/C++ decompiler or source-view debugger. Imported
MZ static-address guards remain intact.

## Verification and release gates

The development source `8fc086b6066b4867ad841e041c8ab98c67d01452`
(`0.19.0.dev0`) passed [ordinary Linux CI](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40505498448)
with 1,112 tests passed and 91 native-dependent skips, and
[native Linux CI](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40505498445)
with 66 stable DOSBox, 372 layers DOSBox under Python 3.13.5, 16 PE64 installed-wheel
and 13 DOS/QEMU/boot installed-wheel checks. All native suites had zero failures,
errors or skips. Candidate archives matched GitHub's SHA-256 digests; all 105
wheel entries matched between ordinary and native-tested builds. The
[candidate receipt](evidence/0.19.0-release/CANDIDATE-CI.json) preserves this scope.

The [development evidence](evidence/0.19.0-dev/VERIFICATION.json) separately records
Mac native qualification, Linux offline qualification, the original callback
failure and the corrected result. Earlier failed scene checks remain preserved.
Those results qualify the recorded candidate, not the final version metadata.
Finalization preserves runtime/test/backend source while changing version and
release documentation. Both Linux workflows must pass on the exact final
0.19.0 commit before its annotated tag is pushed. Publication requires a later
decision; a versioned source tree or tag does not establish a published release.

The corrected backend has a new executable identity. Existing checkpoints remain
bound to the backend that created them; the earlier installation and backend
must be retained for checkpoints requiring that identity.

## Exclusions and deployment

Game files, saved games, native saved-state bytes, project databases and vendor
IDA executables/keys are excluded from Git and tool packages. Only source,
documentation and selected verification receipts are included. Existing private
projects, deliveries and unrelated work remain preserved. Shared installation
promotion and GitHub release publication are outside this finalization step.
