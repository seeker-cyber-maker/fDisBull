"""Author-only u32 C -> optimized LLVM IR -> toy UIL fixed-point experiment.

Not a production fDisBull parser, arbitrary decompiler or original-PE32 proof.
Only pure, local, scalar operations are accepted. Every original child is retained.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

MASK = 0xFFFFFFFF
OPS = {"xor": "^", "add": "+", "sub": "-", "and": "&", "or": "|", "mul": "*", "shl": "<<", "lshr": ">>"}
SSA = re.compile(r"%([A-Za-z_.0-9]+)")
ARG = r"(?:%[A-Za-z_.0-9]+|-?[0-9]+)"
ASSIGN = re.compile(rf"(%[A-Za-z_.0-9]+) = (xor|add|sub|mul|and|or|shl|lshr) i32 ({ARG}), ({ARG})$")
RETURN = re.compile(rf"ret i32 ({ARG})$")


class Refused(ValueError):
    """Fail closed when an unmodeled statement, effect, proof or tool is encountered."""


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate(blocks):
    if not isinstance(blocks, list) or len(blocks) != 2 or not all(isinstance(b, list) and b for b in blocks):
        raise Refused("exactly two nonempty original child blocks required")
    for block in blocks:
        if len(block) > 32:
            raise Refused("block instruction budget exceeded")
        for op in block:
            if not isinstance(op, dict) or set(op) != {"op", "constant"} or op["op"] not in OPS:
                raise Refused("unsupported op/effect: only pure u32 scalar operations")
            k = op["constant"]
            if type(k) is not int or not 0 <= k <= MASK or op["op"] in ("shl", "lshr") and k >= 32:
                raise Refused("non-u32 constant or invalid shift")


def apply(op, left, right):
    if op == "xor": return left ^ right
    if op == "add": return (left + right) & MASK
    if op == "sub": return (left - right) & MASK
    if op == "and": return left & right
    if op == "or": return left | right
    if op == "mul": return (left * right) & MASK
    if op == "shl": return (left << right) & MASK
    if op == "lshr": return left >> right
    raise Refused("unsupported expression")


def original_expr(blocks):
    validate(blocks)
    expr = {"var": "x"}
    for block in blocks:
        for step in block:
            expr = {"op": step["op"], "args": [expr, {"const": step["constant"]}]}
    return expr


def cost(expr):
    if "op" not in expr: return 0
    return 1 + sum(cost(a) for a in expr["args"])


def evaluate(expr, x):
    if "var" in expr: return x
    if "const" in expr: return expr["const"]
    return apply(expr["op"], *(evaluate(a, x) for a in expr["args"]))


def c_expr(expr):
    if "var" in expr: return "input"
    if "const" in expr: return str(expr["const"]) + "u"
    op = expr["op"]
    return "((unsigned int)(" + c_expr(expr["args"][0]) + " " + OPS[op] + " " + c_expr(expr["args"][1]) + "))"


def render_c(expr):
    if cost(expr) > 64:
        raise Refused("C expression budget exceeded")
    return ('_Static_assert(sizeof(unsigned int)==4,"requires 32-bit unsigned int");\n'
            '__attribute__((noinline)) unsigned int fdb_candidate(unsigned int input) {\n'
            '  return ' + c_expr(expr) + ';\n}\n')


def parse_llvm(ir):
    """Import only the compiler's pure, one-block i32 SSA subset, never arbitrary IR."""
    if len(ir) > 512000:
        raise Refused("LLVM IR exceeds budget")
    header = re.search(r"^define [^\n]*@fdb_candidate\(i32(?:\s+[A-Za-z]+)*\s+%([A-Za-z_.0-9]+)\)[^{]*\{\s*$", ir, re.M)
    if not header:
        raise Refused("expected one i32 input and explicit fdb_candidate function")
    tail = ir[header.end():]
    if "}" not in tail:
        raise Refused("unterminated function")
    body = tail.split("}", 1)[0]
    slots = {"%" + header.group(1): {"var": "x"}}
    result = None
    for line in body.splitlines():
        line = line.strip()
        if not line or line == "entry:" or line.startswith(";"):
            continue
        match = ASSIGN.fullmatch(line)
        if match:
            dst, op, left, right = match.groups()
            if dst in slots or len(slots) > 80:
                raise Refused("invalid/repeated SSA or instruction budget")
            def resolve(v):
                if v.startswith("%"):
                    if v not in slots: raise Refused("undefined SSA register")
                    return slots[v]
                n = int(v)
                if not -(1 << 31) <= n <= MASK: raise Refused("out of range LLVM integer")
                return {"const": n & MASK}
            slots[dst] = {"op": op, "args": [resolve(left), resolve(right)]}
            continue
        ret = RETURN.fullmatch(line)
        if ret and result is None:
            token = ret.group(1)
            if token.startswith("%"):
                if token not in slots: raise Refused("undefined return register")
                result = slots[token]
            else: result = {"const": int(token) & MASK}
            continue
        raise Refused("LLVM has branch, call, phi, memory, flags or unsupported instruction: " + line[:100])
    if result is None: raise Refused("missing unique return")
    return result


