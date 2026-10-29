# DinoPark Z continuation on v0.24.0

PRs #18 and #19 are merged. This follow-up merges main `031b53e` and retains
its human capability chooser. Runtime commit
`31ad9a447cf143c70807999fb823a60fc2a732a6` is the current installed candidate.
Core and player metadata both report 0.24.0; this is a branch candidate, not a
new published release. Z consumes public scenes. The real DOS UDC emits the
unchanged executable and explicit resources; original game code supplies the
business effects. Qualification remains `original_bytes_only`, with zero
recovered semantic blocks.

## Installed candidate identity

| Artifact | SHA-256 |
|---|---|
| Core wheel | `13692833a2a134102bacdc1526af7990701d086f00360d131e6fc4f8fb005c4a` |
| Player wheel | `99e5deaa0a5ab48bacfda0adaa675fd37f3856c8dff7fc48eb1e5a4cce34eddb` |
| Native backend, retained 0.22 prefix | `1b0ec91f8a97fb34f336f898c3e9e02bf4559f314b2e4f92f3597f0c52c92277` |
| Original EXE | `2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c` |
| Original VARS.DAT | `5e4b32d6e4afd060d72da79bfcac27fdca493905a7e19e299729e31431a1d153` |

All 148 runtime payload files in the two wheels equal the committed source.
Documentation and distribution checks are recorded separately from native
acceptance. The source benchmark below passed; final Luna installed acceptance
is recorded in the next section once its receipts are sealed.

## Shared-context findings and corrections

**Catalogue page ownership.** Reading the encyclopedia leaves the catalogue on
its last page. The next Coelophysis intent previously clicked that page as
though it were the first. Bounded original mouse panning now restores and
qualifies the first page. Static species labels and price/control samples
replace animated portraits in its selection guards. Before BUY, the original
selected-species word must be 4 and its native price must be 1,250. Original
instructions at `334b:2066..2087` index 26-byte records using `DS:68a5`, read
prices from `DS:4550`, and post the expense. Reading the tiny bitmap as 1,500
was an observation error, not a discovered variable-price rule.

**Scroll recognition.** A closed encyclopedia can leave its software hand
cursor over toolbar probes. Enabled/disabled button bevels also change during
scrolling; even a profile shared by 159 stored views rejected a later valid
one at two bottom-row pixels. The final 48 exact probes use fixed capital-label
and catalogue-shelf pixels, excluding the entire toolbar widget area, cash,
calendar digits and animated artwork. All 170 retained catalogue references
match. In a separate 778-frame corpus it matches eight frames, adds no new
match, and stops matching two dinosaur-arrival views. These are qualification
results, not universal scene recognition. Cursor movement is parked away from
probes. The existing qualified parent, unchanged pending scene-request word,
known-modal rejection and final page/species/price qualification remain separate.
Pan rejection now records the exact failing frame and individual conditions.

**DinoMart exit.** Multiple installed and source runs confirmed the funded
Vegasaurus order but failed the subsequent single exit input. One direct
macro and an installed run without the optional oracle passed; that correlation
does not establish a backend cause. Optional witness queries were removed from
protected native commit callbacks and deferred until command completion.
A later oracle-enabled source run still failed after 150 ms of pointer
settling. The final adapter consumes 1,000 guest milliseconds after released
movement to the saved exit target, sends one 80 ms click, runs a continuous
2,000 guest milliseconds, and verifies the actual street. Bank controls retain
their tested 150 ms preparation. These are bounded input realizations, not a
universal readiness detector, automatic press retry or proof that witness
queries are observationally neutral.

**Operating views and notices.** Earlier retained frames show a clear later
park rejected at 14/32 terrain samples and a spring notice rejected at 31/32
because a sample crosses the season word. The operating profile has 40 exact
stable park anchors and rejects known modals; its quarter profile has 23 exact
anchors outside the season name. The original five imported profile files
remain byte-identical. In 656 stored frames, this recovered 24 clear later
park views and 14 spring-notice views; a further 122 frames retained the same
six park matches and introduced none. Other layouts and notices remain unknown.

