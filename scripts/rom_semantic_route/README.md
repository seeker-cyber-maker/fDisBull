# Authored SH-2 arithmetic experiment

This fixture is authored: big-endian bytes `60 43 70 01 00 0b 00 09`.
Use a new private directory outside Git for `WORK`. Install Ghidra 12.2 and
Java 25, and obtain saturn-recomp at commit
`532fd6054ba3171339c972fab05ebd159f29260d`. The code-generation source and
runtime header must be clean. With `GHIDRA_HOME`, `JAVA_HOME`, `SATURN_ROOT`,
`WORK`, and a Python environment containing fDisBull and Z3 explicitly set:

```sh
mkdir -p "$WORK/project"
python -c 'import pathlib,sys; pathlib.Path(sys.argv[1]).write_bytes(bytes.fromhex("60437001000b0009"))' "$WORK/typed.bin"
"$GHIDRA_HOME/support/analyzeHeadless" "$WORK/project" authored \
  -import "$WORK/typed.bin" -loader BinaryLoader -loader-baseAddr 0x06010000 \
  -processor SuperH:BE:32:SH-2 -noanalysis \
  -scriptPath "$PWD/scripts/rom_semantic_route" \
  -postScript DecompileAuthoredSh2.java "$WORK/typed.c" -deleteProject > "$WORK/ghidra.log" 2>&1
PYTHONPATH="$SATURN_ROOT/src" python -m saturnrecomp.recomp \
  --out "$WORK/typed-recomp" "TYPED=$WORK/typed.bin@06010000+06010000"
PYTHONPATH=src python scripts/check_rom_semantic_route.py \
  --sh2 "$WORK/typed.bin" --ghidra-c "$WORK/typed.c" \
  --saturn-cpp "$WORK/typed-recomp/p_TYPED_000.cpp" \
  --ghidra-home "$GHIDRA_HOME" --saturn-root "$SATURN_ROOT" > "$WORK/receipt.json"
```

The Ghidra log must show `PARAM_STORAGE=r4:4 RETURN_STORAGE=r0:4`.
The prototype is supplied by the experiment; it is not recovered from game
code. The checker compares only the register arithmetic boundary and does not
prove the generated files came from the supplied generator: preserve the log,
source, checkout identity and receipt together. `uint` and `c.r[]` are assumed
to have the indicated 32-bit unsigned types. Native compilation checks three
edge inputs; the solver checks parsed models, not native execution. Return
control, instrumentation, flags, memory, timing and other registers are
excluded. Only the exact generated syntactic forms are supported.
