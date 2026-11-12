"""Bounded CLR metadata inspection and real CIL decoding; never executes code.

Metadata uses dnfile and instructions use Mandiant dncil when those optional
packages are installed. The dependency-free CLR-directory probe protects IL
from being mistaken for native instructions. This is not C# decompilation,
IL verification, runtime reflection, a JIT, or NativeAOT reconstruction.

Primary format reference: ECMA-335, partitions II (metadata/method headers) and
III (CIL). Decoder reference: https://github.com/mandiant/dncil .
"""
from __future__ import annotations

import math
import struct

MAX_INPUT = 64 * 1024 * 1024
MAX_METADATA = 16 * 1024 * 1024
MAX_TABLE_ROWS = 200000
MAX_METHODS = 20000
MAX_CODE = 1024 * 1024
MAX_SWITCH = 4096
MAX_TEXT = 4 * 1024 * 1024


def _input(data):
    if not isinstance(data, bytes):
        raise ValueError("managed analysis requires immutable file bytes")
    if len(data) > MAX_INPUT:
        raise ValueError("managed input exceeds 64 MiB")
    return data


def _layout(data):
    if len(data) < 64 or data[:2] != b"MZ":
        return None
    pe = struct.unpack_from("<I", data, 60)[0]
    if pe < 64 or pe + 24 > len(data) or data[pe:pe + 4] != b"PE\0\0":
        return None
    count = struct.unpack_from("<H", data, pe + 6)[0]
    optional_size = struct.unpack_from("<H", data, pe + 20)[0]
    optional = pe + 24
    if optional_size < 2 or optional + optional_size > len(data):
        raise ValueError("truncated PE optional header")
    magic = struct.unpack_from("<H", data, optional)[0]
    if magic not in (0x10B, 0x20B):
        raise ValueError("unsupported PE optional-header magic")
    directory = optional + (96 if magic == 0x10B else 112)
    if directory > optional + optional_size:
        raise ValueError("truncated PE standard optional header")
    return dict(pe=pe, optional=optional, optional_size=optional_size, directory=directory,
                section_table=optional + optional_size, section_count=count,
                format="PE32" if magic == 0x10B else "PE32+")


def _sections(data, layout):
    count, start = layout["section_count"], layout["section_table"]
    if count > 4096 or start + count * 40 > len(data):
        raise ValueError("invalid or truncated PE section table")
    sections = []
    for index in range(count):
        position = start + index * 40
        virtual_size, rva, size, offset = struct.unpack_from("<IIII", data, position + 8)
        if size and offset + size > len(data):
            raise ValueError("PE raw section extends beyond file bytes")
        sections.append(dict(rva=rva, virtual_size=virtual_size, file_size=size, file_offset=offset))
    return sections


def _map(data, layout, sections, rva, size):
    if not isinstance(rva, int) or not isinstance(size, int) or rva < 0 or size < 0 or rva + size > 1 << 32:
        raise ValueError("invalid managed RVA extent")
    headers = struct.unpack_from("<I", data, layout["optional"] + 60)[0]
    matches = []
    if rva < headers and rva + size <= min(headers, len(data)):
        matches.append(rva)
    for section in sections:
        delta = rva - section["rva"]
        if 0 <= delta and delta + size <= section["file_size"]:
            matches.append(section["file_offset"] + delta)
    if len(matches) != 1:
        raise ValueError("managed RVA is not uniquely file-backed")
    return matches[0]


