"""The framework loads with its own declared dependencies and no fDisBull stack."""
import ast
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_source_has_no_external_fdisbull_or_unbundled_analysis_imports():
    # The operational decoder is an explicit DotBox dependency. Independence
    # excludes a separate fDisBull stack, not the machinery shipped with DotBox.
    forbidden = {"fdisbull", "capstone", "lief", "z3"}
    for path in (ROOT / "src/dotbox").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                names = [item.name for item in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or ""]
            else:
                continue
            assert not forbidden.intersection(name.split(".")[0] for name in names), path


def test_all_framework_modules_load_with_analysis_imports_refused(tmp_path):
    script = r'''
import importlib, importlib.abc, json, pkgutil, sys
sys.path.insert(0, sys.argv[1])
class RejectAnalysis(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split('.')[0] in {'fdisbull','capstone','lief','z3'}:
            raise AssertionError('Forbidden runtime import: '+name)
sys.meta_path.insert(0, RejectAnalysis())
import dotbox
names = [item.name for item in pkgutil.iter_modules(dotbox.__path__) if item.name != '__main__']
for name in names:
    importlib.import_module('dotbox.'+name)
from dotbox.backend import _load_runtime
runtime = _load_runtime()
assert all(item.__module__.startswith('dotbox.') for item in runtime)
print(json.dumps({'modules': names, 'runtime': [item.__name__ for item in runtime]}))
'''
    result = subprocess.run([sys.executable, "-I", "-c", script, str(ROOT / "src")],
                            cwd=tmp_path, capture_output=True, text=True, check=True)
    report = json.loads(result.stdout)
    assert {"backend", "service", "store", "native_rpc", "native_session"} <= set(report["modules"])
    assert report["runtime"][:2] == ["ControlStore", "NativeSession"]
