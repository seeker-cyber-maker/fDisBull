---
name: explain-button-ai
description: Trace a visible app button or menu item from label string to UI construction, action thunk, dispatch path, protection/licensing relation graph, and likely behavior, then explain it as a short evidence-backed story. Use when debugging a button label, SwiftUI/AppKit/UIKit menu action, Electron/web UI control, "what does this button do", button string provenance, click-path tracing, protection-related function inter-relations, Mermaid/JSON graph output for a UI/protection flow, or when the user asks to investigate functions leading to a UI control; combine with debug-ready-ai before live LLDB/DAP work.
---
# ExplainButtonAI

ExplainButtonAI turns a button or menu item into a maintainer-readable story: **what text the user sees, where the app builds the control, what action fires, which functions receive it, and what the first-level behavior likely is.**

Use it for macOS/iOS apps, Electron/web UIs, and source-free binaries when the target is a visible button, menu item, toolbar item, context-menu action, or command palette entry.

## Operating rules

- Start from the user-visible thing: exact label string, screenshot/vision coordinates, accessibility name, menu path, or nearby UI text.
- Ground every role claim in evidence: source, resource file, string table, symbol/selector, disassembly xref, breakpoint, register value, accessibility tree, or observed UI state.
- Prefer a live trace when safe. If live attach is needed, apply `debug-ready-ai` first.
- On macOS attach denial for a hardened app, default to a disposable `/tmp/<App>-debug.app` copy with `com.apple.security.get-task-allow`; never re-sign the original app unless explicitly approved.
- Preserve debugger continuity. Keep one LLDB/DAP attachment alive across label lookup, breakpoints, register checks, and first-level function tracing when possible. If useful, assign one focused subagent to own the long-lived LLDB session and report anchors instead of splitting debugger state across workers.
- If clicking is needed, first try to generate the click yourself: accessibility action, browser automation, AppleScript, CGEvent/coordinates, or coordinates from a screenshot/vision pass. If the control is hidden, scroll/open menus/navigate first. Ask the user only when clicking would be risky, stateful, destructive, credential-gated, or too complex to automate safely.
- Before any stateful click, prove breakpoints are slide-correct. In LLDB, get the image slide with `image list -o -f`, add it to static Mach-O addresses, set breakpoints at loaded addresses, then confirm `breakpoint list` shows resolved locations in the target image. A stale slide can let the click run without stopping.
- If the answer is high-confidence and non-destructive, accept it yourself and present the story. Ask for acceptance only when the next step changes app state, network/tunnel state, files, credentials, security policy, or user data.

## Workflow

1. **Identify the control**
   - Capture label, accessibility name, window/menu context, and target app/process/bundle.
   - If visible UI is needed, use browser/DevTools/a11y tools for web/Electron or screenshot + vision/coordinates for native apps.
   - Record whether the control may trigger external state, network calls, tunnels, purchases, deletes, or credentials.
   - Before assuming SwiftUI/AppKit/UIKit internals, classify the app stack from `Info.plist`, bundle layout, executable name, frameworks, resources, and running processes. Electron/web apps usually expose `Electron Framework`, `app.asar`, `dist/assets`, renderer/helper processes, local backend ports, and optional Chrome DevTools/CDP; inspect those first, then fall back to native Swift/ObjC/Mach-O tracing when the target is native or the web bundle is not enough.

2. **Find label provenance**
   - Search localized resources, metadata, string tables, source, accessibility labels, nib/storyboard files, SwiftUI text builders, AppIntents metadata, ObjC selectors, and binary strings.
   - For source-free Mach-O work, use offline anchors first: `rabin2`, `rz-bin`, `rizin/r2`, `strings`, `nm`, `otool`, `plutil`, `codesign`.
   - Keep exact addresses, offsets, function names, selectors, and nearby strings in the target record.

3. **Map UI construction**
   - Find where the control is created: e.g. SwiftUI `Button(action:label:)`, AppKit target/action, UIKit `addTarget`, web `onClick`, command registration, menu builder, or intent metadata.
   - Separate label construction from action construction. A label helper often chooses `Connect` vs `Disconnect`; the action thunk may be nearby but distinct.
   - Distinguish visually similar controls. An app menu item, menu-bar extra, status-menu item, toolbar button, and SwiftUI view button can share the same label but use different action thunks. If runtime proof uses an alternate accessible control, say so and only claim convergence at functions actually hit.

4. **Trace closest behavior first**
   - Start with the closest action target/thunk/callback and explain that function before walking backward or outward.
   - For each function, classify:
     - **Role**: label builder, button constructor, action thunk, shared dispatcher, state guard, model lookup, command launcher, callback, network/process boundary.
     - **Inputs**: flag/register/argument/object captured by closure.
     - **Outputs/effects**: callback call, state mutation, async task, XPC/process launch, network/tunnel action, UI state change.
     - **Confidence**: live-confirmed, static-only, likely, blocked.
   - Move outward in rings: action callback -> shared dispatcher -> state/model function -> service/XPC/network/process boundary. Stop when the behavior story is useful or the next ring would require risky state changes.

