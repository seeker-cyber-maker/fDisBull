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
  "/tmp/$test"
done
```

Expanded canonical decode includes variable-length range assignments and actor ops, indirect destination scalar operations, basic room/actor/verb/print/resource/script/cutscene and animation intent encodings. The actor metadata model commits only bounded synthetic costume, sound, palette, name-source span and talk-color changes; not resource binding or rendering. The v1 palette form does not consume the extra v2 byte. Long instruction/event lengths are 16-bit; retained source bytes are bounded to 514. No QEMU migration/save state compatibility promised. New status 6 is blocked effect: decoded but not committed or retired. Repeated cont must not advance blocked/terminal state. QOM source exposes subop/payload fields and actor metadata; QEMU wrapper remains uncompiled.

Actual portable core tests: original fixtures, new extended fixtures, ASan/UBSan batch (768 opcode/version probes, 510 truncation probes, 60,000 paired random trials, state invariant with observations). Zero-filled opcode probe admits 50/84/84; counts depend on operands and include structural-only effects, not full execution coverage.

Private batch: 54/60 LFL files including index, 780 global object slots each; 169/148 bounded global scripts. MM disk1 53.LFL invalid chain; readable disk2 copy used. One MM script and seven MM sound entries have invalid size/location under this parser. No repair or inferred substitute. Static sequential prefixes for all scripts: MM 106 -> 590 instructions, 434 -> 3565 bytes; Zak 144 -> 543 instructions, 600 -> 3083 bytes. These are linear decode prefixes, not a CFG, full-script coverage or source-engine trace comparison. Script 1 MM: 6 -> 119 decoded instructions; portable execution 6 -> 7 retired, now blocked at pc 28 cutscene. Zak: 1 -> 24 decoded instructions; execution 1 -> 11 retired, blocked at pc 46 resource operation. All independent script probes initialize synthetic zero-state and stop at first yield, block, fault, termination or cap; no claim of original boot state or arbitrary standalone script semantics.

Native build preflight of supplied prepared AGI QEMU 10.0.13 tree failed at configure on missing glib-2.0 development metadata. GLib/pixman shared runtime libraries exist but no headers/pkg-config .pc files, no DNS for package download. The SCUMM QEMU overlay has not been built or launched. Next: obtain offline dev dependencies, adapt registration to exact AGI companion base or clean source; compile target, compare QMP traces with portable core, add scheduler, resource effects, cutscene state, room/object scene geometry and true reference differential tests.

Encoding fact references (no implementation copied): ScummVM v2.9.0 engines/scumm/resource_v2.cpp, resource.cpp, scumm.cpp, script_v2.cpp, script_v5.cpp; ScummVM 2.2.0+dfsg1-4 script_v0.cpp; ScummVM Tools v2.9.0 descumm.cpp; detection table MD5 values from scummvm/scummvm master (pin exact commit before release). All game data and extracted payloads excluded from repository.
