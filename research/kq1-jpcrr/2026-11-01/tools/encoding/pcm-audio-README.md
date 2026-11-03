# Optional native PC-speaker audio

`pcm_audio.py` adds sound to a separate copy of an already validated 1× video. It leaves `jmd_capture.py`, the original silent MP4 and its verification receipts unchanged.

```bash
python3 pcm_audio.py /path/to/closed-capture.jmd \
  --encoding /path/to/silent-output/encoding.json \
  --out /path/to/new-audio-output \
  --mux
```

Omit `--mux` to extract native event evidence and PCM WAV only. The output directory must be new or empty. The capture SHA-256 must match the silent encoder's sibling `index.json`, and the silent video must match its recorded SHA-256. Audio and video therefore use the same source capture and native crop start/end.

## What is preserved

The reference JMD has one active audio source: `org.jpc.emulator.peripheral.PCSpeaker-0`. It contains **25,466 timestamped PCM events**, with no active FM or other PCM source. `native-audio-events.json` retains every native audio packet's nanosecond timestamp, stream, subtype, payload bytes, and decoded signed sample values. Packet order at identical timestamps is retained. In this reference, the first audio events are at **5.628214800 s** and the last at **21.999926750 s** on the native clock.

Stock `OutputFramePCM` encodes signed stereo 16-bit values in big-endian order. `OutputFrameOneBitMono` emits either −32768 or +32767 on both channels. `PCSpeaker.updateSpeaker` emits old and new levels at the same transition timestamp. The native signal is the latest level held until the next event; before the first event, stock resampling emits silence.

The WAV is a derived **48 kHz, stereo, signed 16-bit PCM rendering** of that signal. Each sample averages the held level over its exact time interval. Computation uses integer `nanoseconds × sample rate` coordinates: transitions are not rounded onto audio sample boundaries or video frames, and there is no accumulated clock drift. Negative averages truncate toward zero. The native events remain the exact archival timing evidence; the WAV is a uniformly sampled representation.

This uses the time-weighted sample-and-hold method documented by the bundled stock PCM resampler. It does not claim byte identity with every configuration of the separate stock streamtools mixer. No gain normalization, analog speaker-response filter, empirical synchronization offset or playback-speed adjustment is applied. If the requested interval ends partway through a sample, the unused portion is explicitly zero-padded and reported as a rational duration.

## Sound preview and alignment checks

With `--mux`, the helper produces `playback-1x-with-sound.mp4`. It copies the silent MP4's video track and adds AAC audio for ordinary playback. AAC is lossy; the native event JSON and uncompressed PCM WAV are kept separately.

The helper independently probes the original and muxed video packets. Every video PTS, DTS, duration, packet size and SHA-256 payload hash must remain identical. The video timebase must also be unchanged. For audio, it verifies the sample rate/timebase, presentation start of zero, priming skip compensation and declared duration against the WAV.

For the reference control:

| Check | Result |
| --- | --- |
| Native interval represented by audio | 0.015–22.000 seconds |
| WAV duration | **21.985 seconds**, exactly 1,055,280 stereo sample frames at 48 kHz |
| Audio sample zero | Same native origin as video PTS zero: 0.015 s |
| Fractional final sample padding | None |
| Copied video packets | All **1,540** bitstreams/timestamps/durations unchanged |
| First AAC packet PTS | −1024 audio samples |
| Declared AAC priming skip | 1024 samples, exactly compensating the negative PTS |
| AAC playback start | 0 samples |
| AAC declared duration | 1,055,280 samples, identical to WAV |

The existing video has its already documented one-microsecond duplicate endpoint, so its track ends one microsecond after the audio's requested interval. That endpoint is a container presentation device, not another native game frame. No native timing is changed by adding audio.

Files in `reference-audio/` include the sound MP4, `native-pc-speaker-1x.wav`, `native-audio-events.json`, `audio-render.json`, and full video/audio `ffprobe` receipts.

## Deliberate scope

The helper rejects active FM synthesis, another active PCM source, unsupported PCM payloads, and non-unit PC-speaker volume changes. It does not silently omit audible streams or substitute an approximate synthesizer. Declared but inactive SoundCard PCM/FM channels are recorded as inactive. A capture outside this scope can still use the validated silent encoder.

Unit-gain one-bit PC-speaker levels reach the full signed 16-bit range. A nonzero constant level is not necessarily audible sound; the reported count of nonzero samples is a numeric signal statistic, not an audibility measurement.

## Verification and provenance

`python3 test_pcm_audio.py` passes four focused tests covering sub-sample transition integration, exact rational sample boundaries, negative truncation, crop initialization, final partial-sample padding, repeated native timestamps, signed PCM decoding and explicit rejection of unhandled sound data. The actual reference mux additionally passed independent FFmpeg packet and audio-clock checks.

`pcm-audio-provenance.json` records input/output hashes, helper/test hashes and the exact bundled source contracts: `OutputChannelPCM`, `OutputFramePCM`, `OutputFrameOneBitMono`, `PCSpeaker`, `resampler.cpp`, `digital-filter.cpp`, and the JMD format description. This adds post-processing only; it performs no guest operation.