def _metadata(data, offset, size):
    end = offset + size
    if size < 20 or data[offset:offset + 4] != b"BSJB":
        raise ValueError("invalid CLR metadata root signature")
    version_size = struct.unpack_from("<I", data, offset + 12)[0]
    if version_size > 4096 or offset + 16 + version_size + 4 > end:
        raise ValueError("invalid CLR metadata version-string extent")
    version = data[offset + 16:offset + 16 + version_size].rstrip(b"\0").decode("utf-8", "replace")[:128]
    cursor = offset + 16 + version_size
    stream_count = struct.unpack_from("<H", data, cursor + 2)[0]
    cursor += 4
    if stream_count > 64:
        raise ValueError("CLR metadata stream count exceeds 64")
    streams = []
    for _ in range(stream_count):
        if cursor + 8 > end:
            raise ValueError("truncated CLR stream header")
        stream_offset, stream_size = struct.unpack_from("<II", data, cursor)
        name_end = data.find(b"\0", cursor + 8, min(cursor + 40, end))
        if name_end < 0:
            raise ValueError("unterminated CLR stream name")
        name = data[cursor + 8:name_end].decode("ascii", "strict")
        cursor = offset + ((name_end + 1 - offset + 3) & ~3)
        if stream_offset + stream_size > size:
            raise ValueError("CLR metadata stream extends beyond metadata directory")
        streams.append(dict(name=name, offset=stream_offset, size=stream_size))
    if any(offset + stream["offset"] < cursor for stream in streams):
        raise ValueError("CLR metadata stream overlaps stream headers")
    if len({stream["name"] for stream in streams}) != len(streams):
        raise ValueError("duplicate CLR metadata stream names are ambiguous")
    nonempty = sorted((stream for stream in streams if stream["size"]), key=lambda stream: stream["offset"])
    if any(left["offset"] + left["size"] > right["offset"] for left, right in zip(nonempty, nonempty[1:])):
        raise ValueError("CLR metadata stream extents overlap")
    table_streams = [stream for stream in streams if stream["name"] in ("#~", "#-")]
    if len(table_streams) != 1:
        raise ValueError("CLR metadata requires one unambiguous tables stream")
    tables = table_streams[0]
    position, table_end = offset + tables["offset"], offset + tables["offset"] + tables["size"]
    if position + 24 > table_end:
        raise ValueError("truncated CLR metadata tables header")
    valid = struct.unpack_from("<Q", data, position + 8)[0]
    position += 24
    counts = {}
    for index in range(64):
        if valid & (1 << index):
            if position + 4 > table_end:
                raise ValueError("truncated CLR metadata row counts")
            counts[str(index)] = struct.unpack_from("<I", data, position)[0]
            position += 4
    if sum(counts.values()) > MAX_TABLE_ROWS:
        raise ValueError(f"CLR metadata exceeds {MAX_TABLE_ROWS} table rows")
    return dict(version=version, streams=streams, table_rows=counts)


def managed_kind(data: bytes) -> dict:
    """Probe CLR metadata without optional dependencies or native-code decoding.

    A PE CLR directory is recognized even if its contents are invalid. NativeAOT
    can have no CLR/CIL payload; absence of CLR is not proof of NativeAOT origin.
    """
    data = _input(data)
    result = dict(managed=False, recognized=False, status="non_managed", il_only=None,
                  native_entrypoint=None, native_aot="not_determined", clr_header=None,
                  metadata=None, warnings=[])
    try:
        layout = _layout(data)
        if layout is None:
            result["warnings"].append("No PE CLR directory recognized. NativeAOT/native-only files require native analysis; NativeAOT origin is not determined.")
            return result
        result["format"] = layout["format"]
        # CLR loaders may ignore NumberOfRvaAndSizes. Inspect a physically
        # present COM_DESCRIPTOR slot even if that count was deliberately zeroed.
        slot = layout["directory"] + 14 * 8
        if slot + 8 > layout["optional"] + layout["optional_size"]:
            result["warnings"].append("PE optional header has no CLR directory slot; NativeAOT origin is not determined.")
            return result
        rva, size = struct.unpack_from("<II", data, slot)
        if not rva and not size:
            result["warnings"].append("PE has no CLR metadata directory. NativeAOT may be native-only; no recoverable CIL is established.")
            return result
        result.update(managed=True, recognized=True)
        if not rva or size < 72 or size > 4096:
            raise ValueError("invalid CLR header directory extent")
        sections = _sections(data, layout)
        offset = _map(data, layout, sections, rva, size)
        header_size = struct.unpack_from("<I", data, offset)[0]
        if not 72 <= header_size <= size:
            raise ValueError("invalid CLR header size")
        metadata_rva, metadata_size, flags, entrypoint = struct.unpack_from("<IIII", data, offset + 8)
        result.update(il_only=bool(flags & 1), native_entrypoint=bool(flags & 0x10))
        result["clr_header"] = dict(rva=rva, size=size, file_offset=offset, flags=flags,
            runtime_major=struct.unpack_from("<H", data, offset + 4)[0], runtime_minor=struct.unpack_from("<H", data, offset + 6)[0],
            metadata_rva=metadata_rva, metadata_size=metadata_size, entrypoint=entrypoint,
            entrypoint_kind="native_rva" if flags & 0x10 else "metadata_token")
        if not metadata_rva or not 20 <= metadata_size <= MAX_METADATA:
            raise ValueError("invalid or oversized CLR metadata directory")
        metadata_offset = _map(data, layout, sections, metadata_rva, metadata_size)
        result["metadata"] = dict(rva=metadata_rva, size=metadata_size, file_offset=metadata_offset,
                                  **_metadata(data, metadata_offset, metadata_size))
        native_rva, native_size = struct.unpack_from("<II", data, offset + 64)
        if native_rva or native_size:
            result["clr_header"]["managed_native_header"] = dict(rva=native_rva, size=native_size)
            result["warnings"].append("CLR managed-native header present; precompiled native payload is not decoded by the CIL API.")
        result["status"] = "managed"
    except (ValueError, struct.error, UnicodeError) as exc:
        result["status"] = "invalid_managed" if result["managed"] else "non_managed"
        result["warnings"].append(str(exc))
    return result


