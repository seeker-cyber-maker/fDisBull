#!/usr/bin/env python3
"""Verify the installed investigation-skill index and its selective Markdown resources."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import posixpath
import queue
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import unquote, urlsplit


FORMAT = "fdisbull-skill-index-1"
SKILL_NAME = "fdisbull-investigate"
ENTRYPOINT = "SKILL.md"
MAX_INDEX_GUIDES = 32
MAX_RESOURCE_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 64 * 1024
MAX_TOTAL_RESPONSE_BYTES = 4 * 1024 * 1024
CHUNK_BYTES = 8192
LINK_RE = re.compile(r"(?<!!)\[[^\]\n]+\]\(\s*(?:<([^>\n]+)>|([^\s)]+))(?:[^)]*)\)")
FRONTMATTER_KEY_RE = re.compile(r"([A-Za-z][A-Za-z0-9_-]*):\s*(.*?)\s*")
SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


class GateError(ValueError):
    """A concise, user-safe validation or bounded-subprocess failure."""


def _safe_reference(value: object, *, label: str = "reference") -> str:
    if not isinstance(value, str) or not value or len(value) > 240:
        raise GateError(f"{label} must be a short relative Markdown path")
    if "\\" in value or "\x00" in value or ":" in value:
        raise GateError(f"{label} contains an unsafe path character")
    path = PurePosixPath(value)
    if (path.is_absolute() or path.as_posix() != value
            or any(part in ("", ".", "..") for part in value.split("/"))):
        raise GateError(f"{label} is not a normalized relative path")
    if value != ENTRYPOINT and not value.startswith("references/"):
        raise GateError(f"{label} is outside the skill reference directory")
    if path.suffix.lower() != ".md":
        raise GateError(f"{label} must name a Markdown file")
    return value


def _frontmatter(text: str, expected_name: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise GateError("entrypoint is missing YAML front matter")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration as exc:
        raise GateError("entrypoint front matter is not closed") from exc

    metadata: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = FRONTMATTER_KEY_RE.fullmatch(line)
        if not match:
            raise GateError("entrypoint front matter must use simple key/value fields")
        key, value = match.groups()
        if key in metadata:
            raise GateError(f"duplicate front matter field: {key}")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] == '"':
            try:
                value = json.loads(value)
            except json.JSONDecodeError as exc:
                raise GateError(f"invalid quoted front matter value: {key}") from exc
        elif len(value) >= 2 and value[0] == value[-1] == "'":
            value = value[1:-1].replace("''", "'")
        metadata[key] = value

    if set(metadata) != {"name", "description"}:
        raise GateError("entrypoint front matter must define only name and description")
    if not SLUG_RE.fullmatch(metadata["name"]) or metadata["name"] != expected_name:
        raise GateError("front matter name does not match the skill index")
    description = metadata["description"].strip()
    if (not description or description.casefold() in {"null", "none", "~"}
            or len(description) > 1024 or "\n" in description):
        raise GateError("front matter description must be a non-empty one-line value")
    return metadata


def _without_fenced_code(text: str) -> str:
    kept: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        stripped = line.lstrip()
        if fence is None:
            match = re.match(r"(`{3,}|~{3,})", stripped)
            if match:
                fence = match.group(1)[0]
                continue
            kept.append(line)
        elif stripped.startswith(fence * 3):
            fence = None
    return "\n".join(kept)


def _local_markdown_targets(source: str, text: str) -> list[str]:
    targets: list[str] = []
    visible = re.sub(r"(?<!`)`(?!`)[^`\n]*`(?!`)", "", _without_fenced_code(text))
    for match in LINK_RE.finditer(visible):
        destination = (match.group(1) or match.group(2) or "").strip()
        if not destination or destination.startswith("#"):
            continue
        if re.match(r"^[A-Za-z]:", destination):
            raise GateError(f"unsafe local Markdown link in {source}")
        split = urlsplit(destination)
        if split.scheme or destination.startswith("//"):
            continue
        decoded = unquote(split.path)
        if not decoded or PurePosixPath(decoded).suffix.lower() != ".md":
            continue
        if decoded.startswith("/") or "\\" in decoded or "\x00" in decoded or ":" in decoded:
            raise GateError(f"unsafe local Markdown link in {source}")
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(source), decoded))
        if resolved in ("", ".", "..") or resolved.startswith("../") or resolved.startswith("/"):
            raise GateError(f"local Markdown link escapes the skill directory in {source}")
        target = _safe_reference(resolved, label=f"link target in {source}")
        targets.append(target)
    return targets


def verify_index(index: object, read_resource) -> dict:
    """Validate an index and each selectively fetched file without matching prose."""
    if not isinstance(index, dict) or set(index) != {"name", "format", "entrypoint", "guides"}:
        raise GateError("skill index has an invalid envelope")
    name = index["name"]
    if not isinstance(name, str) or not SLUG_RE.fullmatch(name):
        raise GateError("skill index name is invalid")
    if name != SKILL_NAME:
        raise GateError(f"skill index name must be {SKILL_NAME}")
    if index["format"] != FORMAT:
        raise GateError("skill index format is unsupported")
    entrypoint = _safe_reference(index["entrypoint"], label="entrypoint")
    if entrypoint != ENTRYPOINT:
        raise GateError(f"required entrypoint must be {ENTRYPOINT}")
    guides = index["guides"]
    if not isinstance(guides, list) or not 1 <= len(guides) <= MAX_INDEX_GUIDES:
        raise GateError("skill index guide list is missing or exceeds its limit")

    purposes: dict[str, str] = {}
    for guide in guides:
        if not isinstance(guide, dict) or set(guide) != {"reference", "purpose"}:
            raise GateError("skill guide metadata must contain reference and purpose")
        reference = _safe_reference(guide["reference"])
        purpose = guide["purpose"]
        if (not isinstance(purpose, str) or not purpose.strip() or len(purpose) > 2048
                or "\n" in purpose or "\r" in purpose):
            raise GateError(f"guide purpose is missing or invalid: {reference}")
        if reference in purposes:
            raise GateError(f"duplicate indexed reference: {reference}")
        purposes[reference] = purpose.strip()
    if entrypoint not in purposes:
        raise GateError("skill index does not list its required entrypoint")

    documents: dict[str, str] = {}
    for reference in purposes:
        try:
            text = read_resource(reference)
        except Exception as exc:
            raise GateError(f"selective read failed for indexed reference: {reference}") from exc
        if not isinstance(text, str):
            raise GateError(f"selective read did not return text for: {reference}")
        try:
            encoded = text.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise GateError(f"selective read contains invalid Unicode: {reference}") from exc
        if len(encoded) > MAX_RESOURCE_BYTES:
            raise GateError(f"skill resource exceeds {MAX_RESOURCE_BYTES} bytes: {reference}")
        documents[reference] = text

    _frontmatter(documents[entrypoint], name)
    link_count = 0
    per_file: list[dict] = []
    references = set(purposes)
    for reference, text in documents.items():
        targets = _local_markdown_targets(reference, text)
        if len(targets) != len(set(targets)):
            raise GateError(f"duplicate local Markdown link in {reference}")
        for target in targets:
            if target not in references:
                raise GateError(f"local Markdown link is missing from the skill index: {reference} -> {target}")
        link_count += len(targets)
        per_file.append({
            "reference": reference,
            "purpose": purposes[reference],
            "bytes": len(text.encode("utf-8")),
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "local_markdown_links": targets,
        })
    return {
        "skill_name": name,
        "index_format": FORMAT,
        "entrypoint": entrypoint,
        "reference_count": len(purposes),
        "local_markdown_link_count": link_count,
        "files": per_file,
    }


def _kill_process_tree(process: subprocess.Popen) -> None:
    if process.poll() is None:
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=1)


def run_bounded(command: list[str], *, timeout: float, output_limit: int,
                env: dict[str, str] | None = None) -> tuple[bytes, int]:
    """Run one process with a wall deadline and bounded in-memory stdout/stderr."""
    if (not command or not isinstance(timeout, (int, float)) or isinstance(timeout, bool)
            or not math.isfinite(timeout) or timeout <= 0
            or type(output_limit) is not int or output_limit <= 0):
        raise GateError("invalid bounded subprocess parameters")
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=False,
            bufsize=0,
            env=env,
            start_new_session=(os.name == "posix"),
            cwd=tempfile.gettempdir(),
        )
    except OSError as exc:
        raise GateError(f"could not start bounded command ({type(exc).__name__})") from exc

    chunks: queue.Queue[bytes | None] = queue.Queue(maxsize=8)
    assert process.stdout is not None

    def pump() -> None:
        try:
            while True:
                chunk = os.read(process.stdout.fileno(), CHUNK_BYTES)
                if not chunk:
                    chunks.put(None)
                    return
                chunks.put(chunk)
        except (OSError, ValueError):
            try:
                chunks.put(None)
            except Exception:
                pass

    reader = threading.Thread(target=pump, name="agent-skill-gate-output", daemon=True)
    reader.start()
    deadline = time.monotonic() + timeout
    output = bytearray()
    failure: str | None = None
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                failure = f"bounded command timed out after {timeout:g}s"
                break
            try:
                chunk = chunks.get(timeout=min(0.1, remaining))
            except queue.Empty:
                if process.poll() is not None and not reader.is_alive():
                    break
                continue
            if chunk is None:
                break
            if len(output) + len(chunk) > output_limit:
                failure = f"bounded command exceeded the {output_limit}-byte output limit"
                break
            output.extend(chunk)
        if failure:
            _kill_process_tree(process)
            raise GateError(failure)
        remaining = deadline - time.monotonic()
        try:
            return_code = process.wait(timeout=max(0.001, remaining))
        except subprocess.TimeoutExpired as exc:
            _kill_process_tree(process)
            raise GateError(f"bounded command timed out after {timeout:g}s") from exc
        if return_code != 0:
            raise GateError(f"bounded command exited with status {return_code}")
        return bytes(output), return_code
    finally:
        if process.poll() is None:
            _kill_process_tree(process)
        if process.stdout:
            process.stdout.close()
        # Drain the bounded queue so a reader blocked while reporting EOF can exit.
        until = time.monotonic() + 1
        while reader.is_alive() and time.monotonic() < until:
            try:
                chunks.get(timeout=0.05)
            except queue.Empty:
                pass
            reader.join(timeout=0.05)


def _load_cli_json(raw: bytes, label: str) -> dict:
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as exc:
        raise GateError(f"installed CLI returned invalid JSON for {label}") from exc
    if not isinstance(value, dict) or value.get("ok") is not True or not isinstance(value.get("result"), dict):
        raise GateError(f"installed CLI rejected {label}")
    return value["result"]


def check_installed(python: str, *, command_timeout: float = 5.0,
                    total_timeout: float = 30.0) -> dict:
    if not 0 < command_timeout <= 30 or not 0 < total_timeout <= 120:
        raise GateError("timeouts must be positive and within the supported bounds")
    checkout = Path(__file__).resolve().parents[1]
    executable = shutil.which(python) or str(Path(python).expanduser().resolve())
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith("PYTHON")}
    environment['FDISBULL_MAX_OUTPUT_BYTES'] = str(MAX_RESPONSE_BYTES)
    deadline = time.monotonic() + total_timeout
    total_output = 0

    def invoke(args: list[str], label: str) -> dict:
        nonlocal total_output
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise GateError(f"skill gate exceeded its {total_timeout:g}s total deadline")
        raw, _ = run_bounded([executable, "-I", "-m", "fdisbull", *args],
                             timeout=min(command_timeout, remaining),
                             output_limit=MAX_RESPONSE_BYTES, env=environment)
        total_output += len(raw)
        if total_output > MAX_TOTAL_RESPONSE_BYTES:
            raise GateError(f"skill gate exceeded its {MAX_TOTAL_RESPONSE_BYTES}-byte total response budget")
        return _load_cli_json(raw, label)

    identity_script = (
        "import fdisbull,importlib.util,json,platform,sys; "
        "print(json.dumps({'package_version':fdisbull.__version__,'python_version':platform.python_version(),'module':importlib.util.find_spec('fdisbull').origin,'python':sys.executable}))"
    )
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise GateError(f"skill gate exceeded its {total_timeout:g}s total deadline")
    raw_identity, _ = run_bounded([executable, "-I", "-c", identity_script],
                                  timeout=min(command_timeout, remaining), output_limit=16 * 1024,
                                  env=environment)
    total_output += len(raw_identity)
    try:
        identity = json.loads(raw_identity)
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as exc:
        raise GateError("installed interpreter identity probe returned invalid JSON") from exc
    if (not isinstance(identity, dict)
            or not all(isinstance(identity.get(key), str) and identity[key]
                       for key in ("package_version", "python_version", "module", "python"))):
        raise GateError("installed interpreter identity probe returned incomplete metadata")
    module_path = Path(identity["module"]).resolve()
    if module_path.is_relative_to(checkout):
        raise GateError("interpreter imported fDisBull from the checkout instead of an installed package")

    index = invoke(["agent-skill", "--index"], "skill index")
    if not isinstance(index, dict):
        raise GateError("installed CLI skill index is not an object")

    def read_resource(reference: str) -> str:
        result = invoke(["agent-skill", "--reference", reference], f"reference {reference}")
        if result.get("name") != index.get("name") or not isinstance(result.get("files"), dict):
            raise GateError(f"selective read returned an invalid envelope: {reference}")
        files = result["files"]
        if set(files) != {reference} or not isinstance(files[reference], str):
            raise GateError(f"selective read did not return exactly the requested file: {reference}")
        return files[reference]

    result = verify_index(index, read_resource)
    result.update({
        "status": "passed",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "package_version": identity["package_version"],
        "python": {"requested": python, "executable": str(Path(identity["python"]).resolve()),
                   "version": identity["python_version"], "module_path": str(module_path), "isolated_mode": True},
        "bounded_commands": {"command_timeout_seconds": command_timeout,
                             "total_timeout_seconds": total_timeout,
                             "response_limit_bytes": MAX_RESPONSE_BYTES,
                             "total_response_limit_bytes": MAX_TOTAL_RESPONSE_BYTES,
                             "captured_response_bytes": total_output},
    })
    return result


def _write_receipt(path: Path, receipt: dict) -> None:
    resolved = path.expanduser().resolve()
    checkout = Path(__file__).resolve().parents[1]
    if resolved.is_relative_to(checkout):
        raise GateError("receipt output must be outside the repository checkout")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(receipt, indent=2, ensure_ascii=True) + "\n"
    try:
        fd = os.open(resolved, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise GateError("receipt output already exists; choose a new private path") from exc
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable,
                        help="installed Python interpreter used for isolated fdisbull CLI queries")
    parser.add_argument("--output", required=True, type=Path,
                        help="new private receipt path outside the repository checkout")
    parser.add_argument("--command-timeout", type=float, default=5.0,
                        help="maximum seconds for each installed CLI subprocess")
    parser.add_argument("--total-timeout", type=float, default=30.0,
                        help="maximum seconds for the full gate")
    args = parser.parse_args(argv)
    try:
        receipt = check_installed(args.python, command_timeout=args.command_timeout,
                                  total_timeout=args.total_timeout)
        _write_receipt(args.output, receipt)
    except (GateError, OSError, ValueError) as exc:
        print(f"agent skill gate failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"status": receipt["status"], "skill_name": receipt["skill_name"],
                      "reference_count": receipt["reference_count"],
                      "local_markdown_link_count": receipt["local_markdown_link_count"],
                      "receipt": str(args.output.expanduser().resolve())}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
