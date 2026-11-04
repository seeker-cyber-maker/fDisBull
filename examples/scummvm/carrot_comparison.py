"""Create a partial Z scene and replay receipt from two fresh KQ1 carrot runs."""

import sys

from fdisbull.scene_backend_comparison import main


if __name__ == "__main__":
    raise SystemExit(main(["--task", "carrot", *sys.argv[1:]]))
