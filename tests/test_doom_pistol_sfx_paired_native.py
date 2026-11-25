"""Opt-in paired original Doom E1M1 pistol-sound witness.

The test keeps a no-shot audio control at pre-increment leveltime 64→84,
then fires exactly once at tic 84 and observes the shot-associated waveform
through tic 114 on both engines. Audio is searched independently against the
pinned WAD's DSPISTOL sample. It does not assert PCM identity, equal onset,
gain, mixing, or a sound-call instruction boundary.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import struct
import time
from PIL import Image

import pytest

from fdisbull.dosbox_rpc import DOSBoxRPC
from fdisbull.le import load_runtime_le_carrier
from fdisbull.project import Project
from support.doom_gameplay import capture_statusbar, decode_ammo_from_wad
from support.doom_le_dosbox import placement, read as dosbox_read, reach_site
from support.doom_le_qemu import CODE_OFFSET, DATA_OFFSET, PINS, runtime_inputs as qemu_runtime_inputs, stage_game
from test_doom_leveltime_paired_native import (
    _qemu_rebind_at_endpoint, _qemu_site, _qemu_wait_tic,
)


START_TIC = 64
CONTROL_END_TIC = 84
SHOT_END_TIC = 114
QEMU_CONTROL_BUDGET_MS = 470
QEMU_SHOT_BUDGET_MS = 760
DOSBOX_CONTROL_BUDGET_MS = 470
DOSBOX_SHOT_BUDGET_MS = 760
TOTAL_DEADLINE_SECONDS = 240
WINDOW_DEADLINE_SECONDS = 90
MAX_AUDIO_FRAMES = 160_000
BDA_ADDRESS = 0x46C
BDA_TICKS_PER_DAY = 0x1800B0
CORRELATION_THRESHOLD = 0.55
# Doom's original pitch range is 113..144 over a 128 divisor. A few fixed
# edge values bracket the endpoints without tuning the grid to capture output.
PITCH_RATIOS = tuple(value / 128 for value in range(110, 149))
REFERENCE_GUARD_SAMPLES = 16
CONTROL_REFERENCE_SAMPLES = 2048
DOSBOX_ONSET_FRONTIER_MARGIN_SECONDS = 0.25
QEMU_ARGUMENTS = "-warp 1 1 -skill 2 -nomonsters -nomouse -config D:\\DEFAULT.CFG"
DOSBOX_ARGUMENTS = "-warp 1 1 -skill 2 -nomonsters -nomouse -config DEFAULT.CFG"


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _source_hashes(source: Path) -> dict:
    return {name: _sha(source / name) for name in PINS}


def _read_dspistol(wad_path: Path) -> tuple[bytes, int]:
    raw = Path(wad_path).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == PINS["DOOM.WAD"]
    if len(raw) < 12 or raw[:4] not in (b"IWAD", b"PWAD"):
        raise ValueError("Pinned Doom WAD has an invalid header")
    count, directory = struct.unpack_from("<ii", raw, 4)
    if count < 1 or directory < 12 or directory + count * 16 > len(raw):
        raise ValueError("Pinned Doom WAD directory is outside the file")
    matches = []
    for index in range(count):
        offset, length = struct.unpack_from("<ii", raw, directory + index * 16)
        name = raw[directory + index * 16 + 8:directory + index * 16 + 16].rstrip(b"\0")
        if name == b"DSPISTOL":
            if offset < 0 or length < 8 or offset + length > len(raw):
                raise ValueError("DSPISTOL lump is outside the pinned WAD")
            matches.append(raw[offset:offset + length])
    if not matches or any(payload != matches[-1] for payload in matches[:-1]):
        raise ValueError(f"Duplicate DSPISTOL lumps disagree or are missing: {len(matches)} entries")
    # Doom's name lookup resolves duplicate entries to the last WAD directory
    # occurrence. Require all duplicates to be identical before using it.
    lump = matches[-1]
    sample_format, sample_rate, sample_count = struct.unpack_from("<HHI", lump)
    if sample_format != 3 or sample_rate != 11025 or sample_count != len(lump) - 8:
        raise ValueError("DSPISTOL DMX header differs from the admitted reference")
    sample = lump[8:]
    if len(sample) <= 2 * REFERENCE_GUARD_SAMPLES:
        raise ValueError("DSPISTOL sample is too short after guard removal")
    return sample[REFERENCE_GUARD_SAMPLES:-REFERENCE_GUARD_SAMPLES], sample_rate


def _wav_pcm(raw: bytes, *, finalized: bool) -> dict:
    if len(raw) < 44 or raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise ValueError("Audio capture is not a complete RIFF/WAVE header")
    riff_size = struct.unpack_from("<I", raw, 4)[0]
    if finalized and riff_size + 8 != len(raw):
        raise ValueError(f"Finalized RIFF size mismatch: header={riff_size + 8}, actual={len(raw)}")
    cursor = 12
    fmt = data_offset = data_length = None
    while cursor + 8 <= len(raw):
        chunk_id = raw[cursor:cursor + 4]
        chunk_size = struct.unpack_from("<I", raw, cursor + 4)[0]
        payload = cursor + 8
        if chunk_id == b"fmt ":
            if chunk_size < 16 or payload + 16 > len(raw):
                raise ValueError("Truncated WAV fmt chunk")
            fmt = struct.unpack_from("<HHIIHH", raw, payload)
        elif chunk_id == b"data":
            data_offset, data_length = payload, chunk_size
            break
        next_cursor = payload + chunk_size + (chunk_size & 1)
        if next_cursor <= cursor:
            raise ValueError("Invalid WAV chunk extent")
        cursor = next_cursor
    if fmt is None or data_offset is None:
        raise ValueError("WAV lacks fmt or data chunk")
    format_code, channels, rate, byte_rate, block_align, bits = fmt
    if format_code != 1 or channels != 2 or bits != 16 or block_align != 4 or byte_rate != rate * 4:
        raise ValueError(f"Expected signed 16-bit stereo PCM, got {fmt}")
    available = max(0, len(raw) - data_offset)
    if finalized:
        available = min(data_length, available)
    available -= available % block_align
    if finalized and available != data_length:
        raise ValueError("Finalized WAV data chunk is truncated")
    pcm = raw[data_offset:data_offset + available]
    return dict(pcm=pcm, rate=rate, channels=channels, sample_width=2,
                frames=len(pcm) // block_align, data_offset=data_offset,
                declared_data_bytes=data_length, available_data_bytes=available,
                riff_bytes=len(raw), finalized=finalized)


def _dosbox_post_stop_pcm(raw: bytes) -> dict:
    """Parse DX-CAPTURE output, accepting its observed post-stop placeholder header."""
    placeholder = (
        len(raw) > 44 and raw[:4] == b"RIFF" and raw[8:12] == b"WAVE"
        and struct.unpack_from("<I", raw, 4)[0] == 28
        and raw[12:16] == b"fmt " and struct.unpack_from("<I", raw, 16)[0] == 16
        and struct.unpack_from("<HHIIHH", raw, 20) == (1, 2, 48_000, 192_000, 4, 16)
        and raw[36:40] == b"data" and struct.unpack_from("<I", raw, 40)[0] == 0
        and (len(raw) - 44) > 0 and (len(raw) - 44) % 4 == 0
    )
    if placeholder:
        parsed = _wav_pcm(raw, finalized=False)
        if parsed["data_offset"] != 44 or parsed["available_data_bytes"] != len(raw) - 44:
            raise ValueError("DX-CAPTURE placeholder header does not contain one canonical PCM payload")
        return dict(**parsed, header_form="zero_size_placeholder",
                    header_finalized=False, capture_completeness="unknown")
    parsed = _wav_pcm(raw, finalized=True)
    return dict(**parsed, header_form="finalized_riff",
                header_finalized=True, capture_completeness="unknown")


def _sample_correlation(pcm: bytes, rate: int, reference: bytes, reference_rate: int,
                        *, reference_samples: int) -> dict:
    try:
        import numpy as np
    except ImportError as error:
        raise RuntimeError("The required private Doom SFX gate needs NumPy for bounded correlation") from error
    if len(pcm) % 4:
        raise ValueError("Stereo PCM length is not frame aligned")
    if not 0 < reference_samples <= len(reference):
        raise ValueError("Reference sample window is invalid")
    # A centered stereo projection keeps the reference match independent of
    # channel pan while retaining the engine's original native PCM.
    stereo = np.frombuffer(pcm, dtype="<i2").reshape(-1, 2).astype(np.float64)
    signal = stereo.mean(axis=1) / 32768.0
    if len(signal) < 16:
        raise ValueError("PCM segment is too short to search")
    ref = (np.frombuffer(reference[:reference_samples], dtype=np.uint8).astype(np.float64) - 128.0) / 128.0
    ref = ref - ref.mean()
    best = dict(score=-1.0, onset_frame=None, pitch_ratio=None, template_frames=None)
    for ratio in PITCH_RATIOS:
        template_count = max(16, round(len(ref) * rate / (reference_rate * ratio)))
        source_positions = np.arange(template_count, dtype=np.float64) * reference_rate * ratio / rate
        template = np.interp(source_positions, np.arange(len(ref), dtype=np.float64), ref)
        template -= template.mean()
        template_energy = float(np.dot(template, template))
        if template_energy <= 1e-12 or len(signal) < len(template):
            continue
        fft_length = 1 << (len(signal) + len(template) - 2).bit_length()
        products = np.fft.irfft(np.fft.rfft(signal, fft_length) *
                                np.fft.rfft(template[::-1], fft_length), fft_length)
        dots = products[len(template) - 1:len(signal)]
        cumulative = np.concatenate(([0.0], np.cumsum(signal, dtype=np.float64)))
        cumulative_squares = np.concatenate(([0.0], np.cumsum(signal * signal, dtype=np.float64)))
        window_sums = cumulative[len(template):] - cumulative[:-len(template)]
        window_squares = cumulative_squares[len(template):] - cumulative_squares[:-len(template)]
        signal_energy = np.maximum(window_squares - window_sums * window_sums / len(template), 0.0)
        denominator = np.sqrt(signal_energy * template_energy)
        scores = np.divide(dots, denominator, out=np.zeros_like(dots), where=denominator > 1e-12)
        if scores.size:
            peak = int(np.argmax(scores))
            score = float(scores[peak])
            if score > best["score"]:
                best = dict(score=score, onset_frame=peak, pitch_ratio=ratio,
                            template_frames=len(template))
    if best["onset_frame"] is None:
        raise ValueError("No valid DSPISTOL correlation window fits in the PCM segment")
    return best


def _qemu_bda(debug) -> int:
    raw = bytes.fromhex(debug.memory(BDA_ADDRESS, length=4, space="physical")["hex"])
    return int.from_bytes(raw, "little")


def _qemu_advance_to_tic(debug, pc: int, counter: int, breakpoint_id: str,
                         target: int, budget_ms: int) -> tuple[int, str]:
    debug.delete_breakpoint(breakpoint_id)
    stopped = debug.clock_advance(budget_ms * 1_000_000, timeout_ms=60_000)
    budget = stopped["clock_budget"]
    assert budget["deadline_reached"] and budget["elapsed_ns"] >= budget_ms * 1_000_000, stopped
    assert stopped["outcome"] not in ("guest_exit", "guest_tsr", "exited"), stopped
    tick = int.from_bytes(bytes.fromhex(debug.memory(counter, length=4, space="virtual")["hex"]), "little")
    assert tick < target, (tick, target, stopped)
    breakpoint_id = debug.breakpoint(pc)["breakpoint_id"]
    tick, _, breakpoint_id = _qemu_wait_tic(debug, pc, counter, breakpoint_id, target)
    return tick, breakpoint_id


def _qemu_capture_window(debug, project: Project, tmp_path: Path, label: str,
                         pc: int, counter: int, breakpoint_id: str, target: int,
                         budget_ms: int) -> tuple[dict, str]:
    tick, breakpoint_id = _qemu_advance_to_tic(
        debug, pc, counter, breakpoint_id, target, budget_ms)
    binding = _qemu_rebind_at_endpoint(debug, pc, counter, target)
    clock = debug.clock_observe()
    bda = _qemu_bda(debug)
    stop = debug.audio_stop()
    assert stop["state"] == "stopped" and stop["stop_ns"] is not None, stop
    assert stop["dropped_frames"] == 0 and stop["frames"] > 0, stop
    assert stop["window"] and stop["epoch"] == clock["epoch"], (stop, clock)
    artifact = debug.capture_audio(label + ".wav")
    output = tmp_path / (label + ".wav")
    project.debug_export(artifact["artifact"], output)
    assert _sha(output) == artifact["sha256"]
    audio = _wav_pcm(output.read_bytes(), finalized=True)
    assert audio["rate"] == 32_000 and audio["channels"] == 2, audio
    return dict(tic=tick, clock_ns=clock["virtual_ns"], bda_tick=bda,
                window=stop["window"], epoch=stop["epoch"], frames=stop["frames"],
                dropped_frames=stop["dropped_frames"], callback_chunks=stop["native"]["chunks"],
                audio=audio, wav_sha256=_sha(output), binding_id=binding["binding_id"]), breakpoint_id


def _run_qemu(root: Path, runtime: dict, reference: bytes, reference_rate: int) -> dict:
    root.mkdir()
    game = stage_game(root, runtime["source"])
    owners = []
    options = dict(backend="qemu-dos", dos_directory=str(game),
        dos_boot_image=str(runtime["boot"]), dos_mcopy=str(runtime["mcopy"]),
        qemu_transport="pipe", qemu_firmware=runtime["firmware"], qemu_audio="sb16-opl",
        qemu_retrace="precise", qemu_clock="virtual",
        qemu_checkpoint_tool=str(runtime["checkpoint_tool"]), dos_arguments=QEMU_ARGUMENTS,
        boot_timeout_ms=35_000)
    with Project.create(root / "doom-pistol.fdb", game / "DOOM.EXE", image="mz") as project:
        with project.debugger(runtime["qemu"], game, _on_spawn=owners.append, **options) as debug:
            pc, counter, code = _qemu_site(project, debug, root / "source-binding.json")
            bp = debug.breakpoint(pc)["breakpoint_id"]
            start_tic, _, bp = _qemu_wait_tic(debug, pc, counter, bp, START_TIC)
            start_binding = _qemu_rebind_at_endpoint(debug, pc, counter, START_TIC)
            start_clock, start_bda = debug.clock_observe(), _qemu_bda(debug)

            control_start = debug.audio_start(max_frames=MAX_AUDIO_FRAMES, capture_format="s16-stereo")
            assert control_start["state"] == "capturing"
            assert control_start["sample_format"] == dict(rate=32_000, channels=2,
                sample_format="s16", bytes_per_frame=4), control_start
            control, bp = _qemu_capture_window(debug, project, root, "qemu-no-shot",
                pc, counter, bp, CONTROL_END_TIC, QEMU_CONTROL_BUDGET_MS)
            assert control["window"] == control_start["window"]
            assert control["audio"]["frames"] == control["frames"]
            control_ammo_view = capture_statusbar(project, debug, root, "qemu-control-end")
            control_ammo = decode_ammo_from_wad(game / "DOOM.WAD", control_ammo_view["statusbar"])
            assert control_ammo["value"] == 50, control_ammo
            control_corr = _sample_correlation(control["audio"]["pcm"], control["audio"]["rate"],
                reference, reference_rate, reference_samples=CONTROL_REFERENCE_SAMPLES)
            assert control_corr["score"] < CORRELATION_THRESHOLD, control_corr

            before_shot_view = capture_statusbar(project, debug, root, "qemu-before-shot")
            before_shot = decode_ammo_from_wad(game / "DOOM.WAD", before_shot_view["statusbar"])
            assert before_shot["value"] == 50, before_shot
            shot_start_clock, shot_start_bda = debug.clock_observe(), _qemu_bda(debug)
            shot_capture_start = debug.audio_start(max_frames=MAX_AUDIO_FRAMES,
                                                   capture_format="s16-stereo")
            assert shot_capture_start["state"] == "capturing"
            assert shot_capture_start["sample_format"] == control_start["sample_format"]
            shot_input = debug.keyboard_press("ctrl", hold_ms=300, gap_ms=80)
            assert shot_input.get("state") == "armed", shot_input
            assert shot_input.get("press", {}).get("hold_ms") == 300, shot_input
            assert shot_input.get("press", {}).get("gap_ms") == 80, shot_input

            tick, bp = _qemu_advance_to_tic(debug, pc, counter, bp, SHOT_END_TIC,
                                             QEMU_SHOT_BUDGET_MS)
            end_binding = _qemu_rebind_at_endpoint(debug, pc, counter, SHOT_END_TIC)
            end_clock, end_bda = debug.clock_observe(), _qemu_bda(debug)
            scheduled_input = debug.input_schedule_observe()
            assert scheduled_input["state"] == "dispatched", scheduled_input
            assert scheduled_input["edge_count"] == 2, scheduled_input
            assert scheduled_input.get("dispatch_ns") is not None, scheduled_input
            press = scheduled_input.get("press", {})
            assert press.get("hold_ms") == 300 and press.get("dispatched_count") == 2, press
            assert [edge["down"] for edge in press["steps"]] == [True, False], press
            shot_stop = debug.audio_stop()
            assert shot_stop["state"] == "stopped" and shot_stop["dropped_frames"] == 0, shot_stop
            assert shot_stop["epoch"] == end_clock["epoch"] and shot_stop["window"] == shot_capture_start["window"]
            shot_artifact = debug.capture_audio("qemu-shot.wav")
            shot_path = root / "qemu-shot.wav"
            project.debug_export(shot_artifact["artifact"], shot_path)
            assert _sha(shot_path) == shot_artifact["sha256"]
            shot_audio = _wav_pcm(shot_path.read_bytes(), finalized=True)
            assert shot_audio["rate"] == 32_000 and shot_audio["channels"] == 2, shot_audio
            after_view = capture_statusbar(project, debug, root, "qemu-after-shot")
            after = decode_ammo_from_wad(game / "DOOM.WAD", after_view["statusbar"])
            assert after["value"] == 49, after
            shot_corr = _sample_correlation(shot_audio["pcm"], shot_audio["rate"],
                reference, reference_rate, reference_samples=len(reference))
            assert shot_corr["score"] >= CORRELATION_THRESHOLD, shot_corr
            assert shot_corr["onset_frame"] + shot_corr["template_frames"] <= shot_audio["frames"], shot_corr

            result = dict(backend="qemu-dos", source_sha256=PINS["DOOM.EXE"],
                endpoint_tics=dict(start=start_tic, control_end=CONTROL_END_TIC, shot_end=tick),
                site=dict(runtime_pc=pc, runtime_counter=counter,
                          instruction_bytes=code.hex(), object_index=1,
                          object_offset=CODE_OFFSET, target_object=3, target_offset=DATA_OFFSET),
                clocks=dict(domain="QEMU_CLOCK_VIRTUAL_ns", start=start_clock["virtual_ns"],
                    shot_start=shot_start_clock["virtual_ns"], end=end_clock["virtual_ns"]),
                bda_ticks=dict(address=hex(BDA_ADDRESS), start=start_bda,
                    shot_start=shot_start_bda, end=end_bda,
                    control_delta=(control["bda_tick"] - start_bda) % BDA_TICKS_PER_DAY,
                    shot_delta=(end_bda - shot_start_bda) % BDA_TICKS_PER_DAY),
                input=dict(receipt=shot_input, native_observation=scheduled_input,
                           claim="one accepted Ctrl chord was dispatched; guest consumption is supported separately by ammo 50-to-49"),
                ammunition=dict(start=before_shot["value"], control=control_ammo["value"],
                                after=after["value"], wad_sha256=after["wad_sha256"],
                                decoder_lumps=after["lumps"]),
                audio=dict(rate=shot_audio["rate"], channels=shot_audio["channels"],
                    sample_width=2, shot_window=dict(start_ns=shot_capture_start["start_ns"],
                        stop_ns=shot_stop["stop_ns"], frames=shot_audio["frames"],
                        dropped_frames=shot_stop["dropped_frames"],
                        overflow=shot_stop["state"] == "overflow", callback_chunks=shot_stop["native"]["chunks"],
                        wav_sha256=_sha(shot_path)),
                    control_window=dict(start_tic=START_TIC, end_tic=CONTROL_END_TIC,
                        frames=control["frames"], dropped_frames=control["dropped_frames"],
                        overflow=False, wav_sha256=control["wav_sha256"]),
                    control_correlation=control_corr, shot_correlation=shot_corr,
                    onset_bound=dict(unit="capture frames; not calibrated to guest milliseconds",
                        shot_capture_start_frame=0, onset_frame=shot_corr["onset_frame"],
                        guest_clock_bracket_ns=[shot_capture_start["start_ns"], end_clock["virtual_ns"]],
                        claim="shot-associated WAD sample match; no sound-call PC attribution")),
                source_binding_ids=[start_binding["binding_id"], control["binding_id"],
                                    end_binding["binding_id"]],
                runtime_sha256=_sha(runtime["qemu"]), boot_sha256=_sha(runtime["boot"]),
                mcopy_sha256=_sha(runtime["mcopy"]),
                checkpoint_tool_sha256=_sha(runtime["checkpoint_tool"]))
    assert owners and all(owner.poll() is not None for owner in owners)
    assert all(owner.returncode == 0 for owner in owners), [owner.returncode for owner in owners]
    result["owner_reaped"] = True
    result["owner_returncodes"] = [owner.returncode for owner in owners]
    assert _source_hashes(game) == PINS
    return result


class _DOSBoxView:
    def __init__(self, call):
        self._call = call

    def call(self, method, params=None):
        return self._call(method, params)

    def registers(self):
        result = self.call("state.get_registers")
        result.update(cs=result["segments"]["cs"], ip=result["instruction_pointer"])
        return result


def _dosbox_bda(view) -> int:
    return int.from_bytes(dosbox_read(view, "linear", BDA_ADDRESS, 4), "little")


def _dosbox_frontier(capture_dir: Path) -> dict:
    files = sorted(Path(capture_dir).glob("*.wav"))
    if len(files) != 1:
        raise ValueError(f"Expected one live DOSBox capture file, found {len(files)}")
    raw = files[0].read_bytes()
    info = _wav_pcm(raw, finalized=False)
    return dict(path=files[0], file_bytes=len(raw), pcm_frames=info["frames"],
                rate=info["rate"], channels=info["channels"])


def _dosbox_ammo(view, game: Path) -> dict:
    from fdisbull.screenshot_codecs import decode_screenshot

    capture = view.call("video.screenshot")
    data, metadata = decode_screenshot(capture)
    with Image.open(io.BytesIO(data)) as source:
        image = source.convert("RGB")
        image.load()
        width, height = image.size
        assert width >= 320 and height >= 200 and width * 200 == height * 320, image.size
        normalized = image.resize((320, 200), Image.Resampling.NEAREST)
        ammo = decode_ammo_from_wad(game / "DOOM.WAD", normalized.crop((14, 170, 44, 190)))
    return dict(**ammo, screenshot_sha256=hashlib.sha256(data).hexdigest(),
                dimensions=[width, height], frame_id=metadata.get("frame_id"))


def _dosbox_wait_tic(call, view, image, pc, counter, address, target,
                     last_tic: int, *, max_stops=SHOT_END_TIC + 8) -> tuple[int, dict]:
    tic = last_tic
    current = None
    for _ in range(max_stops):
        stepped = call("execution.step", dict(mode="into"))
        assert stepped["stop_reason"]["kind"] == "step", stepped
        point = call("breakpoints.create", dict(kind="execution", once=True, address=address))
        operation = call("execution.continue")
        deadline = time.monotonic() + WINDOW_DEADLINE_SECONDS
        while time.monotonic() < deadline:
            stopped = call("execution.wait", dict(operation_id=operation["operation_id"], timeout_ms=100))
            if stopped.get("running"):
                continue
            assert not stopped.get("running") and stopped["stop_reason"]["kind"] == "breakpoint", stopped
            assert stopped["stop_reason"]["breakpoint_id"] == point["breakpoint_id"], stopped
            current = placement(view, image)
            assert current and current["runtime_address"] == pc and current["runtime_target"] == counter
            tic = int.from_bytes(dosbox_read(view, "linear", counter, 4), "little")
            assert tic <= target, (tic, target)
            if tic == target:
                return tic, current
            break
        else:
            raise TimeoutError(f"DOSBox-X did not reach leveltime {target}")
    raise AssertionError(f"DOSBox-X did not reach leveltime {target}; last tic {tic}")


def _dosbox_run_ms(call, view, counter, target, milliseconds: int,
                   last_tic: int) -> tuple[int, dict]:
    timing = call("execution.timing")
    operation = call("execution.continue")
    target_ticks = timing["guest_ticks"] + milliseconds
    deadline = time.monotonic() + WINDOW_DEADLINE_SECONDS
    while time.monotonic() < deadline:
        now = call("execution.timing")
        if now["guest_ticks"] >= target_ticks:
            pause = call("execution.pause")
            stopped = call("execution.wait", dict(operation_id=pause["operation_id"], timeout_ms=3000))
            assert not stopped.get("running") and stopped["stop_reason"]["kind"] == "pause", stopped
            tic = int.from_bytes(dosbox_read(view, "linear", counter, 4), "little")
            assert last_tic < tic < target, (last_tic, tic, target)
            return tic, dict(start_ticks=timing["guest_ticks"], end_ticks=now["guest_ticks"],
                             requested_ms=milliseconds, observed_tic=tic)
        pending = call("execution.wait", dict(operation_id=operation["operation_id"], timeout_ms=100))
        assert pending.get("running"), pending
    raise TimeoutError("DOSBox-X guest-time window timed out")


def _run_dosbox(root: Path, runtime: dict, reference: bytes, reference_rate: int) -> dict:
    root.mkdir()
    game = root / "game"
    game.mkdir()
    for name in PINS:
        source = runtime["source"] / name
        assert _sha(source) == PINS[name]
        (game / name).write_bytes(source.read_bytes())
    assert _source_hashes(game) == PINS
    image = load_runtime_le_carrier((game / "DOOM.EXE").read_bytes())
    wrapper = root / "dosbox-capture-wave"
    wrapper.write_text("#!/bin/sh\nexec " + shlex.quote(str(runtime["dosbox"]))
        + ' "$@" -c "ALIAS CAPW=DX-CAPTURE /A /-D"\n')
    wrapper.chmod(0o700)
    rpc = DOSBoxRPC(wrapper, game)
    owner = rpc.process
    capture_dir = Path(rpc.temporary.name) / "capture"
    total_deadline = time.monotonic() + TOTAL_DEADLINE_SECONDS
    session_id = None
    last_tic = None

    def call(method, parameters=None, *, timeout_ms=15_000):
        assert time.monotonic() < total_deadline, f"DOSBox-X deadline expired at tic {last_tic}"
        return rpc.call(method, parameters, timeout_ms=timeout_ms)

    try:
        started = call("session.start", dict(
            target=dict(command="CAPW", arguments=["DOOM.EXE", *DOSBOX_ARGUMENTS.split()]),
            mounts=[dict(drive="C", host_path=str(game))], break_at="entry"))
        session_id = started["session_id"]

        def session_call(method, parameters=None, *, timeout_ms=15_000):
            return call(method, dict(session_id=session_id, **(parameters or {})), timeout_ms=timeout_ms)

        view = _DOSBoxView(session_call)
        assert session_call("execution.timing")["fast_forward"] is False
        registers = session_call("state.get_registers")
        assert registers["cpu_mode"] == "real", registers
        session_call("execution.timing", dict(fast_forward=True))
        reach_site(view, image)
        site = placement(view, image)
        assert site and site["runtime_address"] == site["cs_base"] + site["ip"]
        pc, counter = site["runtime_address"], site["runtime_target"]
        assert site["runtime_bytes"] == "ff05" + counter.to_bytes(4, "little").hex()
        address = dict(space="segmented", segment=f"0x{site['cs']:04x}",
                       offset=f"0x{pc - site['cs_base']:08x}")
        def tic_at_stop():
            nonlocal last_tic
            last_tic = int.from_bytes(dosbox_read(view, "linear", counter, 4), "little")
            return last_tic

        # `reach_site` leaves the CPU at the selected pre-INC instruction.
        # Execute one instruction, then continue to the next occurrence of
        # that PC. Repeating single steps alone would never advance leveltime
        # efficiently through Doom's intervening game loop.
        tic = tic_at_stop()
        assert tic <= START_TIC
        for _ in range(START_TIC + 1):
            if tic == START_TIC:
                break
            step = session_call("execution.step", dict(mode="into"), timeout_ms=3_000)
            assert step["stop_reason"]["kind"] == "step", step
            point = session_call("breakpoints.create", dict(
                kind="execution", once=True, address=address))
            operation = session_call("execution.continue")
            target_deadline = min(total_deadline,
                                  time.monotonic() + WINDOW_DEADLINE_SECONDS)
            while time.monotonic() < target_deadline:
                stopped = session_call("execution.wait", dict(
                    operation_id=operation["operation_id"], timeout_ms=100), timeout_ms=1_000)
                if stopped.get("running"):
                    continue
                assert not stopped.get("running"), stopped
                assert stopped["stop_reason"]["kind"] == "breakpoint", stopped
                assert stopped["stop_reason"]["breakpoint_id"] == point["breakpoint_id"], stopped
                current = placement(view, image)
                assert current and current["runtime_address"] == pc, current
                tic = tic_at_stop()
                assert tic <= START_TIC, tic
                break
            else:
                raise TimeoutError(
                    f"DOSBox-X did not reach pre-increment leveltime {START_TIC} before the deadline")
        else:
            raise AssertionError(
                f"DOSBox-X did not reach pre-increment leveltime {START_TIC}; last tic {tic}")
        assert tic == START_TIC
        session_call("execution.timing", dict(fast_forward=False))
        start_timing = session_call("execution.timing")
        start_bda = _dosbox_bda(view)
        start_frontier = _dosbox_frontier(capture_dir)
        assert start_frontier["rate"] == 48_000 and start_frontier["channels"] == 2

        control_tic, control_run = _dosbox_run_ms(
            session_call, view, counter, CONTROL_END_TIC, DOSBOX_CONTROL_BUDGET_MS, START_TIC)
        before_shot_tic, _ = _dosbox_wait_tic(
            session_call, view, image, pc, counter, address, CONTROL_END_TIC, control_tic)
        control_timing = session_call("execution.timing")
        control_bda = _dosbox_bda(view)
        control_frontier = _dosbox_frontier(capture_dir)
        control_ammo = _dosbox_ammo(view, game)
        assert control_ammo["value"] == 50, control_ammo
        assert start_frontier["pcm_frames"] < control_frontier["pcm_frames"], (
            start_frontier, control_frontier)
        control_bytes = (control_frontier["pcm_frames"] - start_frontier["pcm_frames"]) * 4
        assert control_bytes // 4 >= round(48_000 * 0.20), control_frontier

        shot_start_timing = session_call("execution.timing")
        shot_start_bda = _dosbox_bda(view)
        shot_frontier = _dosbox_frontier(capture_dir)
        key_receipt = session_call("input.keyboard.press", dict(key="ctrl", hold_ms=300, gap_ms=80))
        assert key_receipt, "DOSBox-X did not admit the single Ctrl press"
        shot_tic, shot_run = _dosbox_run_ms(
            session_call, view, counter, SHOT_END_TIC, DOSBOX_SHOT_BUDGET_MS, CONTROL_END_TIC)
        shot_tic, _ = _dosbox_wait_tic(
            session_call, view, image, pc, counter, address, SHOT_END_TIC, shot_tic)
        end_timing = session_call("execution.timing")
        end_bda = _dosbox_bda(view)
        after_frontier = _dosbox_frontier(capture_dir)
        after_ammo = _dosbox_ammo(view, game)
        assert after_ammo["value"] == 49, after_ammo
        stop = session_call("session.stop")
        stop_operation_id = stop["operation_id"]
        stop_deadline = time.monotonic() + 30
        stopped = None
        while time.monotonic() < stop_deadline:
            stopped = session_call("execution.wait", dict(
                operation_id=stop_operation_id, timeout_ms=250), timeout_ms=1_000)
            if not stopped.get("running"):
                break
        else:
            raise TimeoutError(
                f"DOSBox-X session.stop operation {stop_operation_id} remained running "
                f"for 30s; last execution.wait reply: {stopped!r}")
        files = sorted(capture_dir.glob("*.wav"))
        assert len(files) == 1 and files[0].is_file(), files
        post_stop_payload_path = root / "dosbox-post-stop-payload.wav"
        post_stop_payload_path.write_bytes(files[0].read_bytes())
        payload = _dosbox_post_stop_pcm(post_stop_payload_path.read_bytes())
        assert payload["rate"] == 48_000 and payload["channels"] == 2, payload
        required_frontier = max(start_frontier["pcm_frames"], control_frontier["pcm_frames"],
                                shot_frontier["pcm_frames"], after_frontier["pcm_frames"])
        assert required_frontier <= payload["frames"], (required_frontier, payload)
        post_frontier_tail_frames = payload["frames"] - after_frontier["pcm_frames"]
        diagnostic = dict(format="fdisbull-doom-pistol-dosbox-audio-diagnostic-1",
            source_file_sha256=PINS,
            runtime_sha256=dict(dosbox=_sha(runtime["dosbox"])),
            leveltime=dict(start=START_TIC, control_end=before_shot_tic, shot_end=shot_tic),
            frontiers=dict(start={key: value for key, value in start_frontier.items() if key != "path"},
                control={key: value for key, value in control_frontier.items() if key != "path"},
                shot={key: value for key, value in shot_frontier.items() if key != "path"},
                after={key: value for key, value in after_frontier.items() if key != "path"}),
            post_stop_payload=dict(frames=payload["frames"], rate=payload["rate"],
                channels=payload["channels"], header_form=payload["header_form"],
                header_finalized=payload["header_finalized"],
                capture_completeness="unknown", sha256=_sha(post_stop_payload_path)),
            observed_post_frontier_tail_frames=post_frontier_tail_frames,
            input=dict(key="ctrl", accepted=bool(key_receipt), receipt=key_receipt),
            ammunition=dict(control=control_ammo["value"], after=after_ammo["value"],
                wad_sha256=after_ammo["wad_sha256"]))
        (root / "dosbox-audio-diagnostic.json").write_text(
            json.dumps(diagnostic, sort_keys=True, indent=2) + "\n")

        control_start = start_frontier["pcm_frames"]
        control_end = min(control_frontier["pcm_frames"], payload["frames"])
        control_pcm = payload["pcm"][control_start * 4:control_end * 4]
        assert len(control_pcm) // 4 >= round(48_000 * 0.20), (control_start, control_end)
        control_corr = _sample_correlation(control_pcm, payload["rate"], reference,
            reference_rate, reference_samples=CONTROL_REFERENCE_SAMPLES)
        assert control_corr["score"] < CORRELATION_THRESHOLD, control_corr

        margin_frames = round(payload["rate"] * DOSBOX_ONSET_FRONTIER_MARGIN_SECONDS)
        search_start = max(0, shot_frontier["pcm_frames"] - margin_frames)
        search_end = after_frontier["pcm_frames"]
        shot_pcm = payload["pcm"][search_start * 4:search_end * 4]
        shot_corr = _sample_correlation(shot_pcm, payload["rate"], reference,
            reference_rate, reference_samples=len(reference))
        assert shot_corr["score"] >= CORRELATION_THRESHOLD, shot_corr
        onset_absolute = search_start + shot_corr["onset_frame"]
        assert onset_absolute >= max(0, shot_frontier["pcm_frames"] - margin_frames), shot_corr
        assert onset_absolute <= after_frontier["pcm_frames"] + margin_frames, shot_corr
        assert onset_absolute + shot_corr["template_frames"] <= search_end, shot_corr

        result = dict(backend="dosbox", source_sha256=PINS["DOOM.EXE"],
            endpoint_tics=dict(start=START_TIC, control_end=before_shot_tic, shot_end=shot_tic),
            site=dict(runtime_pc=pc, runtime_counter=counter, instruction_bytes=site["runtime_bytes"],
                      object_index=1, object_offset=CODE_OFFSET,
                      target_object=3, target_offset=DATA_OFFSET),
            clocks=dict(domain="DOSBox-X PIC guest milliseconds", start=start_timing["guest_ticks"],
                control_end=control_timing["guest_ticks"], shot_start=shot_start_timing["guest_ticks"],
                end=end_timing["guest_ticks"], control_run=control_run, shot_run=shot_run),
            bda_ticks=dict(address=hex(BDA_ADDRESS), start=start_bda,
                control_end=control_bda, shot_start=shot_start_bda, end=end_bda,
                control_delta=(control_bda - start_bda) % BDA_TICKS_PER_DAY,
                shot_delta=(end_bda - shot_start_bda) % BDA_TICKS_PER_DAY),
            input=dict(receipt=key_receipt, claim="one accepted Ctrl press; WAD ammo delta separately verifies one pistol round"),
            audio=dict(rate=payload["rate"], channels=payload["channels"], sample_width=payload["sample_width"],
                control_window=dict(start_frame=start_frontier["pcm_frames"],
                    end_frame=control_frontier["pcm_frames"],
                    header_finalized=payload["header_finalized"],
                    capture_completeness=payload["capture_completeness"],
                    overflow=None, dropped_frames=None),
                shot_window=dict(start_frontier_frame=shot_frontier["pcm_frames"],
                    end_frontier_frame=after_frontier["pcm_frames"],
                    available_payload_frames=payload["frames"],
                    post_frontier_tail_frames=post_frontier_tail_frames,
                    header_finalized=payload["header_finalized"],
                    capture_completeness=payload["capture_completeness"],
                    overflow=None, dropped_frames=None,
                    limitation="DX-CAPTURE exposes no native dropped-frame/overflow counter"),
                control_correlation=control_corr, shot_correlation=shot_corr,
                onset_bound=dict(unit="available post-stop payload frame indices; file origin/frontier flush is not guest-clock calibrated",
                    search_frames=[search_start, search_end], onset_frame=onset_absolute,
                    frontier_margin_frames=margin_frames,
                    post_frontier_tail_frames=post_frontier_tail_frames,
                    claim="shot-associated WAD sample match; no sound-call PC attribution"),
                wav_sha256=_sha(post_stop_payload_path), header_form=payload["header_form"],
                header_finalized=payload["header_finalized"],
                capture_completeness=payload["capture_completeness"],
                payload_observation=("DX-CAPTURE bytes observed after session.stop and terminal wait; "
                    "only available aligned bytes bounded by live frontiers were analyzed; capture completeness unknown; "
                    "no Doom guest-exit claim"),
                stop_reply=dict(session_stop=stop, execution_wait=stopped)),
            ammunition=dict(control=control_ammo["value"], after=after_ammo["value"],
                            decoder_wad_sha256=after_ammo["wad_sha256"],
                            decoder_lumps=after_ammo["lumps"],
                            control_screenshot_sha256=control_ammo["screenshot_sha256"],
                            after_screenshot_sha256=after_ammo["screenshot_sha256"]),
            owner_reaped=False, owner_returncode=None)
        # Capture process and source identity after preserving the post-stop payload.
        assert _source_hashes(game) == PINS
        result["runtime_sha256"] = _sha(runtime["dosbox"])
        rpc.close()
        assert owner.poll() is not None and owner.returncode == 0
        result["owner_reaped"] = True
        result["owner_returncode"] = owner.returncode
        return result
    finally:
        rpc.close()


def test_paired_original_doom_e1m1_pistol_sfx_at_shared_leveltime_landmarks(tmp_path):
    if os.environ.get("FDISBULL_REQUIRE_DOOM_PISTOL_SFX_PAIRED") != "1":
        pytest.skip("Set FDISBULL_REQUIRE_DOOM_PISTOL_SFX_PAIRED=1 for pinned private Doom inputs")
    checkout = Path(__file__).resolve().parents[1]
    output = Path(tmp_path).resolve(strict=True)
    try:
        output.relative_to(checkout)
    except ValueError:
        pass
    else:
        pytest.fail("Private Doom captures must stay outside the source checkout")
    # Imports are inside the gated test so collection needs no private media,
    # emulator binaries, or optional numerical package.
    from support.doom_gameplay import runtime_inputs

    runtime = runtime_inputs()
    qemu_runtime = qemu_runtime_inputs()
    runtime["checkpoint_tool"] = qemu_runtime["checkpoint_tool"]
    source = runtime["source"]
    assert _source_hashes(source) == PINS
    reference, reference_rate = _read_dspistol(source / "DOOM.WAD")
    qemu = _run_qemu(tmp_path / "qemu", runtime, reference, reference_rate)
    dosbox = _run_dosbox(tmp_path / "dosbox", runtime, reference, reference_rate)
    assert qemu["endpoint_tics"] == dict(start=START_TIC, control_end=CONTROL_END_TIC,
                                         shot_end=SHOT_END_TIC)
    assert dosbox["endpoint_tics"] == dict(start=START_TIC, control_end=CONTROL_END_TIC,
                                           shot_end=SHOT_END_TIC)
    assert qemu["source_sha256"] == dosbox["source_sha256"] == PINS["DOOM.EXE"]
    assert qemu["ammunition"]["after"] == 49
    assert qemu["ammunition"]["control"] == 50
    assert dosbox["ammunition"]["after"] == 49
    assert dosbox["ammunition"]["control"] == 50
    assert qemu["audio"]["control_correlation"]["score"] < CORRELATION_THRESHOLD
    assert dosbox["audio"]["control_correlation"]["score"] < CORRELATION_THRESHOLD
    assert qemu["audio"]["shot_correlation"]["score"] >= CORRELATION_THRESHOLD
    assert dosbox["audio"]["shot_correlation"]["score"] >= CORRELATION_THRESHOLD
    assert qemu["audio"]["shot_window"]["dropped_frames"] == 0
    assert dosbox["audio"]["shot_window"]["dropped_frames"] is None
    assert qemu["owner_reaped"] and dosbox["owner_reaped"]
    assert _source_hashes(source) == PINS
    receipt = dict(format="fdisbull-paired-doom-pistol-sfx-1",
        scope="private pinned original Doom E1M1: source-qualified tic64-to84 no-shot control, one Ctrl shot at tic84, source-qualified stop at tic114",
        inputs=dict(pins=PINS, source_wad_sha256=PINS["DOOM.WAD"],
                    reference_lump="DSPISTOL", reference_sample_sha256=hashlib.sha256(reference).hexdigest(),
                    reference_rate_hz=reference_rate,
                    reference_guard_samples_removed_per_end=REFERENCE_GUARD_SAMPLES),
        config=dict(qemu=QEMU_ARGUMENTS, dosbox= DOSBOX_ARGUMENTS,
                    note="Neither argument set contains -nosound; both use the pinned DEFAULT.CFG."),
        sample_match=dict(criterion="centered stereo-to-mono normalized correlation against WAD DSPISTOL",
            threshold=CORRELATION_THRESHOLD, bounded_pitch_ratios=PITCH_RATIOS,
            pitch_range_note="fixed 1/128 steps over [110/128, 148/128], bracketing original 113..144/128",
            pcm_identity_claim=False, sound_call_pc_claim=False),
        clock_scope="Engine-local guest clock anchors; no cross-engine clock conversion or onset-ms claim.",
        bda_scope="Raw BDA 0x46C dword anchors only; no nominal tick-period conversion.",
        dosbox_capture_limit="DX-CAPTURE payload is observed after session.stop; exact zero-size placeholder RIFF headers are accepted as available aligned bytes, completeness stays unknown, and only bytes within observed live frontiers are searched for the shot.",
        qemu=qemu, dosbox=dosbox)
    (tmp_path / "paired-doom-pistol-sfx.json").write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n")
