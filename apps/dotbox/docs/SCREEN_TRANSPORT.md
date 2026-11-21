> Current inspection: [16 November code and live-viewer analysis](CODEX_VIEWER_CODE_ANALYSIS.md).

> Preserved investigation from 14 November 2026. This is historical static
> client evidence, not a current live harness integration test. The standalone
> engine uses the ordinary desktop input path and leaves platform ownership
> unknown; it does not subscribe to these internal events.

# Screen transport and takeover signals

Static installed-client inspection, 14 November 2026. This answers how the
shipped viewer is implemented; it does not observe a live connection or expose
a supported API for DotBox to consume.

## Finding

The inspected client contains **both WebRTC and a noVNC-labelled viewer path**.
The Dot shared-computer viewer code uses a WebRTC peer connection with a video
track and a separate data channel. That data channel carries keyboard/mouse
input and explicit control-owner messages. Ownership is not inferred from the
video image.

The inspected Dot UI wiring labels its expanded viewer transport as WebRTC.
An alternate Work cloud-browser path obtains a `novnc_url` and displays it in
an iframe. This is sufficient to distinguish two shipped client paths; it does
not establish which transport every account, platform or live session selects.
The contents of the externally served noVNC iframe were not inspected, so its
underlying RFB/WebSocket implementation is not independently established here.

## Exact artifact and method

- Installed app: `/Applications/ChatGPT.app`, bundle `com.openai.codex`.
- App version: `26.1106.51428`; build: `26605`.
- Artifact: `Contents/Resources/app.asar`, 773,079,866 bytes.
- Artifact SHA-256:
  `3695c17edcab8d66c1e5f2faa03e07826a59a39bf78b369ec87854547d4843c1`.
- ASAR inventory: 19,995 members; packed data starts at byte 5,391,412.

Method: format-aware **static shell inspection**, not REA-generated Evidence.
No REA tools or installed `rea` CLI were available in this task. The ASAR header
was parsed, renderer/bootstrap JavaScript members were searched for narrow
transport/control terms, and selected candidate members were read by their
recorded ranges and hashed. No whole-application semantic graph was constructed.
No app UI, credential store, browser profile or private database was inspected;
no authenticated traffic was intercepted and no internal endpoint was called.
Selected source copies remain in ignored private scratch storage, not public
DotBox source files.

## Source-bound observations

All member names below are under `webview/assets/async/`. Offsets are zero-based
UTF-8 byte offsets within the minified member, not line numbers or ASAR offsets.

| Member and byte offset | Static observation |
| --- | --- |
| `832390.1e72e335e6.js`, 19,296-21,204 | Creates `RTCPeerConnection`, adds audio/video transceivers, creates a data channel, receives a video stream through `ontrack`, and negotiates SDP. This is the cloud-computer client path, not an inference from a generic WebRTC dependency. |
| Same member, 11,331 onward | Has explicit observe/control modes. Input sending is gated on control mode and an open data channel. Pointer/key events use binary messages; control/clipboard operations have explicit JSON messages. |
| Same member, 17,362-18,700 | Handles `control/locked`, `control/release`, `system/init` and `control/host`. Shared takeover requests are correlated with request IDs and peer identity. |
| Same member, 18,238 onward | `_reportControlHost` consumes `has_host` and owner metadata and emits `controlowner`: a human owner when a host is present, a Dot owner otherwise. Unknown/replaced peer state can reset the owner to null. |
| Same member, 21,204 onward | Sends `control/request` and `control/release`; shared requests include `shared_dot_takeover`. These names describe shipped internal behavior, not public endpoints to call. |
| `760107.e048e2c364.js`, 10,792-11,200 | The viewer subscribes separately to `controlowner` and `modechange`, then updates displayed control state. Video readiness and ownership are separate signals. |
| Same member, 22,265 | The displayed `video` element sets `autoPlay:!0,muted:!0,playsInline:!0`. An audio transceiver therefore does not establish audible viewer playback. |
| `832390.1e72e335e6.js`, 20,323 | The track callback processes video-track events and publishes their associated stream. Whether that stream also contains an audio track is a runtime question. |
| `422391.4688d99e30.js`, 55,186 | The separate Live transceiver creates an `audio` element and explicitly sets `muted` false. This is a distinct media/output path, not a game-audio attachment API. |
| `224730.aafbb78c7e.js`, 51,124 onward | Dot viewer state/telemetry uses `product: dots` with expanded WebRTC presentation and explicit takeover requests. |
| `63377.4e2cbc79e0.js`, 3,607 and 5,534 onward | A separate Work cloud-browser handoff takes a `novnc_url` response and embeds an iframe. This supports the alternate noVNC-labelled path, not a conclusion about the active Dot session. |

Selected member SHA-256 identities:

| Member | SHA-256 |
| --- | --- |
| `832390.1e72e335e6.js` | `7449818fd6dbf5e3c8afdde7dac35ef7851c0a48a1a23a67bb477ab58c3a7769` |
| `760107.e048e2c364.js` | `a0a1e69e31850172d471a04e77c44d2d0286ce905bb188a091a6fce666266ad9` |
| `224730.aafbb78c7e.js` | `244c46f6466c8a0c0e9d275720ab7ddcc1fdbc7c0a20a05019814330d88d38e6` |
| `63377.4e2cbc79e0.js` | `e8435375d2b073c50355f790c2f3a4c5914899e4b72f5cc80e644e622843bf9a` |
| `422391.4688d99e30.js` | `0d47de24d06834cc71250ef91e868745c55e40a62bfad1d300af379e2deaf9e0` |

## Audio playback correction

A subsequent bounded read of the installed members confirmed the explicit
viewer mute and separate unmuted Live sink above. Their member hashes match the
inspected artifact identities. This corrects the earlier implication that the
presence of an audio transceiver made native viewer sound a promising default.
The ordinary viewer tone test remains useful evidence, but silence there cannot
by itself establish failure to generate or capture sound on the cloud computer.

Plan an independently enabled audio sink on the user's device. A documented
incoming-track attachment, if one becomes available, could avoid a second media
connection; the available tools have not established one. Otherwise use an owned
independent transport. The companion voice audit did not establish a supported
game-audio attachment to Live. Replacing a microphone sender changes sound sent
into the voice service; it does not create local desktop-audio playback. No app
patch, hidden session access or live media capture was performed.

## Consequence for DotBox

There is a concrete ownership signal in the viewer's transport/control layer.
If a documented host integration exposes that signal, DotBox can consume an
acknowledged owner transition rather than analyze screenshots or guess from
focus/input silence. The available tools in this local task do not expose that
feed. Static discovery of an internal event does not make it a supported public
API or grant access to the authenticated channel.

Monitoring decoded frames can help follow visible game progression, but pixels
alone do not establish who owns input, whether a takeover request was accepted,
or whether control was released during a frozen/delayed frame. Ownership should
come from a supported control event/provider, with unknown state on disconnect
or missing evidence. Keep native DOSBox input ownership and desktop ownership
distinct until that provider is connected and tested.

No conclusion is made about the selected video codec, server implementation,
current live transport, latency, endpoint availability, or whether Dot's tool
context can subscribe to these events. The [runtime probe](../src/dotbox/runtime_probe.py)
continues to report unknown ownership until actual supported provider evidence
is available. Its inventory and the user-visible takeover labels remain useful
separate checks.
