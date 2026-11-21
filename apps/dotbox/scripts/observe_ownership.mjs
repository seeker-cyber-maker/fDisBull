// Observe the existing computer panel through CUA's accessibility snapshot.
// These are viewer UI observations, not a native or whole-computer input lease.
import {constants} from 'node:fs';
import * as fs from 'node:fs/promises';
import {createHash, randomBytes} from 'node:crypto';
import path from 'node:path';
import {performance} from 'node:perf_hooks';
import {setTimeout as sleep} from 'node:timers/promises';

const MAX_AX_BYTES = 256 * 1024;
const MAX_AX_NODES = 4096;
const MAX_AX_DEPTH = 64;
const MAX_MAILBOX_BYTES = 4096;
const HEX64 = /^[0-9a-f]{64}$/;
const unknown = () => ({owner: 'unknown', viewer_mode: 'unknown', connection: 'unknown'});
const normalize = value => value.normalize('NFC').replace(/[\u2018\u2019]/g, "'").replace(/\s+/g, ' ').trim();
const sha256 = value => createHash('sha256').update(value).digest('hex');

function nodesFromAX(ax) {
  const nodes = [];
  const stack = [];
  for (const line of ax.split('\n')) {
    // Keep every AX role in the tree, even when its semantics are irrelevant.
    // Ignoring a sibling role could incorrectly attach its text to the panel.
    const match = /^(\s*)\d+\s+(\S+)(?:\s+(.*))?$/.exec(line);
    if (!match) continue;
    const indent = match[1].replace(/\t/g, '    ').length;
    while (stack.length && stack.at(-1).indent >= indent) stack.pop();
    if (stack.length >= MAX_AX_DEPTH || nodes.length >= MAX_AX_NODES) return null;
    const node = {role: match[2], detail: (match[3] ?? '').trim(), indent, parent: stack.at(-1), children: []};
    node.parent?.children.push(node);
    nodes.push(node);
    stack.push(node);
  }
  return nodes;
}

function label(node) {
  return normalize(node.detail.replace(/^(?:\([^)]*\)\s*)+/, '').replace(/, (?:Value|Description|ID|Secondary Actions):.*$/, ''));
}

function descendants(node) {
  return node.children.flatMap(child => [child, ...descendants(child)]);
}

function textRuns(nodes) {
  const runs = [];
  for (const parent of nodes) {
    let parts = [];
    const finish = () => {
      if (parts.length) runs.push(normalize(parts.join(' ')));
      parts = [];
    };
    for (const child of parent.children) {
      if (child.role === 'text') parts.push(label(child));
      else finish();
    }
    finish();
  }
  return runs;
}

function snapshotBinding(ax, nodes) {
  const headers = [...ax.matchAll(/^Browser tab: [^\r\n]+, URL: "([^"\r\n]+)"\.?\s*$/gm)];
  const areas = nodes.filter(node => node.role === 'AXWebArea');
  if (headers.length !== 1 || areas.length !== 1 || areas[0].parent != null) return null;
  const areaURL = /, URL: (\S+)\s*$/.exec(areas[0].detail)?.[1];
  if (!areaURL) return null;
  try {
    const headerURL = new URL(headers[0][1]);
    const treeURL = new URL(areaURL.includes('://') ? areaURL : `https://${areaURL}`);
    if (headerURL.protocol !== 'https:' || headerURL.username || headerURL.password
        || headerURL.href !== treeURL.href) return null;
    return sha256(headers[0][1]);
  } catch {
    return null;
  }
}

