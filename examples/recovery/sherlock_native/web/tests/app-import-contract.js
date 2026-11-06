#!/usr/bin/env node
/* Execute the shipped browser modules and app.js together against a deliberately
 * small DOM/clock/storage adapter. This qualifies import/API wiring only. It is
 * not a browser, layout, accessibility, input-hit-testing or hosting test. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');
const C = require('../engine.js'), S = require('../state.js'), V = require('../protocol.js');
const web = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(web, 'index.html'), 'utf8');
const files = [...html.matchAll(/<script\s+src="([^"]+)"/g)].map(match => match[1]);
const SAVE_KEY = 'sherlock-replica-browser-v1';
const plain = value => JSON.parse(JSON.stringify(value));
let checks = 0;
async function check(name, operation) {
    try { await operation(); checks++; }
    catch (error) { error.message = name + ': ' + error.message; throw error; }
}
function attributes(text) {
    const out = {};
    for (const match of text.matchAll(/([a-z][a-z0-9-]*)="([^"]*)"/gi)) out[match[1]] = match[2];
    return out;
}
async function boot(options = {}) {
    const elements = [], ids = new Map(), globalListeners = new Map(), intervals = [], timers = [];
    const storage = new Map(), hostWrites = [];
    let now = 0, document;
    if (options.saved) storage.set(SAVE_KEY, JSON.stringify(options.saved));
    class Element {
        constructor(tag, attrs = {}) {
            this.tagName = tag.toUpperCase(); this.id = attrs.id || ''; this.className = attrs.class || '';
            this.dataset = {}; this.style = {}; this.children = []; this.listeners = new Map();
            this.hidden = false; this.disabled = false; this.inert = false; this.open = false;
            this.value = attrs.value || ''; this.textContent = ''; this.innerHTML = ''; this.options = [];
            this.attrs = {...attrs};
            for (const [key, value] of Object.entries(attrs)) if (key.startsWith('data-')) this.dataset[key.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = value;
            elements.push(this); if (this.id) ids.set(this.id, this);
        }
        setAttribute(key, value) { this.attrs[key] = String(value); }
        getAttribute(key) { return this.attrs[key] === undefined ? null : this.attrs[key]; }
        addEventListener(type, callback) {
            if (!this.listeners.has(type)) this.listeners.set(type, []);
            this.listeners.get(type).push(callback);
        }
        dispatch(type, event = {}) {
            for (const callback of this.listeners.get(type) || []) callback({target: this, preventDefault() {}, ...event});
        }
        click() { if (!this.disabled) this.dispatch('click'); }
        focus() { document.activeElement = this; }
        select() {}
        append(child) { this.children.push(child); }
        remove() {}
        replaceChildren(...children) { this.children = children; }
        querySelector(selector) {
            if (selector.startsWith('#')) return ids.get(selector.slice(1)) || null;
            if (selector.startsWith('.')) return elements.find(el => el.className.split(/\s+/).includes(selector.slice(1))) || null;
            if (selector === 'button') return this.children.find(el => el.tagName === 'BUTTON') || null;
            if (selector.startsWith('[data-focus=')) return null; // Presentation focus restoration is outside this seam.
            throw new Error('DOM adapter does not implement selector: ' + selector);
        }
        querySelectorAll(selector) {
            if (selector === '[data-mode]') return elements.filter(el => el.dataset.mode);
            if (selector === 'canvas[data-art]') return []; // No original artwork in these tests.
            if (selector === 'button:not(:disabled),input,textarea,select') return this.children.filter(el => !el.disabled);
            throw new Error('DOM adapter does not implement selector list: ' + selector);
        }
    }
    for (const match of html.matchAll(/<([a-z][a-z0-9-]*)\b([^>]*)>/gi)) {
        const attrs = attributes(match[2]);
        if (attrs.id || attrs.class || attrs['data-mode']) {
            const el = new Element(match[1], attrs);
            el.hidden = /\bhidden(?:\s|>|$)/.test(match[2]);
        }
    }
    for (const match of html.matchAll(/<select\b([^>]*)>([\s\S]*?)<\/select>/gi)) {
        const element = ids.get(attributes(match[1]).id); if (!element) continue;
        element.options = [...match[2].matchAll(/<option\b([^>]*)>/gi)].map(option => ({value: attributes(option[1]).value, selected: /\bselected\b/.test(option[1])}));
        element.value = (element.options.find(option => option.selected) || element.options[0] || {value:''}).value;
    }
    document = {
        activeElement: null, hidden: false,
        getElementById: id => ids.get(id) || null,
        createElement: tag => new Element(tag),
        addEventListener(type, callback) {
            if (!globalListeners.has('document:' + type)) globalListeners.set('document:' + type, []);
            globalListeners.get('document:' + type).push(callback);
        }
    };
    const context = vm.createContext({
        document, TextEncoder, Blob,
        performance: {now: () => now},
        localStorage: {getItem: key => storage.get(key) || null, setItem: (key, value) => storage.set(key, String(value))},
        navigator: {clipboard: {writeText: async () => {}}},
        URL: {createObjectURL: () => 'blob:unit-adapter', revokeObjectURL() {}},
        crypto: {getRandomValues: target => crypto.webcrypto.getRandomValues(target)},
        setTimeout: (callback, delay) => { timers.push({callback, delay}); return timers.length; },
        setInterval: callback => { intervals.push(callback); return intervals.length; },
        addEventListener(type, callback) {
            if (!globalListeners.has(type)) globalListeners.set(type, []);
            globalListeners.get(type).push(callback);
        },
        __hostWrite: state => { hostWrites.push(plain(state)); }
    });
    if (options.host) {
        vm.runInContext('globalThis.openai={widgetState:' + JSON.stringify(options.host) + ',setWidgetState(state){__hostWrite(state);return Promise.resolve();}};', context);
    }
    for (const file of files) vm.runInContext(fs.readFileSync(path.join(web, file), 'utf8'), context, {filename:file});
    async function flush() {
        const immediate = timers.filter(timer => timer.delay === 0); timers.splice(0, timers.length, ...timers.filter(timer => timer.delay !== 0));
        for (const timer of immediate) timer.callback();
        await new Promise(resolve => setImmediate(resolve));
    }
    await flush();
    const api = context.SherlockReplica;
    assert.ok(api, 'Actual app must expose SherlockReplica.');
    assert.doesNotThrow(() => api.snapshot(), ids.get('sh-notice').textContent);
    function state() {
        const snapshot = plain(api.snapshot());
        return {game: snapshot.game, ui: snapshot.ui};
    }
    function view() {
        return Object.fromEntries(['sh-board','sh-clues','sh-identity','sh-provenance','sh-clock','sh-outcome'].map(id => {
            const element = ids.get(id); return [id, {html: element.innerHTML, text: element.textContent}];
        }));
    }
    return {
        api, ids, storage, hostWrites, state, view, context, flush,
        async click(id) { assert.ok(ids.get(id), 'Control exists: ' + id); ids.get(id).click(); await flush(); },
        advance(ms) { now += ms; for (const callback of intervals) callback(); },
        async hostEvent(state) {
            const event = vm.runInContext('JSON.parse(' + JSON.stringify(JSON.stringify({detail:{globals:{widgetState:state}}})) + ')', context);
            for (const callback of globalListeners.get('openai:set_globals') || []) callback(event);
            await flush();
        }
    };
}
function browserSession(game, ui = {}) {
    return {
        format: 'sherlock-browser-session-1', saved_at: '2026-11-06T00:00:00.000Z',
        game: S.exportGame(game), ui: {mode:'remove',bank:0,selected_cell:[0,0],hint_display_ms:null,...ui}, art_name:'Built-in symbols'
    };
}
function rejectedAtomically(app, input, pattern) {
    const before = app.state(), beforeView = app.view(), beforeStorage = app.storage.get(SAVE_KEY);
    assert.throws(() => app.api.load(JSON.stringify(input)), pattern);
    assert.deepEqual(app.state(), before, 'Failed import changes no board, clue order, clocks, undo, outcome or UI selection.');
    assert.deepEqual(app.view(), beforeView, 'Failed import leaves the presented puzzle intact.');
    assert.equal(app.storage.get(SAVE_KEY), beforeStorage, 'Failed import does not overwrite persistence.');
}

(async () => {
    const app = await boot();
    await check('shipped script order boots the actual app with protocol installed', () => {
        assert.equal(app.state().game.puzzle.source.seed, '42');
        assert.ok(files.indexOf('protocol.js') > files.indexOf('assets.js'));
        assert.ok(files.indexOf('protocol.js') < files.indexOf('app.js'));
        assert.equal(app.ids.get('sh-identity').textContent, 'Generated seed 42');
    });
    const start = app.state().game;
    outer: for (let row = 0; row < 6; row++) for (let column = 0; column < 6; column++) {
        if (start.puzzle.given[row][column] >= 0) continue;
        const candidates = app.api.state().candidates[row][column];
        for (let item = 0; item < 6; item++) if (candidates & (1 << item)) {
            assert.equal(app.api.move({kind:'remove',row,column,item}), 1); break outer;
        }
    }
    app.advance(1234);
    const baseline = plain(app.api.snapshot());
    await check('test baseline contains a real edit and nonzero clock', () => {
        assert.equal(baseline.game.undo_count, 1); assert.equal(baseline.game.elapsed_ms, '1234');
    });
    for (const [label, change] of [
        ['reported nodes exceed budget', s => {s.game.puzzle.generation.nodes='1000001';}],
        ['reported attempts exceed limit', s => {s.game.puzzle.generation.attempts=17;}],
        ['in-budget nodes differ from canonical generation', s => {s.game.puzzle.generation.nodes='579';}],
        ['in-budget attempts differ from canonical generation', s => {s.game.puzzle.generation.attempts=2;}],
        ['unexpected outer hidden answer', s => {s.solution=[[0]];}],
        ['unexpected outer field', s => {s.extra='ignored?';}],
        ['unexpected UI field', s => {s.ui.extra=true;}],
        ['inapplicable frozen clock', s => {s.ui.hint_display_ms='1';}]
    ]) await check('atomic rejection: ' + label, () => {
        const bad = plain(baseline); change(bad); rejectedAtomically(app,bad);
    });
    await check('over-capacity public challenge is rejected before adoption', () => {
        const puzzle = {number:0,given:Array.from({length:6},()=>Array(6).fill(-1)),clues:Array.from({length:19},()=>({type:0,a:0,b:6,c:255})),original_slot:Array(19).fill(255)};
        rejectedAtomically(app,C.toDocument(puzzle),/clue-grid capacity/);
    });
    await check('textarea import uses the same rejecting boundary', async () => {
        const bad = plain(baseline); bad.solution = [[0]];
        const before = app.state(), beforeStorage = app.storage.get(SAVE_KEY);
        app.ids.get('sh-json').value = JSON.stringify(bad); await app.click('sh-load-json-text');
        assert.deepEqual(app.state(), before); assert.equal(app.storage.get(SAVE_KEY),beforeStorage);
        assert.match(app.ids.get('sh-notice').className,/sh-error/);
    });
    const generated = C.generate('43').puzzle, validGame = S.createGame(generated,180);
    S.tick(validGame,4567); S.setPaused(validGame,true);
    const valid = browserSession(validGame,{mode:'choose',bank:1,selected_cell:[3,4]});
    await check('valid full session restores board, clock and UI and persists', () => {
        const loaded = plain(app.api.load(JSON.stringify(valid)));
        assert.deepEqual(loaded.game,valid.game); assert.deepEqual(loaded.ui,valid.ui);
        assert.deepEqual(JSON.parse(app.storage.get(SAVE_KEY)).game,valid.game);
        assert.equal(app.ids.get('sh-identity').textContent,'Generated seed 43');
        assert.equal(app.ids.get('sh-agent-panel').hidden,true);
    });
    await check('legacy native save without report acquires canonical generation metadata', () => {
        const old = plain(valid); delete old.game.puzzle.generation;
        app.api.load(JSON.stringify(old)); assert.deepEqual(app.state().game.puzzle.generation,generated.generation);
    });
    await check('bare native challenge remains compatible and gets canonical metadata', () => {
        const doc = C.toChallenge(generated);
        app.api.load(JSON.stringify(doc)); assert.deepEqual(app.state().game.puzzle.generation,generated.generation);
        assert.deepEqual(plain(app.api.challenge()),C.toDocument(generated));
    });
    await check('agent analysis and verification call the canonical protocol', () => {
        assert.deepEqual(plain(app.api.analyze()),V.analyze(generated));
        assert.deepEqual(plain(app.api.verifySolution(JSON.stringify({solution:generated.solution}))),V.verify(generated,{solution:generated.solution}));
        assert.deepEqual(plain(app.api.verifySolution('[]')),V.verify(generated,'[]'));
    });
    await check('actual analysis and verification buttons show canonical envelopes', async () => {
        await app.click('sh-analyze'); assert.deepEqual(JSON.parse(app.ids.get('sh-diagnostic').textContent),V.analyze(generated));
        app.ids.get('sh-json').value=JSON.stringify({solution:generated.solution}); await app.click('sh-check-answer');
        assert.deepEqual(JSON.parse(app.ids.get('sh-diagnostic').textContent),V.verify(generated,{solution:generated.solution}));
        app.ids.get('sh-json').value='[]'; await app.click('sh-check-answer');
        assert.deepEqual(JSON.parse(app.ids.get('sh-diagnostic').textContent),V.verify(generated,'[]'));
        assert.match(app.ids.get('sh-notice').className,/sh-error/);
    });
    await check('challenge export and bug capture roundtrip without hidden answer fields', async () => {
        await app.click('sh-export-challenge'); assert.deepEqual(JSON.parse(app.ids.get('sh-json').value),C.toDocument(generated));
        const bug=plain(app.api.exportBug('Node integration capture'));
        assert.doesNotThrow(()=>V.unwrap(bug));
        const before=app.state(); app.api.load(JSON.stringify(bug)); assert.deepEqual(app.state(),before);
        const bad=plain(bug); bad.assets.solution=generated.solution; rejectedAtomically(app,bad);
    });
    await check('startup restores persisted state instead of default seed', async () => {
        const restored = await boot({saved:valid});
        assert.deepEqual(restored.state(),{game:valid.game,ui:valid.ui});
        assert.match(restored.ids.get('sh-notice').textContent,/Resumed/);
    });
    await check('Space saved state takes precedence and a rejected shared update is atomic', async () => {
        const host = {format:'sherlock-space-state-1',revision:'host-valid',session:valid};
        const restored = await boot({saved:baseline,host});
        assert.deepEqual(restored.state(),{game:valid.game,ui:valid.ui});
        const before = restored.state(), stored = restored.storage.get(SAVE_KEY);
        const bad = plain(valid); bad.game.puzzle.generation.nodes='0';
        await restored.hostEvent({format:'sherlock-space-state-1',revision:'host-invalid',session:bad});
        assert.deepEqual(restored.state(),before); assert.equal(restored.storage.get(SAVE_KEY),stored);
        assert.match(restored.ids.get('sh-notice').textContent,/could not be loaded/);
    });
    const pending = S.createGame(generated,20);
    S.tick(pending,5000); assert.equal(S.requestHint(pending),1); S.tick(pending,25000);
    const pendingSession = browserSession(pending,{hint_display_ms:'15000'});
    await check('inconsistent pending display clock is rejected atomically', () => {
        const bad=plain(pendingSession); bad.ui.hint_display_ms='21000'; rejectedAtomically(app,bad,/inconsistent/);
    });
    await check('pending restore preserves frozen display and deferred timeout until acceptance', async () => {
        app.api.load(JSON.stringify(pendingSession));
        assert.equal(app.state().game.hint_pending,1); assert.equal(app.state().game.elapsed_ms,'30000');
        assert.equal(app.state().ui.hint_display_ms,'15000'); assert.equal(app.ids.get('sh-clock').textContent,'00:15');
        assert.equal(app.ids.get('sh-new').disabled,true); assert.equal(app.ids.get('sh-pause').disabled,true);
        app.advance(10000); assert.equal(app.state().game.elapsed_ms,'40000');
        assert.equal(app.state().game.outcome,0); assert.equal(app.ids.get('sh-clock').textContent,'00:15');
        const apply=app.ids.get('sh-dialog-actions').children.find(button=>button.textContent.startsWith('Apply hint'));
        assert.ok(apply); apply.click(); await app.flush();
        assert.equal(app.state().game.hint_pending,0); assert.equal(app.state().game.elapsed_ms,'70000');
        assert.equal(app.state().game.outcome,3); assert.equal(app.state().ui.hint_display_ms,null);
    });
    const source_hashes = {};
    for (const file of ['index.html',...files,'tests/app-import-contract.js']) source_hashes['web/'+file]=crypto.createHash('sha256').update(fs.readFileSync(path.join(web,file))).digest('hex');
    console.log(JSON.stringify({suite:'browser-app-import-contract',checks,passed:true,
        scope:'Actual app script with minimal DOM, deterministic clock and storage; no browser rendering or hosting qualification.',source_hashes}));
})().catch(error=>{ console.error(error.stack||error); process.exitCode=1; });
