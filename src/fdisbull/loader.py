"""Bounded, static executable loading. Imported binaries are never executed."""
from __future__ import annotations

import hashlib
from pathlib import Path

import lief

from .model import Image, Region, Seed

MAX_IMAGE_SIZE = 64 * 1024 * 1024
MAX_MACHO_FUNCTION_STARTS = 100_000


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


def _macho_instruction_start(address: int, sections, regions: list[Region],
                             file_mappings: list[dict], source_size: int) -> bool:
    """Require one aligned ARM64 instruction in file-backed executable code."""
    return (0 <= address < 1 << 64 and address % 4 == 0 and
            any(section.virtual_address <= address and
                address + 4 <= section.virtual_address + section.size for section in sections) and
            any(region.executable and region.start <= address and
                address + 4 <= region.start + len(region.data) for region in regions) and
            any(mapping['virtual_address'] <= address and
                address + 4 <= mapping['virtual_address'] + mapping['file_size'] and
                0 <= mapping['file_offset'] and
                mapping['file_offset'] + address - mapping['virtual_address'] + 4 <= source_size
                for mapping in file_mappings))


def _macho_function_address(raw: int, text_base: int | None, sections, regions: list[Region],
                            file_mappings: list[dict], source_size: int) -> tuple[int, bool]:
    """Keep a valid VA, otherwise resolve a valid __TEXT-relative LIEF offset."""
    if _macho_instruction_start(raw, sections, regions, file_mappings, source_size):
        return raw, False
    candidate = text_base + raw if text_base is not None and raw >= 0 else -1
    if _macho_instruction_start(candidate, sections, regions, file_mappings, source_size):
        return candidate, True
    return raw, False


