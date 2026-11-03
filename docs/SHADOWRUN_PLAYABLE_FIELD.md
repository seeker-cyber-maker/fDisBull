# Shadowrun playable field milestone

This prepared-state Genesis-to-GameIL-to-NES experiment makes the captured
scene-2 player able to walk, select a captured NPC, fire the equipped pistol and
change that NPC's current HP. The inventory browser supports the captured pistol
and armor equipment branches. The NES starts from the verified original frame
5999; it does not replay the original game's boot, story or scene loaders.
Original files, extracted terrain, captures and generated cartridges remain in
a private workspace outside Git and tool packages.

The previous opening, dialogue and finite animated-walk profiles remain
available. This profile uses a symbolic field presentation to explore beyond
the old captured graphics atlas. It does not add original scenery, animation,
audio, enemy AI, scene transitions, general item use, loot or quests.

## Controls and investigation

| Control | Bounded behavior |
| --- | --- |
| D-pad | Source-derived player movement, terrain collision and camera updates |
| B in the field | Refresh screen admission and cycle eligible captured NPCs |
| A / hold A | Fire / repeat the captured item-2 pistol; display current target HP |
| START | Open the eight-slot inventory browser |
| D-pad, A in inventory | Select a slot and equip/unequip the captured pistol or armor |
| B / START in inventory | Close inventory |
| SELECT | Enter explicitly assisted placement; D-pad moves a cell, A requests placement, B / SELECT cancels |

The field covers a 64-by-44 source terrain table. Each symbol represents a
32-by-32 source-pixel cell; categories describe raw terrain codes, not inferred
walkability or visibility. Unsupported item/state paths refuse with a red X.
Movement and collision use the shared model rather than the display's colors.
Changing scenes and unresolved event dispatches remain outside the domain.
See [the NES profile](SHADOWRUN_NES_PLAY.md) for controls and adaptations.

The separate [city and Z projection](SHADOWRUN_CITY_Z.md) exposes coarse regions,
local cells, exact positions, stacked captured identities, inventory and current
model HP. Historical capture HP stays separate. This follows the established
Civilization and Syndicate representation guidelines: cells are half-open
intervals, no coarse cell has an implicit execution point, and unknown visibility
stays unknown. NPC coordinates are captured facts; the player's coordinate is
current model state. NES and Z execute the same GameIL contract in separate
runtime instances; they are not live synchronized.

An assisted text request can name an exact fixed-point destination and optional
camera recenter. The shared placement component checks revision, scene, bounds,
terrain and the admitted state before committing a transactional update. Physical
policy rejects teleport. Recenter is an authored diagnostic operation. Neither
placement nor the displayed map establishes original reachability, dynamic
collision safety, visibility or a route through scene transitions.

## Repeatable commands

Use the user's pinned ROM, reviewed capture and opening manifest, prepared
cc65 toolchain, and fresh private output directories. Complete the operator's
storage admission check before each bulk build or capture and set an external
temporary directory for that command. No command below downloads game files.

```sh
fdisbull shadowrun-play-build "$OPENING_MANIFEST" \
  --rom "$ROM" --capture "$CAPTURE" --cc65-root "$CC65_ROOT" \
  --output "$PRIVATE_BUILD"
fdisbull shadowrun-city-export "$ROM" \
  --snapshot "$CAPTURE/native/scene-005999" --output "$PRIVATE_CITY"
fdisbull shadowrun-z "$ROM" \
  --snapshot "$CAPTURE/native/scene-005999" --policy assisted
```

The first command creates a private `play.nes` plus source and build receipts.
The second creates private JSON, text and a standalone interactive HTML city
view. The third serves the standard line-oriented `observe`/`act` text-player
protocol; its default policy is physical if `--policy` is omitted. JSON methods
`shadowrun-play-build` and `shadowrun-city-export` work without an analysis project.

## Comparison methodology and results

Each edge is checked separately. Controlled original-core entries qualify
recovered arithmetic and state gates. Ordinary controller captures test actual
source reachability and sampled effects. FCEUmm traces test the compiled NES
against the shared GameIL at completed logical updates. Matching one edge does
not establish whole-game equivalence or equal real-time behavior.

