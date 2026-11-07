# macOS OMP / LLVM / LLDB Attach Issue Cache

Updated: 2026-07-04

Use this as a preflight checklist when `debug-ready-ai` fails on macOS or when OMP/LLVM/LLDB behavior is suspicious. This file is a hypothesis cache, not proof. Confirm against the target with current commands/logs.

## Known local baseline

- Host: macOS/Darwin arm64.
- Apple LLDB: `/usr/bin/lldb` and `/Library/Developer/CommandLineTools/usr/bin/lldb-dap`.
- Homebrew LLVM: `/opt/homebrew/opt/llvm`.
- Homebrew `lldb` and `lldb-dap`: `/opt/homebrew/opt/llvm/bin/lldb`, `/opt/homebrew/opt/llvm/bin/lldb-dap`.
- Homebrew LLVM is keg-only; prefer explicit paths or PATH entries, not `brew link --force llvm`.
- Useful shell exports already recorded in defaults:
  - `LLVM_HOME=/opt/homebrew/opt/llvm`
  - `PATH=/opt/homebrew/opt/llvm/bin:$PATH`
  - `CMAKE_PREFIX_PATH=/opt/homebrew/opt/llvm:...`

## Attach failure branches

### Wrong target / accidental OMP attach

Symptoms:

- PID belongs to `omp`, shell, terminal, or helper rather than the user-mentioned app/process.
- Memory search finds session prompts, environment variables, or terminal content instead of target data.

Action:

- Stop. Re-identify target by name/path/PID.
- Ask if ambiguous.
- Do not claim runtime evidence for the requested process.

### Hardened runtime without `get-task-allow`

Symptoms:

```text
attach failed (Not allowed to attach to process...)
```

Evidence commands:

```sh
codesign -d --entitlements - <binary>
codesign -dvvv <binary>
log show --last 3m --predicate 'eventMessage CONTAINS[c] "Not allowed to attach" OR eventMessage CONTAINS[c] "task_for_pid" OR eventMessage CONTAINS[c] "debugserver"' --style compact
```

Action:

- Prefer re-signing a disposable local debug copy under `/tmp/<AppName>-debug.app` with `com.apple.security.get-task-allow = true`.
- Preserve the original app/binary. Never re-sign `/Applications/...` in place.
- Record the copied bundle path, temporary entitlements plist, signing command shape, launched PID, attach smoke evidence, and cleanup status.
- Ask before using `sudo`, altering originals, disabling system security controls, changing TCC databases, or touching production app data.

Minimal `/tmp` debug-copy recipe:

```sh
ditto "/Applications/Target.app" "/tmp/Target-debug.app"
codesign -d --entitlements :- "/Applications/Target.app" > /tmp/target-debug.entitlements 2>/dev/null || printf '%s\n' '<?xml version="1.0" encoding="UTF-8"?><plist version="1.0"><dict/></plist>' > /tmp/target-debug.entitlements
/usr/libexec/PlistBuddy -c 'Set :com.apple.security.get-task-allow true' /tmp/target-debug.entitlements 2>/dev/null || /usr/libexec/PlistBuddy -c 'Add :com.apple.security.get-task-allow bool true' /tmp/target-debug.entitlements
codesign --force --deep --sign - --entitlements /tmp/target-debug.entitlements "/tmp/Target-debug.app"
open -n "/tmp/Target-debug.app"
```

Use app-specific names/paths. Use `--deep` only on the disposable copy, because it can rewrite nested signatures.

### Initial dyld stop is not failure

Symptoms:

- DAP/LLDB launch stops at `_dyld_start` or reports a stop reason immediately after launch.

Action:

- Treat as normal launch stop unless evidence says otherwise.
- Continue or send `configurationDone` before declaring launch failed.

### Homebrew `lldb-dap` not discoverable by OMP/session PATH

Symptoms:

- `lldb-dap` works by absolute path but not via default PATH.
- Existing terminal session predates PATH/profile changes.

Action:

- Use explicit adapter path if possible: `/opt/homebrew/opt/llvm/bin/lldb-dap`.
- Restart shell/OMP session or source profile changes.
- Do not force-link keg-only LLVM unless explicitly chosen.

### TCC / Developer Tools confusion

Observed local evidence:

- TCC DB may show no DeveloperTool rows even when Apple `debugserver` works.
- `_developer` group membership and signed debugger entitlements matter, but absence of a popup is not proof of failure.

Action:

- Prefer direct attach error, `codesign`, `log show`, and `debugserver` logs over guessing from TCC alone.

## Offline anchor tools

Use these before expensive live debugging when applicable:

```sh
strings -a <binary-or-resource>
nm -m <binary>
otool -l <binary>
otool -Iv <binary>
dwarfdump --uuid <binary>
plutil -p <plist>
codesign -dvvv <binary>
codesign -d --entitlements - <binary>
atos -o <binary> -arch arm64 <address>
```

Record useful addresses, file offsets, symbols, selectors, constants, and values in:

```text
~/Documents/Codex_Projects/omp-agent-defaults/debug-target-records.md
```

## Online reference rule

Use web/API reference only to support a hypothesis when local evidence is unclear. Examples:

- framework API that reads a plist value,
- LLDB/DAP behavior,
- dyld or hardened-runtime behavior,
- calling convention / ABI details,
- library function semantics.

Do not search the wider internet for target strings unless the user asks or the target's own source/project docs are online and relevant.