def _dependencies():
    try:
        import dnfile
        from dncil.cil.body.reader import CilMethodBodyReaderBytes
        from dncil.cil.enums import FlowControl, OperandType
        from dncil.clr.token import StringToken, Token
    except ImportError as exc:
        raise ValueError("Managed metadata/CIL decoding requires optional packages: pip install 'fdisbull[managed]' (dnfile==0.18.0, dncil==1.0.2)") from exc
    return dnfile, CilMethodBodyReaderBytes, FlowControl, OperandType, StringToken, Token


def _open(data):
    dnfile, *_ = _dependencies()
    pe = dnfile.dnPE(data=data, fast_load=True, clr_lazy_load=True)
    try:
        pe.parse_data_directories([14])
        if getattr(pe, "net", None) is None or pe.net.mdtables is None:
            raise ValueError("dnfile could not parse the recognized CLR metadata")
        return pe
    except Exception:
        pe.close()
        raise


def _text(value):
    return str(value)[:4096] if value is not None else ""


def _table(pe, number):
    return pe.net.mdtables.tables.get(number)


def _owners(pe):
    methods, fields = {}, {}
    table = _table(pe, 2)
    if table:
        for row in table.rows:
            namespace, name = _text(row.TypeNamespace), _text(row.TypeName)
            full_name = (namespace + "." if namespace else "") + name
            for item in row.MethodList:
                methods[item.row_index] = full_name
            for item in row.FieldList:
                fields[item.row_index] = full_name
    return methods, fields


def _method(pe, row, rid, owners):
    flags, impl = int(row.struct.Flags), int(row.struct.ImplFlags)
    rva = int(row.Rva)
    has_cil = bool(rva and impl & 3 == 0 and not flags & (0x400 | 0x2000))
    name, owner = _text(row.Name), owners.get(rid, "")
    offset = None
    if rva:
        try:
            offset = int(pe.get_offset_from_rva(rva))
        except Exception:
            pass
    signature = row.Signature.value if row.Signature is not None else b""
    return dict(token=f"0x{0x06000000 | rid:08x}", token_value=0x06000000 | rid,
                name=name, type_name=owner, full_name=(owner + "::" if owner else "") + name,
                rva=rva, file_offset=offset, signature=bytes(signature or b"")[:4096].hex(), flags=flags, impl_flags=impl,
                has_cil_body=has_cil, body_kind="cil" if has_cil else "none" if not rva else "native_or_runtime")


