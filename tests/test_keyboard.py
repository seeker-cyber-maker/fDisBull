"""Guest controller input contracts, including real BIOS consumption."""

import base64
import pytest

from fdisbull.debug_script import validate_script
from fdisbull.project import Project
from test_debugger import emulator
from test_dos_loader import mz_file
from fdisbull.keyboard_input import validate_keyboard


def assert_keyboard_idle(debug):
    state = debug.keyboard.state()["keyboard"]
    assert state["pending_events"] == 0
    assert state["owned_keys"] == 0
    assert state["queued_guest_ms"] == 0
    assert state["frame_keys"] == []


def checkpoint_at_bios_callback(debug, address, breakpoint, name):
    for attempt in range(5):
        try:
            registers = debug.registers()
            assert int(registers["cs"], 16) == int(address["segment"], 16)
            assert int(registers["ip"], 16) == int(address["offset"], 16)
            assert debug.memory("1000:0100", length=2)["hex"] == "0000"
            return debug.save_state(name), breakpoint
        except Exception as exc:
            if "VGA mode change is pending" not in str(exc) or attempt == 4:
                raise
            # The layers backend can still be completing mode 13h when the
            # callback breakpoint first fires. Disarm, let the video state
            # settle, re-arm and hit the same callback before checkpointing.
            debug.delete_breakpoint(breakpoint["breakpoint_id"])
            debug.run(guest_ms=20, timeout_ms=5000, fast_forward=True)
            breakpoint = debug.call(
                "breakpoints.create",
                dict(kind="execution", address=address, once=False),
            )
            assert (
                debug.run(timeout_ms=5000, fast_forward=True)["outcome"] == "breakpoint"
            )
    raise AssertionError("unreachable")


def test_real_continue_at_bios_callback_does_not_invent_keyboard_input(
    tmp_path, emulator
):
    # Each completed BIOS read must account for exactly one counter increment.
    binary = tmp_path / "CALLBACK.EXE"
    binary.write_bytes(
        mz_file(
            bytes.fromhex("b81300cd100e1f30e4cd16ff060001ebf6") + bytes(1024),
            ss=0,
            sp=0x400,
        )
    )
    with Project.create(tmp_path / "callback.fdb", binary) as project:
        project.analyze(max_instructions=30)
        with project.debugger(emulator, tmp_path) as debug:
            # Native-ROM instrumentation for this backend regression only. The
            # project API continues to reject addresses outside its MZ regions.
            vector = debug.call(
                "memory.read",
                dict(address=dict(space="linear", offset="0x00000058"), length=4),
            )
            data = base64.b64decode(vector["data_base64"], validate=True)
            offset = int.from_bytes(data[:2], "little") + 1
            segment = int.from_bytes(data[2:], "little")
            address = dict(
                space="segmented", segment=f"0x{segment:04X}", offset=f"0x{offset:08X}"
            )
            opcode = debug.call("memory.read", dict(address=address, length=4))
            assert (
                base64.b64decode(opcode["data_base64"], validate=True)[:2]
                == b"\xfe\x38"
            )
            bp = debug.call(
                "breakpoints.create",
                dict(kind="execution", address=address, once=False),
            )
            assert (
                debug.run(timeout_ms=5000, fast_forward=True)["outcome"] == "breakpoint"
            )
            registers = debug.registers()
            assert (
                int(registers["cs"], 16) == segment
                and int(registers["ip"], 16) == offset
            )
            assert debug.memory("1000:0100", length=2)["hex"] == "0000"
            checkpoint, bp = checkpoint_at_bios_callback(
                debug, address, bp, "bios-callback.sav"
            )
            debug.delete_breakpoint(bp["breakpoint_id"])
            for restored in (False, True):
                if restored:
                    debug.load_state(checkpoint["artifact"])
                assert (
                    debug.run(guest_ms=100, timeout_ms=5000, fast_forward=True)[
                        "outcome"
                    ]
                    == "guest_time"
                )
                assert debug.memory("1000:0100", length=2)["hex"] == "0000"
                debug.keyboard.press("a", hold_ms=20, gap_ms=20)
                assert (
                    debug.run(guest_ms=100, timeout_ms=5000, fast_forward=True)[
                        "outcome"
                    ]
                    == "guest_time"
                )
                assert debug.memory("1000:0100", length=2)["hex"] == "0100"


