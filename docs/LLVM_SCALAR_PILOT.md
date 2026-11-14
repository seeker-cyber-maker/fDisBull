# LLVM scalar compilation pilot (experimental)

Additive real LLVM output from validated, closed fdisbull-il-1 scalar programs. The API is fdisbull.llvm_scalar_pilot.emit_llvm_scalar_v1(document), returning LLVM IR and stable sorted state slots. Compile using clang -O2 -c -x ir candidate.ll -o candidate.o.

Admitted: u8 and bool state; set, add, subtract, and pure conditional if. Refused: host effects, graphics, sound, require, tables/lookup, wide values, IL v2, arbitrary x86 or QEMU/TCG lifting. Caller supplies canonical bool bytes and valid state. Byte arithmetic wraps. No full game or original machine equivalence claim.

Focused test: Clang-compiled shared object versus existing execute_il on 512 input combinations. This is an exhaustive comparison for the varied u8 and Boolean inputs with remaining limit state held at 137, not a universal correctness proof.

Next: ABI/type expansion, IL-v2 CFG, runtime provider effects, TCG-to-LLVM lifter adapter, blast-radius masks and proof-guided original-vs-native comparison. Keep compilation machinery optional; do not change existing UDC behavior silently.
