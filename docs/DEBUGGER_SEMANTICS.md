# Debugger observation semantics

Version 0.16.0 adds `status().semantics`, `run().stop`, and per-event trace
`identity` / `observation` fields. Original native stop reasons, addresses,
registers and trace evidence remain available. These fields describe what the
backend observed; they do not make different backends behave identically.

| Backend | Execution breakpoint | Data watch | Trace records |
| --- | --- | --- | --- |
| DOSBox / DOSBox in QEMU | Before selected instruction | After data instruction, before the next instruction | Before-fetch observations; earlier completion unknown; final budget record pending |
| Custom Wine/QEMU | Before selected instruction | Before the matching access | Confirmed completed steps, with pre-instruction bytes/registers |
| Optional IDA/Wine/QEMU | Before exact selected PC | Unsupported by this adapter | Confirmed completed steps, with pre-instruction evidence |
| Outer/raw QEMU machine | Before execution BP | Timing left unknown in the normalized view; retain native reply | Confirmed completed steps on selected vCPU; explicit bitness required |

`stop.trigger` identifies a watch independently of the older DOS
`outcome="breakpoint"`. `causing_instruction` is the instruction responsible
when established; `resume_pc` is the reported stopped location and can be null
when the native pause has no PC. `instruction_completed` is true, false or
unknown (`null`); `registers_stage` follows the native boundary. A timeout does
not prove that an instruction or access never occurs. Unsupported operations
continue to fail explicitly; inspect capabilities before choosing a route.

Trace identity names the selected source version, runtime address, project
mapping and context. `source_version` identifies the project's original input;
it does not assert that every executed byte equals that version. DOS real-mode
contexts retain CS identity, so two segment aliases are not conflated. Unmapped
instructions remain unmapped. No timing equivalence is claimed: DOS supports
guest ticks; PE uses host bounds; QEMU stepping masks IRQs/timers by default.

Experiment comparison validates capture counts and operation/range identities
before pairing observations. Misaligned lists raise a capture-alignment error;
they cannot yield an equality result. Trace event-count differences remain
observable differences within an aligned trace capture, and incomplete trials
still cannot establish equality. This hardens malformed helper input; it is not
a claim that a supported native route previously produced misaligned captures.
