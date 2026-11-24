"""Independent Bochs debugger oracle for the authored PAE LE remap fixture.

FDISBULL_BOCHS selects a debugger-enabled Bochs with the test-only native
save bridge. A new process restores the native state before guest execution.
"""

import hashlib
import json
import os
import pty
import re
import select
import shutil
import struct
import subprocess
import sys
import termios
import time
from pathlib import Path

from iced_x86 import Decoder

PROMPT = re.compile(rb"<bochs:\d+> ")


class Bochs:
    def __init__(self, args, timeout=160):
        master, slave = pty.openpty()
        settings = termios.tcgetattr(slave)
        settings[3] &= ~termios.ECHO
        termios.tcsetattr(slave, termios.TCSANOW, settings)
        self.fd = master
        self.proc = subprocess.Popen(args, stdin=slave, stdout=slave, stderr=slave, close_fds=True)
        os.close(slave)
        self.pending = b""
        self.timeout = timeout
        try:
            self.startup = self._read()
        except BaseException:
            self.proc.kill()
            self.proc.wait()
            os.close(self.fd)
            raise

    def _read(self):
        deadline = time.monotonic() + self.timeout
        while not PROMPT.search(self.pending):
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([self.fd], [], [], remaining)[0]:
                raise TimeoutError(
                    "Bochs debugger prompt timed out: "
                    + self.pending[-4000:].decode(errors="replace")
                )
            chunk = os.read(self.fd, 65536)
            if not chunk:
                raise RuntimeError(
                    "Bochs exited before prompt: " + self.pending[-4000:].decode(errors="replace")
                )
            self.pending += chunk
        prompt = PROMPT.search(self.pending)
        result, self.pending = self.pending[: prompt.start()], self.pending[prompt.end() :]
        return result.decode(errors="replace")

    def cmd(self, command):
        os.write(self.fd, (command + "\n").encode())
        return self._read()

    def close(self):
        if self.proc.poll() is None:
            os.write(self.fd, b"q\n")
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
                raise
        os.close(self.fd)
        assert self.proc.returncode == 0, self.proc.returncode

    def abort(self):
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(timeout=5)
        os.close(self.fd)

    def read(self, address, count, physical=False):
        text = self.cmd(f"{'xp' if physical else 'x'} /{count}bx {address:#x}")
        data = bytes(int(value, 16) for value in re.findall(r"\t0x([0-9a-fA-F]{2})(?=\s|$)", text))
        assert len(data) == count, (address, count, text)
        return data

    def context(self):
        regs, segs, cregs = self.cmd("regs"), self.cmd("sreg"), self.cmd("creg")

        def match(pattern, text):
            found = re.search(pattern, text, re.MULTILINE)
            assert found, (pattern, text)
            return int(found.group(1).replace("_", ""), 16)

        return {
            "ip": match(r"^rip:\s*([0-9a-fA-F_]+)", regs),
            "esi": match(r"^rsi:\s*([0-9a-fA-F_]+)", regs) & 0xFFFFFFFF,
            "cs": match(r"^cs:0x([0-9a-fA-F]+)", segs),
            "cs_base": match(r"^cs:.*\n\s*[^\n]*base=0x([0-9a-fA-F]+)", segs),
            "cs_limit": match(r"^cs:.*\n\s*[^\n]*limit=0x([0-9a-fA-F]+)", segs),
            "ldtr_selector": match(r"^ldtr:0x([0-9a-fA-F]+)", segs),
            "gdtr_base": match(r"^gdtr:base=0x([0-9a-fA-F]+)", segs),
            "cr0": match(r"^CR0=0x([0-9a-fA-F]+)", cregs),
            "cr3": match(r"^CR3=0x([0-9a-fA-F]+)", cregs),
            "cr4": match(r"^CR4=0x([0-9a-fA-F]+)", cregs),
            "clock": int(re.search(r"ptime:\s*(\d+)", self.cmd("ptime")).group(1)),
        }


