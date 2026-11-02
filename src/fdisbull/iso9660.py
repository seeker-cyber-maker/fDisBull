"""Bounded metadata-only inspection of the primary ISO 9660 directory tree.

The caller supplies 2048-byte logical sectors relative to the data track. This
reader does not interpret supplementary trees, system-use extensions, or file
contents. See ECMA-119 sections 8, 9 and 10.
"""

from collections import deque


SECTOR_SIZE = 2048


class _Invalid(Exception):
    pass


class _Incomplete(Exception):
    pass


def _both(data, offset, width):
    little = int.from_bytes(data[offset:offset + width], "little")
    big = int.from_bytes(data[offset + width:offset + 2 * width], "big")
    if little != big:
        raise _Invalid("inconsistent both-endian integer")
    return little


def _record(data):
    if len(data) < 34 or data[0] != len(data):
        raise _Invalid("invalid directory record length")
    n = data[32]
    if not n or 33 + n + (n % 2 == 0) > len(data):
        raise _Invalid("invalid directory identifier length")
    if data[1] or data[26] or data[27] or data[25] & 0x80:
        raise _Invalid("extended attributes, interleaving or multi-extent records are unsupported")
    if _both(data, 28, 2) != 1:
        raise _Invalid("multi-volume directory record is unsupported")
    return {"extent": _both(data, 2, 4), "size": _both(data, 10, 4),
            "directory": bool(data[25] & 2), "name": data[33:33+n],
            "system_use": any(data[33 + n + (n % 2 == 0):])}


