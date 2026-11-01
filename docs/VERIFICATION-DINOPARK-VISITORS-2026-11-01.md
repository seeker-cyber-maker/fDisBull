# DinoPark visitor gates and standing-probe continuation — 2026-11-01

This continues the retained original-backed park from
[the preparation/probe batch](VERIFICATION-DINOPARK-PARK-PROBES-2026-11-01.md).
It is a bounded, assisted investigation, not a whole-game or unused-code proof.
Luna owned all live guest commands; a second Luna performed the static slice.
The parent independently checked public results and the failed scene observation.
Sound stayed off. No package, installation, release or merge was performed.

## Source and retained context

- Original EXE SHA-256:
  `2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c`.
- Native-qualified runtime source: `51fadb52151d226d898402f7cb143bc0cbd5d9dd`;
  preceding documentation delivery: `1115898c1406173b6f062b76ff22c2a6d63040ff`.
  This follow-up changes documentation, not the frozen worker's runtime source.
- Same native-04 guest, run `1a2d23eca38044daa1dfdc4421661bd4`, native PID 15028,
  worker 14996, controller 14946. A retained run is not a fresh guest or a
  checkpoint/RNG equivalence claim.
- Continuation admission: conservative 256 MiB on CACHE with the user's
  approved 20 GB reserve for this bounded native validation. It passed with
  26,843,078,656 destination-pool bytes free. The 40 GB default remains the
  policy for other bulk work. A 64 MiB full proposal-worktree admission on
  CODEX was refused; no full checkout or bulk workspace was created there.
  The separate proposal used existing Git objects and small document/control
  files, leaving this live runtime worktree unchanged during the batch.

## Normal park continuation

Luna sent exactly **32 additional `advance time` commands**, each using the
existing 1,000-guest-ms action, in five cohorts of 4, 8, 8, 8 and 4. Each cohort
had public status and actual native probe-inventory checks. One interval is not
a promise of exactly one simulated day.

The parent independently verified all ten cohort inventories against the
persisted run mapping (static load 1000h, runtime load 0824h): all 97 selected
entries mapped to actual enabled execution breakpoints with `once=False`, zero
first hits and zero inventory-query execution/input/restore deltas. The last
such inventory is ticket 0219, before the later held route; a new inventory
during that hold was unavailable through the loaded controller's gate.

| Native report field | Start | Last qualified park report, ticket 0218 |
| --- | --- | --- |
| Year / month indices | 0 / 0 | 0 / 1 |
| Day / weekly counters | 4 / 4 | 2 / 5 |
| Cash | 2,411 | 5,967 |
| Loan | 5,000 | 4,885 |
| Guides | 1 | 1 |
| Small-feeder stock | 20 | 12 |
| Dinosaurs | 1 Coelophysis, pen record 10 | 1 Coelophysis, pen record 10 |
| Hunger counter | 0 | 0 |

This extends coverage through weekly processing and the first month rollover.
Food and loan values changed during ordinary execution; a whole-period cash
delta is not a direct attendance measurement. The separate park-open/closed
boolean remains unqualified. No host clock, guest date or game calendar was
edited, and no new guest replaced the retained one.

## Recovered visitor conditions

The static slice selected **2,482 stored instruction rows** and checked their
bytes against the hash-bound original EXE after the declared MZ relocations,
with **zero mismatches**. These are selected source facts, not newly executed
native visitor-value readbacks or additional whole-binary coverage.

The parent repeated the byte check independently: 2,482 selected rows contain
2,416 distinct address/byte pairs, with zero mismatches.

The current-main mechanics notes at commit
`498c0887f8d15ca3b2fb3dc8994d2de24e144273` supplied attributed leads. The
conditions below were checked against the original code and parameter/string
files; old notes were not promoted directly to fresh runtime evidence.