def observation(debug):
    ctx = debug.context()
    assert ctx["cr0"] & 0x80000001 == 0x80000001 and ctx["cr4"] & 0x20
    pc = ctx["cs_base"] + ctx["ip"]

    def walk(linear):
        levels = []

        def entry(level, address):
            value = int.from_bytes(debug.read(address, 8, True), "little")
            assert value & 1, (level, address, value)
            levels.append({"level": level, "address": address, "value": value})
            return value

        pdpte = entry("pdpte", (ctx["cr3"] & ~31) + (linear >> 30) * 8)
        pde = entry("pde", (pdpte & 0x000FFFFFFFFFF000) + ((linear >> 21) & 511) * 8)
        if pde & 0x80:
            return (pde & 0x000FFFFFFFE00000) + (linear & 0x1FFFFF), 0x200000, levels
        pte = entry("pte", (pde & 0x000FFFFFFFFFF000) + ((linear >> 12) & 511) * 8)
        return (pte & 0x000FFFFFFFFFF000) + (linear & 4095), 0x1000, levels

    data = debug.read(pc, 15)
    decoded = Decoder(32, data, ip=ctx["ip"]).decode()
    assert not decoded.is_invalid
    data = data[: decoded.len]
    walks = [walk(pc + i) for i in range(len(data))]
    assert bytes(debug.read(p, 1, True)[0] for p, _, _ in walks) == data
    mmu_pages = {}
    for offset, (physical, _, _) in enumerate(walks):
        linear = pc + offset
        page = linear & ~0xFFF
        if page not in mmu_pages:
            output = debug.cmd(f"page {linear:#x}")
            found = re.search(
                r"linear page 0x([0-9a-fA-F]+) maps to physical page 0x([0-9a-fA-F]+)", output
            )
            assert found, output
            observed_linear, observed_physical = (int(v, 16) for v in found.groups())
            assert observed_linear == page
            mmu_pages[page] = observed_physical
        assert mmu_pages[page] + (linear & 0xFFF) == physical
    selector = ctx["cs"]
    if selector & 4:
        ldt_desc = debug.read(ctx["gdtr_base"] + (ctx["ldtr_selector"] & ~7), 8)
        ldt_base = int.from_bytes(ldt_desc[2:4], "little") | ldt_desc[4] << 16 | ldt_desc[7] << 24
        desc_addr = ldt_base + (selector & ~7)
    else:
        desc_addr = ctx["gdtr_base"] + (selector & ~7)
    descriptor = debug.read(desc_addr, 8)
    assert debug.context() == ctx
    return {
        "cs": selector,
        "ip": ctx["ip"],
        "pc": pc,
        "esi": ctx["esi"],
        "clock": ctx["clock"],
        "cs_base": ctx["cs_base"],
        "cs_limit": ctx["cs_limit"],
        "descriptor": descriptor.hex(),
        "ldtr_selector": ctx["ldtr_selector"],
        "paging": True,
        "paging_mode": "pae",
        "page_size": walks[0][1],
        "hex": data.hex(),
        "backing": [w[0] for w in walks],
        "walks": [w[2] for w in walks],
        "mmu_pages": [{"linear": k, "physical": v} for k, v in mmu_pages.items()],
    }


