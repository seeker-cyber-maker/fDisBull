import assert from 'node:assert/strict';
import test from 'node:test';
import * as fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {performance} from 'node:perf_hooks';
import {setTimeout as sleep} from 'node:timers/promises';
import {observeOnce, parseViewerAX, pumpMailbox as rawPumpMailbox} from './observe_ownership.mjs';

const pumpMailbox = (tab, name, options) => rawPumpMailbox(tab, name, {ownerUid: process.getuid(), ...options});

const unknown = {owner: 'unknown', viewer_mode: 'unknown', connection: 'unknown'};
const dot = {owner: 'dot', viewer_mode: 'observe', connection: 'live'};
const human = {owner: 'human', viewer_mode: 'control', connection: 'live'};

// Synthetic AX fixtures follow the observed heading/panel/text-node structure.
// They contain no account, connection, computer or chat identifiers.
function panel({name = 'Ada', owner = 'dot', apostrophe = '\u2019', status = '', live = true,
                checkbox, ownerText, extra = ''} = {}) {
  const control = checkbox ?? (owner === 'dot' ? 'Take over, Value: 0' : 'Return control, Value: 1');
  const text = ownerText ?? (owner === 'dot' ? `23 text ${name}\n\t\t\t\t\t24 text  has control` : '23 text You have control');
  return `0 AXWebArea Test\n\t1 container\n\t\t13 heading ${name}${apostrophe}s computer, Value: 2\n\t\t15 button Close panel\n\t\t16 container Description: ${name}${apostrophe}s computer, ID: app-shell-tab-panel-fixture\n\t\t\t17 container\n${live ? '\t\t\t\t18 container Live computer\n' : ''}\t\t\t\t19 container\n\t\t\t\t\t${text}\n\t\t\t\t\t22 checkbox ${control}\n${status ? `\t\t\t\t20 text ${status}\n` : ''}${extra}`;
}

test('observed split-name Dot status and unchecked takeover', () => {
  assert.deepEqual(parseViewerAX(panel(), 'Ada'), dot);
});

test('checked return plus explicit local human status', () => {
  assert.deepEqual(parseViewerAX(panel({owner: 'human'}), 'Ada'), human);
});

test('straight and Unicode apostrophes identify the same selected computer', () => {
  assert.deepEqual(parseViewerAX(panel({apostrophe: "'"}), 'Ada'), dot);
  assert.deepEqual(parseViewerAX(panel({name: 'Luna\u2019s Echo'}), "Luna's Echo"), dot);
});

test('connecting and reconnecting invalidate otherwise plausible controls', () => {
  for (const status of ['Connecting', 'Connecting\u2026', 'Reconnecting...', 'Connecting to computer\u2026', 'Reconnecting to live session']) {
    assert.deepEqual(parseViewerAX(panel({status}), 'Ada'), unknown);
  }
});

test('disconnected UI never grants stale owner or mode', () => {
  assert.deepEqual(parseViewerAX(panel({status: 'Disconnected', owner: 'human'}), 'Ada'),
    {...unknown, connection: 'disconnected'});
});

test('stale checked checkbox with Dot status is refused', () => {
  assert.deepEqual(parseViewerAX(panel({checkbox: 'Return control, Value: 1'}), 'Ada'), unknown);
});

test('unchecked takeover with human status is refused', () => {
  assert.deepEqual(parseViewerAX(panel({owner: 'human', checkbox: 'Take over, Value: 0'}), 'Ada'), unknown);
});

test('another human is not the selected Dot or this viewer human', () => {
  assert.deepEqual(parseViewerAX(panel({ownerText: '23 text Another person has control'}), 'Ada'), unknown);
});

test('wrong Dot computer is refused', () => {
  assert.deepEqual(parseViewerAX(panel({name: 'Other Dot'}), 'Ada'), unknown);
});

test('closed panel and missing live marker remain unknown', () => {
  assert.deepEqual(parseViewerAX(panel().replace('15 button Close panel', '15 button Open computer'), 'Ada'), unknown);
  assert.deepEqual(parseViewerAX(panel({live: false}), 'Ada'), unknown);
});

