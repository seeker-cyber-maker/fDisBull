# Amiga OFS / enhanced v2 intake and original-script probe

This experimental increment extends the raw-code pilot. It does not launch or emulate the supplied games.

Private inputs: user-supplied 880 KiB Amiga OFS ADF disk pairs in ZIP archives, Maniac Mansion and Zak McKracken. Their 00.LFL MD5 values are e781230da44a44e2f0770edb2b3b3633 and e94c7cc3686fce406d3c91b5eae5a72d, respectively. Match enhanced v2 Amiga English in ScummVM detection data. No v0/v1 real assets were supplied.

intake.py follows bounded OFS file-data chains, validates block checksums and child/sequence/size bindings, rejects conflicting readable disk copies, reports bad files rather than repairing them, and decodes the XOR-FF enhanced v2 index. Script payloads use the bounded old-bundle resource header (4 bytes) and directory offsets. It preserves per-resource source identities and emits scripts and a JSON receipt privately. Only 2-digit LFL names are read. No executable, boot sector or script is run by intake. No FFS, DOS/C64 or other file formats claimed. Room-0/unbound records remain excluded. A bounded header is not proof of valid costume, audio or script semantics.

```sh
python native/qemu-scumm/intake.py /private/game.zip /private/new-output
cd native/qemu-scumm
cc -std=c11 -Wall -Wextra -Werror -pedantic -O2 overlay/target/scumm/early.c run_script.c -o /tmp/scumm-run
/tmp/scumm-run 2 /private/new-output/scripts/001.bin
for test in test_early test_extended batch; do
  cc -std=c11 -Wall -Wextra -Werror -pedantic -fsanitize=address,undefined -fno-omit-frame-pointer -g overlay/target/scumm/early.c "$test.c" -o "/tmp/$test"
  ASAN_OPTIONS=detect_leaks=0 "/tmp/$test"
done
```

Expanded canonical decode includes variable-length range assignments and actor ops, indirect destination scalar operations, basic room/actor/verb/print/resource/script/cutscene and animation intent encodings. The actor metadata model commits only bounded synthetic costume, sound, palette, name-source span and talk-color changes; it does not bind resources or render them. The v1 palette form does not consume the extra v2 byte. Long instruction/event lengths are 16-bit; retained source bytes are bounded to 514. No QEMU migration/save state compatibility is promised. Status 6 is blocked effect: decoded but not committed or retired. Repeated `cont` leaves blocked, return and fault states stopped until restart. QOM exposes subop/payload fields and actor metadata; the native wrapper has now been built and exercised with authored fixtures.

Actual portable core tests: original fixtures, new extended fixtures, ASan/UBSan batch (768 opcode/version probes, 510 truncation probes, 60,000 paired random trials, state invariant with observations). These passed with `ASAN_OPTIONS=detect_leaks=0` after LeakSanitizer reported a ptrace incompatibility; memory leak checking remains unverified. Zero-filled opcode probe admits 50/84/84; counts depend on operands and include structural-only effects, not full execution coverage.

Private batch: 54/60 LFL files including index, 780 global object slots each; 169/148 bounded global scripts. MM disk1 53.LFL invalid chain; readable disk2 copy used. One MM script and seven MM sound entries have invalid size/location under this parser. No repair or inferred substitute. Static sequential prefixes for all scripts: MM 106 -> 590 instructions, 434 -> 3565 bytes; Zak 144 -> 543 instructions, 600 -> 3083 bytes. These are linear decode prefixes, not a CFG, full-script coverage or source-engine trace comparison. Script 1 MM: 6 -> 119 decoded instructions; portable execution 6 -> 7 retired, now blocked at pc 28 cutscene. Zak: 1 -> 24 decoded instructions; execution 1 -> 11 retired, blocked at pc 46 resource operation. All independent script probes initialize synthetic zero-state and stop at first yield, block, fault, termination or cap; no claim of original boot state or arbitrary standalone script semantics.

## Native qualification

The earlier missing-development-header blocker was resolved with recovered
offline dependencies. The target built from clean QEMU 10.0.13 and ran on
Debian 13 x86_64 with GCC 14.2, GLib 2.84.4, Pixman 0.44.0 and Ninja 1.12.1.
The overlay checks exact clean or prepared-AGI registration files and preserves
AGI entries; the complete native build was tested only on the clean base.

All 19 authored QMP cases passed, covering versions 0/1/2, scalar execution,
budget/yield resume, restart, sticky return/fault/blocked states, observation
invariance, capacity 0, decode/control bounds and 513-byte instructions. The
baseline passed 17/19: two page-crossing cases failed because QEMU `in_asm`
could not retrieve the full instruction. Registering code reads through
`translator_ldub` fixed both cases, including full-byte retrieval across a
4 KiB boundary.

From the repository root, write the receipt outside the checkout:

```sh
python3 native/qemu-scumm/test_native.py --qemu /private/scumm-build/qemu-system-scumm --output /private/scumm-native.json
```

All **317 private scripts** (169 Maniac Mansion, 148 Zak McKracken) were also
run through the native target. With observation mask 3, every native summary
and counter matched the portable probe. For every script, the full exposed
architectural state matched between native observation masks 0 and 3. All
634 native child processes exited and were reaped normally, with no timeouts
or budget stops. Source, binary and harness identities remained unchanged
throughout the comparison.

The runs stopped at 124 blocked effects, 144 faults, 18 returns and 31 yields.
Maniac Mansion script 1 retired seven instructions before blocking at PC 28,
opcode `0x40` (cutscene). Zak script 1 retired eleven before blocking at PC 46,
opcode `0x0c` (resource), with five actor-model change events. Each probe starts
an individual script in synthetic zero-state and stops at its first boundary.
Native and portable execution use the same semantic core: this establishes
wrapper integration and observation invariance, not independent SCUMM language
validation, an original boot state or complete gameplay.

Optional TCG plugins were disabled: upstream QEMU stores plugin instruction
lengths in an 8-bit field, so compatibility with longer SCUMM instructions is
unqualified. Hosted CI and release qualification were not performed.

Next: implement resource effects, script scheduling and cutscene state, extend
the bounded native/portable comparisons, recover room/object geometry, and
test against independent original-engine behavior. No v0/v1 original-game
coverage is claimed.

Encoding fact references (no implementation copied): ScummVM v2.9.0 engines/scumm/resource_v2.cpp, resource.cpp, scumm.cpp, script_v2.cpp, script_v5.cpp; ScummVM 2.2.0+dfsg1-4 script_v0.cpp; ScummVM Tools v2.9.0 descumm.cpp; detection table MD5 values from scummvm/scummvm master (pin exact commit before release). All game data and extracted payloads excluded from repository.