def verify_saved_high_checkpoint(stage, cfg, hot, cold):
    """Read the native Bochs CPU and sparse RAM files without starting Bochs."""
    assert cfg["paging_mode"] in ("pae-4k-high", "pae-2m-high")
    checkpoint = Path(hot["checkpoint"])
    assert checkpoint.resolve() == (Path(stage) / "bochs-state").resolve()
    cpu_path = checkpoint / "cpu0"
    cpu = cpu_path.read_text()

    def field(name):
        match = re.search(r"^  " + re.escape(name) + r" = (\w+)$", cpu, re.MULTILINE)
        assert match, (name, cpu_path)
        return int(match.group(1), 0)

    def segment(name):
        match = re.search(
            r"^  " + re.escape(name) + r" = \{\n(.*?)^  \}", cpu, re.MULTILINE | re.DOTALL
        )
        assert match, (name, cpu_path)
        return {
            key: int(value, 0)
            for key, value in re.findall(
                r"^    (selector|base|limit_scaled) = (\w+)$", match.group(1), re.MULTILINE
            )
        }

    cs, ldt = segment("CS"), segment("LDTR")
    ip, cr0, cr3, cr4 = (field(name) for name in ("RIP", "CR0", "CR3", "CR4"))
    context = hot["checkpoint_context"]
    assert (cs["selector"], cs["base"], ldt["selector"], ip) == (
        context["cs"], context["cs_base"], context["ldtr_selector"], context["ip"]
    )
    assert (cr0, cr3, cr4) == (context["cr0"], context["cr3"], context["cr4"])
    assert field("RSI") & 0xFFFFFFFF == context["esi"]
    linear = cs["base"] + ip
    assert linear == hot["events"][cfg["checkpoint_index"]]["pc"]

    config = (checkpoint / "config").read_text()
    assert "guest=4120" in config
    block_kib = int(re.search(r"^memory:.*block_size=(\d+)", config, re.MULTILINE)[1])
    assert block_kib == 2048
    memory_meta = (checkpoint / "memory").read_text()
    assert "ram = memory.ram" in memory_meta
    allocation = {
        int(block): int(location)
        for block, location in re.findall(r"^    blk(\d+) = (-?\d+)$", memory_meta, re.MULTILINE)
    }
    ram_path = checkpoint / "memory.ram"

    def physical_read(address, count):
        assert not 0xC0000000 <= address < 0x100000000
        offset = address - 0x40000000 if address >= 0x100000000 else address
        block_bytes = block_kib * 1024
        block = offset // block_bytes
        assert offset // block_bytes == (offset + count - 1) // block_bytes
        location = allocation.get(block, -1)
        assert location >= 0, (hex(address), block, location)
        with ram_path.open("rb") as ram:
            ram.seek(offset)
            data = ram.read(count)
        assert len(data) == count, (hex(address), count)
        return data

    def entry(level, address):
        value = struct.unpack("<Q", physical_read(address, 8))[0]
        assert value & 1, (level, hex(address), hex(value))
        return {"level": level, "address": address, "value": value}

    frame_mask = 0x000FFFFFFFFFF000
    pdpte = entry("pdpte", (cr3 & ~31) + ((linear >> 30) & 3) * 8)
    pde = entry("pde", (pdpte["value"] & frame_mask) + ((linear >> 21) & 511) * 8)
    entries = [pdpte, pde]
    if pde["value"] & 0x80:
        page_size = 0x200000
        page_base = pde["value"] & 0x000FFFFFFFE00000
    else:
        page_size = 0x1000
        pte = entry("pte", (pde["value"] & frame_mask) + ((linear >> 12) & 511) * 8)
        entries.append(pte)
        page_base = pte["value"] & frame_mask
    expected_size = 0x1000 if cfg["paging_mode"] == "pae-4k-high" else 0x200000
    assert page_size == expected_size
    backing = page_base + (linear & (page_size - 1))
    assert backing == cfg["second_target"]

    high_bytes = {
        address: physical_read(address, 2).hex()
        for address in (cfg["first_target"], cfg["second_target"])
    }
    aliases = {address & 0xFFFFFFFF for address in high_bytes}
    assert aliases == set(cfg["low_aliases"])
    low_markers = {address: physical_read(address, 2).hex() for address in aliases}
    assert len(high_bytes) == len(low_markers) == 2
    assert set(high_bytes.values()) == {"46cb"} and set(low_markers.values()) == {"0f0b"}
    assert hot["low_alias_markers"] == cold["low_alias_markers"] == {
        str(address): marker for address, marker in low_markers.items()
    }

    checkpoint_event = hot["events"][cfg["checkpoint_index"]]
    restored_event = cold["events"][0]
    assert checkpoint_event == restored_event
    assert checkpoint_event["backing"][0] == backing
    assert checkpoint_event["walks"][0] == entries
    descriptor_address = ldt["base"] + (cs["selector"] & ~7)
    assert physical_read(descriptor_address, 8).hex() == checkpoint_event["descriptor"]