test('ownership words in chat cannot establish a panel', () => {
  const chat = '0 AXWebArea Test\n\t1 text Ada has control\n\t2 text Live computer\n\t3 text checkbox Take over, Value: 0';
  assert.deepEqual(parseViewerAX(chat, 'Ada'), unknown);
});

test('unrelated chatter outside the selected panel does not change its owner', () => {
  const chatter = '\n\t30 container Chat\n\t\t31 text You have control\n\t\t32 text Connecting\u2026\n\t\t33 text Another Dot has control';
  assert.deepEqual(parseViewerAX(panel() + chatter, 'Ada'), dot);
});

test('unrecognized AX roles still bound the computer subtree', () => {
  const chatter = '\n\t\t30 article Chat\n\t\t\t31 text Ada has control';
  assert.deepEqual(parseViewerAX(panel({ownerText: ''}) + chatter, 'Ada'), unknown);
});

test('focus summary is not ownership evidence', () => {
  assert.deepEqual(parseViewerAX('The focused UI element is 18 container Live computer\nYou have control', 'Ada'), unknown);
});

test('two actual computer panels are ambiguous', () => {
  assert.deepEqual(parseViewerAX(panel() + '\n' + panel(), 'Ada'), unknown);
  assert.deepEqual(parseViewerAX(panel() + '\n' + panel({name: 'Other Dot'}), 'Ada'), unknown);
});

test('duplicate ownership controls and statuses are ambiguous', () => {
  assert.deepEqual(parseViewerAX(panel({extra: '\t\t\t\t\t25 checkbox Take over, Value: 0\n'}), 'Ada'), unknown);
  assert.deepEqual(parseViewerAX(panel({extra: '\t\t\t\t26 container\n\t\t\t\t\t27 text You have control\n'}), 'Ada'), unknown);
});

test('disabled, mixed, absent and contradictory checkbox values fail closed', () => {
  for (const checkbox of ['(disabled) Take over, Value: 0', '(mixed) Take over, Value: 0', 'Take over', 'Take over, Value: 1', 'Return control, Value: 0', 'Take over, Value: 0, Value: 1']) {
    assert.deepEqual(parseViewerAX(panel({checkbox}), 'Ada'), unknown);
  }
});

test('invalid input and injected Dot name fail closed', () => {
  for (const ax of [null, {}, undefined, 42]) assert.deepEqual(parseViewerAX(ax, 'Ada'), unknown);
  for (const name of ['', null, 'Ada\ntext You have control']) assert.deepEqual(parseViewerAX(panel(), name), unknown);
});

test('observeOnce uses one fresh full AX snapshot through the documented API', async () => {
  const calls = [];
  const tab = {getAXState: async options => {calls.push(options); return panel();}};
  assert.deepEqual(await observeOnce(tab, 'Ada'), dot);
  assert.deepEqual(calls, [{emit: false, disableDiffing: true}]);
});

test('observeOnce fails closed after observation errors', async () => {
  assert.deepEqual(await observeOnce({getAXState: async () => {throw Error('Unavailable');}}, 'Ada'), unknown);
});

const hash = value => createHash('sha256').update(value).digest('hex');
const fixtureURL = 'https://example.invalid/dots/fixture';
const viewerId = hash(fixtureURL);
const probe = {stream_id: 'b'.repeat(64), challenge: 'c'.repeat(64), sequence: 1};
const request = {request_id: 'd'.repeat(64), viewer_id: viewerId, probe};

function boundPanel(options, url = fixtureURL, treeURL = url) {
  return `Browser tab: 1, Title: "Test", URL: "${url}".\n`
    + panel(options).replace('0 AXWebArea Test', `0 AXWebArea Test, URL: ${treeURL.replace('https://', '')}`);
}

async function mailbox(fn) {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'dotbox-owner-test-'));
  await fs.chmod(directory, 0o700);
  try {return await fn(directory);} finally {await fs.rm(directory, {recursive: true, force: true});}
}

