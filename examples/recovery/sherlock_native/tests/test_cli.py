#!/usr/bin/env python3
"""Black-box contract tests for a compiled CLI; Python is not a product runtime.

Usage: python3 tests/test_cli.py bin/sherlock-cli [Resources/sherlock_puzzles.bin]
The small independent consumer below solves public JSON constraints. It never
reads the original table, executable memory, or an engine's private solution.
"""
from __future__ import annotations

import argparse
import copy
from functools import lru_cache
import itertools
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


PROTOCOL = "sherlock-cli-1"
UINT64_MAX = "18446744073709551615"
CLUE_TYPES = (
    "same_column", "not_same_column", "next_to", "not_next_to",
    "left_of", "between", "not_between", "reference",
)
VALUES = tuple(tuple(i for i in range(6) if mask & (1 << i)) for mask in range(64))
PERMUTATIONS = tuple(itertools.permutations(range(6)))


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def reject_constant(value):
    raise AssertionError(f"Non-JSON numeric constant in response: {value}")


def no_hidden_answers(value):
    if isinstance(value, dict):
        require(not {"solution", "first_solution", "second_solution"}.intersection(value),
                "A response contains a private answer field")
        for child in value.values():
            no_hidden_answers(child)
    elif isinstance(value, list):
        for child in value:
            no_hidden_answers(child)


class Harness:
    def __init__(self, binary):
        self.binary = str(binary)
        self.calls = 0

    def run(self, arguments, *, data=None, code=0, environment=None, cwd=None, binary=None):
        env = os.environ.copy()
        env.pop("SHERLOCK_PUZZLE_TABLE", None)
        if environment:
            env.update(environment)
        command = [str(binary or self.binary), *arguments]
        result = subprocess.run(command, input=data, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, env=env, cwd=cwd,
                                timeout=30, check=False)
        self.calls += 1
        require(result.returncode == code,
                f"{arguments!r}: exit {result.returncode}, wanted {code}; "
                f"stdout={result.stdout!r}; stderr={result.stderr!r}")
        require(not result.stderr, f"Unexpected stderr: {result.stderr!r}")
        response = json.loads(result.stdout.decode("utf-8"), parse_constant=reject_constant)
        require(isinstance(response, dict) and response.get("format") == PROTOCOL,
                f"Invalid protocol envelope: {response!r}")
        require(result.stdout.endswith(b"\n"), "JSON response needs its terminating newline")
        if code in (2, 3):
            require(response["kind"] == "error" and response["ok"] is False,
                    f"Failure must have a JSON error envelope: {response!r}")
            require(response["error"]["code"] and response["error"]["message"],
                    "Error must identify its code and reason")
        if response["kind"] not in ("help", "version"):
            no_hidden_answers(response)
        return response


def relation(name, a, b=0, c=0):
    if name == "same_column":
        return a == b
    if name == "not_same_column":
        return a != b
    if name == "next_to":
        return abs(a - b) == 1
    if name == "not_next_to":
        return abs(a - b) != 1
    if name == "left_of":
        return a < b
    if name == "between":
        return abs(a - c) == 2 and 2 * b == a + c
    if name == "not_between":
        return abs(a - c) == 2 and 2 * b != a + c
    if name == "reference":
        return True
    raise AssertionError(f"Unknown clue: {name}")


@lru_cache(maxsize=16384)
def row_support(domains):
    support = [0] * 6
    for columns in PERMUTATIONS:
        if all(domains[item] & (1 << columns[item]) for item in range(6)):
            for item, column in enumerate(columns):
                support[item] |= 1 << column
    return tuple(support)


