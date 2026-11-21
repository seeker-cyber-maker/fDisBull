#!/usr/bin/env python3
"""Run the checkout's stdlib probe without installing DotBox.

For a one-file attachment, send src/dotbox/runtime_probe.py itself instead.
"""
from pathlib import Path
import runpy


if __name__ == "__main__":
    runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "src" / "dotbox" / "runtime_probe.py"),
        run_name="__main__",
    )
