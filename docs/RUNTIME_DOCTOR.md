# Runtime doctor

`doctor` runs finite acceptance against a disposable authored target. It accepts
no user game or project. It starts even when decoding libraries are missing and
reports all missing/unusable dependencies in a machine-readable receipt. The
normal CLI and analyzer still require the genuine dependencies.

```bash
fdisbull doctor --backend dosbox --executable /path/to/layers/dosbox-x \
  --output /path/to/new-evidence
fdisbull doctor --backend wine-qemu --executable /path/to/qemu-system-x86_64 \
  --kernel /path/to/linux-amd64 --initramfs /path/to/current-wine.cpio.gz \
  --output /path/to/new-wine-evidence
```

`dosbox-qemu` also accepts the kernel/initramfs arguments. The DOS self-test
requires the layers backend. Prepared Wine and optional IDA runtimes must be rebuilt with this package (the common broker resource changed). The Wine profile is prepared
using `python -m fdisbull.wine_runtime`: the new fixed `selftest.c` is compiled
inside the Linux guest at boot, and its source is part of the checked resource
identity. Old images fail honestly with a rebuild message. No arbitrary source
compilation RPC is introduced. The optional IDA and raw/outer-machine profiles
have no authored full doctor test and are rejected explicitly.

The doctor imports real libraries, decodes an instruction, fingerprints backend
inputs, launches the authored target, reaches an execution breakpoint, executes
an alternate instruction while RAM stays original, verifies a mouse click with
native coordinates and a data watch, records a bounded trace, saves/restores a
native state, promotes captured code offline and exports stored evidence after
reopening the project. Wine also checks guarded memory editing. DOS verifies
that the guest actually observes mouse coordinates; a screenshot alone cannot
pass that check. There is no user-target compatibility or elapsed-time parity
claim.

The CLI returns nonzero on failure. JSON returns a receipt with `status`, the
individual checks, dependency details, capabilities, observation contract,
backend hashes and exported artifact hashes. Failed or unsupported checks are
not upgraded to a pass. An output directory must be new; sealed evidence is
never overwritten. Only receipts, frames and traces are retained there. The
authored EXE, project DB and native checkpoints live in a private temporary
directory and are removed after the finite test. With no `--output`, only the
returned receipt survives. A full VM test may take several minutes.

The externally restricted Pro chat can obtain genuine dependencies and the
corrected direct DOS backend through the [CI-verified 0.15.0 offline kit](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.14.0/fdisbull-linux-dos-offline-0.15.0-e91879c-2026-10-26.zip)
and [checksum](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.14.0/fdisbull-linux-dos-offline-0.15.0-e91879c-2026-10-26.zip.sha256).
That separately versioned candidate kit predates this doctor command. Its
installer creates a new environment without network access or system-library
replacement. The 0.16.0 source candidate is not included in that kit.