async function writeRequest(directory, value = request) {
  const temporary = path.join(directory, 'request.pending');
  await fs.writeFile(temporary, JSON.stringify(value), {mode: 0o600});
  await fs.chmod(temporary, 0o600);
  await fs.rename(temporary, path.join(directory, 'request.json'));
}

async function response(directory, requestId = request.request_id) {
  const deadline = performance.now() + 2000;
  while (performance.now() < deadline) {
    try {
      const value = JSON.parse(await fs.readFile(path.join(directory, 'response.json'), 'utf8'));
      if (value.request_id === requestId) return value;
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
    }
    await sleep(5);
  }
  assert.fail('No response to the current fixture request');
}

test('optional viewer binding requires matching current snapshot header and AX tree URL', () => {
  assert.deepEqual(parseViewerAX(boundPanel(), 'Ada', viewerId), dot);
  assert.deepEqual(parseViewerAX(boundPanel(), 'Ada', 'e'.repeat(64)), unknown);
  assert.deepEqual(parseViewerAX(panel(), 'Ada', viewerId), unknown);
  assert.deepEqual(parseViewerAX(boundPanel(undefined, fixtureURL, `${fixtureURL}-other`), 'Ada', viewerId), unknown);
  assert.deepEqual(parseViewerAX(boundPanel() + `\nBrowser tab: 2, Title: "Test", URL: "${fixtureURL}"`, 'Ada', viewerId), unknown);
});

test('AX byte, node and depth limits fail closed even with retained live controls', () => {
  assert.deepEqual(parseViewerAX(panel() + '\u00e9'.repeat(131073), 'Ada'), unknown);
  const nodes = Array.from({length: 4100}, (_, i) => `\t${100 + i} container Extra`).join('\n');
  assert.deepEqual(parseViewerAX(`${panel()}\n${nodes}`, 'Ada'), unknown);
  const depth = Array.from({length: 70}, (_, i) => `${'\t'.repeat(i + 1)}${100 + i} container Extra`).join('\n');
  assert.deepEqual(parseViewerAX(`${panel()}\n${depth}`, 'Ada'), unknown);
});

test('connecting sibling status also invalidates retained live controls', () => {
  assert.deepEqual(parseViewerAX(panel({extra: '\t\t40 text Reconnecting to computer\u2026\n'}), 'Ada'), unknown);
});

test('mailbox captures after a private request and processes its duplicate only once', async () => mailbox(async directory => {
  await writeRequest(directory);
  const ax = boundPanel();
  const calls = [];
  const records = [];
  const tab = {getAXState: async options => {
    assert.deepEqual(JSON.parse(await fs.readFile(path.join(directory, 'request.json'), 'utf8')), request);
    calls.push(options);
    return ax;
  }};
  const result = await pumpMailbox(tab, 'Ada', {directory, viewerId, durationMs: 100,
    onObservation: async record => {records.push(record);}});
  assert.deepEqual(result, {processed: 1, rejected: 0});
  assert.deepEqual(calls, [{emit: false, disableDiffing: true}]);
  assert.deepEqual(await response(directory), {request_id: request.request_id, event: {...probe, ...dot}});
  assert.equal((await fs.stat(path.join(directory, 'response.json'))).mode & 0o777, 0o600);
  assert.deepEqual(records, [{request_id: request.request_id, event: {...probe, ...dot}, ax_sha256: hash(ax), viewer_id: viewerId}]);
  assert.ok(!JSON.stringify(records).includes(fixtureURL));
  assert.deepEqual((await fs.readdir(directory)).sort(), ['request.json', 'response.json']);
}));

