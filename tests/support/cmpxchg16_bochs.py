"""Independent Bochs observations of guest page faults and CMPXCHG16B."""

import hashlib
import json
import os
from pathlib import Path
import re

from support.le_remap_bochs import Bochs, prepare_bochs_media


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def snapshot(read, registers, cfg):
    target = read(cfg["target"], 16)
    count = int.from_bytes(read(cfg["report"], 8), "little")
    assert 0 <= count <= 3
    faults = []
    for i in range(count):
        raw = read(cfg["report"] + 0x10 + i*64, 56)
        values = [int.from_bytes(raw[n:n+8], "little") for n in range(0, 56, 8)]
        faults.append(dict(zip(("error", "address", "rip", "rax", "rdx", "low", "high"), values)))
    return dict(pc=registers["pc"], rax=registers["rax"], rdx=registers["rdx"],
                zf=bool(registers["flags"] & 0x40), target=target.hex(),
                sentinel=read(cfg["sentinel"], 1).hex(), faults=faults)


def run(stage, phase):
    stage = Path(stage)
    cfg = json.loads((stage/"config.json").read_text())
    source = Path(cfg["source"])
    assert digest(source) == cfg["sha256"]
    binary = Path(os.environ["FDISBULL_BOCHS"]).resolve()
    share = Path(os.environ["FDISBULL_BOCHS_SHARE"])
    saved = stage/"cx16-bochs-state"
    disk = stage/"cx16-bochs.img"
    if phase == "before":
        disk, config = prepare_bochs_media(stage, source, share, False,
            disk_name=disk.name, batch_name="cx16-bochs-auto.bat",
            config_name="cx16-bochsrc", log_name="cx16-bochs.log")
        with config.open("a") as stream:
            stream.write("cpu: model=corei7_sandy_bridge_2600k, count=1, reset_on_triple_fault=0\n")
        args = [str(binary), "-q", "-debugger", "-f", str(config)]
    else:
        prior = json.loads((stage/"cx16-bochs-before.json").read_text())
        assert prior["binary_sha256"] == digest(binary) and prior["media_sha256"] == digest(disk)
        args = [str(binary), "-q", "-debugger", "-r", str(saved)]
    debug = Bochs(args)
    index = 0
    try:
        initial = debug.context()
        def to(address):
            nonlocal index
            index += 1
            debug.cmd(f"lb {address:#x}")
            stopped = debug.cmd("c")
            assert "Breakpoint" in stopped, stopped
            debug.cmd(f"d {index}")
        if phase == "before":
            assert not initial["cr0"] & 0x80000001
            to(cfg["entry"])
        else:
            assert debug.proc.pid != prior["pid"] and initial == prior["checkpoint_context"]
        checkpoint_context = debug.context()
        assert checkpoint_context["ip"] == cfg["entry"]
        assert checkpoint_context["cr0"] & 0x80010001 == 0x80010001
        assert checkpoint_context["cr4"] & 0x20
        control = debug.cmd("creg")
        efer = int(re.search(r"^EFER=0x([0-9a-fA-F]+)", control, re.M)[1], 16)
        assert efer & 0x500 == 0x500
        assert debug.read(cfg["target"],16).hex() == "08070605040302011817161514131211"
        assert int.from_bytes(debug.read(cfg["pte"],8,physical=True),"little") & 2 == 0
        if phase == "before":
            saved.mkdir()
            result = debug.cmd(f'restore "__save_state__" "{saved}"')
            assert "native save state" in result and ": OK" in result, result
        observations = {}
        for key in ("failed_after", "changed_after", "same_after"):
            to(cfg[key])
            raw = debug.cmd("regs")
            def reg(name):
                return int(re.search(r"^"+name+r":\s*([0-9a-fA-F_]+)",raw,re.M)[1].replace("_",""),16)
            flags = int(re.search(r"^eflags:\s*0x([0-9a-fA-F]+)",raw,re.M)[1],16)
            observations[key] = snapshot(lambda a,n: debug.read(a,n,physical=True),
                dict(pc=reg("rip"),rax=reg("rax"),rdx=reg("rdx"),flags=flags),cfg)
            assert debug.read(cfg["target"],16)==debug.read(cfg["target"],16,physical=True)
        if phase == "after":
            assert observations == prior["observations"]
    except BaseException:
        debug.abort()
        raise
    else:
        debug.close()
    result = dict(binary_sha256=digest(binary),media_sha256=digest(disk),
                  checkpoint=str(saved),checkpoint_context=checkpoint_context,initial_context=initial,
                  efer=efer,pid=debug.proc.pid,restore_before_guest_execution=phase=="after",
                  source_sha256=cfg["sha256"],observations=observations)
    (stage/f"cx16-bochs-{phase}.json").write_text(json.dumps(result,indent=2)+"\n")
    return result
