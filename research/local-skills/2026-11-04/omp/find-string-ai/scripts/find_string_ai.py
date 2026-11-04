import json
import lldb
import shlex


def _find_all(buf, needle):
    out = []
    start = 0
    while True:
        idx = buf.find(needle, start)
        if idx < 0:
            return out
        out.append(idx)
        start = idx + 1


def findstringai(debugger, command, result, internal_dict):
    try:
        args = shlex.split(command)
    except ValueError as exc:
        result.PutCString('argument parse failed: %s' % exc)
        return
    if not args:
        result.PutCString('usage: findstringai <ascii-string> [max_hits]')
        return

    needle = args[0].encode('utf-8')
    max_hits = int(args[1]) if len(args) > 1 else 20

    target = debugger.GetSelectedTarget()
    process = target.GetProcess()
    if not process or not process.IsValid():
        result.PutCString('no valid process')
        return

    chunk = 1024 * 1024
    overlap = max(len(needle) - 1, 0)
    max_region = 256 * 1024 * 1024
    max_total = 3 * 1024 * 1024 * 1024
    max_address = 0x0001000000000000

    scanned = 0
    readable_regions = 0
    skipped_large = 0
    regions_seen = 0
    hits = []
    addr_probe = 0

    while addr_probe < max_address:
        r = lldb.SBMemoryRegionInfo()
        err = process.GetMemoryRegionInfo(addr_probe, r)
        if not err.Success():
            break

        start = r.GetRegionBase()
        end = r.GetRegionEnd()
        regions_seen += 1
        next_probe = end if end > addr_probe else addr_probe + 0x1000
        addr_probe = next_probe

        if not r.IsReadable():
            continue
        size = end - start
        if size <= 0:
            continue
        readable_regions += 1
        if size > max_region:
            skipped_large += 1
            continue

        addr = start
        carry = b''
        while addr < end:
            if scanned >= max_total or len(hits) >= max_hits:
                break
            to_read = min(chunk, end - addr)
            e = lldb.SBError()
            data = process.ReadMemory(addr, to_read, e)
            if not e.Success() or not data:
                addr += to_read
                carry = b''
                continue

            blob = carry + data
            base = addr - len(carry)
            for idx in _find_all(blob, needle):
                hit_addr = base + idx
                ctx_start = max(0, idx - 80)
                ctx_end = min(len(blob), idx + len(needle) + 120)
                hits.append({
                    'address': hex(hit_addr),
                    'region_start': hex(start),
                    'region_end': hex(end),
                    'permissions': ''.join([
                        'r' if r.IsReadable() else '-',
                        'w' if r.IsWritable() else '-',
                        'x' if r.IsExecutable() else '-',
                    ]),
                    'region_name': r.GetName() or '',
                    'context_latin1': blob[ctx_start:ctx_end].decode('latin1', 'replace'),
                })
                if len(hits) >= max_hits:
                    break

            scanned += len(data)
            addr += to_read
            carry = data[-overlap:] if overlap else b''

        if scanned >= max_total or len(hits) >= max_hits:
            break

    result.PutCString(json.dumps({
        'needle': needle.decode('utf-8', 'replace'),
        'hits': hits,
        'hit_count': len(hits),
        'readable_regions_considered': readable_regions,
        'skipped_large_regions': skipped_large,
        'regions_seen': regions_seen,
        'bytes_scanned': scanned,
        'max_region_bytes': max_region,
        'max_total_bytes': max_total,
    }, indent=2))


def __lldb_init_module(debugger, internal_dict):
    debugger.HandleCommand('command script add -f find_string_ai.findstringai findstringai')
