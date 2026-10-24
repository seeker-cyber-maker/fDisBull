# Wine/Linux runtime qualification — 2026-10-23

**Wine's Win64 debugger operations work in a headless, fully emulated x86-64 Linux VM on this Mac.** The Apple container/Rosetta route starts Windows programs but fails this debugger probe. Both experiments contain Wine and the real DOSBox layers backend in the same Linux environment.

This directory is a qualification experiment. fDisBull 0.11.0 still launches DOS MZ projects through its debugger API. There is no packaged PE debugger adapter, PE GUI automation, or PE saved-state support in this change.

## Fresh results

| Check | Apple container + Rosetta | QEMU full x86-64 CPU emulation |
| --- | --- | --- |
| Linux environment | Ubuntu 24.04 amd64 userland; Apple Linux 6.18.35 | Same runtime userland; Debian x86-64 kernel 6.1.0-50 |
| Wine | Ubuntu `9.0~repack-4build3`, Win64 prefix | Same Wine build |
| Ordinary Windows command | Expected marker, exit 0 | Debug fixture itself executes successfully |
| Process/module debug events | Process, six modules, loader breakpoint | Process, six modules, loader and fixture breakpoints |
| Fixture breakpoint, memory edit, register read, single-step | Not reached; Rosetta reports `invalid gdt selector index 5` | **Passed** |
| Exact original controller from the Rosetta experiment | Failed | **Passed**, including `CONTEXT_ALL` |
| Required DOSBox native tests | **25 passed, 7 failed, 0 skipped** | **24 passed, 8 failed, 0 skipped** |
| Ordinary fDisBull source suite | **759 passed, 28 skipped** | Not repeated |

The Wine oracle stops at the fixture's authored `INT3`, reads the counter as **7**, writes and reads back **41**, sets the trap flag, then checks that one five-byte instruction advances RIP from `0x1400014dd` to `0x1400014e2` and leaves **EAX = `0x12345678`**. The target subsequently increments the edited counter to **42** and exits 0. A target exit code alone cannot pass the oracle.

This qualifies `CreateProcessA(DEBUG_ONLY_THIS_PROCESS)`, debug-event continuation, target memory read/write, thread context read/write, and instruction stepping for this self-authored **PE32+ x86-64 console fixture**. It does not qualify insertion/removal of arbitrary software breakpoints, hardware watchpoints, arbitrary Windows games, PE32/WoW64, managed debugging, or a project snapshot importer.

Both guest stacks fail the same seven DOSBox tests while restoring native states with `STATE_FAILED`. Their underlying cause is unresolved; these failures are not attributed to Wine or Rosetta. QEMU additionally misses the existing test's two-second host budget for advancing 1,000 guest milliseconds. Neither DOSBox build/environment is promoted as native-acceptance green. Existing tests and their time limits were retained.

The Mac source-suite run also retained the README's existing Linux ELF fixture/compiler failures: 732 passed, 30 skipped, 2 failed and 23 setup errors. The corresponding Linux source suite above passes with its native Linux compiler.

## Evidence and boundaries

- [Rosetta qualification](evidence/2026-10-23/rosetta/qualification.json), [Wine failure](evidence/2026-10-23/rosetta/wine-fixture-context.jsonl), and [native test report](evidence/2026-10-23/rosetta/dosbox-tests.xml).
- [Full x86-64 qualification](evidence/2026-10-23/tcg/qualification.json), [Wine events and oracle](evidence/2026-10-23/tcg/wine-probe.jsonl), [original-controller control](evidence/2026-10-23/tcg/wine-original-controller.jsonl), and [native test report](evidence/2026-10-23/tcg/dosbox-tests.xml).
- [Actual VM command, timeout and input hashes](evidence/2026-10-23/tcg/vm-result.json). The VM powered itself off, returned its bounded report bundle, and exited 0; the driver correctly exits 1 because required DOSBox tests failed.

The DOSBox ELF SHA-256 is `74f3b4dd5e3e93b23efdc5519ee60423e779140517745c6fb6ed882dcca14f88` in both stacks. The target PE SHA-256 is `f15f40b3014353abc9226b914415065fbdb367c9f74973f62ec82762b4779ed6`. The original controller's SHA-256 is `7810ee8542594676e7aea188c8e689890d775cb68986ded20ea5cf47750b458a` in both stacks. The current controller adds exception logging, requests the registers it uses, and continues loader breakpoints without an unnecessary context request; both controller variants passed in the x86 VM.

