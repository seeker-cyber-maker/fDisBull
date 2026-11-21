"""Capture full-LOGIC static scene candidates in one owned stopped CPU.

The caller supplies exact private resource bytes and an explicitly pinned
native binary. There are no game-directory searches, scene-library loads,
guest resumes, observation replays, native draws, or automatic retries here.
Each call owns one child and writes one fresh private evidence directory.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path

from harness import HarnessError, QemuAGI, _sha256_file
from processor_discovery import (derive_scene_candidates, logic_input,
                                 read_reachable_decode_pages, _graph_limits, _roots)
from processor_harness import MAX_PAGE_JSON_BYTES, _integer, _same


SCHEMA = "fdisbull-agi-native-discovery-capture-1"


def _write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def capture_logic(binary, payload, logic, output, *, expected_binary_sha256,
        timeout=5.0, roots=(0,), max_native_rows=4096, max_reached_nodes=4096,
        max_pages=128, max_edges=8192, page_limit=64, deadline_seconds=30.0,
        max_native_json_bytes=32 * 1024**2):
    """Read one exact full resource with one metadata child and zero runs.

    ``payload`` includes the LOGIC resource's two-byte code-length header and
    any following message section. Only its exact declared code is loaded into
    the CPU. The original resource hash/LOGIC number remain a separate source
    mapping; native ``source.logic_id`` remains zero for the raw input.

    ``deadline_seconds`` bounds recursive acquisition. The caller's outer
    owned-child gate bounds launch, final neutrality reads and teardown as well.
    Earlier native packets from copied fragments are not inputs or observations
    of this full-source capture.
    """
    inputs = logic_input(payload, logic)
    code = inputs["code"]
    roots = _roots(code, roots)
    _graph_limits(max_reached_nodes, max_edges)
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 5 \
            or type(deadline_seconds) not in (int, float) \
            or not math.isfinite(deadline_seconds) or not 0 < deadline_seconds <= 30 \
            or not _integer(max_native_rows, 1, 4096) or not _integer(max_pages, 1, 128) \
            or not _integer(page_limit, 1, 64) \
            or not _integer(max_native_json_bytes, 1, 32 * 1024**2) \
            or type(expected_binary_sha256) is not str or len(expected_binary_sha256) != 64 \
            or any(c not in "0123456789abcdef" for c in expected_binary_sha256):
        raise ValueError("Require explicit finite discovery limits and an exact native binary SHA-256")
    output = Path(output).expanduser().absolute()
    output.mkdir(parents=True, exist_ok=False)
    failures, retained = output / "native-failures", output / "inputs"
    failures.mkdir()
    retained.mkdir()
    (retained / "raw-code.bin").write_bytes(code)
    _write_json(retained / "source-mapping.json", {
        "resource_mapping": inputs["resource_mapping"], "source_mappings": inputs["source_mappings"]})
    report = {"schema": SCHEMA, "status": "running", "resource_mapping": inputs["resource_mapping"],
              "parameters": {"maximum_children": 1, "maximum_runs": 0,
                  "roots": list(roots), "max_native_rows": max_native_rows,
                  "max_reached_nodes": max_reached_nodes, "max_pages": max_pages,
                  "max_edges": max_edges, "page_limit": page_limit,
                  "max_page_json_bytes": MAX_PAGE_JSON_BYTES,
                  "max_native_json_bytes": max_native_json_bytes,
                  "qmp_timeout_seconds": timeout, "acquisition_deadline_seconds": deadline_seconds},
              "children": [], "runs": 0}
    stage, vm = "binary_identity", None
    try:
        executable = Path(binary).expanduser().resolve(strict=True)
        if _sha256_file(executable) != expected_binary_sha256:
            raise HarnessError("Explicit discovery binary differs from its pinned identity")
        stage = "stopped_native_capture"
        with QemuAGI(executable, code, timeout=timeout, evidence_dir=failures) as vm:
            report["children"].append({"pid": vm.process.pid, "binary_sha256": vm.binary_sha256,
                                       "purpose": "full_logic_static_metadata_only"})
            if vm.binary_sha256 != expected_binary_sha256:
                raise HarnessError("Native discovery binary changed before child admission")
            capture = read_reachable_decode_pages(vm, code, roots=roots,
                max_native_rows=max_native_rows, max_reached_nodes=max_reached_nodes,
                max_pages=max_pages, max_edges=max_edges, page_limit=page_limit,
                deadline_seconds=deadline_seconds, max_native_json_bytes=max_native_json_bytes)
            if capture["source"].get("logic_id") != 0 \
                    or not _same(capture["source"], capture["before"]["source"]) \
                    or capture["source"]["sha256"] != inputs["resource_mapping"]["code_sha256"]:
                raise HarnessError("Full LOGIC capture has inconsistent raw native source identity")
            _write_json(output / "metadata-capture.json", {
                **{key: deepcopy(value) for key, value in capture.items() if key != "pages"},
                "producer_binary_sha256": vm.binary_sha256,
                "resource_mapping": inputs["resource_mapping"]})
            _write_json(output / "instruction-pages.json", capture["pages"])
        report["children"][-1].update(exit_code=vm.process.returncode,
                                       reaped=vm.process.poll() is not None)
        if not capture["pages"]:
            # A deliberately tiny acquisition budget may admit no page. Retain
            # that explicit native frontier without fabricating decoder rows or
            # an alleged successfully reconstructed candidate graph.
            report.update(status="partial", stage="native_acquisition_budget",
                          native_inputs_unchanged=True, acquisition={
                              key: deepcopy(capture[key]) for key in
                              ("frontier", "pending_pcs", "coverage", "usage", "budgets")},
                          instruction_pages="instruction-pages.json", scene_candidates=None)
            _write_json(output / "report.json", report)
            return report
        stage = "derive_scene_candidates"
        candidates = derive_scene_candidates(code=code, pages=capture["pages"], roots=roots,
            source_mappings=inputs["source_mappings"], resource_mapping=inputs["resource_mapping"],
            max_reached_nodes=max_reached_nodes, max_edges=max_edges)
        candidates["producer"] = {"binary_sha256": expected_binary_sha256,
                                   "kind": "stopped_static_decode", "runs": 0}
        candidates["acquisition"] = {key: deepcopy(capture[key]) for key in
                                      ("frontier", "pending_pcs", "coverage", "usage", "budgets")}
        _write_json(output / "scene-candidates.json", candidates)
        complete = candidates["coverage"]["local_decode_complete"] \
            and capture["coverage"]["local_decode_complete"] \
            and candidates["coverage"]["reference_inventory_complete"]
        report.update(status="completed" if complete else "partial", native_inputs_unchanged=True,
            source=deepcopy(capture["source"]), decoder=deepcopy(candidates["decoder"]),
            producer=deepcopy(candidates["producer"]), coverage=deepcopy(candidates["coverage"]),
            acquisition=deepcopy(candidates["acquisition"]), usage=deepcopy(candidates["usage"]),
            candidate_sha256=sha256((output / "scene-candidates.json").read_bytes()).hexdigest(),
            instruction_pages="instruction-pages.json", scene_candidates="scene-candidates.json",
            runtime_observed=False, native_draw_completed=False, presentation_established=False)
    except BaseException as error:
        if vm is not None and report["children"]:
            report["children"][-1].update(exit_code=vm.process.poll(), reaped=vm.process.poll() is not None)
        report.update(status="failed", stage=stage,
                      error={"type": type(error).__name__, "message": str(error)})
        _write_json(output / "report.json", report)
        raise
    _write_json(output / "report.json", report)
    return report