function parseSnapshot(ax, dotName, viewerId) {
  if (typeof ax !== 'string' || Buffer.byteLength(ax, 'utf8') > MAX_AX_BYTES
      || typeof dotName !== 'string' || /[\r\n]/.test(dotName)) return {observation: unknown(), binding: null};
  const name = normalize(dotName);
  if (!name) return {observation: unknown(), binding: null};
  const nodes = nodesFromAX(ax);
  if (nodes == null) return {observation: unknown(), binding: null};
  const binding = snapshotBinding(ax, nodes);
  const result = observation => ({observation, binding});
  if (viewerId !== undefined && (typeof viewerId !== 'string' || !HEX64.test(viewerId) || binding !== viewerId)) return result(unknown());
  // This identifies the actual app panel, rather than matching words in chat.
  // The dynamic ID is never retained or returned.
  const panels = nodes.filter(node => node.role === 'container'
    && /^Description: .+, ID: app-shell-tab-panel-[^,\s]+(?:,.*)?$/.test(node.detail)
    && normalize(node.detail.match(/^Description: (.+), ID:/)[1]).endsWith("'s computer"));
  if (panels.length !== 1) return result(unknown());
  const panel = panels[0];
  const panelName = normalize(panel.detail.match(/^Description: (.+), ID:/)[1]);
  const expectedName = `${name}'s computer`;
  const siblings = panel.parent?.children ?? [];
  if (panelName !== expectedName
      || siblings.filter(node => node.role === 'heading' && label(node) === expectedName).length !== 1
      || siblings.filter(node => node.role === 'button' && label(node) === 'Close panel').length !== 1) return result(unknown());
  if (viewerId !== undefined) {
    let ancestor = panel;
    while (ancestor.parent) ancestor = ancestor.parent;
    if (ancestor.role !== 'AXWebArea') return result(unknown());
  }
  const contents = descendants(panel);
  const texts = textRuns([panel, ...contents]);
  const statuses = [...contents, ...siblings].filter(node => node.role === 'text' || node.role === 'container').map(label);
  if (statuses.some(value => /^(?:Disconnected|Computer disconnected|Connection lost|Computer unavailable|Computer offline|Offline|Connection failed|Unable to connect|Couldn't connect)(?:[.!\u2026]*)$/i.test(value))) {
    return result({...unknown(), connection: 'disconnected'});
  }
  if (statuses.some(value => /^(?:(?:Connecting|Reconnecting)\b|Loading\b|Preparing computer\b)/i.test(value))) return result(unknown());
  if (contents.filter(node => node.role === 'container' && label(node) === 'Live computer').length !== 1) return result(unknown());
  const checkboxes = contents.filter(node => node.role === 'checkbox' && ['Take over', 'Return control'].includes(label(node)));
  const owners = texts.filter(value => value === 'You have control' || / has control$/.test(value));
  if (checkboxes.length !== 1 || owners.length !== 1) return result(unknown());
  const checkbox = checkboxes[0];
  if (/\((?:[^)]*\b)?(?:disabled|mixed|busy)\b[^)]*\)/i.test(checkbox.detail)) return result(unknown());
  const values = [...checkbox.detail.matchAll(/, Value: ([^,]*)(?=,|$)/g)];
  const value = values.length === 1 ? values[0][1] : undefined;
  if (label(checkbox) === 'Return control' && value === '1' && owners[0] === 'You have control') {
    return result({owner: 'human', viewer_mode: 'control', connection: 'live'});
  }
  if (label(checkbox) === 'Take over' && value === '0' && owners[0] === `${name} has control`) {
    return result({owner: 'dot', viewer_mode: 'observe', connection: 'live'});
  }
  return result(unknown());
}

// An optional binding requires both the current tab header and tree URL to agree.
export function parseViewerAX(ax, dotName, viewerId) {
  return parseSnapshot(ax, dotName, viewerId).observation;
}

export async function observeOnce(tab, dotName) {
  try {
    const ax = await tab.getAXState({emit: false, disableDiffing: true});
    return parseViewerAX(ax, dotName);
  } catch {
    return unknown();
  }
}

function validatePrivate(stat, ownerUid, directory = false, retiredRequest = false) {
  return stat.uid === ownerUid
    && (stat.mode & 0o7777) === (directory ? 0o700 : 0o600)
    && (directory ? stat.isDirectory() : stat.isFile()
      && (stat.nlink === 1 || retiredRequest && stat.nlink === 0) && stat.size <= MAX_MAILBOX_BYTES);
}

