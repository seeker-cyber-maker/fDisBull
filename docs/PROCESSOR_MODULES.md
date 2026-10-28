# Processor decoder seam (development candidate)

The in-process `fdisbull.processor` seam identifies a decoder module and its
version, named address space and address unit, capabilities and a state schema
(or `None` when state is not modeled). A `Location` belongs to a named space;
`DecodedInstruction` retains decoder facts plus explicit `Successor` records.
A successor may have no target when it is unresolved. Processor objects are
supplied explicitly to `decode_instruction`; there is no plugin discovery,
automatic import, execution engine or registry. Module code is trusted in-process code, not sandboxed. The dispatcher validates basic result structure, not semantics.

The existing flat analyzer now calls `NativeProcessor`, which delegates to the
same x86/ARM64 decoder and hands the same native fact dictionary back to the
existing analyzer. Its existing persisted traversal, native memory facts and
CFG behavior are unchanged. The separate `CILMethodProcessor` calls the existing
`disassemble_managed` decoder, keeping the assembly SHA-256 and MethodDef
identity in the address space and preserving multiple switch targets; invalid or unverified targets stay unresolved. It does
not change the managed command, execute CIL, model stacks or exception handlers,
or resolve dynamic calls. Both wrappers identify their adapter contract as
version `1`; this is not a claim that the underlying ISA is version 1.

**Not yet generic persisted VM analysis:** the flat project loader admits only
its supported native architectures. It cannot accept an arbitrary processor
object, and an instruction-indexed or multi-space guest is not silently stored
as a native byte-addressed project. The existing database and CFG assume
numeric native contexts and can reconstruct fallthrough using byte size;
changing those assumptions requires a separately designed persistence
migration. The authored toy VM in tests proves dispatch and successor shape,
not persistence, execution, or compatibility with a real game.

Processor facts do not establish a host-to-guest/file mapping: retain that as
separate, evidence-bearing provenance. Concurrent node scheduling and blocking,
device I/O, game UI, goals and grading belong to separate machine or task layers.
No AGI, Z-machine, QP2A, TIS-100 or Comet-64 processor is supplied by this seam.
A real module needs an authoritative encoding/semantics and its own tests;
QP2A acceptance remains with its native verifier, not this decoder seam.
