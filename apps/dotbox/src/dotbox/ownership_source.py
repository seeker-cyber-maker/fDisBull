"""One bounded SSH/stdin ownership exchange; no network listener or app access.

A trusted coordinator on the viewer host observes each pending probe through its
supported browser tools. The existing SSH command carries only JSON data. This
module never inspects an app, credentials, game data or a private control API.
"""

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import sys
import time

from .client import private_file
from .service import private_directory, session_lock

LIMIT = 4096


def atomic_json(path, value):
    temporary = path.with_name(path.name + "." + secrets.token_hex(8))
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as output:
            json.dump(value, output, allow_nan=False)
            output.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def exchange(directory, viewer_id, probe, *, timeout=2.0):
    if not isinstance(viewer_id, str) or re.fullmatch(r"[0-9a-f]{64}", viewer_id) is None:
        raise ValueError("Invalid selected viewer binding")
    if not isinstance(probe, dict) or set(probe) != {"stream_id", "challenge", "sequence"}:
        raise ValueError("Expected one receiver-issued probe")
    if (any(not isinstance(probe[k], str) or re.fullmatch(r"[0-9a-f]{64}", probe[k]) is None
            for k in ("stream_id", "challenge"))
            or type(probe["sequence"]) is not int or probe["sequence"] < 1):
        raise ValueError("Invalid probe fields")
    if not 0.05 <= timeout <= 30:
        raise ValueError("Invalid source exchange timeout")
    directory = private_directory(directory)
    with session_lock(directory):
        request_id = secrets.token_hex(32)
        deadline = time.monotonic() + timeout
        atomic_json(directory / "request.json", {"request_id": request_id,
                    "viewer_id": viewer_id, "probe": probe})
        while time.monotonic() < deadline:
            try:
                response = json.loads(private_file(directory / "response.json", limit=LIMIT))
            except FileNotFoundError:
                response = None
            if isinstance(response, dict) and response.get("request_id") == request_id:
                if set(response) != {"request_id", "event"} or not isinstance(response["event"], dict):
                    raise ValueError("Invalid source response")
                event = response["event"]
                if any(event.get(k) != v for k, v in probe.items()):
                    raise ValueError("Source response belongs to a different probe")
                return event
            time.sleep(min(0.02, max(0, deadline - time.monotonic())))
        raise TimeoutError("No fresh viewer observation arrived before the source deadline")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True)
    parser.add_argument("--viewer-id", required=True)
    parser.add_argument("--timeout", type=float, default=2.0)
    args = parser.parse_args(argv)
    try:
        data = sys.stdin.buffer.read(LIMIT + 1)
        if len(data) > LIMIT:
            raise ValueError("Source probe exceeds byte limit")
        result = exchange(args.directory, args.viewer_id, json.loads(data), timeout=args.timeout)
        print(json.dumps(result, allow_nan=False), flush=True)
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(json.dumps({"error": str(error)[:200]}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
