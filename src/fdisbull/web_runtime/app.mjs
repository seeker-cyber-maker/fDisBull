// Generic UI controller. All behavior and state commits belong to the shell.
import {loadShell} from './shell.mjs';

const element = id => document.getElementById(id);
const ui = Object.fromEntries([
  'title', 'record', 'backend', 'new-record-name', 'add-record', 'inputs',
  'stored-values', 'record-revision', 'run-step', 'cancel-step', 'status', 'outputs',
].map(id => [id, element(id)]));
const ranges = {i8: [-128, 127], u8: [0, 255], i16: [-32768, 32767], u16: [0, 65535]};
const recordIds = new Set();
const controls = new Map();
let shell, plan, selectedRecord = 'city-a', currentAction = null, nextAction = 0, disposed = false;

function message(text, kind = '') {
  if (disposed) return;
  ui.status.textContent = text;
  ui.status.dataset.kind = kind;
}

function errorMessage(error) {
  return error instanceof Error ? error.message : String(error);
}

function labelFor(cell) {
  return typeof plan.state[cell]?.label === 'string' ? plan.state[cell].label : cell;
}

function render() {
  if (!shell || disposed) return;
  const capabilities = shell.capabilities();
  ui.backend.value = capabilities.selected;
  for (const option of ui.backend.options) {
    const available = capabilities.backends[option.value]?.available === true;
    option.disabled = !available;
    const title = option.value === 'wasm' ? 'CPU · WebAssembly' : 'GPU · WebGPU';
    option.textContent = title + (available ? '' : ' (unavailable)');
  }
  let state;
  try {state = shell.snapshot();}
  catch (error) {
    message('Cannot read the selected record: ' + errorMessage(error), 'error');
    return;
  }
  selectedRecord = state.id;
  recordIds.add(state.id);
  ui.record.replaceChildren(...Array.from(recordIds, id => {
    const option = document.createElement('option');
    option.value = id; option.textContent = id;
    return option;
  }));
  ui.record.value = selectedRecord;
  for (const [cell, input] of controls) {
    if (plan.state[cell].type === 'bool') input.checked = state.values[cell];
    else if (document.activeElement !== input) input.value = String(state.values[cell]);
  }
  const values = [];
  const visibleCells = new Set([...Object.values(plan.inputs), ...Object.values(plan.outputs)]);
  for (const cell of visibleCells) {
    const term = document.createElement('dt'), value = document.createElement('dd');
    term.textContent = labelFor(cell); value.textContent = String(state.values[cell]);
    values.push(term, value);
  }
  ui['stored-values'].replaceChildren(...values);
  ui['record-revision'].textContent = state.id + ' · revision ' + state.revision;
  ui['run-step'].disabled = currentAction !== null;
  ui['cancel-step'].disabled = currentAction === null;
}

function createInputs() {
  const cells = [...new Set(Object.values(plan.inputs))];
  for (const [index, cell] of cells.entries()) {
    const descriptor = plan.state[cell];
    if (!descriptor) throw Error('Input refers to an unknown state cell');
    const label = document.createElement('label');
    const caption = document.createElement('span');
    const input = document.createElement('input');
    caption.textContent = labelFor(cell);
    input.id = 'field-' + index; input.dataset.cell = cell;
    if (descriptor.type === 'bool') {
      input.type = 'checkbox'; label.classList.add('checkbox');
      label.append(input, caption);
    } else {
      if (!ranges[descriptor.type]) throw Error('Unsupported input cell type');
      input.type = 'number'; input.step = '1';
      [input.min, input.max] = ranges[descriptor.type].map(String);
      label.append(caption, input);
    }
    input.addEventListener('input', () => {
      let value;
      if (descriptor.type === 'bool') value = input.checked;
      else {
        value = input.valueAsNumber;
        if (!Number.isInteger(value) || !input.validity.valid) {
          message('Enter a valid ' + labelFor(cell) + ' value.', 'error');
          return;
        }
      }
      try {
        shell.editRecord(selectedRecord, {[cell]: value});
        message('Updated ' + labelFor(cell) + '.'); render();
      } catch (error) {message(errorMessage(error), 'error');}
    });
    controls.set(cell, input); ui.inputs.append(label);
  }
}

