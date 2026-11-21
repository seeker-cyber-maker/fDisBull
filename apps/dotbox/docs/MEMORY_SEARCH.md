# Scalar search over frozen memory

`dotbox memory-search` narrows candidate score, ammunition, timer or coordinate
fields across explicitly identified, frozen byte buffers. It uses the same
standard-library kernel as fDisBull through the small `fdisbull-core` distribution.
The full fDisBull application and a running emulator are not dependencies.

The command does not capture memory, pause or advance a game, write to a target,
or prove that a candidate has a particular meaning. A capture adapter or caller
must supply the bytes and their evidence. Keep candidate sets until further
observations distinguish them; a correlated field is not automatically the
authoritative field or the code that writes it.

## Identify the observations

Each buffer needs snapshot metadata. Supply a context JSON object containing:

| Field | Meaning |
| --- | --- |
| `source_sha256` | Lowercase SHA-256 of the identified source executable or authored fixture. |
| `run_id` | The retained run or observation-series identity. |
| `address_space` | The explicitly declared address domain. |
| `region` | An object with integer `start` and `length`; length must match the complete buffer. |
| `task_id` | The investigation or allocation/task identity relevant to this search. |
| `mapping_id` | The retained mapping identity; an address alone is not enough. |
| `version_id` | The source/runtime version identity used by the observations. |

Additional bounded context fields participate in the identity. Context must
remain identical for refinement. When source, run, task, mapping or region
changes, start a separate search. Do not invent a new label to conceal a change
or claim an allocation lifetime that was not observed. This tool checks supplied
labels and byte identities; it does not authenticate their provenance.

Use a distinct `capture_id` for every observation. Capture time belongs in
`--captured-at`, not in the shared context. A newer capture label alone does not
establish a newer live state.

Keep these inputs and search artifacts in an existing private directory outside
Git. Output files are newly created with mode 0600 and never replace existing
files. Snapshot metadata contains hashes and context, not the memory payload;
retain the frozen `.bin` files separately.

## Narrow a field

Assume `before.bin` and `after.bin` are complete compatible frozen regions and
`context.json` contains the evidence-backed context described above. The
following commands run entirely on those files:

```sh
dotbox memory-search snapshot before.bin --context context.json \
  --capture-id before --output before.snapshot.json
dotbox memory-search snapshot after.bin --context context.json \
  --capture-id after --output after.snapshot.json
dotbox memory-search start before.bin --snapshot before.snapshot.json \
  --width 4 --stride 1 --mode unknown --output initial.search.json
dotbox memory-search refine initial.search.json before.bin after.bin \
  --before-snapshot before.snapshot.json --after-snapshot after.snapshot.json \
  --mode delta --delta 100 --output delta.search.json
dotbox memory-search results delta.search.json after.bin \
  --snapshot after.snapshot.json --before before.bin \
  --before-snapshot before.snapshot.json --limit 64
```

Every reply states `runtime_observed: false`. Creation commands return compact
artifact receipts. `results` returns candidate offsets, addresses in the supplied
domain and scalar values. `--offset` is the candidate ordinal for paging, not a
byte address. Follow `next_offset` until it is null; paging does not discard any
candidate from the saved search state.

Initial modes are `unknown`, `equal --value N` and
`range --minimum LOW --maximum HIGH`. Refinement modes are `equal`, `not_equal`,
`changed`, `unchanged`, `increased`, `decreased` and `delta`. Value comparisons
require `--value`; delta requires `--delta`. A delta is the mathematical new
value minus the old one: an unsigned byte changing from 255 to 0 has delta −255.

Choose widths 1, 2, 4 or 8 bytes, `--signed` when appropriate, and either
`--byteorder little` or `--byteorder big`. The default stride is 1, so unaligned
candidates are included. An explicit bias uses
`stored_value = displayed_value + bias`; arithmetic does not silently wrap.
Width, stride, sign, byte order and bias remain fixed within a search.

## Bounds and refusals

The shared kernel permits at most 16 MiB per buffer, 1,048,576 surviving candidates,
65,536 candidate intervals and 4,096 rows per results call. Candidate or interval
overflow refuses the search; it never returns a partial reusable candidate set.
Use a smaller region, wider stride or discriminating initial value to fit the
declared bound. DotBox limits JSON input/artifacts to 8 MiB and inline replies to
64 KiB; request a smaller results page if its reply would exceed that bound.

Regular-file and stable-read checks refuse special files, symlinks and bytes
that change during reading. Refinement revalidates the retained search state
and its immediate before/after payload bindings; it does not load or authenticate
the full ancestry. A changed context, corrupt payload or capture ID identical
to the immediately preceding observation is an error and does not create a new
result artifact. The caller remains responsible for unique capture identities
across the wider history.

The native capture limit and the offline search limit are separate. These bounds
do not authorize a 16 MiB live read or establish a real-time response guarantee.

## Python and installation

`dotbox.memory_search` exposes the shared functions `snapshot_metadata`,
`validate_snapshot`, `start_search`, `validate_search`, `refine_search` and
`search_results`. These functions accept immutable bytes and dictionaries and
perform no file or emulator operations. The shared wire-format names remain
unchanged for interoperability. DotBox does not expose live edits or the FDB
runtime adapter through this API.

Install the declared `fdisbull-core==0.1.0.dev1` wheel alongside DotBox and its
ordinary dependencies. This is a small shared dependency, not the full fDisBull
application. An offline wheelhouse must include it. `dotbox doctor` checks the
installed shared kernel with an authored fixture; this is an offline package
check, not native or game qualification.