def inspect_managed(data: bytes) -> dict:
    """Return bounded managed method metadata. Tokens are not native addresses."""
    probe = managed_kind(data)
    result = dict(probe, assembly=None, methods=[], method_count=0, methods_returned=0,
                  budget_exhausted=False, backend="dnfile 0.18.0 / dncil 1.0.2")
    if probe["status"] != "managed":
        return result
    pe = None
    try:
        pe = _open(data)
        owners, _ = _owners(pe)
        table = _table(pe, 6)
        rows = table.rows if table else []
        result["method_count"] = len(rows)
        text_used = 0
        for rid, row in enumerate(rows[:MAX_METHODS], 1):
            method = _method(pe, row, rid, owners)
            text_used += sum(len(value) for value in method.values() if isinstance(value, str))
            if text_used > MAX_TEXT:
                break
            result["methods"].append(method)
        result["methods_returned"] = len(result["methods"])
        result["budget_exhausted"] = len(rows) > len(result["methods"])
        assembly = _table(pe, 32)
        if assembly and assembly.rows:
            row = assembly.rows[0]
            result["assembly"] = dict(name=_text(row.Name), version=f"{row.MajorVersion}.{row.MinorVersion}.{row.BuildNumber}.{row.RevisionNumber}", culture=_text(row.Culture))
        if result["budget_exhausted"]:
            result["warnings"].append(f"Method output capped at {MAX_METHODS} records or 4 MiB text; metadata summary is partial.")
        result["warnings"].append("Method signatures are raw metadata blobs; this API does not reconstruct C# source or verify IL types.")
    except ValueError as exc:
        result["status"] = "dependencies_missing" if "optional packages" in str(exc) else "invalid_managed"
        result["warnings"].append(str(exc))
    except Exception as exc:
        result["status"] = "invalid_managed"
        result["warnings"].append(f"CLR metadata parse failed: {type(exc).__name__}: {str(exc)[:512]}")
    finally:
        if pe is not None:
            pe.close()
    return result


def _resolve_unchecked(pe, token, method_owners, field_owners, depth=0):
    value = int(token)
    result = dict(token=f"0x{value:08x}", token_value=value, resolved=False, name=None, table=None)
    table_number, rid = value >> 24, value & 0xFFFFFF
    if table_number == 0x70:
        result["table"] = "UserString"
        item = pe.net.user_strings.get(rid) if pe.net.user_strings is not None and rid else None
        if item is not None and item.value is not None:
            result.update(resolved=True, name=_text(item.value), value=_text(item.value), truncated=len(str(item.value)) > 4096)
        return result
    table = _table(pe, table_number)
    if table is None or not 1 <= rid <= len(table.rows) or depth > 8:
        return result
    row = table.rows[rid - 1]
    result["table"] = table.name
    if table_number in (1, 2):
        namespace, name = _text(row.TypeNamespace), _text(row.TypeName)
        result.update(resolved=True, name=(namespace + "." if namespace else "") + name)
    elif table_number in (4, 6):
        owner = (field_owners if table_number == 4 else method_owners).get(rid, "")
        result.update(resolved=True, name=(owner + "::" if owner else "") + _text(row.Name))
    elif table_number == 10:
        parent = row.Class
        parent_name = None
        if parent and parent.table and parent.row_index:
            parent_name = _resolve(pe, (parent.table.number << 24) | parent.row_index, method_owners, field_owners, depth + 1)["name"]
        result.update(resolved=True, name=(parent_name + "::" if parent_name else "") + _text(row.Name))
    elif table_number == 43:
        parent = row.Method
        resolved = _resolve(pe, (parent.table.number << 24) | parent.row_index, method_owners, field_owners, depth + 1)
        result.update(resolved=resolved["resolved"], name=resolved["name"], instantiation=bytes(row.Instantiation.value or b"")[:4096].hex())
    elif hasattr(row, "Name"):
        result.update(resolved=True, name=_text(row.Name))
    elif hasattr(row, "Signature"):
        result.update(resolved=True, name="signature " + bytes(row.Signature.value or b"")[:4096].hex())
    return result