The source is pinned by SHA-256
`92a614491fc3ea12a6df32459cce08b48574b7b814e244c07eb860dc5c6edb7e`.
The frozen NES candidate is
`7b4e14fb44352c51fb8fdd0558e77079d7cdb5334c7241f9ac69f1462c70265a`,
and its canonical shared GameIL is
`f19f30dc6693542c80d5e89e8c7eda5856f073f9c2b28ceb560a553b1fdd1b1d`.
Build, input, core, capture and comparison receipts bind these identities.

| Boundary | Observed result | Limit |
| --- | --- | --- |
| Original movement → NES | RIGHT 60, LEFT 60, UP 38, DOWN 60 and long LEFT 64 updates matched the compared player/camera fields | Bounded routes, including a wall stop beyond the old graphics atlas |
| Ordinary equipment menus → NES | Captured pistol and armor unequip/re-equip effects matched | Original uses two confirmations; target uses one; other item actions refuse |
| Ordinary encounter → NES | Four samples matched player position, selected NPC, ammo and HP through two hits: HP 10→6→5, ammo 12→11→10 | Original NPC moves; target NPC is frozen; physical hit timing differs |
| Original observer control | All 65,536 RAM bytes matched at 16 sampled frames with and without the write observer | Sampled RAM only, not continuous or whole-machine neutrality |
| Compiled NES → GameIL | 577 ordinary-controller and 578 assisted-combat completed updates had no compared-state mismatches; both target runs reached HP 0 in three shots | Target adaptation with captured NPCs, no enemy AI |
| Original held fire → NES | Six shots matched sampled ammunition, RNG, cooldown and projectile state | 52 logical updates between launches; target physical intervals were longer |
| Source leaves | 15 scoped checks include 50 heading cases, 259 spawn vectors, 36 continuous relocated-actor hit cases, 8 ordered actor scans, 24 animation and 40 retirement cases | Controlled entries and assistance are labeled separately from ordinary gameplay |
| Z and city view | Inventory, movement, assisted placement, current/captured HP separation and three-hit model sequence checked | Projection/model checks; no original teleport or visibility claim |

The original encounter uses LEFT for 60 frames, UP for 21, then B and held A,
with no memory patches. The original's first two ammo writes occurred at frames
6164 and 6216; HP changed at 6172 and 6224. A matching no-observer control
confirms sampled outcomes. The NES route uses ordinary controls from its
prepared start and also depletes the captured target; its third hit has no
matched original-route sample. Private traces and screenshots are retained.

The target deliberately holds the initial action timer until the first A and
allows one active projectile. Its original-derived heading, spawn, terrain,
source-order captured-actor scan and damage components are composed under
explicit profile guards. This does not reproduce the original actor pool, AI,
animation service scheduling or all projectile lifecycle behavior. Incompatible
movement/menu inputs cancel a pending shot or refuse during active flight.

On the tested FCEUmm core the initial symbolic field became stable at frame 80.
Reducing menu exit reconstruction to the one overwritten nametable reduced its
pause from 62 to 21 physical frames, with identical settled field pixels. These
are emulator observations, not hardware or 60-fps claims. An early 500-frame
demo request failed because its input extended to frame 620; that failed run is
preserved separately from the successful 700-frame retry.

Sanitized receipts are in
[source-field.json](evidence/shadowrun-play-2026-11-01/source-field.json),
[nes-play.json](evidence/shadowrun-play-2026-11-01/nes-play.json),
[city-z.json](evidence/shadowrun-play-2026-11-01/city-z.json),
[suite.json](evidence/shadowrun-play-2026-11-01/suite.json) and
[verification.json](evidence/shadowrun-play-2026-11-01/verification.json).
The [field recovery notes](SHADOWRUN_PREPARED_FIELD_ACTION.md) and
[targeting notes](SHADOWRUN_TARGETING.md) identify the original boundaries and
repeatable comparison helpers. Public receipts contain hashes, counts and
semantic results; they contain no ROM, assets, raw RAM or byte-retaining traces.
