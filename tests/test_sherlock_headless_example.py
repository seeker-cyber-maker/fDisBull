"""Keep the separately installable headless example in the repository gate."""
from pathlib import Path
import subprocess
import sys
import pytest


def test_headless_benchmark_contract():
    package = Path(__file__).resolve().parents[1] / "examples" / "recovery" / "sherlock_headless"
    if not package.is_dir():
        pytest.skip("Sherlock headless is a separately packaged, checkout-only example")
    result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                            cwd=package, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
