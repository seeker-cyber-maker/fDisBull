# DOSBox-X CR4 checkpoint candidate

This optional delta applies to DOSBox-X commit `029bd65c5dcc7cdc7f2e14e35278620d9707d969`
with the historical fDisBull layers overlay. Build in a separate directory and
select the resulting binary explicitly when testing.

## Build

From the fDisBull repository, extract the historical overlay and its manifest
into an existing directory named by `BASE_DIR`.

```sh
git show 1004bda484b0405e35247432447deb0e9c7d12de:experimental/dosbox-x/layers/headless-agent.patch > "$BASE_DIR/headless-agent.patch"
git show 1004bda484b0405e35247432447deb0e9c7d12de:experimental/dosbox-x/layers/source-manifest.json > "$BASE_DIR/source-manifest.json"
shasum -a 256 "$BASE_DIR/headless-agent.patch" "$BASE_DIR/source-manifest.json"
```

Compare both digests with [the candidate manifest](source-manifest.json).
Apply the historical overlay to a clean checkout of the pinned DOSBox-X
commit and verify the source hashes in the historical manifest. Verify both
candidate preimage hashes, run `git apply --check` and `git apply` with
[the candidate patch](dosbox-x-029bd65c-pse-checkpoint.patch), then verify
both postimage hashes. Use the layers profile to build the binary.

```sh
./autogen.sh
./configure --enable-sdl2 --enable-debug=heavy --enable-dosbox_agent \
  --enable-agent-zstd --disable-avcodec --disable-libslirp --disable-libfluidsynth
make -j2
shasum -a 256 src/dosbox-x
```

The compiler, dependencies and build flags affect the binary digest. With
the existing QEMU-DOS native test profile and FreeDOS boot image selected,
run the following from the fDisBull repository.

```sh
export FDISBULL_DOSBOX_LARGE_PAGE_CANDIDATE=/absolute/path/to/candidate/src/dosbox-x
python -m pytest -q tests/test_dosbox_pse_checkpoint_format_native.py \
  tests/test_qemu_le_remap_tracking_native.py::test_dosbox_large_page_candidate_paired_unassisted
```

## Checkpoint format and scope

The CPU component keeps its historical prefix and appends two native-endian
32-bit words. On the tested little-endian host the first spells `PSE1` and
the second holds CR4. After the paging loader invalidates cached translations,
the candidate restores CR4 and derives `do_pse` from bit 4 and the configured
PSE capability.

A component ending exactly at the historical prefix retains the receiver's
historical CR4 behavior. An old checkpoint has no saved CR4 value to recover.
Removing the entire extension yields the same legacy representation. A short
prefix, a partial extension, an unknown marker or trailing data causes the
load to fail. The public debugger discards the affected guest because a
native load can change machine state before reporting failure. Public
checkpoints still require the same producer binary for save and restore.

The [local paired results](../../docs/DOS_QEMU_HANDOFF.md#unprimed-dosbox-x-restore-for-4-mib-protected-le-code-2026-11-24)
cover the 4 MiB LE remap and selector-switch fixture and the DOS return path.
