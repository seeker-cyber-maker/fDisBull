"""Native instruction decoding, without analysis or database side effects."""
from __future__ import annotations

from functools import lru_cache

import capstone
import iced_x86 as ix


@lru_cache(maxsize=3)
def _arm_decoder():
    decoder = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_LITTLE_ENDIAN)
    decoder.detail = True
    return decoder


def decode(data: bytes, address: int, arch: str, bits: int) -> dict | None:
    """Decode exactly one instruction. Invalid/truncated bytes return ``None``.

    Addresses are static, flat virtual addresses. Segment-relative x86 data and
    far branches remain unresolved rather than inventing a segment base.
    """
    if not isinstance(address, int) or not 0 <= address < 1 << 64:
        raise ValueError("instruction address must fit in an unsigned 64-bit integer")
    if not data:
        return None
    if arch == "x86":
        if bits not in (16, 32, 64):
            raise ValueError("x86 decoding requires 16, 32, or 64 bits")
        instruction = ix.Decoder(bits, data[:15], ip=address).decode()
        if instruction.is_invalid:
            return None
        formatter = ix.Formatter(ix.FormatterSyntax.NASM)
        text = formatter.format(instruction)
        mnemonic, _, operands = text.partition(" ")
        flow = {
            ix.FlowControl.NEXT: "next",
            ix.FlowControl.UNCONDITIONAL_BRANCH: "jump",
            ix.FlowControl.INDIRECT_BRANCH: "indirect_jump",
            ix.FlowControl.CONDITIONAL_BRANCH: "conditional",
            ix.FlowControl.RETURN: "return",
            ix.FlowControl.CALL: "call",
            ix.FlowControl.INDIRECT_CALL: "indirect_call",
            ix.FlowControl.INTERRUPT: "next",  # interrupt return path may continue
            ix.FlowControl.EXCEPTION: "stop",
            ix.FlowControl.XBEGIN_XABORT_XEND: "conditional",
        }.get(instruction.flow_control, "stop")
        if instruction.mnemonic in (ix.Mnemonic.HLT, ix.Mnemonic.INT3, ix.Mnemonic.XABORT):
            flow = "stop"
        elif instruction.mnemonic == ix.Mnemonic.XEND:
            flow = "next"
        target = None
        if flow in ("jump", "conditional", "call"):
            near_kinds = (ix.OpKind.NEAR_BRANCH16, ix.OpKind.NEAR_BRANCH32, ix.OpKind.NEAR_BRANCH64)
            if any(instruction.op_kind(index) in near_kinds for index in range(instruction.op_count)):
                target = instruction.near_branch_target
            else:
                # A far immediate has a known selector, not a known flat VA.
                flow = "indirect_call" if flow == "call" else "indirect_jump"
        data_refs = []
        if instruction.is_ip_rel_memory_operand:
            data_refs.append(instruction.ip_rel_memory_address)
        elif bits != 16 and instruction.memory_base == ix.Register.NONE and instruction.memory_index == ix.Register.NONE:
            has_memory = any(instruction.op_kind(index) == ix.OpKind.MEMORY for index in range(instruction.op_count))
            if has_memory and instruction.memory_segment not in (ix.Register.FS, ix.Register.GS):
                data_refs.append(instruction.memory_displacement)
        size = instruction.len
    elif arch == "arm64":
        if bits != 64:
            raise ValueError("arm64 decoding requires 64 bits")
        if address % 4 or len(data) < 4:
            return None
        instruction = next(_arm_decoder().disasm(data[:4], address, count=1), None)
        if instruction is None:
            return None
        mnemonic, operands = instruction.mnemonic, instruction.op_str
        text = mnemonic + (" " + operands if operands else "")
        flow, target, data_refs = "next", None, []
        immediate_operands = [operand.imm for operand in instruction.operands if operand.type == capstone.arm64.ARM64_OP_IMM]
        if mnemonic in ("ret", "retaa", "retab", "eret", "eretaa", "eretab"):
            flow = "return"
        elif mnemonic in ("br", "braa", "brab", "braaz", "brabz"):
            flow = "indirect_jump"
        elif mnemonic in ("blr", "blraa", "blrab", "blraaz", "blrabz"):
            flow = "indirect_call"
        elif mnemonic == "bl":
            flow = "call"
            target = immediate_operands[-1] if immediate_operands else None
        elif mnemonic == "b":
            flow = "jump"
            target = immediate_operands[-1] if immediate_operands else None
        elif mnemonic.startswith("b.") or mnemonic in ("cbz", "cbnz", "tbz", "tbnz"):
            flow = "conditional"
            target = immediate_operands[-1] if immediate_operands else None
        elif mnemonic in ("brk", "hlt", "udf"):
            flow = "stop"
        elif mnemonic in ("adr", "adrp") and immediate_operands:
            data_refs.append(immediate_operands[-1])
        elif mnemonic in ("ldr", "ldrsw", "prfm") and immediate_operands:
            # Literal addressing is PC relative; register-indexed loads have no
            # immediate operand in Capstone's top-level operand list.
            data_refs.append(immediate_operands[-1])
        size = instruction.size
    else:
        raise ValueError(f"unsupported architecture: {arch!r}")
    return {
        "address": address,
        "size": size,
        "bytes": bytes(data[:size]).hex(),
        "mnemonic": mnemonic,
        "operands": operands,
        "text": text,
        "flow": flow,
        "target": target,
        "data_refs": data_refs,
    }
