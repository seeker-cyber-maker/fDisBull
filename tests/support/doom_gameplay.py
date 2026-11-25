"""Small private-input helper for paired Doom E1M1 physical-input probes.

All commercial files, project databases, and captured frames stay under the
caller's pytest temporary directory. The HUD reader derives digit masks and
palette colors from the pinned WAD and reports only the bounded shot result.
It does not claim gameplay parity.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import struct

from PIL import Image, ImageChops

from fdisbull.project import Project
from support.doom_le_qemu import PINS


ENV_NAMES = (
    "FDISBULL_DOOM_LE_SOURCE",
    "FDISBULL_DOSBOX",
    "FDISBULL_QEMU_DOS",
    "FDISBULL_QEMU_DOS_BOOT_IMAGE",
    "FDISBULL_QEMU_DOS_MCOPY",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runtime_inputs():
    missing = [name for name in ENV_NAMES if not os.environ.get(name)]
    if missing:
        raise RuntimeError("Missing private Doom gameplay inputs: " + ", ".join(missing))
    source = Path(os.environ["FDISBULL_DOOM_LE_SOURCE"]).expanduser().resolve(strict=True)
    dosbox = Path(os.environ["FDISBULL_DOSBOX"]).expanduser().resolve(strict=True)
    qemu = Path(os.environ["FDISBULL_QEMU_DOS"]).expanduser().resolve(strict=True)
    boot = Path(os.environ["FDISBULL_QEMU_DOS_BOOT_IMAGE"]).expanduser().resolve(strict=True)
    # Preserve an mtools multicall invocation name rather than resolving symlinks.
    mcopy = Path(os.environ["FDISBULL_QEMU_DOS_MCOPY"]).expanduser().absolute()
    for label, path in (("DOSBox-X", dosbox), ("QEMU", qemu), ("mcopy", mcopy)):
        if not path.is_file() or not os.access(path, os.X_OK):
            raise ValueError(f"{label} must select an executable file: {path}")
    if not boot.is_file():
        raise ValueError(f"QEMU DOS boot image must be a file: {boot}")
    for name, expected in PINS.items():
        path = source / name
        if not path.is_file() or digest(path) != expected:
            raise ValueError(f"Pinned private Doom input mismatch: {path}")
    return dict(source=source, dosbox=dosbox, qemu=qemu, boot=boot, mcopy=mcopy,
                firmware=os.environ.get("FDISBULL_QEMU_DOS_FIRMWARE"),
                boot_sha256=digest(boot),
                binary_sha256=dict(dosbox=digest(dosbox), qemu=digest(qemu)))


def stage_game(root: Path, source: Path) -> Path:
    game = root / "game"
    game.mkdir(parents=True)
    for name in PINS:
        shutil.copyfile(source / name, game / name)
    assert {name: digest(game / name) for name in PINS} == PINS
    return game


DOOM_ARGUMENTS = "-warp 1 1 -skill 2 -nomonsters -nosound -nomouse"
_WAD_SHA256 = PINS["DOOM.WAD"]
_AMMO_DIGITS = tuple(f"STTNUM{digit}" for digit in range(10))
_AMMO_RIGHT = 44       # Original Doom 1.9 status number right edge.
_AMMO_TOP = 171         # Status bar y=168 plus ST_AMMOY=3.
_AMMO_CROP = (14, 170)  # Origin of the small crop retained by capture_statusbar.
_PALETTE_TOLERANCE = 5  # Covers the two qualified VGA palette expansions.


def _wad_lumps(data: bytes):
    if len(data) < 12 or data[:4] not in (b"IWAD", b"PWAD"):
        raise ValueError("Not a Doom WAD")
    count, directory = struct.unpack_from("<ii", data, 4)
    if count < 1 or directory < 12 or directory + count * 16 > len(data):
        raise ValueError("Invalid Doom WAD directory")
    lumps = {}
    for index in range(count):
        offset, length = struct.unpack_from("<ii", data, directory + index * 16)
        name = data[directory + index * 16 + 8:directory + index * 16 + 16]
        try:
            key = name.rstrip(b"\0").decode("ascii")
        except UnicodeDecodeError as error:
            raise ValueError("Invalid non-ASCII WAD lump name") from error
        if offset < 0 or length < 0 or offset + length > len(data):
            raise ValueError(f"WAD lump {key!r} lies outside the file")
        lumps[key] = data[offset:offset + length]
    return lumps


def _decode_patch(data: bytes):
    if len(data) < 8:
        raise ValueError("Truncated Doom patch header")
    width, height, left, top = struct.unpack_from("<hhhh", data)
    if not 1 <= width <= 64 or not 1 <= height <= 64 or 8 + width * 4 > len(data):
        raise ValueError("Invalid Doom patch dimensions")
    columns = []
    for column in struct.unpack_from(f"<{width}I", data, 8):
        if column < 8 + width * 4 or column >= len(data):
            raise ValueError("Invalid Doom patch column offset")
        pixels = [-1] * height
        cursor, previous_top = column, -1
        while True:
            if cursor >= len(data):
                raise ValueError("Unterminated Doom patch column")
            top_delta = data[cursor]
            if top_delta == 255:
                break
            if cursor + 4 > len(data):
                raise ValueError("Truncated Doom patch post")
            post_length = data[cursor + 1]
            if cursor + post_length + 4 > len(data):
                raise ValueError("Doom patch post exceeds lump")
            if top_delta <= previous_top:
                top_delta += previous_top
            previous_top = top_delta
            if top_delta + post_length > height:
                raise ValueError("Doom patch post exceeds image height")
            for row, color_index in enumerate(data[cursor + 3:cursor + 3 + post_length]):
                pixels[top_delta + row] = color_index
            cursor += post_length + 4
        columns.append(pixels)
    return dict(width=width, height=height, left=left, top=top, columns=columns)


def decode_ammo_from_wad(wad_path: Path, statusbar: Image.Image) -> dict:
    """Recognize the two-digit ammo HUD using original STTNUM patches/PLAYPAL."""
    wad_data = Path(wad_path).read_bytes()
    if hashlib.sha256(wad_data).hexdigest() != _WAD_SHA256:
        raise ValueError("Doom HUD decoder requires the pinned original DOOM.WAD")
    lumps = _wad_lumps(wad_data)
    if not all(name in lumps for name in (*_AMMO_DIGITS, "PLAYPAL")):
        raise ValueError("Pinned Doom WAD lacks status-number patches or PLAYPAL")
    palette_data = lumps["PLAYPAL"]
    if len(palette_data) < 768:
        raise ValueError("Doom PLAYPAL is truncated")
    palette = [tuple(palette_data[offset:offset + 3]) for offset in range(0, 768, 3)]
    digits = [_decode_patch(lumps[name]) for name in _AMMO_DIGITS]
    frame = statusbar.convert("RGB")
    if frame.size != (30, 20):
        raise ValueError(f"Expected the 30x20 Doom ammo crop, received {frame.size}")

    scores = []
    for value in range(100):
        x = _AMMO_RIGHT - _AMMO_CROP[0]
        y = _AMMO_TOP - _AMMO_CROP[1]
        matched = mismatched = expected_pixels = 0
        for character in reversed(str(value)):
            patch = digits[int(character)]
            x -= patch["width"]
            patch_x = x - patch["left"]
            patch_y = y - patch["top"]
            for dx, column in enumerate(patch["columns"]):
                for dy, color_index in enumerate(column):
                    if color_index < 0:
                        continue
                    expected_pixels += 1
                    screen_x, screen_y = patch_x + dx, patch_y + dy
                    if not (0 <= screen_x < frame.width and 0 <= screen_y < frame.height):
                        mismatched += 1
                        continue
                    actual = frame.getpixel((screen_x, screen_y))
                    expected = palette[color_index]
                    if max(abs(actual[channel] - expected[channel]) for channel in range(3)) <= _PALETTE_TOLERANCE:
                        matched += 1
                    else:
                        mismatched += 1
        scores.append((matched, mismatched, expected_pixels, value))

    best_matches = max(row[0] for row in scores)
    best = [row for row in scores if row[0] == best_matches and row[1] == 0]
    if best_matches < 300 or len(best) != 1:
        ranked = sorted(scores, key=lambda row: (-row[0], row[1], row[3]))[:3]
        raise ValueError(f"Doom ammo digits are missing or ambiguous: {ranked}")
    matched, _, expected_pixels, value = best[0]
    return dict(value=value, matched_pixels=matched, expected_pixels=expected_pixels,
                wad_sha256=_WAD_SHA256, lumps=list(_AMMO_DIGITS))


def launch(project: Project, runtime, game: Path, backend: str, *, on_spawn=None):
    if backend == "dosbox":
        return project.debugger(str(runtime["dosbox"]), game,
                                dos_arguments=DOOM_ARGUMENTS, _on_spawn=on_spawn)
    if backend == "qemu-dos":
        return project.debugger(
            str(runtime["qemu"]), game, backend="qemu-dos",
            dos_boot_image=str(runtime["boot"]), dos_mcopy=str(runtime["mcopy"]),
            dos_directory=str(game), dos_startup_batch="FDAUTO.BAT",
            qemu_transport="pipe", qemu_firmware=runtime["firmware"],
            qemu_clock="virtual", dos_arguments=DOOM_ARGUMENTS,
            boot_timeout_ms=35000, _on_spawn=on_spawn,
        )
    else:
        raise ValueError("Unknown Doom gameplay backend")


def advance(debug, backend: str, milliseconds: int = 1000):
    if backend == "qemu-dos":
        result = debug.clock_advance(milliseconds * 1_000_000, timeout_ms=60000)
        assert result["clock_budget"]["deadline_reached"], result
        return result
    return debug.run(timeout_ms=60000,
                     guest_ms=milliseconds)


def capture_statusbar(project: Project, debug, root: Path, label: str):
    """Export and verify a stored screenshot; return its normalized HUD crop."""
    output = root / (label + ".png")
    receipt = debug.screenshot(name=label + ".png")
    project.debug_export(receipt["artifact"], output)
    assert digest(output) == receipt["sha256"]
    with Image.open(output) as source:
        image = source.convert("RGB")
        image.load()
        width, height = image.size
        assert width >= 320 and height >= 200, image.size
        assert width * 200 == height * 320, f"Unexpected Doom frame aspect ratio: {image.size}"
        # Doom's status bar occupies the bottom 32 rows of a 320x200 frame.
        normalized = image.resize((320, 200), Image.Resampling.NEAREST)
        # Doom 1.9's three-digit ammo value is in this left-side status-bar box.
        crop = normalized.crop((14, 170, 44, 190))
        colors = crop.getcolors(maxcolors=crop.width * crop.height)
        unique_colors = 0 if colors is None else len(colors)
        assert unique_colors > 2, f"Ammo-number crop is blank: {unique_colors} colors"
        crop.save(root / (label + "-statusbar.png"))
    return dict(artifact=receipt["artifact"], sha256=receipt["sha256"],
                dimensions=[width, height], statusbar_unique_colors=unique_colors,
                statusbar=crop)


def statusbar_delta(before, after) -> int:
    diff = ImageChops.difference(before["statusbar"], after["statusbar"])
    raw = diff.tobytes()
    return sum(1 for offset in range(0, len(raw), 3) if raw[offset:offset + 3] != b"\0\0\0")
