# Robb’s KQ1 9.89-second TAS: a route reconstructed from the recording

Primary video: [Robb — Kings Quest 1 TAS speedrun in 9.89 (no audio)](https://www.youtube.com/watch?v=DgW6hNJZjxQ), uploaded 2022-12-16 by Robb (@diploma2007). The title and the final visible timer both say **9.89 seconds**.

The source describes a DOSBox TAS at 157600 cycles. Its author says most of the tricks can also be done manually, with the well section singled out as too fast for a human. That is the author's attributed assessment, not a native replay independently verified by this reconstruction. The window title visibly identifies DOSBox ECE r4319, CPU 157600 cycles, Frameskip 0, Program KQ1. The exact game build, binary hashes, keyboard remapping, graphics selection, and TAS input file are not supplied here. Graphics mode is unknown; the receiving EGA KQ1 2.0F environment needs its own physical qualification.

Use **zero-based frame indices** below. The first decoded frame is f0; frame labels in this document are not one-based video-player counters. Video PTS is the ffprobe manifest timestamp, not the external run timer. The container lasts 20.021 seconds; 599 decoded frames cover PTS 0.000 through 19.933 at nominal 30 fps. The active route is roughly f123–422, with preparation before it and the final modal afterward. Preparation includes a visible restore of save1/kq1sg.1 followed by a restart; that save and the restart’s full state/RNG effects are unknown, so a qualified fresh start is not established.

Read each numbered stage as a landmark-based recreation primitive. Ordinary names such as north/west interpret the classic keypad layout; the overlay visibly lights the physical **top number row**, not a separately verified numpad-to-guest mapping. Check the receiving controller's actual movement intent. A held white tile is not proof of continuous keydown. A disappearing tile is not proof of key release or a movement stop. AGI movement is latched/toggled; repeated same-direction inputs or subframe presses can be invisible. The frame analysis distinguishes visual highlight changes, character displacement, and parser outcomes. No exact native coordinates or input durations are claimed.

This reconstruction considers all 599 encoded frames. **Observed** means visible picture, text, menu state, or key-overlay state. **Inferred** means a command reconstructed from letter highlights and a matching response, or a conventional keypad interpretation. **Unknown** includes hidden key repeats, exact dispatch, native direction timing, game build, and native coordinates. The numbered-label sequences below preserve every detected appearance of 1–9; they are cues rather than a complete executable input script.

## 1. Restart and preparation — f0–122, video 0.000–4.067s

The opening shows a restart-confirmation box at the castle side. Enter appears at f60 and the modal has cleared by f62. F7 at f70 opens a RESTORE GAME path prompt at f71–73. The f72 path prompt shows no entered directory string. The save list at f74–76 displays save1–save4, with its arrow selecting save1. The confirmation at f77–79 names save1 and kq1sg.1, then the game returns at f80. F9 at f81 requests another restart; its confirmation is visible from f83 through f122. Enter at f122 dismisses this final restart prompt and timed active play follows. This is a visible restore UI flow before the final restart. The save1 bytes/state are not supplied, and the final restart’s effect on all restored state or RNG is unverified. Do not describe this as an independently qualified fresh start.

## 2. Castle bounces, rock, and dagger — f123–143, video 4.100–4.767s

Select fast movement: the overlay shows the letters of FAST with 8/Enter near f123–126. Zip through the two walled-garden views and castle gate into the rock grove at f133. Use MOVE ROCK; its response is visible at f134. Use GET KNIFE; the dagger response is visible at f137, and the score reaches 7 by f138. These full commands are reconstructed from letter highlights plus their matching responses. Return through the gate/garden bounces; the numbered-key sequence below preserves the visible steering changes.

Visible numbered-label appearances: f123 (4.100s): 8; f126 (4.200s): 4; f128 (4.267s): 3; f129 (4.300s): 8; f131 (4.367s): 1; f132 (4.400s): 5; f136 (4.533s): 9; f139 (4.633s): 2; f140 (4.667s): 7; f141 (4.700s): 9; f142 (4.733s): 3.

## 3. Clover detour — f144–154, video 4.800–5.133s

Go from the castle side past the lake/cliff into the clover meadow. Approach the small plant on the left, GET CLOVER, and dismiss the pickup message at f149. The score reads 9 by f150. Return via the lake and garden. The visible command intent is supported by the overlay and pickup response, not by a complete captured typing sequence.

Visible numbered-label appearances: f145 (4.833s): 8; f147 (4.900s): 3+5; f150 (5.000s): 7; f151 (5.033s): 2; f154 (5.133s): 9.

## 4. Bridges, pouch, and riverbank — f155–181, video 5.167–6.033s

Cross the flowerbed/riverbank view, wooden canyon bridge, and stone arch bridge into the waterfall-lake view. Zip into the stump field and GET BAG: the pouch response is visible at f166–167, score 12 by f168. Return west through the waterfall/bridge bounces and reach the pine riverbank. An Equals highlight appears near f177; its effect is unknown. The many quick back-and-forth room changes are real visible observations, not collapsed into a single straight walk.

Visible numbered-label appearances: f155 (5.167s): 4; f156 (5.200s): 3; f159 (5.300s): 9; f160 (5.333s): 6; f168 (5.600s): 4; f169 (5.633s): 1; f171 (5.700s): 9; f173 (5.767s): 7; f174 (5.800s): 1; f177 (5.900s): 7; f179 (5.967s): 2; f181 (6.033s): 7.

## 5. Gnome: failed guesses and fallback key — f182–202, video 6.067–6.733s

Enter the gnome lean-to. HI is supported by the f183 overlay and subsequent name challenge. Three unsuccessful guesses are visibly acknowledged around f187, f190, and f192; their exact submitted strings are not recoverable here. Do not substitute the correct-name solution. The gnome gives a fallback gold key at f195–196. Collect it with GET KEY near f199–200; the pickup response is visible and the score reaches 15 by f202. GET KEY letter sets also appear during the guessing phase, but that does not prove the exact order or parser dispatch of every submission.

Visible numbered-label appearances: f195 (6.500s): 1; f197 (6.567s): 9; f199 (6.633s): 7; f202 (6.733s): 4.

## 6. River-edge alignment and speed menu — f203–224, video 6.767–7.467s

Bounce between the river/tree/boulder scene and gnome lean-to, then align at the river scene's far right edge. The menu around f209–211 selects Normal; another menu near f224 selects Fast. The visible route goes north along the far right edge into the hole-island view at f225. Describe that as the video's observed edge crossing; no exact native x-coordinate or transferable collision proof is recovered from these pixels. Use the edge, tree, and boulder as visual anchors and qualify alignment afresh in the receiving runtime.

Visible numbered-label appearances: f203 (6.767s): 9; f204 (6.800s): 3; f206 (6.867s): 7; f208 (6.933s): 8 [menu possible]; f211 (7.033s): 1 [menu possible]; f215 (7.167s): 8; f221 (7.367s): 2 [menu possible].

## 7. Island to mushroom grove, then back — f225–239, video 7.500–7.967s

In the hole-island scene, move down along the cliff, west beneath the foreground bush, northwest, then west into the mushroom grove. The visible top-row onsets include 2 at f225, 4 at f227, 7 at f228, and 3 at f231; a repeated west action can be hidden while 4 stays highlighted. GET MUSHROOM around f232–234; the response is visible at f234 and score 16 by f235. Return east through the island, then down to the river/tree/boulder view at f239. Exact travel times between the encoded frames are unknown.

Visible numbered-label appearances: f225 (7.500s): 2; f227 (7.567s): 4; f228 (7.600s): 7; f231 (7.700s): 3; f235 (7.833s): 6; f237 (7.900s): 1; f239 (7.967s): 8.

## 8. Drop cave, diamonds, and side passage — f240–254, video 8.000–8.467s

Enter the hole/drop cave and descend past the yellow pile and rocks. An OUCH message appears at f247–248; its cause is unqualified. OPEN BAG is directly readable at f249 and the diamonds response follows at f250–251, with score 19 by f253. Move down into the tunnel/side passage. GIVE BAG is already being prepared in the tunnel; it is directly readable in the next room.

Visible numbered-label appearances: f250 (8.333s): 2; f252 (8.400s): 7; f254 (8.467s): 1.

## 9. Rat payment and door — f255–266, video 8.500–8.867s

In the rat/wooden-door room, GIVE BAG is directly readable at f255–257. The rat accepts the treasure at f258 and merges into the wall at f259–260; score changes from 19 to 13. OPEN DOOR is directly readable at f261–263; the door-open response appears at f265–266. Pass through the door into the leprechaun entry cave, then onward into the separate throne chamber.

Visible numbered-label appearances: f261 (8.700s): 4; f263 (8.767s): 1.

## 10. Clover protection and shield — f267–281, video 8.900–9.367s

In the leprechaun entry cave, the response explicitly attributes safe passage to the four-leaf clover at f267–268. Cross into the separate red-carpeted throne chamber at f269 and advance toward the throne/shield area. A King's-magic proximity-blocking message appears at f270–271; no KILL KING command is observed. Use GET SHIELD around f273; the shield-pickup message appears at f274–275, score 21 by f276. Retreat toward the left exit/stair landing, preserving the visible south, west, north, and northwest steering cues listed below.

Visible numbered-label appearances: f269 (8.967s): 6; f271 (9.033s): 7; f273 (9.100s): 5; f276 (9.200s): 2; f278 (9.267s): 4; f279 (9.300s): 8.

## 11. Shrink at the small opening — f282–292, video 9.400–9.733s

Move across the stone landing to the small left opening. EAT MUSHROOM is supported by the f288–289 letter set and the shrink response at f290–291. This occurs after shield pickup. Exit through the small opening; outside, the regrowth message appears at f292 and score reads 24. Do not eat the mushroom before entering the shield chamber when recreating this route.

Visible numbered-label appearances: f282 (9.400s): 7; f284 (9.467s): 1; f287 (9.567s): 4; f292 (9.733s): 2.

## 12. Key door — f293–306, video 9.767–10.200s

Zip through the pine field to the secret tree-door exterior. OPEN DOOR KEY is readable in this sequence, including f300–304. The unlock response appears at f305–306; score is 26 by f307. Enter the tree opening. The observed numbered-label sequence suggests north, southwest, southeast, northeast, north, and northeast; repeated or subframe inputs remain unresolved, and the receiving controller must resolve its own timing against the pictured landmarks.

Visible numbered-label appearances: f293 (9.767s): 8; f294 (9.800s): 1; f297 (9.900s): 3; f298 (9.933s): 9; f302 (10.067s): 8; f303 (10.100s): 9; f306 (10.200s): 4.

## 13. Climb the winding stairs — f307–325, video 10.233–10.833s

Follow the stair landings through successive rooms, then the stairs curving around the large orange trunk, and emerge on the giant plateau. The frame analysis retains all visible numbered-key onset frames: f307, f309, f314, f316, f318, f321, and f323. The character appears at different screen positions across stair-room entries; the mechanism is unqualified, so a direction should not be inferred from the location jump alone. Intermediate redraw frames are retained.

Visible numbered-label appearances: f307 (10.233s): 9; f309 (10.300s): 3; f314 (10.467s): 3; f316 (10.533s): 2; f318 (10.600s): 7; f321 (10.700s): 2; f323 (10.767s): 4.

## 14. Sleeping giant and chest — f326–334, video 10.867–11.133s

Enter the clearing and approach the chest while the giant visibly falls asleep. GET CHEST is already prepared near f328. The sleep message appears at f329–330, then the chest-pickup response at f332–333; score reaches 41 by f334. The split label alone is not used as inventory evidence. The video does not establish that the same giant behavior or timing will occur on another run; use the visible sleep cue before claiming that branch.

Visible numbered-label appearances: f331 (11.033s): 6; f334 (11.133s): 3+8.

## 15. Reverse stairs and reach the well — f335–355, video 11.167–11.833s

Return through the cave mouth, reverse the upper landing and curved stair rooms, descend the first stairs, and emerge from the secret tree door. Cross the thorny field into the well scene. This is a multiscene reverse route, not a single room. The observed numbered-key appearances are retained in the chapter sequence below.

Visible numbered-label appearances: f338 (11.267s): 9; f341 (11.367s): 1; f342 (11.400s): 8; f348 (11.600s): 4; f350 (11.667s): 2; f351 (11.700s): 7; f352 (11.733s): 1; f354 (11.800s): 4.

## 16. Bucket, lower rope, climb rope — f356–364, video 11.867–12.133s

At the well, the letter overlay and response support CUT ROPE: the rope is cut and the bucket taken at f357–358, score 43 by f359. LOWER ROPE is directly readable at f359–360, followed by the descent response at f361. CLIMB ROPE is readable at f362–364 and the actor enters the well. A separate FILL BUCKET or GET WATER command is not visibly established; do not insert one as a video-observed step.

Visible numbered-label appearances: f363 (12.100s): 2.

## 17. Normal dive, then fast underwater traversal — f365–383, video 12.167–12.767s

Inside the shaft, the score reaches 44. Open the speed menu: Fast is highlighted at f367 and Normal at f369. DIVE letter tiles appear with this change; a subsequent underwater view and score 48 establish the visible dive outcome. TOSS WATER is pretyped underwater and readable by f376, before reaching the dragon. Reopen the menu and choose Fast by f379. Navigate toward the right opening using the visible south, east, southwest, and south cues. Menu 8/2 highlights are menu-navigation candidates here; their exact dispatch is unqualified, and they must not be blindly translated into world movement. The author singles out the well section as too fast for a human in the source description.

Visible numbered-label appearances: f366 (12.200s): 8 [menu possible]; f372 (12.400s): 1 [menu possible]; f377 (12.567s): 2 [menu possible]; f379 (12.633s): 6 [menu possible]; f381 (12.700s): 1; f383 (12.767s): 2.

## 18. Dragon and mirror — f384–394, video 12.800–13.133s

Enter the dragon chamber with TOSS WATER already prepared. Its exact Enter-dispatch instant is not independently visible; the water-hit/dragon-retreat response appears at f386–387. GET MIRROR is readable at f388. The mirror-pickup response follows at f389–390; score reaches 62 by f391. Follow the visible northwest/south/northwest/west steering changes to the rock-side exit, then pass through the mixed redraw at f394. Intermediate scores before a pickup message has resumed are not treated as completed inventory commits.

Visible numbered-label appearances: f386 (12.867s): 7; f388 (12.933s): 2; f390 (13.000s): 7; f391 (13.033s): 4; f394 (13.133s): 2.

## 19. Return across the fields to the castle door — f395–415, video 13.167–13.833s

Leave the fenced cave exterior, cross the fenced pasture and brush field, reach the flowerbed riverbank, and return through the castle-side/garden/gate bounces. Approach the front doors near f413. OPEN DOOR is supported by the overlay and open-door response at f415; the exact keystroke ordering is not fully resolved. Enter the hall.

Visible numbered-label appearances: f397 (13.233s): 1; f400 (13.333s): 9; f403 (13.433s): 3; f404 (13.467s): 9; f407 (13.567s): 2; f410 (13.667s): 4; f412 (13.733s): 8.

## 20. Hall, throne, and observed stop — f416–598, video 13.867–19.933s

Move through the hall into the throne room. The final visible directional onset is 1 at f417. At f422 (PTS 14.067), the king-steps-aside message is visible with score 63/158 and the external timer becomes blue at 9.89. At f421 it was still green at 9.87. The same modal/score/timer persists to f598 (PTS 19.933). This is the video's declared TAS endpoint; the recording does not show a later coronation, inventory screen, or a newly reproduced native ending.

Visible numbered-label appearances: f417 (13.900s): 1.

## Practical unknowns for the recreating agent

The exact failed-guess strings, repeated key press order inside persistent highlights, all between-frame direction changes, parser dispatch instants, TAS scheduling, game build/hash, remappings, RNG state, and collision coordinates remain unknown. OPEN BAG, GIVE BAG, OPEN DOOR, OPEN DOOR KEY, LOWER ROPE, CLIMB ROPE, TOSS WATER, GET CHEST, and GET MIRROR have readable parser-line support in the indicated windows; other full command names are reconstructed from letter sets and matching responses. There is no separately established FILL BUCKET/GET WATER command, KILL KING command, magic-ring action, or inventory screen. Selected split names are timing labels. The last recorded game state is the king-steps-aside modal at 63/158, with the author's external timer stopped at 9.89; later completion text is not shown.

Keep each recreated landmark transition and command outcome as a new ordinary-input observation. This reconstruction does not establish that a receiving native controller has reproduced the route.

## Additional visible-motion checks

Key highlights alone do not recover every direction change. Thirteen intervals were also checked against character displacement in the recording. Each compares f(i−2)→f(i−1) with f(i−1)→f(i); i identifies the first frame showing the changed displacement. These are screen-pixel observations, not exact native input times or native coordinates.

- f157: visible westward then southeastward displacement.
- f175: subsequent southwestward displacement is visible, but the small incoming displacement can partly be pose variation.
- f205: excluded from a continuous same-room turn claim because foreground redraw already mixes the river and next gnome scene.
- f228: visible downward then westward displacement at the island cliff.
- f232: visible westward then southeastward approach to the mushroom.
- f264: visible westward then southwestward displacement.
- f270: excluded from a same-room turn claim; the interval crosses the entry cave into the separate throne chamber at f269.
- f287: southwestward then northwestward-sign displacement near the small opening; exact native direction remains unknown.
- f300: southeastward then northeastward displacement is plausible, with tree occlusion and pose uncertainty.
- f317: the small incoming displacement leaves the heading change uncertain.
- f320: partial redraw and occlusion prevent a continuous native northwest-turn claim.
- f344: outgoing displacement is north-dominant; its small horizontal component can be pose variation and does not confirm native northwest.
- f350: visible southwestward then westward displacement.

The measured anchor was the bottom-center of a red-torso image region, not the character’s feet or a native baseline. Color-based matching was unique on 206 frames; unmatched or occluded frames preserve an unknown movement state. Inputs between the recorded frames remain unavailable.
