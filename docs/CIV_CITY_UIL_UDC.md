# Civ city UIL and executable UDC slice

Status: **partial, source-linked fixture with a natively executed macOS arm64 module;
not a whole-screen or whole-game parity claim**.

This document records the first concrete UIL/UDC realization of the city-screen
blueprint. It is intentionally narrower than `city_process()` and preserves the
edition conflict and source/runtime boundaries.

## UIL scene representation

The committed scene is:

- `examples/civ/civ_city_scene.json`
- `examples/civ/civ_city_scene.provenance.json`

It uses `fdisbull-il-scene-1` with a shared typed state projection:

| State | Type | Meaning | Boundary |
|---|---|---|---|
| `$view_mode` | `u8` | `INFO`, `HAPPY`, `MAP`, `VIEW` tab selection | Source-key/tab mapping only |
| `$city_size` | `i16` | population field | Declared state; no population transition |
| `$food_box` | `i16` | stored food | Declared state; no food pass |
| `$shield_box` | `i16` | signed stored production | Declared state; bounded UDC step below |
| `$production` | `i16` | unit/improvement selection | Catalog lookup not modeled |
| `$city_status` | `u8` | status bits; bit 0 is disorder | Bit 0 is exposed as a conditional object |
| `$city_owner` | `u8` | civilization slot | Declared state; no diplomacy/ownership effects |
| `$auto_build` | `bool` | automatic production flag | Display state only |

The scene inventory covers the city title, four tabs, food and production
storage, resources, the 21-tile radius, routes, buildings/wonders, units,
production controls, disorder status, rename and exit controls. Tab programs
are pure IL state/text transitions, so `ILSceneBackend` can observe and change
the selected tab without pretending to render VGA pixels.

`partial: true` is REQUIRED. The scene does not load original font/icon/map
assets, perform text entry, dispatch the production catalog, close a host
session, or implement the complete city turn pass. Objects without a binding
are visible inventory only, not silently executable controls.

## Bounded UDC module

`examples/civ/civ_city_uil.py` builds the module and a new Linux x86-64 shell.
The source input MUST be the exact generated unpacked root:

```text
SHA-256 aa63aa396cfa62519b131ee6c0a231bed02bb9aefce26b955608b5815a569e57
```

Example, with private inputs outside Git:

```bash
PYTHONPATH=src python examples/civ/civ_city_uil.py \
  build/civ-analysis/CIV_UNP.EXE \
  /tmp/fdisbull-civ-city-udc \
  --project /tmp/fdisbull-civ-city-udc.fdb \
  --civd-citymgt /path/to/civd/src/CITYMGT.C \
  --civd-civ-h /path/to/civd/src/CIV.H \
  --civd-production-doc /path/to/civd/book/src/city/production.md
```

The builder:

1. Creates a private fDisBull MZ project from the unchanged unpacked bytes.
2. Captures 64 bytes at translated runtime address `1D12:0045`, the Civ64
   `R:0D12:0045` city-route seed under the MZ load segment `0x1000`.
3. Registers the exact typed contract
   `civ.city.production.sanitized-shield-step`.
4. Selects a shared-IL implementation and composes
   `fdisbull-module-uil-1` around the retained snippet identity.
5. Emits a new `fdisbull-native-shell-build-1` Linux ELF under a new output
   directory, with a selection capsule and hash-bound qualification receipt.

The modeled transition is deliberately preconditioned:

```text
require sanitized == true
if disorder:
    shield_box = 0
else:
    shield_box += shield_delta   # signed i16 semantics
```

`sanitized == true` means the caller has already applied the recovered source
boundary: reset `shield_box` to zero when it is below zero or above 999 before
production. The module does **not** reimplement that comparison because the
current shared UIL condition profile has no ordered comparisons. This avoids
turning the civd signed-storage/reset mismatch into a reachable-bug claim.

The module is therefore an executable bounded state transition, not a compiled
replacement for `city_process()`, the DOS VGA provider, or the Civ64 Windows
implementation.

## Native targets

`--target linux-x64` (default) emits a static ELF64 shell and reports
`native_execution: false` until a Linux runtime is supplied; on macOS that ELF
is a cross-target artifact and is not host-runnable without an external runtime.

`--target macos-arm64` uses the sweding profile
`macos-arm64-c-plan-libsystem-1`: the same UIL and typed state effects are
realized as generator-owned C compiled for `arm64-apple-macos11` and linked
against libSystem. Declared differences:

