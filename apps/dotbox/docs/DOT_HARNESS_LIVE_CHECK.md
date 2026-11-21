# Live Dot computer input check

This check uses Dot's existing little computer and its existing Codex/WebRTC
viewer. It creates no replacement desktop, new cloud environment, account,
transport, ownership API, audio or game feature. Do not use private client
endpoints or copy credentials. Existing user documents stay untouched.

## Brief to run in Dot's existing chat

Please verify keyboard/mouse and the existing Take over / Return control flow
on your own current cloud computer. Use only the documented tools actually
available in your context. Do not substitute the user's Mac or a new cloud task.

1. Identify the desktop/browser tools you have. If an environment-status tool is
   offered, record its environment identity. Report missing tools without
   guessing commands or collecting secrets/private connection URLs.
2. Open a new untitled plain-text editor document on that same desktop. Generate
   a fresh non-sensitive nonce. Use ordinary desktop keyboard/mouse input to
   type `DOTBOX-AGENT-A <nonce>`. Observe the rendered text and record the tool
   used. DOM assignment, clipboard-only state or shell writes are not proof of
   keyboard capture.
3. Ask me to click the viewer's existing **Take over** button. While I own it,
   refrain from agent input. I will click within the editor, move the caret and
   type `DOTBOX-HUMAN <nonce>`. Record any supported ownership notification or
   input-refusal status; if none is exposed, say API detection is unknown.
   Focus, video motion and missing input are not ownership evidence.
4. Ask me to click **Return control**. Inspect the same document. Once the
   harness permits your desktop input again, move the caret with the mouse and
   type `DOTBOX-AGENT-B <nonce>`. Observe all three markers in that document.
5. Record UTC/monotonic request and observation times where available, including
   failed attempts, disconnects, retries and gaps. Distinguish the UI owner
   label, actual accepted keyboard/mouse effects, and an API/event reporting
   owner. Do not call a local viewer-mode acknowledgement a whole-computer lease.
6. Return a compact receipt: actual environment/tool identities; input methods;
   observed markers/caret changes; user takeover/return confirmations; any
   ownership field/event and its source; failures; and unresolved questions.
   Keep raw screenshots, connection information and transcripts private.

A successful round trip verifies this input path on this computer only. It does
not establish a supported ownership subscription for a guest process or general
unattended triggering. A failed takeover must retain the original environment
and be reported rather than repaired by restarting/replacing the computer.

## Completed web-viewer check — 16 November 2026

Initially this local chat had no attached Dot cloud desktop tool, and native
Codex-app access was refused. The user then supplied the existing Dot chat in
the side browser and authorized coordination with it. The allowed web viewer
provided access to the same existing computer. Native-app access stayed unused.

The executed sequence was narrower than the proposed editor protocol above:

1. The coordinator read the viewer's Dot-control label and unchecked Take over.
   Browser automation clicked Take over and read `You have control` / checked
   Return control. A remote address-bar click and individual desktop key events
   produced `dotbox` visibly; Enter was never pressed.
2. Return control restored the Dot-control label and unchecked Take over. Dot
   reported desktop input through `cua_repl.js`, `cua.getApp`, `app.click`,
   `app.pressKey` and `app.typeCharacters` (23 characters). On request she left
   `dotbox-agent-b-20261116` visible. The coordinator independently captured that
   marker through the same viewer while Dot had control.
3. The coordinator took over again and clicked Chromium's new-tab plus. A second
   empty tab visibly appeared, independently demonstrating pointer delivery.
   The coordinator closed only that newly created tab and sent two Escapes to
   restore the original empty address bar. Final capture shows one original tab,
   an empty address bar, Dot control and unchecked Take over. Dot received an
   acknowledgement that the bounded check and cleanup were complete.

The first cleanup attempt used one Escape; Dot observed that it closed the
suggestions but retained the marker. The later two-Escape cleanup was visibly
verified. No test marker was submitted as a search or navigation.

This verifies viewer-side UI detection/triggering, keyboard and distinct mouse
effects, and accepted agent-side input after return. Exact agent tool calls are
agent-reported; their resulting marker was independently observed. Dot reported
no ownership field/event in her tool interface, so guest API detection remains
unestablished. There was no agent-A editor marker, deliberate simultaneous input
attempt, automatic pause/resume test, unattended switching, or transition-latency
measurement. Recorded UTC observation points contain model/coordination gaps.
The viewer-side actor was the authorized coordinator using browser automation.

The [sanitized report](evidence/codex-viewer-2026-11-16.json) retains private
evidence hashes. Raw chats, screenshots, connection/environment IDs and app
source stay outside Git. The current web build was not identity-bound to the
inspected installed macOS app. This does not qualify a native DotBox cloud
installation. Audio and gameplay remain deferred.
