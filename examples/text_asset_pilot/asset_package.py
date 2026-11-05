"""Experimental deterministic asset container and typed shell linker.

No source-game formats, host addresses, executable plugins, or extraction paths
are part of this format. Consumers read verified members in memory. This is an
additive research profile, not a change to a registered core UIL schema.
"""
from __future__ import annotations
import hashlib
import io
import json
import re
import stat
import zipfile
from pathlib import Path

FORMAT = "fdisbull-component-package-1"
LINK_FORMAT = "fdisbull-component-link-1"
MAX_MEMBER = 128 * 1024 * 1024
MAX_TOTAL = 192 * 1024 * 1024
MAX_MANIFEST = 8 * 1024 * 1024
MAX_MEMBERS = 20000
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class PackageError(ValueError):
    """A structural, integrity, dependency, or interface admission failure."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def parse_json(data):
    def pairs(items):
        obj = {}
        for key, value in items:
            if key in obj:
                raise PackageError("duplicate JSON key: " + key)
            obj[key] = value
        return obj
    def bad(value):
        raise PackageError("non-finite JSON value: " + value)
    try:
        return json.loads(data, object_pairs_hook=pairs, parse_constant=bad)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise PackageError("invalid JSON") from exc


def exact(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise PackageError("invalid fields in " + label)


def identifier(value):
    if (not isinstance(value, str) or not NAME.fullmatch(value)
            or ".." in value or "//" in value):
        raise PackageError("invalid logical identity")
    return value


def digest(value):
    if not isinstance(value, str) or not DIGEST.fullmatch(value):
        raise PackageError("invalid SHA-256")
    return value


def validate_manifest(manifest):
    exact(manifest, ("format", "component", "assets", "metadata"), "manifest")
    if manifest["format"] != FORMAT:
        raise PackageError("unsupported package format")
    if not isinstance(manifest["metadata"], dict):
        raise PackageError("invalid package metadata")
    component = manifest["component"]
    exact(component, ("id", "entry", "requires"), "component")
    identifier(component["id"])
    identifier(component["entry"])
    if not isinstance(component["requires"], dict) or len(component["requires"]) > 64:
        raise PackageError("invalid required ports")
    for port, contract in component["requires"].items():
        identifier(port)
        digest(contract)
    assets = manifest["assets"]
    if not isinstance(assets, dict) or not 1 <= len(assets) <= MAX_MEMBERS - 1:
        raise PackageError("invalid asset count")
    if component["entry"] not in assets:
        raise PackageError("missing component entry")
    total = 0
    for key, item in assets.items():
        identifier(key)
        exact(item, ("kind", "media_type", "sha256", "bytes", "dependencies", "metadata"), "asset")
        identifier(item["kind"])
        if not isinstance(item["media_type"], str) or not 1 <= len(item["media_type"]) <= 128:
            raise PackageError("invalid media type")
        digest(item["sha256"])
        if type(item["bytes"]) is not int or not 0 <= item["bytes"] <= MAX_MEMBER:
            raise PackageError("invalid member size")
        total += item["bytes"]
        if total > MAX_TOTAL:
            raise PackageError("package budget exceeded")
        deps = item["dependencies"]
        if (not isinstance(deps, list) or len(deps) > MAX_MEMBERS
                or any(not isinstance(dep, str) or dep not in assets for dep in deps)
                or len(set(deps)) != len(deps)):
            raise PackageError("invalid or missing asset dependency")
        if not isinstance(item["metadata"], dict):
            raise PackageError("invalid asset metadata")
    # Iterative graph walk avoids Python recursion limits on deep input.
    done, active = set(), set()
    for start in assets:
        todo = [(start, False)]
        while todo:
            node, exiting = todo.pop()
            if exiting:
                active.remove(node)
                done.add(node)
            elif node not in done:
                if node in active:
                    raise PackageError("cyclic asset dependency")
                active.add(node)
                todo.append((node, True))
                todo.extend((dep, False) for dep in reversed(assets[node]["dependencies"]))
    return manifest


def zip_bytes(members, *, prefix=b""):
    """Stable member order, fixed timestamp, no filesystem metadata leakage.

    STORE is intentional: deterministic across zlib versions. A target cooker
    may later compress selected payloads under a separately versioned profile.
    """
    stream = io.BytesIO()
    stream.write(prefix)
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, payload in sorted(members.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, payload)
    return stream.getvalue()


def pack(component, entries, metadata=None):
    """entries maps logical IDs to (kind, media type, bytes, dependencies, metadata)."""
    assets, members = {}, {}
    for key, (kind, media_type, payload, dependencies, annotations) in entries.items():
        if not isinstance(payload, bytes):
            raise PackageError("payload must be immutable bytes")
        h = sha(payload)
        assets[key] = dict(kind=kind, media_type=media_type, sha256=h, bytes=len(payload),
                           dependencies=list(dependencies), metadata=annotations)
        members["blobs/" + h] = payload
    manifest = validate_manifest(dict(format=FORMAT, component=component, assets=assets,
                                      metadata=metadata or {}))
    members["manifest.json"] = canonical(manifest)
    if len(members["manifest.json"]) > MAX_MANIFEST:
        raise PackageError("manifest budget exceeded")
    return zip_bytes(members)


class Package:
    """Verified in-memory package. No archive member is executed or extracted."""
    def __init__(self, data):
        if not isinstance(data, bytes) or len(data) > MAX_TOTAL + 16 * 1024 * 1024:
            raise PackageError("invalid archive size")
        self.digest = sha(data)
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                infos = archive.infolist()
                names = [i.filename for i in infos]
                if len(infos) > MAX_MEMBERS or len(names) != len(set(names)):
                    raise PackageError("too many or duplicate archive members")
                if "manifest.json" not in names:
                    raise PackageError("missing manifest")
                total = 0
                for info in infos:
                    if (info.filename != "manifest.json" and
                            not re.fullmatch(r"blobs/[0-9a-f]{64}", info.filename)):
                        raise PackageError("unexpected or unsafe member name")
                    mode = info.external_attr >> 16
                    if stat.S_IFMT(mode) not in (0, stat.S_IFREG) or info.flag_bits & 1 or info.is_dir():
                        raise PackageError("symlink, encryption, or directory refused")
                    if info.compress_type != zipfile.ZIP_STORED:
                        raise PackageError("unsupported compression in v1 profile")
                    limit = MAX_MANIFEST if info.filename == "manifest.json" else MAX_MEMBER
                    if not 0 <= info.file_size <= limit:
                        raise PackageError("member budget exceeded")
                    total += info.file_size
                    if total > MAX_TOTAL:
                        raise PackageError("archive budget exceeded")
                raw = archive.read("manifest.json")
                self.manifest = validate_manifest(parse_json(raw))
                expected = {"manifest.json"} | {"blobs/" + a["sha256"] for a in self.manifest["assets"].values()}
                if set(names) != expected:
                    raise PackageError("missing or undeclared payload")
                self.blobs = {}
                for item in self.manifest["assets"].values():
                    h = item["sha256"]
                    if h not in self.blobs:
                        self.blobs[h] = archive.read("blobs/" + h)
                    payload = self.blobs[h]
                    if len(payload) != item["bytes"] or sha(payload) != h:
                        raise PackageError("payload digest/size mismatch")
        except (zipfile.BadZipFile, RuntimeError, EOFError) as exc:
            raise PackageError("invalid archive") from exc

    @classmethod
    def read(cls, path):
        with Path(path).open("rb") as stream:
            return cls(stream.read(MAX_TOTAL + 16 * 1024 * 1024 + 1))

    def get(self, key, kind=None):
        item = self.manifest["assets"].get(key)
        if item is None or (kind is not None and item["kind"] != kind):
            raise PackageError("missing or incompatible asset: " + str(key))
        return self.blobs[item["sha256"]]


def link(package, shell, wires):
    """Check every required pin and bind identities before any game execution."""
    exact(shell, ("id", "target", "provides"), "shell")
    identifier(shell["id"])
    identifier(shell["target"])
    if not isinstance(shell["provides"], dict):
        raise PackageError("invalid provider ports")
    for name, contract in shell["provides"].items():
        identifier(name)
        digest(contract)
    required = package.manifest["component"]["requires"]
    if not isinstance(wires, dict) or set(wires) != set(required):
        raise PackageError("connector must bind every required port exactly once")
    for pin, provider in wires.items():
        if not isinstance(provider, str) or shell["provides"].get(provider) != required[pin]:
            raise PackageError("incompatible or missing pin: " + pin)
    body = dict(format=LINK_FORMAT, package_sha256=package.digest,
                component=package.manifest["component"]["id"], shell=shell, wires=wires)
    return {**body, "link_sha256": sha(canonical(body))}


def private_output(path):
    path = Path(path).expanduser().resolve()
    for parent in path.parents:
        if (parent / ".git").exists():
            raise PackageError("game-derived output must remain outside Git")
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
