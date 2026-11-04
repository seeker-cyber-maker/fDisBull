# Installed DinoPark shutdown hotfix — November 3, 2026

This follow-up tests the installed headless DOSBox-X closing-popup hotfix. It
is separate from the earlier benchmark's external-object receipt-reader
correction and from the direct indexed-PNG scene-check performance experiment.
It does not package, install or modify runtime code.

## Installed target identity

The active selector resolves to
`/Users/Shared/fDisBull/releases/0.31.1-27b388d`, whose installation record names
source `27b388d38cc14f04842a81b8ec1a113460900f53`. The actual installed Python
host has this local addition to `DOSBoxRPC`'s headless spawn arguments:

```python
# Owned headless sessions must never wait for a host quit dialog.
arguments.extend(['-set', 'dosbox quit warning=false'])
```

The host module SHA-256 is
`b6112a55b710ca10de454f499e1c74a8dd6d684d9a71ddc8c36f31bd83f8c17e`.
The release payload records its earlier hash as
`c6f4ebcc66df1ffe5c1f3da6e8b5145f06f0fb7d399ad12be01c654353478a30`.
The two-line difference is an intentional local hotfix, not a claim that the
installed files still match the pristine release manifest. The native backend
remains byte-identical to its recorded payload, SHA-256
`bcf318de2a22d49d1b28888a312e12b774cf1f041fdd8862fc4ab3335ea59b60`.
The test must pin both the actual host and native binary rather than relying
on the package version alone.

At this verification's source head, `1a1a116`, !72 did not contain the installed
host addition. The subsequent [source and running-park follow-up](VERIFICATION-DINOPARK-SOURCE-SHUTDOWN-2026-11-03.md)
integrates that exact change and separately qualifies the source client.
This dated record continues to describe the installed combination tested here.

## Diagnostic scope and storage boundary

Admission of a new 200 MB capture workspace was refused: internal storage and
the CACHE physical pool were below the configured 20 GB reserve. No new bulk
work was started. The lifecycle check instead uses the explicit read-only
diagnostic exemption: installed pipe RPC, existing original inputs, small
transient native controls/logs and compact verification records. No new game
copy, FDB, screenshot, native state, build or runtime image is required.

The original executable is pinned to SHA-256
`2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c`.
Game-file inventories, module paths, hotfix arguments, selected audio settings,
owned PIDs, stop results and process reaping are checked explicitly. Other
agents' existing DOSBox-X processes and an existing ReportCrash process are
outside this batch and must not be stopped or counted as new failures.

Native host dialogs and crash reports are distinct observations. Successful
process reaping alone does not prove a popup was absent. Conversely, a crash
report already present before the batch is not evidence of a new crash.

## Results

Luna (`gpt-6-luna`) completed **eight fresh installed-client/native cycles**
with the corrected private harness, preceded by one initial contract-check
attempt: **nine launches total**. In the eight-cycle matrix, four stopped at
the original executable entry. Four ran through
60,000 requested guest milliseconds to the title frame, then paused; native
sparse RGB samples matched the retained original title witness at 320×200.
The batch sent no keyboard/mouse input, purchases, saves, restores or action
replays. It loaded the installed `fdisbull` and `dosbox_rpc` modules with
`PYTHONPATH` unset and bytecode writes disabled.

| Original-game stage | Shutdown path | Processes | Result |
| --- | --- | ---: | --- |
| Executable entry | `session.stop` → `execution.wait` → transport close | 2 | Both passed, reaped, exit 0 |
| Executable entry | Direct transport close | 2 | Both reaped, exit 0 |
| Paused title frame | `session.stop` → `execution.wait` → transport close | 2 | Both reaped, exit 0 |
| Paused title frame | Direct transport close | 2 | Both reaped, exit 0 |

Every actual spawn included `dosbox quit warning=false`, SDL dummy audio,
`mixer nosound=true` and `midi mididevice=none`. All nine processes were reaped
with exit code zero, no forced `kill` call and removed transient transport
directories. The normal termination signal used by the installed transport
was recorded separately from forced killing. In the corrected eight-cycle
matrix, RPC transport-close time was 8.959–19.223 ms, median 17.772 ms;
this excludes game startup and guest-stop
RPC latency and is not a general shutdown-latency guarantee.

