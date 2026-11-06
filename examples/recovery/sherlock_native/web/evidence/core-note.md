# Sherlock browser core

The browser core is implemented in replica/web/engine.js as dependency-free JavaScript. It is a direct realization of the retained authored C core and CLI public challenge contract. It adds no original executable, puzzle table, media or third-party solver.

## Behavior

- All eight relation types, including the constrained outer-pair meaning of NOT_BETWEEN.
- Public-row/given/clue answer verification without consulting the stored answer.
- Bounded Hall-subset and supported-tuple propagation with complete depth-first search, capped at two solutions. Search ordering, tie-breaking and budget accounting follow C.
- Native generator version 1 with unsigned 64-bit SplitMix64 wrap, unchanged random-call order, clue scoring, redundancy pruning, limits and display-slot ordering.
- Public FNV-1a fingerprint and the actual sherlock-cli-1 challenge shape.
- Strict public challenge import: exact admitted fields, sizes/ranges, source metadata, predicate definitions, clue arity, given object IDs, public fingerprint and challenge ID. Unknown hidden-answer fields are rejected.
- Bounded raw JSON parsing rejects duplicate keys, escaped duplicate aliases, decoded NUL, trailing documents, excess depth/size and non-finite numeric values.

The solver's solution witnesses and the generator's target remain internal APIs for testing. Public challenge serialization and player operations do not expose or read them.

## API details

The root namespace is SherlockCore in the browser; CommonJS exports the same object for Node.

- relationHolds(type,a,b,c) returns a Boolean.
- verifyAnswer returns {status,row,column,clue_index,reason} with the native numeric statuses.
- analyze returns native numeric status, classification, solution count, decimal-string nodes, witness matrices and reason. Absent witnesses retain C's zero matrix.
- generate returns {status,puzzle?,report}; no puzzle is returned on failure or budget exhaustion. Seeds and report nodes are decimal strings.
- publicFingerprint returns the 16-digit lowercase hexadecimal string.
- toChallenge returns the challenge object only. Generation metadata belongs outside that object.
- toDocument returns the full CLI puzzle envelope, including generation metadata when available.
- fromChallenge accepts the challenge object, the full CLI envelope or raw JSON text, and returns owned visible fields plus source, challenge ID, fingerprint and optional generation metadata.
- validatePuzzle checks public logical fields without reading display metadata or solution.
- parseJSON is available to the host for duplicate-aware file and textarea parsing.

Imported fingerprints establish content identity only. They do not authenticate an original table, a native seed mapping or supplied generation claims. A host requiring canonical provenance must bind the imported challenge to its local generated or table-loaded source. This is separate from verifying a submitted answer against the board's current visible constraints.

## Checks run

Running node replica/web/tests/core-boundaries.js passes **55 named checks**. They cover meaningful relation and solver controls, conflicting givens, repeated operands, hidden-answer getter poisoning, exact 64-bit seed handling, all 256 clues, zero/maximum budgets, rejected malformed input, defensive copies, strict JSON boundaries and challenge metadata consistency.

Initial Node generation observations:

| Seed | Solver nodes | Clues | Givens | Public fingerprint |
| --- | ---: | ---: | ---: | --- |
| 0 | 612 | 20 | 1 | cd2d37eb3c339602 |
| 42 | 580 | 20 | 2 | ba2a25023d51ede2 |
| 18446744073709551615 | 657 | 19 | 2 | 7a1faf5329c31c50 |

Seed 0 matches the retained native CLI fingerprint. The separate parity reviewer owns fresh compiled C comparisons; their receipt is the authority for the broader C-to-JavaScript qualification.

This work does not independently repeat the original-to-native recovery. It carries forward the original-fidelity limits in the native implementation and the prior hint slice.

## Source identities at handoff

| File | SHA-256 |
| --- | --- |
| replica/web/engine.js | 8a56c7dc8c318e6fa7d80f3eff90ae0e1cf29ba80c222b623ef0e8d6eb6ae696 |
| replica/web/tests/core-boundaries.js | 8bb22348733d1473bd8e3f4ad8ec9353a9821c45dc7309e4505402a809e1a046 |
| replica/core/sherlock_logic.c | 448f60902afff61e4fdafddeffcae684344f835ef815f388e681f6b378777688 |
| replica/core/sherlock_logic.h | ce315191a07f932575d2f1b5f46627a102ed4636683c104f9fe360dd30163a7f |
| replica/cli/sherlock_cli.c | 52ba140786953fb6730a675a1cdd7aaceebfdee3c410b85baeba3a9c49755976 |