test('new receiver challenge requires a second current AX capture', async () => mailbox(async directory => {
  await writeRequest(directory);
  const second = {request_id: 'e'.repeat(64), viewer_id: viewerId,
    probe: {...probe, challenge: 'f'.repeat(64), sequence: 2}};
  let captures = 0;
  const records = [];
  const running = pumpMailbox({getAXState: async () => boundPanel({owner: ++captures === 1 ? 'dot' : 'human'})},
    'Ada', {directory, viewerId, durationMs: 250, onObservation: record => {records.push(record);}});
  await response(directory);
  await writeRequest(directory, second);
  assert.deepEqual(await response(directory, second.request_id), {request_id: second.request_id, event: {...second.probe, ...human}});
  assert.deepEqual(await running, {processed: 2, rejected: 0});
  assert.equal(captures, 2);
  assert.deepEqual(records.map(record => record.event.challenge), [probe.challenge, second.probe.challenge]);
}));

test('snapshot URL mismatch returns bound unknown and records only the observed hash', async () => mailbox(async directory => {
  await writeRequest(directory);
  const otherURL = `${fixtureURL}-other`;
  const records = [];
  await pumpMailbox({getAXState: async () => boundPanel(undefined, otherURL)}, 'Ada',
    {directory, viewerId, durationMs: 80, onObservation: record => {records.push(record);}});
  assert.deepEqual((await response(directory)).event, {...probe, ...unknown});
  assert.equal(records[0].viewer_id, hash(otherURL));
  assert.ok(!JSON.stringify(records).includes(otherURL));
}));

test('AX failure answers unknown without leaking the browser error', async () => mailbox(async directory => {
  await writeRequest(directory);
  const records = [];
  await pumpMailbox({getAXState: async () => {throw Error(fixtureURL);}}, 'Ada',
    {directory, viewerId, durationMs: 80, onObservation: record => {records.push(record);}});
  assert.deepEqual((await response(directory)).event, {...probe, ...unknown});
  assert.equal(records[0].ax_sha256, null);
  assert.equal(records[0].viewer_id, null);
  assert.ok(!JSON.stringify(records).includes(fixtureURL));
}));

test('wrong viewer or malformed probe never calls the browser', async () => {
  for (const value of [{...request, viewer_id: 'a'.repeat(64)}, {...request, probe: {...probe, sequence: true}},
    {...request, probe: {...probe, extra: 1}}, {...request, extra: 1}]) {
    await mailbox(async directory => {
      await writeRequest(directory, value);
      const result = await pumpMailbox({getAXState: () => assert.fail('Unexpected AX capture')}, 'Ada',
        {directory, viewerId, durationMs: 40});
      assert.deepEqual(result, {processed: 0, rejected: 1});
      await assert.rejects(fs.stat(path.join(directory, 'response.json')), {code: 'ENOENT'});
    });
  }
});

test('unsafe directory, request symlink, loose mode and oversized request are refused', async () => {
  await mailbox(async directory => {
    await fs.chmod(directory, 0o755);
    await assert.rejects(pumpMailbox({}, 'Ada', {directory, viewerId, durationMs: 20}), /unsafe|private/);
  });
  await mailbox(async directory => {
    const alias = `${directory}-link`;
    await fs.symlink(directory, alias);
    try {await assert.rejects(pumpMailbox({}, 'Ada', {directory: alias, viewerId, durationMs: 20}), /private/);}
    finally {await fs.unlink(alias);}
  });
  await mailbox(async directory => {
    await fs.writeFile(path.join(directory, 'target'), JSON.stringify(request), {mode: 0o600});
    await fs.symlink(path.join(directory, 'target'), path.join(directory, 'request.json'));
    await assert.rejects(pumpMailbox({}, 'Ada', {directory, viewerId, durationMs: 20}), /safely/);
  });
  await mailbox(async directory => {
    await writeRequest(directory);
    await fs.chmod(path.join(directory, 'request.json'), 0o644);
    await assert.rejects(pumpMailbox({}, 'Ada', {directory, viewerId, durationMs: 20}), /private/);
  });
  await mailbox(async directory => {
    await fs.writeFile(path.join(directory, 'request.json'), 'x'.repeat(4097), {mode: 0o600});
    await assert.rejects(pumpMailbox({}, 'Ada', {directory, viewerId, durationMs: 20}), /small/);
  });
  await mailbox(async directory => {
    await fs.mkdir(path.join(directory, 'request.json'), {mode: 0o700});
    await assert.rejects(pumpMailbox({}, 'Ada', {directory, viewerId, durationMs: 20}), /regular/);
  });
});

