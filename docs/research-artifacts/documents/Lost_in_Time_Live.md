# Lost in Time

## A text adventure for ChatGPT Live

**Edition 1.0 · English · 29 October 2026**

Based on Coktel Vision’s 1993 adventure. Original narration with a researched puzzle sequence. This file contains the full game-master specification, including solutions. Give it to the conversation hosting the game; you do not need to read the spoiler sections yourself.

**Contents:** 4 acts, 38 scenes, 188 authored actions, 117 item identifiers, and a complete reference route.

## Quick start

Provide this file to the conversation that will host play, then use the start instruction below. For voice play, keep the script in that same conversation. At a pause, ask for a save block; bring that block and this script to a new conversation if needed. The narrator follows the specification in conversation; no separate app has been installed.

## Narrator contract

This is an original English text-adventure adaptation of Coktel Vision's Lost in Time (1993). It covers the beginning, manor flashback, ship escape, island puzzles and finale. It is a playable specification for a language-model narrator. It is not a transcript, an emulation of the original executable, or an installed ChatGPT integration.

## Start instruction

Read this game document privately as the game master. Start a new game at `a_hold`, using the initial state below. Play in English with concise, atmospheric second-person narration. I control Doralice. Accept natural spoken actions; resolve them against the supplied rules. Keep solutions, future scenes and hidden state private. Do not automatically solve puzzles, take objects, combine items or move for me. Begin with the opening scene and ask what I do. Use the voice-friendly rules and produce a portable save block when I say “save game.”

## Who controls what

The player controls Doralice's choices. The narrator describes consequences, performs NPC dialogue, interprets equivalent phrasing and maintains the state. Narration may add harmless atmosphere, but may not create a useful object, exit, clue, motive, power or solution that the data does not authorize. A locked door remains locked when examined. An attractive suggestion from the player is an attempted action, not proof that it succeeds.

Use the authored mechanics as the authority. The descriptions are original prose, with some visual anchors from screenshots; they do not claim to reproduce every original camera angle. Merge turns, close-ups and repeated clicks into meaningful investigation. Movement uses place names, not invented compass bearings. Preserve the plot's setting and characters while speaking in newly written dialogue.

## Per-turn procedure

1. Parse the intended verb, object, target and destination. Accept synonyms such as “look under,” “check beneath,” and “search underneath.” Match both the action and its objects: a mention of the door alone is not permission to open it. Questions about what might happen do not execute an action.
2. Resolve against actions in the current scene, including that scene's explicitly inherited actions. For several commands in one utterance, execute in order and stop at the first blocked or ambiguous step. Ask one short question only when the intended target is materially ambiguous.
3. Check every `requires` token, at least one `requires_any` token when that list is present, and every `forbids` token before changing anything. A missing prerequisite produces a grounded explanation without exposing undiscovered prerequisites or silently granting them. Completed actions do not duplicate items. Repeating a completed search summarizes its present result.
4. Apply the selected action atomically: process any flashback checkpoint, remove `take` items, add `give` items, remove `unset_flags`, add `set_flags`, mark the action done, then apply `goto`. Record one undo snapshot before the transaction. Items are unique identifiers, not stacks, unless a future version explicitly says otherwise.
5. Update the visible description from state: do not describe a collected object as still available, a person as still captive after rescue, or a mechanism as closed after opening. Speak the authored outcome in natural prose; do not read rule identifiers aloud.
6. Stop and return control. On a room change, give the current description and obvious features/exits. Never continue through the next puzzle merely because its solution appears elsewhere in this file.

## Voice presentation

Use roughly 45–85 words on first entering a scene and 15–40 on a revisit. An action usually needs one to three sentences. Slow down for a new person, a spatial relationship or a newly discovered clue. Let the player interrupt. Avoid long inventories, numbered menus and reciting every conceivable action. A brief dry observation is welcome; constant jokes are not.

Do not read citations, IDs, conditions, JSON, spoiler notes or hint lists aloud. Offer the two or three currently obvious exits when useful. Ask “What do you do?” only when a handoff is needed, not after every sentence. NPC voices can differ in attitude without exaggerated accents. The player may request shorter descriptions or more detail at any time.

## Exploration, dialogue and commands

- **Look / describe the room:** summarize the present visible scene. No puzzle state change.
- **Examine / search an object:** reveal its observable features. If an explicit discovery action matches the intent, execute that action after checking its conditions. A feature description is game-master material: only reveal its hidden contents after the corresponding discovery. Inspecting a lock does not operate it.
- **Take / use / combine / open / pull / turn / give / talk:** execute a matching authored action. “Take everything” collects only visible, reachable, currently collectible objects; it must not search concealed spaces or perform combinations. Do not silently execute a whole scene's action list.
- **Go to a place:** take an available exit. “Back to the lighthouse” can follow an already visited, unlocked route without narrating every intermediate room, but cannot cross an unresolved gate, an act boundary, or a one-way event. Never use an action's `goto` merely as an exit.
- **Inventory:** list held items, using plain names and grouping only genuine container contents. An item mentioned in the scene is not automatically carried.
- **Talk:** give the named character's current information and motives. New dialogue must not reveal future secrets or bypass conditions. Use authored talk actions for consequential exchanges. If a character has nothing new, offer a short, state-consistent reply.
- **Journal / objective / recap:** summarize discovered facts, the immediate unresolved objective and recent progress. Exclude secret solutions. Keep an optional `journal` of known clues so a later narrator can distinguish player knowledge from world truth.
- **Map / exits:** list known accessible places and visible blocked routes. The map may reveal the existence of a visible door, but not a secret room before discovery.
- **Wait:** allow a short atmospheric beat. This adaptation has no wall-clock countdown. Waiting never destroys the campaign or consumes puzzle items.
- **Undo:** restore the complete game state before the latest successful action or move, including inventories and flashback stash. The reference runner keeps a maximum of 30 undo snapshots. Undoing a hint cannot erase what the human heard, but does not alter puzzle state.
- **Save game / pause:** provide a complete portable save block. Do not claim it was written outside the conversation unless an actual file operation occurred.
- **Load game:** validate the save's game/version, scene and token references, then restore it. Do not reconstruct missing state by guessing. Ask for the missing field or offer the last complete checkpoint.

## Hints and alternatives

No unsolicited solutions. On “hint,” use the first hint for the relevant unresolved obstacle; on “stronger hint,” use the second; on “solution,” give the third. After three materially different unsuccessful attempts at the same obstacle, offer a hint once without supplying it. A hint or clarification never consumes a turn or item.

Accept equivalent physical actions when the same inputs, gate and outputs apply. Accept explicitly documented alternative tools. Do not grant a new shortcut because the description sounds plausible: explain the immediate obstacle and let the player try another approach. If the player explicitly requests a freer adaptation, announce the changed rule before committing it and record it in `house_rules` so it stays consistent.

## Fairness decisions for this edition

The original's timed sections become encounters that wait for the player's next deliberate choice. There is no voice-latency death timer. Missing-key and missing-item responses leave state unchanged. Critical consumables have prerequisite guards. The flower needed for the finale must be removed from its bag before the hazardous bag action; the narrator must not remove it on the player's behalf. An invalid attempt receives an in-world observation and remains retryable.

The crypt age and combinations use fixed, stated clues selected for this adaptation. They are not claimed to be universal answers in the original game. Some guides disagree about tool variants; the specific accepted variants are encoded in the action aliases or listed alternatives. Historical adventure-game machinery and potion effects remain fictional game rules. No real chemistry simulation is implied.

## State and condition semantics

The full world JSON is the canonical machine-readable specification. The master Markdown renders the same rules for a human or language-model host. Each scene has a stable ID, description, features, exits and actions. `source_ids` identify research provenance; they are not runtime conditions. A `go:scene_id` entry in a solution route is an ordinary exit move, not a teleport.

Conditions have three forms:

| Token | Meaning |
|---|---|
| `item:identifier` | The current inventory contains this item. |
| `flag:identifier` | This flag is true. Omitted flags are false. |
| `done:action_id` | This action has already completed successfully. |

All `requires` tokens must be true. When `requires_any` is present and nonempty, at least one of those tokens must also be true. Every `forbids` token must be false. An action is once-only unless `repeatable` is explicitly true. An empty requirement list does not remove its location requirement. `give` and `take` refer to inventory IDs. A `take` item must be held; failure aborts the whole action. `set_flags` and `unset_flags` change Boolean world facts. Every action result changes only its listed effects. `say` is a result template and must be conditioned on the actual successful action; it is not a standing permission or an instruction to continue automatically.

Actions marked `portable: true` are pure inventory recipes, available throughout the act that defines them. Their printed room is their suggested introduction point, not a restriction on where held objects can be combined. All other actions remain local. Picking up a room object is never made portable merely because it will later fit in the inventory.

Scene actions may be inherited by ID after the flashback. These refer to the same action and the same completion record, so a missed item can still be retrieved without creating a second copy. Features are inspection material, not a list of automatic state changes.

### Flashback continuity

`begin_flashback`: stash the current 1840 inventory in `flashback_stash`; switch to an empty 1992 inventory; retain completed actions and flags. The 1992 playthrough earns its own items. `end_flashback`: discard the flashback inventory, restore the stashed 1840 inventory, clear the stash, and then apply that transition action's explicit grants (including the small hook). This is a declared modeling choice. It prevents carrying the manor's full inventory into the ship or duplicating tools across the temporal loop.

Chapter C can still access early ship searches that were skipped. Do not require every optional ship item before allowing the flashback. Chapter D starts through its authored transition, not by resetting inventory arbitrarily.

### Portable save

Preserve at least `game_id`, `version`, `scene`, `inventory`, `flags`, `done`, `visited`, `flashback_stash`, `turn`, `journal`, `hint_levels`, `house_rules` and `status`. Include `undo` when feasible; an exported save may omit undo history if explicitly declared. Item and flag arrays contain IDs, not explanatory prose. Record a new checkpoint at each act boundary and when the player requests one. Do not assume a fresh conversation remembers prior state.

When a voice interface can also show text, say “Checkpoint ready” and present the save block without reading it aloud. If it cannot show or retain the block, explain that limitation and ask the player to obtain the text checkpoint before ending. This document does not depend on background tasks, undocumented Live features, external browsing during play, or automatic access to other conversations.

## Host handoff and limits

Load the master script in the conversation that will host play. For an interrupted session, provide the same full script and the latest save block. Act modules can be used as reading aids, but the full world or master script remains necessary to validate earlier action IDs and inventories. A prompt-driven narrator can still make tracking mistakes; the explicit rules and save state make them detectable and repairable. The included reference runner can replay exact action IDs and validate state transitions; it is not a natural-language or voice implementation.

The research establishes a complete playable route in this adaptation. It does not establish pixel-exact room boundaries, every alternate solution in the original, exact dialogue, or original real-time behavior. The source register distinguishes written-guide evidence, inspected screenshots and video references whose footage was not watched.


## Initial state

```json
{
  "game_id": "lost_in_time_live_adaptation",
  "version": "1.0.0",
  "scene": "a_hold",
  "inventory": [
    "paint_remover",
    "pipette",
    "pliers"
  ],
  "flags": [],
  "done": [],
  "visited": [
    "a_hold"
  ],
  "flashback_stash": null,
  "turn": 0,
  "journal": [],
  "hint_levels": {},
  "house_rules": [],
  "status": "playing"
}
```

---

# Game-master material — spoilers

Descriptions are read-aloud templates. Feature details, requirements, effects, hints and source notes are private. Reveal discoveries only through the player’s actions and the current state.

# Act A — The Briscarde: awakening

## a_hold — The Briscarde — locked hold

**On arrival — adjust to current state:**

Timbers complain around you as the ship rolls. Amber light catches the edges of barrels and a low stool; cobwebs bridge the overhead beams. A heavy post rises toward the deck above. There is a lower opening in the floor, and a faded poster covers part of the wooden wall. Somewhere beyond that wall, another person shifts.

### Inspection material

- **stool:** A low stool has an uneven underside.
- **near barrel:** One barrel stands slightly away from the wall.
- **dark barrels:** The recess behind them is too dim to search properly.
- **water bucket:** A bucket contains enough water to wet something.
- **poster:** The paper is stuck against the wooden partition.
- **support post:** The overhead opening is out of reach; the wood could hold footholds.

### Exits

- **down to the bilge** → `a_bilge`. Requires `item:lamp`.
- **up to the mid-deck** → `a_middeck`. Requires `flag:a_steps_carved`.

### Actions and state changes

#### a_take_nail: Pull the nail from beneath the stool

Equivalent phrasing: use pliers on stool; take nail; pull nail.

**Requires:** `item:pliers`. Once only.

**Effects:** give items: `nail`.

**Outcome:** The pliers draw out a sound nail. You pocket it.

**Private hint ladder:**

1. Check what is holding the stool together.
2. There is a nail underneath; bare fingers will not pull it.
3. Use the pliers on the nail beneath the stool.

#### a_find_lamp: Search behind the near barrel

Equivalent phrasing: search barrel; take lamp; look behind barrel.

**Requires:** none. Once only.

**Effects:** give items: `lamp`.

**Outcome:** Your hand closes around a lamp. Its light makes the hold much easier to examine.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Search behind the near barrel

#### a_find_sponge: Light and search the dark barrels

Equivalent phrasing: use lamp on barrels; search dark barrels.

**Requires:** `item:lamp`. Once only.

**Effects:** give items: `sponge`.

**Outcome:** In the lamplight you find a sponge tucked behind the barrels.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Light and search the dark barrels

#### a_wet_sponge: Wet the sponge in the bucket

Equivalent phrasing: use sponge on bucket; soak sponge.

**Requires:** `item:sponge`. Once only.

**Effects:** remove items: `sponge`; give items: `wet_sponge`.

**Outcome:** The sponge absorbs water.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Wet the sponge in the bucket

#### a_remove_poster: Wash the poster with the wet sponge

Equivalent phrasing: use wet sponge on poster; remove poster; wash poster.

**Requires:** `item:wet_sponge`. Once only.

**Effects:** set flags: `a_poster_removed`.

**Outcome:** The paper loosens. Beneath it is a knot in the wooden partition.

**Private hint ladder:**

1. The paper is hiding the wood beneath it.
2. Soften the paper before trying to peel it away.
3. Use the wet sponge on the poster.

#### a_remove_knot: Remove the wooden knot with the corkscrew

Equivalent phrasing: use corkscrew on knot; remove knot.

**Requires:** `flag:a_poster_removed`, `item:corkscrew`. Once only.

**Effects:** set flags: `a_hole_open`.

**Outcome:** The knot comes free, leaving an opening through the partition.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Remove the wooden knot with the corkscrew

#### a_meet_yoruba: Speak through the hole

Equivalent phrasing: talk to Yoruba; look through hole; call through hole.

**Requires:** `flag:a_hole_open`. Once only.

**Effects:** give items: `knife`; set flags: `a_yoruba_met`.

**Outcome:** Yoruba, another prisoner, answers. He lends you a knife to cut footholds in the post, asking for it back when you have finished. He also asks you not to leave him behind.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Speak through the hole

#### a_carve_steps: Carve footholds into the post and return the borrowed knife

Equivalent phrasing: use knife on post; carve post; make steps.

**Requires:** `item:knife`. Once only.

**Effects:** remove items: `knife`; set flags: `a_steps_carved`.

**Outcome:** You cut footholds into the post, then pass the borrowed knife back to Yoruba. The opening above is now reachable.

**Private hint ladder:**

1. The opening is above you, and there is no ladder.
2. A sturdy wooden support is close enough to climb if you improve your grip.
3. Carve footholds into the post with the knife.

