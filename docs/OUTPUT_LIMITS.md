# Bounded replies and retained output

The 0.24 development source limits each core CLI JSON reply to **65,536 bytes,
including its newline**. Small replies retain their existing shape. A larger
reply is retained as immutable private JSON and replaced by an explicit
`fdisbull-output-ref-1` descriptor. This applies to the core `request`, `serve`
and command emitters, including `il-run`; it does not change IL execution
semantics or impose a memory limit on an operation's internal result.

The standalone player/provider protocol has its own bounded public-content
contract. It does not accept core output descriptors as substitutes for scene
observations. Low-level Python `invoke` and analysis/interpreter APIs still
return ordinary structured values; the core `respond` and CLI emission boundary
apply the reply policy. Python hosts can use `OutputPolicy` and
`output_policy_context` explicitly.

## Read the outcome before retrieving the output

A descriptor's `complete:false` means **the full reply is not inline**. Its
`execution` fields preserve the original operation's reported `ok`, `complete`
and short `status` where present. Missing fields remain null. They do not prove
an unknown guest effect or add a completion claim to the original result.
`retry_safe:false` means output retrieval is not a reason to repeat an action.

For a successful wrapped request, the descriptor appears in `result`. For a
failed wrapped request, `ok` stays false, a short error notice remains in
`error`, and the descriptor appears in `output`. The artifact retains the
**entire original response envelope**, including its original error. A raw
command such as `il-run` retains its raw result instead.

`status:"artifact_required"` gives an `artifact` containing an opaque
`out-<sha256>` ID, its SHA-256, byte count and media type. Inspect that immutable
result rather than sending the original operation again. It records a past
observation, not the current state of a running guest. For example, an
`il-run` artifact has `/state`, while a wrapped request's state would be under
`/result/state` if that operation returns a state field.

```sh
fdisbull output-info out-<64-lowercase-hex-digits>
fdisbull output-select out-<64-lowercase-hex-digits> /result/name
fdisbull output-read out-<64-lowercase-hex-digits> --offset 0 --length 1024
fdisbull output-export out-<64-lowercase-hex-digits> /private/work/full-response.json
```

Replace the example ID and paths. These commands and their same-named JSON
methods need no project and work after the original process exits. All use the
same artifact directory. `output-select` uses JSON Pointer, including `~0` and
`~1` escapes; it has no expression evaluator. It returns a selected value only
when the whole selection fits both its budget and the reply budget. Otherwise
it returns `complete:false`, `reason:"selection_too_large"` and **no value**.
An absent pointer is an error, not an absent game object or false predicate.

`output-read` returns base64 with offsets, `eof`, `range_complete` and
`whole_complete`. A complete range is not the whole artifact. The default read
is 1,024 bytes; the library maximum is 8,192 and a smaller inline budget can
require a smaller range. Selections default to a 16,384-byte value budget and
can be reduced with `--max-bytes`. Retrieve a small decision field or export
privately rather than feeding every range into model context.

If an aggregate such as an array length is not an explicit stored field,
export the JSON privately, compute that aggregate locally and print only the
small answer. Do not guess the length from a step count or the last index you
tried. This retrieves the existing result and does not repeat its execution.

## Storage failures are separate from execution

If serialization, private storage, integrity, locking or quota checks prevent
retention, the descriptor reports `status:"output_unavailable"`, a short
`reason`, and `artifact:null`. The total byte count can be unknown. Execution
may already have changed a project or guest. Inspect the known operation
outcome and current state; neither rollback nor safe retry is implied.

When an operation otherwise succeeds, a retained artifact keeps its normal CLI
exit status. Unavailable output changes a successful CLI exit to **2**, while
preserving the operation outcome in the descriptor. An operation that already
failed keeps its failure exit. A server continues to own its live guest until
normal teardown; a delivery failure does not silently rerun or close it.

## Configure and protect the store

Use global options **before** the subcommand:

```sh
fdisbull --max-output-bytes 8192 --output-artifact-dir /private/work/outputs agent-skill
```

The inline limit accepts 4,096 through 1,048,576 bytes. Environment variables
`FDISBULL_MAX_OUTPUT_BYTES` and `FDISBULL_OUTPUT_ARTIFACT_DIR` provide defaults;
explicit global options take precedence. Invalid configuration is refused
before an operation starts.

The default artifact location is under `XDG_DATA_HOME/fdisbull/output-artifacts`
when configured, otherwise `~/Library/Application Support/fdisbull/output-artifacts`
on macOS or `~/.local/share/fdisbull/output-artifacts` on Linux. Artifact stores
must be outside Git, owned by the current user and private (directories 0700,
files 0600). Symlink traversal is refused. Explicit export creates a new 0600
file outside Git, without overwriting an existing destination. These files can
contain game-derived bytes or private analysis; exclude them from repositories
and tool deliveries just like project databases.

The initial limits are 64 MiB per retained artifact and 512 MiB for the store,
including stale temporary files. They bound retained bytes, not process memory.
Streaming writes are process-locked, hash-checked, validated as strict JSON and
published atomically; every read rechecks integrity. Staging a duplicate still
needs quota headroom. No automatic eviction or remote artifact service is
provided: manage the private store after its evidence is no longer needed.
Private locking currently requires POSIX facilities; an unsupported host gets
an explicit refusal instead of a weaker storage promise.

Release gates validate the installed skill's index, front matter, selective
resources and local links from the built wheel. Native offline-kit CI repeats
that check against its installed package. These checks accompany behavior tests;
they do not replace exact-source ordinary and native CI.
