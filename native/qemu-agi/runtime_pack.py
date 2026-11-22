"""Bound explicit, private AGI resources to the native runtime package contract.

This module frames resources and literal message tables, never AGI opcodes.
VIEW, PICTURE and SOUND payloads remain opaque; native resource readers report
their format errors when used. No game directory is discovered implicitly.

build_package accepts code/data as bytes in otherwise JSON-shaped records.
package_from_raw accepts complete version-2 LOGIC payloads as id/data records.
package_from_v2 accepts an explicit directory or an existing V2Resources
snapshot. A malformed container or message table fails the complete build with
per-resource diagnostics; it is never silently omitted.

Run with --game-dir PATH --output PATH to create a private package. Packages
contain original resource bytes and must remain outside source/review uploads.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re


SCHEMA = "fdisbull-agi-runtime-package-1"
PROFILE = "agi-2917-runtime-1"
MAX_PACKAGE_BYTES = 64 * 1024**2
MAX_RESOURCE_BYTES = 2 * 1024**2
MAX_CODE_BYTES = 65536
MAX_MESSAGE_BYTES = 4095
MAX_OBJECT_NAME_BYTES = 255
MAX_WORDS = 10000
_FIELDS = {"schema", "profile", "entry_logic", "logics", "views",
           "pictures", "sounds", "words", "objects"}


class PackageError(ValueError):
    """An explicit package or resource does not satisfy the native contract."""


class ResourcePackageError(PackageError):
    """A build failed; failures identifies every observed malformed resource."""

    def __init__(self, failures):
        self.failures = deepcopy(failures)
        summary = "; ".join(
            f"{item['kind']}"
            + (f"[{item['id']}]" if "id" in item else "")
            + f": {item['error']}" for item in failures)
        super().__init__("Cannot build runtime package: " + summary)


def _uint(value, maximum, label):
    if type(value) is not int or not 0 <= value <= maximum:
        raise PackageError(f"{label} must be an integer in 0..{maximum}")
    return value


def _fields(value, expected, label):
    if type(value) is not dict or set(value) != expected:
        raise PackageError(f"{label} requires exactly {', '.join(sorted(expected))}")


def _array(value, maximum, label):
    if type(value) is not list or len(value) > maximum:
        raise PackageError(f"{label} must be an array of at most {maximum} entries")


def _text(value, label, maximum=None):
    if type(value) is not str or "\0" in value:
        raise PackageError(f"{label} must be literal non-NUL text")
    limit = MAX_PACKAGE_BYTES if maximum is None else maximum
    if len(value) > limit:
        raise PackageError(f"{label} exceeds its {limit}-byte native CP437 limit")
    try:
        encoded = value.encode("cp437")
    except UnicodeEncodeError as error:
        raise PackageError(f"{label} is not representable as native CP437 text") from error
    if len(encoded) > limit:
        raise PackageError(f"{label} exceeds its {limit}-byte native CP437 limit")
    # The byte budget of the package itself is still its UTF-8 JSON transport.
    return len(value.encode("utf-8"))


def _blob(record, field, maximum, label):
    value = record[field]
    if type(value) is not str or not 2 <= len(value) <= maximum * 2 \
            or len(value) % 2 or re.fullmatch("[0-9a-f]+", value) is None:
        raise PackageError(f"{label}.{field} requires 1..{maximum} bytes of lowercase hex")
    digest = record["sha256"]
    if type(digest) is not str or re.fullmatch("[0-9a-f]{64}", digest) is None \
            or sha256(bytes.fromhex(value)).hexdigest() != digest:
        raise PackageError(f"{label}.sha256 differs from its exact {field} bytes")
    return len(value)


def _logic(record, label):
    _fields(record, {"id", "code", "sha256", "messages"}, label)
    _uint(record["id"], 255, label + ".id")
    size = _blob(record, "code", MAX_CODE_BYTES, label)
    _array(record["messages"], 255, label + ".messages")
    for index, message in enumerate(record["messages"], 1):
        if message is not None:
            size += _text(message, f"{label}.messages[{index}]", MAX_MESSAGE_BYTES)
    return size


def validate_package(package):
    """Return an independent validated copy, without normalizing any values.

    All arrays are mandatory. Word text is unique; word IDs may repeat for
    synonyms. Object identity is its array index, so object names may repeat.
    Unknown fields, including an implicit initial state, are rejected.
    Message/object names are Unicode representations of native CP437 bytes;
    messages are bounded to 4095 native bytes and object names to 255 native
    bytes, without substituting glyphs.
    """
    _fields(package, _FIELDS, "package")
    if package["schema"] != SCHEMA or package["profile"] != PROFILE:
        raise PackageError("Unsupported runtime package schema or explicit profile")
    _uint(package["entry_logic"], 255, "entry_logic")
    size = 0
    logic_ids = set()
    for kind in ("logics", "views", "pictures", "sounds"):
        rows = package[kind]
        _array(rows, 256, kind)
        seen = set()
        for index, record in enumerate(rows):
            label = f"{kind}[{index}]"
            if kind == "logics":
                size += _logic(record, label)
            else:
                _fields(record, {"id", "data", "sha256"}, label)
                _uint(record["id"], 255, label + ".id")
                size += _blob(record, "data", MAX_RESOURCE_BYTES, label)
            if record["id"] in seen:
                raise PackageError(f"duplicate {kind} id {record['id']}")
            seen.add(record["id"])
            if size > MAX_PACKAGE_BYTES:
                raise PackageError("runtime package exceeds its byte limit")
        if kind == "logics":
            logic_ids = seen
    if package["entry_logic"] not in logic_ids:
        raise PackageError("entry_logic must exist in logics")
    _array(package["words"], MAX_WORDS, "words")
    words = set()
    for index, word in enumerate(package["words"]):
        label = f"words[{index}]"
        _fields(word, {"text", "id"}, label)
        value = word["text"]
        if type(value) is not str or not 1 <= len(value) <= 63 \
                or any(not 32 <= ord(char) <= 126 for char in value) \
                or value != value.lower():
            raise PackageError(f"{label}.text must be 1..63 lowercase printable ASCII characters")
        _uint(word["id"], 65535, label + ".id")
        if value in words:
            raise PackageError(f"duplicate word text {value!r}")
        words.add(value)
        size += len(value)
    _array(package["objects"], 256, "objects")
    for index, item in enumerate(package["objects"]):
        label = f"objects[{index}]"
        _fields(item, {"name", "room"}, label)
        size += _text(item["name"], label + ".name", MAX_OBJECT_NAME_BYTES)
        _uint(item["room"], 255, label + ".room")
    if size > MAX_PACKAGE_BYTES:
        raise PackageError("runtime package exceeds its byte limit")
    return deepcopy(package)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PackageError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _constant(value):
    raise PackageError(f"Non-JSON numeric constant {value}")


def load_package(data):
    """Validate exact JSON bytes; their SHA-256, including whitespace, is identity."""
    if type(data) is not bytes or not 1 <= len(data) <= MAX_PACKAGE_BYTES:
        raise PackageError(f"runtime package must contain 1..{MAX_PACKAGE_BYTES} JSON bytes")
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object,
                           parse_constant=_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise PackageError("Invalid UTF-8 runtime package JSON") from error
    return validate_package(value)


def dump_package(package):
    """Encode a validated package deterministically; do not re-encode loaded identity."""
    value = validate_package(package)
    data = (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    if len(data) > MAX_PACKAGE_BYTES:
        raise PackageError(f"runtime package exceeds {MAX_PACKAGE_BYTES} JSON bytes")
    return data


def read_package_bytes(path):
    """Read one explicitly selected file with a bounded read and full validation."""
    with Path(path).expanduser().open("rb") as stream:
        data = stream.read(MAX_PACKAGE_BYTES + 1)
    load_package(data)
    return data


def write_package(path, package):
    """Create a new private file; preserve any existing destination."""
    data = dump_package(package)
    destination = Path(path).expanduser()
    with destination.open("xb") as stream:
        stream.write(data)
    return {"sha256": sha256(data).hexdigest(), "size": len(data),
            "schema": SCHEMA, "profile": PROFILE}


def _raw_record(record, field, expected, label):
    _fields(record, expected, label)
    _uint(record["id"], 255, label + ".id")
    raw = record[field]
    maximum = MAX_CODE_BYTES if field == "code" else MAX_RESOURCE_BYTES
    if type(raw) is not bytes or not 1 <= len(raw) <= maximum:
        raise PackageError(f"{label}.{field} requires 1..{maximum} exact bytes")
    return {**record, field: raw.hex(), "sha256": sha256(raw).hexdigest()}


def build_package(*, logics, views=(), pictures=(), sounds=(), words=(), objects=(),
                  entry_logic=0):
    """Build from explicit code/data byte records; message slots stay one based."""
    package = {"schema": SCHEMA, "profile": PROFILE, "entry_logic": entry_logic}
    for name, rows in (("logics", logics), ("views", views),
                       ("pictures", pictures), ("sounds", sounds)):
        if not isinstance(rows, (list, tuple)) or len(rows) > 256:
            raise PackageError(f"{name} requires at most 256 explicit resource records")
        field = "code" if name == "logics" else "data"
        expected = {"id", "code", "messages"} if name == "logics" else {"id", "data"}
        package[name] = [
            _raw_record(row, field, expected, f"{name}[{index}]")
            for index, row in enumerate(rows)
        ]
    if not isinstance(words, (list, tuple)) or not isinstance(objects, (list, tuple)):
        raise PackageError("words and objects must be explicit record sequences")
    package["words"], package["objects"] = list(words), list(objects)
    result = validate_package(package)
    # Include JSON escaping/field overhead in the 64 MiB transport bound.
    dump_package(result)
    return result


def _logic_payload(record):
    from fdisbull.agi_resources import logic_messages

    _fields(record, {"id", "data"}, "logic resource")
    _uint(record["id"], 255, "logic resource id")
    payload = record["data"]
    messages = logic_messages(payload)
    length = int.from_bytes(payload[:2], "little")
    result = {"id": record["id"], "code": payload[2:2 + length],
              "messages": [message["text"] for message in messages]}
    _logic(_raw_record(result, "code", {"id", "code", "messages"}, "logic"),
           f"logics[{record['id']}]")
    return result


def package_from_raw(*, logics, views=(), pictures=(), sounds=(), words=(), objects=(),
                     entry_logic=0):
    """Convert full v2 LOGIC id/data payloads; assets remain opaque native inputs."""
    if not isinstance(logics, (list, tuple)) or len(logics) > 256:
        raise PackageError("logics requires at most 256 complete v2 resources")
    decoded, failures = [], []
    for record in logics:
        try:
            decoded.append(_logic_payload(record))
        except ValueError as error:
            failure = {"kind": "logic", "error": str(error)}
            if type(record) is dict and type(record.get("id")) is int:
                failure["id"] = record["id"]
            failures.append(failure)
    if failures:
        raise ResourcePackageError(failures)
    return build_package(logics=decoded, views=views, pictures=pictures, sounds=sounds,
                         words=words, objects=objects, entry_logic=entry_logic)


def package_from_v2(source, *, entry_logic=0):
    """Package an explicit complete V2Resources snapshot without omitting failures.

    Absent directories/optional WORDS.TOK/OBJECT are empty tables. Malformed
    present files and any malformed referenced resource fail explicitly.
    Literal vocabulary is lowercased for this fixed runtime profile; collisions
    after that conversion are rejected instead of choosing a definition.
    """
    from fdisbull.agi_resources import V2Resources

    resources = V2Resources(source) if isinstance(source, (str, Path)) else source
    if not isinstance(resources, V2Resources):
        raise PackageError("source must be an explicit directory or V2Resources snapshot")
    _uint(entry_logic, 255, "entry_logic")
    failures, raw = [], {}
    for item in resources.manifest()["directories"]:
        if item["status"] == "error":
            failures.append({"kind": item["kind"], "error": item["error"]})
    for kind in ("logic", "view", "picture", "sound"):
        records = []
        for item in resources.resources(kind):
            if item["status"] != "ok":
                failures.append({"kind": kind, "id": item["number"],
                                 "error": item.get("error", "Resource is not available")})
                continue
            record = {"id": item["number"], "data": item["payload"]}
            try:
                if kind == "logic":
                    records.append(_logic_payload(record))
                else:
                    _raw_record(record, "data", {"id", "data"}, kind)
                    records.append(record)
            except ValueError as error:
                failures.append({"kind": kind, "id": item["number"], "error": str(error)})
        raw[kind] = records
    vocabulary, inventory = resources.vocabulary(), resources.objects()
    for kind, table in (("words", vocabulary), ("objects", inventory)):
        if table["status"] == "error":
            failures.append({"kind": kind, "error": table["error"]})
    if not any(record["id"] == entry_logic for record in raw["logic"]):
        failures.append({"kind": "logic", "id": entry_logic,
                         "error": "Entry logic is absent or malformed"})
    if failures:
        raise ResourcePackageError(failures)
    words = [{"text": row["word"].lower(), "id": row["number"]}
             for row in vocabulary["entries"]]
    objects = [{"name": row["name"], "room": row["initial_room"]}
               for row in inventory["objects"]]
    return build_package(logics=raw["logic"], views=raw["view"],
                         pictures=raw["picture"], sounds=raw["sound"],
                         words=words, objects=objects, entry_logic=entry_logic)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--entry-logic", default=0, type=int)
    args = parser.parse_args(argv)
    package = package_from_v2(args.game_dir, entry_logic=args.entry_logic)
    print(json.dumps(write_package(args.output, package), sort_keys=True))


if __name__ == "__main__":
    main()
