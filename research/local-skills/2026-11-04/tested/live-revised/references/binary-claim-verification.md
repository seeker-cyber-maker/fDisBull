# Verify a claim against the original binary

Use this addendum for a disputed mechanism, an exhaustive writer/absence claim,
or a cross-edition conclusion. Finding a useful value, candidate label or one
writer does not require this whole procedure: retain the positive observation
and continue. Guides and names can seed hypotheses immediately. Check only the
parts that affect the requested conclusion, keeping the decoded-image boundary
explicit. The all-field/all-reference controls below apply to exhaustive claims,
not to every reversible prediction.

## Contents

- [Decompose the claim](#decompose-the-claim)
- [Pin the artifact](#pin-the-artifact)
- [Locate the structure independently](#locate-the-structure-independently)
- [Enumerate references](#enumerate-references)
- [Cross-check editions](#cross-check-editions)
- [Report the verdict](#report-the-verdict)
- [Worked example: the "Nuclear Gandhi" claim](#worked-example-the-nuclear-gandhi-claim)
- [Limits](#limits)

## Decompose the claim

Split it into independently checkable parts:

1. **Stored value** — which record and field, and what bytes are there?
2. **Representation** — width, signedness, units and neighbouring fields.
3. **Writer** — does any instruction modify it, and under which condition?
4. **Trigger path** — is the claimed trigger (government change, event, turn)
   actually connected to a writer?
5. **Observed effect** — does a reader use the value in the claimed way?

A claim can be half true: the trigger may exist while the writer does not, or the
value may be stored but never used as described. Report each part separately; do
not let a true premise carry a false mechanism.

## Pin the artifact

- Reuse the tool's input identity, edition, size and container facts. Keep original
  bytes and decoded images private and outside Git; retain hashes as identities.
- If the executable is packed, decode it with a bounded, format-scoped decoder
  that preserves trailing overlays, and record source and output hashes plus the
  decoder identity. Unpacking is a transform; it does not prove runtime memory or
  loader behaviour.
- Rewrite the claim only in terms of the decoded image, and say so. A fact about
  the decoded root is not automatically a fact about every overlay or runtime
  mapping.

## Locate the structure independently

Do not find a table by assuming the claim is true.

- Use an independent anchor with a documented layout — a neighbouring table, a
  unique string, a loader fact — and derive the offset arithmetic from it.
- Confirm the derived offset by parsing the records and checking every plausible
  field (names, lengths, values), not just the one in the claim.
- Record the structure's DGROUP offset and the exact file offset, and show the raw
  bytes at the field.
- Establish width and signedness from the bytes and neighbouring records
  (`ff ff` beside other `ff ff` fields means a signed word, not `01 00`). Do not
  take the width from a document alone.

## Enumerate references

- Disassemble the decoded image as 16-bit code (fDisBull or a bounded Capstone
  pass) and search for the field's effective displacement
  (`structure_base + field_offset`).
- For every hit, classify read vs write, operand width and instruction. A store
  is authoritative evidence of a writer; a compare or register subtraction is a
  reader.
- **Positive control:** find the one known writer and show its store pattern. In
  Civ 1 that is the debug key: `imul 0x3A; rand_scaled(3); dec ax;
  mov word [reg+0x1512], ax` beside the "Leaders randomized." string.
- **Negative control:** show no other store, no byte-sized access and no
  arithmetic write to the displacement.
- **Computed pointers:** search for the base being materialized (`add reg, base`,
  `mov reg, base`) and inspect where those pointers go. A pointer pushed into a
  string-copy routine is not a field write.
- State the analysis boundary: decoded image, scanned instruction windows,
  static analysis. An unobserved writer through an unrecognized encoding remains
  unknown, not impossible.

## Cross-check editions

For a cross-edition claim, repeat the needed parse/scan on the editions in scope.
A selected-edition question does not require scanning other retained copies.
Identical layout and
identical writers strengthen the result; a divergent edition limits the claim to
the editions actually checked. Do not generalize to ports, remakes or later
games.

## Report the verdict

- Verdict per claim component: stored value, representation, writer, trigger.
- Exact hashes, structure offsets, field bytes and instruction sequences.
- What was proven, what remains unknown, and the scope (editions, static vs
  dynamic).
- Do not upgrade "no writer found in this image" to "the behaviour is impossible
  in every execution" without naming the analysis boundary and what a dynamic
  watchpoint or another edition would change.

## Worked example: the "Nuclear Gandhi" claim

Claim: Gandhi's aggression was stored as 1; adopting Democracy subtracted 2;
because the field was an unsigned byte it wrapped to 255, making him hostile.

Method and result against the original DOS binaries:

1. Inputs: CIV.EXE 474.01, 474.03, 474.05 (sha256 pinned in the intake), decoded
   with the bounded EXEPACK decoder; root and overlay tail preserved.
2. Anchor: `utypes` at DGROUP:0x112A (28 records × 34 bytes) ⇒ `civt` at
   DGROUP:0x14E2. Entry 7 (M.Gandhi) is at +0x196; `aggressive` is at +0x30, so
   code addresses it as `[reg + 0x1512]`.
3. Stored bytes at +0x30: `ff ff` = −1, with `ff ff` at +0x32 (−1) and `00 00`
   at +0x34 (0). The field is a signed 16-bit word. `1` would be `01 00`.
4. Writers: the only stores to `0x1512`/`0x1514`/`0x1516` in the image are the
   debug loop shown above. Readers are audience/alliance hostility subtraction,
   the expansionist `inc`/`imul`, civilized science-rate and margin subtraction,
   and advisor `cmp` labels.
5. No `sub …,2` write, no byte access, and no government-change write exists in
   the decoded image. Computed `civt + index` pointers are passed only to string
   copies for the leader, plural and adjective fields.

Verdict: stored-as-1 false; Democracy-subtracts-2 false; wrap-to-255 impossible
for a 16-bit signed field even if a subtraction existed. The story is not
supported by these DOS editions.

## Limits

- This is static evidence about named decoded editions, not a dynamic watchpoint.
- Original bytes, decoded images and game data stay private; only identities,
  offsets and instruction evidence belong in shared notes.
- A successful falsification of one mechanism is not a proof of every other
  behaviour claim about the program.
