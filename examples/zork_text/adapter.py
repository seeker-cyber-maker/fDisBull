"""Bounded text-screen adapter for the supplied DOS Zork I on fDisBull 0.20.

This reads the displayed 80x25 color text page. It does not read hidden game
state, and a detected prompt is a qualified display heuristic, not a VM hook.
"""
import base64
import hashlib
import time


class ObservationError(RuntimeError):
    pass


def decode_screen(bda, video):
    """Decode BIOS display metadata (0x449..0x484) and page-zero text bytes."""
    if len(bda) != 60 or len(video) != 4000:
        raise ObservationError("incomplete BIOS or text-page read")
    mode = bda[0]
    columns = int.from_bytes(bda[1:3], "little")
    page_offset = int.from_bytes(bda[5:7], "little")
    active_page = bda[0x462 - 0x449]
    rows = bda[0x484 - 0x449] + 1
    col, row = bda[7], bda[8]
    if (mode, columns, rows, active_page, page_offset) != (3, 80, 25, 0, 0):
        raise ObservationError("unsupported video mode, dimensions or page")
    if not (0 <= row < rows and 0 <= col < columns):
        raise ObservationError("cursor outside text page")
    lines = [video[i:i + 160:2].decode("cp437").rstrip() for i in range(0, 4000, 160)]
    # Require the cursor immediately after a bare prompt and no later text.
    prompt = lines[row] == ">" and col == 1 and not any(lines[row + 1:])
    return {"mode": mode, "cursor": [row, col], "status": lines[0],
            "lines": lines, "text": "\n".join(lines).rstrip(), "prompt_candidate": prompt,
            "screen_sha256": hashlib.sha256(video).hexdigest()}


def read_memory(session, address, length):
    result = session.call("memory.read", {"address": {"space": "linear", "offset": f"0x{address:08X}"}, "length": length})
    try:
        data = base64.b64decode(result["data_base64"], validate=True)
    except (KeyError, ValueError) as exc:
        raise ObservationError("invalid memory reply") from exc
    if len(data) != length:
        raise ObservationError("short memory reply")
    return data


class ZorkScreenAdapter:
    def __init__(self, session, *, slice_ms=300, max_slices=30):
        if not 1 <= slice_ms <= 2000 or not 2 <= max_slices <= 100:
            raise ValueError("invalid wait budget")
        self.session, self.slice_ms, self.max_slices = session, slice_ms, max_slices
        self.ready = None

    def observe(self):
        # The guest is stopped between calls. This read is not a persisted screenshot.
        return decode_screen(read_memory(self.session, 0x449, 60), read_memory(self.session, 0xB8000, 4000))

    def wait_prompt(self, *, changed_from=None):
        self.ready = None
        prior = None
        for _ in range(self.max_slices):
            result = self.session.run(guest_ms=self.slice_ms, fast_forward=True, timeout_ms=5000)
            if result.get("outcome") != "guest_time":
                self.ready = None
                raise ObservationError("unexpected guest stop: " + str(result.get("outcome")))
            screen = self.observe()
            keys = self.session.keyboard_state()["keyboard"]
            idle = keys["pending_events"] == 0 and keys["owned_keys"] == 0
            current = (screen["screen_sha256"], tuple(screen["cursor"]))
            qualifies = screen["prompt_candidate"] and idle and screen["screen_sha256"] != changed_from
            if qualifies and current == prior:
                self.ready = screen
                return screen
            prior = current if qualifies else None
        self.ready = None
        raise ObservationError("prompt not confirmed within budget; guest outcome unknown")

    def command(self, text):
        if self.ready is None:
            raise ObservationError("no confirmed prompt")
        if not isinstance(text, str) or not 1 <= len(text) <= 63 or any(not 32 <= ord(c) <= 126 for c in text):
            raise ValueError("command requires 1..63 printable ASCII characters")
        before = self.observe()
        keys = self.session.keyboard_state()["keyboard"]
        if before["screen_sha256"] != self.ready["screen_sha256"] or not before["prompt_candidate"] or keys["pending_events"] or keys["owned_keys"]:
            self.ready = None
            raise ObservationError("prompt or input state changed; reacquire")
        self.ready = None  # A timeout after delivery must not permit a blind retry.
        queued = self.session.keyboard_type(text + "\n")
        if queued.get("accepted") is not True or queued.get("delivery") != "queued":
            raise ObservationError("keyboard delivery not confirmed; guest outcome unknown")
        return self.wait_prompt(changed_from=before["screen_sha256"])


def timed(call):
    start = time.perf_counter()
    value = call()
    return value, round(time.perf_counter() - start, 3)