| Original location | Recovered condition or role |
| --- | --- |
| `38FF:4E1D..4E22` | Increment internal day and call attendance at `38FF:211F`. |
| `4020:BFDF/BFE1` | 32-bit numerical attendance used by the original previous-day visitor readout. |
| `38FF:22D0..2315`, `4020:6FAC` | Initial reach is 20 with no parking units, otherwise 35 times parking units; multiply by a daily factor of 1–3, then limit the initial capacity term before later modifiers. |
| `38FF:2525` | Signed terrain/category value `6FAE <= -1` explicitly clears attendance. It is not a universal park-open flag. |
| `38FF:25EE`, `2705` | Missing guides incurs a percentage penalty; zero guides alone is not the zero-attendance gate. A zero sum over staff slots is a separate zeroing condition. |
| `38FF:2717..272B`, `BF9B/BF9D` | `BF9D != 0 && BF9B == 0` clears attendance. Writers connect this to pipeline/highway closure events and a seven-step countdown. |
| `BFCB + 4*CCFA` → `BF56/BF58` | Select scheduled ticket price. Original parameters initialize 350 cents; the current live price was not read back. |
| `38FF:2818..286A` | Post numerical attendance times selected price /100 to cash, followed by a separate concessions calculation in the daily caller. |

Species/pen capacity, advertising, pen/fence grades, price bands, terrain/season,
staffing, hunger, closures and first-year support participate in the calculation.
The source's per-pen catalogue lookup uses the pen slot rather than silently
substituting species ID. Price bands are <=250 cents: 200%, <=500: 100%,
<=750: 50%, <=975: 25%. Normal controls use 50..950-cent values in 50-cent
steps and lock the current quarter after internal day zero. No price or clock
edit was attempted.

The office selector-100 path at `302C:2AF0` tests `BFDF/BFE1`, selects the
zero-attendance message or formats the nonzero quantity as yesterday's visitor
count. This confirms the numerical readout's meaning. The older upper-right
ticket-stack hotspot is an attributed UI lead; its current native hit target
and rendered readout were not newly qualified. The frozen Z catalogue exposes
no named visitor/ticket-price action, and no guessed command was substituted.

Selected initialization code uses DOS date/time services for RNG seeding. This
attendance chain does not establish a rare real-world-weekday condition; the
inspected date helper does not retain DOS's returned weekday byte. Host wall
time, emulated RTC and game calendar must remain distinct.

## Actor activity and BUS.ACT / PEOPLE.ACT

Numerical attendance and actor replenishment have different gates:

1. `38FF:27F0` derives population target `4020:BFBF`, normally attendance divided
   by supplied parameter 2, capped at 32.
2. Park callback `23C5:081A` includes `23C5:0E2C..0E5D`, comparing target BFBF
   with count `452E`. When more records are wanted and countdown `BA90 == 0`,
   it calls `23C5:153F`; the path sets a random **15–24-update** delay.
   This is an update count, not milliseconds or calendar days.
3. The creator uses a 32-record pool through `A5EE/A5F0`, stride 48. Its inspected
   calls are PRNG/stack-check helpers, with **no ACT/file-loader call** in that
   body. Initializer `23C5:190C..1994` also handles a nonzero-attendance fallback.
4. Park initialization supplies fixed `park.act` to the full reader and
   publishes the park callback. A record-creation hit would still need an
   explicit filename/load/render edge to establish BUS.ACT or PEOPLE.ACT use.

The best next read-only discriminators are BFDF[4], BFBF[2], 452C/452E, BA90,
BF9B/BF9D and the selected price, with mapping/identity guards. These are
meaningful fields for selective value probes; arbitrary padding is not.
The loaded controller has no generic guarded value-read/wait operation, and
the public park projection lacks the attendance/ticket controls. This limits
the current native link between the recovered gates and live actor state.

BUS.ACT and PEOPLE.ACT remain unresolved. Their `UNCS` headers alone do not
explain non-use: the original reader's non-UNC2 path accepts the UNC prefix.
Exact filename construction, successful opens/reads and rendering remain
separate requirements. All **97 unresolved entries and 13 asset candidates
remain open**; no global-unused claim is made.

The retained continuation delta is **674 events, sequences 4451..5124**, with
seven filename-argument events, two actor-argument events, seven successful DOS
opens and 122 original-matching read prefixes. Neither BUS.ACT nor PEOPLE.ACT
appears as an exact argument, successful open or retained read prefix in this
delta. No new unresolved-entry hit was recorded. The route's final tail is
incomplete, so this is not a complete-route negative. The same guest/capture
continues; the last qualified 24 capture/run receipts are not incremented, and
older events 1..4450 are not counted again. Whole-ledger cumulative snapshot
totals were not rebuilt in this bounded follow-up.

The positive filename controls include STRINGS.DAT and COEL.ACT during normal
advances, then MALL.ACT, MALL.PIC, BIPLANE.ABT, ROOSTER.ABT and STRINGS.DAT in
the partial route. Loader activity therefore continued into the attempted
street transition; those observations do not certify a ready destination view.