A known quarter interruption returns `accepted` with partial effects only after
its native interruption event and a fresh matching modal context. During
entry the context is `park-entry.quarter-notice`, exposing acknowledgment only.
The original acknowledgment can return to the street before entry occurs.
The final adapter verifies that street, clears the pending notice and tells
the player to issue a new `go park` intent. It does not replay the interrupted
click or claim completed travel. Unknown/conflicting notices remain incomplete.

**Parking advice before food submission.** The Candidate 5 failure identifies
an original advice window over the opened meat menu, with a thumb button and
an existing 32-sample profile. The new adapter recognizes this only at the
pre-submission menu stage, while original balance checks remain active. It
returns accepted/partial with `food_order_submitted:false` and exposes
`dino_diner.parking-notice` with acknowledgment only. The acknowledgment uses
one original Enter input and requires a fresh unique diner, food-menu or street
view, rejects other notices/selected orders, and reasserts its saved scene.
Only a new public food-buy intent may continue; the earlier order is not replayed.
An acknowledgment with an unknown result stays unknown. The pending flag is
included in live checkpoints and blocks saving/navigation while advice awaits
handling. Actual final-candidate native acknowledgment is still being tested.
A source replay passed the entire route and named native load, but did not
encounter this advice. A separate natural-wait diagnostic observed 41 ordinary
food-menu frames without the advice; that is not a native acknowledgment pass.

**Repeated resumption.** Loading renumbers a selected native file to
`DINOSG.000` while preserving an internal title such as `agent001`. Deriving
the next title from free disk slot 001 therefore collides. The adapter now
selects an unused native title independently from the disk slot. Original game
code still writes the save, and 20 declared native fields are verified.

Z creates `zpark`, `zpark-002`, and later named revisions without overwriting.
`load park` selects the latest saved or explicitly loaded revision; named
objects expose `load zpark`. A selected `--load-save` bundle is validated and
copied into the owned library, making it loadable there. Up to 64 public named
backups are exposed; reaching the limit removes new-save availability without
blocking navigation. Public save guidance now teaches the actual Z grammar.
Three-, four- and five-profile legacy manifests are accepted only when their
original identities match; new manifests bind all six profiles. The imported
TextScene source hash is preserved separately from the adapted class hash.

**Sound.** At the user's request, the active Mac output was muted and verified.
Headless launch also explicitly sets the SDL dummy audio driver and disables
mixer and host MIDI output. This closes the host MIDI path that can bypass SDL.
Guest sound devices remain configured. Opt-in visible debugger audio behavior
is unchanged; Z uses headless mode.

## Native acceptance

Candidate 5 installed acceptance is sealed as **partial**. Its fresh primary
guest passed 30 commands covering the encyclopedia-to-Coelophysis route, setup,
initial food, replenishment, navigation and status. Its funded guest confirmed
Vegasaurus, the single exit, the quarter notice, acknowledgment to the street
and a new park-entry intent. It then failed opening the meat menu under a
parking-advice popup (32/32 existing samples). Only the menu-opening press was
sent: quantity selection, reservations, BUY and food confirmation were not
reached. That receipt remains failed/complete:false; no retry or acknowledgment
was attempted there. Save and named load were not reached. Both native children
and workers were reaped. Both 184-file compiled closures and all 192 canonical
source files/eight saves matched. All 148 payloads and 63 actual worker imports
per context were bound to the fresh installed Candidate 5. Three Candidate 2
legacy save bundles also validated offline.

Candidate 6 adds the explicit parking continuation below. Its final installed
Luna report is pending; the completed source replay and earlier partial native
evidence are separate claims.

