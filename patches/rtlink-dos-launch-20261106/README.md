# RTLink and DOS launch source delivery

**Integration handoff only. These patch files are not applied to this branch.**
Merging this directory as-is will not add RTLink commands, change DOS launching,
or install the new skill reference. Keep the MR in draft until the code has
been deliberately applied, reviewed and tested on the intended target.

Origin: `chat:westwood-kyra-intake/task:rtlink-dos-launch-20261106`

The complete authored change was tested on source
`c80bff03e4cd2b946a93e7aecab61e5ff9281f81`. This delivery branch starts from
`release/0.33.0` at `bdd096f963f2c125e70e7f52ae944b662dd89f6f` and leaves all
existing runtime, release and skill files untouched. The two source identities
must not be treated as equivalent test baselines.

## Reconstruct and review

The five numbered parts are consecutive portions of one unified patch, split
only at file boundaries. Together they contain all fourteen intended file
changes, not a series requiring five successive source versions.

From this directory:

```sh
sha256sum -c SHA256SUMS
cat 01-docs-and-cli.patch 02-dos-launch.patch 03-rtlink-reader.patch \
  04-agent-skill.patch 05-regression-tests.patch > /private/rtlink-dos-launch.patch
sha256sum /private/rtlink-dos-launch.patch
```

The combined patch is 69,703 bytes with SHA-256:

```text
c64385fef524f14ec39a8284e02f9eaa32303e22caf140728d91ec8f9a1cfc14
```

Use an isolated current-target worktree. Read its current `AGENTS.md` and
`docs/AGENT_HANDOFF.md`; check `git status` and the exact target head. Run
`git apply --check /private/rtlink-dos-launch.patch` before applying anything.
Where context has changed, port the narrow hunks manually and preserve the
intervening CLI, debugger, capability and skill work. Do not overwrite current
files with older postimages, force-apply rejected hunks, or substitute a passing
old-source result for combined-tree validation. Record the resulting new SHA.

## Intended behavior after application

- Bounded embedded RTLink/Plus v2 inspection, separate private unrelocated
  exports and candidate x86-16 disassembly through CLI, JSON and Python APIs.
- Explicit DOS argument tokens and one validated, read-only Mode-1 CD image.
- CUE-style INS descriptors and normalized one/two-digit TRACK/INDEX numbers.
- Detailed installed DOS-format guidance, source identity and launch diagnosis.
- Authored parser/rejection fixtures and optional real DOSBox launch tests.

This is not universal RTLink support, a runnable flattened EXE, arbitrary
shell execution or a generic disc player. External OVL and other RTLink
profiles remain unsupported. Audio/mixed-mode CD and native CD checkpoint
capture/restore are explicitly outside the qualified launch profile. Review
format-reference attribution and licensing before public release.

## Required integration gates

After applying the actual code, run the selected regression suite from that
worktree and select a compatible real DOSBox agent for the native cases:

```sh
PYTHONPATH=src:tests python -m pytest -q \
  tests/test_rtlink.py tests/test_dos_media_launch.py \
  tests/test_cue.py tests/test_disc.py tests/test_dos_launch.py \
  tests/test_dos_com.py tests/test_dos_loader.py tests/test_dos_inspection.py \
  tests/test_agent_skill_gate.py tests/test_agent_discovery.py tests/test_debugger.py
```

Set `FDISBULL_DOSBOX` to the explicit compatible backend for real execution;
skipped native cases are not native passes. Preserve original target inputs
outside the checkout. Build and test the installed artifact, verify method and
capability discovery and both installed skills, and run the release owner's
exact-source packaging/privacy and required-native gates. Existing earlier
receipts remain separately attributed. Do not start hosted CI, merge, tag,
publish, change a shared installation or trigger another agent as a side effect.

The submission's test scope and outstanding work are in its MR description.
Sanitized reports remain separate originating-chat attachments. No game data,
extracted overlays, emulator binaries, saves or byte-retaining databases belong
in this source delivery.
