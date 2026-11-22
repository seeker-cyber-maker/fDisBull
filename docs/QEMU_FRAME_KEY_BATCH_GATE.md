# QEMU frame-key batches and optional codec validation

This 2026-11-22 continuation records a passing native keyboard-batch witness,
a separate native capacity case on the later producer, and the previously omitted
host `rgba-zstd` case. It preserves the distinction between the reconstructed host
candidate, the integrated sources, and the subsequent monitor-layout correction.

## Source and producer identities

| Item | Exact identity | Recorded coverage |
|---|---|---|
| Keybatch integration | `f6654499491c3f01b1b3990936190539210f06de` | Captured operation owner, exact native plans/receipts, refusal preservation, and native patch packaging |
| Integrated host source | `5e1f58df423c4f0b80d0abe338eae5c31a2d8bd6`, tree `377bf964ece491ef8433ca0639c26849082c9333` | Native keybatch witness and one optional host codec case below |
| First composed QEMU SHA-256 | `31841bb1ef356c5935fda5abb816b8ed5deef9d5223c6f218da23afc28f1d0ae` | Native keybatch attempt 01 passed |
| Monitor-layout correction | Host commit `db3ac85d1e9ea76a7ff8f04d7e3af56c6335eb59`; QEMU SHA-256 `95b3276fd9e38001b42b95b730e1641fe3c54799a3b1235a4e063c6f283d3c32` | Native capacity case below passed on this producer; the full queued-byte/restore witness remains bound to the first binary |
| Capacity-test correction and native check | `5c9c09b2aa70a42c298e41d08868f2c605710b2b` | One exact native capacity/ownership case passed on QEMU `95b3276f`, with zero skips |

The native keybatch patch is
[`qemu-10.0.13-fdisbull-frame-key-batch-v1.patch`](../native/qemu-frame-key-batch/qemu-10.0.13-fdisbull-frame-key-batch-v1.patch),
SHA-256 `c4354b674511bac0ca5c02f8d22ff28a790ab1a5c03cb2a0414ecd4bfd3e1c23`.
Its [manifest](../native/qemu-frame-key-batch/source-manifest.json) preserves the
four retained native before/after identities. This is reconstructed continuation
work; unavailable historical implementations or results are not claimed recovered.

## Host candidate

The bounded keybatch host selection passed **200 tests, with zero failures,
errors or skips**. It contains 92 new cases and the relevant existing keyboard,
frame, deadline, checkpoint, public-route and revision tests. Its complete source
delta and input hashes are recorded in `keybatch-candidate-host200.patch` and
`candidate-manifest.json`; this lane predates the integrated source listed above.

The first host attempt exposed a production cleanup defect: a typed native
refusal could preserve an owner even when restoration or release of the original
lock failed. Preservation now requires an unchanged owner and no cleanup errors.
The original exception and received evidence remain primary, the captured owner
is closed, and replacement resources are left to their owner. The retained first
two failed attempts also include corrected test-fixture mistakes; only the final
200-case lane is recorded as passing.

The native capacity test now selects behavior from complete advertised batch
support. Legacy producers must still reject the three-edge Shift/A/B request
with unchanged proof, then accept their original two-edge request. Batch-capable
producers must accept the three encoded bytes and report three accepted edges.
Both routes verify one generation increment and exact accepted counters. Later
external-input/wrong-token probes use unheld C so a duplicate B transition cannot
confound the ownership assertion. This test update is integrated as `5c9c09b`.

## Separate native capacity case

The exact updated node subsequently passed on source `5c9c09b` and QEMU
`95b3276f`:

```text
tests/test_qemu_frame_keys_native.py::test_native_frame_key_cas_capacity_and_external_input_guards
```

Result: **one passed, zero failures, errors or skips**, 3.71 seconds reported by
pytest and 4.674 seconds of owned-process supervision. The launch and result
receipts pin both complete identities above. Input hashes were unchanged, the
process group was gone, and the supervisor reported no timeout or cleanup errors.

This run exercised the batch-capable branch: three-edge Shift/A/B acceptance,
three encoded bytes, exact generation and accepted counters, a fresh matching
native proof, stale generation rejection, duplicate-held rejection, and external
input/wrong-owner guards without register or virtual-time advancement. The legacy
producer branch remains preserved in source; this run does not qualify it anew.
The original source/collection records are retained alongside the later native
receipt. Neither this result nor its newer producer changes the source/binary
binding of the full queued-byte witness or the optional codec case below.

## Native queued-byte and restore witness

One authored `raw_keyboard_mouse` IRQ fixture ran with the full pinned FreeDOS
floppy, a virtual clock, one x86 CPU, and translated PS/2 scan-code set 2. The
original 1,474,560-byte boot image had SHA-256
`552f7cbb0625960c050a3e682a4d2121cc2ffdfa9dc9d592ccd49edf179333dc`.
Only its private baseline copy was prepared for the fixture.