def run(stage, phase):
    stage = Path(stage).resolve()
    assert phase in ("before", "after")
    cfg = json.loads((stage / "config.json").read_text())
    high_memory = cfg.get("paging_mode", "").endswith("-high")
    source = Path(cfg["source"])
    assert hashlib.sha256(source.read_bytes()).hexdigest() == cfg["sha256"]
    binary = Path(os.environ["FDISBULL_BOCHS"]).resolve(strict=True)
    share = Path(os.environ.get("FDISBULL_BOCHS_SHARE", binary.parent.parent / "share" / "bochs"))
    checkpoint = stage / "bochs-state"
    if phase == "before":
        disk = stage / "bochs.img"
        shutil.copyfile(stage / "boot.img", disk)
        batch = stage / "bochs-auto.bat"
        batch.write_bytes(b"@echo off\r\nA:\\REMAP.EXE\r\n")
        for path, name in ((source, "REMAP.EXE"), (batch, "FDAUTO.BAT")):
            subprocess.run(
                [
                    os.environ["FDISBULL_QEMU_DOS_MCOPY"],
                    "-i",
                    str(disk),
                    "-o",
                    str(path),
                    "::" + name,
                ],
                check=True,
                capture_output=True,
                timeout=15,
            )
        config = stage / "bochsrc"
        memory = (
            "memory: guest=4120, host=32, block_size=2048"
            if high_memory
            else "megs: 32"
        )
        config.write_text(f'''{memory}
romimage: file="{share / "BIOS-bochs-latest"}"
vgaromimage: file="{share / "VGABIOS-lgpl-latest.bin"}"
display_library: nogui
floppya: 1_44="{disk}", status=inserted
boot: floppy
log: "{stage / "bochs.log"}"
panic: action=fatal
error: action=report
info: action=ignore
debug: action=ignore
''')
        args = [str(binary), "-q", "-debugger", "-f", str(config)]
    else:
        args = [str(binary), "-q", "-debugger", "-r", str(checkpoint)]
    media_hash = hashlib.sha256((stage / "bochs.img").read_bytes()).hexdigest()
    binary_hash = hashlib.sha256(binary.read_bytes()).hexdigest()
    if phase == "after":
        previous = json.loads((stage / "bochs-before.json").read_text())
        assert previous["media_sha256"] == media_hash and previous["binary_sha256"] == binary_hash
    debug = Bochs(args)
    pid = debug.proc.pid
    try:
        initial = debug.context()
        if phase == "before":
            debug.cmd(f"lb {cfg['start_pc']:#x}")
            stop = debug.cmd("c")
            assert "Breakpoint" in stop, stop
            debug.cmd("d 1")
            entry = debug.context()
            assert (entry["cs"], entry["ip"], entry["cs_base"] + entry["ip"]) == (
                cfg["start_cs"],
                cfg["start_ip"],
                cfg["start_pc"],
            )
            start = 0
        else:
            assert initial == previous["checkpoint_context"], (
                initial,
                previous["checkpoint_context"],
            )
            start = cfg["checkpoint_index"]
        events = []
        saved_context = None
        for index in range(start, cfg["boundaries"]):
            if phase == "before" and index == cfg["checkpoint_index"]:
                saved_context = debug.context()
                checkpoint.mkdir()
                out = debug.cmd(f'restore "__save_state__" "{checkpoint}"')
                assert "native save state" in out and ": OK" in out, out
            events.append(observation(debug))
            if index + 1 < cfg["boundaries"]:
                debug.cmd("s")
        low_alias_markers = {
            str(address): debug.read(address, 2, True).hex()
            for address in cfg.get("low_aliases", [])
        }
    except BaseException:
        debug.abort()
        raise
    else:
        debug.close()
    media_hash = hashlib.sha256((stage / "bochs.img").read_bytes()).hexdigest()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == cfg["sha256"]
    result = {
        "checkpoint": str(checkpoint),
        "events": events,
        "pid": pid,
        "owners": [debug.proc.returncode],
        "initial_context": initial,
        "checkpoint_context": saved_context,
        "media_sha256": media_hash,
        "binary_sha256": binary_hash,
        "memory_topology": "high-ram-over-4g-sparse" if high_memory else "32m",
        "low_alias_markers": low_alias_markers,
        "max_native_mmu_physical": max(
            page["physical"] for event in events for page in event["mmu_pages"]
        ),
    }
    (stage / f"bochs-{phase}.json").write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    run(Path(sys.argv[1]), sys.argv[2])
