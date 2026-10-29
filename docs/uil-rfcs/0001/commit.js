// Authored synthetic source backing; not recovered DinoPark code.
function commit(values, ready) {
  const keys = ['cash', 'working', 'stock', 'pending', 'expense'];
  const state = Object.fromEntries(keys.map((k, i) => [k, BigInt(values[i])]));
  const encode = () => Object.fromEntries(keys.map(k => [k, state[k].toString()]));
  const checkpoints = [];
  if (ready) {
    state.stock = state.pending;
    checkpoints.push(encode());
    state.expense = (state.expense + 500n) & 0xffffffffn;
    checkpoints.push(encode());
    state.cash = state.working;
    checkpoints.push(encode());
  }
  return {status: ready ? 'complete' : 'refused', state: encode(),
    events: ready ? ['stock', 'expense', 'cash'] : [], checkpoints};
}
console.log(JSON.stringify(commit(process.argv.slice(2, 7), process.argv[7] === '1')));
