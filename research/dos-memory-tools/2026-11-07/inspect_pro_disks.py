"""Read the supplied FAT12 images and compare exact logical-file identities.

The DFI payload offset is an explicit input-profile observation (2048 bytes),
not a universal DFI parser. This script validates both FAT copies, geometry,
directory entries, cluster chains, ownership, and extraction bounds. It neither
mounts images nor executes programs. Output originals remain private.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct


def identity(data):
    return {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def read_fat12(path, offset, output):
    container = path.read_bytes()
    image = container[offset:]
    if len(image) < 512 or image[510:512] != b"\x55\xaa":
        raise ValueError("boot sector signature missing")
    sector_size = struct.unpack_from("<H", image, 11)[0]
    spc, reserved, fats, roots, total16, media, sectors_fat = struct.unpack_from("<BHBHHBH", image, 13)
    total = total16 or struct.unpack_from("<I", image, 32)[0]
    if sector_size not in (512, 1024, 2048, 4096) or spc == 0 or spc & (spc - 1):
        raise ValueError("invalid sector/cluster geometry")
    if reserved == 0 or fats < 1 or sectors_fat == 0 or roots == 0 or total == 0:
        raise ValueError("incomplete FAT12 geometry")
    if total * sector_size != len(image):
        raise ValueError("declared image length mismatch")
    root_sectors = (roots * 32 + sector_size - 1) // sector_size
    root_sector = reserved + fats * sectors_fat
    data_sector = root_sector + root_sectors
    clusters = (total - data_sector) // spc
    if not 0 < clusters < 4085 or data_sector >= total:
        raise ValueError("not a bounded FAT12 geometry")
    fat_copies = [image[(reserved + i * sectors_fat) * sector_size:
                        (reserved + (i + 1) * sectors_fat) * sector_size]
                  for i in range(fats)]
    if any(x != fat_copies[0] for x in fat_copies[1:]):
        raise ValueError("FAT copies disagree")
    fat = fat_copies[0]
    if fat[0] != media or len(fat) * 2 // 3 < clusters + 2:
        raise ValueError("invalid FAT media/capacity")

    def next_cluster(number):
        i = number + number // 2
        value = fat[i] | fat[i + 1] << 8
        return (value >> 4 if number & 1 else value) & 0xFFF

    if next_cluster(1) < 0xFF8:
        raise ValueError("reserved FAT entry invalid")
    cluster_size = spc * sector_size
    owners, members, directories, skipped, seen_names = {}, [], [], [], set()

    def chain(start, owner, length=None):
        if not start:
            if length == 0:
                return [], b""
            raise ValueError("missing starting cluster")
        current, numbers, chunks, seen = start, [], [], set()
        while True:
            if not 2 <= current < clusters + 2 or current in seen:
                raise ValueError("cluster out of range or cyclic")
            if current in owners:
                raise ValueError("cross-linked cluster")
            owners[current] = owner
            seen.add(current)
            numbers.append(current)
            start_byte = (data_sector + (current - 2) * spc) * sector_size
            chunk = image[start_byte:start_byte + cluster_size]
            if len(chunk) != cluster_size:
                raise ValueError("truncated cluster")
            chunks.append(chunk)
            following = next_cluster(current)
            if following >= 0xFF8:
                break
            if following < 2 or following >= 0xFF0:
                raise ValueError("file chain enters free, bad, or reserved cluster")
            current = following
        data = b"".join(chunks)
        if length is not None:
            if len(data) < length or len(data) - length >= cluster_size:
                raise ValueError("chain allocation inconsistent with file size")
            data = data[:length]
        return numbers, data

    def directory(data, parent="", root=False):
        for index in range(0, len(data), 32):
            entry = data[index:index + 32]
            if len(entry) < 32 or entry[0] == 0:
                break
            if entry[0] == 0xE5:
                skipped.append({"parent": parent, "slot": index // 32, "kind": "deleted"})
                continue
            attrs = entry[11]
            if attrs == 0x0F:
                skipped.append({"parent": parent, "slot": index // 32, "kind": "long-filename entry"})
                continue
            name = entry[:8].decode("ascii", "strict").rstrip()
            ext = entry[8:11].decode("ascii", "strict").rstrip()
            if name in (".", ".."):
                continue
            if attrs & 0x08:
                skipped.append({"parent": parent, "slot": index // 32, "kind": "volume label"})
                continue
            if not name or any(c in name + ext for c in "/\\:\0"):
                raise ValueError("unsafe short filename")
            filename = name + ("." + ext if ext else "")
            relative = parent + filename
            if relative.upper() in seen_names:
                raise ValueError("ambiguous DOS filename")
            seen_names.add(relative.upper())
            high = struct.unpack_from("<H", entry, 20)[0]
            start = struct.unpack_from("<H", entry, 26)[0]
            size = struct.unpack_from("<I", entry, 28)[0]
            if high:
                raise ValueError("FAT12 entry has high cluster number")
            if attrs & 0x10:
                numbers, contents = chain(start, relative)
                directories.append({"path": relative, "cluster_chain": numbers})
                directory(contents, relative + "/")
            else:
                numbers, contents = chain(start, relative, size)
                dest = output / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                with dest.open("xb") as stream:
                    stream.write(contents)
                members.append({"path": relative, **identity(contents),
                                "attributes": attrs, "first_cluster": start,
                                "cluster_chain": numbers})

    output.mkdir(parents=True, exist_ok=False)
    directory(image[root_sector * sector_size:root_sector * sector_size + roots * 32], root=True)
    bad = [i for i in range(2, clusters + 2) if next_cluster(i) == 0xFF7]
    return {"container": {"name": path.name, **identity(container)},
            "payload_offset": offset, "payload": identity(image),
            "geometry": {"bytes_per_sector": sector_size, "sectors_per_cluster": spc,
                         "reserved_sectors": reserved, "fat_copies": fats,
                         "sectors_per_fat": sectors_fat, "root_entries": roots,
                         "total_sectors": total, "data_first_sector": data_sector,
                         "data_clusters": clusters},
            "fat_copies_identical": True, "layout_and_chains_checked": True,
            "bad_clusters": bad, "members": members,
            "directories": directories, "skipped_directory_entries": skipped}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("extracted", type=Path)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    profiles = [("ima", "ima30a/GWP30A.IMA", 0),
                ("dfi", "dfi30a/GWP30A.dfi", 2048),
                ("rar_embedded_ima", "english30a/gwpro30a.ima", 0)]
    report = {"schema": "gamewizard-pro-disk-intake-1", "images": []}
    for label, relative, offset in profiles:
        row = read_fat12(args.extracted / relative, offset, args.output / label)
        row["label"] = label
        report["images"].append(row)
        print(json.dumps({"label": label, "files": len(row["members"]),
                          "bad_clusters": row["bad_clusters"]}), flush=True)
    a = (args.extracted / "ima30a/GWP30A.IMA").read_bytes()
    b = (args.extracted / "dfi30a/GWP30A.dfi").read_bytes()[2048:]
    changes = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    if len(a) != len(b):
        raise ValueError("IMA and DFI payload lengths differ")
    report["ima_vs_dfi_payload"] = {"different_bytes": len(changes),
        "different_sectors": sorted({i // 512 for i in changes}),
        "first_difference": min(changes) if changes else None,
        "last_difference_exclusive": max(changes) + 1 if changes else None}
    report["embedded_ima_identical"] = a == (args.extracted / "english30a/gwpro30a.ima").read_bytes()
    file_sets = [{x["path"]: x["sha256"] for x in row["members"]} for row in report["images"]]
    report["all_three_logical_file_sets_identical"] = all(x == file_sets[0] for x in file_sets)
    (args.output / "disk_inventory.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
