/* Supporting-premise records for the browser replica.
 *
 * Port of state/sherlock_hint_proof.c. A record freezes a fixed target and all
 * candidate/given/row assumptions. It is not a human-readable proof trace and
 * does not authenticate the origin of an externally supplied challenge.
 */
(function (root, factory) {
    'use strict';
    if (typeof module === 'object' && module.exports) {
        module.exports = factory(require('./state.js'));
    } else {
        root.SherlockProof = factory(root.SherlockState);
    }
}(typeof globalThis !== 'undefined' ? globalThis : this, function (State) {
    'use strict';
    if (!State) throw new Error('SherlockState must be loaded before SherlockProof.');

    const INVALID = -1, UNRESOLVED = 0, PROVED = 1, REFUTED = 2, INCONSISTENT = 3;
    const VERSION = 1, ROW_RULE = 1, CAPACITY = 256;
    const SAT = State.SH_CONSTRAINT_SAT, UNSAT = State.SH_CONSTRAINT_UNSAT;
    const UNKNOWN = State.SH_CONSTRAINT_UNKNOWN, BAD_PREMISES = State.SH_CONSTRAINT_INVALID;

    function integer(value, low, high) { return Number.isInteger(value) && value >= low && value <= high; }
    function validBudget(value) { return integer(value, 0, 4294967295); }
    function matrix(value) {
        return Array.from({length: 6}, function () { return Array(6).fill(value); });
    }
    function cloneMatrix(value) { return value.map(function (row) { return row.slice(); }); }
    function isMatrix(value, low, high) {
        if (!Array.isArray(value) || value.length !== 6) return false;
        for (const row of value) {
            if (!Array.isArray(row) || row.length !== 6) return false;
            for (const entry of row) if (!integer(entry, low, high)) return false;
        }
        return true;
    }
    function copyClue(clue) { return {type: clue.type, a: clue.a, b: clue.b, c: clue.c}; }
    function emptyRecord() {
        return {
            version: 0, background_rules: 0,
            target: {kind: 0, row: 0, column: 0, item: 0},
            selected_clue_index: 0, candidates: matrix(0), given: matrix(0),
            source_clue_count: 0, support_count: 0, support: []
        };
    }
    function beginReport(budget) {
        return {
            status: INVALID, node_budget: validBudget(budget) ? budget : 0,
            nodes_used: 0, deletion_checks: 0, reduction_complete: 0, reason: ''
        };
    }
    function finish(record, report, status, remaining, reason) {
        report.status = status;
        report.nodes_used = report.node_budget - remaining;
        report.reason = reason;
        return {status: status, record: record, report: report};
    }
    function objectKeys(value, allowed, required) {
        return value !== null && typeof value === 'object' && !Array.isArray(value) &&
            Object.keys(value).every(function (key) { return allowed.includes(key); }) &&
            required.every(function (key) { return Object.prototype.hasOwnProperty.call(value, key); });
    }
    function validTarget(record) {
        const target = record.target;
        return objectKeys(target, ['kind', 'row', 'column', 'item'], ['kind', 'row', 'column', 'item']) &&
            (target.kind === State.SH_HINT_REMOVE || target.kind === State.SH_HINT_CHOOSE) &&
            integer(target.row, 0, 5) && integer(target.column, 0, 5) && integer(target.item, 0, 5) &&
            !!(record.candidates[target.row][target.column] & (1 << target.item));
    }
    function premisePuzzle(record, skip) {
        const clues = [];
        for (let i = 0; i < record.support_count; i++) {
            if (i !== skip) clues.push(copyClue(record.support[i].clue));
        }
        return {number: 0, given: cloneMatrix(record.given), clues: clues,
            clue_count: clues.length, original_slot: Array(clues.length).fill(255)};
    }
    function contraryCandidates(record) {
        const target = record.target, result = cloneMatrix(record.candidates), bit = 1 << target.item;
        if (target.kind === State.SH_HINT_REMOVE) result[target.row][target.column] &= bit;
        else result[target.row][target.column] &= ~bit;
        return result;
    }
    function validRecord(record) {
        const keys = ['version', 'background_rules', 'target', 'selected_clue_index',
            'candidates', 'given', 'source_clue_count', 'support_count', 'support'];
        if (!objectKeys(record, keys, keys) || record.version !== VERSION || record.background_rules !== ROW_RULE ||
            !integer(record.source_clue_count, 0, CAPACITY) ||
            !integer(record.support_count, 0, record.source_clue_count) ||
            !integer(record.selected_clue_index, -1, record.source_clue_count - 1) ||
            !isMatrix(record.candidates, 0, 63) || !isMatrix(record.given, -1, 5) ||
            !Array.isArray(record.support) || record.support.length !== record.support_count ||
            !validTarget(record)) return false;
        const seen = new Set();
        for (const item of record.support) {
            if (!objectKeys(item, ['index', 'clue'], ['index', 'clue']) ||
                !integer(item.index, 0, record.source_clue_count - 1) || seen.has(item.index) ||
                !objectKeys(item.clue, ['type', 'a', 'b', 'c'], ['type', 'a', 'b', 'c']) ||
                !integer(item.clue.type, 0, 6)) return false;
            seen.add(item.index);
        }
        return State.checkCandidates(premisePuzzle(record, CAPACITY), record.candidates, 0).status !== BAD_PREMISES;
    }
    function decide(record, budget) {
        const puzzle = premisePuzzle(record, CAPACITY);
        let result = State.checkCandidates(puzzle, record.candidates, budget.remaining);
        budget.remaining = result.remaining_nodes;
        if (result.status === BAD_PREMISES) return {status: INVALID, reason: 'The stated premises are malformed.'};
        if (result.status === UNKNOWN) return {
            status: UNRESOLVED, reason: 'The node budget ended before premise consistency was established.'
        };
        if (result.status === UNSAT) return {
            status: INCONSISTENT,
            reason: 'The frozen candidates, givens, clues and row rules have no completion; no move is certified.'
        };
        result = State.checkCandidates(puzzle, contraryCandidates(record), budget.remaining);
        budget.remaining = result.remaining_nodes;
        if (result.status === BAD_PREMISES) return {status: INVALID, reason: 'The contrary-move constraints are malformed.'};
        if (result.status === UNKNOWN) return {
            status: UNRESOLVED,
            reason: 'The premises are consistent, but the node budget ended before the exact move was decided.'
        };
        if (result.status === SAT) return {
            status: REFUTED,
            reason: 'A completion satisfies the stated premises and contradicts this move; the move is not forced.'
        };
        return {
            status: PROVED,
            reason: 'The stated premises are consistent and the exact contrary move has no completion. Minimality was not checked.'
        };
    }

    function replayHintProof(record, nodeBudget) {
        if (nodeBudget === undefined) nodeBudget = 20000;
        const report = beginReport(nodeBudget);
        if (!validBudget(nodeBudget)) return finish(record, report, INVALID, 0, 'The node budget must be an unsigned 32-bit integer.');
        if (!validRecord(record)) return finish(record, report, INVALID, nodeBudget,
            'The record has invalid version, rules, target, premise bounds, or source clue indices.');
        const budget = {remaining: nodeBudget}, decision = decide(record, budget);
        return finish(record, report, decision.status, budget.remaining, decision.reason);
    }

    function explainHint(game, selected, nodeBudget) {
        if (nodeBudget === undefined) nodeBudget = 20000;
        const report = beginReport(nodeBudget), record = emptyRecord();
        if (!validBudget(nodeBudget)) return finish(record, report, INVALID, 0, 'The node budget must be an unsigned 32-bit integer.');
        if (!game || !selected) return finish(record, report, INVALID, nodeBudget,
            'A game, selected hint and output record are required.');
        if (!game.board || State.checkCandidates(game.puzzle, game.board.candidates, 0).status === BAD_PREMISES) {
            return finish(record, report, INVALID, nodeBudget, 'The source puzzle or current candidate masks are malformed.');
        }
        record.version = VERSION;
        record.background_rules = ROW_RULE;
        record.target = {kind: selected.kind, row: selected.row, column: selected.column, item: selected.item};
        record.selected_clue_index = selected.clue_index === undefined ? -1 : selected.clue_index;
        record.candidates = cloneMatrix(game.board.candidates);
        record.given = cloneMatrix(game.puzzle.given);
        record.source_clue_count = game.puzzle.clues.length;
        for (let i = 0; i < game.puzzle.clues.length; i++) {
            if (game.puzzle.clues[i].type !== 7) {
                record.support.push({index: i, clue: copyClue(game.puzzle.clues[i])});
            }
        }
        record.support_count = record.support.length;
        if (!validRecord(record)) return finish(record, report, INVALID, nodeBudget,
            'The selected hint must name a currently possible remove/choose target and a valid source clue index.');
        const budget = {remaining: nodeBudget}, decision = decide(record, budget);
        if (decision.status !== PROVED) return finish(record, report, decision.status, budget.remaining, decision.reason);
        const contrary = contraryCandidates(record);
        let complete = true;
        reduction: for (let pass = 0; pass < 2; pass++) {
            let i = 0;
            while (i < record.support_count) {
                const selectedClue = record.support[i].index === record.selected_clue_index;
                if (selectedClue !== (pass === 1)) { i++; continue; }
                if (!budget.remaining) { complete = false; break reduction; }
                const reduced = premisePuzzle(record, i);
                report.deletion_checks++;
                const trial = State.checkCandidates(reduced, contrary, budget.remaining);
                budget.remaining = trial.remaining_nodes;
                if (trial.status === UNKNOWN) { complete = false; break reduction; }
                if (trial.status === BAD_PREMISES) {
                    return finish(record, report, INVALID, budget.remaining, 'A reduced premise set failed validation.');
                }
                if (trial.status === UNSAT) {
                    record.support.splice(i, 1);
                    record.support_count = record.support.length;
                } else {
                    i++;
                }
            }
        }
        report.reduction_complete = complete ? 1 : 0;
        return finish(record, report, PROVED, budget.remaining, complete ?
            'Consistent premises prove this exact move. The completed deletion pass gives deletion-minimal clues relative to all frozen candidates, givens and row rules.' :
            'Consistent premises prove this exact move. Support reduction exhausted its budget; the retained clues are sufficient, with no minimality claim.');
    }

    return Object.freeze({
        SH_HINT_PROOF_VERSION: VERSION, SH_HINT_RULE_ROWS_ARE_PERMUTATIONS: ROW_RULE,
        SH_PROOF_INVALID: INVALID, SH_PROOF_UNRESOLVED: UNRESOLVED, SH_PROOF_PROVED: PROVED,
        SH_PROOF_REFUTED: REFUTED, SH_PROOF_INCONSISTENT: INCONSISTENT,
        explainHint: explainHint, replayHintProof: replayHintProof
    });
}));