def _resolve(pe, token, method_owners, field_owners, depth=0):
    try:
        return _resolve_unchecked(pe, token, method_owners, field_owners, depth)
    except Exception as exc:
        return dict(token=f"0x{int(token):08x}", token_value=int(token), resolved=False, name=None,
                    table=None, warning=f"unresolved metadata token: {type(exc).__name__}: {str(exc)[:128]}")


def _method_header(data, layout, sections, rva):
    offset = _map(data, layout, sections, rva, 1)
    first = data[offset]
    if first & 3 == 2:
        header_size, code_size, max_stack, local_token, flags = 1, first >> 2, 8, 0, 2
    elif first & 3 == 3:
        _map(data, layout, sections, rva, 12)
        flags = struct.unpack_from("<H", data, offset)[0]
        header_size = (flags >> 12) * 4
        if not 12 <= header_size <= 60:
            raise ValueError("invalid fat CIL method header size")
        max_stack, code_size, local_token = struct.unpack_from("<HII", data, offset + 2)
    else:
        raise ValueError("invalid CIL method header format")
    if code_size > MAX_CODE:
        raise ValueError("CIL method code exceeds the 1 MiB limit")
    _map(data, layout, sections, rva, header_size + code_size)
    return dict(file_offset=offset, header_size=header_size, code_size=code_size, max_stack=max_stack,
                local_signature_token=f"0x{local_token:08x}" if local_token else None,
                init_locals=bool(flags & 0x10), exception_sections_present=bool(flags & 8))


