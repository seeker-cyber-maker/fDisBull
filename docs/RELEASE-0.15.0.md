# fDisBull 0.15.0: saved experiments and layer comparisons

This source candidate adds saved debugger experiments. Capture a native
checkpoint together with owned breakpoints, data watches, hook definitions and
hit counts, a bounded script and explicit memory observations. Restore the full
setup after restarting the project or launching another compatible session.

Baseline-versus-layer comparison restores the saved setup before each trial,
runs the same script, stores authentic frames/traces and reports captured
register, memory and execution differences. It restores the baseline controls,
layer stack and machine state afterward, even when a script fails. Incomplete
trials cannot establish equality. Fresh native control IDs are exposed through
stable captured keys in the route's `$controls` binding.

The [experiment guide](DEBUGGER_EXPERIMENTS.md) documents Python, foreground
JSON and offline inspection commands, dispatch budgets, provenance and failure
behavior. DOS experiments require the layers backend. Custom Wine/QEMU supports
its existing execution/data breakpoints, native states and layers; hooks remain
DOS-only. IDA and raw/outer-machine experiments are unsupported.

The [real DinoPark driver](../examples/dinopark/verify_experiments.py) verifies
fresh-session restoration, an execution breakpoint, eight read watches, a
once-hook and the 7,500-versus-5,000 gift-price lookup. States and the project
database remain private. Limited screenshots/traces and verification receipts
are recorded separately from game inputs. See [verification](VERIFICATION-0.15.md).

This is scripted experimentation, not deterministic record/replay or reverse
execution. It does not promote runtime code captures into static versions or
restore mounted host files. Existing ordinary native-state APIs retain their
control semantics. The Linux native-state CRC correction remains included.

Source preparation and local verification do not tag, publish or deliver a
release. Both ordinary and native Linux GitHub CI must pass on the eventual
release commit before tagging. Game files, saved states, project databases,
runtime images and compiled target fixtures stay out of Git and tool packages.
