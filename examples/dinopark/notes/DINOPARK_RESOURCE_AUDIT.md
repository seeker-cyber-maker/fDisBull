# DinoPark external-file audit — 0.8

This audit checked the original archive and the stored instruction bytes. No
gameplay was executed and no Swift code was changed. File relationships below
are authored static evidence, not captured runtime heap mappings.

`dinopark/VARS.DAT` is 364 bytes, or 91 little-endian dwords. SHA-256:
`5e4b32d6e4afd060d72da79bfcac27fdca493905a7e19e299729e31431a1d153`.
The supplied `DINOSG.000` snapshot is 4,153 bytes. Both files and neutral layouts
are included so that an agent can inspect the data instead of searching only
instruction immediates.

## Correcting the base and field interpretation

Startup `38ff:003C/0040` stores an allocated DX:AX pointer at DS:BFC9/BFC7.
`0043–004D` supplies the `vars.dat` filename and `rb` mode. `0075–0085` supplies
91 four-byte elements and that far buffer; `008F` compares the result with 364.
The stored pointer identifies the beginning of the resource. There is no extra
`+94h` rebasing in that sequence.

| File offset | DWORD value | Verified use |
| --- | ---: | --- |
| `10h`, `14h`, `18h`, `1Ch` | 250, 500, 750, 1250 | Low/high WORD loads at `38ff:2343/233F`, indexed by SI×4 |
| `94h` | 20 | Low WORD read at `38ff:22DB` when DS:6FAC is zero |
| `98h` | 35 | Low WORD read at `38ff:22E9`, multiplied by DS:6FAC at `22EE` |
| `128h`, `12Ch`, `130h` | 1250, 1000, 750 | WORD table reads at `38ff:4504` for record types 0, 1, 2 |
| `134h` | 500 | Separate subtraction at `38ff:4517` when record field +0Ch is nonzero |
| `138h` | 3 | DWORD divisor supplied through `4618/461D` to the long-division helper |

The four values 1250/1000/750/500 are present. Their inspected use does **not**
establish four concession prices: the `4504` loop selects three entries, then
uses 500 as a conditional modifier before division, multiplication and a random
threshold comparison. The independently reported rest-room purchase debit of
1000 does not establish that this particular table access implements prices.
Likewise, the literal comparison with 3 at `3CD3` is not proof that the dword
at file offset 138h is the same cap.

The loop at `231D` starts a 32-bit local accumulator at 10000. Each nonzero
WORD among DS:BF4E/BF50/BF52/BF54 independently adds the corresponding
250/500/750/1250, giving 12750 if all four are set. It then multiplies an
existing 32-bit quantity by this factor, retains the low 32 bits and divides
unsigned by 10000. This establishes arithmetic, not gift names or sequential
reward tiers. The `22EE` path also stores only AX after multiplication; its
16-bit truncation must be retained in any claim of bit-for-bit behavior.

At `3CC1`, the tested balance must be strictly greater than the sign-extended
WORD at DS:687B, and signed DS:6FAC must be below 3, after earlier mask/random
gates. This establishes eligibility for the following call/message block. It
does not independently establish purchase enforcement or an entire reward rule.

## Confirmed fDisBull defect and correction

The original bytes and numeric operands were rendered correctly. DOS pointer
propagation was not sound: `_dos_transfer_extras` read the initial descriptor
bytes at DS:BFC7, promoted zeros to known BX=0/ES=0, and the next instruction
became an exact native reference to physical 94h. Startup had already assigned
a runtime allocated pointer there. An initial nonzero descriptor could be stale
for the same reason.

Revision 2 no longer promotes mutable DOS snapshot descriptors through LES/LDS
without reaching-value proof. The raw descriptor-cell reference remains; the
loaded pointer and subsequent native effective address stay unknown. Ordinary
explicit register constants, segment arithmetic and modeled stack transfers
still work. There is no new allocator or emulator.

Older DOS projects are marked as having stale pointer facts. Raw disassembly
remains available with obsolete operand references hidden. Rebuild explicitly:

```bash
fdisbull refresh-dos-state examples/dinopark.fdb --max-instructions 100000
fdisbull analyze examples/dinopark.fdb --max-instructions 100000
```

Repeat bounded analysis if pending work remains. This preserves original bytes,
versions and authored interpretations while recomputing native states and
dependent facts. Registered explicit roots are retained; their old register
assumptions are discarded. Derived analysis has its own queue.

## Inspect the resources

```bash
fdisbull attach-file examples/dinopark.fdb examples/VARS.DAT --kind resource
fdisbull attach-file examples/dinopark.fdb examples/DINOSG.000 --kind save
fdisbull define-type examples/dinopark.fdb VarsParameters examples/vars-layout.json
fdisbull apply-file-type examples/dinopark.fdb VARS.DAT VarsParameters --name vars
fdisbull file-data examples/dinopark.fdb VARS.DAT
fdisbull file-bytes examples/dinopark.fdb DINOSG.000 --offset 3872 --size 20
fdisbull file-reference examples/dinopark.fdb '38ff:22db' VARS.DAT 0x94 \
  --width 2 --access read --evidence 'Startup reads VARS.DAT into DS:BFC7/BFC9; this instruction reads buffer+94h.'
fdisbull file-xrefs examples/dinopark.fdb VARS.DAT 0x94 --size 2
```

The bundled VARS layout calls fields `param_0000` through `param_0168`; it does
not turn guessed economic meanings into labels. Save layouts describe only
the user-reported concession/staff word blocks, with staff roles left unnamed.
The whole save remains available through bounded byte queries.

Authored file references retain evidence, source CS context, width and optional
strided element bounds. They do not create native memory facts. A changed
source instruction makes its inherited reference stale; unchanged source bytes
alone do not prove that an upstream loader relationship still holds after a
patch. Revalidate the supplied evidence when changing program behavior.