def disassemble_managed(data: bytes, token, max_instructions=10000) -> dict:
    """Decode one method's CIL stream through dncil, with method-local offsets."""
    if isinstance(max_instructions, bool) or not isinstance(max_instructions, int) or not 1 <= max_instructions <= 100000:
        raise ValueError("max_instructions must be an integer in 1..100000")
    if isinstance(token, bool) or not isinstance(token, (str, int)):
        raise ValueError("method token must be a MethodDef integer or hexadecimal string")
    try:
        token = int(token, 0) if isinstance(token, str) else token
    except ValueError as exc:
        raise ValueError("method token must be a MethodDef integer or 0x hexadecimal string") from exc
    if token >> 24 != 6 or not token & 0xFFFFFF:
        raise ValueError("CIL method token must identify a nonzero MethodDef row (0x06xxxxxx)")
    probe = managed_kind(data)
    if probe["status"] != "managed":
        raise ValueError("No validated managed CIL metadata: " + "; ".join(probe["warnings"]))
    _, Reader, Flow, Operand, StringToken, Token = _dependencies()
    pe = _open(data)
    try:
        table, rid = _table(pe, 6), token & 0xFFFFFF
        if table is None or rid > len(table.rows):
            raise ValueError("MethodDef token is not present in this assembly")
        method_owners, field_owners = _owners(pe)
        method = _method(pe, table.rows[rid - 1], rid, method_owners)
        if not method["has_cil_body"]:
            raise ValueError("Selected method has no managed CIL body; native/runtime/abstract/PInvoke methods are not decoded as CIL")
        layout = _layout(data)
        header = _method_header(data, layout, _sections(data, layout), method["rva"])
        code_offset = header["file_offset"] + header["header_size"]
        code = data[code_offset:code_offset + header["code_size"]]
        reader = Reader(code)
        instructions, token_refs, branches, warnings = [], [], [], list(probe["warnings"])
        invalid = False
        output_limited, text_used = False, 0
        while reader.tell() < len(code) and len(instructions) < max_instructions:
            offset = reader.tell()
            try:
                if code[offset] == 0x45:
                    if offset + 5 > len(code):
                        raise ValueError("truncated CIL switch count")
                    count = struct.unpack_from("<I", code, offset + 1)[0]
                    if count > MAX_SWITCH or offset + 5 + count * 4 > len(code):
                        raise ValueError("invalid or oversized CIL switch table")
                instruction = reader.read_instruction(offset)
                size = reader.tell() - offset
                if size <= 0 or reader.tell() > len(code):
                    raise ValueError("CIL instruction exceeds method body")
                flow = {Flow.Branch: "jump", Flow.Cond_Branch: "conditional", Flow.Call: "call", Flow.Return: "return",
                        Flow.Throw: "throw", Flow.Break: "break", Flow.Meta: "prefix"}.get(instruction.opcode.flow_control, "next")
                operand, refs, pending_branches = instruction.operand, [], []
                if isinstance(operand, Token):
                    resolved = _resolve(pe, operand.value, method_owners, field_owners)
                    kind = "string" if isinstance(operand, StringToken) else "call" if flow == "call" else "token"
                    reference = dict(offset=offset, kind=kind, **resolved)
                    refs.append(reference)
                    operand_value = f"0x{operand.value:08x}"
                    display = operand_value + (" ; " + str(resolved["name"]) if resolved["name"] is not None else " ; unresolved metadata token")
                    if instruction.mnemonic == "calli":
                        flow = "indirect_call"
                elif instruction.opcode.operand_type in (Operand.InlineBrTarget, Operand.ShortInlineBrTarget):
                    operand_value = int(operand)
                    display = f"IL_{operand:04x}"
                    pending_branches.append(dict(source_offset=offset, target_offset=operand, kind="branch"))
                elif instruction.opcode.operand_type == Operand.InlineSwitch:
                    operand_value = list(operand)
                    display = ", ".join(f"IL_{target:04x}" for target in operand)
                    pending_branches.extend(dict(source_offset=offset, target_offset=target, kind="switch") for target in operand)
                elif operand is None:
                    operand_value, display = None, ""
                elif isinstance(operand, (int, float, str)):
                    operand_value = str(operand) if isinstance(operand, float) and not math.isfinite(operand) else operand
                    display = str(operand_value)
                else:
                    operand_value, display = str(operand), str(operand)
                text_used += len(display) + sum(len(str(ref.get("name") or "")) for ref in refs)
                if text_used > MAX_TEXT:
                    reader.seek(offset)
                    output_limited = True
                    break
                instructions.append(dict(offset=offset, cil_offset=f"IL_{offset:04x}", address=f"0x{token:08x}:IL_{offset:04x}",
                    rva=method["rva"] + header["header_size"] + offset, file_offset=code_offset + offset,
                    size=size, bytes=instruction.get_bytes().hex(), mnemonic=instruction.mnemonic, operands=display,
                    operand=operand_value, flow=flow, references=refs))
                token_refs.extend(refs)
                branches.extend(pending_branches)
            except Exception as exc:
                warnings.append(f"Invalid CIL at IL_{offset:04x}: {type(exc).__name__}: {str(exc)[:256]}")
                invalid = True
                break
        budget_exhausted = not invalid and (output_limited or reader.tell() < len(code) and len(instructions) >= max_instructions)
        complete = not invalid and not budget_exhausted and reader.tell() == len(code)
        starts = {instruction["offset"] for instruction in instructions}
        for branch in branches:
            branch["target_in_code"] = 0 <= branch["target_offset"] < len(code)
            branch["target_is_instruction"] = branch["target_offset"] in starts if complete or branch["target_offset"] < reader.tell() else None
        if any(branch["target_is_instruction"] is False for branch in branches):
            warnings.append("Some branch targets are outside the method or are not decoded instruction boundaries; control flow remains invalid/unresolved.")
        if budget_exhausted:
            warnings.append("CIL instruction/text budget reached; method disassembly is partial.")
        if header["exception_sections_present"]:
            warnings.append("Exception-handling sections are present but not interpreted in this slice.")
        warnings.append("Linear method-body decoding only; no IL type/stack verification or C# source reconstruction.")
        return dict(status="decoded" if complete else "invalid_cil" if invalid else "partial", managed=True,
                    title=method["full_name"], arch="cil", context=f"cil:method=0x{token:08x}", method=method, **header,
                    instructions=instructions, token_references=token_refs, branch_references=branches,
                    budget_exhausted=budget_exhausted, complete=complete, warnings=warnings,
                    backend="dncil 1.0.2", execution="none")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Managed method metadata is invalid or unsupported: {type(exc).__name__}: {str(exc)[:256]}") from exc
    finally:
        pe.close()
