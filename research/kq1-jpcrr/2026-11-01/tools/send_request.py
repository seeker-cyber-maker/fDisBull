"""Submit one file-based authoring request and print a compact receipt."""
import argparse
import json
import sys
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("directory", type=Path)
parser.add_argument("name")
parser.add_argument("--wait", type=float, default=20)
args = parser.parse_args()
request = json.load(sys.stdin)
path = args.directory / "requests" / (args.name + ".json")
if path.exists():
    raise SystemExit("Request already exists; inspect its receipt instead of repeating it")
temp = path.with_suffix(".tmp")
temp.write_text(json.dumps(request) + "\n")
temp.rename(path)
response = args.directory / (args.name + ".response.json")
deadline = time.monotonic() + args.wait
while not response.exists() and time.monotonic() < deadline:
    time.sleep(0.1)
if not response.exists():
    print(json.dumps({"pending": str(response)}))
    raise SystemExit(0)
data = json.loads(response.read_text())
state = data.get("state", {})
error = data.get("error")
print(json.dumps({"receipt": str(response), "ok": data.get("ok"),
    "error": None if error is None else {"type": error["type"], "message": error["message"][:2500]},
    "state": {k: state.get(k) for k in ("time_ns", "room", "previous_room", "score", "x", "y", "view", "direction", "control", "player_control", "window", "items")},
    "result_count": len(data.get("results", []))}))
