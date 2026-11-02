# Source-preserved controller recipe

The two Python files in this directory are **path-parameterized derivatives**
of the private controllers used for the fresh macOS comparison. They preserve
the measured loop, observation, retry, statistics, timeout and cleanup bodies.
They are not the measured files, and these derivatives have not executed a guest.
The separate comparison report owns measurements and their scope.

No game bytes, firmware, JAR, prepared Anchor, native state, private runtime
receipt, private host path or host registry is included here. All actual runtime
outputs must remain in a new authorized private external directory outside Git.
The input movie and authoring source come from the adjacent research import;
the caller must separately provide compatible private media and runtimes.

## Exact source identities and transformations

| Controller | Measured private original SHA-256 | Public derivative SHA-256 |
| --- | --- | --- |
| `fdisbull-loop-benchmark.py` | `13b00f0890546f4d1937f4ee482635f3b19d778ca10575d32162664bd7bbc4d8` | `d0569ee2d8bcaca4e0f97cc56f8ba1f48687192d57d86963e55dca31b3b0a933` |
| `jpcrr-loop-benchmark.py` | `a68ea0740ae57ea931a411207414a50fce87f0e9af284d023137c840f1868e5d` | `02f81e2c2134244f5fa9bb2c5076b68bdbd4a2771be6e2e6d88b227f115ba26b` |

The private originals were read and hashed, never modified. The changes are:

- fDisBull: replace fixed workspace, source-checkout, preparation-receipt,
  observer-helper and storage-admission-helper paths with required CLI inputs.
  Retain the exact MR30 source commit and native backend hash checks. Bind the
  observer helper to its measured SHA-256. Add a default read-only planning exit;
  native execution now requires `--execute`.
- JPC-RR: replace fixed runtime/tools roots and executable defaults with required
  Java, JAR, library, classes, movie, author-source, runtime-root, temporary-root
  and storage-admission paths. The temporary directory is explicit and remains
  under the private runtime root. Preserve stock JAR and media-identity guards,
  the default planning mode, execution opt-in, loop timing and native reaping.
- Reject Git ancestry for the caller-selected JPC-RR private runtime root.
  Neither derivative changes the 20 GB minimum storage reserve, allocation
  ceilings, finite deadlines or guest-protocol algorithms.

The fDisBull observer/helper is an **additional private dependency**, not a file
from the imported JPC-RR ZIP and not distributed by this recipe. Its measured
SHA-256 is
`f4c56cd166dfb4c4ec6afc5f41ef795d49ac87e7bdfa806017e56ea1282f9c29`.
It supplies the source-bound KQ1 RAM observer, safety predicates and public-call/
native-RPC meter. The derivative refuses another helper rather than silently
substituting a different observer. Consequently these sources preserve an
auditable protocol; they do **not** constitute a standalone reproduction kit.
Exact runtime reproduction needs that helper, the matching private preparation,
and the matching native backend. Those dependencies remain explicit unknowns
for a reader who does not possess them.

## Dependencies and planning

Use Python 3.11 or later with the dependencies required by the selected fDisBull
checkout. Use `python -B` to avoid writing bytecode into frozen input directories.
Run `--help` without supplying runtime inputs to inspect either CLI.

For fDisBull, the source checkout must be at
`865542a26b5406b2bc81e0e3bc7c542a287eec25`. The preparation receipt must bind native
backend SHA-256
`a32b8285ea412413e9d60bf8b1c8735b9ee082b683a46dcba3fce65d47c47474`.
The controller also verifies the origins and committed hashes of the modules it
loads. Its preparation must be the matching legacy-embedded FDB with an empty
WAL; it creates and modifies a distinct byte-identical copy, never the original.

Replace these illustrative paths with caller-owned inputs. The existing external
runtime root and its temporary directory must already exist. Without `--execute`,
the following commands validate their available inputs and print a plan. They
create no benchmark output directory and launch no emulator or JVM:

```sh
python -B fdisbull-loop-benchmark.py \
  --runtime-root /path/to/private-external-runtime \
  --source-root /path/to/frozen-fdisbull-checkout \
  --start /path/to/private-preparation-receipt.json \
  --helper /path/to/matching-private-kq1-helper.py \
  --storage-admit /path/to/storage_admit.py \
  --output /path/to/private-external-runtime/new-fdisbull-run \
  --samples 32 --warmups 4 --wall-seconds 300 \
  --max-new-bytes 536870912 --destination-reserve-bytes 20000000000

python -B jpcrr-loop-benchmark.py \
  --run-root /path/to/private-external-runtime \
  --temp-root /path/to/private-external-runtime/tmp \
  --java /path/to/java \
  --jar /path/to/jpcrr-r11.2.jar \
  --library /path/to/private-disklibrary \
  --classes /path/to/matching-author-classes \
  --author-source ../tools/authoring/src/kq1tas/HeadlessAuthor.java \
  --movie ../movies/KQ1-Robb-Route-63-complete.jrsr \
  --storage-admit /path/to/storage_admit.py \
  --out /path/to/private-external-runtime/new-jpcrr-run \
  --start-ns 4009098300 --scan-code 76 --hold-ns 1000000 \
  --warmup 4 --samples 32 --observe-bytes 65536 \
  --depths 1,3,5 --trials 3 \
  --max-new-bytes 67108864 --destination-reserve-bytes 20000000000
```

