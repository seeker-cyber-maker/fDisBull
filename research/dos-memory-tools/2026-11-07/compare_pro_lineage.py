"""Exact, bounded comparisons of the supplied Pro distribution variants.

This is a research comparison over explicitly selected roles and filenames.
No vendor patch is executed and no semantic-equivalence or pristine-copy claim
is made. The report contains identities and offset ranges, not target payloads.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

RETAINED_PREFIX = 25207
KNOWN_UPD_SHA256 = "0c8263fe20a3b545ceb65a864c6691591ca7ed1720f517d5b2db35f36c3f23cf"
KNOWN_NATIVE_UPDATED_INSTALL_SHA256 = "3b0cb4994540852e801d768ca51231e97f014881d1e49b9d1cb0c109139fc945"


def ident(data):
    return {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def compare(before, after):
    changes = [i for i in range(max(len(before), len(after)))
               if i >= min(len(before), len(after)) or before[i] != after[i]]
    ranges = []
    for offset in changes:
        if ranges and ranges[-1][1] == offset:
            ranges[-1][1] += 1
        else:
            ranges.append([offset, offset + 1])
    prefix = 0
    while prefix < min(len(before), len(after)) and before[prefix] == after[prefix]:
        prefix += 1
    suffix = 0
    while suffix < min(len(before), len(after)) - prefix and before[-suffix - 1] == after[-suffix - 1]:
        suffix += 1
    return {"before": ident(before), "after": ident(after), "identical": before == after,
            "size_delta": len(after) - len(before), "fixed_offset_differences": len(changes),
            "changed_ranges": ranges, "common_prefix": prefix, "common_suffix_nonoverlapping": suffix}


def inventory(directory):
    files = {}
    for p in directory.iterdir():
        if p.is_file() and p.suffix.lower() not in (".ima", ".dfi"):
            if p.name.upper() in files:
                raise ValueError("ambiguous DOS filename")
            if p.stat().st_size > 2 * 1024 * 1024:
                raise ValueError("research comparison byte budget exceeded")
            files[p.name.upper()] = p.read_bytes()
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pro_root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    profiles = {
        "donor30": args.pro_root / "extracted/donor30",
        "english30": args.pro_root / "extracted/english30",
        "rar_loose30a": args.pro_root / "extracted/english30a",
        "preserved_disk30a": args.pro_root / "disks/ima",
    }
    data = {name: inventory(path) for name, path in profiles.items()}
    report = {"schema": "gamewizard-pro-lineage-comparison-1", "file_sets": {}, "pairs": []}
    for label, members in data.items():
        report["file_sets"][label] = {n: ident(b) for n, b in sorted(members.items())}
    for left, right in [("donor30", "english30"), ("donor30", "rar_loose30a"),
                        ("rar_loose30a", "preserved_disk30a"), ("donor30", "preserved_disk30a")]:
        a, b = data[left], data[right]
        rows = [{"name": name, **compare(a[name], b[name])} for name in sorted(a.keys() & b.keys())]
        result = {"before": left, "after": right,
                  "shared_file_count": len(rows), "identical_files": [r["name"] for r in rows if r["identical"]],
                  "different_files": [r["name"] for r in rows if not r["identical"]],
                  "before_only": sorted(a.keys() - b.keys()), "after_only": sorted(b.keys() - a.keys()),
                  "comparisons": rows}
        report["pairs"].append(result)
        print(json.dumps({k: result[k] for k in ("before", "after", "shared_file_count", "identical_files", "different_files")}), flush=True)
    before = data["donor30"]["INSTALL.PRO"]
    rar = data["rar_loose30a"]["INSTALL.PRO"]
    post = data["preserved_disk30a"]["INSTALL.PRO"]
    rebuilt_upd = rar[RETAINED_PREFIX:] + data["rar_loose30a"]["GW"]
    differences = [i for i, (x, y) in enumerate(zip(rar, post)) if x != y]
    report["update_lineage"] = {
        "retained_prefix": RETAINED_PREFIX,
        "rar_prefix_equals_donor_prefix": rar[:RETAINED_PREFIX] == before[:RETAINED_PREFIX],
        "rar_install_matches_recorded_native_output": ident(rar)["sha256"] == KNOWN_NATIVE_UPDATED_INSTALL_SHA256,
        "rar_suffix_plus_gw": ident(rebuilt_upd),
        "rar_suffix_plus_gw_matches_recorded_official_upd": ident(rebuilt_upd)["sha256"] == KNOWN_UPD_SHA256,
        "rar_gw_equals_preserved_disk_gw": data["rar_loose30a"]["GW"] == data["preserved_disk30a"]["GW"],
        "rar_vs_disk_install_difference_count": len(differences),
        "rar_vs_disk_install_first_difference": min(differences) if differences else None,
        "rar_vs_disk_install_last_difference_exclusive": max(differences) + 1 if differences else None,
        "all_rar_vs_disk_install_mismatches_inherited_from_donor": bool(differences) and all(i < len(before) and rar[i] == before[i] for i in differences),
        "scope": "Supplied loose RAR outputs agree with the prior vendor-update transformation of the repeated donor; origin of individual predecessor modifications not proved"
    }
    if not all(report["update_lineage"][k] for k in (
        "rar_prefix_equals_donor_prefix", "rar_install_matches_recorded_native_output",
        "rar_suffix_plus_gw_matches_recorded_official_upd", "rar_gw_equals_preserved_disk_gw",
        "all_rar_vs_disk_install_mismatches_inherited_from_donor")):
        raise ValueError("Supplied Pro distributions do not reproduce the recorded update lineage")
    cfg = data["preserved_disk30a"].get("GW.CFG")
    report["config_target"] = {
        "source": "preserved_disk30a/GW.CFG", **ident(cfg), "byte_at_0x10": cfg[16],
        "loose_sets_with_cfg": [label for label in ("donor30", "english30", "rar_loose30a") if "GW.CFG" in data[label]],
        "scope": "Original supplied disk file; no assertion about a fresh installed configuration or CPU compatibility"
    }
    with args.output.open("x") as stream:
        stream.write(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
