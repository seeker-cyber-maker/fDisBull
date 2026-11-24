# Early SCUMM native QEMU target

Initial **unqualified authored-script pilot**, not a complete game engine. One isolated target, scumm-softmmu, explicitly selects version 0/1/2. No change to DOS/QEMU defaults or AGI source.

Build against a separate clean QEMU 10.0.13 tree using the pinned upstream registration hashes inherited from native/qemu-agi. Do not combine overlays until architecture registration is reviewed.

```sh
cc -std=c11 -Wall -Wextra -Werror -pedantic native/qemu-scumm/overlay/target/scumm/early.c native/qemu-scumm/test_early.c -o /tmp/scumm-core-test
/tmp/scumm-core-test
python native/qemu-scumm/apply_overlay.py /path/to/qemu-10.0.13 --check
python native/qemu-scumm/apply_overlay.py /path/to/qemu-10.0.13
# separate build directory
/path/to/qemu-10.0.13/configure --target-list=scumm-softmmu --without-default-features --enable-system --enable-tcg --enable-pixman --disable-user --disable-tools --disable-docs --disable-guest-agent --disable-containers --disable-download --disable-install-blobs --disable-debug-info --disable-qom-cast-debug --disable-rust --audio-drv-list=
ninja -j2 qemu-system-scumm
qemu-system-scumm -M scumm-test,version=1 -accel tcg,thread=single -kernel /private/raw-script.bin -S -display none -serial none -monitor none -nodefaults -no-user-config -qmp stdio
```

Stopped QMP: query-cpus-fast gives CPU QOM path. Set scumm-observation-mask (DISASM=1, SCENE=2), scumm-observation-capacity (0..4096), scumm-step-budget, scumm-decode-pc. Read scumm-state-json, scumm-decode-json (64 sequential records), scumm-events-json. Restart with scumm-restart=true. Yield pauses the single script; next cont resumes, not yet multi-slot scheduling. Return/fault sticky. Status: 0 ready, 1 running, 2 budget, 3 return, 4 yield, 5 fault. Operand tuples kind/value/width: 0 immediate, 1 variable, 2 destination. Branch taken on false condition; unknown/truncated decode stops static listing. Event channel 0=retire, 1=changed authored actor-placement model, not confirmed original scene. Source SHA and raw bytes identify exact script. Bounded journal drops new records at capacity.

Profile: raw scripts, stop, version-specific yield, move, add/sub, inc/dec, comparisons and jump, putActor variants. v0 immediate word operands byte-sized, branch displacement signed LE16 in all versions; v0 yield 0x10 versus v1/v2 0x80. v1/v2 byte assignment and read-indirection for variables 14..16. 256 synthetic 16-bit variables, 32 authored actor slots (0 invalid), script-unit placement coordinates. 16-bit wrapping is a declared pilot model, original-version width, overflow, actor and system-variable side effects not qualified. Reject unadmitted aliases. No resource loading, object semantics, verb dispatch, timers, scheduler, UI, rendering or save migration. Single bounded semantic helper/TB; not opcode-specific TCG lowering. Native build and launch unverified.

Next: qualify opcode catalog and lengths by version; add script slots and resource banks; scene/object/verb extraction; pending effect contracts; independent original-game comparison; snapshot and UIL mapping. Development/held-out C64 original MM, version-verified DOS MM and Zak. No unimplemented opcode may retire. Preserve separate product policies.