The full existing private game inventory and installed/test identities stayed
unchanged. The test reused the prior private original-game copy; it created no
new game copy. Small controls, scripts, inventories and reports occupied
172,378 bytes at Luna's final native receipt, below the private 500 KB budget.

### First-cycle test-contract correction

The first test incorrectly required the emulator host process to exit within
two seconds **before** closing its RPC transport. `session.stop` ends the guest
session; the installed `DebugSession.close()` then closes the transport before
requiring process reaping. The test's premature wait timed out. Its `finally`
cleanup nevertheless used the installed transport and reaped that same process
with exit code zero in 19.352 ms, without forced killing or a matching crash.

The original failed report and script remain unchanged. A separate
`FIRST-CYCLE-ADJUDICATION.json` records the actual successful lifecycle and the
incorrect test assumption. The corrected private script ran the remaining seven
processes, followed by one additional fresh entry-stop case to complete eight
directly passing corrected cycles. No original guest was reopened or resumed,
and no runtime/installed source code was edited to make the test pass. Thus the
evidence is eight direct passes plus the initial lifecycle verified from its
retained receipts; the original failed test status remains preserved.

### Popup and delayed crash observations

Independent parent CUA running-app inventories found no DOSBox-X, ReportCrash,
Problem Report or Crash Report GUI owner at 01:09:30.943 UTC before the batch,
01:13:24.339 after the first cycle, 01:14:22.540 after the next seven cycles, and
01:14:47.851 during readback of the additional entry cycle. No closing popup
was observed. These are
bounded application/dialog-owner observations, not continuous desktop video.
The process receipts additionally exclude a warning that kept any owned
emulator alive awaiting user input. No GUI input or dismissal was sent.

The immediate batch receipts contained no new crash reports. A later report,
`dosbox-x-2026-11-03-201450.ips`, was detected during the parent's delayed scan.
It records SIGABRT in **PID 63534**, a process present before this test and
launched at 19:48:03 local time. None of the nine owned PIDs matches it. The
01:15:30.632 UTC CUA observation after that report again found no matching GUI
owner. The parent's verification explicitly retains this concurrent unowned
crash; it does not turn it into an owned test failure or claim that no DOSBox-X
crash occurred anywhere on the host. That older process's launch guards and
the cause of its crash were not qualified by this batch.

The bounded result supports **no reproduced closing popup across these eight
new headless starts/shutdowns with the installed hotfix**. It does not establish
that the hotfix prevents all native crashes, affects already-running processes,
or covers visible-window mode, loaded/running parks, timeout/fault shutdowns or
an entire playthrough. There was no baseline run deliberately disabling the
hotfix; causality beyond the observed installed combination remains untested.

## Evidence and handoff

Private evidence is under
`/Volumes/CACHE/fDisBull-scene-indexed-20261103/shutdown-hotfix-small/`:
`report.json`, `report-continuation.json`, `report-final-entry.json`,
`FIRST-CYCLE-ADJUDICATION.json`, the three measured scripts, game inventories,
`AGGREGATE.json` and `PARENT-FINAL-VERIFICATION.json`.
The first report SHA-256 is
`3531a626f47ea7a9796038b72a0202e5fb4bb8b5f7b40bff111d4b3c5da3333c`.
The original script SHA-256 is
`78aef8a86b88a4a66fd9c87cbfa78553bbb32b395b2c22290ae6019750d3062a`;
the remaining-cycle script is
`8ff4a8999bf410f1e27f1d25bed1e6a0b8384a0f6186be8992814eb3a1d1b5b1`.
Luna's aggregate receipt SHA-256 is
`bceb972f35b7e2980e8b86aa5eee9cae4345312f4e14b4147075c90a88ea8dfa`.

Only sanitized methodology and results are added to !72. Private game files,
crash-report bodies, full inventories and raw control reports stay outside Git.
No runtime production change, packaging, installation, release or merge was
performed. The screenshot/scene implementation's earlier 437-test result
retains its recorded source scope; this documentation follow-up adds the
installed-hotfix native lifecycle evidence, not a new full repository test run.