def compile_roundtrip(expr, clang):
    compiler = shutil.which(clang) if not Path(clang).is_absolute() else str(Path(clang))
    if not compiler or not Path(compiler).is_file(): raise Refused("explicit Clang executable unavailable")
    source = render_c(expr)
    with tempfile.TemporaryDirectory(prefix="fdb-fusion-") as directory:
        file = Path(directory) / "candidate.c"
        file.write_text(source)
        args = [compiler, "-std=c11", "-O2", "-S", "-emit-llvm", "-target", "x86_64-unknown-linux-gnu",
                "-fno-discard-value-names", "-x", "c", str(file), "-o", "-"]
        try:
            p = subprocess.run(args, capture_output=True, text=True, timeout=10, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise Refused("Clang compilation unavailable or timed out") from error
    if p.returncode or len(p.stdout) > 512000:
        raise Refused("C optimizer refused: " + p.stderr[:200])
    try:
        version_run = subprocess.run([compiler, "--version"], capture_output=True, text=True, timeout=5, check=False)
        version = version_run.stdout.splitlines()[0] if version_run.returncode == 0 and version_run.stdout else "unavailable"
    except (OSError, subprocess.TimeoutExpired):
        version = "unavailable"
    return (parse_llvm(p.stdout), hashlib.sha256(source.encode()).hexdigest(),
            hashlib.sha256(p.stdout.encode()).hexdigest(), version)


def prove(expr_a, expr_b, timeout_ms=3000):
    try: import z3
    except ImportError: raise Refused("Z3 required: sampled agreement cannot promote an optimization") from None
    x = z3.BitVec("x", 32)
    def encode(expr):
        if "var" in expr: return x
        if "const" in expr: return z3.BitVecVal(expr["const"], 32)
        left, right = (encode(p) for p in expr["args"])
        op = expr["op"]
        return {"xor": lambda: left ^ right, "add": lambda: left + right,
                "sub": lambda: left - right, "and": lambda: left & right,
                "or": lambda: left | right, "mul": lambda: left * right,
                "shl": lambda: left << right, "lshr": lambda: z3.LShR(left, right)}[op]()
    solver = z3.Solver()
    solver.set(timeout=timeout_ms)
    solver.add(encode(expr_a) != encode(expr_b))
    status = solver.check()
    if status == z3.sat:
        return {"status": "counterexample", "input": solver.model().eval(x, model_completion=True).as_long()}
    if status != z3.unsat: raise Refused("SMT proof unknown or timed out")
    return {"status": "proved_u32_model", "domain": "all 2^32 input words; no effects or intermediate observation"}


def discover(blocks, *, clang="clang", rounds=8, intermediate_observable=False):
    """Accept strictly improving, fully modeled transformations; keep original forever."""
    validate(blocks)
    if intermediate_observable: raise Refused("a child boundary is observable: do not fuse")
    if type(rounds) is not int or not 1 <= rounds <= 16: raise Refused("iteration budget must be 1..16")
    original = original_expr(blocks)
    original_sha = digest(blocks)
    best = original
    seen = {digest(best)}
    history = []
    status = "budget_exhausted"
    for iteration in range(1, rounds + 1):
        candidate, c_sha, ir_sha, compiler_version = compile_roundtrip(best, clang)
        sig = digest(candidate)
        record = {"round": iteration, "c_sha256": c_sha, "optimized_ir_sha256": ir_sha,
                  "before_nodes": cost(best), "candidate_nodes": cost(candidate), "candidate_hash": sig,
                  "compiler_version": compiler_version, "source_abi": "x86_64-unknown-linux-gnu; unsigned-int u32; C11 -O2"}
        if sig == digest(best):
            record["outcome"] = "fixed_point"
            history.append(record); status = "fixed_point"; break
        if sig in seen:
            record["outcome"] = "cycle_refused"
            history.append(record); status = "cycle_refused"; break
        proof = prove(original, candidate)
        record["proof"] = proof
        if proof["status"] != "proved_u32_model":
            record["outcome"] = "not_equivalent_refused"
            history.append(record); status = "not_equivalent_refused"; break
        if cost(candidate) >= cost(best):
            record["outcome"] = "not_shorter"
            history.append(record); status = "not_shorter"; break
        record["outcome"] = "accepted_bounded_model"
        history.append(record)
        seen.add(sig)
        best = candidate
    changed = digest(best) != digest(original)
    return {"format": "fdisbull-feedback-fusion-experiment-1",
            "scope": "authored u32 pure-model; optimized LLVM subset; no original Win32 or production UIL registration",
            "parent": "candidate:two-children:" + original_sha,
            "original_children": blocks, "original_semantics": original,
            "implementations": {"original": original, **({"candidate_optimized": best} if changed else {})},
            "default": "original", "promotion_eligible": changed and status == "fixed_point",
            "status": status, "history": history,
            "before_nodes": cost(original), "best_nodes": cost(best),
            "native_original_equivalence": False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--clang", default="clang")
    p.add_argument("--rounds", type=int, default=8)
    args = p.parse_args()
    blocks = [[{"op": "xor", "constant": 0x5A}], [{"op": "xor", "constant": 0xA5}]]
    print(json.dumps(discover(blocks, clang=args.clang, rounds=args.rounds), indent=2))


if __name__ == "__main__": main()