The container run had no network, host folder mounts or published ports, used UID 1000, dropped capabilities, and mounted its root read-only. The full-emulation VM has no network device, host folders or display; only its loopback interface is enabled. Its runtime filesystem is an ephemeral RAM filesystem, with unprivileged Wine/DOSBox processes. The VM also changes the Linux kernel, filesystem setup and resource limits, so the comparison does not isolate Rosetta as the sole possible cause of every difference.

No game files, native states or project databases are in the repository evidence. Test databases, Wine prefixes and machine states stayed in guest temporary memory. The image, kernel and compiler caches are local artifacts outside Git and Python packages.

## Reproducing the container experiment

`prepare_context.py` accepts an explicit upstream DOSBox checkout containing commit `029bd65c5dcc7cdc7f2e14e35278620d9707d969` and the unmodified published 0.11.0 wheel. It archives the named commit and copies only named inputs. It checks the wheel and complete layers-patch hashes before preparing a new context.

```bash
python experimental/wine/prepare_context.py \
  --dosbox-source /path/to/dosbox-x-checkout \
  --wheel /path/to/fdisbull-0.11.0-py3-none-any.whl \
  --output .recovery/wine-context
container build --arch amd64 --cpus 4 --memory 6G \
  --file .recovery/wine-context/Containerfile \
  --tag fdisbull-pe-dos-lab:local .recovery/wine-context
container run --detach --arch amd64 --rosetta --network none \
  --read-only --cap-drop ALL --user 1000:1000 --cpus 4 --memory 6G \
  --mount type=tmpfs,target=/work,size=2G,mode=1777 \
  --mount type=tmpfs,target=/tmp,size=1G,mode=1777 \
  --env FDISBULL_HOLD_SECONDS=300 --name fdisbull-wine-check \
  fdisbull-pe-dos-lab:local
```

Check `/work/evidence/exit-codes.json`; do not infer success from the container's running state. The optional extraction window is finite and failures still exit nonzero. The prefix and cache directories are created by the unprivileged user. Collect live tmpfs reports through `container exec ... tar -C /work/evidence -cf - .`; this host's `container cp` could not read the tmpfs path. Stop and delete the specifically named test container afterward.

The base Ubuntu manifest is pinned in `Containerfile`, but apt/PyPI dependency resolution is not a bit-for-bit build lock. Retain the resulting image identity and version receipts. Preflight disk capacity: the compiler cache plus image unpacking exceeded this Mac's initially available space. No existing user files were removed; temporary experiment caches were relocated/trimmed, retaining receipts and a compact VM replay image.

## Reproducing the full x86 VM

Export the disposable container's root filesystem after stopping it. `prepare_tcg.py` builds a Linux initramfs without extracting that filesystem on the host. It omits the large DOSBox source/build tree while retaining the exact tested executable, Wine, MinGW, Python environment and required native tests. It adds an offline PID-1 runner and current probe sources.

```bash
container export --output /path/to/local-rootfs.tar fdisbull-wine-check
python experimental/wine/prepare_tcg.py \
  --rootfs-tar /path/to/local-rootfs.tar --output /path/to/local-initramfs.cpio.gz
python experimental/wine/run_tcg.py \
  --kernel /path/to/verified-x86-64-kernel \
  --initramfs /path/to/local-initramfs.cpio.gz \
  --output .recovery/wine-tcg-check --timeout 600
```

The run uses 8 GiB RAM and two emulated CPUs. `run_tcg.py` enforces the host deadline, reaps its own process, checks the framed evidence size and member allowlist, and retains nonzero native-test results. The guest returns reports over the serial channel and powers off. The kernel used here matches Debian's published [installer SHA-256 manifest](https://deb.debian.org/debian/dists/bookworm/main/installer-amd64/current/images/SHA256SUMS): `d8808aa4ca188560da1e6d749dcb930c87a5fd8b11ebff1f3fa6d728af35203d`. The initramfs follows Linux's documented [CPIO buffer format](https://www.kernel.org/doc/Documentation/early-userspace/buffer-format.txt).

## Integration work still required

The successful Win32 API loop is the foundation for a structured PE session adapter, module/RVA address mapping and persisted observations. The existing [Wine design](../../docs/WINE_DEBUGGER.md) describes that boundary. The DOS-only debugger factory and segmented layer implementation have deliberately not been relabeled as PE support.

Screenshots, coordinate grids, scripts and artifact storage can share frontend behavior once a PE backend supplies real frames, input and stopped-process observations. Reversible RAM code layers need guarded writes, page protection handling and instruction-cache flushing. Execution-only overlays require an execution backend that supplies alternate instruction bytes. A Wine minidump is not a resumable machine state; full VM checkpointing/editing needs its own implementation and verification. Fast-forward and read/write watchpoints likewise need explicit backend capabilities rather than assumed DOSBox parity.
