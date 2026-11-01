"""Open the authored replica's real status menu in Japanese, then close it.

This is an explicit native acceptance check, not part of ordinary unit tests.
It launches only the replica (never the installed original), requests Japanese
through the standard Cocoa localization argument, and uses fDisBull's
reversible macOS session to observe and close the menu it opened. It writes no
preference or login setting. The app is stopped by exact PID in ``finally``.
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve()
REPLICA = HERE.parents[1]
REPO = HERE.parents[4]
APP = REPLICA / "build" / "Cpuinfo Replica.app"
EXECUTABLE = APP / "Contents" / "MacOS" / "CpuinfoReplica"
BUNDLE = "local.codex.cpuinfo-replica"
EXPECTED = [
    "ログイン時に開始",
    "更新間隔",
    "表示",
    "テーマ",
    "コアを個別に表示",
    "アクティビティモニタを開く",
    "終了",
]


def processes() -> list[int]:
    result = subprocess.run(
        ["pgrep", "-x", "CpuinfoReplica"], capture_output=True, text=True, check=False
    )
    return (
        [int(value) for value in result.stdout.split()]
        if result.returncode == 0
        else []
    )


def stop(pids: list[int]) -> None:
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if not processes():
            return
        time.sleep(0.1)
    for pid in processes():
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def main() -> int:
    if sys.platform != "darwin":
        raise SystemExit("live language acceptance requires macOS")
    if not EXECUTABLE.is_file():
        raise SystemExit("build the replica first: ./build-app.sh")
    if processes():
        raise SystemExit(
            "a replica instance is already running; close it before this acceptance"
        )
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(REPO / "src") + (
        os.pathsep + environment["PYTHONPATH"] if environment.get("PYTHONPATH") else ""
    )
    started: list[int] = []
    try:
        subprocess.run(
            ["open", "-n", "-a", str(APP), "--args", "-AppleLanguages", "(ja)"],
            check=True,
            timeout=30,
        )
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            started = processes()
            if started:
                break
            time.sleep(0.1)
        if not started:
            raise SystemExit("the replica did not start")
        # The process exists before AppKit creates its status item and menu.
        time.sleep(2)
        with tempfile.TemporaryDirectory(prefix="cpuinfo-language-") as temporary:
            output = Path(temporary) / "session"
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fdisbull",
                    "macos-session",
                    BUNDLE,
                    str(output),
                    "--live",
                    "--status-index",
                    "0",
                ],
                cwd=REPO,
                env=environment,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            payload = json.loads(result.stdout) if result.stdout.strip() else {}
            error = payload.get("error") or payload.get("result", {}).get("error")
            message = error.get("message") if isinstance(error, dict) else None
            if not payload.get("ok") or result.returncode != 0:
                raise SystemExit(
                    "live session failed: "
                    + (
                        message
                        or result.stderr[-2000:]
                        or json.dumps(payload)[:2000]
                        or "no reply"
                    )
                )
            session = payload["result"]
            if session.get("status") != "confirmed":
                raise SystemExit(
                    "live session was not confirmed: " + json.dumps(session)[:2000]
                )
            before = json.loads(Path(session["artifacts"]["before"]).read_text())
            labels = [
                node.get("title")
                for node in before["ax"]["nodes"]
                if node.get("role") == "AXMenuItem"
                and node.get("depth") == 4
                and node.get("title")
            ]
            if labels != EXPECTED:
                raise SystemExit(
                    "unexpected Japanese labels: "
                    + json.dumps(labels, ensure_ascii=False)
                )
            cleanup = session.get("cleanup", {})
            if cleanup.get("status") != "confirmed" or not any(
                item.get("status") == "restored_closed"
                for item in cleanup.get("outcomes", [])
            ):
                raise SystemExit(
                    "menu was not confirmed closed: " + json.dumps(cleanup)
                )
            evidence = {
                "format": "fdisbull-cpuinfo-live-language-1",
                "bundle_id": BUNDLE,
                "language": "ja",
                "labels": labels,
                "session_status": session["status"],
                "cleanup": cleanup,
                "identity": session.get("identity"),
                "app_sha256": hashlib.sha256(EXECUTABLE.read_bytes()).hexdigest(),
                "menu_preferences_changed": False,
                "original_app_used": False,
            }
            print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
        return 0
    finally:
        stop(started)


if __name__ == "__main__":
    raise SystemExit(main())