The parent final source batch passed 19 public commands in **23.98 seconds**,
including startup and fresh load. One running context combined encyclopedia,
funded purchase, passive look, street exit, finances, interrupted park entry,
notice acknowledgment, explicit new park entry, food refill and saving; native
loading intentionally used a new guest. The optional native oracle was on.
The funded seed is an ordinary original-game save with earned cash; no cash,
calendar or save bytes were edited. Its initial builder receipt remains failed
on a later readiness hold. Independent file readback and a fresh load verified
its 20 fields; the native seed SHA-256 is
`94bad1065e7dfc00be6c6e4deb84074b55c9f8b7f0f7f1e6d2aaa083d37b82a9`.
At the protected Vegasaurus boundaries, committed cash was 26,941 before and
after, loan 4,290 before and after, reservation release 25,000, expense posted
25,000, and herd 1 before and after. Calendar was unchanged across those
protected boundaries; ordinary time elsewhere may change balances. Both native
and outer final receipts are completed; outer cleanup is confirmed.

Retained Candidate 2 installed evidence is separate: four primary native guests
passed 132 commands, including opening, refill, a natural Winter notice after
74 advance-time intents, acknowledgment, and three native save/fresh-load
cycles. Every load matched all 20 fields. Native titles were agent000,
agent001 and agent002; the decisive third guest retained agent001 in imported
slot 000 and wrote agent002 in new slot 001. Named backups were visible, but
that batch executed latest-default loads rather than named loads. This earlier
candidate used 0.23 packages and 144 bound payloads. Its funded context failed
after the confirmed order and remains failed. The operating profile, time and
native-save methods are retained; the final candidate adds further catalogue,
acknowledgment, presentation, witness and audio changes. Earlier evidence is not
upgraded into a final-candidate whole-module pass.

All failed discovery, Candidates 1–4 and source diagnostic contexts remain
preserved. New source-funded attempts 01–03 stopped without retry; 04 confirmed
exit but rejected the original street return after acknowledgment; 05 passed
the complete stated batch. No unknown purchase or exit was replayed in place.
A separate diagnostic engine-checkpoint restore reported completion but its
saved scene then became unavailable. That intervention remains a checkpoint
friction finding and is not evidence of a native disk-save failure or success.

## Source and package verification

- Focused continuation, shared scene/player, distribution and audio-launch tests:
  **124 passed, 2 skipped**.
- Required full checkout command, `python -m pytest -q`: **1,569 passed,
  118 skipped, 13 failed, 23 errors**. A fresh 0.24 main export had **1,539
  passed, 118 skipped, 13 failed, 23 errors**. All 36 failure/error identities
  match exactly; the full suite remains red in this environment.
- Candidate 5 extracted source-package focused checks: **113 passed, 2 skipped**.
  Core/player wheel and source-tarball archive policies passed. Final tool ZIP
  and documentation-archive checks are recorded after documentation is sealed.

## Friction for the next compiler release

1. Expose input-consumption readiness separately from visual scene matches.
   Released driver state and the expected image can precede a usable control.
2. Offer a bounded, non-interfering native observation batch. Extra diagnostics
   must not be assumed neutral merely because they request reads. The precise
   cause of the earlier exit variation remains unproved.
3. Give temporal view profiles a way to exclude cursor overlays, enabled-state
   widgets and moving artwork; keep authoritative economic commit proof separate.
4. Represent interrupted travel and its actual post-notice destination explicitly.
   Dismissing a notice can complete while the earlier journey remains incomplete.
5. Distinguish native disk slot, native title and public backup identity; expose
   portable named-load grammar through the provider contract.
6. Preserve individual failed-predicate evidence and diagnostic checkpoint scene
   restoration failures, alongside receipts that separate effects from cleanup.
7. Keep headless audio and MIDI silence explicit in launcher contracts.

These findings are delivered in this follow-up PR. Raw games, saves, databases,
images, environments and private reports remain outside Git. This is bounded
original-backed playability evidence, not full-game recovery, an independent
synthetic DinoPark implementation, an audio-content test or a model ranking.
