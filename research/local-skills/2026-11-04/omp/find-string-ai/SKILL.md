---
name: find-string-ai
description: Locate a known string inside the user-mentioned target process or app bundle and explain its provenance, mapped memory region, cross-references, and likely runtime use as a short TellStoryAI-style story. Use for requests like "find this string in memory", "tell me the story of where this text comes from", or debugging macOS/LLDB attach, LaunchServices metadata, bundles, receipts, heap copies, and terminal/session strings. MUST apply debug-ready-ai first for any live process work.
---
# FindStringAI

FindStringAI is a bounded debugging workflow for a known string. It does not stop at "string found"; it classifies the hit and reports the story: source artifact, mapped region, runtime owner, cross-references, and pruned false leads.

Default final output is a short TellStoryAI story, not a long evidence dump. Preserve detailed evidence in target records/handoff files.


## Mandatory readiness gate

Before live memory search, apply `debug-ready-ai`.

- The debugger must attach to the process the user mentioned, not OMP, not the terminal, not a helper, unless that is explicitly the requested target.
- If attach fails, stop this live-debugging path and diagnose why. Do not continue to a memory story as if runtime proof exists.
- Use offline tools (`rz-bin`, `rabin2`, `rizin`, `r2`, `strings`, `nm`, `otool`, `dwarfdump`, `plutil`, `codesign`, logs, receipts/resources) to collect anchors before or alongside attach when they can help.
- Ask whether source code is available when source correlation would materially improve the address/symbol/story.
- Record important addresses, offsets, selectors, symbols, constants, and runtime values in the target-name record before moving between tools.
- Use `debug-decision-tree-ai` for branch control when there is more than one possible provenance story or attach path.
- Keep searches scoped to the attached process, relevant debugging project documents, and source/bundle/resources/logs for that target. Use online references only for APIs or framework behavior that explain a target-scoped hypothesis.
- Treat every string search as independent by default. Do not reuse previous filters, exclusions, target assumptions, or negative results unless the user explicitly asks to continue, compare, or filter.

## Safety defaults

- Preserve originals. For macOS app bundles, copy to `/tmp/<Name>-debug.app` before re-signing.
- Re-sign only the debug copy unless the user explicitly approves modifying the original.
- Prefer adding `com.apple.security.get-task-allow` to debug copies when attach is denied by hardened runtime.
- Cap loops: no infinite restart/search cycles. After three failed hypotheses, reassess.
- Record the decision tree while working; prune branches that are proven unrelated.

## Quick decision tree

1. **Choose and prove the target**
   - Running process if the question is about runtime state.
   - App bundle if the question is about static metadata, receipts, or bundled strings.
   - Session/log artifact only if the string is conversation or terminal history, and label it as offline/static.
   - Verify target name/path/PID. Reject accidental OMP/session/terminal PIDs unless explicitly requested.
2. **Attach or classify attach denial**
   - Try bounded LLDB attach to the exact requested target.
   - Confirm debugger output names the target process/path.
   - If denied, inspect code signing, entitlements, `taskgated`, `debugserver`, and logs.
   - Hardened runtime without `com.apple.security.get-task-allow` means: create/re-sign a local debug copy, or report that the live process cannot be inspected safely.
3. **Search readable memory**
   - Enumerate readable regions with hard caps.
   - Skip huge regions unless deliberately searching shared cache / mapped databases.
   - Search UTF-8/ASCII first; add UTF-16 only when needed.
   - Do not add prior-search exclusions such as `3.7.0`/`7.3.0` unless the user asked for that filter in this search.
4. **Classify each hit**
   - Code image / `__cstring` / ObjC metadata.
   - Mapped file, especially LaunchServices `.csstore`, receipts, SQLite, mmap cache.
   - Heap copy.
   - Environment / argv / terminal scrollback / agent session transcript.
   - Framework / dyld shared cache.
   - For code-image hits, immediately enrich with `image lookup --address <addr>` and `memory region <addr>` to identify section, module-relative address, and permissions.