@pytest.mark.parametrize(
    "options",
    [
        {"text": ""},
        {"text": "x" * 65},
        {"text": "nul\0"},
        {"text": "\u00e9"},
        {"key": "ENTER"},
        {"key": "made-up"},
        {"key": "enter", "hold_ms": True},
        {"key": "enter", "gap_ms": 0},
        {"key": "enter", "modifiers": ["ctrl", "ctrl"]},
        {"key": "shift", "modifiers": ["shift"]},
        {"key": "enter", "modifiers": "ctrl"},
    ],
)
def test_keyboard_validation(options):
    with pytest.raises(ValueError):
        validate_keyboard(**options)


def test_keyboard_script_rejects_bad_later_input_before_execution():
    script = {
        "format": "fdisbull-script-1",
        "steps": [
            {"op": "keyboard.press", "key": "enter"},
            {"op": "keyboard.type", "text": "name\u2603"},
        ],
    }
    with pytest.raises(ValueError, match="ASCII"):
        validate_script(script)
    validate_script(
        {
            "format": "fdisbull-script-1",
            "steps": [
                {"op": "keyboard.press", "key": "left", "modifiers": ["ctrl"]},
                {"op": "keyboard.type", "text": "Agent 16!"},
            ],
        }
    )


@pytest.fixture
def keyboard_game(tmp_path):
    # Read BIOS ASCII/scan-code pairs until Enter; keep results at DS:0100.
    # push cs; pop ds; push cs; pop es; mov di,0100; xor ah,ah; int16; stosw;
    # cmp al,0d; jne read; jmp $ (stop at offset 10h).
    binary = tmp_path / "KEYS.EXE"
    binary.write_bytes(
        mz_file(
            bytes.fromhex("0e1f0e07bf000130e4cd16ab3c0d75f7ebfe") + bytes(1024),
            ss=0,
            sp=0x400,
        )
    )
    path = tmp_path / "keys.fdb"
    with Project.create(path, binary) as db:
        db.analyze(max_instructions=20)
    return path, binary


def test_real_keyboard_press_type_script_and_restore(keyboard_game, emulator, tmp_path):
    path, binary = keyboard_game
    with Project(path) as db, db.debugger(emulator, binary.parent) as debug:
        checkpoint = debug.save_state("before-input.sav")
        bp = debug.breakpoint("1000:0010")
        result = debug.keyboard.type("Az 19!?", hold_ms=20, gap_ms=20)
        assert result["accepted"] and result["delivery"] == "queued"
        with pytest.raises(ValueError, match="keyboard"):
            debug.save_state("pending.sav")
        with pytest.raises(Exception, match="pending keyboard"):
            debug.call("state.save", {"path": str(tmp_path / "pending-native.sav")})
        assert not (tmp_path / "pending-native.sav").exists()
        with pytest.raises(Exception, match="pending"):
            debug.keyboard.press("enter")
        debug.run(guest_ms=1200, timeout_ms=5000, fast_forward=True)
        assert_keyboard_idle(debug)
        script = {
            "format": "fdisbull-script-1",
            "steps": [
                {"op": "keyboard.press", "key": "backspace"},
                {"op": "run", "guest_ms": 200, "timeout_ms": 3000},
                {"op": "keyboard.press", "key": "enter"},
                {"op": "run", "timeout_ms": 3000, "expect": "breakpoint"},
                {"op": "screenshot", "name": "keyboard.png"},
            ],
        }
        report = debug.script(script)
        assert report["ok"], report
        data = debug.memory("1000:0100", length=18)["hex"]
        assert bytes.fromhex(data)[::2] == b"Az 19!?\x08\r"
        # Finish Enter's release before saving, even though the BP stopped us.
        debug.delete_breakpoint(bp["breakpoint_id"])
        debug.run(guest_ms=150, timeout_ms=3000, fast_forward=True)
        debug.save_state("completed.sav")
        debug.load_state(checkpoint["artifact"])
        assert debug.keyboard.state()["keyboard"]["pending_events"] == 0
        bp = debug.breakpoint("1000:0010")
        report = debug.script(
            {
                "format": "fdisbull-script-1",
                "steps": [
                    {"op": "keyboard.type", "text": "Restored\n"},
                    {"op": "run", "timeout_ms": 5000, "expect": "breakpoint"},
                ],
            }
        )
        assert report["ok"], report
        assert (
            bytes.fromhex(debug.memory("1000:0100", length=18)["hex"])[::2]
            == b"Restored\r"
        )
        debug.project.debug_export(
            report["artifact"], tmp_path / "keyboard-script.json"
        )
        assert (tmp_path / "keyboard-script.json").is_file()


