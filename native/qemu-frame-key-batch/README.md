# Stopped frame-key batches

This source patch adds exact scan-code planning and one atomic stopped PS/2
commit. It lets a useful multi-modifier chord fit according to its actual bytes
instead of the older conservative eight-bytes-per-edge reservation. Existing
frame-key commands and their conservative capacity remain available.

Apply it only to QEMU 10.0.13 source whose four target files match every
`before_sha256` in `source-manifest.json`. Those files already include the
frame-key ownership and source-video-fence changes. The manifest records the
complete before/after identities; a source hash is not execution evidence.

## Public behavior and protocol

- `x-fdisbull-plan-frame-key-batch {edges}` observes a stopped device. It returns
  an exact bounded plan or a typed refusal without reserving or changing input.
- `x-fdisbull-apply-frame-key-batch` requires that plan's epoch, generation,
  complete state digest, batch digest, ordered edges and owner token. It
  revalidates the request, prepares the complete queue/owner afterimage, then
  publishes it once under BQL and signals the existing PS/2 IRQ path.
- The accepted proof is filled from the actual controller state after the IRQ.
  Acceptance reports device queuing; guest consumption remains unknown.

The first profile supports raw scan-code sets 1 and 2 and translated set 2.
Requests contain 1–32 distinct edges and at most 64 resulting held keys. Encoding
uses at most 256 scratch bytes; the complete translated stream must fit the
16-byte protocol FIFO. Unsupported profiles, busy devices, foreign ownership,
stale state, counter exhaustion and migration admission failures refuse before
commit. Planning never invokes the ordinary live keyboard handler. A zero-byte
Pause release still records its explicit logical edge without fabricating IRQ.

The Python public key grammar is unchanged. Right modifiers, Print and Pause
remain native encoder witness inputs. Typematic repeat is unsupported. Batch
plans are ephemeral and cannot survive reset, detach, load or owner replacement.
No new durable checkpoint state is introduced.

The existing Python `frame_inputs` and `timeline_advance` entries select this
route only when both new commands and the original frame-key capability are
present. A partial new capability refuses. Empty direct input does not plan or
apply. The outer operation captures its original owner and channels before
callbacks; failures never close or write deadlines into a substituted owner.

A fully typed refusal preserves history only when its complete before proof
matches the queried owner and the apply proof is unchanged. An apply refusal
resolves only its own pending intent. Existing journal, cursor and pending
inputs survive. Transport, receipt, persistence or cleanup uncertainty closes
the original owner without retry or compensating release. The compact stored
receipt is byte-bounded before intent/apply against the 8192-byte reservation.

## Verification status

The host selection passed **200 tests**, including the new batch/ownership
cases and existing frame, public-route, deadline, checkpoint-key and cooperative
revision tests. The three frozen independent serializer vectors are tracked at
`tests/fixtures/qemu_frame_key_batch_vectors.json`. They cover idle/active state,
ordered requests, signed bounds, UTF-8 and the zero-byte release encoding.

The complete four-file native delta was inspected and packaged from the
surviving source reconstruction without changing those afterimages. Native
patch composition, QAPI generation, compilation, ordinary keyboard preservation,
raw/translated scan-code witnesses, queue/IRQ behavior and checkpoint replay
remain unexecuted for this candidate. Host protocol doubles do not establish
those results. This source does not qualify global DOSBox parity or change the
default backend.
