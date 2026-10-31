# DinoPark residual analysis and original-native entry verification

This follows the [content-accounting pass](VERIFICATION-DINOPARK-CONTENT-ACCOUNTING-2026-10-31.md)
and works through its 172 partial jobs, 201 no-modeled-reference entry hypotheses
and 13 resource candidates. It includes two analyzer fixes, generic regression
tests, retained per-entry findings and two gpt-6-luna verification tasks.

Source baseline: `0f9715a7f385dd1dc635eefb9377052059899d96`, with the analyzer
changes included in this PR. The existing native backend remains the macOS arm64
0.26.1-f783f2a DOSBox-X executable, SHA-256
`bcf318de2a22d49d1b28888a312e12b774cf1f041fdd8862fc4ab3335ea59b60`.
The supplied original executable remains SHA-256
`2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c`.
Its mapped, relocated project-image hash is a separate identity. No distribution
package, installation, release or original-game file patch was made. Sound
stayed off.

## The 172 partial jobs

Of the old partial results, 171 exhausted the 20,000-step dataflow budget. One
other retained result had stopped at a 512-instruction CFG snapshot. Increasing
the flow budget was not the remedy: a real 14-instruction input reproduced an
endless alternation of symbolic register identities.

The fixes in `flowdata.py` address two mechanisms:

- An unqualified call invalidated known register values but could leave old
  identities for unknown values, including registers read only later. The
  solver now inventories the IR's register names and retires those identities
  at the call boundary. Explicit callee clobber contracts still preserve the
  other register identities. Unknown stack cleanup also gets a fresh identity.
- A loop join replaced its earlier may-state with only the latest predecessor
  contributions. Equal and conflicting symbolic identities could alternate
  forever. The join now retains earlier uncertainty, so lost facts are not
  repeatedly reintroduced. Budget exhaustion still reports partial status.

The register inventory also handles shared or cyclic unused metadata without
looping. The analysis revision changes to `monotone-symbols-3`, invalidating
old derived results when auto-analysis is requested. Original instruction
facts, operands and byte versions remain intact.

The first revision completed 116 old partial jobs. The monotone-join revision
completed the remaining 56. The legacy CFG snapshot was refreshed from stored
native facts under the existing configured instruction limit. One newly pending
control-flow job then completed on a normal continuation pass.

Final stored status is **1,582 done, zero partial, zero pending**, using the
same **20,000 flow steps per job**. Luna joined every one of the original 172
keys to the final results and independently checked their status, source
identity and budgets. The largest final flow used **1,964 steps**. Representative
original 14-instruction graphs converge in 25 and 33 steps. Reopening the project
retains the result; the tool also exported a real SVG from a stored native CFG.

This is closure of the implemented bounded passes. Unknown operations, dynamic
targets, function ownership and whole-program semantic equivalence remain
separate questions.

## The 201 entry hypotheses

Every candidate received an individual native-fact body inspection. There are
**183 closed entry-body graphs** and **18 retaining unresolved transfers**;
these are not 18 new budget-partial jobs. Thirty-five bodies contain conditional
tool-described DOS, BIOS or audio-service candidates. None acquired a certified
function boundary merely by completing a pass.

Two missed reference channels were recovered:

- A priority-ordered, six-byte initializer table publishes near or far callback
  targets. Three of its six records target the old 201-entry set. The supplied
  finalizer range is empty.
- DOS interrupt-vector publication identifies three more targets in that set.
  Partial-register facts matter: a known selector can be split across the high
  and low register bytes. Publication remains distinct from invocation.

Luna ran the prepared observer against the original executable, validating the
entry bytes and relocation adjustment before installing one-shot observations
at all 201 exact segmented PCs. No guest data/register edits, forced calls,
forced resource loads or game-code changes were used.

| Evidence for the original 201 candidates | Count |
| --- | ---: |
| Original native PC reached in retained cohorts | 41 |
| Initializer or interrupt publication targets | 6 |
| Overlap between those two sets | 5 |
| At least one of those positive evidence types | 42 |
| Neither positive evidence type qualified | 159 |

All three initializer-table targets were reached naturally. Positive PC
witnesses from a held cohort remain valid observations, but do not turn that
cohort into a passing gameplay test. A PC witness does not certify complete
function effects. The 159 remaining candidates are not certified dead code.

Forty-two provenance-bearing comments were added to the derived analysis
project through the annotation API, without replacing existing comments or
inventing canonical call edges. Raw instructions, addresses, body exports,
register snapshots and the complete 201-row ledger remain private.

## Native batches, readiness and held outcomes

The provider bootstraps the original game before reading public requests. Three
readiness-gated runs took **68.309, 69.389 and 69.442 seconds** to reach its ready
receipt. Sending the first observation immediately exhausted the player's
60-second whole-request deadline. A proposed 180-second request timeout was
correctly rejected before launch by the existing validation limit.

The private client now waits, with a finite deadline, for the existing atomic
ready receipt in its fresh work directory, matching its live native PID to the
owned launch and requiring no pending action. It then uses the unchanged public
60-second request limit. No public request is sent before readiness. Narrowing
the observer to the active question also removes redundant file/actor probes.

