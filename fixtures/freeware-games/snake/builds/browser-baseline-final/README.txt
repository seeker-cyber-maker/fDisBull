Snake browser conversion - private runnable bundle

1. Extract this ZIP and open the contained snake-browser folder.
2. Serve this folder locally with Python 3:
   python3 -m http.server 8000 --bind 127.0.0.1
3. Open http://127.0.0.1:8000/ in Chrome.

The game starts paused. Arrows/WASD turn, N makes one move, Space/P toggles
pause, R resets and Esc quits. Blue in-game controls accept the mouse.
Click the canvas to focus it. Reload starts a new session.

Game logic and drawing independently select Wasm (CPU) or WebGPU (GPU).
Both use the same recovered UIL. GPU options are disabled when no adapter is
available; failures do not silently change backends or replay an input.
Backend changes end pending input context and release held pointer gestures.

The pixels, font and declared controls are compared with the authored DOS
original. This known-source recovery used source assistance. Original code,
clock adapters and diagnostic full-board setup are identified in the study.
The driver cursor is outside the pixel-comparison projection. Saves and full
PC keyboard/IME behavior are not part of this browser pilot.

Keep this derived game bundle private and out of GitHub. It contains generated
code and working font/data for local analysis, with no original EXE, FDB,
browser profile, native backend, Node dependencies or qualification vectors.
The adjacent continuation receipt records all build and verification paths.
