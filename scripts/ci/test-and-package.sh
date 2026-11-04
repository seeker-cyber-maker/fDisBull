#!/usr/bin/env bash
set -euo pipefail
mkdir -p artifacts/ordinary artifacts/receipts
bash scripts/ci/install-node.sh
python -m pip install --upgrade pip
python -m pip install ".[test,source]" build
python -m build
python -m build --wheel ./player --outdir dist
python scripts/build_release.py
python scripts/check_dist.py
python scripts/check_package_payloads.py --core dist/fdisbull-*.whl --player dist/fdisbull_player-*.whl \
  --sdist dist/fdisbull-*.tar.gz --tool dist/fdisbull-*-tool.zip

bash scripts/ci/package-smoke.sh

# Cheap package/install checks run first; full tests and final inventory bind
# the successful receipt to the unchanged tested source and artifact bytes.
python -m pytest -q --junitxml=artifacts/ordinary/tests.xml 2>&1 | tee artifacts/ordinary/tests.log
python scripts/check_dist.py
python scripts/check_package_payloads.py --core dist/fdisbull-*.whl --player dist/fdisbull_player-*.whl \
  --sdist dist/fdisbull-*.tar.gz --tool dist/fdisbull-*-tool.zip \
  --output artifacts/receipts/package-payloads.json
python scripts/check_ci_qualification.py --write-ordinary --output artifacts/receipts/ordinary.json