5. **Live proof when safe**
   - After `debug-ready-ai` passes, set breakpoints on the button constructor, action thunk, shared dispatcher, and closest callback.
   - Click or trigger the control with automation when safe; otherwise ask the user to click while the debugger stays attached.
   - If the control can affect network/tunnel/process state, prefer stopping at the first safe downstream function that proves intent (selected model/session/UUID/state gate) before the launcher/XPC/network boundary. Do not continue merely to get a deeper stack unless that is the requested win condition.
   - After triggering, immediately check `breakpoint list` hit counts and the stopped stack. If expected breakpoints did not hit, assume the address, slide, or control path is wrong; restore app state if needed before retrying.
   - Capture minimal evidence: breakpoint hit, thread/function, key register/argument values, selected branch, and any state guard result.
   - Do not execute destructive/stateful actions merely to prove a story; use disabled/offline/safe fixtures if available.
   - When a re-signed debug copy blocks during launch on licensing/keychain/purchase frameworks, pause and inspect the stack. A safe debugger return from a nonessential lookup can unblock UI initialization for tracing, but record it as a test-only bypass and do not hide it in the final story.

6. **Tell the button story**
   - Use `tell-story-ai` style: short, exact, evidence-backed.
   - Include caveats: live-confirmed vs static-only, no-click/no-side-effect if applicable, attach/re-sign path used, and next safe branch.

7. **Graph relationships when requested**
   - When the user asks for a graph, map, mind map, Mermaid, JSON, or inter-relations, produce both:
     - a machine-readable JSON file with `nodes[]`, `edges[]`, `clusters[]`, evidence paths, and relationship labels;
     - a Mermaid Markdown file using `flowchart LR` or `flowchart TD`.
   - Keep graph nodes semantic, not just raw functions: UI control, frontend API method, backend route, manager method, persistent setting, cache, external service, feature gate, duplicated bundle/job copy.
   - Keep graph edges typed: `calls`, `reads`, `writes`, `clears`, `HTTP GET`, `HTTP POST`, `fallback`, `sets cache`, `duplicates`, `requires true`.
   - Verify the JSON parses and report node/edge counts. Avoid graph artifacts that encode bypass instructions; map protection relationships for review/hardening.

## Output shape

```text
Story: <plain-language explanation of the button>
What: <exact label/accessibility name/control type>
Where: <app/window/menu/resource/function/address>
Path: <label builder -> button constructor -> action thunk -> closest behavior function>
First-level behavior: <what the closest function does or likely dispatches to>
Confidence: <confirmed | static-only | likely | blocked> because <one sentence of evidence>
Next: <only if deeper tracing is useful or user action is required>
```

Use visible debugging labels when helpful:

- Positive: confirmed useful evidence.
- Blocked: missing live proof, attach denial, or unsafe click/state transition.
- Next: current branch or safe next action.

## Core Tunnel pattern example

For Core Tunnel's `Connect` button, the saved static path was:

```text
label/helper: sym.func.100179710 called with w0 = 1
button construction: sym.func.100176b04 -> SwiftUI Button(action:label:) near 0x100177f74
action thunk: sym.func.100179db8
shared dispatch: sym.func.100179dc4 -> sym.func.100179b38 -> sym.func.100112c60(arg0, flag)
closest callback candidate: sym.func.10016d5fc
```

Story pattern:

```text
The `Connect` label is Core Tunnel's own SwiftUI UI copy. The app builds the label through a Connect/Disconnect helper, then wires the visible button to an action thunk that enters a shared dispatcher and selects the Connect callback. Confidence is static-only until a re-signed debug copy is attached and the click path hits these breakpoints.
```

Live-runtime lesson from the same target:

```text
The accessible app menu path `Tunnel -> Connect` did not hit the earlier status/button thunk candidates. With corrected slide `0x6bc000`, it hit SwiftUI/AppKit menu plumbing and stopped at `sym.func.10016a7b8`, the session lookup/create helper, with `Foundation.UUID` metadata in registers. Tell the story as: menu Connect is live-confirmed to resolve selected profiles into tunnel sessions before the XPC launcher; exact status-bar button equivalence remains a separate proof unless that exact control is triggered.
```

## Relationship to other skills

- Use `debug-ready-ai` before live LLDB/DAP, memory, breakpoint, register, or click-path claims.
- Use `debug-decision-tree-ai` when there are multiple candidate functions or attach/click branches.
- Use `find-string-ai` when the starting point is only a string and not yet tied to a control.
- Use `tell-story-ai` for the final user-facing explanation.
- Use `vision-magic-see-thingy` or browser/a11y tooling when the control must be located visually before automation.