function sameFile(a, b) {
  return a.dev === b.dev && a.ino === b.ino && a.size === b.size && a.mtimeMs === b.mtimeMs;
}

async function readPrivateFile(filename, checkDirectory, ownerUid, {discardReplaced = false} = {}) {
  await checkDirectory();
  let handle;
  try {
    handle = await fs.open(filename, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  } catch (error) {
    if (error.code === 'ENOENT') return null;
    throw new Error('Ownership mailbox file cannot be opened safely');
  }
  try {
    const before = await handle.stat();
    if (!validatePrivate(before, ownerUid, false, discardReplaced)) throw new Error('Ownership mailbox requires small private regular files');
    const buffer = Buffer.alloc(MAX_MAILBOX_BYTES + 1);
    let length = 0;
    while (length < buffer.length) {
      const {bytesRead} = await handle.read(buffer, length, buffer.length - length, null);
      if (!bytesRead) break;
      length += bytesRead;
    }
    const after = await handle.stat();
    if (length > MAX_MAILBOX_BYTES || !validatePrivate(after, ownerUid, false, discardReplaced) || !sameFile(before, after)) {
      throw new Error('Ownership mailbox file changed or exceeded its limit');
    }
    await checkDirectory();
    if (discardReplaced) {
      // Atomic publication can unlink an already-open request inode. Permit
      // nlink=0 only long enough to discard that retired read, never to publish
      // its contents. All ownership/type/mode/size checks above still apply.
      let current;
      try {current = await fs.lstat(filename);} catch (error) {
        if (error.code === 'ENOENT') return null;
        throw error;
      }
      if (!validatePrivate(current, ownerUid)) throw new Error('Ownership mailbox requires small private regular files');
      if (before.nlink === 0 || after.nlink === 0 || current.dev !== after.dev || current.ino !== after.ino) return null;
      if (!sameFile(after, current)) throw new Error('Ownership mailbox file changed or exceeded its limit');
    }
    return buffer.subarray(0, length);
  } finally {
    await handle.close();
  }
}

function validRequest(request) {
  const exact = (value, keys) => value != null && !Array.isArray(value) && typeof value === 'object'
    && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
  return exact(request, ['request_id', 'viewer_id', 'probe'])
    && typeof request.request_id === 'string' && HEX64.test(request.request_id)
    && typeof request.viewer_id === 'string' && HEX64.test(request.viewer_id)
    && exact(request.probe, ['stream_id', 'challenge', 'sequence'])
    && typeof request.probe.stream_id === 'string' && HEX64.test(request.probe.stream_id)
    && typeof request.probe.challenge === 'string' && HEX64.test(request.probe.challenge)
    && Number.isSafeInteger(request.probe.sequence) && request.probe.sequence > 0;
}

async function beforeDeadline(operation, deadline) {
  const remaining = deadline - performance.now();
  if (remaining <= 0) return {expired: true};
  let timer;
  try {
    return await Promise.race([
      Promise.resolve().then(operation).then(value => ({value})),
      new Promise(resolve => {timer = setTimeout(() => resolve({expired: true}), remaining);}),
    ]);
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Serve finite receiver-issued probes through an existing private local mailbox.
 * onObservation receives {request_id, event, ax_sha256, viewer_id}; it observes
 * a sample, not a delivery acknowledgement. No raw AX text or URL is returned.
 */
export async function pumpMailbox(tab, dotName, {directory, viewerId, ownerUid, durationMs = 30000, onObservation} = {}) {
  if (!Number.isSafeInteger(ownerUid) || ownerUid < 0
      || typeof directory !== 'string' || !path.isAbsolute(directory) || directory.includes('\0')
      || typeof viewerId !== 'string' || !HEX64.test(viewerId)
      || !Number.isInteger(durationMs) || durationMs < 1 || durationMs > 60000
      || (onObservation !== undefined && typeof onObservation !== 'function')) {
    throw new TypeError('Invalid bounded ownership mailbox configuration');
  }
  const started = performance.now();
  const deadline = started + durationMs;
  let directoryHandle;
  try {
    directoryHandle = await fs.open(directory, constants.O_RDONLY | constants.O_DIRECTORY | constants.O_NOFOLLOW);
  } catch {
    throw new Error('Ownership mailbox requires an existing private directory');
  }
  let originalDirectory;
  try {
    originalDirectory = await directoryHandle.stat();
  } catch {
    await directoryHandle.close();
    throw new Error('Ownership mailbox directory cannot be inspected');
  }
  const checkDirectory = async () => {
    const current = await fs.lstat(directory);
    if (!validatePrivate(originalDirectory, ownerUid, true) || !validatePrivate(current, ownerUid, true)
        || current.dev !== originalDirectory.dev || current.ino !== originalDirectory.ino) {
      throw new Error('Ownership mailbox directory is unsafe or was replaced');
    }
  };
  const requestPath = path.join(directory, 'request.json');
  const responsePath = path.join(directory, 'response.json');
  const seen = new Set();
  let processed = 0;
  let rejected = 0;
  try {
    await checkDirectory();
    while (performance.now() < deadline) {
      const raw = await readPrivateFile(requestPath, checkDirectory, ownerUid, {discardReplaced: true});
      if (raw != null) {
        const requestHash = sha256(raw);
        let request;
        try {request = JSON.parse(raw.toString('utf8'));} catch { /* Invalid probes get no observation. */ }
        const key = validRequest(request) ? request.request_id : requestHash;
        if (!seen.has(key)) {
          seen.add(key);
          if (!validRequest(request) || request.viewer_id !== viewerId) rejected++;
          else {
            const capture = await beforeDeadline(async () => {
              try {return await tab.getAXState({emit: false, disableDiffing: true});} catch {return null;}
            }, deadline);
            if (capture.expired) break;
            const ax = capture.value;
            const {observation, binding} = parseSnapshot(ax, dotName, viewerId);
            const event = {...request.probe, ...observation};
            const current = await readPrivateFile(requestPath, checkDirectory, ownerUid, {discardReplaced: true});
            if (current != null && sha256(current) === requestHash && performance.now() < deadline) {
              if (onObservation) {
                const callback = await beforeDeadline(() => onObservation({request_id: request.request_id, event: {...event},
                  ax_sha256: typeof ax === 'string' && Buffer.byteLength(ax, 'utf8') <= MAX_AX_BYTES ? sha256(ax) : null,
                  viewer_id: binding}), deadline);
                if (callback.expired) break;
              }
              const latest = await readPrivateFile(requestPath, checkDirectory, ownerUid, {discardReplaced: true});
              if (latest != null && sha256(latest) === requestHash && performance.now() < deadline) {
                await readPrivateFile(responsePath, checkDirectory, ownerUid);
                const temporary = path.join(directory, `response.json.${randomBytes(16).toString('hex')}`);
                let handle;
                try {
                  handle = await fs.open(temporary, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600);
                  await handle.chmod(0o600);
                  await handle.writeFile(`${JSON.stringify({request_id: request.request_id, event})}\n`, 'utf8');
                  await handle.sync();
                  await handle.close();
                  handle = null;
                  await checkDirectory();
                  if (performance.now() >= deadline) break;
                  await fs.rename(temporary, responsePath);
                  processed++;
                } finally {
                  await handle?.close();
                  await fs.unlink(temporary).catch(error => {if (error.code !== 'ENOENT') throw error;});
                }
              }
            }
          }
        }
      }
      const remaining = deadline - performance.now();
      if (remaining > 0) await sleep(Math.min(20, remaining));
    }
    return {processed, rejected};
  } finally {
    await directoryHandle.close();
  }
}
