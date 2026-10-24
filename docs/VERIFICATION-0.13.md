# 0.13.0 verification gates

Version 0.13.0 promotes the PE64 watches/layers/native-state work described in the [release notes](RELEASE-0.13.0.md). Tagging is gated on successful **ordinary Linux/package CI and all native debugger CI jobs on the exact candidate commit**. A workflow definition or local pass does not establish a GitHub CI result.

The required workflows are [Tests and tool packages](https://github.com/seeker-cyber-maker/fDisBull/actions/workflows/ci.yml) and [Native debugger acceptance](https://github.com/seeker-cyber-maker/fDisBull/actions/workflows/native-debugger.yml). The latter builds the pinned stable DOS backend, layers DOS backend and QEMU/Wine runtime, then requires actual native acceptance. Its PE job runs `test_wine_debugger.py` and `test_wine_advanced.py` against an installed release wheel with `FDISBULL_REQUIRE_PE=1`. Runtime images, states, compiled fixtures and databases are not uploaded as verification artifacts.

CI produces exact source/wheel/backend identities, test logs/JUnit and authored screenshots/traces. The ordinary job audits the wheel, sdist and tool ZIP. Before tagging, inspect each job's completed success, read its test counts and package/backend identities, audit downloaded package contents, and compare the PE-tested wheel's entry contents with the package-job wheel. An annotated tag records the exact accepted commit and CI run URLs. Publishing a GitHub release or replacing the DeepSeek delivery is a separate action.

## Preserved local development evidence

The [development record](PE64_ADVANCED_VERIFICATION.md) and its [hash-bound receipt](../experimental/wine/evidence/2026-10-24/pe-advanced/verification.json) preserve the earlier `0.13.0.dev0` builds without rewriting their identities or then-uncommitted status:

| Gate | Recorded result |
| --- | --- |
| Full installed-wheel PE gate | 12 passed, no skips |
| Asset-aware native follow-up | 6 passed, no skips |
| Final installed-wheel unit checks | 10 passed; three native cases deliberately deselected |
| Shared DOS native regression | 45 passed |
| Full ordinary Linux source suite in QEMU | 769 passed, 31 skipped, no failures/errors |

The authored PE program's RAM layer made its self-CRC fail; an execution layer changed behavior while preserving source RAM and a passing self-CRC. A native child restored counter 51 and RAX `0x123456789abcdef0` after project/VM restart, resumed to 54 with the saved execution layer and to 55 after disabling it, then restored the immutable parent at 17. Original EXE bytes and separate static versions remained intact. Selected clean/grid screenshots, data-watch stops and completed-instruction traces are included as evidence, with no game or state payloads.

Earlier failed test setup/reporting gates remain separately recorded. The broad Mac suite has pre-existing Linux ELF fixture compiler/linker failures, so a complete green macOS suite is not claimed. Native Mac-host Wine/QEMU/DOS results and the full Linux source result are distinct qualifications. The final release CI additionally tests the bumped 0.13.0 version and full combined source; development receipts do not substitute for that gate.

See [PE runtime limits](WINE_DEBUGGER.md#pe64-watches-layers-and-native-states-0130) for guard-page/scalar access restrictions, relocated execution overhead, native-state sidecar requirements and the bounded authored-fixture claim ceiling.
