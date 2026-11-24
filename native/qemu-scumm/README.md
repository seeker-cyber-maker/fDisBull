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
python3 native/qemu-scumm/test_observation_native.py --qemu /private/scumm-build/qemu-system-scumm --output /private/scumm-observations.json
python3 native/qemu-scumm/test_verbs_native.py --qemu /private/scumm-build/qemu-system-scumm --output /private/scumm-verbs.json
python3 -m unittest discover -s native/qemu-scumm -p test_processor_scene.py
python3 -m unittest discover -s native/qemu-scumm -p test_navigation.py
/private/scumm-build/qemu-system-scumm -M scumm-test,version=1 -accel tcg,thread=single -kernel /private/raw-script.bin -S -display none -serial none -monitor none -nodefaults -no-user-config -qmp stdio
```

## Stopped QMP controls

`query-cpus-fast` supplies the CPU QOM path. Controls require one stopped TCG
CPU. Set `scumm-observation-mask` (off=0, DISASM=1, SCENE=2, both=3),
`scumm-observation-capacity` (0..4096), and `scumm-step-budget` (1..1 billion).
The independent static listing selectors are `scumm-decode-pc` and
`scumm-decode-limit` (1..64). Read `scumm-state-json`, `scumm-decode-json`,
`scumm-events-json`, and `scumm-scene-json` for a coherent snapshot of the
supported scene model. `scumm-observation-clear=true` clears the journal and
advances its epoch without changing guest state or last-run accounting.
`scumm-restart=true` clears execution state and the journal while retaining
the configured controls and static listing selectors.
QMP `system_reset` now reaches the CPU's registered reset hook and has the same
execution/journal reset behavior.

For the optional source-bound Amiga v2 resource bank, cutscene entry, cursor
and authored verb state, see [the isolated v2 runtime](V2_RUNTIME.md). It adds a startup-only
`resource-manifest` machine option and a stopped `scumm-runtime-json` getter.
The profile explicitly declares one active global script and zero initial
controls; it does not claim authentic game boot state.

Status values are **0 ready, 1 running, 2 budget, 3 return, 4 yield, 5 fault,
6 blocked effect**. A subsequent `cont` resumes after a budget stop or yield.
Return, fault and blocked states remain stopped until restart; an unimplemented
effect is neither committed nor retired. Yield currently pauses one script;
there is no script scheduler.

Operand tuples contain kind/value/width: kind 0 is immediate, 1 variable,
2 destination. Conditional branches use the relative target when the condition
is false. Unknown or truncated instructions stop static listing. Event channel
0 records retirement and historical operand values; channel 1 records committed
actor, default-talk-color, resource residency/lock, cursor/cutscene control,
and authored verb changes. Full actor deltas include palette membership and exact source-bound
name bytes. These model changes do not establish a rendered game scene.
Source SHA-256, catalog identity and retained instruction bytes identify the
execution inputs. The bounded journal drops new records when full and reports
eligible/stored/dropped counts per channel, including at capacity 0.

[Observation modes](OBSERVATION_MODES.md) specifies the AGI-aligned control,
epoch, generation, generated-code and record contracts. The
[scene consumer](SCENE_CONSUMER.md) validates native records against exact
code bytes and produces a stateless packet without claiming complete history
or inventing rendered output.

[Room navigation](NAVIGATION.md) adds read-only inspection of v2 walkboxes and
their stored next-hop matrix. It creates deterministic, source/state-bound
movement proposals and rechecks them against the complete captured packet.
Caller-selected initial or overridden flags remain explicit assumptions.
This host capability does not execute a walk command or initialize a room.

## Verified scope

The clean QEMU 10.0.13 target built and ran on Debian 13 x86_64 with GCC 14.2,
GLib 2.84.4, Pixman 0.44.0 and Ninja 1.12.1. All **22 authored native tests**
passed: versions 0/1/2, scalar execution, budget/yield resume, restart, sticky
terminal states, observation invariance, capacity-zero journals, decode/control
bounds, global system reset, 513-byte instructions and 4 KiB page crossings. The page-crossing tests
also require QEMU `in_asm` to retrieve every translated byte. They failed before
the translator registered its instruction reads through `translator_ldub` and
passed after that correction.

The additional v2 runtime suite passes source-binding/rejection tests, effect
budget accounting, full runtime observation invariance and both reset paths.
Its 22 rejected startups require clean validation exits. Portable runtime tests
have 5,775 assertions; 11 intake tests use authored OFS/resource inputs. Review
also found and fixed missing CPU registration in the system reset graph, and
the harness now requires normal child teardown for a successful test.

All **16 additional native observation case groups** pass. They cover complete
actor/global/resource/control facts, historical operands in all three versions,
all four masks at capacities 0/1/64, capacity growth after loss, cached mode
switches, clear/reset generations and epochs, query purity, blocked effects,
and native scene-packet consumption. Eight generated-TCG configurations verify
the optional observer calls and the mandatory semantic helper separately.
The retained earlier binary fails the same suite because it lacks the new
public observation contract. This is a before/after contract check, not a claim
of sixteen distinct prior execution defects.

The **six native verb groups** pass: create/delete/mode semantics, slot lookup
and variable indirection, escaped text, 12 mask/capacity combinations, atomic
failures, raw-profile blocking, clear/reset, query neutrality and a maximum
514-byte instruction crossing a code page. The retained earlier binary fails
this new verb contract. Both v1 and v2 canonical escaped-name decoding were
also checked independently; native effects remain restricted to v2.

The scene consumer passes **20 authored groups**, including new verb facts
without inventing rendering. The navigation layer passes **36 authored tests**
for room bounds, stored/signed next hops, source and capture consistency,
integer geometry/ties, flags, cycles, budgets, stale/tampered plans and purity.
These standard-library runners require no third-party test dependency. The
environment's `python -m pytest` is unavailable because pytest is not installed.

Portable original/extended fixtures and the 60,000-pair randomized batch passed
with AddressSanitizer and UndefinedBehaviorSanitizer. LeakSanitizer was disabled
with `ASAN_OPTIONS=detect_leaks=0` after LeakSanitizer reported a ptrace
incompatibility; leak checking remains unverified.

Optional TCG plugins are disabled in this build. Upstream QEMU 10.0.13 stores
plugin instruction lengths in an 8-bit field, which cannot represent every
admitted SCUMM instruction. Plugin compatibility is not qualified.

## Processor model and remaining work

The default core executes bounded scalar arithmetic, comparisons, branches, range
assignments, actor placement and synthetic actor metadata changes. It also
decodes selected resource, script, room, cutscene, verb, print and animation
intents, stopping before their unimplemented effects. Version 0 immediate word
operands are byte-sized; relative branches use signed LE16 in all versions.
Yield is `0x10` in v0 and `0x80` in v1/v2. The model has 256 synthetic 16-bit
variables and 32 actor slots (slot 0 is invalid for placement), with v1/v2 read
indirection for variables 14..16. Sixteen-bit wrapping and actor/system-variable
behavior remain a pilot model, not an independently qualified original engine.

Each TB invokes one bounded semantic helper; enabled observation variants can
also invoke a separate observer. Mask zero generates no observer call and
passes no diagnostic capture buffer to the semantic helper. SCENE-only scalar
instructions likewise need no observer. The mode is part of the TB key;
changing it selects a matching cached variant without a blanket flush.
No opcode-specific TCG lowering is claimed. The opt-in v2 profile adds verified resource availability, logical
residency/locks, cutscene entry, cursor/control state and 100 authored verb slots.
Script scheduling, room transitions, object semantics, native actor walking,
verb dispatch, timers, rendered UI, audio
and save migration remain unimplemented. Original
game equivalence and complete gameplay remain unverified, and supplied real
assets cover only Amiga v2. Local results do not establish hosted CI or release
qualification. Next work is room/object lifecycle and scheduling, actor motion
and explicit ticks, cutscene exit, and independent original-engine comparisons. Private target
results are retained separately from this authored-source contribution.