5. **Cross-reference statically**
   - `rz-bin`, `rabin2`, `rizin`, `r2`, `Info.plist`, receipts, localized resources, executable strings, symbols/selectors, logs/session JSONL.
   - If an executable has the key but not the value, treat it as code that queries metadata rather than hardcoding the literal.
   - For executable/string-table hits, correlate the runtime address with a static executable byte offset or `strings -a` line when possible; record both runtime address and file offset.
   - For universal Mach-O binaries, note which architecture slice is being inspected and verify reusable file offsets with a raw byte search when tool offset semantics differ.
   - Preserve API call names, function names, selectors, symbol names, and nearby constants; they are often the quickest clues for why a string exists.
6. **Tell the story**
   - Use `tell-story-ai` for the final explanation.
   - Answer What / Where / Why-role in simple language.
   - Include the larger containing string or nearby UI/API context when available.
   - Include only the strongest evidence in the user-visible answer: address/section or source file, one call/API/function clue if useful, and confidence.
   - Update the target record with any address, file offset, symbol, selector, or value that may help cross-correlate later.

## LLDB scanner

Use `scripts/find_string_ai.py` as an LLDB command script when built-in `memory find` is too narrow.

Example:

```sh
lldb -b \
  -o 'process attach --pid <PID>' \
  -o 'command script import /Users/tiga/.codex/skills/find-string-ai/scripts/find_string_ai.py' \
  -o 'findstringai "needle text" 20' \
  -o detach \
  -o quit
```

The script returns JSON containing:

- `needle`
- `hits[]`: address, region bounds, permissions, region name, Latin-1 context
- `hit_count`
- `readable_regions_considered`
- `skipped_large_regions`
- `regions_seen`
- `bytes_scanned`
- configured caps

Default caps:

- region size: 256 MiB
- total scan: 3 GiB
- chunk size: 1 MiB
- max hits: argument, default 20

## macOS hardened-runtime branch

Attach denial shape:

```text
attach failed (Not allowed to attach to process...)
```

Checks:

```sh
codesign -d --entitlements - <binary>
codesign -dvvv <binary>
log show --last 3m --predicate 'eventMessage CONTAINS[c] "Not allowed to attach" OR eventMessage CONTAINS[c] "task_for_pid" OR eventMessage CONTAINS[c] "debugserver"' --style compact
```

If the target is an App Store-style/hardened app and lacks `com.apple.security.get-task-allow`, do not keep retrying. Re-sign a local copy if allowed:

```sh
ditto /Applications/App.app /tmp/App-debug.app
codesign --force --deep --sign - --options runtime --entitlements /tmp/debug.entitlements /tmp/App-debug.app
```

Minimal entitlement:

```xml
<plist version="1.0">
<dict>
  <key>com.apple.security.get-task-allow</key><true/>
  <key>com.apple.security.cs.disable-library-validation</key><true/>
</dict>
</plist>
```

## Story patterns from known runs

### `3.7.0` in NotepadX

- Live original attach denied: hardened app lacked `get-task-allow`.
- Debug copy was re-signed under `/tmp/NotepadX-debug.app`.
- Memory hit: LaunchServices `.csstore` mapped into the process, grouped with `net.notepadx.editor`, `CFBundleShortVersionString`, icon, bundle version, and usage strings.
- Static source: `Contents/Info.plist` had `CFBundleShortVersionString = 3.7.0`; receipt also embedded it; executable referenced metadata keys but did not hardcode the value.
- Story: app-version metadata, not business logic.

### target string `curated fallback chain` in OMP session

- `curated fallback chain` is a target string, not a skill name.
- Live OMP attach was denied on the current session process.
- Static search found the phrase in the active OMP session transcript as the user prompt, not as a product code string.
- Related docs contain model fallback-chain behavior, but not the exact phrase.
- Story: phrase is session/conversation provenance unless a separate target process or bundle also contains it.
- If the user wants runtime proof in OMP memory, inspect a debuggable OMP process launched with suitable signing/permissions or analyze the session JSONL artifact directly.

## Reporting template

```text
Target:
- process/app/artifact

Hit summary:
- address/path/line
- region or file type
- context

Provenance:
- authoritative source
- runtime copy path
- cross-references

Pruned:
- unrelated env/session/framework hits
- failed hypotheses and why

Decision:
- what the string is for
- what it is not
- next safe action if deeper proof is needed
```