**Research anchors:** [early_sierrahelp](https://sierrahelp.com/Walkthroughs/LostInTimeWalkthrough.html). Narration is original.

## a_bilge — The bilge

**On arrival — adjust to current state:**

The air changes as you descend: closer, wetter, heavy with the ship's neglected underside. Lamplight glances across standing water. A cask rests against the timbers, and a pump waits beside it. A length of chain disappears toward a low corner. Every movement of the hull sends another small ripple through the darkness.

### Inspection material

- **cask:** Its contents are worth checking.
- **bilge pump:** The handle resists movement.
- **chain:** The low corner beneath it is flooded until the pump works.

### Exits

- **up to the hold** → `a_hold`. Requires none.

### Actions and state changes

#### a_find_oil: Search the cask

Equivalent phrasing: inspect cask; take oil.

**Requires:** none. Once only.

**Effects:** give items: `palm_oil`.

**Outcome:** Inside the cask you find a bottle of oil.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Search the cask

#### a_oil_pump: Oil the pump handle

Equivalent phrasing: use oil on pump; lubricate pump.

**Requires:** `item:palm_oil`. Once only.

**Effects:** remove items: `palm_oil`; set flags: `a_pump_oiled`.

**Outcome:** The oil works into the seized joint.

**Private hint ladder:**

1. The pump is present, but its mechanism is stiff.
2. The cask contains something suitable for a seized joint.
3. Use the oil on the pump handle.

#### a_pump_water: Work the pump

Equivalent phrasing: pump water; pull pump handle.

**Requires:** `flag:a_pump_oiled`. Once only.

**Effects:** set flags: `a_bilge_drained`.

**Outcome:** The handle moves. With repeated strokes, the water falls away from the corner beside the chain.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Work the pump

#### a_find_corkscrew: Search the drained corner beneath the chain

Equivalent phrasing: inspect chain; take corkscrew; search chain.

**Requires:** `flag:a_bilge_drained`. Once only.

**Effects:** give items: `corkscrew`.

**Outcome:** You retrieve a corkscrew from beside the chain.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Search the drained corner beneath the chain

**Research anchors:** [early_sierrahelp](https://sierrahelp.com/Walkthroughs/LostInTimeWalkthrough.html). Narration is original.

## a_middeck — The mid-deck

**On arrival — adjust to current state:**

The deck stretches between heavy ribs of timber. Cannons and their ammunition crowd the passage; a damaged oar lies near the cannonballs. Containers stand farther aft, below a hanging ring and a wall panel. Forward, a sliding door refuses to move cleanly. There is someone behind it, close enough to hear you trying.

### Inspection material

- **wooden pegs:** A useful wooden pin can be pulled from the rack.
- **broken oar:** Damaged, but still a good length of wood.
- **containers:** The middle container holds something folded.
- **hanging ring:** Its surface is unpleasant to grip firmly.
- **concealed wall panel:** The hanging ring operates this panel.
- **chipped cannon:** The rough metal would abrade a softer material.
- **sliding door:** The lower runner is the source of the resistance.

### Exits

- **down to the hold** → `a_hold`. Requires none.

### Actions and state changes

#### a_take_pin: Pull a wooden pin from the rack

Equivalent phrasing: use pliers on peg; take wooden pin.

**Requires:** `item:pliers`. Once only.

**Effects:** give items: `wooden_pin`.

**Outcome:** A wooden pin comes away in the pliers.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Pull a wooden pin from the rack

#### a_take_oar: Take the broken oar

Equivalent phrasing: take oar; search cannonballs.

**Requires:** none. Once only.

**Effects:** give items: `broken_oar`.

**Outcome:** You take the broken oar from beside the cannonballs.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Take the broken oar

#### a_take_towel: Search the middle container

Equivalent phrasing: take towel; search containers.

**Requires:** none. Once only.

**Effects:** give items: `towel`.

**Outcome:** You find a towel in the middle container.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Search the middle container

#### a_pull_ring: Pull the ring using the towel

Equivalent phrasing: use towel on ring; pull ring with towel.

**Requires:** `item:towel`. Once only.

**Effects:** set flags: `a_cache_open`.

**Outcome:** With the towel around your hand, you get a firm hold. The ring moves and a panel opens.

**Private hint ladder:**

1. The ring moves a mechanism, but it is difficult to hold.
2. Protect your hand and improve your grip.
3. Wrap the towel around the ring and pull.

#### a_take_soap: Search the opened wall compartment

Equivalent phrasing: take soap; search cache.

**Requires:** `flag:a_cache_open`. Once only.

**Effects:** give items: `soap`.

**Outcome:** The compartment contains a bar of soap.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Search the opened wall compartment

#### a_shave_soap: Rub the soap against the chipped cannon

Equivalent phrasing: use soap on cannon; make soap shavings.

**Requires:** `item:soap`. **Forbidden when:** `done:a_shave_soap_corkscrew`. Once only.

**Effects:** remove items: `soap`; give items: `soap_shavings`.

**Outcome:** The rough metal scrapes the soap into shavings.

**Private hint ladder:**

1. The door runner needs something that will reduce friction.
2. A solid bar is awkward; a rough surface can reduce it to small pieces.
3. Rub the soap on the chipped cannon.

#### a_shave_soap_corkscrew: Shave the soap with the corkscrew

Equivalent phrasing: use corkscrew on soap.

**Requires:** `item:soap`, `item:corkscrew`. **Forbidden when:** `done:a_shave_soap`. Once only.

**Effects:** remove items: `soap`; give items: `soap_shavings`.

**Outcome:** The corkscrew scrapes usable shavings from the bar.

**Private hint ladder:**

1. The door runner needs lubrication.
2. You can scrape the soap with a rough tool.
3. Shave the soap with the corkscrew.

#### a_lubricate_door: Put soap shavings in the door runner

Equivalent phrasing: use soap shavings on door; lubricate door.

**Requires:** `item:soap_shavings`. Once only.

**Effects:** remove items: `soap_shavings`; set flags: `a_door_lubricated`.

**Outcome:** The shavings settle into the runner. The door can now slide.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Put soap shavings in the door runner

#### a_begin_flashback: Open the sliding door and speak to Melkior

Equivalent phrasing: open sliding door; talk to Melkior.

**Requires:** `flag:a_door_lubricated`. Once only.

**Effects:** checkpoint `begin_flashback`; set flags: `a_melkior_met`; move to `b_gate`.

**Outcome:** The bound man calls himself Melkior. He says this ship is sailing in 1840. As you try to explain that you belong in 1992, the memory returns: your inherited manor, the missing notary, a tractor, and a horse blocking the gate. The remembered day begins.

**Private hint ladder:**

1. Someone is behind the door.
2. Once its runner is lubricated, you can open it.
3. Open the sliding door and speak to Melkior.

**Research anchors:** [early_sierrahelp](https://sierrahelp.com/Walkthroughs/LostInTimeWalkthrough.html), [early_walkthroughking](https://www.walkthroughking.com/text/lostintime.aspx). Narration is original.

# Act B — The manor: the remembered day

## b_gate — The manor gate — 1992

**On arrival — adjust to current state:**

A pale stone wall encloses the property you have inherited. Shrubs crowd the approach, and an old tractor waits beside the entrance. A horse occupies the space in front of the gate with the confidence of an owner. Beyond it, a note has been fixed where a visitor should notice it. The gate is secured by a lock.

### Inspection material

- **tractor:** There is a basket above the cab, a toolbox, and a removable battery.
- **horse:** It blocks a comfortable approach to the gate.
- **gate note:** A dart fastens the note to the gate.
- **gate lock:** An old metal lock secures the gate.

### Exits

- **through the gate to the garden** → `b_garden`. Requires `flag:b_gate_open`.

### Actions and state changes

#### b_search_tractor: Search the tractor, basket, and toolbox

Equivalent phrasing: search tractor; search toolbox; inspect tractor.

**Requires:** none. Once only.

**Effects:** give items: `apple`, `battery`, `cigarette_pack`, `pipette`.

**Outcome:** You collect an apple, a battery, a cigarette pack, and a small pipette.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Search the tractor, basket, and toolbox

#### b_open_pack: Open the cigarette pack

Equivalent phrasing: inspect pack; open pack.

**Requires:** `item:cigarette_pack`. Once only.

**Portable recipe:** may be performed anywhere in this act when its required items are held.

**Effects:** remove items: `cigarette_pack`; give items: `foil`, `match_striker`.

**Outcome:** The pack contains foil and an empty matchbox with a usable striking surface.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Open the cigarette pack

#### b_move_horse: Give the apple to the horse

Equivalent phrasing: feed horse; use apple on horse.

**Requires:** `item:apple`. Once only.

**Effects:** remove items: `apple`; set flags: `b_horse_moved`.

**Outcome:** The horse follows the apple away from the gate.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Give the apple to the horse

#### b_read_gate_note: Read the note and remove its dart

Equivalent phrasing: read note; take dart; inspect gate.

**Requires:** `flag:b_horse_moved`. Once only.

**Effects:** give items: `dart`; set flags: `b_gate_note_read`.

**Outcome:** You read the note and remove the dart that held it in place. The gate's lock is now within easy reach.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Read the note and remove its dart

#### b_draw_acid: Fill the pipette from the battery

Equivalent phrasing: use pipette on battery; take battery acid.

**Requires:** `item:pipette`, `item:battery`. Once only.

**Effects:** remove items: `battery`; give items: `acid_charge`, `empty_battery`.

**Outcome:** The pipette takes up a small quantity from the battery. The emptied battery remains useful.

**Private hint ladder:**

1. The lock can be defeated using the game's improvised tools.
2. The tractor supplies both a liquid source and a small transfer tool.
3. Fill the pipette from the battery.

#### b_open_gate: Apply the filled pipette to the gate lock

Equivalent phrasing: use acid on lock; open gate lock; use filled pipette on lock.

**Requires:** `flag:b_horse_moved`, `item:acid_charge`. Once only.

**Effects:** remove items: `acid_charge`; set flags: `b_gate_open`.

**Outcome:** The lock yields. The gate swings into the garden.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Apply the filled pipette to the gate lock

**Research anchors:** [early_ltf1](https://www.abandonware-france.org/ltf_abandon/ltf_solutions.php?id_soluce=30&page=0). Narration is original.

## b_garden — The garden and well

**On arrival — adjust to current state:**

Green growth softens the grounds around the stone house. A well occupies the garden, with a faucet on the manor wall nearby. The main entrance is close at hand; farther around the property stand the lighthouse and an ornate stone vault. The sea is somewhere beyond them, audible in the pauses between the wind.

### Inspection material

- **well:** Its water lies too low to retrieve a small floating object by hand.
- **garden faucet:** The supply is controlled elsewhere; a hose can carry its water.
- **hose repair area:** A leak will need both reinforcing material and a binding resin.

### Exits

- **to the manor entrance** → `b_entry`. Requires none.
- **to the lighthouse's north wall** → `b_lighthouse_north`. Requires none.
- **to the vault** → `b_vault`. Requires none.
- **back to the gate** → `b_gate`. Requires none.
- **down the established cliff rope** → `b_beach`. Requires `flag:b_cliff_route`.

### Actions and state changes

#### b_attach_hose_faucet: Attach the recovered hose to the garden faucet

Equivalent phrasing: attach hose to faucet; attach repaired hose to faucet; attach leaky hose to faucet.

**Requires:** none. **Also requires at least one:** `item:leaky_hose`, `item:repaired_hose`. Once only.

**Effects:** set flags: `b_hose_on_faucet`.

**Outcome:** You fasten one end of the hose to the faucet.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Attach the leaky hose to the garden faucet

#### b_patch_hose: Patch the hose with fiberglass and resin

Equivalent phrasing: repair hose; use fiberglass and resin on hose.

**Requires:** `item:leaky_hose`, `item:fiberglass`, `item:resin`. Once only.

**Effects:** remove items: `leaky_hose`, `fiberglass`, `resin`; give items: `repaired_hose`; set flags: `b_hose_repaired`.

**Outcome:** Fiberglass bridges the split, and resin binds it into a firm patch.

**Private hint ladder:**

1. The tear needs reinforcement as well as something adhesive.
2. The crypt and manor supply complementary repair materials.
3. Patch the hose using fiberglass followed by resin.

#### b_position_hose: Put the repaired hose's free end into the well

Equivalent phrasing: put hose in well; use hose end on well.

**Requires:** `item:repaired_hose`, `flag:b_hose_on_faucet`. Once only.

**Effects:** set flags: `b_hose_in_well`.

**Outcome:** The free end hangs inside the well.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Put the repaired hose's free end into the well

#### b_recover_cork: Turn on the faucet and recover the floating cork

Equivalent phrasing: fill well; turn on faucet; take cork.

**Requires:** `flag:b_water_supply`, `flag:b_hose_repaired`, `flag:b_hose_in_well`, `flag:b_cork_in_well`. Once only.

**Effects:** give items: `cork`; set flags: `b_cork_recovered`.

**Outcome:** Water flows into the well. The rising surface brings your escaped cork within reach.

**Private hint ladder:**

1. The missing cork can float.
2. Bring the water to the cork rather than climbing down to it.
3. With the supply valve open and the hose repaired, fill the well and take the cork.

#### b_make_club: Cut the hardened hose patch into a club

Equivalent phrasing: cut hose; use razor on hardened hose; make club.

**Requires:** `item:repaired_hose`, `item:razor`, `flag:b_cork_recovered`. Once only.

**Effects:** remove items: `repaired_hose`; give items: `club`; set flags: `b_hose_cut`.

**Outcome:** The reinforced section has hardened. You cut it free as a compact club, after the hose has finished its work.

**Private hint ladder:**

1. The repair has changed the material as well as sealing it.
2. Once the cork is recovered, the hardened section has another use.
3. Cut out the resin-hardened hose section with the razor.

**Research anchors:** [early_neppomuk](https://neppomuk.ch/PointClick/Coktel/LiT.pdf). Narration is original.

## b_entry — The manor entrance

**On arrival — adjust to current state:**

The manor door is solid and unwelcoming. A portrait hangs above it from a length of wire, and logs have been stacked nearby. The handle does not feel secure. Through the keyhole you can make out the irritating reason an ordinary key will not help: another key has been left in place on the far side.

### Inspection material

- **portrait:** The frame and its hanging wire can be removed together.
- **door handle:** Loose enough to come away.
- **logs:** A single dry log is manageable.
- **keyhole:** An inside key occupies the opening.
- **gap under door:** Wide enough for a thin object, but not for your hand.

### Exits

- **back to the garden** → `b_garden`. Requires none.
- **inside the manor** → `b_interior`. Requires `flag:b_manor_open`.

### Actions and state changes

#### b_take_portrait: Take the portrait and its hanging wire

Equivalent phrasing: take portrait; take picture.

**Requires:** none. Once only.

**Effects:** give items: `portrait`, `portrait_wire`.

**Outcome:** You lift down the portrait and keep the wire.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Take the portrait and its hanging wire

#### b_take_handle: Try the door handle

Equivalent phrasing: take handle; pull handle.

**Requires:** none. Once only.

**Effects:** give items: `door_handle`.

**Outcome:** The handle comes away in your hand. It is still a useful piece of metal.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Try the door handle

#### b_take_log: Take a log

**Requires:** none. Once only.

**Effects:** give items: `log`.

**Outcome:** You select a dry log from the stack.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Take a log

#### b_drop_key: Push the inside key out with the dart

Equivalent phrasing: use dart in keyhole; push key; use dart on lock.

**Requires:** `item:dart`. Once only.

**Effects:** set flags: `b_key_on_floor`.

**Outcome:** The key drops onto the floor on the far side of the door.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Push the inside key out with the dart

#### b_make_coil: Wind the portrait wire around the door handle

Equivalent phrasing: combine wire and handle; make coil.

**Requires:** `item:portrait_wire`, `item:door_handle`. Once only.

**Portable recipe:** may be performed anywhere in this act when its required items are held.

**Effects:** remove items: `portrait_wire`, `door_handle`; give items: `coil`.

**Outcome:** You wind the wire around the handle to form a coil.

**Private hint ladder:**

1. You need to attract something metallic on the other side.
2. Wire and a metal core form one part of the solution.
3. Wind the portrait wire around the door handle.

#### b_charge_battery: Pour vinegar into the empty battery

Equivalent phrasing: use vinegar on battery; fill battery.

**Requires:** `item:vinegar`, `item:empty_battery`. Once only.

**Portable recipe:** may be performed anywhere in this act when its required items are held.

**Effects:** remove items: `vinegar`, `empty_battery`; give items: `charged_battery`.

**Outcome:** The vinegar restores the battery for one more task.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Pour vinegar into the empty battery

#### b_make_magnet: Connect the coil to the restored battery

Equivalent phrasing: combine coil and battery; make electromagnet.

**Requires:** `item:coil`, `item:charged_battery`. Once only.

**Portable recipe:** may be performed anywhere in this act when its required items are held.

**Effects:** remove items: `coil`, `charged_battery`; give items: `electromagnet`.

**Outcome:** The coil and battery become an electromagnet.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Connect the coil to the restored battery

#### b_get_key: Draw the fallen key under the door with the electromagnet

Equivalent phrasing: use magnet under door; get key; use electromagnet on gap.

**Requires:** `item:electromagnet`, `flag:b_key_on_floor`. Once only.

**Effects:** give items: `manor_key`.

**Outcome:** Metal scrapes across the far side of the floor. The key slides beneath the door.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Draw the fallen key under the door with the electromagnet

#### b_unlock_manor: Unlock the manor door

Equivalent phrasing: use key on door; open manor door.

**Requires:** `item:manor_key`. Once only.

**Effects:** set flags: `b_manor_open`.

**Outcome:** The lock turns, and the manor opens to you.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Unlock the manor door

**Research anchors:** [early_ltf1](https://www.abandonware-france.org/ltf_abandon/ltf_solutions.php?id_soluce=30&page=0). Narration is original.

## b_interior — The manor room

**On arrival — adjust to current state:**

A broad stone fireplace dominates the room. An iron rod leans nearby, and a roasting spit rests at the hearth. An oar occupies a wall recess. On one side is a box holding electrical fittings; on the other, a chest contains fine sand. An extinguisher stands ready above it, a modern detail among older things.

### Inspection material

- **fuse box:** Copper wire fastens its cover; one fuse is broken.
- **fireplace:** The hearth has contact points suited to the loose iron rod.
- **sand chest:** Fine sand is available in quantity.
- **iron rod:** Too cumbersome for ordinary carrying, but easy to move within this room.
- **floor in front of hearth:** The mechanism beneath it is dormant until the fireplace is prepared.

### Exits

- **outside to the entrance** → `b_entry`. Requires none.
- **through the concealed passage** → `b_wreck`. Requires `flag:b_passage_open`.

### Actions and state changes

#### b_take_manor_tools: Collect the oar, roasting spit, and extinguisher

Equivalent phrasing: take oar; take extinguisher; take roasting spit.

**Requires:** none. Once only.

**Effects:** give items: `manor_oar`, `roasting_spit`, `extinguisher`.

**Outcome:** You collect the loose tools from the room.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Collect the oar, roasting spit, and extinguisher

#### b_open_fuse_box: Open and search the fuse box

Equivalent phrasing: open fuse box; search fuse box.

**Requires:** none. Once only.

**Effects:** give items: `copper_wire`, `resin`; set flags: `b_fuse_exposed`.

**Outcome:** You remove the copper fastening wire, find resin inside, and expose the broken fuse.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Open and search the fuse box

#### b_restore_power: Repair the broken fuse with the foil

Equivalent phrasing: use foil on fuse; repair fuse.

**Requires:** `flag:b_fuse_exposed`, `item:foil`. Once only.

**Effects:** remove items: `foil`; set flags: `b_power_on`.

**Outcome:** The improvised repair restores power to the property's mechanism.

**Private hint ladder:**

1. The lift requires electrical power.
2. The broken connection is in the manor, and the cigarette pack supplied a conductive scrap.
3. Use the foil on the broken fuse.

#### b_place_rod: Lay the iron rod across the hearth contacts

Equivalent phrasing: put rod in fireplace; use rod on hearth.

**Requires:** none. Once only.

**Effects:** set flags: `b_rod_placed`.

**Outcome:** You fit the rod across the fireplace contacts.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Lay the iron rod across the hearth contacts

#### b_place_log: Put the log in the fireplace

Equivalent phrasing: use log on fireplace.

**Requires:** `item:log`. Once only.

**Effects:** remove items: `log`; set flags: `b_log_placed`.

**Outcome:** The log settles into the hearth.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Put the log in the fireplace

#### b_prepare_fire: Add the handkerchief and kerosene to the hearth

Equivalent phrasing: prepare fireplace; use handkerchief and kerosene on fireplace.

**Requires:** `item:handkerchief`, `item:kerosene`. Once only.

**Effects:** remove items: `handkerchief`, `kerosene`; set flags: `b_kindling_ready`.

**Outcome:** The prepared hearth is ready for a flame.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Add the handkerchief and kerosene to the hearth

#### b_get_match: Break the bottled ship with the club

Equivalent phrasing: use club on bottled ship; break ship in bottle.

**Requires:** `item:bottled_ship`, `item:club`. Once only.

**Portable recipe:** may be performed anywhere in this act when its required items are held.

**Effects:** remove items: `bottled_ship`; give items: `match`.

**Outcome:** The bottle breaks, releasing a match from the model.

**Private hint ladder:**

1. Your matchbox has a striker but no match.
2. The model ship contains a small combustible part.
3. Break the bottled ship with the club to obtain a match.

#### b_light_match: Strike the match on the matchbox

Equivalent phrasing: light match; use match on matchbox.

**Requires:** `item:match`, `item:match_striker`. Once only.

**Portable recipe:** may be performed anywhere in this act when its required items are held.

**Effects:** remove items: `match`; give items: `lit_match`.

**Outcome:** The match catches.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Strike the match on the matchbox

#### b_light_hearth: Light the prepared fireplace

Equivalent phrasing: light fireplace; use lit match on hearth.

**Requires:** `item:lit_match`, `flag:b_log_placed`, `flag:b_rod_placed`, `flag:b_kindling_ready`. Once only.

**Effects:** remove items: `lit_match`; set flags: `b_hearth_active`.

**Outcome:** As heat spreads through the hearth, the iron rod shifts against its contacts. A slab in front of the fireplace rises into a working position.

**Private hint ladder:**

1. The fire is part of a mechanism.
2. The rod must span the contacts before heat can do its work.
3. Position the rod, prepare the fuel, and light the fireplace.

#### b_place_barrel: Put the empty barrel on the raised slab

Equivalent phrasing: use barrel on slab; place barrel on flagstone.

**Requires:** `item:barrel`, `flag:b_hearth_active`. Once only.

**Effects:** remove items: `barrel`; set flags: `b_barrel_on_slab`.

**Outcome:** The empty barrel rests on the slab, but it is not heavy enough.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Put the empty barrel on the raised slab

#### b_open_barrel: Open the barrel with the club

Equivalent phrasing: use club on barrel; open barrel.

**Requires:** `flag:b_barrel_on_slab`, `item:club`. Once only.

**Effects:** set flags: `b_barrel_open`.

**Outcome:** The top gives way, leaving the barrel ready to fill.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Open the barrel with the club

#### b_seal_barrel: Plug the barrel hole with the candle

Equivalent phrasing: use candle on barrel; plug barrel.

**Requires:** `flag:b_barrel_on_slab`, `item:candle`. Once only.

**Effects:** remove items: `candle`; set flags: `b_barrel_sealed`.

**Outcome:** The candle seals the hole where the contents would escape.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Plug the barrel hole with the candle

#### b_weight_slab: Fill the barrel with sand using the wooden shoe

Equivalent phrasing: fill barrel with sand; use shoe on sand; weight floor.

**Requires:** `flag:b_barrel_open`, `flag:b_barrel_sealed`, `item:wooden_shoe`. Once only.

**Effects:** set flags: `b_passage_open`.

**Outcome:** Scoop after scoop adds weight. The slab sinks, and a section of wall opens onto a concealed passage.

**Private hint ladder:**

1. The empty barrel does not exert enough pressure.
2. The room already contains a heavy material and you have a scoop.
3. Seal the barrel, open its top, and fill it with sand using the wooden shoe.

**Research anchors:** [early_ltf1](https://www.abandonware-france.org/ltf_abandon/ltf_solutions.php?id_soluce=30&page=0), [early_ltf2](https://www.abandonware-france.org/ltf_abandon/ltf_solutions.php?id_soluce=30&page=1), [early_walkthroughking](https://www.walkthroughking.com/text/lostintime.aspx). Narration is original.

## b_vault — The stone vault

**On arrival — adjust to current state:**

The little stone building is more ornate than its surroundings. A shallow recess interrupts the steps, with the proportions of something meant to fit there. A memorial plaque and a cross form part of the structure. This place looks ceremonial, but the railing and concealed machinery suggest a more practical purpose beneath the stonework.

### Inspection material

- **recess in steps:** Its shape matches the removable portrait.
- **memorial plaque:** The memorial is covered until its mechanism has been exposed.
- **lift railing:** A strong attachment point once the elevator is revealed.
- **lift control:** The mechanism depends on the manor's power supply.

### Exits

- **back to the garden** → `b_garden`. Requires none.
- **down in the lift to the crypt** → `b_crypt`. Requires `flag:b_vault_open`, `flag:b_power_on`.

### Actions and state changes

#### b_fit_portrait: Fit the portrait into the stair recess

Equivalent phrasing: use portrait on recess; put picture in steps.

**Requires:** `item:portrait`. Once only.

**Effects:** remove items: `portrait`; set flags: `b_plaque_exposed`.

**Outcome:** The portrait fits. Touching it exposes a memorial plaque with a two-digit mechanism.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Fit the portrait into the stair recess

#### b_read_plaque: Read Philibert's memorial plaque

Equivalent phrasing: read plaque; inspect dates.

**Requires:** `flag:b_plaque_exposed`. Once only.

**Effects:** set flags: `b_plaque_read`.

**Outcome:** The plaque gives two years: 1803 and 1840. Below them are two number wheels and the cross.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Read Philibert's memorial plaque

#### b_solve_plaque: Enter 37 and press the cross

Equivalent phrasing: 37; enter 37; Philibert was 37.

**Requires:** `flag:b_plaque_exposed`, `flag:b_plaque_read`. Once only.

**Effects:** set flags: `b_vault_open`.

**Outcome:** The mechanism accepts Philibert's age. The lift is revealed.

**Private hint ladder:**

1. The plaque asks for a relationship between the dates.
2. Calculate how old Philibert was when he died.
3. Subtract 1803 from 1840; enter 37 and press the cross.

#### b_tie_lift_end: Tie the hose's free end to the lift railing

Equivalent phrasing: tie hose to railing; use hose on lift rail.

**Requires:** `flag:b_vault_open`, `flag:b_hose_on_door`, `item:hose`. Once only.

**Effects:** set flags: `b_hose_on_lift`.

**Outcome:** The hose now links the lighthouse door and the lift.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Tie the hose's free end to the lift railing

#### b_pull_lighthouse_door: Lower the lift remotely to pull the lighthouse door

Equivalent phrasing: lower lift; press lift control; open lighthouse using lift.

**Requires:** `flag:b_power_on`, `flag:b_vault_open`, `flag:b_hose_on_door`, `flag:b_hose_on_lift`, `item:hose`. Once only.

**Effects:** remove items: `hose`; give items: `leaky_hose`; set flags: `b_lighthouse_open`.

**Outcome:** The lift descends and the hose pulls taut. The lighthouse door gives way. You recover the hose, now torn by the strain.

**Private hint ladder:**

1. The lift can exert more force than you can.
2. Connect the stubborn door to the moving lift, then operate it from outside.
3. Tie the hose to the lighthouse door and lift rail, then lower the powered lift.

**Research anchors:** [early_ltf1](https://www.abandonware-france.org/ltf_abandon/ltf_solutions.php?id_soluce=30&page=0). Narration is original.

## b_lighthouse_north — The lighthouse's north wall

**On arrival — adjust to current state:**

The lighthouse rises above a narrow working space behind the manor. A barrel sits against the wall near a small basement window, and a bottle has been left beside it. Around the corner, the main door refuses to open. Its handle is solid enough to bear a substantial pull, if you can arrange one.

### Inspection material

- **bottle:** A bottle of vinegar stands beside the barrel.
- **barrel stopper:** The full barrel is awkward to move; its stopper can be pried free.
- **basement window:** The space around the barrel gives access to this low window.
- **lighthouse door:** Stubbornly closed, with a strong handle.

### Exits

- **back to the garden** → `b_garden`. Requires none.
- **inside the lighthouse** → `b_lighthouse_ground`. Requires `flag:b_lighthouse_open`.

### Actions and state changes

#### b_take_vinegar: Take the vinegar bottle

Equivalent phrasing: take bottle; take vinegar.

**Requires:** none. Once only.

**Effects:** give items: `vinegar`.

**Outcome:** You take the vinegar.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Take the vinegar bottle

#### b_empty_barrel: Remove the barrel stopper with the dart

Equivalent phrasing: use dart on barrel; empty barrel; take barrel.

**Requires:** `item:dart`. Once only.

**Effects:** give items: `barrel`; set flags: `b_barrel_emptied`.

**Outcome:** The contents drain away. You can now move and carry the empty barrel.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Remove the barrel stopper with the dart

#### b_break_window: Break the basement window with the roasting spit

Equivalent phrasing: use spit on window; break window.

**Requires:** `item:roasting_spit`, `flag:b_barrel_emptied`. Once only.

**Effects:** set flags: `b_window_broken`.

**Outcome:** The spit breaks the glass. A hose is visible through the opening.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Break the basement window with the roasting spit

#### b_take_hose: Retrieve the hose through the broken window

Equivalent phrasing: take hose; search window.

**Requires:** `flag:b_window_broken`. Once only.

**Effects:** give items: `hose`.

**Outcome:** You draw the hose out through the opening.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Retrieve the hose through the broken window

#### b_tie_door_end: Tie one end of the hose to the lighthouse door handle

Equivalent phrasing: use hose on door; tie hose to handle.

**Requires:** `item:hose`. Once only.

**Effects:** set flags: `b_hose_on_door`.

**Outcome:** One end is firmly attached to the door handle. You still need a source of pulling force.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Tie one end of the hose to the lighthouse door handle

**Research anchors:** [early_ltf1](https://www.abandonware-france.org/ltf_abandon/ltf_solutions.php?id_soluce=30&page=0). Narration is original.

## b_lighthouse_ground — The foot of the lighthouse

**On arrival — adjust to current state:**

Stone steps curve upward from the lighthouse entrance. A wooden shoe rests close to the stairs, out of place but deliberately left within reach. A second door leads toward the lower workings. Through a broken window, the outside light picks out sharp remnants of glass. Above you, the tower promises a better view of the coast.

### Inspection material

- **wooden shoe:** A useful hollow shape; something rattles inside.
- **basement door:** Its old lock is still intact.
- **broken window:** A single manageable glass shard remains.

### Exits

- **outside to the north wall** → `b_lighthouse_north`. Requires none.
- **up to the study** → `b_lighthouse_study`. Requires none.
- **down to the canal gate** → `b_canal`. Requires `flag:b_basement_open`.

### Actions and state changes

#### b_take_shoe: Take the wooden shoe

Equivalent phrasing: take shoe.

**Requires:** none. Once only.

**Effects:** give items: `wooden_shoe`.

**Outcome:** You pick up the wooden shoe.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Take the wooden shoe

#### b_search_shoe: Look inside the wooden shoe

Equivalent phrasing: inspect shoe; search shoe; take key from shoe.

**Requires:** `item:wooden_shoe`. Once only.

**Effects:** give items: `rusted_key`.

**Outcome:** A key is hidden inside it.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Look inside the wooden shoe

#### b_unlock_basement: Unlock the basement door with the hidden key

Equivalent phrasing: use key on basement door; open basement door.

**Requires:** `item:rusted_key`. Once only.

**Effects:** set flags: `b_basement_open`.

**Outcome:** The key turns in the lower door.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Unlock the basement door with the hidden key

#### b_take_glass: Take a loose glass shard from the broken window

Equivalent phrasing: take glass; search broken window.

**Requires:** `flag:b_window_broken`. Once only.

**Effects:** give items: `glass_shard`.

**Outcome:** You take a shard with an edge suitable for scraping.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Take a loose glass shard from the broken window

**Research anchors:** [early_neppomuk](https://neppomuk.ch/PointClick/Coktel/LiT.pdf). Narration is original.

## b_lighthouse_study — The lighthouse study

**On arrival — adjust to current state:**

A writing table and lamp occupy the warm little room above the entrance. Papers rest near a drawer, and a chair faces the work surface. A field glass points out toward the sea. A cupboard stands nearby with a reluctant door. From here the coast becomes something you can search, rather than merely hear.

### Inspection material

- **desk drawer:** A thorough search may find more than the first sheet of paper.
- **cupboard:** Its door needs leverage.
- **field glass:** It can isolate distant details on the coast, including a wreck.
- **captain's papers:** The papers mention the Devil's Seven Teeth; a lead rather than a usable tool.

### Exits

- **down to the entrance** → `b_lighthouse_ground`. Requires none.
- **up to the lantern chamber** → `b_lighthouse_lantern`. Requires none.

### Actions and state changes

#### b_search_study_drawer: Thoroughly search the desk drawer

Equivalent phrasing: search drawer; read diary; take paint remover.

**Requires:** none. Once only.

**Effects:** give items: `paint_remover`; set flags: `b_diary_read`.

**Outcome:** The papers mention the Devil's Seven Teeth. Searching beneath them also produces a bottle of paint remover.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Thoroughly search the desk drawer

#### b_open_cupboard: Pry open the cupboard with the manor oar

Equivalent phrasing: use oar on cupboard; open cupboard.

**Requires:** `item:manor_oar`. Once only.

**Effects:** give items: `razor`.

**Outcome:** The oar provides the leverage you need. Inside is a razor.

**Private hint ladder:**

1. The cupboard needs leverage, not a key.
2. One of the manor's tools is long enough to act as a lever.
3. Use the manor oar to pry open the cupboard.

#### b_observe_wreck: Study the wreck through the field glass

Equivalent phrasing: use telescope; look through field glass; inspect wreck.

**Requires:** none. Once only.

**Effects:** set flags: `b_wreck_code_seen`.

**Outcome:** Three painted panels become clear, left to right: a green sword, a red cannon, and a red cannonball. You record their order as well as their colors.

**Private hint ladder:**

1. The crypt's decoration has a counterpart elsewhere.
2. The lighthouse's field glass can reveal small details offshore.
3. Look through the field glass and record the wreck's three colored symbols.

**Research anchors:** [early_ltf1](https://www.abandonware-france.org/ltf_abandon/ltf_solutions.php?id_soluce=30&page=0), [early_neppomuk](https://neppomuk.ch/PointClick/Coktel/LiT.pdf). Narration is original.

## b_lighthouse_lantern — The lantern chamber

**On arrival — adjust to current state:**

The top of the lighthouse opens around its great cylindrical lens. Windows encircle the chamber, admitting a broad wash of daylight and a view of water. Curtains soften part of that glare. This is a place built to send light far away, yet the useful details are close: the folds of fabric, the space behind them, the tools of tending a lamp.

### Inspection material

- **curtains:** There is space behind the folds, and enough fabric to spare a small piece.
- **great lens:** An impressive part of the lighthouse, not a portable object.

### Exits

- **down to the study** → `b_lighthouse_study`. Requires none.

### Actions and state changes

#### b_take_kerosene: Search behind the curtains

Equivalent phrasing: move curtains; take kerosene.

**Requires:** none. Once only.

**Effects:** give items: `kerosene`.

**Outcome:** Behind the curtains you find a bottle of kerosene.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Search behind the curtains

#### b_cut_rag: Cut a piece of curtain with the razor

Equivalent phrasing: use razor on curtain; cut curtain; take rag.

**Requires:** `item:razor`. Once only.

**Effects:** give items: `curtain_rag`.

**Outcome:** You cut a useful piece of cloth from the curtain.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Cut a piece of curtain with the razor

**Research anchors:** [early_ltf1](https://www.abandonware-france.org/ltf_abandon/ltf_solutions.php?id_soluce=30&page=0), [visual_planete](https://www.planete-aventure.net/jeux.php?num_jeu=1626&cat=screenshots). Narration is original.

## b_crypt — The crypt below the vault

**On arrival — adjust to current state:**

The lift delivers you into a compact chamber where storage has taken over from ceremony. Bottles sit above easy reach, and another container rests on a high beam. A chest carries three adjustable weapon pictures with colored backgrounds. Its controls let you change both the pictures and their colors.

### Inspection material

- **high bottles:** A stable step would put them within reach.
- **container on beam:** Too high even with a step; a small launched object might dislodge it.
- **chest panels:** Three positions accept knife, pistol, or bullet symbols with colors. The correspondence is to larger weapons elsewhere.

### Exits

- **up in the lift** → `b_vault`. Requires none.

### Actions and state changes

#### b_take_cider: Stand on the barrel to reach a cider bottle

Equivalent phrasing: use barrel on high bottles; take cider; climb barrel.

**Requires:** `item:barrel`. Once only.

**Effects:** give items: `cider`.

**Outcome:** You use the barrel as a step, take a cider bottle, and reclaim the barrel.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Stand on the barrel to reach a cider bottle

#### b_launch_cork: Aim the cider cork at the container on the beam

Equivalent phrasing: shoot cork at bottle; use cider cork on beam bottle.

**Requires:** `item:cider`. Once only.

**Effects:** remove items: `cider`; give items: `rust_remover`; set flags: `b_cork_in_well`.

**Outcome:** The cork pops upward and knocks the container down. You recover rust remover, but the cork itself escapes through an opening toward the garden well.

**Private hint ladder:**

1. The container is beyond your reach.
2. The cider supplies a small projectile.
3. Aim the cider bottle's cork at the container on the overhead beam.

#### b_open_crypt_chest: Set green knife, red pistol, red bullet on the chest

Equivalent phrasing: green knife red pistol red bullet; green knife red gun red bullet; enter green knife, red pistol, red bullet.

**Requires:** `flag:b_wreck_code_seen`. Once only.

**Effects:** give items: `fiberglass`; set flags: `b_crypt_chest_open`, `b_ship_log_read`.

**Outcome:** The smaller weapons match their larger counterparts. The chest opens to reveal a ship's log with a piece of fiberglass tucked inside.

**Private hint ladder:**

1. The chest's images correspond to symbols somewhere along the coast.
2. Keep the observed colors and order, but translate each weapon to a smaller equivalent.
3. Set green knife, red pistol, red bullet, matching the chosen wreck clue.

**Research anchors:** [early_neppomuk](https://neppomuk.ch/PointClick/Coktel/LiT.pdf). Narration is original.

## b_canal — The lighthouse sea gate

**On arrival — adjust to current state:**

Stone steps descend toward an iron-barred opening above the water. A small boat waits on the sheltered side, carrying water of its own. Near the gate, algae cover part of the wall and a mechanism has stiffened with rust. A separate valve controls a channel. The route to the sea exists; it simply has several reasons to refuse you.

### Inspection material

- **channel valve:** Opening it enables the garden's water supply.
- **algae:** The growth conceals part of the gate mechanism.
- **gate mechanism:** It needs cleaning, lubrication, and a turning handle.
- **small boat:** Water has entered through a leak; the boat needs bailing and a firm plug.

### Exits

- **up to the lighthouse entrance** → `b_lighthouse_ground`. Requires none.

### Actions and state changes

#### b_open_water_supply: Open the channel valve

Equivalent phrasing: turn valve; open canal valve.

**Requires:** none. Once only.

**Effects:** set flags: `b_water_supply`.

**Outcome:** The channel opens, restoring the supply that feeds the garden faucet.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Open the channel valve

#### b_soften_algae: Apply paint remover to the algae

Equivalent phrasing: use paint remover on algae; use acid on algae.

**Requires:** `item:paint_remover`. Once only.

**Effects:** set flags: `b_algae_softened`.

**Outcome:** The stubborn growth softens.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Apply paint remover to the algae

#### b_scrape_algae: Scrape away the softened algae with the glass shard

Equivalent phrasing: use glass on algae; scrape algae.

**Requires:** `flag:b_algae_softened`, `item:glass_shard`. Once only.

**Effects:** set flags: `b_mechanism_exposed`.

**Outcome:** The glass clears the remaining growth and exposes the mechanism.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Scrape away the softened algae with the glass shard

#### b_free_mechanism: Apply rust remover to the exposed mechanism

Equivalent phrasing: use rust remover on mechanism; lubricate gate.

**Requires:** `flag:b_mechanism_exposed`, `item:rust_remover`. Once only.

**Effects:** set flags: `b_mechanism_freed`.

**Outcome:** The seized parts begin to move.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Apply rust remover to the exposed mechanism

#### b_open_sea_gate: Use the roasting spit as the mechanism's handle

Equivalent phrasing: use spit on mechanism; turn gate mechanism; open sea gate.

**Requires:** `flag:b_mechanism_freed`, `item:roasting_spit`. Once only.

**Effects:** set flags: `b_sea_gate_open`.

**Outcome:** The spit fits the exposed socket. Turning it opens the barred route to the sea.

**Private hint ladder:**

1. Cleaning and freeing the mechanism are only part of the job.
2. Its exposed socket needs a suitable lever.
3. After removing algae and rust, use the roasting spit to turn the gate mechanism.

#### b_bail_boat: Bail out the boat with the wooden shoe

Equivalent phrasing: use shoe on boat water; bail boat.

**Requires:** `item:wooden_shoe`. Once only.

**Effects:** set flags: `b_boat_bailed`.

**Outcome:** The hollow shoe serves as a bailer. The cleared water exposes the leak.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Bail out the boat with the wooden shoe

#### b_patch_boat: Pack the leak with the curtain rag and cork

Equivalent phrasing: repair boat; use rag and cork on leak.

**Requires:** `flag:b_boat_bailed`, `item:curtain_rag`, `item:cork`. Once only.

**Effects:** remove items: `curtain_rag`, `cork`; set flags: `b_boat_sealed`.

**Outcome:** Cloth fills the irregular gap; the cork wedges it firmly in place.

**Private hint ladder:**

1. A hard stopper alone does not match the irregular hole.
2. Use something flexible around the stopper.
3. Pack the leak with the curtain rag, then secure it with the cork.

#### b_row_to_cabin: Row out through the sea gate

Equivalent phrasing: use oar on boat; row boat; sail.

**Requires:** `flag:b_sea_gate_open`, `flag:b_boat_bailed`, `flag:b_boat_sealed`, `item:manor_oar`. Once only.

**Effects:** set flags: `b_boat_trip_complete`; move to `b_beach`.

**Outcome:** You paddle out. The short coastal journey proves less orderly than expected, and you come ashore by a small fisherman's cabin beneath the cliffs.

**Private hint ladder:**

1. The boat must float, and the barred passage must be open.
2. Bail, repair the leak, and bring a paddle.
3. With the gate open and boat repaired, use the manor oar to depart.

**Research anchors:** [early_neppomuk](https://neppomuk.ch/PointClick/Coktel/LiT.pdf). Narration is original.

## b_beach — The cabin beach

**On arrival — adjust to current state:**

Blue water presses against the narrow shore below a rocky cliff. A pale little building stands close to the beach. Something round has caught on its roof, with a length of rope attached, while gulls watch for food. The cliff is the direct route back toward the manor, but its face offers no easy handholds.

### Inspection material

- **buoy on roof:** A rope hangs with it, beyond your reach.
- **gulls:** They are interested in anything that smells edible.
- **cliff:** A grappling line could make the ascent possible.

### Exits

- **inside the cabin** → `b_cabin`. Requires none.
- **up the established cliff rope** → `b_garden`. Requires `flag:b_cliff_route`.

### Actions and state changes

#### b_scent_bread: Soak the bread in fish sauce

Equivalent phrasing: use fish sauce on bread; prepare gull bait.

**Requires:** `item:bread`, `item:fish_sauce`. Once only.

**Portable recipe:** may be performed anywhere in this act when its required items are held.

**Effects:** remove items: `bread`, `fish_sauce`; give items: `scented_bread`.

**Outcome:** The bread takes on a strong smell.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Soak the bread in fish sauce

#### b_lure_gull: Throw the scented bread onto the roof

Equivalent phrasing: throw bread on roof; feed gulls.

**Requires:** `item:scented_bread`. Once only.

**Effects:** remove items: `scented_bread`; set flags: `b_buoy_down`.

**Outcome:** A gull lands to seize the food and knocks the buoy loose. It falls within reach.

**Private hint ladder:**

1. You cannot reach the buoy, but another creature can.
2. Give a gull a reason to land where the buoy is lodged.
3. Throw fish-sauce-soaked bread onto the roof.

#### b_take_rope: Cut the buoy's rope free with the razor

Equivalent phrasing: use razor on buoy; take rope; cut rope.

**Requires:** `flag:b_buoy_down`, `item:razor`. Once only.

**Effects:** give items: `rope`.

**Outcome:** You free a useful length of rope.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Cut the buoy's rope free with the razor

#### b_make_grapple: Attach the rope to the anchor

Equivalent phrasing: combine anchor and rope; make grapple.

**Requires:** `item:rope`, `item:anchor`. Once only.

**Portable recipe:** may be performed anywhere in this act when its required items are held.

**Effects:** remove items: `rope`, `anchor`; give items: `grapple`.

**Outcome:** The anchor and rope make a grappling line.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Attach the rope to the anchor

#### b_climb_cliff: Secure the grapple on the cliff and climb

Equivalent phrasing: use grapple on cliff; climb cliff.

**Requires:** `item:grapple`. Once only.

**Effects:** remove items: `grapple`; set flags: `b_cliff_route`; move to `b_garden`.

**Outcome:** The hook holds. You climb back to the manor garden, leaving the line secured behind you.

**Private hint ladder:**

1. The cliff requires a secure line.
2. The cabin's improvised chandelier supplied the metal part.
3. Combine the anchor with rope, hook it over the cliff, and climb.

**Research anchors:** [early_ltf2](https://www.abandonware-france.org/ltf_abandon/ltf_solutions.php?id_soluce=30&page=1), [early_neppomuk](https://neppomuk.ch/PointClick/Coktel/LiT.pdf). Narration is original.

## b_cabin — The fisherman's cabin

**On arrival — adjust to current state:**

The cabin is small enough that every object seems to perform several jobs. A dresser occupies one corner; clothing and odds and ends lie on a table. A chair sits unevenly beneath a hanging chandelier assembled from practical-looking parts. A folded paper has been used where proper furniture repair would have been more sensible.

### Inspection material

- **dresser:** Its contents extend beyond the first compartment.
- **clothing on table:** A thorough search can recover several small belongings.
- **chair:** A paper props one leg; the chair can be moved and climbed.
- **improvised chandelier:** Its upper fastening is too high until you arrange a step.

### Exits

- **outside to the beach** → `b_beach`. Requires none.

### Actions and state changes

#### b_search_dresser: Thoroughly search the dresser

Equivalent phrasing: search dresser; take bottled ship; take fish sauce.

**Requires:** none. Once only.

**Effects:** give items: `bottled_ship`, `fish_sauce`.

**Outcome:** You find a ship in a bottle and a bottle of fish sauce.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Thoroughly search the dresser

#### b_search_clothes: Search the clothing and table

Equivalent phrasing: search table; search clothing; search basket.

**Requires:** none. Once only.

**Effects:** give items: `handkerchief`, `cabin_nail`, `bread`.

**Outcome:** You recover a handkerchief, a nail, and bread.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Search the clothing and table

#### b_read_cabin_note: Read the paper beneath the chair leg

Equivalent phrasing: read notebook; search chair leg; read paper.

**Requires:** none. Once only.

**Effects:** set flags: `b_melkior_note_read`.

**Outcome:** The paper is associated with Melkior. It gives the scattered clues around the property the feeling of a route someone has already passed through.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Read the paper beneath the chair leg

#### b_move_chair: Move the chair beneath the chandelier and climb

Equivalent phrasing: move chair; climb chair.

**Requires:** none. Once only.

**Effects:** set flags: `b_chandelier_reachable`.

**Outcome:** From the repositioned chair you can reach the upper fastening.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Move the chair beneath the chandelier and climb

#### b_detach_chandelier: Release the chandelier fastening with the nail

Equivalent phrasing: use nail on chandelier; take chandelier.

**Requires:** `flag:b_chandelier_reachable`, `item:cabin_nail`. Once only.

**Effects:** give items: `chandelier`.

**Outcome:** The nail releases the fastening. You lower the improvised chandelier.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Release the chandelier fastening with the nail

#### b_dismantle_chandelier: Dismantle the chandelier

Equivalent phrasing: inspect chandelier; take chandelier apart.

**Requires:** `item:chandelier`. Once only.

**Portable recipe:** may be performed anywhere in this act when its required items are held.

**Effects:** remove items: `chandelier`; give items: `anchor`, `candle`, `floats`.

**Outcome:** The ornament separates into an anchor-like hook, a candle, and cork floats.

**Private hint ladder:**

1. The chandelier was assembled from useful components.
2. Examine it as a construction rather than a single decoration.
3. Dismantle the chandelier into anchor, candle, and floats.

**Research anchors:** [early_ltf2](https://www.abandonware-france.org/ltf_abandon/ltf_solutions.php?id_soluce=30&page=1). Narration is original.

## b_wreck — The concealed wreck and sarcophagus

**On arrival — adjust to current state:**

The passage opens into the timbers of a wreck. A wooden case occupies the cramped space, wired in a way that makes careless handling unwise. Water gathers on the floor. Near a mast, pliers hold a small panel open. Beyond the case's fastenings lies the shape of something ceremonial, hidden inside a place built for cargo.

### Inspection material

- **mast panel:** A pair of pliers has been left holding the panel open.
- **wet floor:** There is room to arrange a small platform in front of the case.
- **electrical wire:** The connection must be diverted before it is cut.
- **crate lock:** After the electrical obstacle, the lock still needs to be defeated.
- **puddle:** The pipette can transfer a small amount of water.

### Exits

- **back through the passage** → `b_interior`. Requires none.

### Actions and state changes

#### b_take_pliers: Take the pliers from the mast panel

Equivalent phrasing: inspect mast; take pliers.

**Requires:** none. Once only.

**Effects:** give items: `pliers`.

**Outcome:** You retrieve the pliers. Their presence here will matter more than you yet understand.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Take the pliers from the mast panel

#### b_place_floats: Place the cork floats on the wet floor

Equivalent phrasing: use floats on floor; stand on floats.

**Requires:** `item:floats`. Once only.

**Effects:** remove items: `floats`; set flags: `b_standing_on_floats`.

**Outcome:** You arrange the floats as a platform before approaching the case.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Place the cork floats on the wet floor

#### b_divert_wire: Divert the connection with the copper wire

Equivalent phrasing: use copper wire on electrical wire; bypass wire.

**Requires:** `flag:b_standing_on_floats`, `item:copper_wire`. Once only.

**Effects:** remove items: `copper_wire`; set flags: `b_wire_diverted`.

**Outcome:** The copper wire diverts the connection away from the fastening.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Divert the connection with the copper wire

#### b_cut_wire: Cut the diverted wire with the pliers

Equivalent phrasing: use pliers on wire; cut electrical wire.

**Requires:** `flag:b_standing_on_floats`, `flag:b_wire_diverted`, `item:pliers`. Once only.

**Effects:** set flags: `b_wire_cut`.

**Outcome:** The pliers cut the diverted connection. The lock can now be handled.

**Private hint ladder:**

1. Do not start with the cutters.
2. Address both the wet footing and the live connection first.
3. Stand on the floats, divert the connection with copper wire, then cut with the pliers.

#### b_take_water: Fill the pipette from the puddle

Equivalent phrasing: use pipette on puddle; take water.

**Requires:** `item:pipette`. Once only.

**Effects:** set flags: `b_pipette_water`.

**Outcome:** The pipette takes up water.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Fill the pipette from the puddle

#### b_wet_lock: Put the pipette's water into the crate lock

Equivalent phrasing: use water on lock; wet lock.

**Requires:** `flag:b_wire_cut`, `flag:b_pipette_water`. Once only.

**Effects:** clear flags: `b_pipette_water`; set flags: `b_lock_wet`.

**Outcome:** Water enters the lock.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Put the pipette's water into the crate lock

#### b_freeze_lock: Use the extinguisher on the wet lock

Equivalent phrasing: freeze lock; use extinguisher on lock.

**Requires:** `flag:b_lock_wet`, `item:extinguisher`. Once only.

**Effects:** set flags: `b_lock_frozen`.

**Outcome:** The lock chills and stiffens under the extinguisher's discharge.

**Private hint ladder:**

1. Inspect the relevant object and consider what is preventing progress.
2. Use an available object that addresses that particular obstacle.
3. Use the extinguisher on the wet lock

#### b_break_lock: Strike the frozen lock with the club

Equivalent phrasing: use club on lock; break lock.

**Requires:** `flag:b_lock_frozen`, `item:club`. Once only.

**Effects:** set flags: `b_crate_open`.

**Outcome:** The brittle fastening breaks. The wooden case opens around a golden sarcophagus.

**Private hint ladder:**

1. The lock needs to be made vulnerable before impact.
2. Water, cold, and the hardened club form the final sequence.
3. Wet the lock, freeze it with the extinguisher, then strike it with the club.

#### b_end_flashback: Examine the revealed sarcophagus and finish the recollection

Equivalent phrasing: open sarcophagus; examine sarcophagus; finish memory.

**Requires:** `flag:b_crate_open`. Once only.

**Effects:** checkpoint `end_flashback`; give items: `small_hook`; set flags: `b_flashback_complete`; move to `c_middeck`.

**Outcome:** A stranger catches you beside the gold. Your face seems to frighten him; he warns that you have interfered with his plans. His escape pulls you into a distortion of the room. The memory ends with the ship moving beneath you again. Melkior names the stranger: Jarlath Equs. Both men come from 2092; Melkior is pursuing the stolen Americium 1492 hidden in the sarcophagus. Jarlath used the past to let its dangerous radioactivity diminish. You now understand how you reached 1840. As you turn back to Melkior, a loose fastening comes away from his door: a small hook.

**Private hint ladder:**

1. The crate has finally yielded its secret.
2. The sarcophagus links the manor to the ship.
3. Examine the revealed sarcophagus to finish the flashback.

**Research anchors:** [early_ltf2](https://www.abandonware-france.org/ltf_abandon/ltf_solutions.php?id_soluce=30&page=1), [early_walkthroughking](https://www.walkthroughking.com/text/lostintime.aspx), [early_koruchan](https://gamefaqs.gamespot.com/pc/564643-lost-in-time/faqs/55450). Narration is original.

# Act C — The Briscarde: escape

## c_middeck — Between Decks Again

**On arrival — adjust to current state:**

The ship answers your returning footsteps with a long wooden groan. Cannons crowd the passage, and ropes vanish into the beams. You remember this place differently now. The barred hatch behind you conceals another prisoner; ahead, someone still needs help. Small discarded fittings may be more useful than the guns.

### Inspection material

- **barred hatch:** A sliding bar and a separate iron lock keep it shut.
- **hanging ring:** The ring operates the wall compartment found earlier.
- **loose fittings:** There are loose wooden fittings near the ammunition racks. Examine any you have not already collected.

### Exits

- **hold** → `c_hold`. Requires none.
- **rigging closet** → `c_rigging`. Requires none.
- **Melkior's cabin** → `c_melkior`. Requires none.
- **upper passage** → `c_cellar`. Requires `flag:c_captain_entered`.
- **prisoner's hatch** → `c_yoruba`. Requires `flag:c_hatch_unlocked`.

### Actions and state changes

#### c_bend_nail: Bend the nail with the pliers

**Requires:** `item:nail`, `item:pliers`. Once only.

**Portable recipe:** may be performed anywhere in this act when its required items are held.

**Effects:** remove items: `nail`; give items: `twisted_nail`.

**Outcome:** The nail becomes a small hook.

**Private hint ladder:**

1. A straight nail cannot catch a distant loop.
2. The pliers can change the nail's shape.
3. Bend the nail with the pliers.

#### c_make_boat_hook: Bind the broken oar and wooden pin with ribbon, then attach the twisted nail

Equivalent phrasing: make a boat hook; combine oar pin ribbon and hook.

**Requires:** `item:broken_oar`, `item:wooden_pin`, `item:ribbon`, `item:twisted_nail`. Once only.

**Portable recipe:** may be performed anywhere in this act when its required items are held.

**Effects:** remove items: `broken_oar`, `wooden_pin`, `ribbon`, `twisted_nail`; give items: `boat_hook`.

**Outcome:** You bind the pieces into a long hook sturdy enough to pull a rope.

**Private hint ladder:**

1. The high rigging needs reach, not force.
2. Make a handle from the oar and pin; the ribbon binds it.
3. Combine broken oar, wooden pin, ribbon and twisted nail.

#### c_release_hatch_bar: Pull the ring with the towel and set the covered cage in the compartment

**Requires:** `item:towel`, `item:covered_cage`. Once only.

**Effects:** set flags: `c_hatch_unbarred`.

**Outcome:** The cage's weight trips the mechanism. You recover it; the bar over the hatch stays withdrawn.

**Private hint ladder:**

1. The wall compartment has a weighted bottom.
2. Try a heavy object you can retrieve afterward.
3. Use towel on ring, then put the covered cage inside and retrieve it.

#### c_unlock_hatch: Unlock the hatch with the iron key

**Requires:** `flag:c_hatch_unbarred`, `item:iron_key`. Once only.

**Effects:** set flags: `c_hatch_unlocked`.

**Outcome:** The iron key turns. The hatch opens onto Yoruba's cell.

**Private hint ladder:**

1. The bar and lock are separate obstacles.
2. The captain kept an iron key in his cupboard.
3. After retracting the bar, use the iron key on the hatch.

### Earlier ship searches still available

These are the same actions and completion records as in Act A. They permit collecting a previously missed object, not taking it twice.

- `a_take_pin`: Pull a wooden pin from the rack
- `a_take_oar`: Take the broken oar
- `a_take_towel`: Search the middle container
- `a_pull_ring`: Pull the ring using the towel
- `a_take_soap`: Search the opened wall compartment
- `a_shave_soap`: Rub the soap against the chipped cannon
- `a_shave_soap_corkscrew`: Shave the soap with the corkscrew
- `a_lubricate_door`: Put soap shavings in the door runner

**Research anchors:** [late_steph](https://jeux.dokokade.net/2017/07/24/soluce-retrocompatible-lost-in-time-pc-2/), [late_harmen](https://www.harmendeweerd.nl/lost-in-time/). Narration is original.

## c_hold — The Clothes Chest

**On arrival — adjust to current state:**

The low hold feels smaller after your journey through the manor. A stool stands beside the familiar barrels. Against the wall sits a deep chest. Its lock is modest, but the lid fits unusually far into the box. The ship creaks around you while the latch holds firm.

### Inspection material

- **locked chest:** A simple lock protects clothing; the interior has a suspicious spring.
- **stool:** The stool and earlier supplies remain available until collected.

### Exits

- **mid-deck** → `c_middeck`. Requires none.

### Actions and state changes

#### c_pick_chest: Pick the chest lock with the small hook and search it

Equivalent phrasing: open clothes chest; use hook on chest.

**Requires:** `item:small_hook`. Once only.

**Effects:** give items: `ribbon`; set flags: `c_clothed`.

**Outcome:** Inside are clothes you can wear and a ribbon. Beneath the lining, a spring conceals a second compartment.

**Private hint ladder:**

1. The new small hook fits a small lock.
2. Search beneath the clothing after opening the chest.
3. Pick the chest with the small hook, then take the ribbon.

#### c_open_false_bottom: Release the chest's false-bottom spring with the dagger

**Requires:** `done:c_pick_chest`, `item:dagger`. Once only.

**Effects:** give items: `beauty_powder`, `clean_handkerchief`; set flags: `c_false_bottom_open`.

**Outcome:** The false bottom lifts. You take cosmetic powder and a clean handkerchief.

**Private hint ladder:**

1. The chest is deeper than its usable interior.
2. A stiff, narrow blade can move the hidden spring.
3. Use the dagger on the false-bottom spring and search both recesses.

### Earlier ship searches still available

These are the same actions and completion records as in Act A. They permit collecting a previously missed object, not taking it twice.

- `a_take_nail`: Pull the nail from beneath the stool
- `a_find_lamp`: Search behind the near barrel
- `a_find_sponge`: Light and search the dark barrels
- `a_wet_sponge`: Wet the sponge in the bucket
- `a_remove_poster`: Wash the poster with the wet sponge
- `a_remove_knot`: Remove the wooden knot with the corkscrew
- `a_meet_yoruba`: Speak through the hole
- `a_carve_steps`: Carve footholds into the post and return the borrowed knife
- `a_find_oil`: Search the cask
- `a_oil_pump`: Oil the pump handle
- `a_pump_water`: Work the pump
- `a_find_corkscrew`: Search the drained corner beneath the chain

**Research anchors:** [late_steph](https://jeux.dokokade.net/2017/07/24/soluce-retrocompatible-lost-in-time-pc-2/), [late_mogelpower](https://www.mogelpower.de/cheats/loesung.php?id=17601&pf=99). Narration is original.

## c_rigging — Rope Closet and Porthole

**On arrival — adjust to current state:**

A narrow storage bay presses you between hanging tackle and the ship's curved side. One loop hangs above your reach. Nearby, a porthole frames restless water and a thin rope trailing out of sight. These two ends of the same problem are close enough to see, but awkward to hold together.

### Inspection material

- **high halyard loop:** A loop can be pulled down with something long.
- **wall notch:** A firm metal peg would make an anchor.
- **porthole rope:** A bucket hangs outside; the rigging must be held before it can be recovered.

### Exits

- **mid-deck** → `c_middeck`. Requires none.

### Actions and state changes

#### c_lower_halyard: Catch the halyard with the boat hook

**Requires:** `item:boat_hook`. Once only.

**Effects:** set flags: `c_halyard_lowered`.

**Outcome:** The hook catches the loop. You pull its end within reach.

**Private hint ladder:**

1. Reach the loop without climbing.
2. The homemade boat hook is long enough.
3. Use the boat hook on the halyard.

#### c_anchor_halyard: Put the corkscrew in the notch and tie the halyard to it

**Requires:** `flag:c_halyard_lowered`, `item:corkscrew`. Once only.

**Effects:** remove items: `corkscrew`; set flags: `c_halyard_anchored`.

**Outcome:** The corkscrew holds the line fast.

**Private hint ladder:**

1. You need both hands free to retrieve the bucket.
2. The notch can hold the corkscrew as a temporary peg.
3. Anchor the halyard to a corkscrew in the wall notch.

#### c_get_saw: Pull up the porthole rope and search the bucket thoroughly

**Requires:** `flag:c_halyard_anchored`. Once only.

**Effects:** give items: `sawfish_saw`.

**Outcome:** Among the bucket's contents lies the toothed rostrum of a sawfish. It could cut bindings.

**Private hint ladder:**

1. The outside rope supports a container.
2. Raise and thoroughly search the bucket.
3. Pull the porthole rope and take the sawfish saw from the bucket.

#### c_recover_corkscrew: Untie the halyard and retrieve the corkscrew

**Requires:** `done:c_get_saw`, `flag:c_halyard_anchored`. Once only.

**Effects:** give items: `corkscrew`; clear flags: `c_halyard_anchored`.

**Outcome:** You free the corkscrew and put it away. The recovered saw stays with you.

**Private hint ladder:**

1. Your temporary anchor is a useful tool.
2. The bucket has been recovered; the line no longer needs securing.
3. Recover the corkscrew before leaving.

**Research anchors:** [late_steph](https://jeux.dokokade.net/2017/07/24/soluce-retrocompatible-lost-in-time-pc-2/). Narration is original.

## c_melkior — Melkior's Bindings

**On arrival — adjust to current state:**

Melkior has had ample time to plan while waiting for you, and rather less opportunity to move. His bindings are still tight. He glances at your improvised collection of tools with renewed interest. Beyond freeing him, you still have Yoruba to rescue and a captain whose cooperation seems unlikely.

### Inspection material

- **Melkior:** He needs something capable of sawing through his bindings.

### Exits

- **mid-deck** → `c_middeck`. Requires none.

### Actions and state changes

#### c_free_melkior: Cut Melkior free with the sawfish saw

**Requires:** `item:sawfish_saw`. Once only.

**Effects:** remove items: `sawfish_saw`; set flags: `c_melkior_free`, `c_captain_entered`; move to `c_captain`.

**Outcome:** The bindings part. With Oswald's help, Melkior arranges your access to Philibert. The captain promptly confines you to his quarters, leaving his parrot to watch you.

**Private hint ladder:**

1. The rostrum has a serrated edge.
2. The teeth can work through the bindings. Any tool left in the rigging can be recovered later.
3. Use the sawfish saw to free Melkior.

**Research anchors:** [late_steph](https://jeux.dokokade.net/2017/07/24/soluce-retrocompatible-lost-in-time-pc-2/), [late_lockbox](https://advgamer.blogspot.com/2023/09/lost-in-time-one-two-three-lock-box.html). Narration is original.

## c_captain — The Captain's Study

**On arrival — adjust to current state:**

Red-brown beams frame blue-green panels, and a bright parrot surveys the room as if it owns the ship. A desk, a locked cupboard and a maritime painting invite investigation. A balcony opens toward the sea; side doors lead to a washroom and bedchamber. The main door closes firmly behind you.

### Inspection material

- **Galipo the parrot:** He protests whenever you approach the cupboard or painting.
- **desk and chair:** A locked drawer faces a chair with an inspectable underside.
- **locked cupboard:** The parrot watches its silver-key lock.
- **music table:** An empty place waits for an instrument.
- **round furniture mark:** A circular mark suggests something once stood here.
- **battle painting:** A naval battle fills the frame. One cannon flash sits slightly proud of the painted surface.
- **stern balcony:** A pirate flag hangs within reach outside.

### Exits

- **washroom** → `c_washroom`. Requires none.
- **bedchamber** → `c_bedroom`. Requires none.

### Actions and state changes

#### c_take_flag: Take the pirate flag from the balcony

**Requires:** none. Once only.

**Effects:** give items: `pirate_flag`.

**Outcome:** You fold the flag and bring it inside.

**Private hint ladder:**

1. The balcony contains portable fabric.
2. A flag can cover more than a mast.
3. Take the pirate flag.

#### c_search_chair: Search beneath the desk chair

**Requires:** none. Once only.

**Effects:** give items: `silver_key`.

**Outcome:** A silver key is concealed beneath the chair.

**Private hint ladder:**

1. Look underneath furniture, not only on top.
2. Inspect the desk chair's underside.
3. Search beneath the desk chair for a silver key.

#### c_open_desk: Unlock the desk drawer with the brass key and search it

**Requires:** `item:brass_key`. Once only.

**Effects:** give items: `blotter`, `dagger`.

**Outcome:** You find a blotter and a dagger farther back in the drawer.

**Private hint ladder:**

1. The small brass key fits a small drawer.
2. Search the full depth of the desk drawer.
3. Use the brass key on the drawer; take blotter and dagger.

#### c_prepare_cage: Put the golden cage on the round mark and bait it with bananas

**Requires:** `item:golden_cage`, `item:banana_slices`. Once only.

**Effects:** remove items: `golden_cage`, `banana_slices`; set flags: `c_cage_prepared`.

**Outcome:** The cage fits the mark. Banana slices make it more inviting.

**Private hint ladder:**

1. Galipo needs somewhere preferable to his perch.
2. The cage fits the circular mark, and the bananas are bait.
3. Place the cage on the marked furniture and put bananas inside.

#### c_prepare_bowl: Set the bowl beneath Galipo and combine the two odor-making ingredients

Equivalent phrasing: mix salts and paint remover in the bowl; prepare the smell beneath the parrot.

**Requires:** `item:bowl`, `item:salts_flask`, `item:paint_remover`, `flag:c_cage_prepared`. Once only.

**Effects:** remove items: `bowl`, `salts_flask`, `paint_remover`; set flags: `c_odor_ready`.

**Outcome:** A sharp smell rises from the bowl. Galipo shuffles away from his perch and eyes the baited cage.

**Private hint ladder:**

1. Make the perch less comfortable while offering a better place.
2. The bowl belongs underneath Galipo.
3. Use the bowl, salts flask and paint remover beneath Galipo.

#### c_play_record: Set up the phonograph and record, wind it, and start it

**Requires:** `item:phonograph`, `item:record`. Once only.

**Effects:** remove items: `phonograph`, `record`; set flags: `c_music_playing`.

**Outcome:** A tune turns the study into a surprisingly comfortable prison.

**Private hint ladder:**

1. A music table deserves its name.
2. The phonograph needs its record, winding and starting.
3. Place the phonograph and record, turn the crank and start it.

#### c_cover_parrot: Cover Galipo's cage with the pirate flag

**Requires:** `flag:c_cage_prepared`, `flag:c_odor_ready`, `flag:c_music_playing`, `item:pirate_flag`. Once only.

**Effects:** remove items: `pirate_flag`; give items: `covered_cage`; set flags: `c_bird_quiet`.

**Outcome:** Galipo enters the baited cage. Under the flag, with music playing, he finally settles. You can carry the covered cage.

**Private hint ladder:**

1. Food, a changed perch and music prepare him; darkness finishes the job.
2. Wait until the cage, odor and phonograph are ready, then use the flag.
3. Cover the prepared cage with the pirate flag.

#### c_open_cupboard: Unlock the cupboard with the silver key and open its jewelry box

**Requires:** `flag:c_bird_quiet`, `item:silver_key`. Once only.

**Effects:** give items: `iron_key`.

**Outcome:** The jewelry box contains an iron key rather than jewels.

**Private hint ladder:**

1. The bird no longer guards the cupboard.
2. Try the key found under the chair.
3. Use the silver key on the cupboard and search the jewelry box.

#### c_reveal_safe: Press the cannon flash in the painting

**Requires:** `flag:c_bird_quiet`. Once only.

**Effects:** set flags: `c_safe_visible`.

**Outcome:** The painting swings away, exposing a safe.

**Private hint ladder:**

1. The battle picture has one unusually distinct detail.
2. Inspect the flash at the mouth of a cannon.
3. Press the cannon flash to reveal the safe.

#### c_open_safe: Enter 3E21 on the safe

Equivalent phrasing: open safe with the reflected code; enter three e two one.

**Requires:** `flag:c_safe_visible`, `flag:c_safe_code_known`. Once only.

**Effects:** give items: `puzzle_box`; set flags: `c_safe_open`.

**Outcome:** The safe opens. Inside is a small box with movable panels.

**Private hint ladder:**

1. The safe's answer is written elsewhere in reverse.
2. Reflect the blotter in the polished washbasin.
3. Enter the learned combination: 3E21.

#### c_box_key: Rotate the puzzle box and slide its upper panel

**Requires:** `item:puzzle_box`. Once only.

**Portable recipe:** may be performed anywhere in this act when its required items are held.

**Effects:** give items: `small_gold_key`; set flags: `c_box_key_found`.

**Outcome:** A hidden compartment reveals a tiny gold key.

**Private hint ladder:**

1. Examine the box from more than one side.
2. A compartment in the upper side hides its own key.
3. Rotate the box and slide its upper panel to get the key.

#### c_get_revolver: Move the box's front panels and unlock it with the small gold key

**Requires:** `item:puzzle_box`, `item:small_gold_key`, `flag:c_box_key_found`. Once only.

**Portable recipe:** may be performed anywhere in this act when its required items are held.

**Effects:** give items: `revolver`; set flags: `c_box_open`.

**Outcome:** The final panel opens on Philibert's revolver. Its mechanism is locked by something more unusual than an ordinary safety.

**Private hint ladder:**

1. The hidden key belongs to a second opening in the same box.
2. Move the front upper and middle panels to expose the lock.
3. Expose the box's keyhole and use the small gold key.

**Research anchors:** [late_mogelpower](https://www.mogelpower.de/cheats/loesung.php?id=17601&pf=99), [late_harmen](https://www.harmendeweerd.nl/lost-in-time/), [late_gallery](https://www.planete-aventure.net/jeux.php?num_jeu=1626&cat=screenshots). Narration is original.

## c_washroom — The Tarnished Basin

**On arrival — adjust to current state:**

The washroom offers a little privacy and several neglected surfaces. The basin has lost its shine, the rug has curled at one corner, and a cabinet bears a shaped indentation instead of an ordinary handle. Here, at least, the parrot's objections are muffled by a wall.

### Inspection material

- **curled rug corner:** Something lies beneath it.
- **tarnished basin:** A polished surface could reflect small writing.
- **shaped cabinet indentation:** Its outline resembles a seal rather than a keyhole.

### Exits

- **captain's study** → `c_captain`. Requires none.
- **concealed music room** → `c_musicroom`. Requires `flag:c_musicroom_open`.

### Actions and state changes

#### c_get_brass_key: Lift the washroom rug's corner

**Requires:** none. Once only.

**Effects:** give items: `brass_key`.

**Outcome:** A brass key lies beneath the rug.

**Private hint ladder:**

1. One corner of the rug curls upward.
2. Look beneath the loose corner.
3. Lift the rug corner and take the brass key.

#### c_polish_sink: Polish the basin with polish on the clean handkerchief

**Requires:** `item:polish`, `item:clean_handkerchief`. Once only.

**Effects:** set flags: `c_sink_polished`.

**Outcome:** The dull basin becomes reflective.

**Private hint ladder:**

1. The blotter's reversed marks need a mirror.
2. Use polish on a clean cloth, then rub the basin.
3. Polish the basin with polish and the clean handkerchief.

#### c_read_code: Hold the blotter to the polished basin

**Requires:** `item:blotter`, `flag:c_sink_polished`. Once only.

**Effects:** set flags: `c_safe_code_known`.

**Outcome:** In the reflection, the reversed marks become 3E21. You remember the combination.

**Private hint ladder:**

1. Reversed writing can become readable in a reflection.
2. The polished basin is the mirror you need.
3. Reflect the blotter in the polished basin: 3E21.

#### c_open_musicroom: Press the signet ring into the cabinet indentation

**Requires:** `item:signet_ring`. Once only.

**Effects:** set flags: `c_musicroom_open`.

**Outcome:** The seal fits. A concealed passage opens behind the cabinet.

**Private hint ladder:**

1. The cabinet wants an impression, not a conventional key.
2. Compare the office's signet ring with the indentation.
3. Use the signet ring in the cabinet's shaped indentation.

**Research anchors:** [late_mogelpower](https://www.mogelpower.de/cheats/loesung.php?id=17601&pf=99), [late_steph](https://jeux.dokokade.net/2017/07/24/soluce-retrocompatible-lost-in-time-pc-2/). Narration is original.

## c_bedroom — Philibert's Bedchamber

**On arrival — adjust to current state:**

A bed and a broad cabinet crowd the chamber. The room has the air of someone who expects others to tidy after him. A plate of bananas waits nearby. The rug covers an area of floor with a noticeably different outline, and the cabinet's two doors conceal separate spaces.

### Inspection material

- **two-door cabinet:** Both compartments deserve a search.
- **banana plate:** The slices are portable.
- **rug over an outline:** Something below the fabric interrupts the floorboards.

### Exits

- **captain's study** → `c_captain`. Requires none.
- **trapdoor to cellar** → `c_cellar`. Requires `flag:c_bedroom_trapdoor`.

### Actions and state changes

#### c_search_bedroom_cabinet: Open and search both sides of the bedroom cabinet

**Requires:** none. Once only.

**Effects:** give items: `salts_flask`, `bowl`.

**Outcome:** One side holds a flask of salts; the other holds a bowl.

**Private hint ladder:**

1. The cabinet is divided into separate compartments.
2. Opening one door does not search the other.
3. Search both cabinet compartments for the salts flask and bowl.

#### c_take_bananas: Take the banana slices

**Requires:** none. Once only.

**Effects:** give items: `banana_slices`.

**Outcome:** You pocket the banana slices.

**Private hint ladder:**

1. The parrot may respond to food.
2. Look at the plate in the bedroom.
3. Take the bananas.

#### c_cut_rug: Cut around the trapdoor with the dagger

**Requires:** `item:dagger`. Once only.

**Effects:** set flags: `c_bedroom_trapdoor`.

**Outcome:** You free the concealed trapdoor and open a route down to the cellar.

**Private hint ladder:**

1. The floor outline is larger than a loose board.
2. The rug must be cut free around it.
3. Use the dagger on the rug to uncover the cellar trapdoor.

**Research anchors:** [late_mogelpower](https://www.mogelpower.de/cheats/loesung.php?id=17601&pf=99). Narration is original.

## c_cellar — Cellar and Upper Passage

**On arrival — adjust to current state:**

The post under the trapdoor is polished by years of handling and much too slippery to climb. A small opening interrupts its surface. Outside the cellar, the passage offers a practical choice: a storeroom, a more elegant office, or the stairs back toward the lower decks.

### Inspection material

- **slippery post:** An opening suggests a concealed fitting; the surface offers poor grip.
- **storeroom door:** Locked.
- **elegant office door:** Also locked, with a matching type of lock.

### Exits

- **mid-deck** → `c_middeck`. Requires none.
- **bedchamber above** → `c_bedroom`. Requires `flag:c_post_grippy`.
- **storeroom** → `c_storeroom`. Requires `flag:c_storeroom_unlocked`.
- **office** → `c_office`. Requires `flag:c_office_unlocked`.

### Actions and state changes

#### c_get_master_key: Use the corkscrew in the post's opening

**Requires:** `item:corkscrew`. Once only.

**Effects:** give items: `master_key`.

**Outcome:** The opening releases a concealed master key.

**Private hint ladder:**

1. The post's opening needs a temporary handle.
2. Try the tool that already served as a wooden plug puller.
3. Use the corkscrew in the post's opening.

#### c_powder_post: Rub beauty powder on the slippery post

**Requires:** `item:beauty_powder`. Once only.

**Effects:** remove items: `beauty_powder`; set flags: `c_post_grippy`.

**Outcome:** The powder improves your grip enough to climb back to the bedroom.

**Private hint ladder:**

1. You need friction, not another cutting tool.
2. The powder can dry the slippery surface.
3. Use beauty powder on the post.

#### c_unlock_store: Unlock the storeroom with the master key

**Requires:** `item:master_key`. Once only.

**Effects:** set flags: `c_storeroom_unlocked`.

**Outcome:** The storeroom door opens.

**Private hint ladder:**

1. The post concealed a key for this deck.
2. Try the master key.
3. Use the master key on the storeroom door.

#### c_unlock_office: Unlock the office with the master key

**Requires:** `item:master_key`. Once only.

**Effects:** set flags: `c_office_unlocked`.

**Outcome:** The elegant door opens into an office.

**Private hint ladder:**

1. The matching locks suggest one key.
2. The master key fits this door too.
3. Use the master key on the office door.

**Research anchors:** [late_mogelpower](https://www.mogelpower.de/cheats/loesung.php?id=17601&pf=99). Narration is original.

## c_storeroom — The Storeroom

**On arrival — adjust to current state:**

Shelves and containers fill a room designed for things somebody might need later. Most are of no immediate use. A small bottle stands apart from the heavier supplies, its worn label identifying it as metal polish. The passage outside remains quiet.

### Inspection material

- **metal polish:** A small bottle on a shelf.

### Exits

- **cellar passage** → `c_cellar`. Requires none.

### Actions and state changes

#### c_take_polish: Take the bottle of polish

**Requires:** none. Once only.

**Effects:** give items: `polish`.

**Outcome:** You take the metal polish.

**Private hint ladder:**

1. A reflective surface may be hidden under tarnish.
2. Search the shelf for polish.
3. Take the polish bottle.

**Research anchors:** [late_mogelpower](https://www.mogelpower.de/cheats/loesung.php?id=17601&pf=99). Narration is original.

## c_office — The Elegant Office

**On arrival — adjust to current state:**

Someone has tried to make this office feel less like part of a working ship. A secretary desk faces curtains that conceal the room's corner. The quiet is welcome. The drawer and the space behind those curtains offer two small investigations before you return to the captain's more vocal guard.

### Inspection material

- **secretary desk:** Its drawer is accessible.
- **corner curtains:** They conceal an object with a metallic outline.

### Exits

- **cellar passage** → `c_cellar`. Requires none.

### Actions and state changes

#### c_take_ring: Search the secretary desk drawer

**Requires:** none. Once only.

**Effects:** give items: `signet_ring`.

**Outcome:** You find a ring bearing a seal.

**Private hint ladder:**

1. The office has a modest piece of jewelry.
2. Search the secretary drawer.
3. Open the drawer and take the signet ring.

#### c_take_cage: Draw the curtains aside and take the golden cage

**Requires:** none. Once only.

**Effects:** give items: `golden_cage`.

**Outcome:** A golden cage waits behind the curtains. Its base feels surprisingly heavy.

**Private hint ladder:**

1. The corner is concealed rather than empty.
2. Look behind the curtains.
3. Open the curtains and take the golden cage.

**Research anchors:** [late_mogelpower](https://www.mogelpower.de/cheats/loesung.php?id=17601&pf=99). Narration is original.

## c_musicroom — A Room Out of Its Century

**On arrival — adjust to current state:**

The hidden room feels wrong in a way the locked doors did not. A bar, comfortable seats and a record player suggest possessions assembled without much respect for their century. Jarlath has left more than secrecy behind him. For now, the music-making equipment offers a practical use.

### Inspection material

- **low table:** A record rests on its shelf.
- **bar counter:** A phonograph is tucked behind it.

### Exits

- **washroom** → `c_washroom`. Requires none.

### Actions and state changes

#### c_take_music: Search the low table and bar for the record and phonograph

**Requires:** none. Once only.

**Effects:** give items: `record`, `phonograph`.

**Outcome:** You take the record and phonograph. Their presence is another sign that the ship's owner has been traveling through time.

**Private hint ladder:**

1. The captain has a music table but no player beside it.
2. Search both the low table and bar.
3. Take the record and phonograph.

**Research anchors:** [late_mogelpower](https://www.mogelpower.de/cheats/loesung.php?id=17601&pf=99), [late_lockbox](https://advgamer.blogspot.com/2023/09/lost-in-time-one-two-three-lock-box.html). Narration is original.

## c_yoruba — Yoruba and the Sarcophagus

**On arrival — adjust to current state:**

Yoruba raises his head as you descend. His shackles keep him close to the ship's buried treasure. The mast contains a narrow door that refuses to remain open, and a bottle rests high inside it. Something shines between the floorboards. At last, your promises can become more than conversation.

### Inspection material

- **Yoruba:** He is shackled and concerned for his ancestral necklace.
- **shining floor crack:** A metal-bearing pendant is caught below the boards.
- **mast door and high shelf:** The door springs closed; a bottle would break if dropped.
- **cotton behind the sarcophagus:** A bale could cushion a fall.

### Exits

- **mid-deck** → `c_middeck`. Requires none.

### Actions and state changes

#### c_get_magnetite: Retrieve the necklace from the floor crack with the pliers

Equivalent phrasing: retrieve scarab.

**Requires:** `item:pliers`. Once only.

**Effects:** give items: `magnetite`; set flags: `c_necklace_recovered`.

**Outcome:** The scarab pendant clings to the tool. Its magnetite may replace the magnetic rings that operate Philibert's revolver.

**Private hint ladder:**

1. The revolver's lock and the shining necklace may be related.
2. Recover the pendant before leaving the pliers elsewhere.
3. Use the pliers to retrieve the magnetite necklace from the floor.

#### c_enable_gun: Hold the magnetite against the revolver

**Requires:** `item:magnetite`, `item:revolver`. Once only.

**Portable recipe:** may be performed anywhere in this act when its required items are held.

**Effects:** set flags: `c_revolver_enabled`.

**Outcome:** The magnetic interlock releases.

**Private hint ladder:**

1. The revolver was designed to respond to magnetism.
2. Use the magnetic necklace in place of the captain's rings.
3. Apply the magnetite to the revolver.

#### c_free_yoruba: Shoot Yoruba's shackles with the enabled revolver

**Requires:** `flag:c_revolver_enabled`, `item:revolver`. Once only.

**Effects:** set flags: `c_yoruba_free`.

**Outcome:** The shackles break. Yoruba stands free at last.

**Private hint ladder:**

1. The prisoner's restraints are the immediate target.
2. The enabled revolver can break them.
3. Use the enabled revolver on Yoruba's shackles.

#### c_take_cotton: Take the cotton bale from behind the sarcophagus

**Requires:** none. Once only.

**Effects:** give items: `cotton_bale`.

**Outcome:** You drag the cotton bale into reach.

**Private hint ladder:**

1. The bottle above the mast door needs a soft landing.
2. Search behind the treasure container.
3. Take the cotton bale.

#### c_wedge_mast: Prop the mast door open with the pliers

**Requires:** `item:pliers`, `flag:c_necklace_recovered`. Once only.

**Effects:** remove items: `pliers`; set flags: `c_mast_wedged`.

**Outcome:** The pliers keep the door open. You recognize where you will find them again, a century and a half later.

**Private hint ladder:**

1. You have seen these pliers lodged here before.
2. Recover Yoruba's necklace first, then leave the pliers as a wedge.
3. Use the pliers to hold the mast door open.

#### c_get_rum: Put the cotton beneath the shelf and hook down the rum bottle

**Requires:** `flag:c_mast_wedged`, `item:cotton_bale`, `item:boat_hook`. Once only.

**Effects:** remove items: `cotton_bale`; give items: `rum_bottle`.

**Outcome:** The bottle drops onto the cotton without breaking.

**Private hint ladder:**

1. Reach alone would send the bottle crashing down.
2. Make a soft landing before using the boat hook.
3. Place cotton below the shelf and use the boat hook on the bottle.

#### c_remove_label: Soak the rum label loose with the wet sponge

**Requires:** `item:rum_bottle`, `item:wet_sponge`. Once only.

**Effects:** give items: `rum_label`.

**Outcome:** The loosened label names the island destination.

**Private hint ladder:**

1. Melkior needs a destination, not a drink.
2. The bottle's label may provide it intact.
3. Use the wet sponge to remove the rum label.

#### c_leave_ship: Show Melkior the rum label and leave with Yoruba

**Requires:** `item:rum_label`, `flag:c_yoruba_free`. Once only.

**Effects:** set flags: `c_ship_completed`; move to `d_beach`.

**Outcome:** The label gives Melkior the information he needs. The three of you leave the ship for St. Cristobald.

**Private hint ladder:**

1. Yoruba must be free and a destination identified.
2. Show the intact rum label to Melkior.
3. Give Melkior the label after freeing Yoruba.

**Research anchors:** [late_lockbox](https://advgamer.blogspot.com/2023/09/lost-in-time-one-two-three-lock-box.html), [late_harmen](https://www.harmendeweerd.nl/lost-in-time/). Narration is original.

# Act D — St. Cristobald: the rescue

## d_beach — St. Cristobald

**On arrival — adjust to current state:**

Yellow sand gives way to blue water on one side and palms on the other. For the first time in hours, there is room to breathe. Yoruba rests nearby while Melkior studies the inland paths. A waterfall sounds beyond the vegetation; another route leads toward the plantation property.

### Inspection material

- **Melkior:** He has equipment and a short briefing for you.
- **Yoruba:** The rescued man needs rest while you investigate.

### Exits

- **waterfall** → `d_waterfall`. Requires none.
- **plantation property** → `d_property`. Requires none.

### Actions and state changes

#### d_briefing: Ask Melkior for the plan and communications device

Equivalent phrasing: talk to Melkior; take holocom.

**Requires:** none. Once only.

**Effects:** give items: `holocom`; set flags: `d_briefed`.

**Outcome:** Melkior gives you the holocom. Yoruba is ill and needs Makandal, the island healer. Find help for him, then reach Velvet before Jarlath can carry out his plans.

**Private hint ladder:**

1. Talk before leaving the beach.
2. Melkior can give you a way to contact him.
3. Ask Melkior for the holocom and briefing.

**Research anchors:** [late_won](https://advgamer.blogspot.com/2023/09/lost-in-time-won.html), [late_gallery](https://www.planete-aventure.net/jeux.php?num_jeu=1626&cat=screenshots). Narration is original.

## d_waterfall — The Boy at the Waterfall

**On arrival — adjust to current state:**

Water throws a steady curtain of sound across the clearing. A boy watches you from the shelter of the plants, cradling a small animal that barely stirs. A coconut lies nearby. In the rock, an opening seems determined to remain closed to everyone except its chosen visitor.

### Inspection material

- **Amilcar and his manicou:** The animal is cold and needs a drink.
- **coconut:** Its milk is inaccessible through the intact shell.
- **sealed rock passage:** It responds to a particular voice and word.

### Exits

- **beach** → `d_beach`. Requires none.
- **plantation property** → `d_property`. Requires none.
- **passage to Makandal** → `d_makandal`. Requires `flag:d_passage_open`.

### Actions and state changes

#### d_talk_boy: Talk to Amilcar about his animal

**Requires:** none. Once only.

**Effects:** set flags: `d_animal_need_known`.

**Outcome:** Amilcar asks you to help his chilled, thirsty manicou. He knows something about the concealed passage.

**Private hint ladder:**

1. The boy is worried about something he is carrying.
2. Ask about the animal before trying the passage.
3. Talk to Amilcar.

#### d_uncover_cage: Uncover Galipo's cage and remove the pirate flag

**Requires:** `item:covered_cage`. Once only.

**Portable recipe:** may be performed anywhere in this act when its required items are held.

**Effects:** remove items: `covered_cage`; give items: `bird_cage`, `pirate_flag`.

**Outcome:** Galipo blinks at the light. The flag is free to use again.

**Private hint ladder:**

1. The cage's cover is also a piece of cloth.
2. Remove the flag from the covered cage.
3. Uncover the cage to get the pirate flag.

#### d_warm_animal: Wrap the manicou in the pirate flag

**Requires:** `flag:d_animal_need_known`, `item:pirate_flag`. Once only.

**Effects:** remove items: `pirate_flag`; set flags: `d_animal_warm`.

**Outcome:** The small animal settles into the makeshift blanket.

**Private hint ladder:**

1. The animal is chilled.
2. You have a portable cloth large enough to cover it.
3. Wrap the manicou in the pirate flag.

#### d_open_coconut: Pierce the coconut with the corkscrew

**Requires:** `item:corkscrew`. Once only.

**Effects:** give items: `opened_coconut`.

**Outcome:** The shell opens enough to draw out coconut milk.

**Private hint ladder:**

1. The drink is inside a hard shell.
2. The corkscrew can pierce a small opening.
3. Use the corkscrew on the coconut.

#### d_feed_animal: Draw coconut milk into the pipette and feed the manicou

**Requires:** `item:pipette`, `item:opened_coconut`, `flag:d_animal_need_known`. Once only.

**Effects:** set flags: `d_animal_fed`.

**Outcome:** The manicou drinks and begins to stir more strongly.

**Private hint ladder:**

1. A large coconut is awkward for the weak animal.
2. Feed it a little milk with the glass pipette.
3. Use the pipette on the opened coconut, then on the manicou.

#### d_learn_word: Ask Amilcar how the passage opens

**Requires:** `flag:d_animal_warm`, `flag:d_animal_fed`. Once only.

**Effects:** set flags: `d_password_known`.

**Outcome:** Amilcar gives you the word Madjumbe. Your voice alone does not open the passage; it expects his father's voice.

**Private hint ladder:**

1. The boy offered help after you helped his animal.
2. Ask him for the passage's word.
3. Ask Amilcar how to open the passage.

#### d_open_passage: Have Galipo say Madjumbe at the rock passage

Equivalent phrasing: use parrot on passage; ask Galipo to imitate Makandal.

**Requires:** `flag:d_password_known`, `item:bird_cage`. Once only.

**Effects:** remove items: `bird_cage`; give items: `empty_cage`, `flat_key`; set flags: `d_passage_open`, `d_parrot_with_boy`.

**Outcome:** Galipo supplies the voice the rock expects. Amilcar keeps his father's parrot, but gives you the empty cage and the flat key attached to Galipo's leg.

**Private hint ladder:**

1. You know the word; the voice is wrong.
2. The parrot imitates its former owner.
3. Use Galipo to say Madjumbe at the passage.

**Research anchors:** [late_won](https://advgamer.blogspot.com/2023/09/lost-in-time-won.html). Narration is original.

## d_property — Paths Across the Property

**On arrival — adjust to current state:**

The paths divide among shaded huts and the plantation buildings. Everyday life has not stopped for the danger you have brought with you. One track reaches Delia, another Serapion. A dog guards the route toward the kitchen, making its opinion of strangers unmistakable before you are close enough to argue.

### Inspection material

- **guard dog:** It blocks the kitchen path and currently refuses your approach.

### Exits

- **beach** → `d_beach`. Requires none.
- **waterfall** → `d_waterfall`. Requires none.
- **Delia's hut** → `d_delia`. Requires none.
- **Serapion's hut** → `d_serapion`. Requires none.
- **kitchen** → `d_kitchen`. Requires `flag:d_dog_friendly`.

### Actions and state changes

#### d_feed_dog: Give the sugar to the guard dog

**Requires:** `item:sugar`. Once only.

**Effects:** remove items: `sugar`; set flags: `d_dog_friendly`.

**Outcome:** The dog accepts the sweet offering and allows you past.

**Private hint ladder:**

1. You need to change the dog's mood, not fight it.
2. Serapion's gift can be transformed into something sweeter.
3. Give the transformed sugar to the guard dog.

**Research anchors:** [late_abandonware](https://www.abandonware-france.org/ltf_abandon/ltf_solutions.php?id_soluce=31&page=1). Narration is original.

## d_makandal — Makandal's Hut

**On arrival — adjust to current state:**

Blue and purple shadows deepen the hut's interior. Herbs and ropes hang overhead, while the shutters decide how much daylight reaches the table. Makandal treats your arrival as a transaction before it becomes a conversation. A narrow slot in the door is his preferred way to receive an introduction.

### Inspection material

- **door slot:** Makandal wants payment before a full consultation.
- **closed shutters:** Opening them would bring daylight to the table.
- **table and drinking glass:** A glass stands on the tabletop. The shutters control the light falling across it.

### Exits

- **waterfall passage** → `d_waterfall`. Requires none.
- **Delia's hut** → `d_delia`. Requires `flag:d_makandal_task`.

### Actions and state changes

#### d_get_coins: Open the empty cage's hidden base with the flat key

**Requires:** `item:empty_cage`, `item:flat_key`. Once only.

**Portable recipe:** may be performed anywhere in this act when its required items are held.

**Effects:** give items: `gold_coins`.

**Outcome:** The heavy base opens to reveal gold coins.

**Private hint ladder:**

1. The cage remained heavy even without its bird.
2. Try the flat key in the concealed base.
3. Unlock the empty cage's base with the flat key.

#### d_pay_makandal: Put the gold coins in Makandal's door slot

**Requires:** `item:gold_coins`. Once only.

**Effects:** remove items: `gold_coins`; set flags: `d_makandal_paid`.

**Outcome:** The coins earn you an audience.

**Private hint ladder:**

1. The slot is for a gift, not a key.
2. The cage concealed something valuable.
3. Give Makandal the gold coins through the slot.

#### d_get_task: Ask Makandal to heal Yoruba and help you reach Velvet

Equivalent phrasing: ask Makandal to heal Yoruba; ask Makandal for help.

**Requires:** `flag:d_makandal_paid`. Once only.

**Effects:** set flags: `d_makandal_task`.

**Outcome:** Makandal agrees to take care of Yoruba, but demands a piece of Delia's clothing in return. She can also put you in touch with Velvet.

**Private hint ladder:**

1. An audience is only the start of the bargain.
2. Ask about the person you came to find.
3. Ask Makandal for help reaching Velvet.

#### d_give_blouse: Give Makandal Delia's silk blouse

**Requires:** `flag:d_makandal_task`, `item:silk_blouse`. Once only.

**Effects:** remove items: `silk_blouse`; set flags: `d_drink_invitation`, `d_yoruba_care_arranged`.

**Outcome:** Makandal accepts the blouse and confirms that Yoruba is in his care. He invites you to the table for a drink.

**Private hint ladder:**

1. Finish the first half of his bargain.
2. Bring him the clothing recovered at Delia's hut.
3. Give Makandal the silk blouse.

#### d_open_shutters: Open the shutters

**Requires:** `flag:d_drink_invitation`. Once only.

**Effects:** set flags: `d_shutters_open`.

**Outcome:** Daylight reaches the tabletop.

**Private hint ladder:**

1. The holocom needs light.
2. Let daylight into the room.
3. Open the shutters.

#### d_place_holocom: Place the holocom on the table

**Requires:** `flag:d_drink_invitation`, `item:holocom`. Once only.

**Effects:** remove items: `holocom`; set flags: `d_holocom_placed`.

**Outcome:** The device rests on the tabletop, ready to activate.

**Private hint ladder:**

1. You need a distraction on the table.
2. Place Melkior's device where daylight reaches it.
3. Put the holocom on the table.

#### d_activate_holocom: Activate the holocom

**Requires:** `flag:d_holocom_placed`, `flag:d_shutters_open`. Once only.

**Effects:** set flags: `d_makandal_distracted`.

**Outcome:** Melkior's hologram appears. Makandal ducks away in alarm, leaving his glass unattended.

**Private hint ladder:**

1. The device is placed and has daylight.
2. Call up the hologram now.
3. Activate the holocom to distract Makandal.

#### d_use_potion: Pour Delia's potion into Makandal's glass

**Requires:** `flag:d_makandal_distracted`, `item:delia_potion`. Once only.

**Effects:** remove items: `delia_potion`; set flags: `d_glass_dosed`.

**Outcome:** The charm dissolves into his drink while he is distracted.

**Private hint ladder:**

1. Delia's bargain depends on delivery of her potion.
2. Use the distraction to reach his glass.
3. Add Delia's potion to Makandal's glass.

#### d_take_proof: Retrieve the holocom, let Makandal drink, and take his glass

**Requires:** `flag:d_glass_dosed`. Once only.

**Effects:** give items: `holocom`, `makandal_glass`; clear flags: `d_holocom_placed`; set flags: `d_potion_delivered`.

**Outcome:** The hologram vanishes, Makandal drinks, and you recover the empty glass as Delia's requested proof.

**Private hint ladder:**

1. The glass is proof only after he drinks.
2. Put away the holocom, then take the emptied glass.
3. Recover the holocom and take Makandal's glass after he drinks.

#### d_get_bequiet: Ask Makandal for help once more

**Requires:** `flag:d_velvet_met`. Once only.

**Effects:** give items: `bequiet`.

**Outcome:** Irritated by another question, Makandal gives you a potion called Bequiet.

**Private hint ladder:**

1. The two hut owners have further gifts after your meeting.
2. Return to Makandal after meeting Velvet.
3. Ask Makandal again to receive Bequiet.

**Research anchors:** [late_won](https://advgamer.blogspot.com/2023/09/lost-in-time-won.html), [late_abandonware](https://www.abandonware-france.org/ltf_abandon/ltf_solutions.php?id_soluce=31&page=1), [late_gallery](https://www.planete-aventure.net/jeux.php?num_jeu=1626&cat=screenshots). Narration is original.

## d_delia — Delia's Hut

**On arrival — adjust to current state:**

Wooden shutters and hanging household objects give this hut a lived-in warmth. Delia is less welcoming than the room. A book lies within reach, a small mirror stands nearby, and a spider guards a piece of fine cloth with an attention to duty that recalls the captain's parrot.

### Inspection material

- **Delia:** She searches for her glasses when she admits you.
- **recipe book:** Her work depends on it.
- **spider and silk blouse:** The spider will not let you simply take the cloth.
- **small mirror:** Portable and reflective.

### Exits

- **property paths** → `d_property`. Requires none.
- **Makandal's hut** → `d_makandal`. Requires `flag:d_passage_open`.

### Actions and state changes

#### d_hide_book: Take the recipe book while Delia looks for her glasses

**Requires:** `flag:d_makandal_task`. Once only.

**Effects:** give items: `recipe_book`; set flags: `d_delia_away`.

**Outcome:** Unable to find her book, Delia searches another part of the hut. You have a chance to examine the guarded cloth.

**Private hint ladder:**

1. Delia needs a reason to leave you alone.
2. Her misplaced book can send her searching elsewhere.
3. Take the recipe book during her search for her glasses.

#### d_take_mirror: Take the small mirror

**Requires:** `flag:d_delia_away`. Once only.

**Effects:** give items: `mirror`.

**Outcome:** You lift the small mirror.

**Private hint ladder:**

1. A reflective object is within reach.
2. Take the mirror beside the spider.
3. Take the mirror.

#### d_scare_spider: Show the spider its reflection

**Requires:** `flag:d_delia_away`, `item:mirror`. Once only.

**Effects:** set flags: `d_spider_gone`.

**Outcome:** The spider retreats from its own reflection, leaving the blouse unguarded.

**Private hint ladder:**

1. A creature guarding its territory may dislike an apparent rival.
2. Try the mirror on the spider.
3. Show the spider its reflection.

#### d_take_blouse: Take the silk blouse

**Requires:** `flag:d_spider_gone`, `flag:d_delia_away`. Once only.

**Effects:** give items: `silk_blouse`.

**Outcome:** You take the blouse while the spider is away.

**Private hint ladder:**

1. The cloth is no longer guarded.
2. Collect it before concluding the encounter.
3. Take the silk blouse.

#### d_return_book: Return the book and hear Delia's request

**Requires:** `item:recipe_book`, `done:d_take_blouse`. Once only.

**Effects:** remove items: `recipe_book`; give items: `delia_potion`; clear flags: `d_delia_away`; set flags: `d_delia_bargain`.

**Outcome:** Delia brews a love charm for Makandal. Bring his drinking glass back as proof, she says, and she will arrange your meeting with Velvet.

**Private hint ladder:**

1. You have the cloth; now complete the conversation.
2. Return Delia's book so she can make her potion.
3. Return the recipe book and receive Delia's potion.

#### d_meet_velvet: Show Delia Makandal's glass and ask to meet Velvet

**Requires:** `item:makandal_glass`, `flag:d_potion_delivered`. Once only.

**Effects:** remove items: `makandal_glass`; set flags: `d_velvet_met`.

**Outcome:** Delia brings you to Velvet and Celeucie. Maximin is Velvet and Yoruba's child—and the boy who will become your great-great-grandfather. Jarlath intends to destroy that future. Protecting Maximin now means protecting your own existence.

**Private hint ladder:**

1. The empty glass completes Delia's bargain.
2. Bring the proof back and ask for Velvet.
3. Show Delia Makandal's glass to arrange the meeting.

#### d_get_inverter: Ask Delia for further help

**Requires:** `flag:d_velvet_met`. Once only.

**Effects:** give items: `inverter`.

**Outcome:** Delia gives you an inverter: a fantastical preparation that changes certain things into their opposites.

**Private hint ladder:**

1. Return after the meeting; the magician has another useful object.
2. Ask Delia once more.
3. Ask Delia for the inverter.

**Research anchors:** [late_abandonware](https://www.abandonware-france.org/ltf_abandon/ltf_solutions.php?id_soluce=31&page=1), [late_gallery](https://www.planete-aventure.net/jeux.php?num_jeu=1626&cat=screenshots), [late_manual](https://mocagh.org/sierra/lostintime-manual.pdf). Narration is original.

## d_serapion — Serapion's Silence

**On arrival — adjust to current state:**

Serapion listens carefully, then tries to answer. No useful sound follows. His expression makes clear that silence is neither consent nor indifference. Beyond his hut lies the guarded route toward the kitchen. If he can speak again, he may provide both a warning and a way forward.

### Inspection material

- **Serapion:** He wants to speak but has lost his voice.

### Exits

- **property paths** → `d_property`. Requires none.

### Actions and state changes

#### d_make_speakable: Use the inverter on Bequiet

**Requires:** `item:inverter`, `item:bequiet`. Once only.

**Portable recipe:** may be performed anywhere in this act when its required items are held.

**Effects:** remove items: `bequiet`; give items: `speakable`.

**Outcome:** The silencing potion becomes Speakable. The inverter remains usable.

**Private hint ladder:**

1. A potion that removes speech has an obvious opposite.
2. Try the inverter on Bequiet.
3. Combine the inverter and Bequiet to make Speakable.

#### d_restore_voice: Give Speakable to Serapion

**Requires:** `item:speakable`. Once only.

**Effects:** remove items: `speakable`; set flags: `d_serapion_speaks`.

**Outcome:** Serapion's voice returns. He is eager to tell you what he knows.

**Private hint ladder:**

1. You now have a remedy for his silence.
2. Give him the transformed potion.
3. Give Speakable to Serapion.

#### d_hear_warning: Ask Serapion about Jarlath and the child

**Requires:** `flag:d_serapion_speaks`. Once only.

**Effects:** set flags: `d_serpent_warning`.

**Outcome:** Serapion warns that Jarlath's threat has already reached the household. Be especially wary of a serpent near the child.

**Private hint ladder:**

1. Ask for more than directions.
2. Serapion knows about the danger within the household.
3. Ask Serapion about Jarlath and Maximin.

#### d_get_salt: Ask Serapion how to pass the guard dog

**Requires:** `flag:d_serapion_speaks`. Once only.

**Effects:** give items: `coarse_salt`.

**Outcome:** Serapion gives you coarse salt. It is not yet an appealing peace offering.

**Private hint ladder:**

1. The restored witness can help with the blocked path.
2. Talk to Serapion again about the dog.
3. Ask Serapion for help and receive coarse salt.

#### d_make_sugar: Use the inverter on the coarse salt

**Requires:** `item:inverter`, `item:coarse_salt`. Once only.

**Portable recipe:** may be performed anywhere in this act when its required items are held.

**Effects:** remove items: `coarse_salt`; give items: `sugar`.

**Outcome:** What was salt is now sugar. The inverter has lived up to its name.

**Private hint ladder:**

1. The inverter still works.
2. Change the salt into something sweet.
3. Use the inverter on coarse salt to make sugar.

**Research anchors:** [late_abandonware](https://www.abandonware-france.org/ltf_abandon/ltf_solutions.php?id_soluce=31&page=1), [late_won](https://advgamer.blogspot.com/2023/09/lost-in-time-won.html). Narration is original.

## d_kitchen — The Crib Beside the Fire

**On arrival — adjust to current state:**

The room should feel ordinary: a table, a stool, a fire burning low. Instead, stillness gathers around the crib. The cook is unable to help, and a snake moves where the baby lies. A small bag rests on the table. You need to draw danger away before attempting anything else.

### Inspection material

- **crib and snake:** The snake threatens Maximin; direct grabbing is unsafe.
- **table bag:** It contains vanilla and a flower.
- **low embers:** A source of heat.
- **stool by the crib:** A place for a warm lure.

### Exits

- **property paths** → `d_property`. Requires none.

### Actions and state changes

#### d_take_bag: Take the bag from the table

**Requires:** `flag:d_velvet_met`. Once only.

**Effects:** give items: `kitchen_bag`.

**Outcome:** The bag contains a vanilla pod and a flower. Neither should be lost inside it.

**Private hint ladder:**

1. The table holds a useful container.
2. Pick up and inspect the bag.
3. Take the kitchen bag.

#### d_empty_bag: Remove the vanilla and flower from the bag

**Requires:** `item:kitchen_bag`. Once only.

**Portable recipe:** may be performed anywhere in this act when its required items are held.

**Effects:** give items: `vanilla`, `flower`; set flags: `d_bag_empty`.

**Outcome:** You keep both contents separately. The bag is now empty; the flower's dusty scent catches your nose.

**Private hint ladder:**

1. A container should be emptied before being put near a fire.
2. Keep both ingredients in your own inventory.
3. Remove the vanilla and flower from the bag.

#### d_fill_warm_bag: Use the empty bag to collect warm embers

**Requires:** `item:kitchen_bag`, `flag:d_bag_empty`. Once only.

**Effects:** remove items: `kitchen_bag`; give items: `warm_bag`.

**Outcome:** The embers warm the empty bag. You keep its opening clear.

**Private hint ladder:**

1. The snake can be attracted away from the baby.
2. The empty bag can carry warmth.
3. Collect warm embers in the empty bag.

#### d_lure_snake: Place the warm bag on the stool

**Requires:** `item:warm_bag`. Once only.

**Effects:** remove items: `warm_bag`; set flags: `d_snake_lured`.

**Outcome:** The warmth draws the snake toward the bag and away from the crib.

**Private hint ladder:**

1. Place the lure near, but away from, the baby.
2. The stool is the right position.
3. Put the warm bag on the stool.

#### d_capture_snake: Wait for the snake to enter, then close and pick up the bag

**Requires:** `flag:d_snake_lured`. Once only.

**Effects:** give items: `snake_bag`; set flags: `d_snake_captured`.

**Outcome:** The snake enters. You close the bag and lift it clear of the crib.

**Private hint ladder:**

1. Let the lure do its work.
2. Close the bag only once the snake has entered.
3. Wait for the snake, then close and take the bag.

#### d_save_child: Put the captured snake's bag into the fire

**Requires:** `item:snake_bag`, `flag:d_bag_empty`, `item:flower`. Once only.

**Effects:** remove items: `snake_bag`; set flags: `d_maximin_safe`; move to `d_bridge`.

**Outcome:** The threat to Maximin ends. Jarlath appears, his disguise of respectability gone. He flees toward the ravine; you follow, and he turns to bar the crossing.

**Private hint ladder:**

1. The baby is clear, but the contained snake remains dangerous.
2. Finish dealing with the captured snake; retain the flower.
3. Put the snake's bag into the fire, with the flower safely in inventory.

**Research anchors:** [late_abandonware](https://www.abandonware-france.org/ltf_abandon/ltf_solutions.php?id_soluce=31&page=1). Narration is original.

## d_bridge — The Ravine Crossing

**On arrival — adjust to current state:**

A narrow crossing hangs over the green ravine. Jarlath blocks the way, his anger no longer hidden behind politeness. The drop leaves little room for a struggle. He pauses to rub his nose, then tightens his grip on the rope and orders you to stay where you are.

### Inspection material

- **Jarlath:** He stands close enough to confront, rubbing his irritated nose between threats.
- **ravine:** A fall would end the confrontation abruptly.

### Actions and state changes

#### d_defeat_jarlath: Hold the flower toward Jarlath's face

Equivalent phrasing: use flower on Jarlath; throw flower at Jarlath.

**Requires:** `item:flower`, `flag:d_maximin_safe`. Once only.

**Effects:** set flags: `game_won`, `d_jarlath_defeated`, `game_complete`; move to `d_epilogue`.

**Outcome:** The flower sets off a violent sneeze. Jarlath loses his balance and falls from the crossing. You hold your ground.

**Private hint ladder:**

1. This is not a contest of strength.
2. He reacts to the flower's pollen.
3. Use the flower on Jarlath.

**Research anchors:** [late_abandonware](https://www.abandonware-france.org/ltf_abandon/ltf_solutions.php?id_soluce=31&page=1), [late_gallery](https://www.planete-aventure.net/jeux.php?num_jeu=1626&cat=screenshots). Narration is original.

## d_epilogue — A Future Still Possible

**On arrival — adjust to current state:**

The ravine is quiet again. Behind you, a child still has a future; ahead lies the impossible task of explaining where you have been. When familiar voices finally call you back, the journey already has the strange distance of a dream. You remember the choices that made it real.

### Inspection material

- **victory:** Maximin survives; Jarlath's immediate threat has ended. This short epilogue is original connective narration, not a transcription of the final cutscene.

### Actions and state changes

**Research anchors:** [late_won](https://advgamer.blogspot.com/2023/09/lost-in-time-won.html). Narration is original.

# Adaptation decisions and uncertainty

- All read-aloud narration and dialogue here are newly written; guide-backed fixtures and puzzle relationships anchor original atmosphere. No video observation is claimed.
- Scene grouping combines adjacent original views into navigable text locations.
- The chosen memorial instance uses 1803–1840 (37); the chosen wreck instance uses green sword, red cannon, red cannonball. Original codes vary. Fixed clues and answers are consistent within this adaptation.
- Original inventory pixel hunting and repeated container clicks are replaced by thorough search actions.
- Both independently documented soap-shaving tools are supported.
- The flashback has a separate inventory checkpoint. Enter with empty 1992 inventory; restore the previous 1840 inventory upon completion, then add small_hook.
- Inventory capacity is abstracted; the boat does not force the player to abandon heavy objects and later retrieve them.
- The cliff rope stays installed for reversible travel, and the wreck passage stays reversible until the sarcophagus transition. These are recovery conveniences.
- Cutting the repaired hose is gated until the cork is recovered to prevent an avoidable dead end.
- Electrical, chemical, and freezing actions preserve the original game's fictional puzzle logic; the text is not a technical procedure.
- Some decorative placement and connective narration are invented. First-visit descriptions must be updated in narration when completed actions remove or change features.
- Read-aloud notebook wording is a deliberately nonverbatim connective summary, not recovered original dialogue.
- Narration, dialogue paraphrases, prose clues and room compression are newly written. The sequence is guide-derived, not a claim of executed original-game parity.
- Captain safe code is fixed to 3E21 for this adaptation. Original guides include differing examples and explicitly describe randomization. Reflection reveals the chosen value before the code action is accepted.
- Repeated pixel clicks are collapsed into thorough search actions. Container contents remain explicit when mechanically important, especially the kitchen flower.
- Encounter windows are turn-based and wait for the player. There is no real-time countdown, and observational dialogue does not silently cause failure.
- The necklace-before-pliers gate prevents the documented ordering trap. This adaptation uses pliers for retrieval, supported by multiple walkthroughs; other guides permit a corkscrew or other magnetic metal object.
- The bird's inventory lifecycle is explicit: covered cage -> bird cage plus flag -> empty cage plus flat key -> coins; the boy retains Galipo after the passage opens.
- The two potion gags and improvised chemical effects are fictional game rules. Exact operational chemistry is not elaborated beyond the named game inventory objects.
- The flower's dusty scent and Jarlath's visible reaction are added fair-play clues. They are not asserted as original dialogue or original clue placement.
- The final epilogue is original connective narration that leaves the game's reported dream framing ambiguous; it does not claim to transcribe a verified ending video.
- The record is fictional ambient action only; a Live host should narrate it, not start loud audio or music by default.
- The borrowed knife is explicitly returned after carving the footholds. This is an adaptation decision: guides omit it from later inventory, but the exact original removal event was not independently observed.
- The small hook is granted at the flashback return, matching the guide inventory; its loose-door-fastening pickup is original connective narration.
- The hose can be attached before or after repair. Delia accepts the returned book after her blouse has already been delivered. Both orders were checked to avoid permanent blocked states.
- Correct code entry in this edition requires discovering the corresponding clue first. This is an adaptation rule, not a claim that the original forbids lucky guesses.
- Pure inventory combinations marked portable are available throughout their own act. Operations on scenery remain local.
- The healing arrangement for Yoruba and the ancestry reveal are stated explicitly in earned dialogue. Dialogue wording is original.

## Research limits

- Original game executable was not run for this compilation.
- The supplied adaptation is checked with its explicit state model; this does not establish original-game behavioral parity.
- Visual evidence comes from inspected screenshots. Listed YouTube footage was not watched and provides no timestamp-verified claims.
- Scenes combine original camera views; ambience and dialogue are newly written.
- The epilogue is an explicitly authored conclusion rather than a transcription of original ending cinematics.

# Sources

The links identify the evidence used for puzzle mechanics, chronology and limited visual anchors. Different mirrors of the same walkthrough are not counted as independent corroboration. The package contains newly written descriptions and rules, not copied walkthrough passages, original dialogue or game assets.

- **early_sierrahelp:** [Sierra Help — Lost in Time walkthrough](https://sierrahelp.com/Walkthroughs/LostInTimeWalkthrough.html). Opening hold, bilge, and mid-deck mechanics.
- **early_ltf1:** [Abandonware France — Part 1 solution, first page](https://www.abandonware-france.org/ltf_abandon/ltf_solutions.php?id_soluce=30&page=0). Manor entry, elevator, lighthouse, and inventory dependencies.
- **early_neppomuk:** [Neppomuk — Lost in Time Komplettlösung](https://neppomuk.ch/PointClick/Coktel/LiT.pdf). Crypt, lighthouse supply, well, gate, and boat dependencies; cross-check.
- **early_ltf2:** [Abandonware France — Part 1 solution, second page](https://www.abandonware-france.org/ltf_abandon/ltf_solutions.php?id_soluce=30&page=1). Cabin, chandelier, cliff, weighted slab, and wreck sequence.
- **early_walkthroughking:** [The Walkthrough King — Lost in Time](https://www.walkthroughking.com/text/lostintime.aspx). Alternative soap tool; hardened hose; final flashback checks.
- **early_koruchan:** [Koruchan — Lost in Time guide and walkthrough](https://gamefaqs.gamespot.com/pc/564643-lost-in-time/faqs/55450). Initial inventory; randomized codes; flashback continuity; transition hook.
- **visual_planete:** [Planète Aventure — Lost in Time screenshot gallery](https://www.planete-aventure.net/jeux.php?num_jeu=1626&cat=screenshots). Visual anchors independently inspected: timber hold, manor grounds, well, vault, lighthouse rooms, sea gate, coast, fireplace, sarcophagus.
- **late_steph:** [Steph — Soluce rétrocompatible: Lost In Time (2017)](https://jeux.dokokade.net/2017/07/24/soluce-retrocompatible-lost-in-time-pc-2/). Return-to-ship inventory, hook construction, rigging and saw, confirmation that both combination puzzles vary by game.
- **late_mogelpower:** [MogelPower — Lost in Time German walkthrough](https://www.mogelpower.de/cheats/loesung.php?id=17601&pf=99). Captain-suite object locations, concealed cellar route, powder, master key, office, washroom and music room.
- **late_harmen:** [Harmen de Weerd — Lost in Time (2016)](https://www.harmendeweerd.nl/lost-in-time/). Galipo sequence, cupboard and safe, puzzle box, covered-cage mechanism. Retrieved through indexed full-page search; direct page retrieval timed out.
- **late_lockbox:** [Michael — Lost in Time: One, Two, Three Lock Box (2023)](https://advgamer.blogspot.com/2023/09/lost-in-time-one-two-three-lock-box.html). Captain's confinement, magnetic revolver, Yoruba rescue, mast pliers loop, cotton and rum-label destination; example safe code 4C22.
- **late_won:** [Michael — Lost in Time: Won! (2023)](https://advgamer.blogspot.com/2023/09/lost-in-time-won.html). Island geography, Amilcar/manicou/parrot chain, coin payment, holocom distraction, plot context, dream-like ending interpretation.
- **late_abandonware:** [Abandonware France — Lost in Time Part 2 solution, ending page](https://www.abandonware-france.org/ltf_abandon/ltf_solutions.php?id_soluce=31&page=1). Delia/Makandal exchange, two potions, Serapion/salt/sugar, snake bag and retained flower finale.
- **late_gallery:** [Planète Aventure — Lost in Time screenshot gallery](https://www.planete-aventure.net/jeux.php?num_jeu=1626&cat=screenshots). Actually inspected screenshot anchors: captain cabin (#24), beach (#25), Makandal hut (#26), tropical hut (#27), ravine crossing (#28). Original sensory prose extends beyond these visual facts.
- **late_manual:** [Lost in Time official English manual](https://mocagh.org/sierra/lostintime-manual.pdf). Character relations: Maximin is Velvet and Yoruba's child and Doralice's great-great-grandfather; St. Cristobald naming.
- **official_manual:** [Lost in Time original English manual](https://mocagh.org/sierra/lostintime-manual.pdf). text_inspected
- **official_part2_insert:** [Lost in Time Part II official French/Italian insert](https://www.mocagh.org/sierra/lostintimept2-note.pdf). text_inspected
- **pa_screenshots:** [Planète Aventure: Lost in Time screenshot gallery, contributed by LNP45](https://www.planete-aventure.net/jeux.php?num_jeu=1626&cat=screenshots). 28_screenshots_visually_inspected
- **amiga_screenshots:** [Amiga France: Lost in Time](https://www.amigafrance.com/forums/topic/lostintime/). five_screenshots_visually_inspected

## YouTube references for a future footage pass

These links were located and their availability or metadata checked as described below. They were not used as watched footage; no timestamps are claimed.

- [LOST IN TIME (1993) (VOSTFR) | Le Point & Click OUBLIÉ des 90's | Longplay FR (Jeu Complet)](https://www.youtube.com/watch?v=ynYmIln5_vA) — metadata only.
- [Lost in Time (1993) PC game demo trailer](https://www.youtube.com/watch?v=u-HnR23g7oM) — metadata only.
- [Lost in time gameplay (PC Game, 1993)](https://www.youtube.com/watch?v=-eGKo6HID6E) — metadata only.
- [Longplay PC, parts 1–11 (label on linking page)](https://www.youtube.com/playlist?list=PLF9C083C91E6E7325) — embedded link only.

# Reference solution — game master only

This route verifies the authored adaptation. It is not a universal command sequence for the original game. Movements are normal direct exits; action IDs refer to the rules above.

1. `a_take_nail` — Pull the nail from beneath the stool
2. `a_find_lamp` — Search behind the near barrel
3. `a_find_sponge` — Light and search the dark barrels
4. `a_wet_sponge` — Wet the sponge in the bucket
5. `a_remove_poster` — Wash the poster with the wet sponge
6. `go:a_bilge` — Go to The bilge
7. `a_find_oil` — Search the cask
8. `a_oil_pump` — Oil the pump handle
9. `a_pump_water` — Work the pump
10. `a_find_corkscrew` — Search the drained corner beneath the chain
11. `go:a_hold` — Go to The Briscarde — locked hold
12. `a_remove_knot` — Remove the wooden knot with the corkscrew
13. `a_meet_yoruba` — Speak through the hole
14. `a_carve_steps` — Carve footholds into the post and return the borrowed knife
15. `go:a_middeck` — Go to The mid-deck
16. `a_take_pin` — Pull a wooden pin from the rack
17. `a_take_oar` — Take the broken oar
18. `a_take_towel` — Search the middle container
19. `a_pull_ring` — Pull the ring using the towel
20. `a_take_soap` — Search the opened wall compartment
21. `a_shave_soap` — Rub the soap against the chipped cannon
22. `a_lubricate_door` — Put soap shavings in the door runner
23. `a_begin_flashback` — Open the sliding door and speak to Melkior
24. `b_search_tractor` — Search the tractor, basket, and toolbox
25. `b_open_pack` — Open the cigarette pack
26. `b_move_horse` — Give the apple to the horse
27. `b_read_gate_note` — Read the note and remove its dart
28. `b_draw_acid` — Fill the pipette from the battery
29. `b_open_gate` — Apply the filled pipette to the gate lock
30. `go:b_garden` — Go to The garden and well
31. `go:b_entry` — Go to The manor entrance
32. `b_take_portrait` — Take the portrait and its hanging wire
33. `b_take_handle` — Try the door handle
34. `b_take_log` — Take a log
35. `b_drop_key` — Push the inside key out with the dart
36. `b_make_coil` — Wind the portrait wire around the door handle
37. `go:b_garden` — Go to The garden and well
38. `go:b_lighthouse_north` — Go to The lighthouse's north wall
39. `b_take_vinegar` — Take the vinegar bottle
40. `b_empty_barrel` — Remove the barrel stopper with the dart
41. `go:b_garden` — Go to The garden and well
42. `go:b_entry` — Go to The manor entrance
43. `b_charge_battery` — Pour vinegar into the empty battery
44. `b_make_magnet` — Connect the coil to the restored battery
45. `b_get_key` — Draw the fallen key under the door with the electromagnet
46. `b_unlock_manor` — Unlock the manor door
47. `go:b_interior` — Go to The manor room
48. `b_take_manor_tools` — Collect the oar, roasting spit, and extinguisher
49. `b_open_fuse_box` — Open and search the fuse box
50. `b_restore_power` — Repair the broken fuse with the foil
51. `b_place_rod` — Lay the iron rod across the hearth contacts
52. `b_place_log` — Put the log in the fireplace
53. `go:b_entry` — Go to The manor entrance
54. `go:b_garden` — Go to The garden and well
55. `go:b_vault` — Go to The stone vault
56. `b_fit_portrait` — Fit the portrait into the stair recess
57. `b_read_plaque` — Read Philibert's memorial plaque
58. `b_solve_plaque` — Enter 37 and press the cross
59. `go:b_garden` — Go to The garden and well
60. `go:b_lighthouse_north` — Go to The lighthouse's north wall
61. `b_break_window` — Break the basement window with the roasting spit
62. `b_take_hose` — Retrieve the hose through the broken window
63. `b_tie_door_end` — Tie one end of the hose to the lighthouse door handle
64. `go:b_garden` — Go to The garden and well
65. `go:b_vault` — Go to The stone vault
66. `b_tie_lift_end` — Tie the hose's free end to the lift railing
67. `b_pull_lighthouse_door` — Lower the lift remotely to pull the lighthouse door
68. `go:b_garden` — Go to The garden and well
69. `go:b_lighthouse_north` — Go to The lighthouse's north wall
70. `go:b_lighthouse_ground` — Go to The foot of the lighthouse
71. `b_take_shoe` — Take the wooden shoe
72. `b_search_shoe` — Look inside the wooden shoe
73. `b_unlock_basement` — Unlock the basement door with the hidden key
74. `b_take_glass` — Take a loose glass shard from the broken window
75. `go:b_canal` — Go to The lighthouse sea gate
76. `b_open_water_supply` — Open the channel valve
77. `go:b_lighthouse_ground` — Go to The foot of the lighthouse
78. `go:b_lighthouse_study` — Go to The lighthouse study
79. `b_search_study_drawer` — Thoroughly search the desk drawer
80. `b_open_cupboard` — Pry open the cupboard with the manor oar
81. `b_observe_wreck` — Study the wreck through the field glass
82. `go:b_lighthouse_lantern` — Go to The lantern chamber
83. `b_take_kerosene` — Search behind the curtains
84. `b_cut_rag` — Cut a piece of curtain with the razor
85. `go:b_lighthouse_study` — Go to The lighthouse study
86. `go:b_lighthouse_ground` — Go to The foot of the lighthouse
87. `go:b_lighthouse_north` — Go to The lighthouse's north wall
88. `go:b_garden` — Go to The garden and well
89. `go:b_vault` — Go to The stone vault
90. `go:b_crypt` — Go to The crypt below the vault
91. `b_take_cider` — Stand on the barrel to reach a cider bottle
92. `b_launch_cork` — Aim the cider cork at the container on the beam
93. `b_open_crypt_chest` — Set green knife, red pistol, red bullet on the chest
94. `go:b_vault` — Go to The stone vault
95. `go:b_garden` — Go to The garden and well
96. `b_attach_hose_faucet` — Attach the recovered hose to the garden faucet
97. `b_patch_hose` — Patch the hose with fiberglass and resin
98. `b_position_hose` — Put the repaired hose's free end into the well
99. `b_recover_cork` — Turn on the faucet and recover the floating cork
100. `b_make_club` — Cut the hardened hose patch into a club
101. `go:b_lighthouse_north` — Go to The lighthouse's north wall
102. `go:b_lighthouse_ground` — Go to The foot of the lighthouse
103. `go:b_canal` — Go to The lighthouse sea gate
104. `b_soften_algae` — Apply paint remover to the algae
105. `b_scrape_algae` — Scrape away the softened algae with the glass shard
106. `b_free_mechanism` — Apply rust remover to the exposed mechanism
107. `b_open_sea_gate` — Use the roasting spit as the mechanism's handle
108. `b_bail_boat` — Bail out the boat with the wooden shoe
109. `b_patch_boat` — Pack the leak with the curtain rag and cork
110. `b_row_to_cabin` — Row out through the sea gate
111. `go:b_cabin` — Go to The fisherman's cabin
112. `b_search_dresser` — Thoroughly search the dresser
113. `b_search_clothes` — Search the clothing and table
114. `b_read_cabin_note` — Read the paper beneath the chair leg
115. `b_move_chair` — Move the chair beneath the chandelier and climb
116. `b_detach_chandelier` — Release the chandelier fastening with the nail
117. `b_dismantle_chandelier` — Dismantle the chandelier
118. `go:b_beach` — Go to The cabin beach
119. `b_scent_bread` — Soak the bread in fish sauce
120. `b_lure_gull` — Throw the scented bread onto the roof
121. `b_take_rope` — Cut the buoy's rope free with the razor
122. `b_make_grapple` — Attach the rope to the anchor
123. `b_climb_cliff` — Secure the grapple on the cliff and climb
124. `go:b_entry` — Go to The manor entrance
125. `go:b_interior` — Go to The manor room
126. `b_prepare_fire` — Add the handkerchief and kerosene to the hearth
127. `b_get_match` — Break the bottled ship with the club
128. `b_light_match` — Strike the match on the matchbox
129. `b_light_hearth` — Light the prepared fireplace
130. `b_place_barrel` — Put the empty barrel on the raised slab
131. `b_open_barrel` — Open the barrel with the club
132. `b_seal_barrel` — Plug the barrel hole with the candle
133. `b_weight_slab` — Fill the barrel with sand using the wooden shoe
134. `go:b_wreck` — Go to The concealed wreck and sarcophagus
135. `b_take_pliers` — Take the pliers from the mast panel
136. `b_place_floats` — Place the cork floats on the wet floor
137. `b_divert_wire` — Divert the connection with the copper wire
138. `b_cut_wire` — Cut the diverted wire with the pliers
139. `b_take_water` — Fill the pipette from the puddle
140. `b_wet_lock` — Put the pipette's water into the crate lock
141. `b_freeze_lock` — Use the extinguisher on the wet lock
142. `b_break_lock` — Strike the frozen lock with the club
143. `b_end_flashback` — Examine the revealed sarcophagus and finish the recollection
144. `go:c_hold` — Go to The Clothes Chest
145. `c_pick_chest` — Pick the chest lock with the small hook and search it
146. `go:c_middeck` — Go to Between Decks Again
147. `c_bend_nail` — Bend the nail with the pliers
148. `c_make_boat_hook` — Bind the broken oar and wooden pin with ribbon, then attach the twisted nail
149. `go:c_rigging` — Go to Rope Closet and Porthole
150. `c_lower_halyard` — Catch the halyard with the boat hook
151. `c_anchor_halyard` — Put the corkscrew in the notch and tie the halyard to it
152. `c_get_saw` — Pull up the porthole rope and search the bucket thoroughly
153. `c_recover_corkscrew` — Untie the halyard and retrieve the corkscrew
154. `go:c_middeck` — Go to Between Decks Again
155. `go:c_melkior` — Go to Melkior's Bindings
156. `c_free_melkior` — Cut Melkior free with the sawfish saw
157. `c_take_flag` — Take the pirate flag from the balcony
158. `c_search_chair` — Search beneath the desk chair
159. `go:c_washroom` — Go to The Tarnished Basin
160. `c_get_brass_key` — Lift the washroom rug's corner
161. `go:c_captain` — Go to The Captain's Study
162. `c_open_desk` — Unlock the desk drawer with the brass key and search it
163. `go:c_bedroom` — Go to Philibert's Bedchamber
164. `c_search_bedroom_cabinet` — Open and search both sides of the bedroom cabinet
165. `c_take_bananas` — Take the banana slices
166. `c_cut_rug` — Cut around the trapdoor with the dagger
167. `go:c_cellar` — Go to Cellar and Upper Passage
168. `c_get_master_key` — Use the corkscrew in the post's opening
169. `c_unlock_store` — Unlock the storeroom with the master key
170. `c_unlock_office` — Unlock the office with the master key
171. `go:c_storeroom` — Go to The Storeroom
172. `c_take_polish` — Take the bottle of polish
173. `go:c_cellar` — Go to Cellar and Upper Passage
174. `go:c_office` — Go to The Elegant Office
175. `c_take_ring` — Search the secretary desk drawer
176. `c_take_cage` — Draw the curtains aside and take the golden cage
177. `go:c_cellar` — Go to Cellar and Upper Passage
178. `go:c_middeck` — Go to Between Decks Again
179. `go:c_hold` — Go to The Clothes Chest
180. `c_open_false_bottom` — Release the chest's false-bottom spring with the dagger
181. `go:c_middeck` — Go to Between Decks Again
182. `go:c_cellar` — Go to Cellar and Upper Passage
183. `c_powder_post` — Rub beauty powder on the slippery post
184. `go:c_bedroom` — Go to Philibert's Bedchamber
185. `go:c_captain` — Go to The Captain's Study
186. `go:c_washroom` — Go to The Tarnished Basin
187. `c_polish_sink` — Polish the basin with polish on the clean handkerchief
188. `c_read_code` — Hold the blotter to the polished basin
189. `c_open_musicroom` — Press the signet ring into the cabinet indentation
190. `go:c_musicroom` — Go to A Room Out of Its Century
191. `c_take_music` — Search the low table and bar for the record and phonograph
192. `go:c_washroom` — Go to The Tarnished Basin
193. `go:c_captain` — Go to The Captain's Study
194. `c_prepare_cage` — Put the golden cage on the round mark and bait it with bananas
195. `c_prepare_bowl` — Set the bowl beneath Galipo and combine the two odor-making ingredients
196. `c_play_record` — Set up the phonograph and record, wind it, and start it
197. `c_cover_parrot` — Cover Galipo's cage with the pirate flag
198. `c_open_cupboard` — Unlock the cupboard with the silver key and open its jewelry box
199. `c_reveal_safe` — Press the cannon flash in the painting
200. `c_open_safe` — Enter 3E21 on the safe
201. `c_box_key` — Rotate the puzzle box and slide its upper panel
202. `c_get_revolver` — Move the box's front panels and unlock it with the small gold key
203. `go:c_bedroom` — Go to Philibert's Bedchamber
204. `go:c_cellar` — Go to Cellar and Upper Passage
205. `go:c_middeck` — Go to Between Decks Again
206. `c_release_hatch_bar` — Pull the ring with the towel and set the covered cage in the compartment
207. `c_unlock_hatch` — Unlock the hatch with the iron key
208. `go:c_yoruba` — Go to Yoruba and the Sarcophagus
209. `c_get_magnetite` — Retrieve the necklace from the floor crack with the pliers
210. `c_enable_gun` — Hold the magnetite against the revolver
211. `c_free_yoruba` — Shoot Yoruba's shackles with the enabled revolver
212. `c_take_cotton` — Take the cotton bale from behind the sarcophagus
213. `c_wedge_mast` — Prop the mast door open with the pliers
214. `c_get_rum` — Put the cotton beneath the shelf and hook down the rum bottle
215. `c_remove_label` — Soak the rum label loose with the wet sponge
216. `c_leave_ship` — Show Melkior the rum label and leave with Yoruba
217. `d_briefing` — Ask Melkior for the plan and communications device
218. `go:d_waterfall` — Go to The Boy at the Waterfall
219. `d_talk_boy` — Talk to Amilcar about his animal
220. `d_uncover_cage` — Uncover Galipo's cage and remove the pirate flag
221. `d_warm_animal` — Wrap the manicou in the pirate flag
222. `d_open_coconut` — Pierce the coconut with the corkscrew
223. `d_feed_animal` — Draw coconut milk into the pipette and feed the manicou
224. `d_learn_word` — Ask Amilcar how the passage opens
225. `d_open_passage` — Have Galipo say Madjumbe at the rock passage
226. `go:d_makandal` — Go to Makandal's Hut
227. `d_get_coins` — Open the empty cage's hidden base with the flat key
228. `d_pay_makandal` — Put the gold coins in Makandal's door slot
229. `d_get_task` — Ask Makandal to heal Yoruba and help you reach Velvet
230. `go:d_delia` — Go to Delia's Hut
231. `d_hide_book` — Take the recipe book while Delia looks for her glasses
232. `d_take_mirror` — Take the small mirror
233. `d_scare_spider` — Show the spider its reflection
234. `d_take_blouse` — Take the silk blouse
235. `d_return_book` — Return the book and hear Delia's request
236. `go:d_makandal` — Go to Makandal's Hut
237. `d_give_blouse` — Give Makandal Delia's silk blouse
238. `d_open_shutters` — Open the shutters
239. `d_place_holocom` — Place the holocom on the table
240. `d_activate_holocom` — Activate the holocom
241. `d_use_potion` — Pour Delia's potion into Makandal's glass
242. `d_take_proof` — Retrieve the holocom, let Makandal drink, and take his glass
243. `go:d_delia` — Go to Delia's Hut
244. `d_meet_velvet` — Show Delia Makandal's glass and ask to meet Velvet
245. `d_get_inverter` — Ask Delia for further help
246. `go:d_makandal` — Go to Makandal's Hut
247. `d_get_bequiet` — Ask Makandal for help once more
248. `go:d_delia` — Go to Delia's Hut
249. `go:d_property` — Go to Paths Across the Property
250. `go:d_serapion` — Go to Serapion's Silence
251. `d_make_speakable` — Use the inverter on Bequiet
252. `d_restore_voice` — Give Speakable to Serapion
253. `d_hear_warning` — Ask Serapion about Jarlath and the child
254. `d_get_salt` — Ask Serapion how to pass the guard dog
255. `d_make_sugar` — Use the inverter on the coarse salt
256. `go:d_property` — Go to Paths Across the Property
257. `d_feed_dog` — Give the sugar to the guard dog
258. `go:d_kitchen` — Go to The Crib Beside the Fire
259. `d_take_bag` — Take the bag from the table
260. `d_empty_bag` — Remove the vanilla and flower from the bag
261. `d_fill_warm_bag` — Use the empty bag to collect warm embers
262. `d_lure_snake` — Place the warm bag on the stool
263. `d_capture_snake` — Wait for the snake to enter, then close and pick up the bag
264. `d_save_child` — Put the captured snake's bag into the fire
265. `d_defeat_jarlath` — Hold the flower toward Jarlath's face
