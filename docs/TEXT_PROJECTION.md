# Live text projection

A text projection is an immutable, hash-checked project record over one pinned
progressive workflow revision. It exposes only authored public context and
object descriptions. The original guest remains authoritative: each read
checks all declared scenes against a paused guest, and exactly one complete
match is required. Ambiguous, unknown, inconsistent-frame, drifted-resource and
failed checks yield `{"complete":false}` without investigator details.

Save with `project.debug_save_text_projection(name, definition, parent=None,
version=None)`. Subsequent revisions require the current parent ID. Read with
`project.debug_text_projection_info(name_or_revision, version=None)`; an active
handle pins its selected revision. Open a live backend with
`session.text_projection(name_or_revision, resource_root)`; it implements
`observe()` and `act(request)` as described in [TEXT_PLAYER.md](TEXT_PLAYER.md).
`serve_stream(backend, reader, writer)` serves one request and response per
JSON line on caller-owned streams. Callers exposing it over a transport must
authenticate clients. The text host below does so with a private per-run
password file. The independently distributed player does not import fDisBull.

The source definition has this shape (IDs, names and text below are synthetic):

```json
{"format":"fdisbull-text-projection-1", "workflow_revision":"PINNED_WORKFLOW_REVISION",
 "contexts":[{"id":"room", "title":"Room", "description":"A door is here.",
 "scene_revision":"PINNED_SCENE_REVISION", "partial":true,
 "objects":[{"id":"door", "label":"door", "aliases":["gate"],
 "description":"A wooden door.", "scene_object":"SCENE_OBJECT_ID", "inventory":false,
 "bindings":[{"verb":"open", "item":null, "action":"WORKFLOW_ACTION_NAME",
 "dispatch":{"kind":"scene"}}]}]}]}
```

`item` is null or the internal ID of another object in that context. Verbs are
lowercase. Objects and their verbs are exposed only while the scene's visibility
predicate is true; readiness and enabled predicates are checked separately at
act time. Context and object IDs on the wire are opaque, handle-scoped values,
not the authored internal IDs. The opaque token binds the projection, workflow,
run, runtime epoch/load, frame, state revision and recognition/availability
result. Repeated paused reads of the same state retain the same token. A token
from another handle cannot be used here. Clients must treat IDs and tokens as
opaque and refresh them after reconnecting.

