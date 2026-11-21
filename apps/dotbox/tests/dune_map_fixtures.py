"""Authored map memory and native protocol events, independent of the selector.

These fixtures model documented wire boundaries. They neither load commercial
bytes nor claim that the authored event schedule qualifies the real game.
"""
from collections import deque
from copy import deepcopy
import hashlib
import struct

from test_dune_progress import Peer, progress, registers
from test_dune_progress_native import CAPABILITIES
from test_dune_ui_reader import BASE, authored_map, put_word, reader


MAP_DISPATCH, MAP_CALLBACK, SITE_ACCEPT = 0xD2FE, 0x4D4E, 0x4D74
VECTOR, TARGET, ORIGIN = 0x2176, 0x011C, 0x0100
VECTOR_WORDS = (0x4D9F, 0x4D4E, 0x133D, 0x133D, 0x133D, 0x4D9F, 0x4D9F)
TARGET_XY = (120, 80)
VIEWPORT = (81, 45, 241, 134)


def map_ram(source):
    ram = authored_map()
    put_word(ram, 0x2824, 0x2794)
    # Authored ordinary row, outside the selected map point.
    for offset, value in ((0x2794, 0x00FF), (0x2796, 1), (0x2798, 0x1111),
                          (0x279A, 2), (0x279C, 0x1112),
                          (0x4258, ORIGIN), (0x2A5C, VECTOR)):
        put_word(ram, offset, value)
    ram[BASE + 0x11D6] = 4
    struct.pack_into("<4H", ram, BASE + 0x423F, *VIEWPORT)
    struct.pack_into("<7H", ram, BASE + VECTOR, *VECTOR_WORDS)
    # These code witnesses end before the authored DS region. Copying the
    # entire near-code image would overwrite the independent site records.
    code_ranges = [(0x4D4E, 0x4DF7), (0x6ABD, 0x6AD6), (0x6C0D, 0x6C70),
                   (0xD093, 0xD0F2), (0xD26A, 0xD340)]
    code_ranges += [(offset, offset + 5) for offset in
                    (progress.DISPATCH, progress.INPUT_LOOP, *progress.ROW_CALLBACKS,
                     MAP_DISPATCH, MAP_CALLBACK, SITE_ACCEPT)]
    for start, end in code_ranges:
        address = progress.CS * 16 + start
        ram[address:address + end - start] = source[progress.HEADER + start:progress.HEADER + end]
    return ram


