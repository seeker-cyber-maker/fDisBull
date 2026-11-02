"""Checkout entry point for the redistributable common-UIL test-source fixture."""
from pathlib import Path
import sys

# Test-source distributions deliberately exclude examples. Keep the actual
# authored fixture with their other complete helpers, and reuse it here.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tests'))
from fixtures_common_uil import *  # noqa: F403

if __name__ == '__main__':
    main()  # noqa: F405
