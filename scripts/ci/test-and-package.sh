#!/usr/bin/env bash
set -euo pipefail
mkdir -p artifacts/ordinary artifacts/receipts
bash scripts/ci/install-node.sh
python -m pip install --upgrade pip
python -m pip install ".[test,source,udc]" build
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
# These release contracts must execute, including their optional native emulator
# and compiler seams. Their separate report rejects skips independently of the
# ordinary suite's intentionally optional backend cases.
python -m pytest -q tests/test_udc_return_contracts.py \
  tests/test_udc_layers.py::test_event_contract_compares_behavior_and_retains_provenance \
  --junitxml=artifacts/ordinary/required-contracts.xml 2>&1 | tee artifacts/ordinary/required-contracts.log
python - <<'PY'
from xml.etree import ElementTree as ET
root=ET.parse('artifacts/ordinary/required-contracts.xml').getroot()
cases=root.findall('.//testcase')
assert len(cases)==26, f'Expected 22 return and four event contracts, got {len(cases)}'
assert not root.findall('.//skipped'), 'Required return/event contracts were skipped'
assert not root.findall('.//failure') and not root.findall('.//error')
PY
python scripts/check_dist.py
python scripts/check_package_payloads.py --core dist/fdisbull-*.whl --player dist/fdisbull_player-*.whl \
  --sdist dist/fdisbull-*.tar.gz --tool dist/fdisbull-*-tool.zip \
  --output artifacts/receipts/package-payloads.json
python scripts/check_ci_qualification.py --write-ordinary --output artifacts/receipts/ordinary.json
