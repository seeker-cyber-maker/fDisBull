"""Private output and provenance checks for the benchmark harness."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("rom_asm_benchmark", Path(__file__).resolve().parents[1] / "scripts/benchmark_rom_asm.py")
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def test_rejects_git_worktree_and_accepts_private_output(tmp_path):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / ".git").write_text("gitdir: elsewhere")
    with pytest.raises(ValueError, match="outside every Git worktree"):
        benchmark.private_output(checkout / "nested" / "raw")
    assert benchmark.private_output(tmp_path / "private") == tmp_path / "private"


def test_rejects_nonregular_and_oversized_source(tmp_path):
    with pytest.raises((ValueError, OSError)):
        benchmark.read_source(tmp_path)
    source = tmp_path / "big"
    with source.open("wb") as f:
        f.truncate(benchmark.MAX_SOURCE_BYTES + 1)
    with pytest.raises(ValueError, match="64 MiB"):
        benchmark.read_source(source)


def test_comparison_counts_unknowns_and_ordered_hypotheses():
    def row(address, mnemonic, operands):
        return {"address": address, "normalized": {"mnemonic": mnemonic, "operands": operands}}
    a = {"mapping": {"address": 0}, "attempted_words": 4, "instructions": [row(0, "nop", ""), row(2, "mov", "x"), row(4, "rts", "")]}
    b = {"instructions": [row(0, "nop", ""), row(2, "mov", "y")]}
    assert benchmark.compare(a, b) == {"both_decoded": 2, "both_unknown": 1, "left_only_decoded": 1,
                                     "right_only_decoded": 0, "mnemonic_agreement": 2,
                                     "operand_agreement": 1, "both_agreement": 1}


def test_accuracy_gate_runs_same_manual_cases_with_corrected_capstone():
    from types import SimpleNamespace
    result = benchmark.accuracy_gate(SimpleNamespace(ghidra_home=None, saturn_root=None, timeout=60), None,
                                     backends=('capstone',))
    assert result == {'capstone': {'cases': 23, 'passed': 23, 'failed_cases': []}}
