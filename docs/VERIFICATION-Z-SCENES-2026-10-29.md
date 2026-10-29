# Z scene consumer verification — 29 October 2026

Candidate from 0.22.0 source `85839c54266a0efbb3db6678701b23d86ff7dd22`.
The installed core was independently selected from `0.22.0-75bbd7e` with isolated
Python; installed files were not modified. Native/debugger processes were not
started. The adapter, standalone player and fixtures are candidate source.

## Reproduced release conditions

The public `examples/z/verify_release.py` runs finite subprocesses with output
redirected to private files. No large payload is sent to the chat.

| Probe | Installed 0.22.0 result | Candidate treatment |
| --- | --- | --- |
| Repeated text through `il-run` | 53,583-byte valid input, 13,152,686-byte output, exit 0 | Z rejects action text over its conservative 32 KiB budget before effects; general core output budgeting remains follow-up |
| Silent TCP peer | Installed player did not finish within the 1.5-second outer limit; the probe killed/reaped it | Configured 0.2-second socket inactivity limit ended the candidate with exit 1 |
| Silent/partial local content service | New interface, absent from installed release | Whole-request deadline stops and reaps the worker; connection cannot retry an uncertain action |

These are bounded output/hang observations, not an observed native crash or
proof of why conversation retrieval fails. The separate ongoing investigation
reported retrieval errors; this verification makes no causal claim about them.
No crashed conversations, account state or existing running sessions were changed.

## Debugger-free content execution

The authored key-and-gate content ran with the installed 0.22.0 IL evaluator
and candidate adapter/player. Taking the key, unlocking, going north and looking
completed with exit 0 and 272 stdout bytes. A deterministic external protocol
driver completed two live turns with `agent_done` and memory checkpoints.
It is a protocol test, not a model benchmark or a claim of intelligence.

A source-mapping test decodes authored v3 attribute instructions into IL,
stores their source-checked immutable revision, closes/reopens the project,
and opens the object through Z. Source corruption refuses loading. This
exercises UDL-to-UIL correspondence and the consumer boundary without a debugger;
it is not original Zork or DinoPark parity evidence.

Tests cover passive reads, inventory and navigation, source revision identity,
stale/hidden targets, malformed packages, unsupported host capabilities, known
commits outside follow-up coverage, output amplification, failed transport,
checkpoint scope, parser aliases and standalone subprocess cleanup. Existing
player/distribution/IL tests remain part of the affected checks. Full-suite and
CI results are recorded in the change's PR; local baseline failures are retained
as failures rather than relabelled passing.

## Explicit limits

The scene envelope only projects current shared-IL semantics. It does not add
native UDC pass-through, full source reconstruction, original simulation time,
media execution, durable saves or a general benchmark service. The standalone
player stays independent of the disassembler package; only the selected scene
service imports fDisBull. Library-owned generic streams still require the caller
to supply timeout policy. Socket inactivity limits do not bound a trickling peer's
whole request; the local-process route supplies that stronger deadline.

Fresh affected check: **74 passed, 1 skipped**. Required `python -m pytest -q`:
**1,433 passed, 116 skipped, 13 failed, 23 errors**, retaining the same 36
baseline failure/error identities. All 26 new tests passed. The local full suite
is not green; foreign-ELF fixtures, optional managed dependencies and the
previous CLI failure remain outside this change.