Each binding pins a workflow action in the same scene. `scene` dispatch invokes
that action's scene object. `movement` dispatch uses `{"kind":"movement",
"args":{...}}`, with the keyword arguments accepted by `session.move`, including
`macro_set`, `start`, `stop`, `observations`, `until`, `progress` and `settle`.
`assisted-travel` uses `{"kind":"assisted-travel","plan":{...},
"timeout_ms":10000}` and requires a validated plan pinned to the same scene.
These descriptors are investigator-side data and are never returned in the
player view. Assisted travel may change guest memory and skips traversal as
specified by its plan; it is an intentional assistance profile, not ordinary
movement. The workflow checks resource identity, dependencies and the scene
again before dispatch, and stores its private receipts. The bridge compares the
token again under the workflow controller lock immediately before the callback.
Other controllers must honor that same lock; this interface cannot serialize
uncooperative external guest control.

## Private live checkpoints

The live backend supports `save(slot="live")` and `load(checkpoint="live")`;
the line protocol uses `{"op":"save","slot":"live"}` and
`{"op":"load","checkpoint":"live"}`. Save returns an opaque checkpoint ID
and advances the named slot while preserving older IDs. Load accepts either a
slot or a returned ID. An existing slot takes precedence if its name also looks
like an ID; prefix `id:` to select the opaque ID explicitly in that case.
A missing slot returns `missing`; an incompatible,
corrupt, interrupted or otherwise failed restore returns `incomplete` and
blocks projection handles on that session until a successful restore. It never silently starts a fresh
game after a failed restore. Public replies do not include private paths,
runtime addresses, native states, or debugger errors.

Checkpoint records, native experiment artifacts, binding recipes and private
diagnostics stay in the project database. Capture requires a paused, qualified
projection, verified runtime binding witnesses, and the native experiment
backend. It refuses untracked debugger controls; supported owned breakpoints,
watches and hooks are captured by the native experiment mechanism. Active code
layers remain outside the original-byte workflow qualification. On load, the
source and byte version, native backend, pinned projection and workflow, and
resource inventory must still match. Native state compatibility checks include
the mounted game files. Runtime bindings are invalidated and re-established
with their captured witnesses. Restoring rotates public tokens, so pending
actions and clarifications from an earlier state must be discarded.

Native restore invalidates its cached frame. The host therefore advances a
bounded guest interval after each restore, defaulting to 100 guest milliseconds
and configurable as `checkpoint_prepare_guest_ms` (1–10,000). The response
reports requested and measured guest time; game logic can run during this
interval. A breakpoint, watchpoint, hook, timeout or incomplete fresh scene
check makes restore incomplete; it is not automatically resumed. The setting
is distinct from the initial host `prepare_guest_ms`. These checkpoints preserve
the native state and owned controls; they do not establish full game fidelity.

A scene action reports success only after its observed outcome is complete and
matched; movement and assisted travel require their own complete, successful
result. Accepted input alone is not success. Errors and partial execution are
reported generically as incomplete; they may already have changed the guest.
Detailed private workflow receipts retain the actual result or error. Public
authored labels, aliases, prose and verb lists must themselves be suitable for
the player profile. This interface does not verify that descriptions match a
specific game's perceptual information, nor does it implement a full game or
prove text/graphics equivalence.

## Loopback host

`fdisbull.text_host.host(config, on_listen=callback)` starts the selected native
debugger, optionally restores a stored state artifact, binds the explicitly
listed runtime fields, and then serves one connection on IPv4 loopback. It
opens an existing project and uses `game_dir` as both the debugger game directory
and workflow resource root. No game, debugger, state or database is bundled.
For example:

```json
{"format":"fdisbull-text-host-1", "project":"/path/to/project.fdb",
 "backend":"/path/to/debugger", "game_dir":"/path/to/game",
 "version":1, "projection":"public-view", "state":"stored-state-artifact-id",
 "bindings":[{"name":"actor", "address":1234, "length":16,
              "expected_hex":"4142", "provenance":{"source":"qualified observation"}}],
 "port":0, "timeout_ms":60000, "prepare_guest_ms":100}
```

`version`, `state`, `bindings`, `port`, `timeout_ms`, and `prepare_guest_ms` are optional. Each
binding requires `name`, integer linear `address`, `length`, `expected_hex`,
and `provenance`; `mask_hex` is optional. The runtime validates the witness
against the paused guest. Addresses and witnesses must be supplied from the
user's qualified context; the host does not discover or guess them. A failed
restore or binding closes the session and project before opening a listener.

`prepare_guest_ms` defaults to 0. When explicitly set to 1–10,000, the host
advances that many guest milliseconds after restore and binding, before opening
the listener, to allow a fresh frame to be produced. This changes guest time and
may execute game logic; it is not a passive observation. The run uses fast
forward, stops on hooks, and has a host timeout capped at 30 seconds (or the
configured timeout, if shorter). A breakpoint, hook, timeout, or other stop
prevents listening; no automatic continuation occurs. The endpoint callback
includes the requested and measured guest duration and the stop outcome when
preparation succeeds. The workflow still performs its normal fresh checks;
preparation does not guarantee that the resulting frame matches a scene.

Port 0 selects an available port. The callback receives `host`, `port`, and
`password_file` on the owner thread. Connect the separate player with
`--connect 127.0.0.1:PORT --connect-password-file PASSWORD_FILE`. The host
creates the file in a private temporary directory and removes it on close.
The player sends the password before any observation or action. Invalid
connections close without consuming the one authenticated client slot.
The host accepts one authenticated client and closes the session and project on disconnect.
The default 60-second timeout applies separately to waiting for a client and to
each idle socket read; it can be set from 1 to 600,000 milliseconds. A client
that continues issuing requests can keep the connection open. It is not an
automation or a persistent service. Loopback restricts remote network access,
but other local processes may connect and delay admission. Protect the password
file and the endpoint callback output; TCP traffic is not encrypted.
