# Recovering an oversized DinoPark Z reply

The DinoPark bridge keeps its **32,768-byte UTF-8 line limit, including the newline**.
When a producer returns a larger JSON result, the bridge retains the exact full
JSON bytes in a private, content-addressed artifact before sending a compact
`fdisbull-z-reply-ref-1` response. It persists a delivery hold before transmission.
An oversized observer history therefore cannot erase a returned native stop or
force the caller to repeat its original input.

This is reply delivery recovery. A producer's `complete` and `status` describe
that producer's result. Completing a native input interval does not establish
that an entire quit sequence or other game intent has finished. Selected DOS
termination requires actual native `guest_exit` evidence; closing the debugger
or worker does not provide that evidence.

## Protocol

Small replies retain their existing shape. An oversized reply returns:

```json
{"format":"fdisbull-z-reply-ref-1","complete":false,"status":"reply-retained","retry_safe":false,"delivery_pending":true,"reply":{"id":"reply-<32 hex digits>","artifact_id":"out-<sha256>","sha256":"<sha256>","bytes":54000,"media_type":"application/json"},"execution":{"returned":true,"complete":true,"status":"native-control-complete"}}
```

The actual response includes a short recovery message. `execution` preserves
only the producer's returned completeness and bounded status; it is not a new
completion certificate. Request the retained original result before interpreting
its detailed native outcome. Artifact IDs and receipt IDs are opaque; there is
no client-supplied filesystem path.

| Request | Behavior |
| --- | --- |
| `{"op":"reply_status"}` | Recover the pending receipt even if the compact response was lost. |
| `{"op":"read_reply","reply_id":"reply-…","offset":0,"length":8192}` | Read verified original bytes as base64. Follow `next_offset` until `eof`. Length is 1–8,192 bytes; offsets are byte offsets. |
| `{"op":"select_reply","reply_id":"reply-…","pointer":"/run/outcome"}` | Select a JSON Pointer from the verified original result, with a 16,384-byte selection limit. An oversized selection returns `complete:false`; use pages. |
| `{"op":"accept_reply","reply_id":"reply-…","sha256":"…"}` | Acknowledge delivery only after the caller has verified the result's digest and meaning. |

`reply_status`, `read_reply` and `select_reply` access retained files only. They
perform no native RPC, guest input, run, step, save, restore, scene readback or
new-guest launch. Read responses stay below the same wire limit. Assemble pages,
verify their total length and SHA-256, and decode the full JSON. A selection is
useful for inspecting an individual stop; it does not imply that the caller has
read every diagnostic entry.

While delivery is pending, ordinary observe, act, save and load requests return
the pending reference. They do not re-enter their handlers. Extension adapters
that send native input directly must check `ZService.reply_pending` before
sending input or advancing execution. The private investigator adapter used for
native verification does so; raw terminal controls remain investigator test
infrastructure rather than newly exposed public Z scene verbs.

Acknowledgement checks the artifact and the current read-only `session.status`
against the retained worker epoch, provider token, native run, session ID, state,
revision and stop reason. Missing native evidence, a new worker, changed native
state, the wrong digest, a foreign receipt or corrupt bytes leave the hold in
place. Repeating a successful acknowledgement is idempotent while that witness
is unchanged. A receipt from an earlier delivery cannot clear a later hold.
Acknowledgement does not clear existing action/checkpoint recovery flags or
upgrade an unknown effect to a confirmed effect.

If the retrieved result shows that credits are still running, finishing them
requires a **separately declared input-free execution continuation**. Reading or
acknowledging a reply never performs that continuation, and never repeats the
Quit, confirm or decline-save input.

## Retention and failure behavior

Results live under the worker's private `z-replies/artifacts` directory. Immutable
receipt records contain the artifact identity and private native witness;
`state.json` records the pending delivery. A failure tombstone is persisted
before the spill, and file contents and directory entries are synchronized before
the compact reference is sent. Artifacts reuse the core's verified JSON output
store: 64 MiB per result, 512 MiB per store. Receipt state belongs to one owned
worker; concurrent workers must not share a work directory.

A storage/quota/integrity failure leaves delivery unresolved, with retry marked
unsafe and further action input withheld. It cannot recreate missing native
evidence. Lost reference recovery is supported while the same worker and native
guest survive. Retained bytes remain inspectable on disk after shutdown, but a
new worker cannot acknowledge an old worker's native witness or resume a disposed
guest. Starting a fresh process still requires a new work directory.

EOF with a pending delivery produces an incomplete recovery-required session
receipt even when all owned processes shut down cleanly. Host cleanup and
selected-program termination remain separate facts.

## Verification scope

Regression tests exercise the former overflow failure, exact UTF-8 accounting,
paging and selections, read-only retrieval, held action/checkpoint dispatch,
lost references, journal reopen, stale/foreign/corrupt receipts, retention failure
and repeated acknowledgement. Native acceptance against the original DinoPark
is recorded with the [PR #41 findings](DINOPARK_STATIC_ANALYSIS_FRICTION.md).
The change is source-only; packaging, publication and installation belong to the
release workflow.
