# Progressive scene workflows

This first format qualifies the original stored byte version. An active RAM or
execution layer withholds workflow dispatch even when the scene still looks the
same. Layered experiments retain their separate saved-experiment controls; a
fresh screenshot does not requalify altered code semantics for this workflow.

A workflow records a partial, version-bound set of scene action contracts and research questions. It is not a game reconstruction or a claim of complete coverage. Existing `fdisbull-scene-bundle-1` files are unchanged. No external files are imported, modified, or copied.

Build a separate `fdisbull-resource-inventory-1` using `resource_inventory(root, engine=..., profile=..., adapter=...)`. It records every regular file under the supplied directory by relative path and SHA-256. The directory should be the complete external resource root relevant to the edition; the tool cannot establish that a caller selected the correct root or that a profile label is accurate. Symbolic links are rejected. Resource bytes are rehashed before every workflow observation and dispatch, and again after the live check. Added, removed, or changed files block the operation. The inventory records content identity, not provenance or decoder correctness.

Save a JSON document using `project.debug_save_workflow(name, document, resource_root=root, parent=..., version=..., author=...)`. Its exact fields are:

```json
{
  "format": "fdisbull-progressive-workflow-1",
  "source": {"source_sha256": "...", "format": "MZ", "arch": "x86", "bits": 16, "mapped_sha256": "..."},
  "inventory": {"format": "fdisbull-resource-inventory-1", "engine": "...", "profile": "...", "adapter": "...", "files": [{"path": "...", "sha256": "..."}]},
  "research": [{"context": "room", "question": "other exit", "status": "unknown", "evidence": []}],
  "actions": [{"name": "open", "kind": "scene", "scene_revision": "exact revision ID", "object_id": "exact object ID", "dependencies": [{"name": "room logic", "status": "resolved", "evidence": ["evidence reference"]}], "evidence": ["evidence reference"]}]
}
```

Use `fdisbull.scene_bundles.identity(project, version)` to obtain the source identity. Evidence entries are caller-supplied references, not independently verified claims; scene revisions themselves validate their stored screenshots. Research status and dependencies are `unknown` or `resolved`; all dependencies require evidence, including evidence of an unresolved question. Unknown dependencies block only their associated action. The caller must accurately declare relevant dependencies and evidence. An empty dependency list asserts that no additional dependencies are needed for the bounded contract.

Each save creates an immutable revision. Existing workflows require the current revision as `parent`; a stale parent fails rather than merging local edits. `debug_workflow_info(name_or_revision, version=...)` reads the latest named revision or an exact revision. Byte versions and exact scene/object identities are checked on save and read.

`session.workflow(name_or_revision, resource_root=root)` pins a revision. `observe(action=None, context=None)` reports qualified and blocked action names and an on-demand queue of unknown research filtered by context, plus unknown dependencies for a selected action. For an action, it also runs a fresh scene check. `adopt(exact_revision_id)` switches to a revision of the same workflow between actions. `act(name, **options)` performs a scene action through the existing scene handle, which independently rechecks the current state immediately before input and verifies its outcome. The workflow receipt includes its revision, inventory digest, scene and object identities, fresh observation and action result. Scene errors retain their existing behavior.

`execute(name, callback)` permits an integrating controller to implement `movement` or `assisted-travel`: the callback receives `(contract, pinned_scene_handle, fresh_observation)` after resource, dependency and scene checks, and runs while the workflow controller lock is held. Non-scene contracts may set `object_id` to null. `act` rejects non-scene contracts. Callback implementations are responsible for bounded input, their own prerequisites, outcome verification and honest receipts. The workflow does not validate callback semantics or confer permission for memory writes. A shared per-session lock serializes workflow operations and prevents adoption during a callback; callers must route all live input and guest advancement through the same controller. Direct session methods and separate sessions are outside this lock. The caller is also responsible for keeping the resource tree stable during an action and for any isolated-session or external-service policy.

Every dispatch appends a `started` receipt before qualification and a `returned` or `failed` receipt afterward. `project.debug_workflow_receipts(name_or_revision, version=...)` reads the hash-checked records for that workflow, including the pinned revision, attempt ID, action, observation when available, and result or error. A `started` record without a terminal record means the outcome is unknown, such as after interruption. A failed callback may have already sent input; no rollback is implied. `returned` means the callback returned; its result must be inspected to determine whether the action succeeded or was incomplete. Receipts record callback results as reported, not independent proof that an action succeeded. Callbacks and observations must be JSON-serializable.
