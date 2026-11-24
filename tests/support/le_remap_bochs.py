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


def run(stage, phase):
    stage = Path(stage).resolve()
    assert phase in ("before", "after")
    cfg = json.loads((stage / "config.json").read_text())
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
        config.write_text(f'''megs: 32
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
    }
    (stage / f"bochs-{phase}.json").write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    run(Path(sys.argv[1]), sys.argv[2])
