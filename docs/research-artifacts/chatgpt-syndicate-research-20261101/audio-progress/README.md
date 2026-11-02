# Local Syndicate audio continuation

Start with [REPORT.md](REPORT.md) and the
[source-free evidence summary](evidence/audio-progress-summary.json).
No GitHub query or write was performed. The local PR is not submitted.

## Contents

- REPORT.md: natural DOSBox service observations, loop experiment and limits.
- evidence/audio-progress-summary.json: sanitized measurements, exact source
  identities and hashes/locators for privately retained raw evidence.
- tools/: a pinned, original-instruction callback experiment. No original driver
  bytes, memory snapshots or compiled launcher are included.
- LOCAL_PR_ADDENDUM.md: proposed implementation/skill requirements for the pending
  PR. Historical evidence and fresh tests are explicitly distinguished.
- CHECKSUMS.sha256: hashes for the delivered text/source files.

## Reproduce the six callback cases using an owned original

This is a **Linux x86-64 trusted-input diagnostic**, not a DOS runtime or a security
sandbox. It requires i386 compatibility execution, permitted ptrace, a local C
compiler, Python and Capstone. The tested versions were Python 3.13.5 and Capstone
5.0.9. No tool downloads or installations are performed by these scripts.

Use the exact GAMEFM.DLL identified in REPORT.md. The preparation tool rejects
other source hashes. The destination must be new, private and outside Git. It
contains original code after preparation and must not be published.

```sh
python tools/prepare_fm_profile.py /path/to/owned/GAMEFM.DLL /new/private/fm-profile
SYNDICATE_PRIVATE=/new/private/fm-profile python tools/run_cases.py
SYNDICATE_PRIVATE=/new/private/fm-profile python tools/repeat_delay.py
```

Read `summary.json` and `delay-continuation-summary.json` in that private profile.
Both must report `all_expected: true`, and every case must report successful
child cleanup. The intended no-delay negative control reports
`instruction_budget`, not `returned`. The maximum is 8,000 instructions per case;
wall/CPU bounds are also applied. Existing summary files are refused, not replaced.
Use another new directory for another complete run.

The separate continuation script reuses only its preceding prepared-state result,
not a DOS checkpoint. The mixed code/data image is RWX in the isolated child;
pre-step instruction checks reject changed original instruction windows. This
profile is for one pinned benign driver, not arbitrary input.

The one-object LX reader is a research component, not a general supported LX
loader. Run normally, without Python `-O`; its narrow structural assertions are
part of its checks. The fixed source-hash gate is mandatory.

Raw private output contains source-derived state and must stay outside Git and
public deliveries. Only the source-free summary and authored scripts belong in
this bundle. The original DOSBox service trace needs the user's original game
and configured backend; these six isolated cases do not reproduce that live run.

## Publication status

The original local PR patch is unchanged. The new addendum and evidence need
reconciliation with accepted upstream content when access is restored. A separate
updated pending-PR archive preserves the older draft and all addenda. No helper
is scheduled and no remote publication has been attempted.
