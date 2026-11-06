/*
 * Portable JavaScript realization of the authored Sherlock native core.
 *
 * Behavioral reference: core/sherlock_logic.c and the public JSON helpers in
 * cli/sherlock_cli.c. This file contains no original executable or game data.
 * Solver and verifier read only givens and public clue relations. In particular,
 * they never consult a puzzle's optional generator-owned solution field.
 *
 * Generator version 1 includes the exact SplitMix64 arithmetic, random-call
 * order, search order, scoring and pruning policy of the native C generator.
 * Changing any of those requires a new version, not a silent seed remapping.
 */
(function (root, factory) {
    "use strict";
    if (typeof module === "object" && module.exports) module.exports = factory();
    else root.SherlockCore = factory();
}(typeof globalThis !== "undefined" ? globalThis : this, function () {
    "use strict";

    const SIZE = 6;
    const OBJECTS = 36;
    const ALL_COLUMNS = 63;
    const MAX_CLUES = 256;
    const U64_MAX = (1n << 64n) - 1n;
    const GENERATOR_ID = "sherlock-native-constraints";
    const GENERATOR_VERSION = 1;
    const DEFAULT_SOLVE_NODES = "200000";
    const DEFAULT_GENERATE_LIMITS = Object.freeze({
        node_budget: "1000000", max_attempts: 16, max_givens: 3
    });
    const RELATIONS = Object.freeze({
        SAME_COLUMN: 0, NOT_SAME_COLUMN: 1, NEXT_TO: 2, NOT_NEXT_TO: 3,
        LEFT_OF: 4, BETWEEN: 5, NOT_BETWEEN: 6, UNUSED: 7
    });
    const CLUE_NAMES = Object.freeze([
        "same_column", "not_same_column", "next_to", "not_next_to",
        "left_of", "between", "not_between", "reference"
    ]);
    const CLASSIFICATIONS = Object.freeze({
        "-1": "error", "0": "unsat", "1": "unique",
        "2": "multiple", "3": "unknown"
    });
    const ANSWER_FORMAT = Object.freeze({
        layout: "answer[row][column] = within-row item ID",
        item_minimum: 0,
        item_maximum: 5,
        row_constraint: "each row is a permutation of 0..5"
    });
    const OBJECT_IDS = Object.freeze({
        minimum: 0,
        maximum: 35,
        formula: "row * 6 + item",
        inverse_row: "id / 6 (integer division)",
        inverse_item: "id % 6"
    });
    const COLUMN_FUNCTION = "col(object) is its zero-based column in the submitted answer";
    const CLUE_PREDICATES = Object.freeze({
        same_column: "col(a) == col(b)",
        not_same_column: "col(a) != col(b)",
        next_to: "abs(col(a)-col(b)) == 1",
        not_next_to: "abs(col(a)-col(b)) != 1",
        left_of: "col(a) < col(b)",
        between: "abs(col(a)-col(c)) == 2 && 2*col(b) == col(a)+col(c)",
        not_between: "abs(col(a)-col(c)) == 2 && 2*col(b) != col(a)+col(c)",
        reference: "true (informational object only)"
    });

    function integer(value, low, high) {
        return Number.isSafeInteger(value) && value >= low && value <= high;
    }

    function matrix(value, low, high) {
        if (!Array.isArray(value) || value.length !== SIZE) return false;
        // Array#every skips holes. Explicit iteration must reject sparse input.
        for (const row of value) {
            if (!Array.isArray(row) || row.length !== SIZE) return false;
            for (const item of row) if (!integer(item, low, high)) return false;
        }
        return true;
    }

    function filledMatrix(value) {
        return Array.from({ length: SIZE }, function () {
            return Array(SIZE).fill(value);
        });
    }

    function copyMatrix(value) {
        return value.map(function (row) { return row.slice(); });
    }

    function unsigned64(value, label) {
        let result;
        if (typeof value === "bigint") result = value;
        else if (typeof value === "number" && Number.isSafeInteger(value)) result = BigInt(value);
        else if (typeof value === "string" && value.length <= 128 && /^[0-9]+$/.test(value)) {
            result = BigInt(value);
        } else throw new TypeError((label || "Value") + " must be an exact unsigned decimal integer.");
        if (result < 0n || result > U64_MAX) {
            throw new RangeError((label || "Value") + " must fit an unsigned 64-bit integer.");
        }
        return result;
    }

    function canonicalDecimal(value, label) {
        if (typeof value !== "string" || !/^(0|[1-9][0-9]{0,19})$/.test(value)) {
            throw new TypeError(label + " must be a canonical decimal JSON string.");
        }
        return unsigned64(value, label).toString();
    }

    function bitCount(value) {
        value &= ALL_COLUMNS;
        value -= (value >> 1) & 0x55;
        value = (value & 0x33) + ((value >> 2) & 0x33);
        return (value + (value >> 4)) & 15;
    }

    function firstColumn(mask) {
        let column = 0;
        while (column < SIZE && !(mask & (1 << column))) ++column;
        return column;
    }

    function clueArity(type) {
        return type === RELATIONS.UNUSED ? 1 :
            type === RELATIONS.BETWEEN || type === RELATIONS.NOT_BETWEEN ? 3 : 2;
    }

    function relationHolds(type, a, b, c) {
        // Reference cards make no logical assertion, exactly as in the C core.
        if (type === RELATIONS.UNUSED) return true;
        if (!integer(type, 0, 7) || !integer(a, 0, 5) || !integer(b, 0, 5)) return false;
        if (clueArity(type) === 3 && !integer(c, 0, 5)) return false;
        const ab = Math.abs(a - b);
        const ac = clueArity(type) === 3 ? Math.abs(a - c) : 0;
        switch (type) {
            case RELATIONS.SAME_COLUMN: return a === b;
            case RELATIONS.NOT_SAME_COLUMN: return a !== b;
            case RELATIONS.NEXT_TO: return ab === 1;
            case RELATIONS.NOT_NEXT_TO: return ab !== 1;
            case RELATIONS.LEFT_OF: return a < b;
            case RELATIONS.BETWEEN: return ac === 2 && 2 * b === a + c;
            // NOT_BETWEEN still constrains the outer pair to distance two.
            case RELATIONS.NOT_BETWEEN: return ac === 2 && 2 * b !== a + c;
            default: return false;
        }
    }

    function validatePuzzle(puzzle) {
        // Do not enumerate, copy or otherwise touch the optional hidden answer.
        if (!puzzle || typeof puzzle !== "object") {
            return { valid: false, reason: "No puzzle was supplied." };
        }
        if (!Array.isArray(puzzle.clues) || puzzle.clues.length > MAX_CLUES ||
                (puzzle.clue_count !== undefined && puzzle.clue_count !== puzzle.clues.length)) {
            return { valid: false, reason: "The clue count exceeds the supported capacity or disagrees with the clue array." };
        }
        if (!matrix(puzzle.given, -1, 5)) {
            return { valid: false, reason: "A given contains an invalid item index or the matrix is not six by six." };
        }
        for (let i = 0; i < puzzle.clues.length; ++i) {
            const clue = puzzle.clues[i];
            if (!clue || typeof clue !== "object" ||
                    !integer(clue.type, 0, 7) || !integer(clue.a, 0, 35) ||
                    (clue.type !== RELATIONS.UNUSED && !integer(clue.b, 0, 35)) ||
                    (clueArity(clue.type) === 3 && !integer(clue.c, 0, 35))) {
                return { valid: false, reason: "Clue " + i + " has an invalid relation or object reference." };
            }
        }
        return { valid: true, reason: "" };
    }

    function verifyAnswer(puzzle, answer) {
        const result = { status: -1, row: -1, column: -1, clue_index: -1, reason: "" };
        const validation = validatePuzzle(puzzle);
        if (!validation.valid) { result.reason = validation.reason; return result; }
        if (!Array.isArray(answer) || answer.length !== SIZE ||
                Array.from(answer).some(function (row) { return !Array.isArray(row) || row.length !== SIZE; })) {
            result.reason = "No complete six-by-six answer was supplied.";
            return result;
        }
        const position = new Uint8Array(OBJECTS);
        result.status = 0;
        for (let row = 0; row < SIZE; ++row) {
            let seen = 0;
            for (let column = 0; column < SIZE; ++column) {
                const item = answer[row][column];
                if (!integer(item, 0, 5) || (seen & (1 << item))) {
                    result.row = row;
                    result.column = column;
                    result.reason = "Each row must contain all six item indices exactly once.";
                    return result;
                }
                seen |= 1 << item;
                position[row * SIZE + item] = column;
            }
        }
        for (let row = 0; row < SIZE; ++row) for (let column = 0; column < SIZE; ++column) {
            const given = puzzle.given[row][column];
            if (given >= 0 && answer[row][column] !== given) {
                result.row = row;
                result.column = column;
                result.reason = "The answer disagrees with a given square.";
                return result;
            }
        }
        for (let i = 0; i < puzzle.clues.length; ++i) {
            const clue = puzzle.clues[i];
            if (clue.type === RELATIONS.UNUSED) continue;
            if (!relationHolds(clue.type, position[clue.a], position[clue.b],
                    clueArity(clue.type) === 3 ? position[clue.c] : 0)) {
                result.clue_index = i;
                result.reason = "Clue " + i + " does not hold for this answer.";
                return result;
            }
        }
        result.status = 1;
        result.reason = "All rows, givens, and clue relations are satisfied.";
        return result;
    }

    function compatible(a, b, ca, cb) {
        if (a === b) return ca === cb;
        return Math.floor(a / SIZE) !== Math.floor(b / SIZE) || ca !== cb;
    }

    function prepareSearch(puzzle, budget, result) {
        const search = {
            puzzle: puzzle, budget: budget, result: result,
            nodes: 0n, degree: new Uint16Array(OBJECTS),
            constraints: [], exhausted: false, error: false
        };
        for (const clue of puzzle.clues) {
            if (clue.type === RELATIONS.UNUSED) continue;
            const arity = clueArity(clue.type);
            const constraint = { object: [clue.a, clue.b, clue.c], arity: arity, tuples: [] };
            ++search.degree[clue.a];
            ++search.degree[clue.b];
            if (arity === 3) ++search.degree[clue.c];
            for (let a = 0; a < SIZE; ++a) for (let b = 0; b < SIZE; ++b) {
                if (!compatible(clue.a, clue.b, a, b)) continue;
                for (let c = 0; c < (arity === 3 ? SIZE : 1); ++c) {
                    if (arity === 3 && (!compatible(clue.a, clue.c, a, c) ||
                            !compatible(clue.b, clue.c, b, c))) continue;
                    if (relationHolds(clue.type, a, b, c)) constraint.tuples.push([a, b, c]);
                }
            }
            search.constraints.push(constraint);
        }
        return search;
    }

    function propagate(search, domains) {
        let changed;
        do {
            changed = false;
            for (let i = 0; i < OBJECTS; ++i) if (!domains[i]) return false;
            // Every Hall subset is feasible to visit for a row of only six items.
            for (let row = 0; row < SIZE; ++row) {
                for (let subset = 1; subset < 64; ++subset) {
                    let places = 0;
                    const count = bitCount(subset);
                    for (let item = 0; item < SIZE; ++item) {
                        if (subset & (1 << item)) places |= domains[row * SIZE + item];
                    }
                    const placeCount = bitCount(places);
                    if (placeCount < count) return false;
                    if (placeCount !== count) continue;
                    for (let item = 0; item < SIZE; ++item) if (!(subset & (1 << item))) {
                        const object = row * SIZE + item;
                        const old = domains[object];
                        domains[object] &= ~places;
                        if (!domains[object]) return false;
                        if (domains[object] !== old) changed = true;
                    }
                }
            }
            for (const constraint of search.constraints) {
                const supported = [0, 0, 0];
                for (const tuple of constraint.tuples) {
                    let k;
                    for (k = 0; k < constraint.arity; ++k) {
                        if (!(domains[constraint.object[k]] & (1 << tuple[k]))) break;
                    }
                    if (k < constraint.arity) continue;
                    for (k = 0; k < constraint.arity; ++k) supported[k] |= 1 << tuple[k];
                }
                for (let k = 0; k < constraint.arity; ++k) {
                    const object = constraint.object[k];
                    const old = domains[object];
                    domains[object] &= supported[k];
                    if (!domains[object]) return false;
                    if (old !== domains[object]) changed = true;
                }
            }
        } while (changed);
        return true;
    }

    function countSolutions(search, domains) {
        const result = search.result;
        if (result.solution_count >= 2 || search.error || search.exhausted) return;
        if (search.nodes === search.budget) { search.exhausted = true; return; }
        ++search.nodes;
        if (!propagate(search, domains)) return;
        let object = OBJECTS;
        let smallest = 7;
        let degree = 0;
        for (let i = 0; i < OBJECTS; ++i) {
            const count = bitCount(domains[i]);
            if (count > 1 && (count < smallest || (count === smallest && search.degree[i] > degree))) {
                object = i;
                smallest = count;
                degree = search.degree[i];
            }
        }
        if (object === OBJECTS) {
            const answer = filledMatrix(255);
            for (let i = 0; i < OBJECTS; ++i) {
                answer[Math.floor(i / SIZE)][firstColumn(domains[i])] = i % SIZE;
            }
            if (verifyAnswer(search.puzzle, answer).status !== 1) {
                search.error = true;
                return;
            }
            if (result.solution_count === 0) result.first_solution = answer;
            else result.second_solution = answer;
            ++result.solution_count;
            return;
        }
        for (let column = 0; column < SIZE; ++column) if (domains[object] & (1 << column)) {
            const child = domains.slice();
            child[object] = 1 << column;
            countSolutions(search, child);
            if (result.solution_count >= 2 || search.exhausted || search.error) return;
        }
    }

    function analyze(puzzle, nodeBudget) {
        const result = {
            status: -1, classification: "error", solution_count: 0, nodes: "0",
            first_solution: filledMatrix(0), second_solution: filledMatrix(0), reason: ""
        };
        const validation = validatePuzzle(puzzle);
        if (!validation.valid) { result.reason = validation.reason; return result; }
        let budget;
        try { budget = unsigned64(nodeBudget === undefined ? DEFAULT_SOLVE_NODES : nodeBudget, "Node budget"); }
        catch (error) { result.reason = error.message; return result; }
        const domains = new Uint8Array(OBJECTS).fill(ALL_COLUMNS);
        for (let row = 0; row < SIZE; ++row) for (let column = 0; column < SIZE; ++column) {
            const item = puzzle.given[row][column];
            if (item >= 0) domains[row * SIZE + item] &= 1 << column;
        }
        const search = prepareSearch(puzzle, budget, result);
        countSolutions(search, domains);
        result.nodes = search.nodes.toString();
        if (search.error) {
            result.status = -1;
            result.reason = "A solver completion failed independent answer validation.";
        } else if (result.solution_count >= 2) {
            result.status = 2;
            result.reason = "At least two distinct answers satisfy the visible constraints.";
        } else if (search.exhausted) {
            result.status = 3;
            result.reason = "The node budget expired before solution multiplicity was proved.";
        } else if (result.solution_count === 1) {
            result.status = 1;
            result.reason = "Exactly one answer satisfies the visible constraints.";
        } else {
            result.status = 0;
            result.reason = "No answer satisfies all givens and clue relations.";
        }
        result.classification = CLASSIFICATIONS[String(result.status)];
        return result;
    }

    function randomWord(random) {
        random.state = (random.state + 0x9e3779b97f4a7c15n) & U64_MAX;
        let value = random.state;
        value = ((value ^ (value >> 30n)) * 0xbf58476d1ce4e5b9n) & U64_MAX;
        value = ((value ^ (value >> 27n)) * 0x94d049bb133111ebn) & U64_MAX;
        return value ^ (value >> 31n);
    }

    function randomBelow(random, bound) {
        return Number(randomWord(random) % BigInt(bound));
    }

    function shuffle(values, random) {
        let count = values.length;
        while (count > 1) {
            const other = randomBelow(random, count);
            const value = values[count - 1];
            values[count - 1] = values[other];
            values[other] = value;
            --count;
        }
    }

    function positions(answer) {
        const output = new Uint8Array(OBJECTS);
        for (let row = 0; row < SIZE; ++row) for (let column = 0; column < SIZE; ++column) {
            output[row * SIZE + answer[row][column]] = column;
        }
        return output;
    }

    function sameAnswer(left, right) {
        for (let row = 0; row < SIZE; ++row) for (let column = 0; column < SIZE; ++column) {
            if (left[row][column] !== right[row][column]) return false;
        }
        return true;
    }

    function clueHolds(clue, position) {
        return relationHolds(clue.type, position[clue.a], position[clue.b],
            clueArity(clue.type) === 3 ? position[clue.c] : 0);
    }

    function makePool(position) {
        const pool = [];
        for (let a = 0; a < OBJECTS; ++a) for (let b = a + 1; b < OBJECTS; ++b) {
            for (let type = 0; type < 4; ++type) {
                if (type < 2 && Math.floor(a / SIZE) === Math.floor(b / SIZE)) continue;
                if (relationHolds(type, position[a], position[b], 0)) {
                    pool.push({ type: type, a: a, b: b, c: 255 });
                }
            }
            if (position[a] < position[b]) pool.push({ type: 4, a: a, b: b, c: 255 });
            else if (position[b] < position[a]) pool.push({ type: 4, a: b, b: a, c: 255 });
        }
        for (let a = 0; a < OBJECTS; ++a) for (let c = a + 1; c < OBJECTS; ++c) {
            const distance = position[a] - position[c];
            if (distance !== -2 && distance !== 2) continue;
            for (let b = 0; b < OBJECTS; ++b) {
                if (b === a || b === c) continue;
                const type = position[b] * 2 === position[a] + position[c] ? 5 : 6;
                pool.push({ type: type, a: a, b: b, c: c });
            }
        }
        return pool;
    }

    function normalizedLimits(limits) {
        if (limits === undefined || limits === null) return Object.assign({}, DEFAULT_GENERATE_LIMITS);
        assertKeys(limits, ["node_budget", "max_attempts", "max_givens"], [], "Generation limits");
        const nodeBudget = unsigned64(limits.node_budget, "Generation node budget").toString();
        if (!integer(limits.max_attempts, 0, 64) || !integer(limits.max_givens, 0, 3)) {
            throw new RangeError("Invalid generation output or limits (at most 3 givens and 64 attempts).");
        }
        return { node_budget: nodeBudget, max_attempts: limits.max_attempts, max_givens: limits.max_givens };
    }

    function generate(seedInput, suppliedLimits) {
        const report = {
            status: -1, seed: "0", version: GENERATOR_VERSION,
            attempts: 0, nodes: "0", clue_count: 0, given_count: 0, proof: 3, reason: ""
        };
        let seed;
        let limits;
        try {
            seed = unsigned64(seedInput, "Seed");
            report.seed = seed.toString();
            limits = normalizedLimits(suppliedLimits);
        } catch (error) {
            report.reason = error.message;
            return { status: -1, report: report };
        }
        let remaining = BigInt(limits.node_budget);
        let used = 0n;
        const random = { state: seed ^ 0x534845524c4f434bn };
        const information = [18, 2, 12, 4, 8, 22, 16];
        function finish(status, reason, puzzle) {
            report.status = status;
            report.nodes = used.toString();
            report.reason = reason;
            const output = { status: status, report: report };
            if (status === 0) output.puzzle = puzzle;
            return output;
        }
        function solve(puzzle) {
            puzzle.clue_count = puzzle.clues.length;
            const slice = remaining < 20000n ? remaining : 20000n;
            const solved = analyze(puzzle, slice);
            const nodes = BigInt(solved.nodes);
            remaining -= nodes;
            used += nodes;
            return solved;
        }
        if (remaining === 0n || limits.max_attempts === 0) {
            return finish(1, "The generation budget permits no work.");
        }
        for (let attempt = 0; attempt < limits.max_attempts && remaining !== 0n; ++attempt) {
            const puzzle = {
                number: 0, given: filledMatrix(-1), clue_count: 0,
                clues: [], original_slot: []
            };
            const target = filledMatrix(0);
            const rows = [0, 1, 2, 3, 4, 5];
            const groupCount = [0, 0];
            const typeCount = [0, 0, 0, 0, 0, 0, 0];
            report.attempts = attempt + 1;
            for (let row = 0; row < SIZE; ++row) {
                for (let column = 0; column < SIZE; ++column) target[row][column] = column;
                shuffle(target[row], random);
            }
            const targetPosition = positions(target);
            shuffle(rows, random);
            const givens = limits.max_givens ? 1 + randomBelow(random, limits.max_givens) : 0;
            for (let i = 0; i < givens; ++i) {
                const row = rows[i];
                const column = randomBelow(random, SIZE);
                puzzle.given[row][column] = target[row][column];
            }
            const pool = makePool(targetPosition);
            if (pool.length > 8192) return finish(-1, "The bounded clue pool overflowed.");
            const active = new Uint8Array(pool.length);
            let proved = false;
            for (;;) {
                const solved = solve(puzzle);
                if (solved.status === -1 || solved.status === 0) {
                    return finish(-1, "True target clues produced an inconsistent constraint problem.");
                }
                if (solved.status === 1 && puzzle.clues.length >= 12) {
                    proved = true;
                    break;
                }
                if (remaining === 0n || puzzle.clues.length === 39) break;
                const alternatives = [];
                if (solved.solution_count > 0 && !sameAnswer(solved.first_solution, target)) {
                    alternatives.push(positions(solved.first_solution));
                }
                if (solved.solution_count > 1 && !sameAnswer(solved.second_solution, target)) {
                    alternatives.push(positions(solved.second_solution));
                }
                let best = -1;
                let bestScore = -10000;
                for (let i = 0; i < pool.length; ++i) {
                    const clue = pool[i];
                    const group = clue.type < 2 ? 0 : 1;
                    if (active[i] || groupCount[group] === (group ? 21 : 18)) continue;
                    let cuts = 0;
                    for (const alternative of alternatives) if (!clueHolds(clue, alternative)) ++cuts;
                    if (alternatives.length && cuts === 0) continue;
                    const score = 128 * cuts + (typeCount[clue.type] ? 0 : 32) +
                        information[clue.type] - 2 * typeCount[clue.type] +
                        randomBelow(random, 16);
                    if (score > bestScore) { best = i; bestScore = score; }
                }
                if (best < 0) break;
                puzzle.clues.push(pool[best]);
                active[best] = 1;
                ++typeCount[pool[best].type];
                ++groupCount[pool[best].type < 2 ? 0 : 1];
            }
            if (!proved) continue;
            // A smaller budget must never silently return a different success.
            for (let i = puzzle.clues.length; i > 0 && puzzle.clues.length > 12; --i) {
                const index = i - 1;
                const saved = puzzle.clues[index];
                const available = remaining;
                puzzle.clues.splice(index, 1);
                const solved = solve(puzzle);
                if (solved.status !== 1) puzzle.clues.splice(index, 0, saved);
                if (solved.status === 3 && available < 20000n) {
                    return finish(1, "The total solver-node budget expired during clue pruning; no puzzle was returned.");
                }
                if (solved.status === -1 || solved.status === 0) {
                    return finish(-1, "Removing a clue violated the known satisfiable target.");
                }
            }
            for (let row = 0; row < SIZE; ++row) for (let column = 0; column < SIZE; ++column) {
                const saved = puzzle.given[row][column];
                if (saved < 0) continue;
                const available = remaining;
                puzzle.given[row][column] = -1;
                const solved = solve(puzzle);
                if (solved.status !== 1) puzzle.given[row][column] = saved;
                if (solved.status === 3 && available < 20000n) {
                    return finish(1, "The total solver-node budget expired during given pruning; no puzzle was returned.");
                }
                if (solved.status === -1 || solved.status === 0) {
                    return finish(-1, "Removing a given violated the known satisfiable target.");
                }
            }
            puzzle.clue_count = puzzle.clues.length;
            if (verifyAnswer(puzzle, target).status !== 1) {
                return finish(-1, "The generated target failed answer validation.");
            }
            puzzle.solution = copyMatrix(target);
            groupCount[0] = groupCount[1] = 0;
            const ordered = puzzle.clues.map(function (clue, index) {
                const group = clue.type < 2 ? 0 : 1;
                return {
                    clue: clue, index: index,
                    slot: (group ? 54 : 36) + groupCount[group]++
                };
            });
            ordered.sort(function (a, b) { return a.slot - b.slot || a.index - b.index; });
            puzzle.clues = ordered.map(function (item) { return item.clue; });
            puzzle.original_slot = ordered.map(function (item) { return item.slot; });
            report.given_count = puzzle.given.reduce(function (sum, row) {
                return sum + row.filter(function (value) { return value >= 0; }).length;
            }, 0);
            report.clue_count = puzzle.clue_count;
            report.proof = 1;
            puzzle.source = {
                kind: "native", generator: GENERATOR_ID, generator_version: GENERATOR_VERSION,
                seed: report.seed, limits: Object.assign({}, limits)
            };
            puzzle.generation = { classification: "unique", attempts: report.attempts, nodes: used.toString() };
            puzzle.public_fingerprint = { algorithm: "fnv1a64-public-v1", hex: publicFingerprint(puzzle) };
            puzzle.challenge_id = challengeId(puzzle.source, puzzle.public_fingerprint.hex);
            return finish(0, "A unique native puzzle was proved from its visible constraints.", puzzle);
        }
        return finish(1, remaining !== 0n ?
            "The attempt limit was reached before a display-sized unique puzzle was proved." :
            "The total solver-node budget was exhausted; no puzzle was returned.");
    }

    function publicFingerprint(puzzle) {
        const validation = validatePuzzle(puzzle);
        if (!validation.valid) throw new TypeError(validation.reason);
        let hash = 14695981039346656037n;
        function add(value) {
            hash = ((hash ^ BigInt(value & 255)) * 1099511628211n) & U64_MAX;
        }
        for (const char of "sherlock-public-v1") add(char.charCodeAt(0));
        add(SIZE);
        add(SIZE);
        for (let row = 0; row < SIZE; ++row) for (let column = 0; column < SIZE; ++column) {
            add(puzzle.given[row][column] < 0 ? 255 : puzzle.given[row][column]);
        }
        add(puzzle.clues.length & 255);
        add(puzzle.clues.length >> 8);
        for (let i = 0; i < puzzle.clues.length; ++i) {
            const clue = puzzle.clues[i];
            const arity = clueArity(clue.type);
            const slot = puzzle.original_slot && puzzle.original_slot[i];
            add(clue.type);
            add(clue.a);
            add(arity >= 2 ? clue.b : 255);
            add(arity === 3 ? clue.c : 255);
            add(integer(slot, 36, 74) ? slot : 255);
        }
        return hash.toString(16).padStart(16, "0");
    }

    function plainObject(value) {
        if (!value || typeof value !== "object" || Array.isArray(value)) return false;
        const prototype = Object.getPrototypeOf(value);
        return prototype === Object.prototype || prototype === null;
    }

    function assertKeys(value, required, optional, label) {
        if (!plainObject(value)) throw new TypeError(label + " must be a plain JSON object.");
        const allowed = new Set(required.concat(optional || []));
        for (const key of Reflect.ownKeys(value)) {
            if (!allowed.has(key)) throw new TypeError(label + " has an unsupported field: " + String(key) + ".");
        }
        for (const key of required) {
            if (!Object.prototype.hasOwnProperty.call(value, key)) {
                throw new TypeError(label + " is missing field: " + key + ".");
            }
        }
    }

    function assertExactRecord(value, expected, label) {
        assertKeys(value, Object.keys(expected), [], label);
        for (const key of Object.keys(expected)) {
            if (value[key] !== expected[key]) throw new TypeError(label + " has an unsupported " + key + ".");
        }
    }

    function normalizeSource(source) {
        if (!plainObject(source)) throw new TypeError("A public challenge source is required.");
        if (source.kind === "original") {
            assertKeys(source, ["kind", "edition", "table_format", "number"], [], "Original source");
            if (source.edition !== "Sherlock 1.50 UK" || source.table_format !== 1 ||
                    !integer(source.number, 0, 65535)) throw new TypeError("Unsupported original puzzle source.");
            return { kind: "original", edition: "Sherlock 1.50 UK", table_format: 1, number: source.number };
        }
        if (source.kind === "native") {
            assertKeys(source, ["kind", "generator", "generator_version", "seed", "limits"], [], "Native source");
            if (source.generator !== GENERATOR_ID || source.generator_version !== GENERATOR_VERSION) {
                throw new TypeError("Unsupported native generator identity.");
            }
            const seed = canonicalDecimal(source.seed, "Native source seed");
            assertKeys(source.limits, ["node_budget", "max_attempts", "max_givens"], [], "Native source limits");
            const limits = normalizedLimits({
                node_budget: canonicalDecimal(source.limits.node_budget, "Native source node budget"),
                max_attempts: source.limits.max_attempts,
                max_givens: source.limits.max_givens
            });
            return {
                kind: "native", generator: GENERATOR_ID, generator_version: GENERATOR_VERSION,
                seed: seed, limits: limits
            };
        }
        throw new TypeError("Unsupported challenge source kind.");
    }

    function challengeId(source, fingerprint) {
        return source.kind === "native" ?
            GENERATOR_ID + ":v" + GENERATOR_VERSION + ":" + source.seed + ":" + fingerprint :
            "sherlock-1.50-uk:" + source.number + ":" + fingerprint;
    }

    function toChallenge(puzzle, source) {
        const validation = validatePuzzle(puzzle);
        if (!validation.valid) throw new TypeError(validation.reason);
        if (source === undefined) source = puzzle.source;
        if (source === undefined && integer(puzzle.number, 0, 65535)) {
            source = { kind: "original", edition: "Sherlock 1.50 UK", table_format: 1, number: puzzle.number };
        }
        source = normalizeSource(source);
        if (source.kind === "original" && puzzle.number !== source.number) {
            throw new TypeError("Original source number disagrees with the puzzle.");
        }
        const fingerprint = publicFingerprint(puzzle);
        const givens = [];
        for (let row = 0; row < SIZE; ++row) for (let column = 0; column < SIZE; ++column) {
            const item = puzzle.given[row][column];
            if (item >= 0) givens.push({ row: row, column: column, item: item, object: row * SIZE + item });
        }
        const clues = puzzle.clues.map(function (clue, index) {
            const output = { index: index, type: CLUE_NAMES[clue.type], a: clue.a };
            const arity = clueArity(clue.type);
            if (arity >= 2) output.b = clue.b;
            if (arity === 3) output.c = clue.c;
            const slot = puzzle.original_slot && puzzle.original_slot[index];
            output.display_slot = integer(slot, 36, 74) ? slot : null;
            return output;
        });
        return {
            challenge_id: challengeId(source, fingerprint),
            source: source,
            public_fingerprint: { algorithm: "fnv1a64-public-v1", hex: fingerprint },
            rows: SIZE, columns: SIZE, items_per_row: SIZE,
            answer_format: Object.assign({}, ANSWER_FORMAT),
            object_ids: Object.assign({}, OBJECT_IDS),
            column_function: COLUMN_FUNCTION,
            clue_predicates: Object.assign({}, CLUE_PREDICATES),
            givens: givens,
            clues: clues
        };
    }

    function normalizeGeneration(value) {
        assertKeys(value, ["classification", "attempts", "nodes"], [], "Generation metadata");
        if (value.classification !== "unique" || !integer(value.attempts, 1, 64)) {
            throw new TypeError("Invalid successful generation metadata.");
        }
        return {
            classification: "unique", attempts: value.attempts,
            nodes: canonicalDecimal(value.nodes, "Generation node count")
        };
    }

    function toDocument(puzzle, source, generation) {
        const challenge = toChallenge(puzzle, source);
        const document = { format: "sherlock-cli-1", kind: "puzzle", ok: true, challenge: challenge };
        if (challenge.source.kind === "native") {
            if (generation === undefined) generation = puzzle.generation;
            if (generation) {
                // Accept the internal C-shaped report as well as CLI metadata.
                if (generation.classification === undefined && generation.proof === 1) {
                    generation = { classification: "unique", attempts: generation.attempts, nodes: generation.nodes };
                }
                document.generation = normalizeGeneration(generation);
            }
        }
        return document;
    }

    function fromChallenge(document) {
        if (typeof document === "string") document = parseJSON(document);
        let challenge = document;
        let generation;
        if (plainObject(document) && Object.prototype.hasOwnProperty.call(document, "challenge")) {
            assertKeys(document, ["format", "kind", "ok", "challenge"], ["generation"], "Puzzle response");
            if (document.format !== "sherlock-cli-1" || document.kind !== "puzzle" || document.ok !== true) {
                throw new TypeError("Only successful sherlock-cli-1 puzzle responses can be imported.");
            }
            challenge = document.challenge;
            if (document.generation !== undefined) generation = normalizeGeneration(document.generation);
        }
        assertKeys(challenge, [
            "challenge_id", "source", "public_fingerprint", "rows", "columns", "items_per_row",
            "answer_format", "object_ids", "column_function", "clue_predicates", "givens", "clues"
        ], [], "Public challenge");
        if (challenge.rows !== SIZE || challenge.columns !== SIZE || challenge.items_per_row !== SIZE) {
            throw new TypeError("Only six-by-six Sherlock challenges are supported.");
        }
        assertExactRecord(challenge.answer_format, ANSWER_FORMAT, "Answer format");
        assertExactRecord(challenge.object_ids, OBJECT_IDS, "Object ID contract");
        assertExactRecord(challenge.clue_predicates, CLUE_PREDICATES, "Clue predicates");
        if (challenge.column_function !== COLUMN_FUNCTION) throw new TypeError("Unsupported column function.");
        const source = normalizeSource(challenge.source);
        if (generation && source.kind !== "native") throw new TypeError("Original puzzles have no native generation metadata.");
        if (source.kind === "native") {
            if (source.limits.max_attempts === 0 || source.limits.node_budget === "0") {
                throw new TypeError("A successful native challenge cannot have an empty generation budget.");
            }
            if (generation && (generation.attempts > source.limits.max_attempts ||
                    BigInt(generation.nodes) > BigInt(source.limits.node_budget))) {
                throw new TypeError("Generation metadata exceeds the declared source limits.");
            }
        }
        assertKeys(challenge.public_fingerprint, ["algorithm", "hex"], [], "Public fingerprint");
        if (challenge.public_fingerprint.algorithm !== "fnv1a64-public-v1" ||
                typeof challenge.public_fingerprint.hex !== "string" ||
                !/^[0-9a-f]{16}$/.test(challenge.public_fingerprint.hex)) {
            throw new TypeError("Unsupported public fingerprint.");
        }
        if (!Array.isArray(challenge.givens) || challenge.givens.length > OBJECTS) {
            throw new TypeError("The public given list is invalid.");
        }
        if (!Array.isArray(challenge.clues) || challenge.clues.length > MAX_CLUES) {
            throw new TypeError("The public clue count exceeds the supported capacity.");
        }
        const puzzle = {
            number: source.kind === "original" ? source.number : 0,
            given: filledMatrix(-1), clue_count: challenge.clues.length,
            clues: [], original_slot: [], source: source
        };
        for (const given of challenge.givens) {
            assertKeys(given, ["row", "column", "item", "object"], [], "Given");
            if (!integer(given.row, 0, 5) || !integer(given.column, 0, 5) ||
                    !integer(given.item, 0, 5) || given.object !== given.row * SIZE + given.item ||
                    puzzle.given[given.row][given.column] !== -1) {
                throw new TypeError("A given has invalid indices, a mismatched object ID or a duplicate cell.");
            }
            puzzle.given[given.row][given.column] = given.item;
        }
        for (let index = 0; index < challenge.clues.length; ++index) {
            const clue = challenge.clues[index];
            if (!plainObject(clue)) throw new TypeError("A public clue is not an object.");
            const type = CLUE_NAMES.indexOf(clue.type);
            if (type < 0) throw new TypeError("A public clue has an unknown relation.");
            const arity = clueArity(type);
            const keys = ["index", "type", "a", "display_slot"];
            if (arity >= 2) keys.push("b");
            if (arity === 3) keys.push("c");
            assertKeys(clue, keys, [], "Clue " + index);
            if (clue.index !== index || !integer(clue.a, 0, 35) ||
                    (arity >= 2 && !integer(clue.b, 0, 35)) ||
                    (arity === 3 && !integer(clue.c, 0, 35)) ||
                    (clue.display_slot !== null && !integer(clue.display_slot, 36, 74))) {
                throw new TypeError("A public clue has invalid operands, index or display slot.");
            }
            puzzle.clues.push({
                type: type, a: clue.a, b: arity >= 2 ? clue.b : 255,
                c: arity === 3 ? clue.c : 255
            });
            puzzle.original_slot.push(clue.display_slot === null ? 255 : clue.display_slot);
        }
        const fingerprint = publicFingerprint(puzzle);
        if (fingerprint !== challenge.public_fingerprint.hex) {
            throw new TypeError("Public challenge fingerprint does not match its givens, clues and layout.");
        }
        const expectedId = challengeId(source, fingerprint);
        if (challenge.challenge_id !== expectedId) throw new TypeError("Challenge identity does not match its source and fingerprint.");
        puzzle.challenge_id = expectedId;
        puzzle.public_fingerprint = { algorithm: "fnv1a64-public-v1", hex: fingerprint };
        if (generation) puzzle.generation = generation;
        // Matching a digest authenticates no publisher, original table or seed.
        // A caller requiring canonical provenance must bind to its local source.
        return puzzle;
    }

    /*
     * File/textarea JSON parser for import boundaries. JSON.parse alone loses
     * duplicate keys before schema validation can see them. This small parser
     * rejects duplicates (including escaped aliases), decoded NUL, excessive
     * depth/size, non-finite numbers and trailing documents without eval.
     * Object inputs to fromChallenge have already crossed their parser boundary.
     */
    function parseJSON(text, maximumBytes) {
        if (typeof text !== "string") throw new TypeError("JSON input must be text.");
        const maximum = maximumBytes === undefined ? 262144 : maximumBytes;
        if (!integer(maximum, 1, 1048576)) throw new RangeError("Invalid JSON byte limit.");
        if (text.length > maximum || new TextEncoder().encode(text).length > maximum) {
            throw new RangeError("JSON input exceeds its byte limit.");
        }
        let offset = 0;
        function fail(message) { throw new SyntaxError(message + " at character " + offset + "."); }
        function whitespace() {
            while (offset < text.length && /[ \t\r\n]/.test(text[offset])) ++offset;
        }
        function stringValue() {
            const start = offset++;
            let escaped = false;
            while (offset < text.length) {
                const code = text.charCodeAt(offset++);
                if (code < 32) fail("Unescaped control character in JSON string");
                if (escaped) {
                    if (code === 117) {
                        if (!/^[0-9a-fA-F]{4}$/.test(text.slice(offset, offset + 4))) fail("Invalid Unicode escape");
                        offset += 4;
                    } else if (![34, 92, 47, 98, 102, 110, 114, 116].includes(code)) fail("Invalid JSON escape");
                    escaped = false;
                } else if (code === 92) escaped = true;
                else if (code === 34) {
                    const value = JSON.parse(text.slice(start, offset));
                    if (value.includes("\u0000")) fail("Decoded NUL is not accepted");
                    return value;
                }
            }
            fail("Unterminated JSON string");
        }
        function value(depth) {
            if (depth > 64) fail("JSON nesting exceeds its limit");
            whitespace();
            const token = text[offset];
            if (token === '"') return stringValue();
            if (token === "{") {
                ++offset;
                whitespace();
                const result = Object.create(null);
                const seen = new Set();
                if (text[offset] === "}") { ++offset; return result; }
                for (;;) {
                    whitespace();
                    if (text[offset] !== '"') fail("Expected JSON object key");
                    const key = stringValue();
                    if (seen.has(key)) fail("Duplicate JSON object key");
                    seen.add(key);
                    whitespace();
                    if (text[offset++] !== ":") fail("Expected colon");
                    result[key] = value(depth + 1);
                    whitespace();
                    if (text[offset] === "}") { ++offset; return result; }
                    if (text[offset++] !== ",") fail("Expected comma");
                }
            }
            if (token === "[") {
                ++offset;
                whitespace();
                const result = [];
                if (text[offset] === "]") { ++offset; return result; }
                for (;;) {
                    if (result.length >= 16384) fail("JSON array exceeds its item limit");
                    result.push(value(depth + 1));
                    whitespace();
                    if (text[offset] === "]") { ++offset; return result; }
                    if (text[offset++] !== ",") fail("Expected comma");
                }
            }
            for (const literal of ["true", "false", "null"]) {
                if (text.slice(offset, offset + literal.length) === literal) {
                    offset += literal.length;
                    return literal === "true" ? true : literal === "false" ? false : null;
                }
            }
            const number = /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/.exec(text.slice(offset));
            if (!number) fail("Expected JSON value");
            offset += number[0].length;
            const result = Number(number[0]);
            if (!Number.isFinite(result)) fail("Non-finite JSON number");
            return result;
        }
        const result = value(0);
        whitespace();
        if (offset !== text.length) fail("Trailing JSON data");
        return result;
    }

    return Object.freeze({
        SIZE: SIZE,
        OBJECTS: OBJECTS,
        MAX_CLUES: MAX_CLUES,
        RELATIONS: RELATIONS,
        CLUE_NAMES: CLUE_NAMES,
        GENERATOR_ID: GENERATOR_ID,
        GENERATOR_VERSION: GENERATOR_VERSION,
        DEFAULT_SOLVE_NODES: DEFAULT_SOLVE_NODES,
        DEFAULT_GENERATE_LIMITS: DEFAULT_GENERATE_LIMITS,
        clueArity: clueArity,
        relationHolds: relationHolds,
        validatePuzzle: validatePuzzle,
        verifyAnswer: verifyAnswer,
        analyze: analyze,
        generate: generate,
        publicFingerprint: publicFingerprint,
        toChallenge: toChallenge,
        toDocument: toDocument,
        fromChallenge: fromChallenge,
        parseJSON: parseJSON
    });
}));
