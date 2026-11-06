/* Browser protocol adapters over the retained native CLI JSON contract.
 * The host binds an admitted puzzle to its generator/table before calling us.
 * These read-only functions never use a hidden answer or mutate game state. */
(function (root, factory) {
    'use strict';
    if (typeof module === 'object' && module.exports) {
        module.exports = factory(require('./engine.js'), require('./assets.js'));
    } else root.SherlockProtocol = factory(root.SherlockCore, root.SherlockAssets);
}(typeof globalThis !== 'undefined' ? globalThis : this, function (Core, Assets) {
    'use strict';
    if (!Core || !Assets) throw new Error('SherlockCore and SherlockAssets must load before SherlockProtocol.');
    const FORMAT = 'sherlock-cli-1', U64_MAX = (1n << 64n) - 1n;
    const encoder = new TextEncoder();
    const forbidden = new Set(['solution', 'answer', 'first_solution', 'second_solution', '__proto__', 'constructor', 'prototype']);
    const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
    const integer = (value, low, high) => Number.isInteger(value) && value >= low && value <= high;
    function object(value) {
        return value !== null && typeof value === 'object' && !Array.isArray(value) &&
            (Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null);
    }
    function fail(message) { throw new TypeError(message); }
    function keys(value, required, optional, label) {
        if (!object(value)) fail(label + ' must be a JSON object.');
        const allowed = new Set(required.concat(optional || []));
        for (const key of Reflect.ownKeys(value)) {
            if (!allowed.has(key)) fail(label + ' has an unsupported field: ' + String(key) + '.');
        }
        for (const key of required) if (!own(value, key)) fail(label + ' is missing ' + key + '.');
    }
    function text(value, maximum, label) {
        if (typeof value !== 'string' || value.length > maximum || value.includes('\u0000')) fail('Invalid ' + label + '.');
    }
    function decimal(value, label) {
        if (typeof value !== 'string' || !/^(0|[1-9][0-9]{0,19})$/.test(value) || BigInt(value) > U64_MAX) {
            fail(label + ' must be a decimal uint64 string.');
        }
        return value;
    }
    /* Object callers cross the same bounded JSON-data boundary as text callers.
     * Reject accessors, cycles, sparse arrays and hidden-answer fields before
     * reading nested wrapper values. State/Core own their semantic validation. */
    function jsonData(value, rejectHidden) {
        let nodes = 0, characters = 0;
        const active = new Set();
        function visit(entry, depth) {
            if (++nodes > 30000 || depth > 64) fail('JSON structure is too large.');
            if (entry === null || typeof entry === 'boolean') return;
            if (typeof entry === 'number') {
                if (!Number.isSafeInteger(entry) || Object.is(entry, -0)) fail('JSON numbers must be canonical safe integers.');
                return;
            }
            if (typeof entry === 'string') {
                if (entry.includes('\u0000')) fail('NUL is not permitted in JSON strings.');
                characters += entry.length;
                if (characters > 1024 * 1024) fail('JSON input is limited to 1 MiB.');
                return;
            }
            if (!Array.isArray(entry) && !object(entry)) fail('Expected plain JSON data.');
            if (active.has(entry)) fail('Circular JSON data is not permitted.');
            active.add(entry);
            const array = Array.isArray(entry), names = Reflect.ownKeys(entry);
            if (array && (entry.length > 30000 || names.length !== entry.length + 1)) fail('Sparse or extended arrays are not permitted.');
            for (const key of names) {
                if (array && key === 'length') continue;
                if (typeof key !== 'string' || (array && (!/^(0|[1-9][0-9]*)$/.test(key) || Number(key) >= entry.length))) {
                    fail('Unsupported JSON property.');
                }
                if (rejectHidden && forbidden.has(key)) fail('Hidden-answer or reserved field is not permitted: ' + key + '.');
                characters += key.length;
                if (characters > 1024 * 1024) fail('JSON input is limited to 1 MiB.');
                const descriptor = Object.getOwnPropertyDescriptor(entry, key);
                if (!descriptor || !own(descriptor, 'value') || !descriptor.enumerable) fail('JSON accessors and hidden properties are not permitted.');
                visit(descriptor.value, depth + 1);
            }
            active.delete(entry);
        }
        visit(value, 0);
    }
    function error(code, message, detail) {
        return {format: FORMAT, kind: 'error', ok: false, error: Object.assign({code, message}, detail || {})};
    }
    function identity(puzzle) {
        const challenge = Core.toChallenge(puzzle);
        return {challenge_id: challenge.challenge_id, source: challenge.source, public_fingerprint: challenge.public_fingerprint};
    }
    function checkedIdentity(puzzle) {
        if (!Core.validatePuzzle(puzzle).valid) return {failure: error('puzzle_error', 'The engine returned malformed public puzzle fields.')};
        try { return {value: identity(puzzle)}; }
        catch (_) { return {failure: error('identity_error', 'The challenge identity could not be represented.')}; }
    }
    /* Same small answer grammar and diagnostic cursor as parse_answer in C.
     * Assets.parseJSON still owns JSON decoding; this cursor preserves the
     * native distinction between invalid input and a rejected permutation. */
    function answerGrammar(bytes) {
        let at = 0;
        const whitespace = () => { while ([32, 9, 13, 10].includes(bytes[at])) at++; };
        function invalid(message) { throw {message, byte_offset: at}; }
        function expect(wanted, reason) {
            whitespace();
            if (at >= bytes.length || bytes[at] !== wanted) invalid(reason);
            at++;
        }
        function key() {
            expect(34, 'The object must have exactly the key "solution".');
            const reason = 'The object must have exactly the key "solution"; other fields are not accepted.';
            for (const expected of 'solution') {
                if (at >= bytes.length) invalid(reason);
                let value = bytes[at++];
                if (value === 92) {
                    if (at >= bytes.length || bytes[at++] !== 117) invalid(reason);
                    value = 0;
                    for (let digit = 0; digit < 4; digit++) {
                        if (at >= bytes.length) invalid(reason);
                        const ch = bytes[at++], hex = ch >= 48 && ch <= 57 ? ch - 48 :
                            ch >= 65 && ch <= 70 ? ch - 55 : ch >= 97 && ch <= 102 ? ch - 87 : -1;
                        if (hex < 0) invalid(reason);
                        value = value * 16 + hex;
                    }
                }
                if (value !== expected.charCodeAt(0)) invalid(reason);
            }
            if (at >= bytes.length || bytes[at++] !== 34) invalid(reason);
        }
        try {
            whitespace(); const wrapped = bytes[at] === 123;
            if (wrapped) { at++; key(); expect(58, "Expected ':' after the solution key."); }
            expect(91, 'Expected an array of exactly six rows.');
            for (let row = 0; row < 6; row++) {
                expect(91, 'Each of the six rows must be an array.');
                for (let column = 0; column < 6; column++) {
                    whitespace();
                    if (at >= bytes.length || bytes[at] < 48 || bytes[at] > 53) {
                        invalid('Each item must be a single JSON integer digit from 0 through 5.');
                    }
                    at++;
                    if (column < 5) expect(44, 'Each row must have exactly six integer items.');
                }
                expect(93, 'Each row must end after exactly six integer items.');
                if (row < 5) expect(44, 'The answer must contain exactly six rows.');
            }
            expect(93, 'The answer must end after exactly six rows.');
            if (wrapped) expect(125, 'The solution object permits exactly one field and no trailing comma.');
            whitespace();
            if (at !== bytes.length) invalid('Trailing data after the JSON answer is not permitted.');
            return null;
        } catch (problem) { return error('invalid_answer', problem.message, {byte_offset: problem.byte_offset}); }
    }
    function verify(puzzle, input) {
        let encoded = input;
        if (typeof input !== 'string') {
            try { jsonData(input, false); encoded = JSON.stringify(input); }
            catch (_) { return error('invalid_answer', 'Expected a six by six JSON answer or an object with only a solution field.', {byte_offset: 0}); }
        }
        const bytes = encoder.encode(encoded);
        if (bytes.length > 65536) return error('answer_too_large', 'The JSON answer exceeds 65536 bytes.', {path: '-'});
        const malformed = answerGrammar(bytes);
        if (malformed) return malformed;
        let parsed;
        try { parsed = Assets.parseJSON(encoded); }
        catch (problem) { return error('invalid_answer', problem.message, {byte_offset: 0}); }
        const answer = Array.isArray(parsed) ? parsed : parsed.solution;
        const admitted = checkedIdentity(puzzle);
        if (admitted.failure) return admitted.failure;
        const result = Core.verifyAnswer(puzzle, answer);
        if (result.status === -1) return error('verification_error', result.reason);
        const index = value => value < 0 ? null : value;
        return Object.assign({format: FORMAT, kind: 'verification', ok: true}, admitted.value, {
            accepted: result.status === 1, reason: result.reason,
            violation: {row: index(result.row), column: index(result.column), clue_index: index(result.clue_index)}
        });
    }
    function analyze(puzzle, budget) {
        if (budget === undefined) budget = Core.DEFAULT_SOLVE_NODES;
        let nodes;
        try {
            if (typeof budget === 'bigint') nodes = budget;
            else if (typeof budget === 'number' && Number.isSafeInteger(budget)) nodes = BigInt(budget);
            else if (typeof budget === 'string' && /^[0-9]+$/.test(budget) && budget.length <= 128) nodes = BigInt(budget);
            else throw new TypeError();
            if (nodes < 0n || nodes > U64_MAX) throw new RangeError();
        } catch (_) {
            const detail = ['string', 'number', 'bigint'].includes(typeof budget) ? {argument: String(budget)} : {};
            return error('invalid_arguments', 'The node budget must be an unsigned decimal uint64 integer.', detail);
        }
        const admitted = checkedIdentity(puzzle);
        if (admitted.failure) return admitted.failure;
        const result = Core.analyze(puzzle, nodes);
        if (result.status === -1) return error('analysis_error', result.reason);
        return Object.assign({format: FORMAT, kind: 'analysis', ok: true}, admitted.value, {
            classification: result.classification, solutions_found: result.solution_count,
            solution_count_is_exact: result.status === 0 || result.status === 1,
            nodes: result.nodes, node_budget: nodes.toString(), reason: result.reason
        });
    }
    function session(value) {
        keys(value, ['format', 'game', 'ui'], ['saved_at', 'art_name'], 'Session');
        if (value.format !== 'sherlock-browser-session-1' || !object(value.game) || value.game.format !== 'sherlock-browser-save-1') {
            fail('A session must contain one browser game save.');
        }
        if (own(value, 'saved_at')) {
            text(value.saved_at, 32, 'session timestamp');
            const date = new Date(value.saved_at);
            if (!Number.isFinite(date.getTime()) || date.toISOString() !== value.saved_at) fail('Invalid session timestamp.');
        }
        if (own(value, 'art_name')) text(value.art_name, 1024, 'artwork name');
        keys(value.ui, ['mode', 'bank', 'selected_cell'], ['hint_display_ms'], 'Session UI');
        if (!['remove', 'choose', 'restore'].includes(value.ui.mode) || !integer(value.ui.bank, 0, 1) ||
            !Array.isArray(value.ui.selected_cell) || value.ui.selected_cell.length !== 2 ||
            !value.ui.selected_cell.every(n => integer(n, 0, 5))) fail('Invalid session UI selection.');
        if (own(value.ui, 'hint_display_ms') && value.ui.hint_display_ms !== null) decimal(value.ui.hint_display_ms, 'Frozen hint display');
        return {incoming: value.game, ui: value.ui};
    }
    function hint(value) {
        keys(value, ['kind', 'row', 'column', 'item', 'clue_index', 'explanation'], [], 'Recorded hint');
        if (!integer(value.kind, 0, 4) || ![value.row, value.column, value.item].every(n => integer(n, 0, 5)) ||
            !integer(value.clue_index, -1, 255)) fail('Invalid recorded hint.');
        text(value.explanation, 255, 'recorded hint explanation');
    }
    function action(value) {
        const fields = {
            new: ['source'], restart: [], remove: ['row', 'column', 'item'], choose: ['row', 'column', 'item'],
            restore: ['row', 'column', 'item'], undo: [], pause: [], resume: [], 'import-session': [],
            'hint-offered': ['bank', 'target'], 'hint-accepted': ['target', 'changed'],
            'archive-clue': ['clue'], 'move-clue': ['clue', 'slot']
        };
        if (!object(value) || !own(fields, value.action)) fail('Unsupported recorded action.');
        keys(value, ['action', 'elapsed_ms'].concat(fields[value.action]), [], 'Recorded action');
        decimal(value.elapsed_ms, 'Action elapsed time');
        for (const name of ['row', 'column', 'item']) if (own(value, name) && !integer(value[name], 0, 5)) fail('Invalid action cell.');
        if (own(value, 'bank') && !integer(value.bank, 0, 1)) fail('Invalid action clue bank.');
        if (own(value, 'clue') && !integer(value.clue, 0, 255)) fail('Invalid action clue index.');
        if (own(value, 'slot') && !integer(value.slot, 0, 20)) fail('Invalid action clue slot.');
        if (own(value, 'changed') && !integer(value.changed, -1, 1)) fail('Invalid action mutation result.');
        if (own(value, 'target')) hint(value.target);
        if (own(value, 'source')) {
            const source = value.source;
            if (!object(source)) fail('Invalid recorded source.');
            if (source.kind === 'original') {
                keys(source, ['kind', 'edition', 'table_format', 'number'], [], 'Recorded original source');
                if (source.edition !== 'Sherlock 1.50 UK' || source.table_format !== 1 || !integer(source.number, 0, 65535)) fail('Invalid recorded original source.');
            } else if (source.kind === 'native') {
                keys(source, ['kind', 'generator', 'generator_version', 'seed', 'limits'], [], 'Recorded native source');
                keys(source.limits, ['node_budget', 'max_attempts', 'max_givens'], [], 'Recorded generator limits');
                if (source.generator !== Core.GENERATOR_ID || source.generator_version !== 1 ||
                    !integer(source.limits.max_attempts, 1, 64) || !integer(source.limits.max_givens, 0, 3)) fail('Invalid recorded native source.');
                decimal(source.seed, 'Recorded seed'); decimal(source.limits.node_budget, 'Recorded generator budget');
            } else fail('Unsupported recorded source.');
        }
    }
    function evidence(value) {
        if (value === null) return;
        keys(value, ['status', 'record', 'report'], [], 'Hint evidence');
        keys(value.report, ['status', 'node_budget', 'nodes_used', 'deletion_checks', 'reduction_complete', 'reason'], [], 'Hint evidence report');
        if (!integer(value.status, -1, 3) || value.report.status !== value.status ||
            !integer(value.report.node_budget, 0, 4294967295) || !integer(value.report.nodes_used, 0, value.report.node_budget) ||
            !integer(value.report.deletion_checks, 0, 4294967295) || !integer(value.report.reduction_complete, 0, 1)) fail('Invalid hint evidence report.');
        text(value.report.reason, 2048, 'hint evidence reason');
        const record = value.record;
        keys(record, ['version', 'background_rules', 'target', 'selected_clue_index', 'candidates', 'given', 'source_clue_count', 'support_count', 'support'], [], 'Hint evidence record');
        keys(record.target, ['kind', 'row', 'column', 'item'], [], 'Hint evidence target');
        if (!integer(record.version, 0, 1) || !integer(record.background_rules, 0, 1) ||
            !integer(record.target.kind, 0, 2) || ![record.target.row, record.target.column, record.target.item].every(n => integer(n, 0, 5)) ||
            !integer(record.selected_clue_index, -1, 255) || !integer(record.source_clue_count, 0, 256) ||
            !Array.isArray(record.support) || record.support.length > record.source_clue_count || record.support_count !== record.support.length) fail('Invalid hint evidence record.');
        for (const name of ['candidates', 'given']) {
            if (!Array.isArray(record[name]) || record[name].length !== 6 ||
                !record[name].every(row => Array.isArray(row) && row.length === 6 &&
                    row.every(n => integer(n, name === 'given' ? -1 : 0, name === 'given' ? 5 : 63)))) fail('Invalid evidence matrix.');
        }
        for (const entry of record.support) {
            keys(entry, ['index', 'clue'], [], 'Supporting card');
            keys(entry.clue, ['type', 'a', 'b', 'c'], [], 'Supporting clue');
            if (!integer(entry.index, 0, 255) || !integer(entry.clue.type, 0, 7) || !integer(entry.clue.a, 0, 35) ||
                !integer(entry.clue.b, 0, 255) || !integer(entry.clue.c, 0, 255)) fail('Invalid supporting clue.');
        }
        // This is structural validation, not a claim that imported evidence is
        // proved. The host recomputes a pending proof from its admitted game.
    }
    function unwrap(data) {
        if (typeof data === 'string') data = Assets.parseJSON(data);
        jsonData(data, true);
        if (object(data) && data.format === 'sherlock-browser-repro-1') {
            keys(data, ['format', 'browser_version', 'native_reference', 'note', 'session', 'provenance', 'challenge', 'recent_actions', 'last_hint_evidence', 'assets'], [], 'Bug capture');
            if (data.browser_version !== 1 || typeof data.native_reference !== 'string' || !/^[0-9a-f]{40}$/.test(data.native_reference) ||
                !['generated-v1', 'local-original-table', 'imported-public-constraints'].includes(data.provenance)) fail('Invalid bug-capture version or provenance.');
            text(data.note, 4000, 'bug note');
            keys(data.assets, ['art_name', 'original_table_loaded', 'table_name', 'bytes_included'], [], 'Capture assets');
            text(data.assets.art_name, 1024, 'artwork name'); text(data.assets.table_name, 1024, 'table name');
            if (typeof data.assets.original_table_loaded !== 'boolean' || data.assets.bytes_included !== false) fail('Bug captures must omit original file bytes.');
            if (!Array.isArray(data.recent_actions) || data.recent_actions.length > 1000) fail('Invalid recent-action list.');
            for (const entry of data.recent_actions) action(entry);
            evidence(data.last_hint_evidence);
            const unwrapped = session(data.session), imported = Core.fromChallenge(data.challenge);
            const savedChallenge = Core.toChallenge(unwrapped.incoming.puzzle);
            if (JSON.stringify(Core.toChallenge(imported)) !== JSON.stringify(savedChallenge)) fail('The capture challenge differs from its saved game.');
            return unwrapped;
        }
        if (object(data) && data.format === 'sherlock-browser-session-1') return session(data);
        return {incoming: data, ui: null};
    }
    return Object.freeze({verify, analyze, unwrap});
}));
