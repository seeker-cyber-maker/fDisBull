#!/usr/bin/env bash
# Shared by hosted CI and local artifact verification; uses existing genuine dependencies.
set -euo pipefail
# Run every installed entry point outside both the checkout and unpacked roots.
# A source-tree import or a missing helper must not be hidden by the build cwd.
# CI_BUILDS_DIR is the runner parent, not CI_PROJECT_DIR. The installed-skill
# gate deliberately refuses even a venv's site-packages beneath the checkout.
ci_python="${FDISBULL_CI_PYTHON:-python}"
package_dir="${FDISBULL_CI_PACKAGES:-$CI_PROJECT_DIR/dist}"
receipt_dir="${FDISBULL_CI_RECEIPTS:-$CI_PROJECT_DIR/artifacts/receipts}"
mkdir -p "$receipt_dir"
smoke_root=$(mktemp -d "$CI_BUILDS_DIR/fdisbull-package-smoke.XXXXXX")
"$ci_python" -m venv --system-site-packages "$smoke_root/core"
"$smoke_root/core/bin/python" -m pip install --no-index --no-deps --force-reinstall "$package_dir"/fdisbull-*.whl
"$ci_python" scripts/check_agent_skill.py --python "$smoke_root/core/bin/python" --output "$smoke_root/agent-skill.json"
cp "$smoke_root/agent-skill.json" "$receipt_dir/agent-skill.json"
"$ci_python" scripts/check_agent_skill.py --python "$smoke_root/core/bin/python" --skill write-gamefaqs-guide --output "$smoke_root/guide-skill.json"
cp "$smoke_root/guide-skill.json" "$receipt_dir/guide-skill.json"
"$ci_python" -m venv "$smoke_root/player"
"$smoke_root/player/bin/python" -m pip install --no-index --no-deps "$package_dir"/fdisbull_player-*.whl
(
  cd "$smoke_root"
  env -u PYTHONPATH core/bin/python -I -c "import fdisbull; assert 'site-packages' in fdisbull.__file__"
  env -u PYTHONPATH core/bin/python -I -m fdisbull --help
  env -u PYTHONPATH player/bin/python -I -c "import importlib.util; import fdisbull_player; assert importlib.util.find_spec('fdisbull') is None"
  env -u PYTHONPATH player/bin/python -I -m fdisbull_player --help
)

"$ci_python" - "$smoke_root" "$package_dir" <<'PY'
from pathlib import Path
import sys, tarfile, zipfile
root = Path(sys.argv[1])
packages = Path(sys.argv[2])
with tarfile.open(next(packages.glob('fdisbull-*.tar.gz'))) as archive:
    archive.extractall(root / 'sdist', filter='data')
with zipfile.ZipFile(next(packages.glob('fdisbull-*-tool.zip'))) as archive:
    archive.extractall(root / 'tool')
PY
for source_kind in sdist tool; do
  "$ci_python" -m venv --system-site-packages "$smoke_root/$source_kind-env"
  "$smoke_root/$source_kind-env/bin/python" -m pip install --force-reinstall --no-index --no-build-isolation --no-deps "$smoke_root/$source_kind"/fdisbull-*
  (cd "$smoke_root" && env -u PYTHONPATH "$source_kind-env/bin/python" -I -m fdisbull --help)
done
