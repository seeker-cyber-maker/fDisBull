# Browser semantic evidence

These authored notes and bounded receipts accompany the browser implementation.
They contain no original executable, artwork, puzzle-table payload, screenshot,
saved game or browser capture.

- [Public parity receipt](parity-public-review.json): resource-free execution
  comparison of the retained C implementation and JavaScript, including exact
  source hashes and compiler/runtime identity.
- [Independent parity review](parity-review.md): method, vectors, negative
  control and explicit scope limits. References to privately retained adapter
  observations are labels; the original inputs are not supplied here.
- [Core implementation note](core-note.md) and [state/proof note](state-note.md):
  APIs, semantic contracts and focused boundary checks.
- [Browser slice record](BROWSER-SLICE.md): implemented source, commands,
  protocol comparisons, import boundaries and separately reported UI progress.
- [Protocol receipt](protocol-review.json): 63 boundary checks and 54 complete
  native CLI JSON comparisons.
- [Actual-app integration receipt](app-import-review.json): 22 checks using the
  real application script with a minimal DOM, clock and storage adapter. This
  does not replace rendered-browser testing.
- [UI review](ui-review.md) and [UI receipt](ui-review.json): managed Chrome
  preview interactions, narrow-layout checks and explicit production/Space
  authentication limits. Original-art rendered pixel equality and real Space
  synchronization are not claimed.

Workspace paths retained inside JSON receipts identify the source observations;
they are labels, not a claim that private screenshots or hosting records are
part of this publication. No production Site URL or Space hosting receipt is
included here.

Run from the parent example's root directory:

```sh
node web/tests/parity.js --skip-private --report /tmp/sherlock-browser-parity.json
node web/tests/protocol-contract.js --native
```

These commands use authored fixtures and a freshly compiled native C reference.
They require Node and a C11 compiler; the browser game itself does not. They
establish finite native-to-JavaScript correspondence. They do not independently
prove original DOS fidelity or macOS AppKit execution, and they do not qualify
browser/Space storage merely by passing in Node.
