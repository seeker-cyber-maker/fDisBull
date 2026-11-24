# Early SCUMM native QEMU target

Bounded native processor pilot with passing authored QMP tests. The isolated
`scumm-softmmu` target explicitly selects version 0, 1 or 2. It does not yet
provide a complete game engine or change DOS/QEMU backend defaults.

## Build and check

Use a private QEMU **10.0.13** source tree and a separate build directory.
`apply_overlay.py` checks six pinned registration files before writing. It
accepts the exact clean upstream registration or the exact prepared AGI
registration, preserves AGI entries, and supports reapplying its own recorded
overlay. Unrecognized changes are refused. The complete native build below
has been tested on the **clean upstream base**; an AGI-plus-SCUMM build has
not been qualified.

From the fDisBull checkout:

```sh
cc -std=c11 -Wall -Wextra -Werror -pedantic native/qemu-scumm/overlay/target/scumm/early.c native/qemu-scumm/test_early.c -o /tmp/scumm-core-test
/tmp/scumm-core-test
python3 native/qemu-scumm/apply_overlay.py /path/to/qemu-10.0.13 --check
python3 native/qemu-scumm/apply_overlay.py /path/to/qemu-10.0.13
```

In a new build directory outside the checkout:

```sh
/path/to/qemu-10.0.13/configure --target-list=scumm-softmmu --without-default-features --enable-system --enable-tcg --enable-pixman --disable-user --disable-tools --disable-docs --disable-guest-agent --disable-containers --disable-download --disable-install-blobs --disable-debug-info --disable-qom-cast-debug --disable-rust --audio-drv-list=
ninja -j2 qemu-system-scumm
```

Run the native harness from the checkout, keeping its output outside the repo:

```sh
python3 native/qemu-scumm/test_native.py --qemu /private/scumm-build/qemu-system-scumm --output /private/scumm-native.json
/private/scumm-build/qemu-system-scumm -M scumm-test,version=1 -accel tcg,thread=single -kernel /private/raw-script.bin -S -display none -serial none -monitor none -nodefaults -no-user-config -qmp stdio
```

## Stopped QMP controls

`query-cpus-fast` supplies the CPU QOM path. Controls require one stopped TCG
CPU. Set `scumm-observation-mask` (DISASM=1, SCENE=2),
`scumm-observation-capacity` (0..4096), `scumm-step-budget`, and
`scumm-decode-pc`. Read `scumm-state-json`, `scumm-decode-json` (up to 64
sequential records), and `scumm-events-json`. `scumm-restart=true` clears
execution state and the event journal while retaining the configured controls.

Status values are **0 ready, 1 running, 2 budget, 3 return, 4 yield, 5 fault,
6 blocked effect**. A subsequent `cont` resumes after a budget stop or yield.
Return, fault and blocked states remain stopped until restart; an unimplemented
effect is neither committed nor retired. Yield currently pauses one script;
there is no script scheduler.

Operand tuples contain kind/value/width: kind 0 is immediate, 1 variable,
2 destination. Conditional branches use the relative target when the condition
is false. Unknown or truncated instructions stop static listing. Event channel
0 records retirement; channel 1 records changes to the bounded actor model.
These model changes do not establish an original game scene. Source SHA-256 and
retained instruction bytes identify the script. The bounded journal drops new
records when full and reports eligible/dropped counts, including at capacity 0.

## Verified scope

The clean QEMU 10.0.13 target built and ran on Debian 13 x86_64 with GCC 14.2,
GLib 2.84.4, Pixman 0.44.0 and Ninja 1.12.1. All **19 authored native tests**
passed: versions 0/1/2, scalar execution, budget/yield resume, restart, sticky
terminal states, observation invariance, capacity-zero journals, decode/control
bounds, 513-byte instructions and 4 KiB page crossings. The page-crossing tests
also require QEMU `in_asm` to retrieve every translated byte. They failed before
the translator registered its instruction reads through `translator_ldub` and
passed after that correction.

Portable original/extended fixtures and the 60,000-pair randomized batch passed
with AddressSanitizer and UndefinedBehaviorSanitizer. LeakSanitizer was disabled
with `ASAN_OPTIONS=detect_leaks=0` after LeakSanitizer reported a ptrace
incompatibility; leak checking remains unverified.

All **317 private Amiga v2 script probes** (169 Maniac Mansion, 148 Zak McKracken)
matched the portable core's summaries and counters with native observations
enabled. Each script's full exposed architectural state also matched between
native observation masks 0 and 3. All 634 native processes exited and were
reaped normally, with no timeouts. These are isolated, zero-initialized script
runs through a shared core, demonstrating integration rather than independent
language validation or original game boot behavior. See
[Amiga v2 intake](AMIGA_V2_INTAKE.md) for source identity, stop results and limits.

Optional TCG plugins are disabled in this build. Upstream QEMU 10.0.13 stores
plugin instruction lengths in an 8-bit field, which cannot represent every
admitted SCUMM instruction. Plugin compatibility is not qualified.

## Processor model and remaining work

The core executes bounded scalar arithmetic, comparisons, branches, range
assignments, actor placement and synthetic actor metadata changes. It also
decodes selected resource, script, room, cutscene, verb, print and animation
intents, stopping before their unimplemented effects. Version 0 immediate word
operands are byte-sized; relative branches use signed LE16 in all versions.
Yield is `0x10` in v0 and `0x80` in v1/v2. The model has 256 synthetic 16-bit
variables and 32 actor slots (slot 0 is invalid for placement), with v1/v2 read
indirection for variables 14..16. Sixteen-bit wrapping and actor/system-variable
behavior remain a pilot model, not an independently qualified original engine.

Each TB invokes one bounded semantic helper; no opcode-specific TCG lowering is
claimed. Resource loading, script scheduling, object semantics, verb dispatch,
timers, UI, rendering, audio and save migration remain unimplemented. Original
game equivalence and complete gameplay remain unverified, and supplied real
assets cover only Amiga v2. Local results do not establish hosted CI or release
qualification. Next work is resource/effect completion, scheduler and cutscene
state, room/object geometry, and independent original-engine comparisons.