def test_real_keyboard_chords_atomic_rejection_and_pending_restore(
    keyboard_game, emulator
):
    path, binary = keyboard_game
    with Project(path) as db, db.debugger(emulator, binary.parent) as debug:
        checkpoint = debug.save_state("clean.sav")
        with pytest.raises(Exception, match="ASCII"):
            debug.call("input.keyboard.type", {"text": "valid\u2603"})
        assert debug.keyboard.state()["keyboard"]["pending_events"] == 0
        debug.keyboard.press("shift", hold_ms=1000)
        debug.run(guest_ms=10, timeout_ms=3000, fast_forward=True)
        assert debug.keyboard.state()["keyboard"]["owned_keys"] == 1
        debug.load_state(checkpoint["artifact"])
        assert debug.keyboard.state()["keyboard"]["pending_events"] == 0
        debug.keyboard.press("a", modifiers=["shift"])
        debug.run(guest_ms=200, timeout_ms=3000, fast_forward=True)
        debug.keyboard.press("left")
        debug.run(guest_ms=200, timeout_ms=3000, fast_forward=True)
        debug.keyboard.press("f1")
        debug.run(guest_ms=200, timeout_ms=3000, fast_forward=True)
        assert debug.memory("1000:0100", length=6)["hex"] == "411e004b003b"
        assert debug.keyboard.state()["keyboard"]["owned_keys"] == 0


@pytest.mark.parametrize("hold_ms,expected_control", [(80, 0), (500, 4)])
def test_real_keyboard_delivery_and_late_modifier_poll(
    tmp_path, emulator, hold_ms, expected_control
):
    """A delivered pulse can expire before a target samples modifier state.

    The authored guest waits four BIOS clock ticks, samples keyboard flags once,
    and stores the Control bit plus a completion byte. Timing comes from the
    emulated clock, not host sleep or instruction counts. No game is required.
    """
    # push cs; pop ds; sti; xor ah,ah; int 1a; mov bx,dx
    # wait: xor ah,ah; int 1a; sub dx,bx; cmp dx,4; jb wait
    # mov ah,02; int 16; and al,04; mov [0201],al
    # mov byte [0202],1; done: jmp done
    code = bytes.fromhex(
        "0e1ffb30e4cd1a89d330e4cd1a29da83fa0472f5b402cd162404a20102c606020201ebfe"
    )
    binary = tmp_path / "POLL.EXE"
    binary.write_bytes(mz_file(code + bytes(1024), ss=0, sp=0x400))
    path = tmp_path / "poll.fdb"
    with Project.create(path, binary) as project:
        project.analyze(max_instructions=32)
        with project.debugger(emulator, binary.parent) as debug:
            entered = debug.breakpoint("1000:0003")
            assert (
                debug.run(timeout_ms=5000, fast_forward=True)["outcome"] == "breakpoint"
            )
            debug.delete_breakpoint(entered["breakpoint_id"])
            assert debug.memory("1000:0201", length=2)["hex"] == "0000"
            finished = debug.breakpoint("1000:0022")
            queued = debug.keyboard.press("ctrl", hold_ms=hold_ms, gap_ms=40)
            assert queued["accepted"] and queued["delivery"] == "queued"
            assert (
                debug.run(timeout_ms=5000, fast_forward=True)["outcome"] == "breakpoint"
            )
            observed = bytes.fromhex(debug.memory("1000:0201", length=2)["hex"])
            assert observed == bytes([expected_control, 1])
            queue = debug.keyboard.state()["keyboard"]
            if expected_control == 0:
                # Delivery completed, but the application observed no held Ctrl.
                assert queue["pending_events"] == 0
                assert queue["owned_keys"] == 0
                assert queue["queued_guest_ms"] == 0
            else:
                assert queue["owned_keys"] == 1 and queue["pending_events"] > 0
            # Explicitly permit release; never resume through an armed stop.
            debug.delete_breakpoint(finished["breakpoint_id"])
            assert (
                debug.run(guest_ms=700, timeout_ms=5000, fast_forward=True)["outcome"]
                == "guest_time"
            )
            assert_keyboard_idle(debug)
            assert debug.memory("1000:0201", length=2)["hex"] == observed.hex()