function showOutcome(result) {
  const captions = {committed: 'Committed', discarded: 'Discarded', refused: 'Refused', failed: 'Failed'};
  const caption = captions[result.status] || 'Unknown result';
  const reason = typeof result.reason === 'string' && result.reason ? ': ' + result.reason : '.';
  message(caption + reason, result.status === 'committed' ? 'success' : result.status === 'failed' ? 'error' : '');
  ui.outputs.textContent = result.status === 'committed'
    ? JSON.stringify(result.outputs, null, 2) : '';
}

async function runStep() {
  if (!shell || disposed || currentAction) return;
  const action = {token: ++nextAction, id: null};
  try {
    const ticket = shell.start();
    action.id = ticket.id; currentAction = action;
    ui.outputs.textContent = ''; message('Running step…'); render();
    const result = await shell.finish(ticket.id);
    if (!disposed && action.token === nextAction) showOutcome(result);
  } catch (error) {
    if (!disposed && action.token === nextAction) message('Failed: ' + errorMessage(error), 'error');
  } finally {
    // A cancelled job may complete after a new run has already started.
    if (currentAction === action) currentAction = null;
    render();
  }
}

function publicAPI(api) {
  return Object.freeze(Object.fromEntries([
    'addRecord', 'editRecord', 'removeRecord', 'selectEntity', 'selectBackend',
    'snapshot', 'start', 'finish', 'cancel', 'capabilities', 'describe', 'dispose',
  ].map(name => [name, (...args) => api[name](...args)])));
}

async function initialize() {
  shell = await loadShell(new URL('./', import.meta.url));
  plan = shell.describe().plan;
  if (!plan || !plan.state || !plan.inputs || !plan.outputs) throw Error('Invalid shell plan');
  if (disposed) {await shell.dispose(); return publicAPI(shell);}
  const title = typeof plan.title === 'string' && plan.title ? plan.title : 'Block shell';
  ui.title.textContent = title; document.title = title;
  for (const id of ['city-a', 'city-b']) {shell.addRecord(id, {}); recordIds.add(id);}
  shell.selectEntity(selectedRecord);
  createInputs();
  ui.record.disabled = ui.backend.disabled = ui['new-record-name'].disabled = ui['add-record'].disabled = false;
  ui.record.addEventListener('change', () => {
    try {shell.selectEntity(ui.record.value); render(); message('Selected ' + selectedRecord + '.');}
    catch (error) {message(errorMessage(error), 'error'); render();}
  });
  ui.backend.addEventListener('change', () => {
    try {shell.selectBackend(ui.backend.value); render(); message('Implementation selected.');}
    catch (error) {message(errorMessage(error), 'error'); render();}
  });
  ui['add-record'].addEventListener('click', () => {
    const id = ui['new-record-name'].value.trim();
    if (!id) {message('Enter a record name.', 'error'); return;}
    try {
      shell.addRecord(id, {}); recordIds.add(id); shell.selectEntity(id);
      render(); message('Added ' + id + '.');
    } catch (error) {message(errorMessage(error), 'error');}
  });
  ui['run-step'].addEventListener('click', runStep);
  ui['cancel-step'].addEventListener('click', () => {
    const action = currentAction;
    if (!action) return;
    try {
      shell.cancel(action.id);
      if (currentAction === action) currentAction = null;
      message('Cancellation requested. Any delayed result will be discarded.'); render();
    } catch (error) {message(errorMessage(error), 'error');}
  });
  globalThis.fdisbullShell = publicAPI(shell);
  document.body.dataset.shellState = 'ready';
  render(); message('Ready.');
  return globalThis.fdisbullShell;
}

addEventListener('pagehide', () => {
  disposed = true; currentAction = null;
  if (shell) void Promise.resolve(shell.dispose()).catch(() => {});
}, {once: true});

globalThis.fdisbullShellReady = initialize();
void globalThis.fdisbullShellReady.catch(error => {
  document.body.dataset.shellState = 'failed';
  message('Unable to start: ' + errorMessage(error), 'error');
});