test('response symlinks cannot redirect or overwrite another file', async () => mailbox(async directory => {
  await writeRequest(directory);
  const target = path.join(directory, 'preserved');
  await fs.writeFile(target, 'untouched', {mode: 0o600});
  await fs.symlink(target, path.join(directory, 'response.json'));
  await assert.rejects(pumpMailbox({getAXState: async () => boundPanel()}, 'Ada',
    {directory, viewerId, durationMs: 100}), /safely/);
  assert.equal(await fs.readFile(target, 'utf8'), 'untouched');
}));

test('superseded request gets no response from its in-flight AX capture', async () => mailbox(async directory => {
  await writeRequest(directory);
  const second = {...request, request_id: 'e'.repeat(64), probe: {...probe, challenge: 'f'.repeat(64), sequence: 2}};
  let captures = 0;
  const records = [];
  await pumpMailbox({getAXState: async () => {
    if (++captures === 1) await writeRequest(directory, second);
    return boundPanel();
  }}, 'Ada', {directory, viewerId, durationMs: 120, onObservation: record => {records.push(record);}});
  assert.deepEqual(await response(directory, second.request_id), {request_id: second.request_id, event: {...second.probe, ...dot}});
  assert.equal(captures, 2);
  assert.equal(records.length, 1);
  assert.equal(records[0].request_id, second.request_id);
}));

for (const replacement of ['rename', 'delete']) {
  test(`request ${replacement} during an open read is discarded and the pump continues`, async t => mailbox(async directory => {
    await writeRequest(directory);
    const filename = path.join(directory, 'request.json');
    const original = await fs.stat(filename);
    const example = await fs.open(filename);
    const prototype = Object.getPrototypeOf(example);
    const read = prototype.read;
    await example.close();
    const second = {...request, request_id: 'e'.repeat(64),
      probe: {...probe, challenge: 'f'.repeat(64), sequence: 2}};
    let raced = false;
    let publication;
    t.mock.method(prototype, 'read', async function (...args) {
      const opened = await this.stat();
      if (!raced && opened.dev === original.dev && opened.ino === original.ino) {
        raced = true;
        if (replacement === 'rename') await writeRequest(directory, second);
        else {
          await fs.unlink(filename);
          publication = sleep(30).then(() => writeRequest(directory, second));
        }
        assert.equal((await this.stat()).nlink, 0);
      }
      return read.apply(this, args);
    });
    const records = [];
    let captures = 0;
    try {
      const result = await pumpMailbox({getAXState: async () => {captures++; return boundPanel();}}, 'Ada',
        {directory, viewerId, durationMs: 180, onObservation: record => {records.push(record);}});
      assert.equal(raced, true);
      assert.deepEqual(result, {processed: 1, rejected: 0});
      assert.equal(captures, 1);
      assert.deepEqual(records.map(record => record.request_id), [second.request_id]);
      assert.deepEqual(await response(directory, second.request_id),
        {request_id: second.request_id, event: {...second.probe, ...dot}});
    } finally {
      await publication;
    }
  }));
}

test('request with a second hard link remains unsafe', async () => mailbox(async directory => {
  await writeRequest(directory);
  await fs.link(path.join(directory, 'request.json'), path.join(directory, 'retained-link'));
  await assert.rejects(pumpMailbox({getAXState: () => assert.fail('Unsafe request reached browser')}, 'Ada',
    {directory, viewerId, durationMs: 80}), /private/);
}));

test('request owner UID is checked on the opened file', async t => mailbox(async directory => {
  await writeRequest(directory);
  const filename = path.join(directory, 'request.json');
  const original = await fs.stat(filename);
  const example = await fs.open(filename);
  const prototype = Object.getPrototypeOf(example);
  const stat = prototype.stat;
  await example.close();
  t.mock.method(prototype, 'stat', async function (...args) {
    const opened = await stat.apply(this, args);
    if (opened.dev === original.dev && opened.ino === original.ino) opened.uid++;
    return opened;
  });
  await assert.rejects(pumpMailbox({getAXState: () => assert.fail('Wrong owner reached browser')}, 'Ada',
    {directory, viewerId, durationMs: 80}), /private/);
}));

