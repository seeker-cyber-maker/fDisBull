"""Finite authenticated publisher using a caller-selected, existing command route."""

import argparse
import json
import os
import selectors
import signal
import subprocess
import sys
import time

from .client import Client, ClientError, private_file


def command_exchange(command, probe, *, timeout):
    if (not isinstance(command, list) or not command
            or any(not isinstance(x, str) or not x or "\0" in x for x in command)):
        raise ValueError("Source command must be an explicit argument list")
    # No shell expansion, automatic installation, tunnel creation or secret copy.
    payload = json.dumps(probe, allow_nan=False).encode()
    if len(payload) > 4096 or not 0 < timeout <= 30:
        raise ValueError("Invalid source probe size or timeout")
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    deadline = time.monotonic() + timeout
    output = bytearray()
    try:
        process.stdin.write(payload)
        process.stdin.close()
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise subprocess.TimeoutExpired([], timeout)
                chunk = os.read(process.stdout.fileno(), min(4096, 4097 - len(output)))
                if not chunk:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired([], timeout)
                    if process.wait(timeout=remaining):
                        raise ClientError("The configured ownership source command failed")
                    return json.loads(output)
                output.extend(chunk)
                if len(output) > 4096:
                    raise ClientError("Ownership source response exceeds byte limit")
    finally:
        # Kill only this invocation's new process group, including SSH helpers'
        # children. A timed-out source must not keep running after invalidation.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        process.stdout.close()
        if not process.stdin.closed:
            process.stdin.close()


def publish_once(client, stream_id, exchange):
    challenge = client.request("bridge-challenge", {"stream_id": stream_id})
    if not challenge["ok"]:
        raise ClientError(challenge["error"]["message"])
    result = challenge["result"]
    probe = {k: result[k] for k in ("stream_id", "challenge", "sequence")}
    event = exchange(probe, result["expires_in_ms"] / 1000)
    response = client.request("bridge-observe", event)
    if not response["ok"]:
        raise ClientError(response["error"]["message"])
    return response["result"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publisher", required=True, help="Private ownership-publisher.json descriptor")
    parser.add_argument("--viewer-id", required=True)
    parser.add_argument("--source-command", required=True, help="Private JSON argument-list file for an existing transport")
    parser.add_argument("--duration", type=float, default=30)
    parser.add_argument("--interval", type=float, default=0.1)
    args = parser.parse_args(argv)
    if not 0 < args.duration <= 3600 or not 0.01 <= args.interval <= 5:
        parser.error("Choose a finite duration (0..3600 seconds) and interval (0.01..5)")
    client = Client(args.publisher)
    command = json.loads(private_file(args.source_command, limit=8192))
    opened = client.request("bridge-open", {"viewer_id": args.viewer_id})
    if not opened["ok"]:
        raise ClientError(opened["error"]["message"])
    stream = opened["result"]["stream_id"]
    deadline = time.monotonic() + args.duration
    try:
        while time.monotonic() < deadline:
            status = publish_once(client, stream, lambda probe, ttl: command_exchange(
                command, probe, timeout=min(ttl, max(0.01, deadline - time.monotonic()))))
            print(json.dumps(status), flush=True)
            time.sleep(min(args.interval, max(0, deadline - time.monotonic())))
        return 0
    finally:
        # Receiver expiry is the fallback if this process or its transport dies.
        client.request("bridge-invalidate", {"stream_id": stream})


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(json.dumps({"error": str(error)[:200]}), file=sys.stderr)
        raise SystemExit(1)