The JPC-RR source/class pair must provide the `HeadlessAuthor` protocol commands
used by the controller. The caller builds it separately using the documented
authoring workflow and the unchanged matching JAR. Building is a separate
storage-admitted phase; these scripts do not install or build dependencies.

Add `--execute` only for an authorized serialized guest run. The 20 GB argument
expresses the bounded-work reserve used for this comparison, not a general
exception to another caller's storage policy. Use a higher reserve when required.
Honor a nonzero storage-admission result; do not lower the floor or redirect
output to another storage pool to bypass it. Sibling APFS volume free-space
figures must not be summed. The admission check is not a live quota.

For the JPC-RR external dense-history variant, choose another **new** output
directory and add `--checkpoint-every-sample --capture-every-sample`. This retains
full native states through the external Python controller; it is not built-in
delta rewind. Keep the admitted allocation ceiling and finite sample bounds.

## Source-bound protocol

The fDisBull controller runs the following finite procedure in one owned session:

1. Verify source/backend/preparation identities, admit storage and copy the FDB.
2. Load the existing seed Anchor and verify original KQ1 code/RAM witnesses.
3. For each mode, reload that Anchor and advance the same alignment frame.
4. Run four warmups followed by 32 timed loops. Each loop sends keypad-5 make
   then break through **two ordered paused calls**, advances **one completed
   renderer frame followed by a safe CPU fetch**, then observes exposed CPU
   registers, one atomic 65,536-byte DS span and released-key ownership. Native
   frame info comes from the verified advance receipt.
5. In manual dense mode, capture a full Anchor and PNG after each core loop.
   Report that cost separately and include it in total loop latency. Automatic
   timeline capture is intrinsically part of its frame-advance operation;
   combined mode also pins the initial point.
6. Return to the preceding boundary and repeat the same complete input pair.
   Compare CPU and full observed DS with the recorded boundary and endpoint.
   With recording off, the corresponding return is a seed load plus known-plan
   replay, explicitly labeled as a different navigation cost.
7. Search at most 64 frames for a natural nonzero RNG transition. If observed,
   verify a full rewind restores the earlier DS/CPU, replay the transition, and
   preserve only the two declared current RNG bytes while returning to the
   earlier point. Verify the other 65,534 DS bytes, refusal of unapproved mixed-
   state execution, and complete Anchor recovery. If no transition appears,
   report `not_observed`; passing latency loops do not qualify preservation.
8. Reap the owned process and verify the original FDB, preparation receipt,
   native backend and source game-file identities remain unchanged.

The JPC-RR controller similarly loads the selected movie, advances to the declared
ready prefix, truncates future input, warms the same JVM and repeats a make/break,
native-frame-wait and paused observation loop. It explicitly observes dispatch
of release, allowing bounded extra native frames. Its observation consists of
`info`, exposed registers and the declared conventional-RAM span. Separate retry
trials save/load native states and compare their observed projections. All calls,
native logs, source identities and cleanup outcomes remain in private output.

## Comparison limits

- DOSBox queues its pair while paused; JPC-RR spaces its scheduled edges by 1 ms.
  Dispatch acceptance and released ownership do not prove BIOS or game-level
  consumption. The game-level keypad-5 effect remains unknown.
- DOSBox completed-renderer-frame/safe-fetch and JPC-RR retrace-start are distinct
  boundaries, with no fixed 60 Hz or AGI logic-update equivalence.
- The fDisBull prepared rat-room and JPC-RR ready first-room are different scenes
  and machine configurations. Their hidden state is not normalized.
- Observer postprocessing differs. The fDisBull helper computes full-DS and
  masked-RNG hashes and parses actor fields; JPC-RR returns its own info/register
  dictionaries and hashes DS. Native frame info may be aggregated in one API.
- fDisBull report IO and file-bound checks are outside its core/total-loop timer;
  JPC-RR per-command file/log/size work may be inside its total. These are
  controller-specific task timings, not a normalized emulator-throughput or
  whole-loop cross-engine speed ratio.
- Explicit API/RPC counts are not model turns. Warm median and nearest-rank p95
  describe the finite observations in one owned session. Selected observation
  equality does not establish whole-machine equivalence or whole-game TAS parity.

## Non-execution validation

Both derivatives were parsed and their `--help` entry points were exercised
without launching a guest. The timed core/retry/statistics method bodies were
compared structurally with the private originals; path selection, planning and
validation changes remain outside those measured algorithm bodies. No derivative
runtime result is claimed. The measured originals retain the hashes above.
