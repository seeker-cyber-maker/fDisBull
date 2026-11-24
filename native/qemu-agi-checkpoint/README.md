# Native AGI debugger checkpoints

This patch adds the stopped QOM string property `agi-debug-checkpoint-hex` to
the AGI CPU. The property reads a private binary checkpoint encoded in hex.
Its setter admits one load into a fresh owner configured with the public AGI
debugger's observation mask and capacity. The native runtime validates the
source identity, state, stack and journal bounds before it adopts the payload.
The debugger uses this property independently of AGI's guest save-game slots.

Start with the QEMU 10.0.13 release source and the AGI overlay at commit
`63d233502b04e55355fda837c22d3b621b54b6a7`.
The [pinned AGI overlay](https://gitlab.com/brewster-jennings-group/fdisbull/-/tree/63d233502b04e55355fda837c22d3b621b54b6a7/native/qemu-agi)
contains the target sources and build prerequisites. The
[source manifest](source-manifest.json) records the archive, overlay, patch
and individual source file hashes.

Set `agi_base` to the checkout of that pinned commit, `qemu_src` to the
extracted QEMU source and `checkpoint_dir` to this directory. Use absolute
paths. Apply the overlays in order and build in a fresh directory.

```sh
python3 "$agi_base/native/qemu-agi/apply_overlay.py" "$qemu_src"
(cd "$qemu_src" && git apply --check "$checkpoint_dir/qemu-10.0.13-fdisbull-agi-checkpoint-v1.patch" &&
 git apply "$checkpoint_dir/qemu-10.0.13-fdisbull-agi-checkpoint-v1.patch")
mkdir agi-checkpoint-build && cd agi-checkpoint-build
"$qemu_src/configure" --target-list=agi-softmmu --without-default-features \
  --enable-system --enable-tcg --enable-pixman --disable-user --disable-tools \
  --disable-docs --disable-guest-agent --disable-containers --disable-download \
  --disable-install-blobs --disable-debug-info --disable-qom-cast-debug \
  --disable-rust --audio-drv-list=
ninja -j2 qemu-system-agi
```

Set `FDISBULL_QEMU_AGI_CHECKPOINT` to the resulting executable for
`tests/test_qemu_agi_checkpoint_native.py`. Set `FDISBULL_QEMU_AGI_LEGACY` to the
earlier unpatched AGI executable to exercise compatibility with it in the
same batch. See [the debugger guide](../../docs/QEMU_AGI.md) for the public API.