## New friction: park-to-street observation failure

After the 32-command cohort, canonical `go street` ticket 0222 entered recovery
root `063654b007c9c0117f04248a887a4404`. It failed before a verified destination
view, and no office or alternate route was subsequently attempted.

The outer error trace ends with `pointer_prepared` and a `press: not_sent`
marker from that earlier stage. That marker is **not a complete input history**.
The parent independently read the actual failed scene observation
`6d5af48bdf1c48259a6000d14ff63fdf` from the live project's SQLite database in
read-only mode. It contains an **accepted, queued button input**, native point
(346,187), state revision **7916**, with release still pending in that receipt.
Consumption and navigation outcome remain unknown.

The exact observation error is `RpcAdmissionTimeout`: observer native prelude
withheld for insufficient allowance; stopped state unqualified. This is an
observation/budget failure, not demonstrated game crash or missing actor media.
The frozen source's navigation reconciler covers the four business destinations,
not `go street` from the park.

Read-only reconciliation ticket 0223 retained the same root and returned
incomplete/unknown. Execution, input, input-read and restore deltas were all
zero; failure diagnostics were unchanged. The provider was retained and further
action input stayed blocked. The queued press was not replayed. Stored frames
are historical observations, not a completion certificate for the held route.

Luna's final checks confirmed the same native/worker/controller alive, all
12 runtime pins matching their as-launched files, all 192 original files
unchanged, `SDL_AUDIODRIVER=dummy`, mixer `nosound=true` and MIDI `none`.
Current post-route cash, food, date and view remain unknown. The loaded private
probe-status gate also requires no held action, so ticket 0219 remains the last
actual inventory proof; no bypass or unsupported query was attempted.

Recommended tool fixes for this friction: budget the complete navigation and
observer prelude together; retain the authoritative queued-input receipt even
when observation raises; extend source-qualified read-only destination
reconciliation to park/street/office routes; and expose the missing attendance
and selected-value observation seams. These are findings for implementation,
not fixes claimed by this documentation follow-up.

## Separate tool and skill proposal

[GitLab !31](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/31),
source `46622ebff05b8278685eea2324b1cfb7fc24750e`, proposes durable standing-probe
definitions, checked live bindings, passive first-hit capture and prioritized
analysis leads. It updates the bundled skill to strongly recommend probes on
plausible unknown code and selected meaningful values, while excluding blanket
probes on null padding/filler and recording overhead/capability deferrals.

A hypothetical real-world-weekday-only branch illustrates rare activation; it
is not a DinoPark finding. Durable definitions are distinct from live bindings,
and first-hit capture latches the native probe off for analysis/rearming rather
than repeatedly stalling a hot path. Capture failure retains the pending hit;
it cannot authorize action replay.

The bundled-skill verifier passed all **12 references / 30 local Markdown
links** against the exact main baseline plus candidate changes. All three
published files were hash-checked through GitLab readback; its description
matched after GitLab removed one final newline. No production probe-plan API,
native feature qualification or installed-skill change is claimed by !31.

## Evidence and claim ceiling

Private native receipts are under
`/Volumes/CACHE/fDisBull-native-validation-20261101/luna/visitors-20261101`;
the selected static packet is under sibling `visitors-static-20261101`.
`PARENT-VISITORS-ROUTE-OBSERVATIONS.json` retains the independent queued-input
finding. The earlier 50-file snapshot remains byte-identical and the live root
is not sealed or moved.

The selected continuation snapshot contains **53 files / 11,027,763 bytes** at
`/Volumes/CACHE/fDisBull-native-validation-20261101/verified-visitors-receipts-20261101/EVIDENCE-MANIFEST.json`,
SHA-256 `de39dbc0075807219d510f0fb746906497309bf3068be428a68e691a1c4e7e08`.
It contains selected native/static/parent receipts and the retained trace, not a
database clone or package. The parent also independently matched all 122 new
read-prefix byte strings to their canonical source-file ranges.

This follow-up adds original-code visitor/actor predicates and a real normal
play cohort through month rollover. It leaves actual current attendance/actor
values, a BUS/PEOPLE producer-load-render chain and the held street transition
unqualified. The 97-entry probes remain useful precisely because rare paths
may still activate during later authorized ordinary play.
