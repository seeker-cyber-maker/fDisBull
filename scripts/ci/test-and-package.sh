#!/usr/bin/env bash
set -euo pipefail
mkdir -p artifacts/ordinary artifacts/receipts
bash scripts/ci/install-node.sh
python -m pip install --upgrade pip
python -m pip install ".[test,source]" build
python -m pytest -q --junitxml=artifacts/ordinary/tests.xml 2>&1 | tee artifacts/ordinary/tests.log
python -m build
python -m build --wheel ./player --outdir dist
python scripts/build_release.py
python scripts/check_dist.py
python scripts/check_package_payloads.py --core dist/fdisbull-*.whl --player dist/fdisbull_player-*.whl \
  --sdist dist/fdisbull-*.tar.gz --tool dist/fdisbull-*-tool.zip \
  --output artifacts/receipts/package-payloads.json

# Run every installed entry point outside both the checkout and unpacked roots.
# A source-tree import or a missing helper must not be hidden by the build cwd.
smoke_root=$(mktemp -d "$CI_PROJECT_DIR/.package-smoke.XXXXXX")
python -m venv --system-site-packages "$smoke_root/core"
"$smoke_root/core/bin/python" -m pip install --no-index --no-deps --force-reinstall dist/fdisbull-*.whl
python scripts/check_agent_skill.py --python "$smoke_root/core/bin/python" --output artifacts/receipts/agent-skill.json
python scripts/check_agent_skill.py --python "$smoke_root/core/bin/python" --skill write-gamefaqs-guide --output artifacts/receipts/guide-skill.json
python -m venv "$smoke_root/player"
"$smoke_root/player/bin/python" -m pip install --no-index --no-deps dist/fdisbull_player-*.whl
(
  cd "$smoke_root"
  env -u PYTHONPATH core/bin/python -I -c "import fdisbull; assert 'site-packages' in fdisbull.__file__"
  env -u PYTHONPATH core/bin/python -I -m fdisbull --help
  env -u PYTHONPATH player/bin/python -I -c "import importlib.util; import fdisbull_player; assert importlib.util.find_spec('fdisbull') is None"
  env -u PYTHONPATH player/bin/python -I -m fdisbull_player --help
)

python - "$smoke_root" <<'PY'
from pathlib import Path
import sys, tarfile, zipfile
root = Path(sys.argv[1])
with tarfile.open(next(Path('dist').glob('fdisbull-*.tar.gz'))) as archive:
    archive.extractall(root / 'sdist', filter='data')
with zipfile.ZipFile(next(Path('dist').glob('fdisbull-*-tool.zip'))) as archive:
    archive.extractall(root / 'tool')
PY
for source_kind in sdist tool; do
  python -m venv --system-site-packages "$smoke_root/$source_kind-env"
  "$smoke_root/$source_kind-env/bin/python" -m pip install --force-reinstall --no-build-isolation --no-deps "$smoke_root/$source_kind"/fdisbull-*
  (cd "$smoke_root" && env -u PYTHONPATH "$source_kind-env/bin/python" -I -m fdisbull --help)
done
python scripts/check_ci_qualification.py --write-ordinary --output artifacts/receipts/ordinary.json