def load_image(path: str | Path, *, arch: str | None = None, bits: int | None = None,
               base: int | None = None, entry: int | None = None, load_segment: int = 0x1000,
               module: bool = False, slice_arch: str | None = None, image: str | None = None,
               profile: str | None = None, vector_count: int | None = None) -> Image:
    """Load classic MZ, Win16 NE, DOS/4GW LE, ELF, PE, Mach-O, COM or raw code.

    Native flat mappings use preferred image addresses (PIE load bias is not
    applied). NE uses logical segment/offset keys without assigning selectors. Raw mode requires ``arch`` and defaults to 64 bits. DLLs
    without an entry can be inspected and recursively seeded by exports.
    Module mode also permits an absent entry for other explicitly chosen libraries.
    """
    if image=='auto':image=None
    if image not in (None,'pe','le','ne','mz','com','ail'):raise ValueError('image must be auto, pe, le, ne, mz, com or ail')
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
    explicit_base = base is not None
    base = _address(0 if base is None else base, "base address")
    if entry is not None:
        entry = _address(entry, "entry address")
    if profile is not None:
        if profile != 'cortex-m':
            raise ValueError('profile must be cortex-m')
        if not explicit_base or vector_count is None:
            raise ValueError('Cortex-M requires an explicit base and vector_count')
        if arch not in (None, 'thumb') or bits not in (None, 32) or image is not None or slice_arch is not None or module or load_segment != 0x1000:
            raise ValueError('Cortex-M profile cannot use other architecture/container/module options')
        from .cortex_m import load
        return load(data, path.name, base, vector_count, entry)
    if vector_count is not None:
        raise ValueError('vector_count requires profile=cortex-m')
    if arch is not None:
        if image is not None:raise ValueError('image selects a container view; arch selects raw mode')
        if slice_arch is not None:raise ValueError('slice_arch selects a Mach-O image; arch selects raw mode')
        if arch not in ("x86", "arm64", "thumb"):
            raise ValueError("raw architecture must be x86, arm64 or thumb")
        bits = (32 if arch == "thumb" else 64) if bits is None else bits
        if isinstance(bits,bool) or not isinstance(bits,int):
            raise ValueError("raw bitness must be an integer")
        if (arch == "x86" and bits not in (16, 32, 64)) or (arch == "arm64" and bits != 64):
            raise ValueError("raw x86 requires 16/32/64 bits; arm64 requires 64 bits")
        if arch == 'thumb' and (bits != 32 or base & 1 or base + len(data) > 1 << 32):
            raise ValueError('raw Thumb requires 32 bits, halfword base alignment and a 32-bit mapping')
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
        if arch == 'thumb' and entry & 1:
            raise ValueError('Thumb entry must be a canonical halfword-aligned code address')
        return Image("raw", arch, bits, entry, regions, [Seed(entry, "entry", "entry")],
                     {"mapping": "flat", "filename": path.name, "source_sha256": hashlib.sha256(data).hexdigest(), "file_mappings":[dict(virtual_address=base,file_offset=0,file_size=len(data))]}, source_bytes=data)
    from .ail import ail_signature, load_ail
    if image=='ail' or image is None and ail_signature(data):
        if bits is not None or base or load_segment != 0x1000 or slice_arch is not None:
            raise ValueError('AIL uses module-relative offsets; bits/base/load_segment/slice overrides are not supported')
        return load_ail(data, entry=entry)
    if image=='com':
        if slice_arch is not None or bits is not None or base or module:
            raise ValueError('COM uses load_segment and cannot use raw, module or slice options')
        from .dos import load_com
        return load_com(data,load_segment=load_segment,entry=entry)
    if image=='mz':
        if slice_arch is not None:raise ValueError('slice_arch selects Mach-O CPUs and cannot select an MZ view')
        if bits is not None or base:raise ValueError('DOS MZ uses load_segment; bits/base require raw mode')
        from .dos import load_mz
        return load_mz(data,load_segment=load_segment,entry=entry,allow_secondary=True)
    from .image_views import secondary_header
    secondary = secondary_header(data)
    if image == 'ne' or (image is None and secondary and secondary['format'] == 'NE'):
        if slice_arch is not None or bits is not None or base or load_segment != 0x1000:
            raise ValueError('NE uses logical segment indices; slice/bits/base/load_segment overrides are unsupported')
        from .ne import load_ne
        loaded = load_ne(data, entry=entry, module=module)
        loaded.metadata.update(filename=path.name, source_sha256=hashlib.sha256(data).hexdigest())
        return loaded
    if image == 'le' or (image is None and (data.startswith(b'LE') or secondary and secondary['format'] == 'LE')):
        if slice_arch is not None:
            raise ValueError('slice_arch selects Mach-O CPUs and cannot select an LE image')
        if bits is not None or base or load_segment != 0x1000:
            raise ValueError('LE uses its preferred flat object addresses; bits/base/load_segment overrides are not supported')
        from .le import load_le
        return load_le(data, entry=entry)
    if image=='pe':
        if not secondary or secondary['format']!='PE':raise ValueError('requested PE image is not present')
    if data[:2]==b'MZ':
        if not secondary or secondary['format']!='PE':
            if slice_arch is not None:raise ValueError('slice_arch applies only to Mach-O containers')
            if bits is not None or base:
                raise ValueError('DOS MZ uses --load-segment; --bits/--base require raw mode')
            from .dos import load_mz
            return load_mz(data,load_segment=load_segment,entry=entry)
    if load_segment!=0x1000:
        raise ValueError('load_segment applies only to DOS MZ or explicitly selected COM')
    if bits is not None or base:
        raise ValueError("bits and base overrides require an explicit raw architecture")
    original_data=data
    selection=None
    is_macho=data[:4] in (b"\xca\xfe\xba\xbe",b"\xbe\xba\xfe\xca",b"\xca\xfe\xba\xbf",b"\xbf\xba\xfe\xca",b"\xce\xfa\xed\xfe",b"\xcf\xfa\xed\xfe",b"\xfe\xed\xfa\xce",b"\xfe\xed\xfa\xcf")
    if is_macho:
        from .macho_slices import select_macho_slice
        data,selection=select_macho_slice(data,slice_arch)
    elif slice_arch is not None:raise ValueError('slice_arch applies only to Mach-O containers')
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

    metadata = {"filename": path.name, "mapping": "preferred static virtual addresses", "source_sha256": hashlib.sha256(original_data).hexdigest(), "file_mappings":[]}
    if selection:
        metadata['macho_slice']=selection
        metadata['slice_arch']=selection['selector']
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
        metadata['selected_image']='pe'
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
    excluded_seeds=set()
    if file_format=='ELF':
        valid_functions=set()
        for symbol in binary.symbols:
            kind=str(symbol.type).rsplit('.',1)[-1];address=int(symbol.value);section=int(symbol.shndx)
            if kind=='FUNC' and section not in (0,0xfff1,0xfff2):valid_functions.add(address)
            elif kind in ('OBJECT','TLS','GNU_IFUNC','IFUNC') or section==0xfff1:excluded_seeds.add(address)
        excluded_seeds-=valid_functions
    elif file_format=='Mach-O':
        from .macho_metadata import inspect_macho
        exports=inspect_macho(binary,data)['exports']
        # LIEF's abstract functions include every exported address, including
        # constants in executable __TEXT segments. Preserve the section/trie
        # classification rather than promoting segment permissions to code.
        excluded_seeds={item['address'] for item in exports
                        if item['address'] is not None and not item['is_code']}
        excluded_seeds-={item['address'] for item in exports if item['is_code']}
    macho_text_base = None
    macho_code_sections = []
    macho_unwind_offsets = set()
    if file_format == "Mach-O" and arch == "arm64":
        text_segments = [segment for segment in binary.segments if segment.name == "__TEXT"]
        if len(text_segments) == 1:
            macho_text_base = int(text_segments[0].virtual_address)
        executable_segments = {segment.name for segment in binary.segments
                               if segment.init_protection & 4}
        macho_code_sections = [section for section in binary.sections
                               if section.segment_name in executable_segments and
                               (section.has(lief.MachO.Section.FLAGS.PURE_INSTRUCTIONS) or
                                section.has(lief.MachO.Section.FLAGS.SOME_INSTRUCTIONS))]
        macho_unwind_offsets = {int(function.address) for function in binary.unwind_functions}
    normalized_unwind = 0
    for function in binary.functions:
        raw_address = int(function.address)
        address = raw_address
        source = "symbol_or_unwind"
        if file_format == "PE":
            address += imagebase  # LIEF PE function entries are RVAs.
        elif file_format == "Mach-O" and arch == "arm64":
            address, relative = _macho_function_address(raw_address, macho_text_base,
                                                        macho_code_sections, regions,
                                                        metadata['file_mappings'], len(data))
            if relative:
                source = "LC_UNWIND_INFO" if raw_address in macho_unwind_offsets else "symbol_or_unwind_relative"
        if present and address == entry and function.name and seeds[0].name == "entry":
            seeds[0] = Seed(entry, function.name, "entry + symbol_or_unwind")
        valid = (_macho_instruction_start(address, macho_code_sections, regions,
                                          metadata['file_mappings'], len(data))
                 if file_format == "Mach-O" and arch == "arm64" else _is_executable(address, regions))
        if address not in seen and address not in excluded_seeds and valid:
            seen.add(address)
            seeds.append(Seed(address, function.name or f"sub_{address:x}", source))
            normalized_unwind += int(source == "LC_UNWIND_INFO")
    if file_format == "Mach-O" and arch == "arm64" and binary.has_function_starts:
        # LIEF exposes LC_FUNCTION_STARTS as offsets from __TEXT, whereas its
        # symbols and `binary.entrypoint` use preferred virtual addresses.
        # Treating those offsets as absolute loses nearly every Swift function.
        starts = list(binary.function_starts.functions)
        if len(starts) > MAX_MACHO_FUNCTION_STARTS:
            raise ValueError("Mach-O LC_FUNCTION_STARTS exceeds the supported seed limit")
        if macho_text_base is None:
            raise ValueError("Mach-O LC_FUNCTION_STARTS requires one __TEXT segment")
        if starts and not macho_code_sections:
            raise ValueError("Mach-O LC_FUNCTION_STARTS has no declared instruction section")
        seeded = 0
        for relative in starts:
            offset = int(relative)
            address = macho_text_base + offset
            if (offset < 0 or address >= 1 << 64 or address % 4 or
                address in excluded_seeds or
                not _macho_instruction_start(address, macho_code_sections, regions,
                                             metadata['file_mappings'], len(data))):
                raise ValueError(f"invalid Mach-O LC_FUNCTION_STARTS entry at relative offset 0x{offset:x}")
            if address not in seen:
                seen.add(address)
                seeds.append(Seed(address, f"sub_{address:x}", "LC_FUNCTION_STARTS"))
                seeded += 1
        metadata["macho_function_starts"] = {
            "declared": len(starts), "seeded": seeded,
            "source": "LC_FUNCTION_STARTS relative to __TEXT", "status": "validated",
        }
    if normalized_unwind:
        metadata["macho_unwind_relative_seeds"] = normalized_unwind
    metadata["seed_count"] = len(seeds)
    metadata["relocations"] = "recorded mapping only; no runtime relocation applied"
    if selection and selection['offset']:
        for mapping in metadata['file_mappings']:mapping['file_offset']+=selection['offset']
    return Image(file_format, arch, bits, entry, regions, seeds, metadata, source_bytes=original_data)
