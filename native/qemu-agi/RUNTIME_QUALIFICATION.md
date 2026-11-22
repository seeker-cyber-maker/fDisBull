# Native runtime resource qualification

`qualify_runtime_resources.py` runs caller-supplied runtime packages through
the actual QEMU AGI target. It checks independently supplied state expectations
and saved visual/priority planes, then compares the entire native architectural
state across observation settings. It does not decode or execute LOGIC in
Python.

The controller uses five fresh processes for each case:

| Observation mask | Capacity | Purpose |
| --- | --- | --- |
| 0 | 0 | Both channels disabled |
| 1 | 4096 | DISASM only |
| 2 | 4096 | SCENE only |
| 3 | 4096 | Both channels |
| 3 | 1 | Deliberate bounded diagnostic loss |

Every run must produce identical complete `guest` JSON, including the native
state fingerprint, and identical visual/priority planes. Reading the scene and
event journal must leave the guest and observation counters unchanged. Disabled
observation must remain empty. The full recorder must have no dropped events;
the capacity-one run records its loss explicitly.

## Inputs

Prepare packages with `runtime_pack.py`. Package identity is the SHA-256 of
the exact JSON bytes; resource code and data hashes remain separate. Initial
variables and flags belong in the explicit qualification case, not in the
resource package.

A UTF-8 JSON manifest has exactly two top-level fields:

| Field | Value |
| --- | --- |
| `schema` | `fdisbull-agi-runtime-qualification-1` |
| `cases` | One to 32 case records |

Each case has these fields:

| Field | Meaning |
| --- | --- |
| `name` | Unique lowercase letters/digits/hyphens, at most 80 characters |
| `scope` | Explicit description of original execution, an authored resource probe, or another bounded qualification |
| `package` | `{ "path": "package.json", "sha256": "<exact lowercase SHA-256>" }` |
| `seed` | `{}` for native defaults, or explicit `variables` and/or `flags` maps keyed by decimal index |
| `step_budget` | One native run of one to 100,000 instructions |
| `expected_fields` | Nonempty list of `{ "path": ["guest", "status"], "value": "return" }` records; array indices are JSON integers |
| `expected_planes` | Zero, one or both `visual`/`priority` entries, each with an exact file path and SHA-256 |

File paths resolve relative to the input manifest. Every supplied expected
plane must contain exactly 26,880 bytes: one four-bit palette/priority index per
pixel on the 160 by 168 canvas. The controller rejects changed package or oracle
bytes before launching QEMU. It checks the admitted binary hash before and after
the batch.

Run the controller with an immutable executable and a new output directory:

```sh
python native/qemu-agi/qualify_runtime_resources.py \
  --manifest /private/qualification/cases.json \
  --binary /private/qualification/qemu-system-agi \
  --binary-sha256 <exact-binary-sha256> \
  --output /private/qualification/attempt-01
```

The output contains exact input manifest/package copies, launch commands,
explicit initial-context records, complete stopped state, events, scene JSON,
binary planes, comparisons and a cumulative receipt. A failed check produces a
nonzero exit status; an exception is retained in the receipt. Existing attempt
directories are rejected. Processes are owned and reaped by `QemuAGIRuntime`.

Original game packages, messages, state and images must remain in an authorized
private directory outside the source repository. The controller and authored
tests can be committed; private game bytes cannot.

## Interpreting the result

A resource fault is an execution boundary. It can be the expected outcome of a
deliberately incomplete resource bank, but it does not qualify subsequent
instructions. A complete-bank packaging failure must be reported with its
malformed resources; creating an explicitly selected resource subset is a
separate operation with a narrower scope. Do not silently omit failed entries.

An original room entry can depend on global initialization from LOGIC 0. If ego
has no bound VIEW when the original program draws it, retain that fault. A
separate original LOGIC 0 run may establish the context naturally. Never replace
a missing original callee, change the room's code, or supply invented ego state
and describe the result as original execution.

An authored program can independently exercise verified original PICTURE/VIEW
resources at explicit positions, priorities and poses. This is useful for
comparing a native compositor with an earlier selected-layer preview. Its scope
must state that it is an authored draw probe. A prior design preview may omit
actors or fill unspecified poses and therefore cannot serve as the oracle for a
whole original room without qualification.

The controller performs a single native run and makes no host-device choices or
clock/tick calls. Interactive startup progression requires a separate explicit
command sequence. Keep system-clock advancement, world updates and sound output
timing distinct, and use the runtime's current cycle contract when collecting
that evidence. An observation-neutral run or a matching scene does not alone
establish original-engine timing, complete gameplay or device fidelity.
