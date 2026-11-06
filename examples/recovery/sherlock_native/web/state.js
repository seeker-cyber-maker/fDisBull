/* Sherlock browser state, ported from state/sherlock_state.c.
 *
 * The portable C implementation is the behavioral reference for this seam.
 * Its original-game qualification and deliberate policy differences remain
 * documented in research/HINT-SLICE-20261105.md. This module does not inspect
 * the hidden solution, run original machine code, or depend on a browser DOM.
 */
(function (root, factory) {
    'use strict';
    if (typeof module === 'object' && module.exports) {
        module.exports = factory(require('./engine.js'));
    } else {
        root.SherlockState = factory(root.SherlockCore);
    }
}(typeof globalThis !== 'undefined' ? globalThis : this, function (Core) {
    'use strict';

    if (!Core) throw new Error('SherlockCore must be loaded before SherlockState.');

    const SIZE = 6;
    const CAPACITY = 256;
    const UNDO_LIMIT = 25;
    const VERTICAL_SLOTS = 18;
    const HORIZONTAL_SLOTS = 21;
    const UINT32_MAX = 4294967295;
    const UINT64_MAX = (1n << 64n) - 1n;
    const PLAYING = 0, WON = 1, WRONG = 2, TIMED_OUT = 3, QUIT = 4;
    const NONE = 0, REMOVE = 1, CHOOSE = 2, CONTRADICTION = 3, UNRESOLVED = 4;
    const INVALID = -2, UNKNOWN = -1, UNSAT = 0, SAT = 1;
    const POPCOUNT = Array.from({length: 64}, function (_, n) {
        let count = 0;
        while (n) { count += n & 1; n >>>= 1; }
        return count;
    });

    function integer(value, minimum, maximum) {
        return Number.isInteger(value) && value >= minimum && value <= maximum;
    }

    function validBudget(value) { return integer(value, 0, UINT32_MAX); }
    function validCell(row, column, item) {
        return integer(row, 0, 5) && integer(column, 0, 5) && integer(item, 0, 5);
    }
    function matrix(value) {
        return Array.from({length: SIZE}, function () { return Array(SIZE).fill(value); });
    }
    function cloneMatrix(value) { return value.map(function (row) { return row.slice(); }); }
    function firstBit(value) {
        for (let bit = 0; bit < SIZE; bit++) if (value & (1 << bit)) return bit;
        return SIZE;
    }
    function isMatrix(value, low, high) {
        if (!Array.isArray(value) || value.length !== SIZE) return false;
        /* for..of observes sparse entries as undefined; Array#every skips them. */
        for (const row of value) {
            if (!Array.isArray(row) || row.length !== SIZE) return false;
            for (const item of row) if (!integer(item, low, high)) return false;
        }
        return true;
    }
    function clueCount(puzzle) {
        if (!puzzle || !Array.isArray(puzzle.clues) || puzzle.clues.length > CAPACITY) return -1;
        if (puzzle.clue_count !== undefined && puzzle.clue_count !== puzzle.clues.length) return -1;
        return puzzle.clues.length;
    }
    function validClue(clue) {
        if (!clue || !integer(clue.type, 0, 7) || !integer(clue.a, 0, 35) ||
            !integer(clue.b, 0, 255) || !integer(clue.c, 0, 255)) return false;
        if (clue.type !== 7 && clue.b >= 36) return false;
        if ((clue.type === 5 || clue.type === 6) && clue.c >= 36) return false;
        return true;
    }
    function validPremises(puzzle, candidates) {
        const count = clueCount(puzzle);
        if (count < 0 || !isMatrix(puzzle.given, -1, 5) || !isMatrix(candidates, 0, 63)) return false;
        for (const clue of puzzle.clues) if (!validClue(clue)) return false;
        return true;
    }
    function copyClue(clue) {
        return {type: clue.type, a: clue.a, b: clue.b, c: clue.c};
    }
    function uint64(value) {
        let parsed;
        if (typeof value === 'bigint') parsed = value;
        else if (typeof value === 'number' && Number.isSafeInteger(value)) parsed = BigInt(value);
        else if (typeof value === 'string' && /^(0|[1-9][0-9]*)$/.test(value) && value.length <= 20) parsed = BigInt(value);
        else throw new TypeError('Clock values must be unsigned integer milliseconds.');
        if (parsed < 0n || parsed > UINT64_MAX) throw new RangeError('Clock value exceeds uint64.');
        return parsed;
    }
    function ownObject(value) {
        return value !== null && typeof value === 'object' && !Array.isArray(value) &&
            (Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null);
    }
    function exactKeys(value, allowed, required) {
        if (!ownObject(value)) return false;
        const keys = Object.keys(value);
        return keys.every(function (key) { return allowed.includes(key); }) &&
            required.every(function (key) { return Object.prototype.hasOwnProperty.call(value, key); });
    }

    /* Copy only declared public fields. In particular, do not spread a puzzle
     * or serialize it wholesale: even a solution getter must never be read. */
    function cloneSource(source) {
        if (source === undefined) return undefined;
        if (!ownObject(source)) throw new TypeError('Invalid puzzle source metadata.');
        if (source.kind === 'native') {
            const limits = source.limits;
            if (!exactKeys(source, ['kind', 'generator', 'generator_version', 'seed', 'limits'],
                    ['kind', 'generator', 'generator_version', 'seed', 'limits']) ||
                source.generator !== 'sherlock-native-constraints' || source.generator_version !== 1 ||
                !exactKeys(limits, ['node_budget', 'max_attempts', 'max_givens'],
                    ['node_budget', 'max_attempts', 'max_givens']) ||
                !integer(limits.max_attempts, 1, UINT32_MAX) || !integer(limits.max_givens, 0, 3)) {
                throw new TypeError('Invalid native puzzle identity.');
            }
            const seed = uint64(source.seed).toString();
            const nodes = uint64(limits.node_budget).toString();
            return {
                kind: 'native', generator: source.generator, generator_version: 1, seed: seed,
                limits: {node_budget: nodes, max_attempts: limits.max_attempts, max_givens: limits.max_givens}
            };
        }
        if (source.kind === 'original' &&
            exactKeys(source, ['kind', 'edition', 'table_format', 'number'],
                ['kind', 'edition', 'table_format', 'number']) &&
            source.edition === 'Sherlock 1.50 UK' && source.table_format === 1 &&
            integer(source.number, 0, 65535)) {
            return {kind: 'original', edition: source.edition, table_format: 1, number: source.number};
        }
        throw new TypeError('Unsupported puzzle source identity.');
    }

    function visiblePuzzle(puzzle) {
        if (!validPremises(puzzle, matrix(63))) throw new TypeError('The public puzzle is malformed.');
        const slots = puzzle.original_slot === undefined ? Array(puzzle.clues.length).fill(255) : puzzle.original_slot;
        if (!Array.isArray(slots) || slots.length !== puzzle.clues.length) {
            throw new TypeError('Invalid clue display slots.');
        }
        for (const slot of slots) if (!integer(slot, 0, 255)) throw new TypeError('Invalid clue display slot.');
        const number = puzzle.number === undefined ? 0 : puzzle.number;
        if (!integer(number, 0, 65535)) throw new TypeError('Invalid puzzle number.');
        const result = {
            number: number, given: cloneMatrix(puzzle.given), clues: puzzle.clues.map(copyClue),
            clue_count: puzzle.clues.length, original_slot: slots.slice()
        };
        const source = cloneSource(puzzle.source);
        if (source !== undefined) result.source = source;
        if (puzzle.challenge_id !== undefined) {
            if (typeof puzzle.challenge_id !== 'string' || puzzle.challenge_id.length > 200 ||
                /[\u0000-\u001f]/.test(puzzle.challenge_id)) throw new TypeError('Invalid challenge identity.');
            result.challenge_id = puzzle.challenge_id;
        }
        if (puzzle.public_fingerprint !== undefined) {
            const fp = puzzle.public_fingerprint;
            if (!exactKeys(fp, ['algorithm', 'hex'], ['algorithm', 'hex']) ||
                fp.algorithm !== 'fnv1a64-public-v1' || typeof fp.hex !== 'string' ||
                !/^[0-9a-f]{16}$/.test(fp.hex)) throw new TypeError('Invalid public fingerprint.');
            result.public_fingerprint = {algorithm: fp.algorithm, hex: fp.hex};
        }
        if (puzzle.generation !== undefined) {
            const generation = puzzle.generation;
            if (!exactKeys(generation, ['classification', 'attempts', 'nodes'],
                    ['classification', 'attempts', 'nodes']) ||
                generation.classification !== 'unique' || !integer(generation.attempts, 1, UINT32_MAX)) {
                throw new TypeError('Invalid generation metadata.');
            }
            result.generation = {
                classification: 'unique', attempts: generation.attempts,
                nodes: uint64(generation.nodes).toString()
            };
        }
        const fingerprint = Core.publicFingerprint(result);
        if (result.public_fingerprint && result.public_fingerprint.hex !== fingerprint) {
            throw new TypeError('Public fingerprint does not match the puzzle.');
        }
        result.public_fingerprint = {algorithm: 'fnv1a64-public-v1', hex: fingerprint};
        if (result.source) {
            if (result.source.kind === 'original' && result.source.number !== result.number) {
                throw new TypeError('Original puzzle number disagrees with its source.');
            }
            const canonical = Core.toChallenge(result, result.source);
            if (result.challenge_id !== undefined && result.challenge_id !== canonical.challenge_id) {
                throw new TypeError('Public challenge identity does not match the puzzle.');
            }
            result.challenge_id = canonical.challenge_id;
        } else if (result.challenge_id !== undefined) {
            throw new TypeError('A challenge identity requires source metadata.');
        }
        return result;
    }

    function emptyHint() {
        return {kind: NONE, row: 0, column: 0, item: 0, clue_index: -1, explanation: ''};
    }
    function cloneHint(hint) {
        return {kind: hint.kind, row: hint.row, column: hint.column, item: hint.item,
            clue_index: hint.clue_index, explanation: hint.explanation};
    }
    function cloneBoard(board) {
        return {
            candidates: cloneMatrix(board.candidates),
            chosen: cloneMatrix(board.chosen),
            clue_slots: board.clue_slots.map(function (bank) {
                return bank.map(function (group) { return group.slice(); });
            })
        };
    }
    function emptySlots() {
        return Array.from({length: 2}, function () {
            return Array.from({length: 2}, function () { return Array(CAPACITY).fill(-1); });
        });
    }
    function remember(game) {
        if (game.undo.length === UNDO_LIMIT) game.undo.shift();
        game.undo.push(cloneBoard(game.board));
        game.undo_count = game.undo.length;
    }
    function finalVerdict(game) {
        if (game.board.chosen.some(function (row) { return row.some(function (item) { return item < 0; }); })) return;
        game.outcome = Core.verifyAnswer(game.puzzle, game.board.chosen).status === 1 ? WON : WRONG;
    }
    function clueGroup(clue) { return clue && clue.type >= 2 && clue.type <= 6 ? 1 : 0; }
    function puzzleClueGroup(puzzle, clue) {
        const count = clueCount(puzzle);
        if (!integer(clue, 0, count - 1)) return -1;
        const slot = puzzle.original_slot ? puzzle.original_slot[clue] : 255;
        if (slot >= 36 && slot <= 53) return 0;
        if (slot >= 54 && slot <= 74) return 1;
        return clueGroup(puzzle.clues[clue]);
    }

    function createGame(puzzle, timeLimitSeconds) {
        if (timeLimitSeconds === undefined) timeLimitSeconds = 0;
        if (!integer(timeLimitSeconds, 0, UINT32_MAX)) throw new RangeError('Time limit must be uint32 seconds.');
        const owned = visiblePuzzle(puzzle);
        const game = {
            puzzle: owned,
            board: {candidates: matrix(63), chosen: matrix(-1), clue_slots: emptySlots()},
            undo: [], undo_count: 0, fixed: matrix(0), outcome: PLAYING,
            elapsed_ms: 0n, limit_ms: BigInt(timeLimitSeconds) * 1000n,
            paused: 0, hint_pending: 0, pending_hint: emptyHint()
        };
        for (let row = 0; row < SIZE; row++) {
            for (let column = 0; column < SIZE; column++) {
                const item = owned.given[row][column];
                if (item < 0) continue;
                game.fixed[row][column] = 1;
                game.board.chosen[row][column] = item;
                game.board.candidates[row][column] = 1 << item;
                for (let other = 0; other < SIZE; other++) {
                    if (other !== column) game.board.candidates[row][other] &= ~(1 << item);
                }
            }
        }
        const next = [0, 0];
        for (let i = 0; i < owned.clues.length; i++) {
            const group = puzzleClueGroup(owned, i), raw = owned.original_slot[i];
            const capacity = group ? HORIZONTAL_SLOTS : VERTICAL_SLOTS;
            let slot = next[group];
            if (!group && raw >= 36 && raw <= 53) slot = raw - 36;
            if (group && raw >= 54 && raw <= 74) slot = raw - 54;
            while (slot < capacity && game.board.clue_slots[0][group][slot] >= 0) slot++;
            if (slot >= capacity) { game.outcome = WRONG; return game; }
            game.board.clue_slots[0][group][slot] = i;
            while (next[group] < capacity && game.board.clue_slots[0][group][next[group]] >= 0) next[group]++;
        }
        return game;
    }

    function cellByte(game, row, column) {
        if (!game || !integer(row, 0, 5) || !integer(column, 0, 5)) return 0;
        let value = game.board.candidates[row][column] & 63;
        if (game.fixed[row][column]) value |= 128;
        else if (game.board.chosen[row][column] >= 0) value |= 64;
        return value;
    }
    function canEdit(game, row, column) {
        return game.outcome === PLAYING && !game.paused && !game.hint_pending && !game.fixed[row][column];
    }
    function remove(game, row, column, item) {
        if (!game || !validCell(row, column, item)) return -1;
        if (!canEdit(game, row, column)) return 0;
        const bit = 1 << item;
        if (!(game.board.candidates[row][column] & bit)) return 0;
        remember(game);
        game.board.candidates[row][column] &= ~bit;
        game.board.chosen[row][column] = -1;
        return 1;
    }
    function restore(game, row, column, item) {
        if (!game || !validCell(row, column, item)) return -1;
        if (!canEdit(game, row, column)) return 0;
        const bit = 1 << item;
        if (game.board.candidates[row][column] & bit) return 0;
        remember(game);
        game.board.candidates[row][column] |= bit;
        game.board.chosen[row][column] = -1;
        return 1;
    }
    function choose(game, row, column, item) {
        if (!game || !validCell(row, column, item)) return -1;
        if (!canEdit(game, row, column)) return 0;
        const bit = 1 << item;
        if (!(game.board.candidates[row][column] & bit) || game.board.chosen[row][column] === item) return 0;
        remember(game);
        game.board.candidates[row][column] = bit;
        game.board.chosen[row][column] = item;
        for (let other = 0; other < SIZE; other++) {
            if (other === column || game.fixed[row][other]) continue;
            game.board.candidates[row][other] &= ~bit;
            if (game.board.chosen[row][other] === item) game.board.chosen[row][other] = -1;
        }
        finalVerdict(game);
        return 1;
    }
    function undo(game) {
        if (!game) return -1;
        if (!game.undo_count || game.hint_pending || game.paused || game.outcome !== PLAYING) return 0;
        game.board = game.undo.pop();
        game.undo_count = game.undo.length;
        return 1;
    }
    function clueLocation(game, clue) {
        if (!game || !integer(clue, 0, clueCount(game.puzzle) - 1)) return null;
        for (let bank = 0; bank < 2; bank++) for (let group = 0; group < 2; group++) {
            for (let slot = 0; slot < CAPACITY; slot++) {
                if (game.board.clue_slots[bank][group][slot] === clue) return {bank: bank, group: group, slot: slot};
            }
        }
        return null;
    }
    function archiveClue(game, clue) {
        if (!game || !integer(clue, 0, clueCount(game.puzzle) - 1)) return -1;
        if (game.outcome !== PLAYING || game.paused || game.hint_pending) return 0;
        const where = clueLocation(game, clue);
        if (!where) return -1;
        const capacity = where.group ? HORIZONTAL_SLOTS : VERTICAL_SLOTS;
        const target = game.board.clue_slots[1 - where.bank][where.group];
        let destination = 0;
        while (destination < capacity && target[destination] >= 0) destination++;
        if (destination === capacity) return -1;
        remember(game);
        game.board.clue_slots[where.bank][where.group][where.slot] = -1;
        target[destination] = clue;
        return 1;
    }
    function moveClue(game, clue, destination) {
        if (!game || !integer(clue, 0, clueCount(game.puzzle) - 1) ||
            !integer(destination, 0, CAPACITY - 1)) return -1;
        if (game.outcome !== PLAYING || game.paused || game.hint_pending) return 0;
        const where = clueLocation(game, clue);
        if (!where) return -1;
        const capacity = where.group ? HORIZONTAL_SLOTS : VERTICAL_SLOTS, source = where.slot;
        if (destination >= capacity || source >= capacity) return -1;
        if (source === destination) return 0;
        const slots = game.board.clue_slots[where.bank][where.group];
        let free = destination;
        while (free < capacity && slots[free] >= 0 && free !== source) free++;
        remember(game);
        if (free === capacity) {
            for (let i = source; i < destination; i++) slots[i] = slots[i + 1];
            slots[destination] = clue;
            return 1;
        }
        slots[source] = -1;
        while (free > destination) { slots[free] = slots[free - 1]; free--; }
        slots[destination] = clue;
        return 1;
    }
    function advanceElapsed(game, milliseconds) {
        const old = uint64(game.elapsed_ms);
        game.elapsed_ms = UINT64_MAX - old < milliseconds ? UINT64_MAX : old + milliseconds;
    }
    function tick(game, milliseconds) {
        if (!game) return 0;
        let delta;
        try { delta = uint64(milliseconds); } catch (_) { return -1; }
        if (game.paused || game.outcome !== PLAYING) return 0;
        advanceElapsed(game, delta);
        const limit = uint64(game.limit_ms);
        if (!game.hint_pending && limit && game.elapsed_ms >= limit) {
            game.outcome = TIMED_OUT;
            game.hint_pending = 0;
        }
        return 1;
    }
    function setPaused(game, paused) { if (game) game.paused = paused ? 1 : 0; }
    function displayTimeMs(game) {
        if (!game) return 0n;
        const elapsed = uint64(game.elapsed_ms), limit = uint64(game.limit_ms);
        return !limit ? elapsed : (elapsed >= limit ? 0n : limit - elapsed);
    }
    function quit(game) {
        if (game && game.outcome === PLAYING) { game.outcome = QUIT; game.hint_pending = 0; }
    }

    function visibleDomains(candidates) {
        const domains = new Uint8Array(36);
        for (let row = 0; row < 6; row++) for (let item = 0; item < 6; item++) {
            for (let column = 0; column < 6; column++) {
                if (candidates[row][column] & (1 << item)) domains[row * 6 + item] |= 1 << column;
            }
        }
        return domains;
    }
    function consistentPair(a, b, ca, cb) {
        if (a === b) return ca === cb;
        return Math.floor(a / 6) !== Math.floor(b / 6) || ca !== cb;
    }
    function clueArity(clue) { return clue.type === 5 || clue.type === 6 ? 3 : 2; }
    function hasSupport(clue, domains, object, column) {
        if (clue.type === 7) return true;
        const arity = clueArity(clue);
        if (clue.a >= 36 || clue.b >= 36 || (arity === 3 && clue.c >= 36)) return false;
        for (let a = 0; a < 6; a++) {
            if (!(domains[clue.a] & (1 << a)) || (clue.a === object && a !== column)) continue;
            for (let b = 0; b < 6; b++) {
                if (!(domains[clue.b] & (1 << b)) || (clue.b === object && b !== column) ||
                    !consistentPair(clue.a, clue.b, a, b)) continue;
                for (let c = 0; c < (arity === 3 ? 6 : 1); c++) {
                    if (arity === 3 && (!(domains[clue.c] & (1 << c)) ||
                        (clue.c === object && c !== column) ||
                        !consistentPair(clue.a, clue.c, a, c) || !consistentPair(clue.b, clue.c, b, c))) continue;
                    if (Core.relationHolds(clue.type, a, b, c)) return true;
                }
            }
        }
        return false;
    }
    function propagate(puzzle, domains) {
        let changed;
        do {
            changed = false;
            for (let i = 0; i < 36; i++) if (!domains[i]) return false;
            for (let row = 0; row < 6; row++) {
                for (let subset = 1; subset < 64; subset++) {
                    let places = 0;
                    const count = POPCOUNT[subset];
                    for (let item = 0; item < 6; item++) {
                        if (subset & (1 << item)) places |= domains[row * 6 + item];
                    }
                    if (POPCOUNT[places] < count) return false;
                    if (POPCOUNT[places] !== count) continue;
                    for (let item = 0; item < 6; item++) {
                        if (subset & (1 << item)) continue;
                        const object = row * 6 + item, old = domains[object];
                        domains[object] &= ~places;
                        if (!domains[object]) return false;
                        if (domains[object] !== old) changed = true;
                    }
                }
            }
            for (let i = 0; i < puzzle.clues.length; i++) {
                const clue = puzzle.clues[i], objects = [clue.a, clue.b, clue.c];
                if (clue.type === 7) continue;
                for (let k = 0; k < clueArity(clue); k++) {
                    const object = objects[k];
                    if (object >= 36) return false;
                    for (let column = 0; column < 6; column++) {
                        if ((domains[object] & (1 << column)) && !hasSupport(clue, domains, object, column)) {
                            domains[object] &= ~(1 << column);
                            changed = true;
                        }
                    }
                    if (!domains[object]) return false;
                }
            }
        } while (changed);
        return true;
    }
    function satisfiable(puzzle, domains, budget) {
        if (!budget.remaining) return UNKNOWN;
        budget.remaining--;
        if (!propagate(puzzle, domains)) return UNSAT;
        let object = 36, smallest = 7, unknown = false;
        for (let i = 0; i < 36; i++) {
            const count = POPCOUNT[domains[i]];
            if (count > 1 && count < smallest) { object = i; smallest = count; }
        }
        if (object === 36) return SAT;
        for (let column = 0; column < 6; column++) {
            if (!(domains[object] & (1 << column))) continue;
            const child = domains.slice();
            child[object] = 1 << column;
            const result = satisfiable(puzzle, child, budget);
            if (result === SAT) return SAT;
            if (result < 0) unknown = true;
        }
        return unknown ? UNKNOWN : UNSAT;
    }
    function checkCandidates(puzzle, candidates, nodeBudget) {
        if (nodeBudget === undefined) nodeBudget = 20000;
        if (!validBudget(nodeBudget) || !validPremises(puzzle, candidates)) {
            return {status: INVALID, remaining_nodes: validBudget(nodeBudget) ? nodeBudget : 0, nodes_used: 0};
        }
        const domains = visibleDomains(candidates), budget = {remaining: nodeBudget};
        for (let row = 0; row < 6; row++) for (let column = 0; column < 6; column++) {
            const given = puzzle.given[row][column];
            if (given >= 0) domains[row * 6 + given] &= 1 << column;
        }
        const status = satisfiable(puzzle, domains, budget);
        return {status: status, remaining_nodes: budget.remaining, nodes_used: nodeBudget - budget.remaining};
    }

    function hintAt(kind, object, column, clue, reason) {
        const row = Math.floor(object / 6), item = object % 6;
        return {kind: kind, row: row, column: column, item: item, clue_index: clue,
            explanation: reason + '\nRow ' + (row + 1) + ', column ' + (column + 1) + ', item ' + (item + 1) + '.',
            result: 1};
    }
    function orderedClueHint(game, index, domains) {
        const clue = game.puzzle.clues[index], a = clue.a, b = clue.b;
        if (clue.type === 0 || clue.type === 1) {
            const abit = 1 << (a % 6), bbit = 1 << (b % 6), ar = Math.floor(a / 6), br = Math.floor(b / 6);
            for (let column = 0; column < 6; column++) {
                const amask = game.board.candidates[ar][column], bmask = game.board.candidates[br][column];
                if (clue.type === 0) {
                    const chooseReason = 'The partner is in this column. These pictures share a column, so select this one here.';
                    const removeReason = 'The partner is absent from this column. These pictures share a column, so remove this one here.';
                    if (amask === abit && (bmask & bbit) && game.board.chosen[br][column] < 0) {
                        return hintAt(CHOOSE, b, column, index, chooseReason);
                    }
                    if (bmask === bbit && (amask & abit) && game.board.chosen[ar][column] < 0) {
                        return hintAt(CHOOSE, a, column, index, chooseReason);
                    }
                    if (!(amask & abit) && (bmask & bbit)) return hintAt(REMOVE, b, column, index, removeReason);
                    if (!(bmask & bbit) && (amask & abit)) return hintAt(REMOVE, a, column, index, removeReason);
                } else {
                    const reason = 'The partner is in this column. These pictures belong in different columns, so remove this one here.';
                    if (amask === abit && (bmask & bbit)) return hintAt(REMOVE, b, column, index, reason);
                    if (bmask === bbit && (amask & abit)) return hintAt(REMOVE, a, column, index, reason);
                }
            }
        } else if (clue.type === 4) {
            const firstA = firstBit(domains[a]);
            let lastB = 6;
            for (let column = 0; column <= firstA && column < 6; column++) {
                if (domains[b] & (1 << column)) {
                    return hintAt(REMOVE, b, column, index,
                        'This picture must be to the right of its partner, which has no possible column to its left here.');
                }
            }
            while (lastB && !(domains[b] & (1 << (lastB - 1)))) lastB--;
            if (lastB) for (let column = 5; column >= lastB - 1; column--) {
                if (domains[a] & (1 << column)) {
                    return hintAt(REMOVE, a, column, index,
                        'This picture must be to the left of its partner, which has no possible column to its right here.');
                }
            }
        }
        return null;
    }
    const REASONS = [
        'These items must share a column; this position has no matching partner.',
        'These items cannot share a column; this position has no legal partner.',
        'These items must occupy neighboring columns; this position cannot do so.',
        'These items must not be neighbors; this position would force adjacency.',
        'The first item must be left of the second; this position cannot satisfy that order.',
        'The middle item must have the other two as its immediate neighbors.',
        'The outer items must be two columns apart, with the named item absent from the middle.'
    ];
    function findHint(game, bank, searchBudget) {
        if (bank === undefined) bank = 0;
        if (searchBudget === undefined) searchBudget = 20000;
        const empty = emptyHint();
        empty.result = 0;
        if (!game || !integer(bank, 0, 1) || !validBudget(searchBudget)) { empty.result = -1; return empty; }
        if (game.outcome !== PLAYING) return empty;
        if (checkCandidates(game.puzzle, game.board.candidates, 0).status === INVALID) { empty.result = -1; return empty; }
        const domains = visibleDomains(game.board.candidates), checked = domains.slice();
        if (!propagate(game.puzzle, checked)) {
            empty.kind = CONTRADICTION;
            empty.explanation = "The current possibilities contradict the clues or a row's six distinct items. Undo a deduction or restore a removed possibility.";
            return empty;
        }
        for (let row = 0; row < 6; row++) for (let column = 0; column < 6; column++) {
            const mask = game.board.candidates[row][column];
            if (game.board.chosen[row][column] < 0 && POPCOUNT[mask] === 1) {
                return hintAt(CHOOSE, row * 6 + firstBit(mask), column, -1,
                    'Only this item remains possible in this square. Select it.');
            }
        }
        for (let i = 0; i < 36; i++) {
            if (POPCOUNT[domains[i]] !== 1) continue;
            const column = firstBit(domains[i]);
            if (game.board.chosen[Math.floor(i / 6)][column] < 0) {
                return hintAt(CHOOSE, i, column, -1, 'This is the only remaining column for this item. Select it.');
            }
        }
        for (let group = 0; group < 2; group++) {
            const capacity = group ? HORIZONTAL_SLOTS : VERTICAL_SLOTS;
            for (let slot = 0; slot < capacity; slot++) {
                const index = game.board.clue_slots[bank][group][slot];
                if (index < 0 || index >= game.puzzle.clues.length) continue;
                const clue = game.puzzle.clues[index], objects = [clue.a, clue.b, clue.c];
                if (clue.type >= 7) continue;
                const ordered = orderedClueHint(game, index, domains);
                if (ordered) return ordered;
                for (let k = 0; k < clueArity(clue); k++) {
                    const object = objects[k];
                    for (let column = 0; column < 6; column++) {
                        if ((domains[object] & (1 << column)) && !hasSupport(clue, domains, object, column)) {
                            return hintAt(REMOVE, object, column, index, REASONS[clue.type]);
                        }
                    }
                }
            }
        }
        for (let i = 0; i < 36; i++) for (let column = 0; column < 6; column++) {
            if ((domains[i] & (1 << column)) && !(checked[i] & (1 << column))) {
                return hintAt(REMOVE, i, column, -1,
                    'Combining the clues with the rule that each row contains every item once rules out this position.');
            }
        }
        if (searchBudget) {
            const budget = {remaining: searchBudget};
            let result = satisfiable(game.puzzle, domains.slice(), budget);
            if (result === UNSAT) {
                empty.kind = CONTRADICTION;
                empty.explanation = 'No completion satisfies the clues and your current possibilities. Undo a deduction or restore a candidate.';
                return empty;
            }
            let unresolved = result < 0;
            if (!unresolved) search: for (let i = 0; i < 36; i++) {
                if (POPCOUNT[domains[i]] <= 1) continue;
                for (let column = 0; column < 6; column++) {
                    if (!(domains[i] & (1 << column))) continue;
                    const child = domains.slice();
                    child[i] = 1 << column;
                    result = satisfiable(game.puzzle, child, budget);
                    if (result === UNSAT) {
                        return hintAt(REMOVE, i, column, -1,
                            'Assuming this position leaves no possible completion under the clues. Remove it.');
                    }
                    if (result < 0) { unresolved = true; break search; }
                }
            }
            if (unresolved) {
                empty.kind = UNRESOLVED;
                empty.explanation = 'The bounded logical search did not finish. No move or time penalty was applied.';
                return empty;
            }
        }
        empty.explanation = 'No forced deduction was found from the current possibilities and clues. No time penalty was charged.';
        return empty;
    }
    function requestHint(game, bank, searchBudget) {
        if (bank === undefined) bank = 0;
        if (searchBudget === undefined) searchBudget = 20000;
        if (!game || !integer(bank, 0, 1) || !validBudget(searchBudget)) return -1;
        if (game.hint_pending || game.paused || game.outcome !== PLAYING) return 0;
        const hint = findHint(game, bank, searchBudget);
        game.pending_hint = cloneHint(hint);
        if (hint.result !== 1) return hint.result;
        game.hint_pending = 1;
        return 1;
    }
    function acceptHint(game) {
        if (!game) return -1;
        if (!game.hint_pending || game.outcome !== PLAYING) return 0;
        const hint = cloneHint(game.pending_hint);
        game.hint_pending = 0;
        let mutation = 0;
        if (hint.kind === REMOVE) mutation = remove(game, hint.row, hint.column, hint.item);
        else if (hint.kind === CHOOSE) mutation = choose(game, hint.row, hint.column, hint.item);
        if (mutation === 1) {
            advanceElapsed(game, 30000n);
            const limit = uint64(game.limit_ms);
            if (limit && game.elapsed_ms >= limit) game.outcome = TIMED_OUT;
        }
        return mutation;
    }

    /* Compact saves contain native cell bytes and visible clue-grid slots.
     * Fixed flags are checked against public givens during import; saved data
     * cannot create new givens, a bogus win, or an unproved pending deduction.
     * Undo is deliberately board-only and never restores elapsed time. */
    function packedBoard(board, fixed) {
        const cells = [];
        for (let row = 0; row < 6; row++) for (let column = 0; column < 6; column++) {
            let value = board.candidates[row][column];
            if (fixed[row][column]) value |= 128;
            else if (board.chosen[row][column] >= 0) value |= 64;
            cells.push(value);
        }
        return {
            cells: cells,
            clue_slots: board.clue_slots.map(function (bank) {
                return [bank[0].slice(0, VERTICAL_SLOTS), bank[1].slice(0, HORIZONTAL_SLOTS)];
            })
        };
    }
    function unpackBoard(data, puzzle) {
        if (!exactKeys(data, ['cells', 'clue_slots'], ['cells', 'clue_slots']) ||
            !Array.isArray(data.cells) || data.cells.length !== 36 ||
            !Array.isArray(data.clue_slots) || data.clue_slots.length !== 2) {
            throw new TypeError('Invalid saved board shape.');
        }
        const board = {candidates: matrix(0), chosen: matrix(-1), clue_slots: emptySlots()};
        for (let cell = 0; cell < 36; cell++) {
            const value = data.cells[cell], row = Math.floor(cell / 6), column = cell % 6;
            if (!integer(value, 0, 255) || (value & 192) === 192) throw new TypeError('Invalid saved cell flags.');
            const mask = value & 63, given = puzzle.given[row][column];
            const fixed = !!(value & 128), selected = !!(value & 64);
            if (fixed !== (given >= 0) || (fixed && mask !== (1 << given)) ||
                (selected && POPCOUNT[mask] !== 1)) throw new TypeError('Saved selection or fixed cell is inconsistent.');
            board.candidates[row][column] = mask;
            board.chosen[row][column] = fixed ? given : (selected ? firstBit(mask) : -1);
        }
        const seen = new Set();
        for (let bank = 0; bank < 2; bank++) {
            if (!Array.isArray(data.clue_slots[bank]) || data.clue_slots[bank].length !== 2) {
                throw new TypeError('Invalid saved clue banks.');
            }
            for (let group = 0; group < 2; group++) {
                const slots = data.clue_slots[bank][group], capacity = group ? HORIZONTAL_SLOTS : VERTICAL_SLOTS;
                if (!Array.isArray(slots) || slots.length !== capacity) throw new TypeError('Invalid saved clue slot count.');
                for (let slot = 0; slot < capacity; slot++) {
                    const index = slots[slot];
                    if (!integer(index, -1, puzzle.clues.length - 1)) throw new TypeError('Invalid saved clue index.');
                    if (index >= 0) {
                        if (seen.has(index) || puzzleClueGroup(puzzle, index) !== group) {
                            throw new TypeError('Duplicate or misplaced saved clue.');
                        }
                        seen.add(index);
                    }
                    board.clue_slots[bank][group][slot] = index;
                }
            }
        }
        if (seen.size !== puzzle.clues.length) throw new TypeError('A saved clue is missing.');
        return board;
    }
    function exportGame(game) {
        if (!game) throw new TypeError('A game is required.');
        return {
            format: 'sherlock-browser-save-1',
            puzzle: visiblePuzzle(game.puzzle),
            board: packedBoard(game.board, game.fixed),
            undo: game.undo.map(function (board) { return packedBoard(board, game.fixed); }),
            undo_count: game.undo.length,
            outcome: game.outcome, elapsed_ms: uint64(game.elapsed_ms).toString(),
            limit_ms: uint64(game.limit_ms).toString(), paused: game.paused ? 1 : 0,
            hint_pending: game.hint_pending ? 1 : 0, pending_hint: cloneHint(game.pending_hint)
        };
    }

    /* The core JSON reader already checks decoded duplicate keys, NUL, bounded
     * nesting and input size. Share that boundary with challenge/agent imports. */
    function parseSaveJSON(text) {
        return Core.parseJSON(text, 131072);
    }

    function importGame(document, expectedPuzzle) {
        const data = typeof document === 'string' ? parseSaveJSON(document) : document;
        const keys = ['format', 'puzzle', 'board', 'undo', 'undo_count', 'outcome',
            'elapsed_ms', 'limit_ms', 'paused', 'hint_pending', 'pending_hint'];
        if (!exactKeys(data, keys, keys) || data.format !== 'sherlock-browser-save-1' ||
            !Array.isArray(data.undo) || data.undo.length > UNDO_LIMIT ||
            data.undo_count !== data.undo.length || !integer(data.outcome, PLAYING, QUIT) ||
            !integer(data.paused, 0, 1) || !integer(data.hint_pending, 0, 1)) {
            throw new TypeError('Invalid browser save envelope.');
        }
        const puzzleKeys = ['number', 'given', 'clues', 'clue_count', 'original_slot',
            'source', 'challenge_id', 'public_fingerprint', 'generation'];
        if (!exactKeys(data.puzzle, puzzleKeys, ['number', 'given', 'clues', 'clue_count', 'original_slot'])) {
            throw new TypeError('Invalid saved public puzzle fields.');
        }
        if (!Array.isArray(data.puzzle.clues) || !data.puzzle.clues.every(function (clue) {
            return exactKeys(clue, ['type', 'a', 'b', 'c'], ['type', 'a', 'b', 'c']);
        })) throw new TypeError('Invalid saved clue fields.');
        const puzzle = visiblePuzzle(data.puzzle);
        const fingerprint = Core.publicFingerprint(puzzle);
        if (puzzle.public_fingerprint && puzzle.public_fingerprint.hex !== fingerprint) {
            throw new TypeError('Saved public fingerprint does not match its constraints.');
        }
        if (puzzle.source && puzzle.challenge_id) {
            const canonical = Core.toChallenge(puzzle, puzzle.source, puzzle.generation);
            if (canonical.challenge_id !== puzzle.challenge_id) throw new TypeError('Saved challenge identity is inconsistent.');
        }
        if (expectedPuzzle) {
            const expected = visiblePuzzle(expectedPuzzle);
            if (Core.publicFingerprint(expected) !== fingerprint ||
                JSON.stringify(expected.source || null) !== JSON.stringify(puzzle.source || null)) {
                throw new TypeError('Save does not belong to the expected public challenge.');
            }
        }
        if (typeof data.elapsed_ms !== 'string' || typeof data.limit_ms !== 'string') {
            throw new TypeError('Saved uint64 clocks must be decimal strings.');
        }
        const elapsed = uint64(data.elapsed_ms), limit = uint64(data.limit_ms);
        const initial = createGame(puzzle);
        if (initial.outcome !== PLAYING) throw new TypeError('Saved puzzle exceeds the visible clue-grid capacity.');
        const board = unpackBoard(data.board, puzzle);
        const history = Array.from(data.undo, function (entry) { return unpackBoard(entry, puzzle); });
        const pending = data.pending_hint;
        if (!exactKeys(pending, ['kind', 'row', 'column', 'item', 'clue_index', 'explanation'],
                ['kind', 'row', 'column', 'item', 'clue_index', 'explanation']) ||
            !integer(pending.kind, NONE, UNRESOLVED) || !validCell(pending.row, pending.column, pending.item) ||
            !integer(pending.clue_index, -1, puzzle.clues.length - 1) ||
            typeof pending.explanation !== 'string' || pending.explanation.length > 255 ||
            pending.explanation.includes('\u0000')) throw new TypeError('Invalid saved hint.');
        const complete = board.chosen.every(function (row) { return row.every(function (item) { return item >= 0; }); });
        /* Native initialization does not run the completion verdict. A wholly
         * given synthetic puzzle can therefore start complete and PLAYING. */
        const whollyFixed = initial.fixed.every(function (row) { return row.every(Boolean); });
        const answerStatus = complete ? Core.verifyAnswer(puzzle, board.chosen).status : null;
        if ((data.outcome === WON && (!complete || answerStatus !== 1 || (limit && elapsed >= limit))) ||
            (data.outcome === WRONG && (!complete || answerStatus !== 0)) ||
            (data.outcome === TIMED_OUT && (!limit || elapsed < limit)) ||
            (data.outcome === PLAYING && ((complete && !whollyFixed) || (!data.hint_pending && limit && elapsed >= limit))) ||
            (data.hint_pending && data.outcome !== PLAYING)) {
            throw new TypeError('Saved outcome contradicts the board or clock.');
        }
        if (data.hint_pending) {
            const bit = 1 << pending.item;
            if ((pending.kind !== REMOVE && pending.kind !== CHOOSE) ||
                initial.fixed[pending.row][pending.column] ||
                !(board.candidates[pending.row][pending.column] & bit) ||
                (pending.kind === CHOOSE && board.chosen[pending.row][pending.column] === pending.item)) {
                throw new TypeError('Saved pending hint cannot apply to this board.');
            }
            const premise = checkCandidates(puzzle, board.candidates, 20000);
            const contrary = cloneMatrix(board.candidates);
            if (pending.kind === REMOVE) contrary[pending.row][pending.column] &= bit;
            else contrary[pending.row][pending.column] &= ~bit;
            const opposite = checkCandidates(puzzle, contrary, premise.remaining_nodes);
            if (premise.status !== SAT || opposite.status !== UNSAT) {
                throw new TypeError('Saved pending hint could not be proved from the public board.');
            }
        }
        initial.board = board;
        initial.undo = history;
        initial.undo_count = history.length;
        initial.outcome = data.outcome;
        initial.elapsed_ms = elapsed;
        initial.limit_ms = limit;
        initial.paused = data.paused;
        initial.hint_pending = data.hint_pending;
        initial.pending_hint = cloneHint(pending);
        return initial;
    }

    return Object.freeze({
        SH_SIZE: SIZE, SH_CLUE_CAPACITY: CAPACITY, SH_UNDO_LIMIT: UNDO_LIMIT,
        SH_VERTICAL_SLOTS: VERTICAL_SLOTS, SH_HORIZONTAL_SLOTS: HORIZONTAL_SLOTS,
        UINT64_MAX: UINT64_MAX,
        SH_PLAYING: PLAYING, SH_WON: WON, SH_WRONG: WRONG, SH_TIMED_OUT: TIMED_OUT, SH_QUIT: QUIT,
        SH_HINT_NONE: NONE, SH_HINT_REMOVE: REMOVE, SH_HINT_CHOOSE: CHOOSE,
        SH_HINT_CONTRADICTION: CONTRADICTION, SH_HINT_UNRESOLVED: UNRESOLVED,
        SH_CONSTRAINT_INVALID: INVALID, SH_CONSTRAINT_UNKNOWN: UNKNOWN,
        SH_CONSTRAINT_UNSAT: UNSAT, SH_CONSTRAINT_SAT: SAT,
        createGame: createGame, cellByte: cellByte, remove: remove, restore: restore, choose: choose,
        undo: undo, clueGroup: clueGroup, puzzleClueGroup: puzzleClueGroup, clueLocation: clueLocation,
        archiveClue: archiveClue, moveClue: moveClue, tick: tick, setPaused: setPaused,
        displayTimeMs: displayTimeMs, quit: quit, relationHolds: Core.relationHolds,
        findHint: findHint, requestHint: requestHint, acceptHint: acceptHint,
        checkCandidates: checkCandidates, cloneBoard: cloneBoard, visiblePuzzle: visiblePuzzle,
        exportGame: exportGame, importGame: importGame, parseSaveJSON: parseSaveJSON
    });
}));