def solve_public(challenge, *, candidates=None, contrary=None, allow_unsat=False):
    """Independent, bounded finite-domain consumer of the documented JSON."""
    constraints = []
    for clue in challenge["clues"]:
        operands = tuple(clue[key] for key in ("a", "b", "c") if key in clue)
        constraints.append((clue["type"], operands))
    domains = [63] * 36
    if candidates is not None:
        domains = [sum(1 << column for column in range(6)
                       if candidates[obj // 6][column] & (1 << (obj % 6)))
                   for obj in range(36)]
    for given in challenge["givens"]:
        domains[given["object"]] &= 1 << given["column"]
    if contrary is not None:
        obj = contrary["row"] * 6 + contrary["item"]
        bit = 1 << contrary["column"]
        domains[obj] &= bit if contrary["kind"] == "remove" else 63 ^ bit

    def propagate(current):
        while True:
            before = tuple(current)
            for row in range(6):
                support = row_support(tuple(current[row * 6:row * 6 + 6]))
                if not all(support):
                    return False
                current[row * 6:row * 6 + 6] = support
            for name, operands in constraints:
                if name == "reference":
                    continue
                support = [0] * len(operands)
                for positions in itertools.product(*(VALUES[current[obj]] for obj in operands)):
                    valid = True
                    for i in range(len(operands)):
                        for j in range(i):
                            if operands[i] == operands[j] and positions[i] != positions[j]:
                                valid = False
                            elif operands[i] != operands[j] and operands[i] // 6 == operands[j] // 6 and positions[i] == positions[j]:
                                valid = False
                    if valid and relation(name, *positions):
                        for i, column in enumerate(positions):
                            support[i] |= 1 << column
                if not all(support):
                    return False
                for obj, mask in zip(operands, support):
                    current[obj] &= mask
                    if not current[obj]:
                        return False
            if tuple(current) == before:
                return True

    nodes = 0

    def search(current):
        nonlocal nodes
        nodes += 1
        require(nodes <= 100000, "Independent public consumer exhausted its search budget")
        if not propagate(current):
            return None
        choices = [(len(VALUES[mask]), obj) for obj, mask in enumerate(current)
                   if len(VALUES[mask]) > 1]
        if not choices:
            return current
        _, obj = min(choices)
        for column in VALUES[current[obj]]:
            branch = current.copy()
            branch[obj] = 1 << column
            solved = search(branch)
            if solved is not None:
                return solved
        return None

    solved = search(domains)
    if solved is None and allow_unsat:
        return None
    require(solved is not None, "Public challenge has no answer in independent consumer")
    answer = [[None] * 6 for _ in range(6)]
    for obj, mask in enumerate(solved):
        answer[obj // 6][VALUES[mask][0]] = obj % 6
    require(all(sorted(row) == list(range(6)) for row in answer), "Consumer built invalid row")
    return answer


def fingerprint(challenge):
    """Reconstruct the documented public checksum without native C code."""
    givens = [255] * 36
    for given in challenge["givens"]:
        givens[given["row"] * 6 + given["column"]] = given["item"]
    count = len(challenge["clues"])
    payload = bytearray(b"sherlock-public-v1")
    payload.extend((6, 6, *givens, count & 255, count >> 8))
    for clue in challenge["clues"]:
        payload.extend((CLUE_TYPES.index(clue["type"]), clue["a"],
                        clue.get("b", 255), clue.get("c", 255),
                        255 if clue["display_slot"] is None else clue["display_slot"]))
    value = 14695981039346656037
    for byte in payload:
        value = ((value ^ byte) * 1099511628211) & ((1 << 64) - 1)
    return f"{value:016x}"


def check_challenge(response):
    require(response["kind"] == "puzzle" and response["ok"] is True, "Expected challenge")
    challenge = response["challenge"]
    require((challenge["rows"], challenge["columns"], challenge["items_per_row"]) == (6, 6, 6),
            "Wrong board dimensions")
    require(set(challenge["clue_predicates"]) == set(CLUE_TYPES), "Predicate catalog incomplete")
    require(len(challenge["clues"]) <= 256, "Clue count exceeds engine bound")
    for index, clue in enumerate(challenge["clues"]):
        require(clue["index"] == index and clue["type"] in CLUE_TYPES, "Invalid ordered clue")
        arity = 1 if clue["type"] == "reference" else 3 if clue["type"] in ("between", "not_between") else 2
        require(all(type(clue[key]) is int and 0 <= clue[key] < 36
                    for key in ("a", "b", "c")[:arity]), "Invalid global object ID")
        require(all(key not in clue for key in ("a", "b", "c")[arity:]), "Extraneous clue operand")
        require(clue["display_slot"] is None or 36 <= clue["display_slot"] <= 74,
                "Invalid presentation slot")
    for given in challenge["givens"]:
        require(all(type(given[key]) is int and 0 <= given[key] < 6
                    for key in ("row", "column", "item")), "Invalid given")
        require(given["object"] == given["row"] * 6 + given["item"], "Given identity mismatch")
    expected = fingerprint(challenge)
    require(challenge["public_fingerprint"] == {"algorithm": "fnv1a64-public-v1", "hex": expected},
            "Public fingerprint disagrees with JSON content")
    require(challenge["challenge_id"].endswith(":" + expected), "Identity checksum mismatch")
    return challenge


def json_bytes(value):
    return json.dumps(value, separators=(",", ":")).encode("ascii")


def initial_state(challenge):
    state = {"candidates": [[63] * 6 for _ in range(6)], "chosen": [[-1] * 6 for _ in range(6)]}
    for given in challenge["givens"]:
        row, column, item = (given[key] for key in ("row", "column", "item"))
        state["chosen"][row][column] = item
        state["candidates"][row][column] = 1 << item
        for other in range(6):
            if other != column:
                state["candidates"][row][other] &= 63 ^ (1 << item)
    return state


def check_hint_response(response, challenge, classification):
    require(response["kind"] in ("hint", "hint_verification") and response["ok"] is True,
            "Hint result requires an ordinary successful protocol envelope")
    require(response["challenge_id"] == challenge["challenge_id"] and
            response["public_fingerprint"] == challenge["public_fingerprint"],
            "Hint is not bound to the requested canonical challenge")
    require(response["classification"] == classification and
            response["proved"] == (classification == "proved"), "Hint classification is ambiguous")
    require(response["assumptions"]["candidate_masks"] == "premises" and
            response["assumptions"]["earlier_edits_verified"] is False,
            "Player assumptions must not be presented as proved history")
    proof, record = response["proof"], response["support_record"]
    if proof is not None:
        require(int(proof["nodes_used"]) <= int(proof["node_budget"]), "Proof exceeded its node budget")
        require(proof["reduction_complete"] == (
            proof["minimality"] == "deletion_minimal_clues_relative_to_frozen_background"),
            "Minimality label disagrees with completed reduction")
    if classification != "proved":
        require(record is None, "An unproved result emitted a certified support record")
        return
    require(record["format"] == "sherlock-hint-support-1" and record["version"] == 1 and
            record["background_rule_mask"] == 1, "Unknown supporting-premise format")
    require(record["target"] == response["proposed_move"], "Support changed the selected target")
    require(record["candidates"] == response["state"]["candidates"], "Support changed candidate assumptions")
    givens = [[-1] * 6 for _ in range(6)]
    for given in challenge["givens"]:
        givens[given["row"]][given["column"]] = given["item"]
    require(record["givens"] == givens, "Support did not preserve canonical givens")
    require(record["source_clue_count"] == len(challenge["clues"]), "Source clue count mismatch")
    require(record["support_count"] == len(record["clues"]), "Support count mismatch")
    indices = [clue["index"] for clue in record["clues"]]
    require(len(set(indices)) == len(indices), "Duplicate supporting-clue identities")
    for clue in record["clues"]:
        require(0 <= clue["index"] < len(challenge["clues"]), "Support invented a clue index")
        canonical = {key: value for key, value in challenge["clues"][clue["index"]].items()
                     if key != "display_slot"}
        require(clue == canonical, "Support changed a canonical clue's relation or operands")
    reduced = {**challenge, "clues": record["clues"]}
    require(solve_public(reduced, candidates=record["candidates"], allow_unsat=True) is not None,
            "Independent consumer found inconsistent purported support")
    require(solve_public(reduced, candidates=record["candidates"], contrary=record["target"],
                         allow_unsat=True) is None,
            "Independent consumer found a completion refuting the certified target")
    if proof["reduction_complete"]:
        for index in range(len(record["clues"])):
            smaller = {**reduced, "clues": record["clues"][:index] + record["clues"][index + 1:]}
            require(solve_public(smaller, candidates=record["candidates"], contrary=record["target"],
                                 allow_unsat=True) is not None,
                    "Completed deletion pass claimed a redundant retained clue was necessary")


def check_hint_contract(harness, challenge, answer, directory):
    state = initial_state(challenge)
    state_path = directory / "state.json"
    move_path = directory / "move.json"
    state_path.write_bytes(json_bytes(state))
    hint = harness.run(["hint", "--seed", "0"])
    check_hint_response(hint, challenge, "proved")
    require(hint["state"] == state and hint["state_origin"] == "canonical_initial",
            "Initial hint state differs from public givens")
    require(hint["selection"]["node_budget"] == "20000" and hint["proof"]["node_budget"] == "20000",
            "Selector/proof budgets must be separate and documented")
    move = hint["proposed_move"]
    move_path.write_bytes(json_bytes(move))
    checked = harness.run(["check-hint", "--seed", "0", "--move", "-"], data=json_bytes(move))
    check_hint_response(checked, challenge, "proved")
    require(checked["selection"] is None and checked["proposed_move"] == move,
            "Fixed-target verification must not choose a different move")
    checked = harness.run(["check-hint", "--seed", "0", "--move", str(move_path),
                           "--state", "-"], data=json_bytes({"candidates": state["candidates"]}))
    check_hint_response(checked, challenge, "proved")
    require(checked["state"] == state and checked["state_origin"] == "submitted_assumptions",
            "Omitted chosen bookkeeping should default to canonical givens only")
    for command, payload in [
        (["hint", "--seed", "0", "--max-nodes", "0"], None),
        (["check-hint", "--seed", "0", "--move", "-", "--max-nodes", "0"], json_bytes(move)),
    ]:
        result = harness.run(command, data=payload, code=4)
        check_hint_response(result, challenge, "unresolved")
        require(result["proof"]["nodes_used"] == "0", "Zero budget performed solver work")

    # A known completion is obtained from public JSON, not private table bytes.
    # A remove claim about one of its items is a directly witnessed counterexample.
    wrong = {"kind": "remove", "row": 0, "column": 0, "item": answer[0][0]}
    refuted = harness.run(["check-hint", "--seed", "0", "--move", "-"], data=json_bytes(wrong), code=1)
    check_hint_response(refuted, challenge, "refuted")
    solved = {"candidates": [[1 << item for item in row] for row in answer], "chosen": answer}
    state_path.write_bytes(json_bytes(solved))
    no_hint = harness.run(["hint", "--seed", "0", "--state", str(state_path)])
    check_hint_response(no_hint, challenge, "none")
    require(no_hint["proposed_move"] is None and no_hint["proof"] is None,
            "Completed chosen board must not manufacture a new target")
    known = {"kind": "choose", "row": 0, "column": 0, "item": answer[0][0]}
    partial = harness.run(["check-hint", "--seed", "0", "--state", str(state_path),
                           "--move", "-", "--max-nodes", "2"], data=json_bytes(known))
    check_hint_response(partial, challenge, "proved")
    require(partial["proof"]["reduction_complete"] is False and
            partial["proof"]["minimality"] == "not_certified",
            "Budget exhaustion during reduction must keep the proof without claiming minimality")
    completed = harness.run(["check-hint", "--seed", "0", "--state", str(state_path),
                             "--move", "-"], data=json_bytes(known))
    check_hint_response(completed, challenge, "proved")
    require(completed["support_record"]["clues"] == [] and
            completed["proof"]["reduction_complete"] is True,
            "A frozen singleton premise should need no active clue")

    fixed = {(given["row"], given["column"]) for given in challenge["givens"]}
    free = next((row, column) for row in range(6) for column in range(6)
                if (row, column) not in fixed and (row, column) != (move["row"], move["column"]))
    inconsistent = copy.deepcopy(state)
    inconsistent["candidates"][free[0]][free[1]] = 0
    state_path.write_bytes(json_bytes(inconsistent))
    impossible = harness.run(["hint", "--seed", "0", "--state", str(state_path)], code=1)
    check_hint_response(impossible, challenge, "inconsistent")
    impossible = harness.run(["check-hint", "--seed", "0", "--state", str(state_path),
                              "--move", str(move_path)], code=1)
    check_hint_response(impossible, challenge, "inconsistent")
    absent = copy.deepcopy(state)
    absent["candidates"][move["row"]][move["column"]] &= 63 ^ (1 << move["item"])
    state_path.write_bytes(json_bytes(absent))
    invalid = harness.run(["check-hint", "--seed", "0", "--state", str(state_path),
                           "--move", str(move_path)], code=2)
    require(invalid["error"]["code"] == "invalid_move", "An absent target is not a candidate move")

    for given in challenge["givens"][:1]:
        changed = copy.deepcopy(state)
        changed["candidates"][given["row"]][given["column"]] = 63
        state_path.write_bytes(json_bytes(changed))
        harness.run(["hint", "--seed", "0", "--state", str(state_path)], code=2)
        changed = copy.deepcopy(state)
        changed["chosen"][given["row"]][given["column"]] = -1
        state_path.write_bytes(json_bytes(changed))
        harness.run(["hint", "--seed", "0", "--state", str(state_path)], code=2)
    mismatch = copy.deepcopy(state)
    mismatch["chosen"][free[0]][free[1]] = 0
    state_path.write_bytes(json_bytes(mismatch))
    harness.run(["hint", "--seed", "0", "--state", str(state_path)], code=2)

    raw_state, raw_move = json_bytes(state), json_bytes(move)
    bad_states = [
        b"", b"{}", b"[]", b'{"chosen":' + json_bytes(state["chosen"]) + b"}",
        raw_state + b"{}", raw_state + b"\0", raw_state[:-1] + b",}",
        b'{"candidates":' + json_bytes(state["candidates"]) + b',"accepted":true}',
        b'{"candidates":' + json_bytes(state["candidates"]) + b',"candidates":[]}',
        raw_state.replace(b'"candidates"', b'"candidates\\u0000ignored"'),
        raw_state.replace(b'"chosen"', b'"clues"'),
        raw_state.replace(b"63", b"64", 1), raw_state.replace(b"63", b"-0", 1),
        raw_state.replace(b"63", b"true", 1), raw_state.replace(b"63", b"01", 1),
        raw_state.replace(b"63", b"6e1", 1), raw_state.replace(b"63", b'"63"', 1),
        raw_state.replace(b"-1", b"-2", 1), raw_state.replace(b"-1", b"-0", 1),
        json_bytes({"candidates": state["candidates"][:5]}),
        json_bytes({"candidates": [state["candidates"][0][:5], *state["candidates"][1:]]}),
    ]
    for document in bad_states:
        result = harness.run(["hint", "--seed", "0", "--state", "-"], data=document, code=2)
        require(result["error"]["code"] == "invalid_state" and
                type(result["error"]["byte_offset"]) is int, "State parser must locate malformed input")
    syntax_move = b'{"kind":"remove","row":0,"column":0,"item":0}'
    bad_moves = [
        b"", b"{}", b"[]", syntax_move + b"{}", syntax_move + b"\0", syntax_move[:-1] + b",}",
        syntax_move[:-1] + b',"accepted":true}', syntax_move[:-1] + b',"solution":[]}',
        syntax_move[:-1] + b',"clues":[]}', syntax_move[:-1] + b',"row":0}',
        syntax_move.replace(b'"kind"', b'"kind\\u0000ignored"'),
        syntax_move.replace(b'"remove"', b'"restore"'),
        syntax_move.replace(b'"row":0', b'"row":6'), syntax_move.replace(b'"row":0', b'"row":-0'),
        syntax_move.replace(b'"row":0', b'"row":0.0'), syntax_move.replace(b'"row":0', b'"row":true'),
        syntax_move.replace(b'"row":0', b'"row":00'), syntax_move.replace(b'"row":0,', b""),
    ]
    for document in bad_moves:
        result = harness.run(["check-hint", "--seed", "0", "--move", "-"], data=document, code=2)
        require(result["error"]["code"] == "invalid_move" and
                type(result["error"]["byte_offset"]) is int, "Move parser must locate malformed input")
    # Whitespace, arbitrary field order and ASCII Unicode-escaped keys are valid.
    valid_state = b'{"chosen":' + json_bytes(state["chosen"]) + b',"cand\\u0069dates":' + json_bytes(state["candidates"]) + b"}"
    result = harness.run(["hint", "--seed", "0", "--state", "-", "--max-nodes", "0"],
                         data=b" \r\n" + valid_state + b"\t", code=4)
    check_hint_response(result, challenge, "unresolved")
    valid_move = json_bytes({key: move[key] for key in ("item", "column", "row", "kind")})
    valid_move = valid_move.replace(b'"kind"', b'"k\\u0069nd"')
    result = harness.run(["check-hint", "--seed", "0", "--move", "-", "--max-nodes", "0"],
                         data=valid_move, code=4)
    check_hint_response(result, challenge, "unresolved")
    for command, document, name in [
        (["hint", "--seed", "0", "--state", "-"], raw_state, "state"),
        (["check-hint", "--seed", "0", "--move", "-"], raw_move, "move"),
    ]:
        result = harness.run(command, data=b" " * 65537, code=2)
        require(result["error"]["code"] == name + "_too_large", "Hint input size limit missing")
        result = harness.run(command + ["--max-nodes", "0"],
                             data=document + b" " * (65536 - len(document)), code=4)
        check_hint_response(result, challenge, "unresolved")
    harness.run(["hint", "--seed", "0", "--state", str(directory / "missing-state.json")], code=3)
    harness.run(["check-hint", "--seed", "0", "--move", str(directory / "missing-move.json")], code=3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("table", type=Path, nargs="?")
    arguments = parser.parse_args()
    binary = arguments.binary.resolve(strict=True)
    table = arguments.table.resolve(strict=True) if arguments.table else None
    harness = Harness(binary)
    for command in ([], ["help"], ["--help"], ["generate", "--help"],
                    ["hint", "--help"], ["check-hint", "--help"]):
        help_response = harness.run(command)
        require(help_response["kind"] == "help", "Help must be JSON")
    version = harness.run(["version"])
    require(version["generator"] == "sherlock-native-constraints" and version["generator_version"] == 1,
            "Unexpected generator identity/version; update versioned contract intentionally")
    require(harness.run(["--version"]) == version, "Version aliases differ")

    generated = {}
    for seed in ("0", "1", "4294967296", UINT64_MAX):
        response = harness.run(["generate", "--seed", seed])
        challenge = check_challenge(response)
        generated[seed] = response
        require(challenge["source"]["kind"] == "native" and challenge["source"]["seed"] == seed,
                "Full uint64 seed must round-trip as a string")
        require("number" not in challenge["source"], "Native challenge mislabeled as original zero")
        require(response["generation"]["classification"] == "unique", "Generation lacks unique proof")
        require(harness.run(["generate", "--seed", seed]) == response,
                "Seed/version generation must be deterministic")
        answer = solve_public(challenge)
        verified = harness.run(["verify", "--seed", seed, "--solution", "-"], data=json_bytes(answer))
        require(verified["accepted"] is True and verified["challenge_id"] == challenge["challenge_id"],
                "Public-only consumer's answer was not accepted for the same challenge")
        swapped = copy.deepcopy(answer)
        swapped[0][0], swapped[0][1] = swapped[0][1], swapped[0][0]
        rejected = harness.run(["verify", "--seed", seed, "--solution", "-"], data=json_bytes(swapped), code=1)
        require(rejected["accepted"] is False and rejected["reason"], "Incorrect row swap accepted")
        analyzed = harness.run(["analyze", "--seed", seed])
        require(analyzed["classification"] == "unique" and analyzed["solutions_found"] == 1
                and analyzed["solution_count_is_exact"] is True
                and analyzed["challenge_id"] == challenge["challenge_id"], "Incorrect analysis")
    require(generated["0"]["challenge"]["public_fingerprint"] !=
            generated["4294967296"]["challenge"]["public_fingerprint"], "Upper seed bits ignored")
    require(harness.run(["generate", "--seed", "0000"]) == generated["0"], "Seed is not canonicalized")

    answer = solve_public(generated["0"]["challenge"])
    raw_answer = json_bytes(answer)
    for document in (json_bytes({"solution": answer}), b'{"sol\\u0075tion":' + raw_answer + b'}',
                     b" \r\n\t" + raw_answer.replace(b",", b", \r\n\t") + b"\r\n"):
        require(harness.run(["verify", "--seed", "0", "--solution", "-"], data=document)["accepted"],
                "Supported answer document rejected")
    repeated = copy.deepcopy(answer)
    repeated[0][1] = repeated[0][0]
    require(harness.run(["verify", "--seed", "0", "--solution", "-"],
                        data=json_bytes(repeated), code=1)["accepted"] is False,
            "Non-permutation row accepted")
    unknown = harness.run(["analyze", "--seed", "0", "--max-nodes", "0"], code=4)
    require(unknown["classification"] == "unknown" and unknown["solution_count_is_exact"] is False,
            "Exhaustion must not be reported as UNSAT or unique")
    require(harness.run(["analyze", "--seed", "0", "--max-nodes", UINT64_MAX])["node_budget"] == UINT64_MAX,
            "Full-width node budget failed")

    bad_arguments = [
        ["unknown"], ["help", "extra"], ["version", "extra"], ["puzzle"],
        ["generate"], ["generate", "--seed"], ["generate", "--seed", "0", "extra"],
        ["generate", "--seed=0"], ["generate", "--seed", "0", "--unknown", "1"],
        ["generate", "--seed", "0", "--seed", "1"],
        ["generate", "--seed", "0", "--number", "0"], ["puzzle", "--seed", "0"],
        ["generate", "--number", "0"], ["puzzle", "--number", "65536"],
        ["generate", "--seed", "0", "--data", "ignored"],
        ["generate", "--seed", "0", "--max-nodes", "1"],
        ["generate", "--seed", "0", "--solution", "-"], ["verify", "--seed", "0"],
        ["verify", "--seed", "0", "--solution", ""],
        ["verify", "--seed", "0", "--solution", "-", "--solution", "-"],
        ["analyze", "--seed", "0", "--max-nodes", "1", "--max-nodes", "2"],
        ["puzzle", "--number", "0", "--data", ""],
        ["puzzle", "--number", "0", "--data", "a", "--data", "b"],
        ["hint"], ["hint", "--seed", "0", "--move", "-"],
        ["hint", "--seed", "0", "--state", ""],
        ["hint", "--seed", "0", "--state", "a", "--state", "b"],
        ["hint", "--seed", "0", "--max-nodes", str(int(help_response["hint_node_maximum"]) + 1)],
        ["hint", "--seed", "0", "--max-nodes", "1", "--max-nodes", "2"],
        ["hint", "--seed", "0", "--solution", "-"],
        ["check-hint", "--seed", "0"], ["check-hint", "--seed", "0", "--move", ""],
        ["check-hint", "--seed", "0", "--move", "a", "--move", "b"],
        ["check-hint", "--seed", "0", "--move", "-", "--state", "-"],
        ["analyze", "--seed", "0", "--state", "-"],
        ["generate", "--seed", "0", "--move", "-"],
    ]
    for bad in ("", "-1", "+1", " 1", "1 ", "1.0", "1e0", "0x10", "1junk", "18446744073709551616"):
        bad_arguments.append(["generate", "--seed", bad])
        bad_arguments.append(["analyze", "--seed", "0", "--max-nodes", bad])
    for command in bad_arguments:
        harness.run(command, code=2)

    malformed = [
        b"", b"[", b"[]", json_bytes(answer[:5]), json_bytes(answer + [answer[0]]),
        json_bytes([answer[0][:5], *answer[1:]]), json_bytes([answer[0] + [0], *answer[1:]]),
        b"/*comment*/" + raw_answer, raw_answer + b"garbage", raw_answer + raw_answer,
        raw_answer[:-1] + b",]", b"```json\n" + raw_answer + b"\n```",
        b"\xef\xbb\xbf" + raw_answer, raw_answer + b"\0", b"\0" + raw_answer,
        b'{"solution":' + raw_answer + b',"accepted":true}',
        b'{"solution":' + raw_answer + b',"solution":' + raw_answer + b'}',
        b'{"solution":' + raw_answer + b',}', b'{"solution ":' + raw_answer + b'}',
        b'{"sol\\u00zztion":' + raw_answer + b'}', b'{"Solution":' + raw_answer + b'}',
        b'{"solution":' + raw_answer + b'} {}', b"true", b"null",
    ]
    # Replace the first item while keeping all remaining syntax and dimensions.
    for token in (b"6", b"-1", b"-0", b"true", b"null", b'"0"', b"1.0", b"1e0", b"01", b"999999999999999999999999999999"):
        malformed.append(b"[[" + token + raw_answer[3:])
    for document in malformed:
        response = harness.run(["verify", "--seed", "0", "--solution", "-"], data=document, code=2)
        require(response["error"]["code"] == "invalid_answer" and
                type(response["error"]["byte_offset"]) is int, "Parser failure needs a byte offset")
    too_large = harness.run(["verify", "--seed", "0", "--solution", "-"], data=b" " * 65537, code=2)
    require(too_large["error"]["code"] == "answer_too_large", "Answer size limit missing")
    # Exactly 64 KiB of a valid document plus legal whitespace is supported.
    padded = raw_answer + b" " * (65536 - len(raw_answer))
    require(harness.run(["verify", "--seed", "0", "--solution", "-"], data=padded)["accepted"],
            "Inclusive answer size boundary is wrong")

    with tempfile.TemporaryDirectory(prefix="sherlock-cli-test-") as temporary:
        directory = Path(temporary)
        missing = str(directory / "missing-table.bin")
        require(harness.run(["generate", "--seed", "0"], cwd=directory,
                            environment={"SHERLOCK_PUZZLE_TABLE": missing}) == generated["0"],
                "Native generation has an original-table dependency")
        harness.run(["puzzle", "--number", "0", "--data", missing], code=3)
        harness.run(["verify", "--seed", "0", "--solution", str(directory / "missing.json")], code=3)
        unusual_file = directory / 'answer-é-"-\\.json'
        unusual_file.write_bytes(raw_answer)
        require(harness.run(["verify", "--seed", "0", "--solution", str(unusual_file)])["accepted"],
                "Valid Unicode/quoted path failed")
        check_hint_contract(harness, generated["0"]["challenge"], answer, directory)
        if os.name == "posix":
            response = harness.run([b"bad-\xff-command"], code=2)
            require(response["error"]["argument"] == "bad-ÿ-command", "Invalid UTF-8 diagnostic escaped incorrectly")

        if table:
            for number in (0, 235, 11656, 65535):
                response = harness.run(["puzzle", "--number", str(number), "--data", str(table)])
                challenge = check_challenge(response)
                require(challenge["source"]["kind"] == "original" and challenge["source"]["number"] == number,
                        "Original identity mismatch")
                require("generation" not in response, "Original puzzle mislabeled as native generation")
                original_answer = solve_public(challenge)
                verified = harness.run(["verify", "--number", str(number), "--data", str(table), "--solution", "-"],
                                       data=json_bytes(original_answer))
                require(verified["accepted"] and verified["challenge_id"] == challenge["challenge_id"],
                        "Original public challenge did not round-trip")
            expected = harness.run(["puzzle", "--number", "0", "--data", str(table)])
            original_hint = harness.run(["hint", "--number", "0", "--data", str(table)])
            check_hint_response(original_hint, expected["challenge"], "proved")
            require(harness.run(["puzzle", "--number", "0", "--data", str(table)],
                                environment={"SHERLOCK_PUZZLE_TABLE": missing}) == expected,
                    "Explicit --data must take precedence over environment")
            require(harness.run(["puzzle", "--number", "0"], cwd=directory,
                                environment={"SHERLOCK_PUZZLE_TABLE": str(table)}) == expected,
                    "Environment table override failed")
            corrupt = directory / "corrupt-table.bin"
            corrupt.write_bytes(b"This is not a Sherlock puzzle table.\n")
            harness.run(["puzzle", "--number", "0", "--data", str(corrupt)], code=3,
                        environment={"SHERLOCK_PUZZLE_TABLE": str(table)})
            # Copy the executable so discovery depends on its actual new path.
            (directory / "bin").mkdir()
            (directory / "Resources").mkdir()
            installed = directory / "bin" / "sherlock-cli"
            shutil.copy2(binary, installed)
            os.symlink(table, directory / "Resources" / "sherlock_puzzles.bin")
            require(harness.run(["puzzle", "--number", "0"], binary=installed, cwd=directory) == expected,
                    "Executable-relative ../Resources discovery failed")
    print(f"CLI contract tests passed: {harness.calls} invocations; public-only answer consumer; "
          f"original-table tests {'included' if table else 'not requested'}.")


if __name__ == "__main__":
    main()
