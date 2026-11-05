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


def solve_public(challenge):
    """Independent, bounded finite-domain consumer of the documented JSON."""
    constraints = []
    for clue in challenge["clues"]:
        operands = tuple(clue[key] for key in ("a", "b", "c") if key in clue)
        constraints.append((clue["type"], operands))
    domains = [63] * 36
    for given in challenge["givens"]:
        domains[given["object"]] &= 1 << given["column"]

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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("table", type=Path, nargs="?")
    arguments = parser.parse_args()
    binary = arguments.binary.resolve(strict=True)
    table = arguments.table.resolve(strict=True) if arguments.table else None
    harness = Harness(binary)
    for command in ([], ["help"], ["--help"], ["generate", "--help"]):
        require(harness.run(command)["kind"] == "help", "Help must be JSON")
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
