"""Isolated authored pure-u32 proof and real Clang LLVM roundtrip tests."""
import importlib.util
from pathlib import Path
import shutil

import pytest

FILE = Path(__file__).resolve().parents[1] / "examples" / "uil_common" / "feedback_fusion.py"
spec = importlib.util.spec_from_file_location("feedback_fusion", FILE)
fusion = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fusion)


@pytest.mark.parametrize("source,expected", [
    ([[{"op": "xor", "constant": 0x5A}], [{"op": "xor", "constant": 0xA5}]], 1),
    ([[{"op": "add", "constant": 17}], [{"op": "sub", "constant": 17}]], 0),
    ([[{"op": "xor", "constant": 0xDEAD}], [{"op": "xor", "constant": 0xDEAD}]], 0),
])
def test_real_clang_fixed_point(source, expected):
    pytest.importorskip("z3")
    if not shutil.which("clang"): pytest.skip("Clang unavailable")
    result = fusion.discover(source)
    assert result["before_nodes"] == 2
    assert result["best_nodes"] == expected
    assert result["status"] == "fixed_point"
    assert result["promotion_eligible"]
    assert result["original_children"] == source
    assert result["default"] == "original"
    assert len(result["history"]) >= 2
    assert result["history"][0]["proof"]["status"] == "proved_u32_model"
    for x in (0, 1, 255, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFF):
        assert fusion.evaluate(result["original_semantics"], x) == fusion.evaluate(result["implementations"]["candidate_optimized"], x)


def test_already_simple_retained():
    pytest.importorskip("z3")
    if not shutil.which("clang"): pytest.skip("Clang unavailable")
    source = [[{"op": "xor", "constant": 90}], [{"op": "add", "constant": 3}]]
    result = fusion.discover(source)
    assert result["best_nodes"] == 2
    assert not result["promotion_eligible"]
    assert "candidate_optimized" not in result["implementations"]
    assert result["original_children"] == source


def test_invalid_input_or_live_intermediate_refuses():
    s = [[{"op": "xor", "constant": 2}], [{"op": "xor", "constant": 3}]]
    with pytest.raises(fusion.Refused, match="observable"):
        fusion.discover(s, intermediate_observable=True)
    with pytest.raises(fusion.Refused, match="unsupported op"):
        fusion.discover([[{"op": "call", "constant": 2}], s[1]])
    with pytest.raises(fusion.Refused, match="invalid shift"):
        fusion.discover([[{"op": "shl", "constant": 32}], s[1]])
    with pytest.raises(fusion.Refused, match="exactly two"):
        fusion.discover([s[0]])


def test_unmodeled_llvm_refuses():
    for text in (
        "define i32 @fdb_candidate(i32 %input) {\nentry:\n  call void @foreign()\n  ret i32 %input\n}",
        "define i32 @fdb_candidate(i32 %input) {\nentry:\n  br label %done\ndone:\n  ret i32 %input\n}",
        "define i32 @fdb_candidate(i32 %input) {\nentry:\n  %t = load i32, ptr %input\n  ret i32 %t\n}",
    ):
        with pytest.raises(fusion.Refused): fusion.parse_llvm(text)


def test_z3_catches_wrong_optimized_reconstruction():
    pytest.importorskip("z3")
    src = fusion.original_expr([[{"op": "xor", "constant": 5}], [{"op": "xor", "constant": 10}]])
    bad = {"const": 123}
    p = fusion.prove(src, bad)
    assert p["status"] == "counterexample"
    assert fusion.evaluate(src, p["input"]) != 123


def test_false_compiler_result_does_not_promote(monkeypatch):
    pytest.importorskip("z3")
    monkeypatch.setattr(fusion, "compile_roundtrip", lambda expr, clang, **kwargs: ({"const": 0}, "c" * 64, "i" * 64, "test clang"))
    src = [[{"op": "xor", "constant": 1}], [{"op": "xor", "constant": 2}]]
    r = fusion.discover(src)
    assert r["status"] == "not_equivalent_refused"
    assert r["default"] == "original"
    assert not r["promotion_eligible"]
    assert "candidate_optimized" not in r["implementations"]


def test_round_budget_and_unknown_tool():
    src = [[{"op": "xor", "constant": 1}], [{"op": "xor", "constant": 2}]]
    with pytest.raises(fusion.Refused, match="iteration budget"):
        fusion.discover(src, rounds=0)
    with pytest.raises(fusion.Refused, match="unavailable"):
        fusion.compile_roundtrip(fusion.original_expr(src), "/nonexistent/fdb-clang")


def test_a_shortened_unstable_result_is_not_promoted():
    pytest.importorskip("z3")
    if not shutil.which("clang"): pytest.skip("Clang unavailable")
    source = [[{"op": "xor", "constant": 0x5A}], [{"op": "xor", "constant": 0xA5}]]
    result = fusion.discover(source, rounds=1)
    assert result["status"] == "budget_exhausted"
    assert result["best_nodes"] == 1
    assert not result["promotion_eligible"]
    assert result["default"] == "original"


def test_macos_local_host_target_is_independent_of_windows_guest():
    """Use the installed host Clang (including Apple clang) for pure IR work.

    Does not claim that a Mach-O or Windows executable was compiled or run.
    """
    pytest.importorskip("z3")
    if not shutil.which("clang"): pytest.skip("Host Clang unavailable")
    blocks = [[{"op": "xor", "constant": 0x5A}], [{"op": "xor", "constant": 0xA5}]]
    result = fusion.discover(blocks, llvm_target="host")
    assert result["status"] == "fixed_point"
    assert result["requested_llvm_target"] == "host"
    assert result["history"][0]["requested_llvm_target"] == "host"
    assert result["original_children"] == blocks
    assert result["native_original_equivalence"] is False


def test_invalid_target_refuses_before_compilation():
    blocks = [[{"op": "xor", "constant": 1}], [{"op": "xor", "constant": 2}]]
    with pytest.raises(fusion.Refused, match="unsupported LLVM IR target"):
        fusion.discover(blocks, llvm_target="arbitrary-PE32-executable")
    with pytest.raises(fusion.Refused, match="unsupported LLVM IR target"):
        fusion.compile_roundtrip(fusion.original_expr(blocks), "clang", llvm_target="bad")