| Check | Observed result |
|---|---|
| Ctrl/Alt/A/Up make | Exact planned and guest-consumed bytes `1d 38 1e e0 48` |
| Up/A/Alt/Ctrl release | Exact planned and guest-consumed bytes `e0 c8 9e b8 9d` |
| Complete original and restored IRQ streams | Both `1d381ee048e0c89eb89d` |
| First acceptance | Four edges, generation 1, modifier mask 5, five FIFO bytes |
| Actual post-IRQ proof | Status 29, pending 16, output source 1, edge capacity 0; receipt equals a fresh native query |
| Busy refusal | Typed `device-busy` plan refusal; native proof, accepted prefix, registers, virtual time, guest log and owner preserved |
| Queued checkpoint | Captured before consumption; queue, counters, modifiers, IRQ state and full FIFO hash preserved across restore |
| Restore ownership | Fresh token and epoch 1→2; previous process reaped and source binding restored |
| Old release plan | Exact typed `stale-state` result with unchanged current before/after proofs |
| Fresh release afterward | Eight total accepted edges, generation 2, held set and FIFO empty |

An independent serializer, first checked against three frozen vectors, matched
the native state and batch digests. Direct planning left the cooperative session
revision unchanged. A refused direct apply may advance that host revision;
native state, guest memory/registers and virtual time were the no-effect oracle.

Enqueue and consumption were observed separately. Each enqueue left the guest
stopped; three explicit renderer updates then exposed the exact IRQ bytes.
Restoring the queued checkpoint reproduced the ten-byte future without a second
make request. The worker passed on its first run in 4.775 seconds. The reviewed
`WNOWAIT`/subreaper supervisor completed in 5.024 seconds, reaped both QEMU
lifetimes with exit code 0, and reported no timeout or cleanup errors.

This flow did not enter the initial public `status()` pending-event path. The
separate checkpoint witness's early monitor-eligibility refusal on the first
binary therefore remains a distinct observation. The later internal-GDB-monitor
layout correction and its pending-event/partial-source-frame checks require their
own receipts; they are not inferred from this keyboard result.

## Optional `rgba-zstd` host case

The exact previously skipped node passed once on integrated source `5e1f58d`:

```text
tests/test_qemu_frame_contract.py::test_each_codec_is_real_and_rgba_does_not_publish_or_run_hooks[rgba-zstd]
```

Result: **one passed, zero failures, errors or skips**, 1.83 seconds reported by
pytest, with 2.886 seconds of owned-process supervision. The case verifies the
declared 256,000-byte RGBA content size, exact decompressed pixels and hashes,
stable session revision, and absence of event/artifact/hook publication.

The dependency was the exact official `zstandard` 0.23.0 CPython 3.13 manylinux
x86-64 wheel: 5,436,310 bytes, SHA-256
`6f77fa49079891a4aab203d0b1744acc85577ed16d767b52fc089d83faf8d8ed`.
All 14 ZIP members, 11 regular files, 23,380,593 decoded bytes, safe paths and
every RECORD hash/size were checked before materializing a separate read-only
overlay. No package was installed into the shared runtime.

The isolated `-I -S -B` test child selected only the inspected `cext` branch.
The imported backend SHA-256 was
`3f34b3d48fff26f3f90fd85ac6db6d7a77df6c30c9a56ae25fe2fa98f52c697b`.
Its actual libpthread/libc/loader closure matched qualified runtime identities.
Evidence records 502 file-bearing module names, 496 unique files, and 49 final
executable mappings. Complete runtime trees of 1,177/1,383/629 entries, 152 named
runtime files, six absent loader paths, selected source, overlay and 13 historical
control files were unchanged afterward.

An earlier current-plan preflight rejected a list-order mismatch between two
otherwise identical inventories. A separate incomplete plan-hash argument was
also rejected. Both are retained; neither launched a test child or imported the
codec. The corrected explicit current plan ran the one selected case. Original
historical optional-case proposals and their old omission remain unchanged and
unexecuted.

## Evidence and remaining scope

The compact `qemu-keybatch-codec-validation-20261122-v2.zip` contains the authored
drivers, current plans, exact receipts, module/dependency identity records,
source manifests, the capacity-test patch, and earlier failure records. Its
member manifest provides per-file hashes. Package-source text is removed from
the sanitized wheel audit; its original audit hash is retained. No wheel,
overlay ELF, native executable, guest disk, checkpoint database, or guest binary
is included.

This version adds the separate capacity-test launch, result, pytest log and JUnit
record. The original archive is preserved unchanged; earlier collection-only
records continue to describe their original point in the work.

Primary result hashes:

| Receipt | SHA-256 |
|---|---|
| Native keybatch attempt 01 | `e98124080e518b8554d63c4f72fcdbfcd9d518bcd5876c969ba77528cd033919` |
| Native capacity case on `5c9c09b` / `95b3276f` | `3e7f0f5817ed0ecbd8502371855a9d7a957facb6fb89b82fdaf3c20a0358db5a` |
| Optional codec current check | `76055e71d65b8fb42f3f93a5308cbfff63bce42af5ce109525829f28a81bca21` |
| Optional codec import proof | `4d587145a0ba13be0088fd46bc633eed234a4fdebd32433affb1a20a31bee291` |

The keyboard witness covers one translated-set-2 chord and public DOS checkpoint
trajectory. Raw scan-code sets, Print/Pause/right modifiers, typematic, timeline
journals, scheduled input, hooks/layers, file-workspace combinations and vendor
games remain outside that native witness. FIFO hashes are opaque device proofs;
the guest IRQ log independently establishes the delivered bytes. The codec case
uses a host wire fixture and does not establish native raster generation or
DOSBox phase equivalence. Counts from separate historical selections must not be
summed as a new complete regression result.
