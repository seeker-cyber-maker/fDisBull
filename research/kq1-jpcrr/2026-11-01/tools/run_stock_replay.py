#!/usr/bin/env python3
"""Replay a frozen JRSR with the unchanged JPC-RR PCRunner and RAWDumper.

No adaptive input is supplied. Host elapsed time includes JVM setup, emulation,
capture and shutdown; JMD timestamps retain the separate emulated timeline.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jar", type=Path, required=True)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--movie", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--stop-ns", type=int, required=True)
    parser.add_argument("--host-timeout", type=float, default=600)
    args = parser.parse_args()
    jar, library, movie, out = [p.resolve() for p in (args.jar, args.library, args.movie, args.out)]
    if args.stop_ns <= 0 or args.host_timeout <= 0:
        raise ValueError("Positive execution bounds are required")
    for path in (jar, library, movie, out):
        if any(c in str(path) for c in "(),\n\r"):
            raise ValueError("The stock plugin syntax cannot represent this path")
    out.mkdir(parents=True, exist_ok=False)
    capture = out / "capture.jmd"
    script = out / "replay.jpcrrinit"
    script.write_text(
        f"library {library}\n"
        f"load org.jpc.plugins.RAWDumper(rawoutput={capture})\n"
        f"load org.jpc.plugins.PCRunner(movie={movie},stoptime={args.stop_ns})\n"
    )
    command = ["java", "-Xmx512m", "-Djava.awt.headless=true", "-jar", str(jar), "-autoexec", str(script)]
    record = {
        "format": "kq1-stock-jpcrr-replay-1",
        "command": command,
        "movie": str(movie), "movie_sha256": digest(movie),
        "jar": str(jar), "jar_sha256": digest(jar),
        "stop_ns": args.stop_ns,
        "host_timing_scope": "Process launch through exit, including JVM, emulation, capture and teardown.",
        "adaptive_inputs": False,
    }
    started = time.monotonic_ns()
    timed_out = False
    with (out / "native.log").open("wb") as log:
        process = subprocess.Popen(command, cwd=jar.parent, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT)
        print(json.dumps({"event": "started", "pid": process.pid, "out": str(out)}), flush=True)
        last_report = -1
        while process.poll() is None:
            elapsed = (time.monotonic_ns() - started) / 1e9
            if elapsed > args.host_timeout:
                timed_out = True
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                break
            bucket = int(elapsed // 15)
            if bucket != last_report:
                last_report = bucket
                text = (out / "native.log").read_text(errors="replace")
                frames = re.findall(r"Saved frame #(\d+): (\d+)x(\d+) <(\d+)>", text)
                print(json.dumps({"event": "progress", "host_seconds": round(elapsed, 3),
                    "last_frame": frames[-1] if frames else None}), flush=True)
            time.sleep(0.2)
        code = process.wait()
        if process.stdin:
            process.stdin.close()
    record.update(exit_code=code, host_timeout=timed_out,
        elapsed_host_ns=time.monotonic_ns() - started)
    text = (out / "native.log").read_text(errors="replace")
    frames = re.findall(r"Saved frame #(\d+): (\d+)x(\d+) <(\d+)>", text)
    record["saved_frames_logged"] = len(frames)
    record["last_logged_frame"] = frames[-1] if frames else None
    record["critical_log_lines"] = [line for line in text.splitlines()
        if "Critical:" in line or "Exception" in line or "Error:" in line]
    record["capture"] = {"path": str(capture), "bytes": capture.stat().st_size,
        "sha256": digest(capture)} if capture.exists() else None
    record["movie_unchanged"] = digest(movie) == record["movie_sha256"]
    record["jar_unchanged"] = digest(jar) == record["jar_sha256"]
    (out / "replay-result.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record), flush=True)
    if code or timed_out or record["critical_log_lines"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