class MapPeer(Peer):
    """One queued click encounters callback, acceptance, then input-loop events.

    A configured event delay is paid once across all bounded calls; each frame
    advances fourteen guest milliseconds. Reaching an event costs one further
    guest millisecond. No code under test supplies this schedule or counters.
    """

    def __init__(self, source):
        super().__init__(source)
        self.ram = map_ram(source)
        self.events = deque()
        self.event_delays = {MAP_DISPATCH: 0, SITE_ACCEPT: 0, progress.INPUT_LOOP: 0}
        self.block_at = None
        self.foreign_at = None
        self.uncertain_at = None
        self.on_boundary = None
        self.dispatch_si = VECTOR
        self.dispatch_xy = TARGET_XY
        self.accept_di = TARGET
        self.accept_selected = TARGET
        self.release_at = None
        self.acceptance_observed = False
        self.execution_receipts = []
        self.event_call_indices = {}
        self.after_call = None

    def _registers(self):
        result = registers(self.ip, self.accept_di if self.ip == SITE_ACCEPT else ORIGIN)
        result["general"]["esi"] = hex(self.dispatch_si)
        result["general"]["edx"] = hex(self.dispatch_xy[0])
        result["general"]["ebx"] = hex(self.dispatch_xy[1])
        return result

    def _frame(self):
        self.frames += 1
        self.frame_id += 1
        self.ticks = (self.ticks + 14) % (1 << 32)
        self.ip = 0xD532

    def _bounded_step(self, params):
        before, frames = self.ticks, 0
        frame_limit, guest_limit = params["max_frames"], params["max_guest_ms"]
        self.revision += 1
        while True:
            remaining = guest_limit - ((self.ticks - before) % (1 << 32))
            event = self.events[0] if self.events else None
            if event is None:
                # Repeated ordinary input-loop opportunities after readiness.
                if any(int(entry["address"]["offset"], 16) == progress.INPUT_LOOP
                       for entry in self.entries.values() if "address" in entry):
                    event = {"offset": progress.INPUT_LOOP, "frames": 0}
            offset = event["offset"] if event else None
            if self.uncertain_at in ("execution", offset) and offset is not None:
                raise TimeoutError("Authored lost execution acknowledgement")
            if self.foreign_at == offset and offset is not None:
                self.ip = offset
                self.stop = {"kind": "breakpoint", "breakpoint_id": "foreign",
                             "address": {"space": "segmented", "segment": "0x0824",
                                         "offset": hex(offset)}}
                self.entries["foreign"] = {"breakpoint_id": "foreign", "kind": "execution",
                                           "address": deepcopy(self.stop["address"])}
                cause = "breakpoint"
                break
            if event and not event["frames"] and self.block_at != offset and remaining >= 1:
                self.ticks = (self.ticks + 1) % (1 << 32)
                self.ip = offset
                if self.events and self.events[0] is event:
                    self.events.popleft()
                if offset == SITE_ACCEPT:
                    put_word(self.ram, 0x4258, self.accept_selected)
                    self.acceptance_observed = True
                if self.on_boundary:
                    self.on_boundary(self, offset)
                matching = [(identifier, entry) for identifier, entry in self.entries.items()
                            if "address" in entry and int(entry["address"]["offset"], 16) == offset]
                if matching:
                    identifier, entry = matching[0]
                    del self.entries[identifier]
                    self.probes_seen.append(offset)
                    self.event_call_indices[offset] = len(self.calls) - 1
                    self.stop = {"kind": "breakpoint", "breakpoint_id": identifier,
                                 "address": deepcopy(entry["address"])}
                    cause = "breakpoint"
                    break
                continue
            if frames >= frame_limit:
                self.stop, cause = {"kind": "frame"}, "frame_limit"
                break
            if remaining < 14:
                self.ticks = (self.ticks + remaining) % (1 << 32)
                self.stop, cause = {"kind": "budget"}, "guest_time_limit"
                break
            self._frame()
            frames += 1
            if event and event["frames"]:
                event["frames"] -= 1
        reply = {"session_id": "test-session", "state_revision": self.revision,
                 "completed": cause == "frame_limit", "stop_reason": deepcopy(self.stop),
                 "registers": self._registers(), "guest_ticks": self.ticks,
                 "frame_available": True, "frame_id": self.frame_id, "mode_id": 1,
                 "bounded": {"max_frames": frame_limit, "max_guest_ms": guest_limit,
                             "frames_completed": frames, "guest_tick_bits": 32,
                             "guest_ticks_before": before, "guest_ticks_after": self.ticks,
                             "guest_elapsed_ms": (self.ticks - before) % (1 << 32),
                             "stop_cause": cause}}
        self.execution_receipts.append(deepcopy(reply))
        return reply

    def __call__(self, method, params, timeout_ms):
        if method in ("frame.step", "state.get_registers", "input.mouse.state", "input.mouse.click"):
            self.calls.append((method, deepcopy(params)))
            common = {"session_id": "test-session", "state_revision": self.revision}
            if method == "frame.step":
                assert "max_frames" in params and "max_guest_ms" in params, "Native bounds must be explicit"
                result = self._bounded_step(params)
            elif method == "state.get_registers":
                result = {**common, **self._registers()}
            elif method == "input.mouse.state":
                held = self.release_at is not None and self.ticks < self.release_at
                result = {**common, "mouse": {"buttons": int(held), "owned_buttons": int(held),
                          "pending_release_buttons": int(held), "release_pending": held}}
            else:
                self.click = True
                self.frames = 0
                self.revision += 1
                common["state_revision"] = self.revision
                self.release_at = self.ticks + params["hold_ms"]
                self.events = deque({"offset": offset, "frames": self.event_delays[offset]}
                                    for offset in (MAP_DISPATCH, SITE_ACCEPT, progress.INPUT_LOOP))
                if self.uncertain_at == "click":
                    raise TimeoutError("Authored click may have been delivered")
                result = {**common, "accepted": True, "delivery": "queued"}
        else:
            result = super().__call__(method, params, timeout_ms)
            if method in ("breakpoints.create", "breakpoints.delete"):
                self.revision += 1
                result["state_revision"] = self.revision
        if self.after_call:
            self.after_call(self, method, params, result)
        return result


def make_controller(tmp_path, monkeypatch, *, read_strategy="sparse", wait_strategy="native",
                    mutate_before_ready=None):
    source = b"\x90" * progress.SOURCE_SIZE
    monkeypatch.setattr(progress, "SOURCE_SHA256", hashlib.sha256(source).hexdigest())
    game = tmp_path / "game"
    game.mkdir()
    executable = game / "authored.exe"
    executable.write_bytes(source)
    peer = MapPeer(source)
    if mutate_before_ready:
        mutate_before_ready(peer)
    controller = progress.ProgressController(
        peer, reader.describe, tmp_path / "evidence", session_id="test-session",
        source_path=executable, wait_strategy=wait_strategy, capabilities=CAPABILITIES,
        read_strategy=read_strategy, sparse_reader=reader.describe_sparse,
        structure_reader=reader.read_structure_sparse,
    )
    if wait_strategy != "native":
        return peer, controller, None
    ready = controller.await_ready(max_frames=6)
    assert ready["outcome"] == "input_boundary", ready.get("error")
    peer.calls.clear()
    peer.execution_receipts.clear()
    peer.probes_seen.clear()
    return peer, controller, ready["after"]


def input_calls(peer):
    return [params for method, params in peer.calls if method == "input.mouse.click"]


def execution_calls(peer):
    return [params for method, params in peer.calls if method == "frame.step"]