- machinery changes from fixed x86-64 slot lowering to C plus dyld/libSystem;
- observation is one JSON frame on stdout (no `capture_state` fd);
- the builder still records `native_execution: false`; execution is separate
  evidence.

Observed on this host for the default state:

```text
$ file /tmp/civ-city-macos-20261030/program
Mach-O 64-bit executable arm64
$ /tmp/civ-city-macos-20261030/program
{"format":"fdisbull-macos-observation-1","status":0,"value":0,
 "state":{"$shield_box":3,"$shield_delta":3,"$disorder":0,"$sanitized":1}}
```

That is the disorder-false branch adding the supplied contribution to a
sanitized box.

## Differential boundary sweep

`examples/civ/civ_city_udc_diff.py` builds one module per boundary state, runs
the emitted binary, and compares the observation frame with `execute_il` on the
primitive program. Every listed state agrees:

| case | initial state | interpreter | native arm64 |
|---|---|---|---|
| default | `box 0, delta 3` | `box 3` | `box 3` |
| wrap-high | `box 32767, delta 1` | `box -32768` | `box -32768` |
| wrap-low | `box -32768, delta -1` | `box 32767` | `box 32767` |
| negative-box | `box -5, delta 3` | `box -2` | `box -2` |
| disorder-zeroes | `box 7, delta 5, disorder` | `box 0` | `box 0` |
| unsanitized-refusal | `box 4, delta 2, sanitized false` | `status: refused` | exit 1, no frame |

`verdict: match` over the six states, with per-case artifact hashes in the
sweep receipt. Refusal is observable only as a nonzero exit with no observation
frame, because the program publishes state only on a committed transition.

Scope: this proves interpreter/native agreement for the tested states. It does
not prove that the UIL model matches the DOS routine, which the static trace
covers separately.

## BUY commit module

A second bounded module, `examples/civ/civ_city_buy_udc.py`, models the buy
commit recovered at `R:0D12:4DD6`: shields increase by the remaining-shield
cost, gold decreases by twice that cost, all in 16-bit wraparound. The cost
derivation (item table times an unresolved multiplier, minus shield stock)
stays outside the module; the caller supplies the computed remaining cost.

The excluded items are named in the contract evidence: the cost tables, the
`[bp-0x4a]` multiplier, the `> 2000` surcharge, and the cleared status flag
(`and byte [bx+0x70f2], 0xef`).

Native macOS arm64 with `shield_box 5, treasury 100, remaining 10`:

```text
{"format":"fdisbull-macos-observation-1","status":0,"value":0,
 "state":{"$shield_box":15,"$treasury":80,"$remaining":10}}
```

| case | initial | interpreter | native arm64 |
|---|---|---|---|
| default | `shields 5, gold 100, remaining 10` | `shields 15, gold 80` | `shields 15, gold 80` |
| wrap-treasury | `shields 0, gold 5, remaining 10` | `shields 10, gold 65521` | `shields 10, gold 65521` |
| negative-remaining | `shields 2, gold 20, remaining -3` | `shields -1, gold 26` | `shields -1, gold 26` |
| zero-remaining | `shields 7, gold 40, remaining 0` | unchanged | unchanged |

`examples/civ/civ_city_udc_diff.py --module all` runs both sweeps and reports a
single verdict.

## Evidence and conflicts

The source-linked receipt keeps:

- Civd `CITYMGT.C`, `CIV.H` and production documentation hashes and exact
  commit `d9214fcd36aa6003d28aae60c3974b665f752280`.
- Civ64 analysis commit
  `4e46572d727544722d90c24dc2ce51a9c6d22f15` and the relative-to-runtime
  address translation.
- The pinned packed/unpacked executable identities.

The Civd label `474.05` and Civ64 label `475.05` still refer to the same packed
hash and remain `CIV-EDITION-001`; this slice does not resolve that conflict.

## Verification boundary

Fresh checks for this slice:

- `tests/test_civ_city_uil.py`: scene tab transitions, disorder/reset refusal,
  and pinned-source rejection.
- The builder was run against the exact unpacked root and produced a 32,768-byte
  ELF64 x86-64 executable with mode `0700`.
- fDisBull's shared-IL qualification status is
  `equivalent_under_contract`; that status qualifies the supplied model and
  selected layer, not source recovery or native runtime behavior.

Next required probe: trace a verified DOS caller/overlay path through the city
screen and compare one controlled state/display transition before promoting
any scene object from inventory to an executable game action.
