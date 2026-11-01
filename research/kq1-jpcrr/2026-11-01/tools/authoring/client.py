"""Small synchronous client for HeadlessAuthor; no emulation or game logic."""
from __future__ import annotations

import json
import os
from pathlib import Path
import select
import subprocess
from typing import Any


class AuthoringError(RuntimeError):
    pass


class Author:
    def __init__(
        self,
        jar: str | Path,
        library: str | Path,
        log_path: str | Path,
        *,
        classes: str | Path | None = None,
        capture: str | Path | None = None,
        java: str = "java",
        response_timeout: float = 70,
    ) -> None:
        classes = Path(classes or Path(__file__).with_name("classes"))
        self.timeout = response_timeout
        self._log = open(log_path, "x", encoding="utf-8")
        command = [java, "-cp", os.pathsep.join((str(classes), str(jar))),
                   "kq1tas.HeadlessAuthor", "--library", str(library)]
        if capture is not None:
            command.extend(("--capture", str(capture)))
        self.process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self._log, text=True, encoding="utf-8", bufsize=1,
        )
        try:
            self.ready = self._read()
            if self.ready.get("event") != "ready":
                raise AuthoringError(f"Unexpected handshake: {self.ready!r}")
        except BaseException:
            self.process.terminate()
            self.process.wait(timeout=10)
            self._log.close()
            raise

    def _read(self) -> dict[str, Any]:
        assert self.process.stdout is not None
        if not select.select([self.process.stdout], [], [], self.timeout)[0]:
            raise TimeoutError("No authoring response; inspect the stock-core log before continuing")
        line = self.process.stdout.readline()
        if not line:
            raise AuthoringError(f"Authoring process ended; exit={self.process.poll()}; inspect log")
        reply = json.loads(line)
        if not reply.get("ok"):
            raise AuthoringError(f"{reply.get('error')}: {reply.get('message')}")
        return reply

    def command(self, name: str, *fields: object) -> dict[str, Any]:
        parts = [name, *(str(field) for field in fields)]
        if any(any(c in field for c in "\r\n\t") for field in parts):
            raise ValueError("Protocol fields cannot contain tabs or line endings")
        assert self.process.stdin is not None
        self.process.stdin.write("\t".join(parts) + "\n")
        self.process.stdin.flush()
        return self._read()

    def read(self, address: int, length: int) -> bytes:
        return bytes.fromhex(self.command("read", address, length)["hex"])

    def run_until(self, time_ns: int, host_budget_ms: int = 30_000) -> dict[str, Any]:
        """One bounded attempt; caller explicitly resumes if reason is host_budget."""
        return self.command("run_until_ns", time_ns, host_budget_ms)

    def close(self) -> None:
        try:
            if self.process.poll() is None:
                self.command("quit")
                self.process.wait(timeout=10)
        finally:
            self._log.close()

    def __enter__(self) -> "Author":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()