test('in-place request mutation still stops the pump', async t => mailbox(async directory => {
  await writeRequest(directory);
  const filename = path.join(directory, 'request.json');
  const original = await fs.stat(filename);
  const example = await fs.open(filename);
  const prototype = Object.getPrototypeOf(example);
  const read = prototype.read;
  await example.close();
  let changed = false;
  t.mock.method(prototype, 'read', async function (...args) {
    const opened = await this.stat();
    if (!changed && opened.dev === original.dev && opened.ino === original.ino) {
      changed = true;
      await fs.appendFile(filename, ' ');
    }
    return read.apply(this, args);
  });
  await assert.rejects(pumpMailbox({getAXState: () => assert.fail('Changed bytes reached browser')}, 'Ada',
    {directory, viewerId, durationMs: 80}), /changed/);
  assert.equal(changed, true);
}));

test('retired read cannot hide an unsafe replacement pathname', async t => mailbox(async directory => {
  await writeRequest(directory);
  const filename = path.join(directory, 'request.json');
  const original = await fs.stat(filename);
  const example = await fs.open(filename);
  const prototype = Object.getPrototypeOf(example);
  const read = prototype.read;
  await example.close();
  let replaced = false;
  t.mock.method(prototype, 'read', async function (...args) {
    const opened = await this.stat();
    if (!replaced && opened.dev === original.dev && opened.ino === original.ino) {
      replaced = true;
      await writeRequest(directory, {...request, request_id: 'e'.repeat(64)});
      await fs.chmod(filename, 0o644);
      assert.equal((await this.stat()).nlink, 0);
    }
    return read.apply(this, args);
  });
  await assert.rejects(pumpMailbox({getAXState: () => assert.fail('Unsafe replacement reached browser')}, 'Ada',
    {directory, viewerId, durationMs: 80}), /private/);
  assert.equal(replaced, true);
}));

test('finite pump does not wait indefinitely for AX or publish a late result', async () => mailbox(async directory => {
  await writeRequest(directory);
  let captureResolved = false;
  const result = await pumpMailbox({getAXState: async () => {await sleep(120); captureResolved = true; return boundPanel();}}, 'Ada',
    {directory, viewerId, durationMs: 35});
  assert.equal(captureResolved, false);
  assert.deepEqual(result, {processed: 0, rejected: 0});
  await sleep(130);
  await assert.rejects(fs.stat(path.join(directory, 'response.json')), {code: 'ENOENT'});
}));

test('pending receipt callback cannot keep the pump running or publish after its deadline', async () => mailbox(async directory => {
  await writeRequest(directory);
  let called = false;
  const result = await pumpMailbox({getAXState: async () => boundPanel()}, 'Ada',
    {directory, viewerId, durationMs: 35, onObservation: () => {called = true; return new Promise(() => {});}});
  assert.equal(called, true);
  assert.deepEqual(result, {processed: 0, rejected: 0});
  await assert.rejects(fs.stat(path.join(directory, 'response.json')), {code: 'ENOENT'});
}));

test('invalid duration and callback configuration cannot start the pump', async () => {
  for (const durationMs of [0, -1, 60001, Infinity, 1.5]) {
    await assert.rejects(pumpMailbox({}, 'Ada', {directory: '/not-opened', viewerId, durationMs}), TypeError);
  }
  await assert.rejects(pumpMailbox({}, 'Ada', {directory: '/not-opened', viewerId, onObservation: true}), TypeError);
});


test('restricted observer requires an explicit trusted host UID, not process access', async () => {
  await assert.rejects(rawPumpMailbox({}, 'Ada', {directory: '/not-opened', viewerId}), TypeError);
  await assert.rejects(rawPumpMailbox({}, 'Ada', {directory: '/not-opened', viewerId, ownerUid: -1}), TypeError);
});
