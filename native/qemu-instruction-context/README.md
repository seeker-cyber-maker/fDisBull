# QEMU instruction trace context v2

Apply this incremental patch after the exact `qemu-instruction-trace` v1 package. Verify every preimage hash in `source-manifest.json`, then run `git apply --check`. Build the x86 system target with TCG plugins enabled (`-Dplugins=true`).

Schema v2 receipts include `trace-version: 2`. TCG events add up to 15 exact translated bytes copied after final TB size is set in `plugin_gen_tb_end`, using `translator_st` over translation-retained bytes. Each generated callback carries its own immutable payload from a bounded 65,536-entry slab. The runtime callback does not reread guest memory. A failed copy, instruction longer than 15 bytes, or exhausted slab preserves the boundary record and marks bytes unavailable with a reason.

Capture admission requires serial TCG (`CF_PARALLEL` disabled). This makes `tb_flush` synchronous before the payload slab is freed or replaced, including on machines configured with `max_cpus` greater than one. Parallel TCG receives the QMP error `instruction trace requires serial TCG (CF_PARALLEL disabled)`.

The x86 provider samples current code bits, CS selector, and effective CS base at the event. It reports code bits 16, 32, or 64, and uses base zero in 64-bit code mode. Other targets report context unavailable. `breakpoint-pre-dispatch` events report bytes unavailable with `breakpoint-pre-dispatch-no-translation` because the breakpoint check precedes TB translation; runtime x86 context may still be available.

The fields describe translation and runtime CPU context. They do not establish source identity, successful decode, completion, or retirement. Paging faults before translation produce no TCG dispatch callback. Self-modifying code is represented by the bytes attached to each translated TB; a later TB translation can carry changed bytes at the same PC. Reset and instrumented checkpoint load/import invalidate trace records and advance epoch. The v1 trace package and DOSBox default backend are unchanged.

Local plugin-enabled build passed with candidate SHA `6f969d1bbe8f8e4398412bcd3ee24e88984f2e6be869267450b0bb5523bcc641`. The final candidate passed a 38-test host/native selection with no skips, including the paired SMC case and a paused one-active/max-cpus-two serial-TCG refusal witness. The private JUnit hash is in `source-manifest.json`. Broader parity remains unqualified.
