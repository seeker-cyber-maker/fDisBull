import os
from pathlib import Path

import pytest

from fdisbull.rom_asm_ghidra import GhidraDecodeSession, decode
from fdisbull.rom_asm import disassemble_rom


HOME = os.environ.get("GHIDRA_HOME")
pytestmark = pytest.mark.skipif(not HOME or not (Path(HOME) / "support/analyzeHeadless").is_file(),
                                reason="GHIDRA_HOME required for real Ghidra session test")


def test_shared_contract_reuses_owned_session():
    with GhidraDecodeSession(ghidra_home=HOME) as session:
        first = disassemble_rom(bytes.fromhex('e0010009'), base_address=0x1000,
            backend='ghidra', ghidra_session=session, mode='word-scan')
        second = disassemble_rom(bytes.fromhex('e002ffff'), base_address=0x2000,
            backend='ghidra', ghidra_session=session, mode='word-scan')
        assert first['engine_lifecycle'] == second['engine_lifecycle'] == 'owned persistent session'
        assert first['session_startup_seconds'] == second['session_startup_seconds'] > 0
        assert first['instructions'][0]['normalized']['operands'] == '#1,r0'
        assert second['instructions'][0]['normalized']['operands'] == '#2,r0'
        assert first['source_sha256'] != second['source_sha256']
        assert second['undecoded_words'][0]['bytes'] == 'ffff'


def test_repeated_images_match_fresh_and_close():
    cases = [(bytes.fromhex("0009e001"), 0x1000, 2, False),
             (bytes.fromhex("e0020009"), 0x2000, 1, False),
             (bytes.fromhex("ffff000900"), 0x1000, 3, True),
             (bytes.fromhex("0009e001"), 0x1000, 2, False)]
    expected = [decode(data, address, limit, ghidra_home=HOME, scan_all_words=scan)["instructions"]
                for data, address, limit, scan in cases]
    with GhidraDecodeSession(ghidra_home=HOME) as session:
        pid = session._proc.pid
        actual = [decode(data, address, limit, session=session, scan_all_words=scan)["instructions"]
                  for data, address, limit, scan in cases]
        assert session._proc.pid == pid
        assert actual == expected
        with pytest.raises(ValueError):
            session.decode(b"\x00", 1, 1)
        assert session.decode(b"\x00", 0, 1)["instructions"] == []
        root = session._root
    assert not root.exists()
    with pytest.raises(RuntimeError, match="not running"):
        session.decode(b"\x00\x09", 0, 1)
    with session:
        assert session.decode(b"\x00\x09", 0, 1)["instructions"][0]["mnemonic"] == "nop"


def test_timeout_closes_owned_process(monkeypatch):
    with GhidraDecodeSession(ghidra_home=HOME) as session:
        root = session._root
        proc = session._proc
        def timeout_wait(path, timeout):
            raise RuntimeError("timed out")
        monkeypatch.setattr(session, "_wait_for", timeout_wait)
        with pytest.raises(RuntimeError, match="timed out"):
            session.decode(b"\x00\x09", 0, 1, timeout=1)
        assert proc.poll() is not None
        assert not root.exists()


def test_same_address_branch_delay_context_matches_fresh():
    cases = [(bytes.fromhex("a0010009e0010009"), False),
             (bytes.fromhex("e0020009a0010009"), True),
             (bytes.fromhex("a0010009e0010009"), False)]
    expected = [decode(data, 0x1000, 4, ghidra_home=HOME, scan_all_words=scan)["instructions"]
                for data, scan in cases]
    with GhidraDecodeSession(ghidra_home=HOME) as session:
        assert [session.decode(data, 0x1000, 4, scan_all_words=scan)["instructions"]
                for data, scan in cases] == expected


@pytest.mark.parametrize("timeout", [True, float("nan"), float("inf"), 0, -1, 3601])
def test_invalid_session_timeout(timeout):
    with pytest.raises(ValueError):
        GhidraDecodeSession(ghidra_home=HOME, timeout=timeout)


def test_session_rejects_unbounded_direct_requests():
    with GhidraDecodeSession(ghidra_home=HOME) as session:
        for data, address, limit, timeout in [
            (b"\0" * 65537, 0, 1, None), (b"\0", True, 1, None),
            (b"\0", 0, True, None), (b"\0", 0, 32769, None),
            (b"\0", 0, 1, float("nan")), (b"\0", 0, 1, 3601),
        ]:
            with pytest.raises(ValueError):
                session.decode(data, address, limit, timeout=timeout)


def test_startup_interrupt_reaps_process_and_removes_temp(monkeypatch):
    session = GhidraDecodeSession(ghidra_home=HOME)
    captured = {}
    def interrupt(path, timeout):
        captured["proc"] = session._proc
        captured["root"] = session._root
        raise KeyboardInterrupt()
    monkeypatch.setattr(session, "_wait_for", interrupt)
    with pytest.raises(KeyboardInterrupt):
        session.__enter__()
    assert captured["proc"].poll() is not None
    assert not captured["root"].exists()


def test_request_interrupt_reaps_process_and_removes_temp(monkeypatch):
    with GhidraDecodeSession(ghidra_home=HOME) as session:
        proc, root = session._proc, session._root
        def interrupt(path, timeout):
            raise KeyboardInterrupt()
        monkeypatch.setattr(session, "_wait_for", interrupt)
        with pytest.raises(KeyboardInterrupt):
            session.decode(b"\x00\x09", 0, 1)
        assert proc.poll() is not None
        assert not root.exists()


def test_queue_timeout_does_not_close_worker():
    import time
    with GhidraDecodeSession(ghidra_home=HOME) as session:
        proc = session._proc
        session._lock.acquire()
        try:
            started = time.monotonic()
            with pytest.raises(RuntimeError, match="waiting for another request"):
                session.decode(b"\x00\x09", 0, 1, timeout=0.01)
            assert time.monotonic() - started < 1
            assert proc.poll() is None
        finally:
            session._lock.release()
        assert session.decode(b"\x00\x09", 0, 1)["instructions"][0]["mnemonic"] == "nop"
