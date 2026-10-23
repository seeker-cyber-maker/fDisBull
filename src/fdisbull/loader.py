"""Bounded, static executable loading. Imported binaries are never executed."""
from __future__ import annotations

import hashlib
from pathlib import Path

import lief

from .model import Image, Region, Seed

MAX_IMAGE_SIZE = 64 * 1024 * 1024


def _address(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 1 << 64:
        raise ValueError(f"{label} must fit in an unsigned 64-bit integer")
    return value


def _regions_check(regions: list[Region]) -> list[Region]:
    regions = sorted((region for region in regions if region.data), key=lambda region: region.start)
    if not regions:
        raise ValueError("executable contains no mapped bytes")
    total = 0
    previous_end = 0
    for region in regions:
        _address(region.start, "region address")
        end = region.start + len(region.data)
        if end > 1 << 64:
            raise ValueError("mapped region exceeds the 64-bit address space")
        if region.start < previous_end:
            raise ValueError("overlapping mapped regions are not supported")
        previous_end = end
        total += len(region.data)
        if total > MAX_IMAGE_SIZE:
            raise ValueError("mapped image exceeds the 64 MiB limit")
    return regions


def _content(content, virtual_size: int, budget: int = MAX_IMAGE_SIZE) -> bytes:
    size = max(len(content), int(virtual_size))
    if not 0 <= size <= min(MAX_IMAGE_SIZE, budget):
        raise ValueError("mapped region exceeds the 64 MiB limit")
    return bytes(content) + bytes(size - len(content))


def _is_executable(address: int, regions: list[Region]) -> bool:
    return any(region.executable and region.start <= address < region.start + len(region.data) for region in regions)


def load_image(path: str | Path, *, arch: str | None = None, bits: int | None = None,
               base: int = 0, entry: int | None = None, load_segment: int = 0x1000,
               module: bool = False) -> Image:
    """Load classic MZ, ELF, PE, thin Mach-O or explicitly declared raw code.

    Native file mappings use their preferred image addresses (PIE load bias is
    not applied). Raw mode requires ``arch`` and defaults to 64 bits. DLLs
    without an entry can be inspected and recursively seeded by exports.
    Module mode also permits an absent entry for other explicitly chosen libraries.
    """
    path = Path(path)
    if not isinstance(module,bool):
        raise ValueError('module must be a boolean')
    if not path.is_file():
        raise ValueError(f"not a regular input file: {path}")
    size = path.stat().st_size
    if not 0 < size <= MAX_IMAGE_SIZE:
        raise ValueError("input file must be nonempty and at most 64 MiB")
    with path.open("rb") as stream:
        data = stream.read(MAX_IMAGE_SIZE + 1)
    if not 0 < len(data) <= MAX_IMAGE_SIZE:
        raise ValueError("input file must be nonempty and at most 64 MiB")
    base = _address(base, "base address")
    if entry is not None:
        entry = _address(entry, "entry address")
    if arch is not None:
        if arch not in ("x86", "arm64"):
            raise ValueError("raw architecture must be x86 or arm64")
        bits = 64 if bits is None else bits
        if isinstance(bits,bool) or not isinstance(bits,int):
            raise ValueError("raw bitness must be an integer")
        if (arch == "x86" and bits not in (16, 32, 64)) or (arch == "arm64" and bits != 64):
            raise ValueError("raw x86 requires 16/32/64 bits; arm64 requires 64 bits")
        if arch == "arm64" and (base % 4 or len(data) % 4):
            raise ValueError("raw arm64 base and byte length must be 4-byte aligned")
        if arch == "x86" and bits in (16, 32) and base + len(data) > 1 << bits:
            raise ValueError("raw x86 16/32-bit image must fit in its flat address space")
        regions = _regions_check([Region("raw", base, data, True)])
        entry = base if entry is None else entry
        if not _is_executable(entry, regions):
            raise ValueError("entry address is outside the raw image")
        if arch == "arm64" and entry % 4:
            raise ValueError("arm64 entry point must be 4-byte aligned")
        return Image("raw", arch, bits, entry, regions, [Seed(entry, "entry", "entry")],
                     {"mapping": "flat", "filename": path.name, "source_sha256": hashlib.sha256(data).hexdigest(), "file_mappings":[dict(virtual_address=base,file_offset=0,file_size=len(data))]}, source_bytes=data)
    if data[:2]==b'MZ':
        pe_offset=int.from_bytes(data[0x3c:0x40],'little') if len(data)>=0x40 else 0
        if data[pe_offset:pe_offset+4]!=b'PE\0\0':
            if bits is not None or base:
                raise ValueError('DOS MZ uses --load-segment; --bits/--base require raw mode')
            from .dos import load_mz
            return load_mz(data,load_segment=load_segment,entry=entry)
    if load_segment!=0x1000:
        raise ValueError('load_segment applies only to classic DOS MZ')
    if bits is not None or base:
        raise ValueError("bits and base overrides require an explicit raw architecture")
    if data[:4] in (b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca", b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca"):
        raise ValueError("fat Mach-O requires selecting a thin architecture slice first")
    if data[:2]!=b'MZ' and data[:4] != b"\x7fELF" and data[:4] not in (b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf"):
        raise ValueError("unsupported file format; declare --arch for raw code")
    try:
        binary = lief.parse(data)
    except Exception as exc:
        raise ValueError(f"cannot parse executable: {exc}") from exc
    if binary is None:
        raise ValueError("invalid or unsupported executable")
    regions: list[Region] = []
    mapped_size = 0

    def mapped_content(content, virtual_size):
        nonlocal mapped_size
        result = _content(content, virtual_size, MAX_IMAGE_SIZE - mapped_size)
        mapped_size += len(result)
        return result

    metadata = {"filename": path.name, "mapping": "preferred static virtual addresses", "source_sha256": hashlib.sha256(data).hexdigest(), "file_mappings":[]}
    is_dll=False
    if isinstance(binary, lief.ELF.Binary):
        if binary.header.file_type not in (lief.ELF.Header.FILE_TYPE.EXEC, lief.ELF.Header.FILE_TYPE.DYN):
            raise ValueError("only executable and shared/PIE ELF images are supported")
        if binary.header.identity_data != lief.ELF.Header.ELF_DATA.LSB:
            raise ValueError("big-endian executables are not supported")
        machine = binary.header.machine_type
        if machine == lief.ELF.ARCH.X86_64:
            arch, bits = "x86", 64
        elif machine == lief.ELF.ARCH.I386:
            arch, bits = "x86", 32
        elif machine == lief.ELF.ARCH.AARCH64:
            arch, bits = "arm64", 64
        else:
            raise ValueError(f"unsupported ELF architecture: {machine}")
        for index, segment in enumerate(binary.segments):
            if segment.type == lief.ELF.Segment.TYPE.LOAD:
                metadata["file_mappings"].append(dict(virtual_address=int(segment.virtual_address),file_offset=int(segment.file_offset),file_size=int(segment.physical_size)))
                regions.append(Region(f"LOAD{index}", segment.virtual_address,
                                      mapped_content(segment.content, segment.virtual_size),
                                      segment.has(lief.ELF.Segment.FLAGS.X),
                                      segment.has(lief.ELF.Segment.FLAGS.W)))
        file_format = "ELF"
    elif isinstance(binary, lief.PE.Binary):
        is_dll=binary.header.has_characteristic(lief.PE.Header.CHARACTERISTICS.DLL)
        metadata['is_dll']=is_dll
        from .managed import managed_kind
        clr=managed_kind(data)
        if clr['recognized']:
            metadata['managed']=clr
        machine = binary.header.machine
        if machine == lief.PE.Header.MACHINE_TYPES.AMD64:
            arch, bits = "x86", 64
        elif machine == lief.PE.Header.MACHINE_TYPES.I386:
            arch, bits = "x86", 32
        elif machine == lief.PE.Header.MACHINE_TYPES.ARM64:
            arch, bits = "arm64", 64
        else:
            raise ValueError(f"unsupported PE architecture: {machine}")
        imagebase = binary.optional_header.imagebase
        metadata["imagebase"] = hex(imagebase)
        headers_size = min(int(binary.optional_header.sizeof_headers), len(data))
        if headers_size:
            metadata["file_mappings"].append(dict(virtual_address=int(imagebase),file_offset=0,file_size=headers_size))
            regions.append(Region("headers", imagebase, mapped_content(data[:headers_size], headers_size), False))
        for section in binary.sections:
            metadata["file_mappings"].append(dict(virtual_address=int(imagebase+section.virtual_address),file_offset=int(section.pointerto_raw_data),file_size=int(section.sizeof_raw_data)))
            regions.append(Region(section.name, imagebase + section.virtual_address,
                                  mapped_content(section.content, section.virtual_size),
                                  section.has_characteristic(lief.PE.Section.CHARACTERISTICS.MEM_EXECUTE),
                                  section.has_characteristic(lief.PE.Section.CHARACTERISTICS.MEM_WRITE)))
        file_format = "PE"
    elif isinstance(binary, lief.MachO.Binary):
        cpu = binary.header.cpu_type
        if cpu == lief.MachO.Header.CPU_TYPE.X86_64:
            arch, bits = "x86", 64
        elif cpu == lief.MachO.Header.CPU_TYPE.X86:
            arch, bits = "x86", 32
        elif cpu == lief.MachO.Header.CPU_TYPE.ARM64:
            arch, bits = "arm64", 64
        else:
            raise ValueError(f"unsupported Mach-O architecture: {cpu}")
        if data[:4] not in (b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe"):
            raise ValueError("big-endian executables are not supported")
        for segment in binary.segments:
            if segment.name == "__PAGEZERO" or not segment.init_protection:
                continue
            metadata["file_mappings"].append(dict(virtual_address=int(segment.virtual_address),file_offset=int(segment.file_offset),file_size=int(segment.file_size)))
            regions.append(Region(segment.name, segment.virtual_address,
                                  mapped_content(segment.content, segment.virtual_size),
                                  bool(segment.init_protection & 4), bool(segment.init_protection & 2)))
        file_format = "Mach-O"
    else:
        raise ValueError("only ELF, PE, and thin Mach-O executables are supported")
    regions = _regions_check(regions)
    explicit_entry=entry is not None
    if entry is None:
        entry = int(binary.entrypoint)
    declared_has_entry=bool(binary.optional_header.addressof_entrypoint) if file_format=='PE' else bool(binary.entrypoint)
    metadata['declared_entrypoint']=int(binary.entrypoint)
    present=_is_executable(entry,regions) and (explicit_entry or declared_has_entry)
    if not present and (explicit_entry or not(module or is_dll or metadata.get('managed',{}).get('recognized'))):
        raise ValueError("entry point is not in an executable mapped region; supply an explicit entry")
    metadata['entrypoint_present']=present
    if not present:
        entry=regions[0].start
        metadata['entrypoint_note']='No executable entry; this anchor is not a code seed. Analyze exports or an explicit address.'
    if arch == "arm64" and present and entry % 4:
        raise ValueError("arm64 entry point must be 4-byte aligned")
    seeds = [Seed(entry, "entry", "entry")] if present else []
    seen = {entry} if present else set()
    for function in binary.functions:
        address = int(function.address)
        if file_format == "PE":
            address += imagebase  # LIEF PE function entries are RVAs.
        if present and address == entry and function.name and seeds[0].name == "entry":
            seeds[0] = Seed(entry, function.name, "entry + symbol_or_unwind")
        if address not in seen and _is_executable(address, regions):
            seen.add(address)
            seeds.append(Seed(address, function.name or f"sub_{address:x}", "symbol_or_unwind"))
    metadata["seed_count"] = len(seeds)
    metadata["relocations"] = "recorded mapping only; no runtime relocation applied"
    return Image(file_format, arch, bits, entry, regions, seeds, metadata, source_bytes=data)