The final batch reused one guest to reach the office, bank, street, DinoMart,
General Store, employment office and diner. Buying the already-qualified desert
plot satisfied the provider's business-access guard. Four later status,
inventory and park requests were rejected with confirmed no effects in the
current projection. Completing the batch loop does not mean all requests passed
or that the entire park is playable in that state.

A separate earlier batch held a Coelophysis purchase as **incomplete/unknown**:
the picked view matched, but the following selected-view witness did not. The
provider required recovery and the purchase was not replayed. The later batch
avoided that purchase and all other unneeded economic actions. No complete
playthrough or successful dinosaur purchase is claimed by this pass.

The three readiness-gated native runs have explicit native exit-code-0 cleanup
receipts. Two earlier timed-out runs have no surviving owned native PID but
lack a final native exit-code certificate; their return codes remain unknown.
The invalid-timeout experiment launched no guest. Worker exit code alone is not
used as a gameplay or shutdown certificate.

## The 13 resource candidates

Luna hash-checked and scanned all 183 intake files, byte zero through EOF, for
case-insensitive full filenames, bare basenames, and space/NUL-padded DOS 8.3
forms. Text hits such as branding, ordinary words and `OFFICE.PIC` were kept
distinct from references to the candidate files. The review also inspected main
executable filename literals, formatter patterns, stored reader callers and the
configuration chain. Those are bounded producer searches.

| Candidates | Current disposition |
| --- | --- |
| `BUS.ACT`, `PEOPLE.ACT` | Valid legacy actor resources; no producer in the recovered actor filename set; ordinary word hits do not establish resource use |
| `OFFICE.ACT` | Valid actor content; `OFFICE.PIC` references do not establish use of this separate file; alternate UI use remains unproved |
| `MECC.PIC` | Valid frame; no exact indexed-pixel or pixel-plus-palette match among the other 165 frames; branding text does not establish a filename producer |
| Eight candidate ABT files | No exact decoded PCM-and-rate match against the other 36 files; no candidate basename or padded-name hit in the scanned intake; use remains unresolved |
| `SBP1FM.ADV` | Byte-identical to `MIDPAK.ADV`; the configuration's different `SBPFM.ADV` name and recorded `.AD`/`.COM` reads do not prove this alias filename was opened |

The eight sound candidates are `CLICK11.ABT`, `DINO1.ABT`, `EARSQK.ABT`,
`NEONA1.ABT`, `NEONB1.ABT`, `RICOCHE2.ABT`, `SQUEAK.ABT` and `TING1.ABT`.
The comparisons reuse the earlier original-native decoder outputs; no audio
was played or decoder fixture unnecessarily rerun. Exact-buffer/frame
inequality does not rule out excerpts, palette reindexing or compositing.

All 13 now have explicit identity, content-comparison and producer-search
records. None is certified globally unused. Entry-only native cohorts supply
no negative file-use evidence: their file probes were deliberately disabled.

## Verification and follow-ups

- **91 affected tests passed**, including generic regressions that fail on the
  old call-identity and loop-join behavior, explicit-ABI preservation, finite
  budget stops and cyclic-metadata handling.
- The fresh full macOS run recorded **2,056 passed, 130 skipped, 12 failed and
  23 errors**. A clean Git checkout of the unchanged baseline recorded 2,051
  passed, 130 skipped, 12 failed and 23 errors. The failing/error node IDs match
  exactly; the five added regressions pass. Managed-code dependencies are
  absent and native macOS compiler commands do not build the ELF fixtures. The
  full suite is not reported green.
- Luna independently verified the original 172-key join, all final flow
  budgets and the distinct original-file/project-image identities, as well as
  the candidate corpus checks and native PC evidence.
- Original game files and earlier sealed packets are preserved; failed and
  held experiments remain in the new private packet
  `residual-analysis-20261031-01`. No packaging or system activation occurred.

Observed friction for the next implementation pass:

1. Expose provider startup readiness/progress separately from action-request
   deadlines. The private owned-receipt wait is a working local prototype;
   it is not a new public protocol feature in this PR.
2. Recover typed initializer and register-passed OS callback references, with
   explicit priority, segment and selector provenance. Keep publication, PC
   observation and complete effect execution distinct in graph queries.
3. Retain pending/unknown actions through readback and shutdown. The held
   selected-view witness needs a stable discriminator or qualified read-only
   reconciliation; another purchase click is not a recovery method.
4. Keep confirmed-no-effect refusals available to a batch controller so it can
   continue independent checks. Current projection qualifications must remain
   distinct from original-game rules and from a complete-playthrough claim.
5. Make missing native shutdown certificates visible even when no owned process
   remains. Private wrappers must also propagate service exit status rather
   than treating worker code 0 as proof of a successful intent.
6. Preserve nullable/unknown service descriptions. The private body-inspection
   summary initially mishandled an unsupported service's null contract; its
   already-written 201 bodies were reconciled against original facts without
   rerunning a native action.

The committed implementation changes are the analyzer fixes and their tests.
The remaining runtime/observer proposals stay prospective.
