# DinoPark gift stand: where 7,500 comes from

Observed on 2026-10-23 using the unmodified published fDisBull 0.11.0 wheel and the delivered Mac ARM64 layers backend. This is a companion experiment created after the release, not a rebuild of its packages.

## Price source

The gift stand's unit price is the little-endian WORD `4c 1d` (7,500) in the original `DINOPARK.EXE` at **file offset `0x3b279`**. With the project's MZ load segment `0x1000`, its project address is **`0x46a79`**, or **`4020:6879`** in the static data-segment context. The EXE header occupies `0x4800` bytes, so `0x10000 + 0x3b279 - 0x4800 = 0x46a79`.

| Project address | Static DS offset | Observed facility | WORD value |
| --- | --- | --- | --- |
| `0x46a75` | `6875` | Food stand | 5,000 |
| `0x46a77` | `6877` | Rest rooms | 1,000 |
| `0x46a79` | `6879` | Gift stand | 7,500 |
| `0x46a7b` | `687b` | Parking lot | 10,000 |

The four values are already present at the program entry breakpoint. Write watches observed no CPU writes to that block during the tested boot, in-game-save load and catalogue route; the same bytes remained present afterward. `VARS.DAT` contains no literal 16-bit 7,500 value. The actual traced price reads use this executable-initialized RAM table, resolving the earlier ambiguity about the balance-file values for this purchase path.

In the observed loading context, the backend loaded the image at segment `0824` rather than static `1000`. It therefore translated the gift price to runtime `3844:6879`, linear `0x3ecb9`. Obtain the translation from the current session; these runtime addresses must not be hardcoded for another loading context.

## Observed readers and purchase accounting

The instruction bytes `8b 87 75 68` decode as `mov ax,[bx+6875h]`. With `BX=4` for the third facility, the read returns `AX=1d4c`.

| Static instruction | Observed role |
| --- | --- |
| `334b:0c9e` | Gift selection/affordability path reads the unit price and passes it to helper `334b:0008`. |
| `334b:0dcf` | Buying a unit reads its price; `0dd4`/`0dd8` subtract AX/DX from the staged available-cash DWORD at `DS:bad4`. The next instructions increment the pending facility count. |
| `334b:0a95` | Shop OK reads the unit price for final accounting. The path multiplies the pending-minus-live facility count by that price, accumulates transaction/expense totals, then commits the counters and staged cash. |

The 24-event cash-staging trace directly shows the 7,500 subtraction. The 192-event OK trace shows the one-unit multiplication through `1000:1650` (`mul bx`), the additions to the transaction total at `DS:686c`, and the expense DWORD at `DS:585a`. The path copies the pending facility block at `DS:b914` to live counters at `DS:6fa6`, and transfers staged available cash at `DS:bad4` into actual cash at `DS:5c3a`. Thus the working balance reserves the purchase before OK; OK commits the live counters and actual cash. This is distinct from the later game tick or a write to an in-game save file.

These are observed readers, not a complete inventory. An additional read at `334b:0f94` was observed during the affordance refresh. Other static byte-pattern matches were not all classified. The catalogue continues to print 7,500 when the tested execution layer changes the accounting lookup; this experiment does not fully trace the image-resource rendering path.

## State restore and layer comparison

The replay captures a native checkpoint, closes its emulator, restores it in a fresh emulator, and reaches the concessions page with native-coordinate `click-frame` actions. It then compares the same price-lookup checkpoint with the layer disabled, enabled and disabled again: **7,500 → 5,000 → 7,500**. A checkpoint captured with the layer enabled restores that active layer in another fresh emulator and again returns 5,000.

The execution layer changes the displacement from `6875` to `6871` at the three selection/cash-staging/commit readers above. For the gift index `BX=4`, this redirects the read to the existing food-stand entry (5,000). It changes no guest code RAM or price-table bytes. This is a bounded theory about the observed gift purchase, not a complete replacement of every concession-price consumer or a permanent game patch.

An earlier two-site layer changed the selection and final expense paths but omitted cash staging. It produced a **7,500 cash debit with 5,000 recorded expense**. That negative result is retained separately. Patching only the final accounting routine is therefore insufficient for a consistent repricing experiment.

For repeatable purchases, the script makes an explicit immutable native-state fork with **actual cash and staged available cash set to 100,000**. The pmm fixture can otherwise become unable to afford the gift stand while the calendar runs through the menu route. This preparation changes only those two RAM DWORDs, with expected-byte guards and recorded parent-state provenance. The original checkpoint, game files, in-game save, price table and static byte versions remain unchanged. Lookup discovery was also observed before this funding edit.

| Trial from the same funded checkpoint | Actual cash before OK | Actual cash after OK | Debit | Expense increase | Gift count after OK |
| --- | --- | --- | --- | --- | --- |
| Original instructions | 100,450 | 92,950 | 7,500 | 7,500 | 1 |
| Three-site execution layer | 100,450 | 95,450 | 5,000 | 5,000 | 1 |

Each transaction's before/after observations and 192-event trace stayed at guest tick **50122**. These bounded observations establish this gift purchase's price source and accounting path; they do not establish complete economic behavior, arbitrary game-state compatibility or full code coverage.

## Replay and retained files

Run [the companion source script](../verify_concession_price.py) with the original game directory, the delivered 0.11.0 directory and a **new output directory outside Git**. It verifies wheel/backend/game/save identities, copies the game into `private/`, and keeps all project/native-state bytes there. The JSON menu scripts, screenshots, traces, results and input hashes are written separately under `evidence/`.

```bash
python examples/dinopark/verify_concession_price.py \
  --delivery /absolute/path/to/fdisbull-0.11.0-a216747 \
  --game-dir /absolute/path/to/original/dinopark \
  --output /absolute/path/outside/Git/new-concession-run
```

The successful working project is local at `~/Conversions/DinoParkTycoon/debugger-runs/published-0.11.0-concession-replay-20261023-v5/private/dinopark.fdb`. Its mounted game directory is the sibling `game/`; keep that exact resolved path for restoring its checkpoints. The report and action journal identify the original, funded, lookup and layer-enabled checkpoint artifacts. Native checkpoint bytes are embedded only in that private database.

The DeepSeek companion delivery is `~/Conversions/DinoParkTycoon/fdisbull-deliveries/dinopark-0.11.0-concession-7500-2026-10-23/`. It contains the script, this report and diagnostic evidence, with a sibling ZIP and checksums. The already published tool/backend delivery is unchanged. All 192 original and copied game files matched their starting hashes. The screenshots retain clean sources and 8px grids with 32px label spacing; `offline-concessions-grid8.png` was regenerated from the stored project after every emulator had exited.
