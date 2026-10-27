# fDisBull 0.19.0 — shared Mac installation

Installed source: `57824bd9a06c7f25f6a25172b3f4dcb4dfcfdc95`, tag `v0.19.0`.
The selector `/Users/Shared/fDisBull/current` chooses the active version. Global
commands in `/usr/local/bin` and Homebrew's bin directory follow that selector.

Use `fdisbull --version`, `fdisbull --help`, `fdisbull agent-skill` and
`fdisbull-runtime` to inspect the active package and launch profiles.
`fdisbull-python` is the managed interpreter for API scripts; project-specific
PYTHONPATH is cleared. Existing project/Conda environments are preserved.
`fdisbull-dosbox` selects native Mac DOSBox; `fdisbull-qemu` selects copied QEMU
with matching firmware. RUNTIME.json contains version-bound DOS, DOS-in-QEMU,
Wine/QEMU and raw-machine profiles.

0.19.0 adds guarded DOS filename aliases, persistent screenshot pre/post policies,
callback-safe DOSBox continuation, stop-race handling and expanded bundled skill
references. Screenshot hooks and scene probes currently support direct DOSBox.
Frame freshness alone does not establish readiness. C/C++ decompilation, UIL
engines and semantic navigation remain unimplemented proposals.

The previous 0.18.0 prefix remains at
`/Users/Shared/fDisBull/releases/0.18.0-416b64d`. Retain its backend for native
checkpoints bound to that executable identity. New commands select the active
prefix; existing processes and private projects are not migrated or terminated.
The guarded `share/rollback-to-0.18.py` script can atomically select the previous
prefix if 0.19.0 is still the active version.

Keep game files, saved games, native states and project databases outside this
installation. Included boot filesystems are audited pristine OS/runtime inputs,
not captured sessions. Mac executables use existing Homebrew libraries; this
installation is qualified on this Mac, not advertised as arbitrary-host portable.
No vendor IDA servers/keys or new DeepSeek delivery is included.

Verify the sealed payload with:
`fdisbull-python /Users/Shared/fDisBull/current/share/verify-system.py`.

This tool is not currently suitable for malware analysis or security work.
Must bring your own weapons. I have only done this once before. Safety not guaranteed.

The [0.19.0 GitHub release](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.19.0) is published. Its five assets
passed download readback; identities are retained under share/verification.
