# Read-only browser preview

The experimental presenter in `scripts/experiments/browser_preview.py` displays
original native PNG frames in an ordinary HTTP page. The original DOSBox process
remains responsible for game execution. Refreshing the page or changing its
display scale never advances the guest or changes game coordinates.

## Use with an existing service

Run the presenter on the same computer/network namespace as the browser and
the existing DotBox service:

```sh
python scripts/experiments/browser_preview.py \
  --session /private/dotbox/session/session.json \
  --port 8766 --fps 10
```

Open `http://127.0.0.1:8766/` in that browser. The command observes an existing
service; it does not launch a game. It uses the installed `dotbox.client.Client`
and leaves the private descriptor and credential on the server. Observation
rates above zero and at most 20 per second are accepted. This experiment is
not a new packaged command or release.

The page offers Fit and 1x through 4x presentation choices, preserves image
aspect ratio, and uses pixelated image rendering. Native frame width and height
remain unchanged. The view is read-only: keyboard, mouse, game input and platform
Take over/Return control are not implemented by this page.

## Use with an existing direct native owner

The owner can import `FrameStore` and `start_server`, then publish verified native
PNG bytes and their metadata with `store.publish(png_bytes, metadata)`.
`start_server(store, host='127.0.0.1', port=8766)` only binds and returns the HTTP
server. The owner starts `serve_forever` in a separate thread and owns shutdown.
`store.finish(status, message)` retains the last frame with a terminal status.

The HTTP threads only read the cache. They receive no native-session handle and
cannot call `frame.step`, inject input or transfer ownership. Only `/`, `/status`
and `/frame.png` are served. The last route returns the exact original PNG bytes;
the page handles presentation sizing. Unexpected Host values, other paths and
mutation methods are refused. The server binds only to local loopback.

## Initial verification on 20 November 2026

Confirmed:

- Python and embedded JavaScript syntax checks passed.
- One authored-PNG HTTP contract checked exact bytes, dimension/hash refusals,
  metadata filtering, loopback/Host/method/path restrictions and terminal cleanup.
- A separate integration check served an actual original Keen Dreams PNG,
  byte-identical at 320 by 200, with its native SHA-256 preserved.
- An isolated original Keen guest completed the existing ordinary-input bootstrap
  and ran continuously. Native frame IDs advanced from 1339 to 1343 and later
  4151. The last retained status records 801 post-bootstrap captures.

Not qualified in that initial attempt:

- The actual cloud browser did not reach the presenter. Its first HTTP request
  returned `net::ERR_CONNECTION_REFUSED`; a separate command execution context
  also could not reach that listener.
- Chrome then held `chrome-error://chromewebdata/`. Inspection and issue reporting
  on that internal URL were rejected by the browser protocol policy.
- Read-only desktop inventory was allowed after clarifying that distinction, but
  automatic approval review rejected launching a terminal on the same cloud
  desktop to start the viewer there, describing it as a prohibited workaround.
  No terminal launch occurred. Explicit authorization for that concrete local
  launch is the pending step; no end-to-end browser display is claimed.

The initial command-surface run was interrupted through its exact execution
session and returned exit code 130. It did not retain a native close/reap receipt;
do not describe that interruption as a qualified graceful guest closure.
Its game files were isolated copies. No commercial assets or native captures
are included in this repository.

The prepared private owner uses a one-hour execution deadline and supports a
local stop-request file. Its desktop launch and actual browser presentation were
pending at that checkpoint. The [initial result receipt](evidence/browser-preview-2026-11-20.json)
preserves the source identities, evidence hashes and precise partial outcome.

## Successful cloud-browser check on 20 November 2026

After the user explicitly approved the prepared local launch, the owner was
started from a terminal on the attached cloud desktop. The existing cloud
Chrome tab reached `http://127.0.0.1:8766/` and visibly displayed the original
Keen Dreams level. The temporary terminal was closed while the detached owner
and viewer continued running. The game tab was marked as the user deliverable.

The browser's image geometry was observed at a 1363 by 936 CSS-pixel viewport:

| Display choice | Rendered image (CSS pixels) | Native image (pixels) |
| --- | --- | --- |
| Fit | 1275.1875 by 797 | 320 by 200 |
| 1x | 320 by 200 | 320 by 200 |
| Fit again | 1275.1875 by 797 | 320 by 200 |

The 1x and subsequent Fit observations both showed frame 8121, so this size
change was observed on the same native frame. A later screenshot showed
`Live view`, native frame 16274 and 4241 received captures. Native receipts
independently recorded advancing frame IDs and guest ticks, with unchanged
320 by 200 dimensions and changing image hashes. The seven installed original
game files still matched their launch hashes.

This verifies live browser presentation and the two observed display choices.
The owner resumes the guest once after the ordinary-input bootstrap, then only
captures screenshots; HTTP requests read its cache. The game clock, world
coordinates and controller algorithms are unchanged. This is a read-only
presentation experiment, not a sustained refresh-rate or input-latency benchmark.
The existing service CLI route and other browser sizes were not exercised by
this successful direct-owner check.

The viewer was left running for user review under its one-hour owner deadline.
No native closure receipt is claimed for the active session. No new package was
released. See the [successful result receipt](evidence/browser-preview-live-2026-11-20.json)
for exact source identities, observations and limits; the initial failed attempt
remains recorded separately above.
