# 0.14.0 source and package preflight

This pre-commit receipt identifies the 0.14.0 sources and locally audited tool
packages. It is not a hosted CI result or a publication receipt. The installed
0.14.0 wheel passed 50 checks with 10 optional runtime skips, including actual
QEMU boot control, with the imported package path checked and pytest source
insertion disabled. Source/config whitespace and Actions workflow validation
passed. Earlier raw test reports retain their original bytes.

The release commit must pass ordinary Linux CI and native Linux acceptance
before `v0.14.0` is created. Native acceptance now builds both pinned DOSBox
profiles, exercises the DOS binary endpoint, prepares Linux DOS/Wine runtimes,
and runs actual DOS-in-QEMU, boot and custom Wine cases on the installed wheel.
No game, saved state, database, runtime image, vendor executable or key is
included. Existing sealed local evidence and unrelated TAKEOVER.md are preserved.