def test_real_keyboard_mid_dialog_checkpoint_restore(keyboard_game, emulator):
    path, binary = keyboard_game
    with Project(path) as db, db.debugger(emulator, binary.parent) as debug:
        wait = debug.breakpoint("1000:0009")
        assert debug.run(timeout_ms=5000, fast_forward=True)["outcome"] == "breakpoint"
        debug.delete_breakpoint(wait["breakpoint_id"])
        debug.run(guest_ms=20, timeout_ms=3000, fast_forward=True)
        checkpoint = debug.save_state("waiting-for-name.sav")

        end = debug.breakpoint("1000:0010")
        debug.keyboard.type("TIGA16\n")
        assert debug.run(timeout_ms=5000, fast_forward=True)["outcome"] == "breakpoint"
        assert (
            bytes.fromhex(debug.memory("1000:0100", length=14)["hex"])[::2]
            == b"TIGA16\r"
        )
        debug.delete_breakpoint(end["breakpoint_id"])

        restored = debug.load_state(checkpoint["artifact"])
        assert restored["framebuffer"] == "invalidated_until_next_completed_frame"
        assert_keyboard_idle(debug)
        debug.run(guest_ms=50, timeout_ms=3000, fast_forward=True)
        assert debug.screenshot("restored-dialog.png")["artifact"]

        end = debug.breakpoint("1000:0010")
        debug.keyboard.type("TIGA16\n")
        assert debug.run(timeout_ms=5000, fast_forward=True)["outcome"] == "breakpoint"
        assert (
            bytes.fromhex(debug.memory("1000:0100", length=14)["hex"])[::2]
            == b"TIGA16\r"
        )


@pytest.mark.parametrize("prefix", ["", "TI"])
def test_real_keyboard_mid_dialog_checkpoint_fresh_session(
    keyboard_game, emulator, prefix
):
    path, binary = keyboard_game
    expected = b"TIGA16\r"
    suffix = "TIGA16"[len(prefix) :] + "\n"
    with Project(path) as db:
        with db.debugger(emulator, binary.parent) as debug:
            wait = debug.breakpoint("1000:0009")
            assert (
                debug.run(timeout_ms=5000, fast_forward=True)["outcome"] == "breakpoint"
            )
            debug.delete_breakpoint(wait["breakpoint_id"])
            debug.run(guest_ms=20, timeout_ms=3000, fast_forward=True)
            if prefix:
                debug.keyboard.type(prefix)
                debug.run(guest_ms=300, timeout_ms=3000, fast_forward=True)
                assert bytes.fromhex(
                    debug.memory("1000:0100", length=2 * len(prefix))["hex"]
                )[::2] == prefix.encode("ascii")
            assert_keyboard_idle(debug)
            checkpoint = debug.save_state("waiting-for-name-fresh.sav")
            first_process = debug.rpc.process
            debug.breakpoint("1000:0010")
            debug.keyboard.type(suffix)
            assert (
                debug.run(timeout_ms=5000, fast_forward=True)["outcome"] == "breakpoint"
            )
            assert (
                bytes.fromhex(debug.memory("1000:0100", length=14)["hex"])[::2]
                == expected
            )
        assert first_process.poll() is not None

    # Reopen both project and emulator, not just the native state in one session.
    with Project(path) as db, db.debugger(emulator, binary.parent) as debug:
        assert debug.rpc.process.pid != first_process.pid
        restored = debug.load_state(checkpoint["artifact"])
        assert restored["framebuffer"] == "invalidated_until_next_completed_frame"
        assert_keyboard_idle(debug)
        debug.run(guest_ms=50, timeout_ms=3000, fast_forward=True)
        assert debug.screenshot("fresh-restored-dialog.png")["artifact"]
        if prefix:
            assert bytes.fromhex(
                debug.memory("1000:0100", length=2 * len(prefix))["hex"]
            )[::2] == prefix.encode("ascii")
        debug.breakpoint("1000:0010")
        debug.keyboard.type(suffix)
        assert debug.run(timeout_ms=5000, fast_forward=True)["outcome"] == "breakpoint"
        assert (
            bytes.fromhex(debug.memory("1000:0100", length=14)["hex"])[::2] == expected
        )
