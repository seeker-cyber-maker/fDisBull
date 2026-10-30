# Debugger observation semantics

Version 0.16.0 adds `status().semantics`, `run().stop`, and per-event trace
`identity` / `observation` fields. Original native stop reasons, addresses,
registers and trace evidence remain available. These fields describe what the
backend observed; they do not make different backends behave identically.

| Backend | Execution breakpoint | Data watch | Trace records |
| --- | --- | --- | --- |
| DOSBox / DOSBox in QEMU | Before selected instruction | After the observed data access, at a normal-core check; whole instruction completion unknown | Before-fetch observations; earlier completion unknown; final budget record pending |
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

Starting with the 0.26 candidate, DOS data stops use
`registers_stage="after-access"` and `instruction_completed=null`. Earlier
versions reported completed unconditionally. A repeated string instruction can
stop with the same CS:IP and a nonzero remaining count after only some elements
were accessed. A different stopped PC is not sufficient either: interrupts can
change the observed context. Keep the causing PC, resume PC, raw registers and
memory effects as evidence; the access hook does not certify completion of the
whole instruction or the larger game action. Authored native tests distinguish
a completed four-word copy from a partially executed 8,192-word copy. Both retain
unknown completion in the generic normalization because it carries no native
completion certificate.

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
