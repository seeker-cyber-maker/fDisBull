#!/usr/bin/env python3
"""Describe and preview detached scene packets without executing their guest.

Each capture owns one stopped metadata-only QEMU child. Existing packet state
and history remain attributed to their original producer; the new executable
supplies static instruction facts only. No original game resources are read.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import struct
import zlib

from draw_intent_harness import QemuAGIDrawIntent
from harness import HarnessError
from processor_harness import _integer, _same, read_decode_pages
from processor_scene import derive_scene_plan
from scene_harness import _bounded_timeout
from scene_packet_preview import _raw, _read, preview_packet


def packet_source_mappings(packet, code):
    """Check the retained mapping and keep authored bytes out of original PCs."""
    mapping = packet["fragment_mapping"]
    copied = mapping["copied_fragment_span"]
    if type(copied) is not list or len(copied) != 2 \
            or not _integer(copied[0], 0, len(code) - 1) \
            or not _integer(copied[1], copied[0] + 1, len(code) - 1) \
            or mapping.get("authored_load_prologue_span") != [0, copied[0]] \
            or copied[0] != len(_raw(packet["entry"]["load_prologue_bytes"])) \
            or type(mapping.get("authored_return_pc")) is not int \
            or mapping["authored_return_pc"] != copied[1] \
            or copied[1] != len(code) - 1 \
            or mapping.get("authored_original_source_address") is not None \
            or mapping.get("containing_logic_executed") is not False \
            or mapping.get("copied_span_sha256") != sha256(code[copied[0]:copied[1]]).hexdigest():
        raise HarnessError("Detached packet source mapping or copied byte identity differs")
    original = {"logic": packet["logic"]["number"],
                "resource_sha256": packet["logic"]["sha256"],
                "code_span": deepcopy(mapping["source_code_span"]),
                "payload_span": deepcopy(mapping["source_payload_span"])}
    for site in packet["sites"]:
        delta = site["fragment_pc"] - copied[0]
        if type(site.get("code_pc")) is not int or type(site.get("payload_offset")) is not int \
                or site["code_pc"] != original["code_span"][0] + delta \
                or site.get("payload_offset") != original["payload_span"][0] + delta:
            raise HarnessError("Detached source site disagrees with its copied mapping")
    result = []
    if copied[0]:
        result.append({"kind": "authored", "fragment_span": [0, copied[0]], "source": None})
    result.extend(({"kind": "original", "fragment_span": copied, "source": original},
                   {"kind": "authored", "fragment_span": [copied[1], len(code)], "source": None}))
    return result


def packet_inputs(packet_directory):
    """Read exact retained bytes/evidence; selection labels are diagnostic only."""
    directory = Path(packet_directory).expanduser().resolve(strict=True)
    raw = _read(directory, "packet.json", 2 * 1024**2)
    packet = json.loads(raw)
    if type(packet) is not dict or packet.get("schema") != "fdisbull-agi-draw-intent-packet-1":
        raise HarnessError("Unsupported detached native scene packet")
    prelude = _raw(packet["entry"]["load_prologue_bytes"])
    sites = packet["sites"]
    if type(sites) is not list or not 1 <= len(sites) <= 64:
        raise HarnessError("Detached fragment requires 1..64 retained source sites")
    code = bytearray(prelude)
    for site in sites:
        if type(site) is not dict or type(site.get("fragment_pc")) is not int \
                or site["fragment_pc"] != len(code):
            raise HarnessError("Detached source bytes are not contiguous")
        data = _raw(site["bytes"])
        if not data or type(site.get("opcode")) is not int or site["opcode"] != data[0]:
            raise HarnessError("Detached site opcode differs from its retained bytes")
        code.extend(data)
    if _raw(packet["entry"]["authored_return_bytes"]) != b"\x00" or len(code) >= 65536:
        raise HarnessError("Detached authored return or code extent differs")
    code.append(0)
    code = bytes(code)
    catalog = _read(directory, packet["catalog"]["file"], 65536)
    if packet["catalog"].get("sha256") != sha256(catalog).hexdigest():
        raise HarnessError("Detached catalog file identity differs")
    views = packet.get("views")
    if type(views) is dict and all(type(key) is str and key.isdecimal() for key in views):
        views = sorted(int(key) for key in views)
    legacy = {"selected_actors": deepcopy(packet.get("selected_actors")),
              "views": deepcopy(views), "execution_endpoint": deepcopy(packet.get("execution_endpoint"))}
    return {"directory": directory, "packet": packet, "packet_sha256": sha256(raw).hexdigest(),
            "code": code, "catalog": catalog,
            "source_mappings": packet_source_mappings(packet, code), "legacy": legacy,
            "initial": packet["entry"]["initial_snapshot"],
            "state": packet["native"]["snapshot"], "events": packet["native"]["observations"]}


def plan_packet(packet_directory, pages):
    """Derive a portable plan without QEMU or a scene library."""
    inputs = packet_inputs(packet_directory)
    plan = derive_scene_plan(pages=pages, **{key: inputs[key] for key in
        ("code", "catalog", "initial", "state", "events", "source_mappings", "legacy")})
    plan["packet_sha256"] = inputs["packet_sha256"]
    plan["observation_producer"] = {"binary_sha256": inputs["packet"]["native"]["binary_sha256"],
                                    "kind": "existing_detached_native_capture"}
    return plan


def _write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_png(path, visual, palette):
    if type(visual) is not bytes or len(visual) != 160 * 168 \
            or type(palette) is not list or len(palette) != 16 \
            or any(type(color) is not list or len(color) != 3
                   or any(not _integer(value, 0, 255) for value in color) for color in palette) \
            or any(value >= 16 for value in visual):
        raise HarnessError("Preview palette or visual plane is invalid")
    def chunk(name, payload):
        return struct.pack(">I", len(payload)) + name + payload + \
            struct.pack(">I", zlib.crc32(name + payload) & 0xffffffff)
    pixels = b"".join(b"\x00" + b"".join(bytes(palette[index]) for index in visual[y * 160:(y + 1) * 160])
                      for y in range(168))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 160, 168, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))


def capture_packet(binary, packet_directory, output, *, expected_binary_sha256, timeout=5.0,
                   kernel=None, bands=None, actor_policy=None, draw_order=None, max_attempts=4096):
    """Own one metadata-only child, derive the plan, and optionally preview it.

    Preview requires all four explicit inputs: kernel, bands, actor_policy and
    draw_order. The existing packet supplies the explicitly chosen background.
    All outputs use a fresh directory; failures are preserved without retry.
    """
    timeout = _bounded_timeout(timeout)
    if timeout > 5 or type(expected_binary_sha256) is not str or len(expected_binary_sha256) != 64 \
            or any(c not in "0123456789abcdef" for c in expected_binary_sha256):
        raise ValueError("Require a pinned binary identity and timeout at most five seconds")
    if kernel is None and any(value is not None for value in (bands, actor_policy, draw_order)) \
            or kernel is not None and any(value is None for value in (bands, actor_policy, draw_order)):
        raise ValueError("Preview requires explicit kernel, bands, actor policy and draw order")
    output = Path(output).expanduser().absolute()
    output.mkdir(parents=True, exist_ok=False)
    failures = output / "native-failures"
    failures.mkdir()
    report = {"schema": "fdisbull-agi-processor-packet-capture-1", "status": "running",
              "parameters": {"maximum_children": 1, "maximum_runs": 0, "maximum_instructions": 256,
                             "page_limit": 64, "qmp_timeout_seconds": timeout},
              "children": [], "runs": 0}
    stage, vm = "inputs", None
    try:
        inputs = packet_inputs(packet_directory)
        executable = Path(binary).expanduser().resolve(strict=True)
        with executable.open("rb") as stream:
            digest = sha256()
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != expected_binary_sha256:
            raise HarnessError("Explicit metadata binary differs from its pinned identity")
        report["packet_sha256"] = inputs["packet_sha256"]
        stage = "static_native_capture"
        with QemuAGIDrawIntent(executable, inputs["code"], inputs["catalog"],
                              timeout=timeout, evidence_dir=failures) as vm:
            report["children"].append({"pid": vm.process.pid, "binary_sha256": vm.binary_sha256,
                                       "purpose": "static_metadata_only"})
            if vm.binary_sha256 != expected_binary_sha256:
                raise HarnessError("Metadata binary changed before child admission")
            before, events_before = vm.state(), vm.events()
            if not _same(before["source"], inputs["state"]["source"]):
                raise HarnessError("New static producer loaded a different source/profile/catalog")
            pages = read_decode_pages(vm, inputs["code"], max_instructions=256)
            after, events_after = vm.state(), vm.events()
            if not _same(before, after) or not _same(events_before, events_after):
                raise HarnessError("Static capture changed native inputs")
            _write_json(output / "metadata-capture.json", {
                "producer_binary_sha256": vm.binary_sha256, "before": before, "after": after,
                "events_before": events_before, "events_after": events_after,
                "native_inputs_unchanged": True, "runs": 0})
        report["children"][-1]["exit_code"] = vm.process.returncode
        report["children"][-1]["reaped"] = vm.process.poll() is not None
        _write_json(output / "instruction-pages.json", pages)
        stage = "derive_scene_plan"
        plan = plan_packet(packet_directory, pages)
        report["static_producer"] = {"binary_sha256": expected_binary_sha256,
                                     "decoder": plan["decoder"], "kind": "stopped_static_decode"}
        report["observation_producer"] = plan["observation_producer"]
        _write_json(output / "scene-plan.json", plan)
        if kernel is not None:
            stage = "explicit_policy_preview"
            preview = preview_packet(kernel, packet_directory, bands=bands, actor_policy=actor_policy,
                                     max_attempts=max_attempts, scene_plan=plan, draw_order=draw_order)
            for name in ("visual", "priority"):
                (output / (name + ".idx")).write_bytes(preview[name])
            _write_png(output / "scene.png", preview["visual"], inputs["packet"]["render_contract"]["palette_rgb"])
            _write_json(output / "preview.json", {key: value for key, value in preview.items()
                                                   if key not in ("visual", "priority")})
            report["preview"] = {"status": preview["status"], "file": "preview.json", "image": "scene.png",
                                 "library_sha256": kernel.binary_sha256, "draw_order": list(draw_order)}
        if packet_inputs(packet_directory)["packet_sha256"] != inputs["packet_sha256"]:
            raise HarnessError("Detached packet changed during static capture")
        report.update(status="completed", native_inputs_unchanged=True, packet_unchanged=True,
                      actor_ids=plan["actor_ids"], current_view_ids=plan["current_view_ids"],
                      endpoint=plan["endpoint"], legacy_contradictions=plan["legacy_contradictions"],
                      instruction_pages="instruction-pages.json", scene_plan="scene-plan.json")
    except BaseException as error:
        if vm is not None and report["children"]:
            report["children"][-1].update(exit_code=vm.process.poll(), reaped=vm.process.poll() is not None)
        report.update(status="failed", stage=stage, error={"type": type(error).__name__, "message": str(error)})
        _write_json(output / "report.json", report)
        raise
    _write_json(output / "report.json", report)
    return report


def capture_packets(binary, requests, output, *, expected_binary_sha256, kernel=None,
                    timeout=5.0, max_attempts=4096):
    """Run one finite process batch, sharing a scene library across 1..2 packets.

    Each request has id, packet_directory, bands, actor_policy and draw_order.
    Policies are explicit per packet; kernel is loaded by the caller once.
    No capture is retried, and an earlier successful result survives a failure.
    """
    fields = {"id", "packet_directory", "bands", "actor_policy", "draw_order"}
    if type(requests) is not list or not 1 <= len(requests) <= 2 \
            or any(type(request) is not dict or set(request) != fields for request in requests):
        raise ValueError("Require one or two explicit packet/policy requests")
    ids = [request["id"] for request in requests]
    if any(type(name) is not str or not 1 <= len(name) <= 64
           or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for c in name) for name in ids) \
            or len(set(ids)) != len(ids):
        raise ValueError("Packet request IDs must be unique safe directory names")
    output = Path(output).expanduser().absolute()
    output.mkdir(parents=True, exist_ok=False)
    report = {"schema": "fdisbull-agi-processor-packet-batch-1", "status": "running", "packets": []}
    try:
        for request in requests:
            result = capture_packet(binary, request["packet_directory"], output / request["id"],
                expected_binary_sha256=expected_binary_sha256, timeout=timeout, kernel=kernel,
                bands=request["bands"], actor_policy=request["actor_policy"],
                draw_order=request["draw_order"], max_attempts=max_attempts)
            report["packets"].append({"id": request["id"], "report": request["id"] + "/report.json",
                                      "children": result["children"], "runs": result["runs"],
                                      "status": result["status"]})
        report.update(status="completed", children=sum(len(row["children"]) for row in report["packets"]),
                      runs=sum(row["runs"] for row in report["packets"]))
    except BaseException as error:
        failed = output / request["id"] / "report.json"
        if failed.is_file():
            result = json.loads(failed.read_text(encoding="utf-8"))
            report["packets"].append({"id": request["id"], "report": request["id"] + "/report.json",
                                      "children": result["children"], "runs": result["runs"],
                                      "status": result["status"]})
        report.update(status="failed", failed_packet=request["id"],
                      children=sum(len(row["children"]) for row in report["packets"]),
                      runs=sum(row["runs"] for row in report["packets"]),
                      error={"type": type(error).__name__, "message": str(error)})
        _write_json(output / "report.json", report)
        raise
    _write_json(output / "report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("binary", "expected-binary-sha256", "output"):
        parser.add_argument("--" + name, required=True)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--packet")
    selection.add_argument("--batch", help="JSON array of one or two explicit packet/policy requests")
    parser.add_argument("--policy", help="Explicit JSON bands, actor_policy and draw_order for preview")
    parser.add_argument("--scene-library")
    parser.add_argument("--expected-library-sha256")
    args = parser.parse_args()
    if args.batch:
        if args.policy or not args.scene_library or not args.expected_library_sha256:
            parser.error("Batch preview uses per-request policy and one explicit scene library")
        from sarien_scene import SarienScene
        batch_path = Path(args.batch)
        if batch_path.stat().st_size > 131072:
            parser.error("Packet batch exceeds 128 KiB")
        requests = json.loads(batch_path.read_text(encoding="utf-8"))
        if type(requests) is not list or not 1 <= len(requests) <= 2:
            parser.error("Batch requires one or two requests")
        for request in requests:
            request["bands"] = bytes(request["bands"])
            request["actor_policy"] = {int(key): value for key, value in request["actor_policy"].items()}
        kernel = SarienScene(args.scene_library, expected_sha256=args.expected_library_sha256)
        report = capture_packets(args.binary, requests, args.output,
            expected_binary_sha256=args.expected_binary_sha256, kernel=kernel)
        print(json.dumps({"status": report["status"], "children": report["children"], "runs": report["runs"]}))
        return
    preview = {}
    if any((args.policy, args.scene_library, args.expected_library_sha256)):
        if not all((args.policy, args.scene_library, args.expected_library_sha256)):
            parser.error("Preview requires policy, scene-library and expected-library-sha256")
        from sarien_scene import SarienScene
        policy_path = Path(args.policy)
        if policy_path.stat().st_size > 65536:
            parser.error("Scene policy exceeds 64 KiB")
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        preview = {"kernel": SarienScene(args.scene_library, expected_sha256=args.expected_library_sha256),
                   "bands": bytes(policy["bands"]),
                   "actor_policy": {int(key): value for key, value in policy["actor_policy"].items()},
                   "draw_order": policy["draw_order"]}
    report = capture_packet(args.binary, args.packet, args.output,
                            expected_binary_sha256=args.expected_binary_sha256, **preview)
    print(json.dumps({"status": report["status"], "scene_plan": report["scene_plan"],
                      "children": len(report["children"]), "runs": report["runs"]}))


if __name__ == "__main__":
    main()