def inspect_iso(read_sector, sector_count, *, max_entries=10000,
                max_directory_bytes=8 * 1024 * 1024, max_depth=32):
    """Inspect the primary tree, returning JSON-safe bounded metadata.

    ``valid`` means no invalid/unsupported structure was encountered; ``complete``
    additionally requires a terminator and a fully traversed primary tree. An
    unreadable extent or exhausted budget leaves validity unknown (None).
    """
    if any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in
           (sector_count, max_entries, max_directory_bytes, max_depth)):
        raise ValueError("sector count and limits must be non-negative integers")
    if max_entries > 100000 or max_directory_bytes > 64 * 1024 * 1024 or max_depth > 128:
        raise ValueError("inspection limits exceed hard maximum")
    out = {"format": "iso9660", "valid": None, "complete": False,
           "volume_id": None, "declared_sectors": None,
           "available_sectors": sector_count, "volume_extent_fits": None,
           "validation_scope": "primary ISO 9660 metadata tree only",
           "availability_scope": "extent in supplied track range",
           "content_verified": False,
           "descriptors": [], "entries": [], "warnings": []}

    def sector(lba, limit):
        if lba < 0 or lba >= limit:
            raise _Incomplete("required metadata sector is outside available volume")
        try:
            block = read_sector(lba)
        except (OSError, ValueError, IndexError) as exc:
            raise _Incomplete("metadata sector read failed: " + str(exc)) from exc
        if not isinstance(block, bytes) or len(block) != SECTOR_SIZE:
            raise _Incomplete("metadata sector read did not return 2048 bytes")
        return block

    try:
        pvd = None
        terminated = False
        for lba in range(16, 80):
            d = sector(lba, sector_count)
            if d[1:6] != b"CD001" or d[6] != 1:
                raise _Invalid("invalid volume descriptor identifier or version")
            typ = d[0]
            if typ not in (0, 1, 2, 3, 255):
                raise _Invalid("unknown volume descriptor type")
            if typ in (2, 3):
                warning = "supplementary or partition descriptor ignored; primary tree only"
                if warning not in out["warnings"]:
                    out["warnings"].append(warning)
            out["descriptors"].append({"lba": lba, "type": typ})
            if typ == 1:
                if pvd is not None:
                    raise _Invalid("multiple primary volume descriptors are unsupported")
                pvd = d
            if typ == 255:
                terminated = True
                break
        if not terminated:
            raise _Incomplete("volume descriptor sequence exceeds 64 sectors")
        if pvd is None:
            raise _Invalid("primary volume descriptor is absent")
        declared = _both(pvd, 80, 4)
        if not declared or _both(pvd, 128, 2) != SECTOR_SIZE:
            raise _Invalid("unsupported volume size or logical block size")
        if _both(pvd, 120, 2) != 1 or _both(pvd, 124, 2) != 1:
            raise _Invalid("multi-volume sets are unsupported")
        try:
            out["volume_id"] = pvd[40:72].decode("ascii").rstrip(" ")
        except UnicodeDecodeError as exc:
            raise _Invalid("non-ASCII primary volume identifier") from exc
        out["declared_sectors"] = declared
        out["volume_extent_fits"] = declared <= sector_count
        if declared > sector_count:
            out["warnings"].append("declared volume extends beyond available data track")
        limit = min(declared, sector_count)
        if any(x["lba"] >= declared for x in out["descriptors"]):
            raise _Invalid("volume descriptors exceed declared volume")
        root = _record(pvd[156:190])
        if root["name"] != b"\0" or not root["directory"] or not root["size"]:
            raise _Invalid("invalid root directory record")
        queue = deque([(root, root, "", 0)])
        seen = set()
        seen_starts = set()
        directory_extents = []
        file_extents = []
        reserved_end = out["descriptors"][-1]["lba"] + 1
        total_bytes = 0
        while queue:
            current, parent, path, depth = queue.popleft()
            key = (current["extent"], current["size"])
            if key in seen or current["extent"] in seen_starts:
                raise _Invalid("directory cycle or reused directory extent")
            seen.add(key)
            seen_starts.add(current["extent"])
            if depth > max_depth:
                raise _Incomplete("directory depth budget exhausted")
            total_bytes += current["size"]
            if total_bytes > max_directory_bytes:
                raise _Incomplete("directory byte budget exhausted")
            count = (current["size"] + SECTOR_SIZE - 1) // SECTOR_SIZE
            if current["extent"] < reserved_end:
                raise _Invalid("directory extent overlaps reserved system or descriptor area")
            directory_extents.append((current["extent"], current["extent"] + count))
            if current["extent"] + count > declared:
                raise _Invalid("directory extent exceeds declared volume")
            if current["extent"] + count > limit:
                raise _Incomplete("directory extent exceeds available data track")
            records = []
            for i in range(count):
                block = sector(current["extent"] + i, limit)
                end = min(SECTOR_SIZE, current["size"] - i * SECTOR_SIZE)
                pos = 0
                while pos < end and block[pos]:
                    length = block[pos]
                    if pos + length > end or pos + length > SECTOR_SIZE:
                        raise _Invalid("directory record crosses sector or directory boundary")
                    rec = _record(block[pos:pos + length])
                    if rec["system_use"] and "system-use bytes are uninterpreted" not in out["warnings"]:
                        out["warnings"].append("system-use bytes are uninterpreted")
                    if len(records) >= max_entries - len(out["entries"]) + 2:
                        raise _Incomplete("entry budget exhausted")
                    records.append(rec)
                    pos += length
                if any(block[pos:end]):
                    raise _Invalid("nonzero bytes after directory sector padding")
            if len(records) < 2:
                raise _Invalid("directory lacks self and parent records")
            for rec, expected, name in ((records[0], current, b"\0"),
                                        (records[1], parent, b"\1")):
                if (rec["name"] != name or not rec["directory"] or
                    (rec["extent"], rec["size"]) != (expected["extent"], expected["size"])):
                    raise _Invalid("invalid directory self or parent record")
            names = set()
            for rec in records[2:]:
                name_bytes = rec["name"]
                try:
                    name = name_bytes.decode("ascii")
                except UnicodeDecodeError as exc:
                    raise _Invalid("non-ASCII primary directory identifier") from exc
                if (name in ("", ".", "..") or any(ord(c) < 32 or ord(c) == 127 or c in "/\\" for c in name)
                        or name in names):
                    raise _Invalid("unsafe or duplicate directory identifier")
                names.add(name)
                if len(out["entries"]) >= max_entries:
                    raise _Incomplete("entry budget exhausted")
                size, extent = rec["size"], rec["extent"]
                sectors = (size + SECTOR_SIZE - 1) // SECTOR_SIZE
                if sectors and extent < reserved_end:
                    raise _Invalid("entry extent overlaps reserved system or descriptor area")
                if not rec["directory"] and sectors:
                    file_extents.append((extent, extent + sectors))
                if extent + sectors > declared:
                    raise _Invalid("entry extent exceeds declared volume")
                child_path = path + "/" + name
                out["entries"].append({"path": child_path, "size": size,
                    "extent_lba": extent, "extent_sectors": sectors,
                    "available": extent + sectors <= sector_count,
                    "kind": "directory" if rec["directory"] else "file"})
                if rec["directory"]:
                    if not size:
                        raise _Invalid("empty directory extent")
                    queue.append((rec, current, child_path, depth + 1))
        # Sort once rather than comparing each file with every preceding file.
        ranges = sorted([(start, end, "directory") for start, end in directory_extents]
                        + [(start, end, "file") for start, end in file_extents])
        max_directory_end = max_file_end = 0
        for start, end, kind in ranges:
            if kind == "directory":
                if start < max(max_directory_end, max_file_end):
                    raise _Invalid("directory extent overlaps another recorded extent")
                max_directory_end = max(max_directory_end, end)
            else:
                if start < max_directory_end:
                    raise _Invalid("file extent overlaps directory extent")
                if start < max_file_end and "file extents overlap or alias" not in out["warnings"]:
                    out["warnings"].append("file extents overlap or alias")
                max_file_end = max(max_file_end, end)
        out["valid"] = True
        out["complete"] = True
    except _Invalid as exc:
        out["valid"] = False
        out["warnings"].append(str(exc))
    except _Incomplete as exc:
        out["warnings"].append(str(exc))
    return out
