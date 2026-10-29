# DinoPark scenes through the original-backed UDC

Development integration, 29 October 2026. This connects the existing DinoPark
native scenes to the Z player from PR #18. It requires the separate v0.23
original-backed DOS UDC APIs; published 0.22.0 does not supply them.

UDL maps original code to UIL; a UDC realizes UIL as code. Z consumes the public
scene view. This integration exercises the first, original-backed DOS compiler:
the unchanged executable and explicit resources are reconstructed from stored
backings, then played in the original engine. DinoPark has **zero semantic
blocks** in this compiler definition. Its qualification is
`original_bytes_only`, not recovered source or independently generated game
semantics. The purchase handlers still send qualified original game inputs;
direct invocation of an isolated purchase effect remains separate research.

## Execution and evidence

`fdisbull.dinopark_z` first imports the qualified DOS executable into a private
project and attaches every non-save resource. It calls the real
`capture_dos_definition` and `compile_dos` APIs, then checks the output manifest,
resource closure and file hashes independently. Only these emitted artifacts
are copied to a disposable runtime directory. Compiler metadata is kept outside
that directory so it does not alter the existing save-resource fingerprint.
The selected original directory is checked for mutation. There is no legacy
copy-only fallback when the UDC is unavailable.

The tested input emitted 184 artifacts: the executable plus 183 resources;
eight existing `DINOSG.*` saves were excluded. Counts depend on the selected
resource directory. The pinned EXE and VARS.DAT identities are in
`fdisbull.dinopark_scenes`; another edition must be qualified explicitly.

The worker translates public Z objects and verbs to the existing native
handlers. Original game code owns cash, debt, purchases, staff, food, time and
saved parks. The `TextScene` class retains the imported implementation's exact
AST hash. Session hooks expose observations, completion events and owned native
processes without changing those business methods. Recognition profiles and
their source hashes ship under `fdisbull/data/dinopark-e55-*`.

The player receives titles, descriptions, visible actions, opaque freshness
tokens and deliberately partial inventory coverage. Register and memory
readback, raw errors, compiler receipts, game files and screenshots stay in the
private work directory. Optional `--oracle` captures independent native test
readback and exports screenshots from stored artifacts; it is never a source
of hidden hints for the player.

## Run Z

Use a Python environment containing the v0.23 UDC candidate, this integration,
the standalone player and normal fDisBull dependencies. Select the genuine
patched DOSBox-X backend explicitly. From a combined source checkout:

```sh
PYTHONPATH=src:player python -m fdisbull_player \
  --backend-command "python -m fdisbull.dinopark_z --game-dir /private/game --backend /private/backend/dosbox-x --work-dir /private/runs/new-z-park" \
  --backend-timeout 60
```

Replace the example paths. The work directory must be new, outside Git and
separate from the original game. It is created with private permissions.
Quoted paths within `--backend-command` are parsed without a shell. Use a new
work directory for each fresh process. Missing UDC support fails before game
copying or launch.

One tested opening sequence is:

```text
look
go bank
repay loan
borrow loan
go street
buy desert plot
go dinomart
buy coelophysis
go street
check inventory
go store
buy wood fence
go employment
hire tour guide
go diner
buy 20 small feeders
open park
check status
check inventory
advance time
save park
list saves
load park
check status
```

Known destinations are office, bank, street, dinomart, store, employment, diner
and park. Multi-hop travel uses the original menu inputs and existing scene
guards; it does not teleport or edit scene fields. Businesses remain closed
before land purchase, and park entry needs the qualified opening prerequisites.
Borrow and repay use the original full quote/full repayment, not an arbitrary
amount. Fence purchase uses the existing occupied-pen placement path.

`inventory` is Z's passive partial carrying view. Use **`check inventory`** for
park quantities: before opening, the street command uses the qualified original
count screen; after opening it uses the original-backed operating report, as
does `check status`. The explicit street object `inventory screen` retains the
narrow original screen handler and can refuse outside its qualified state.
Unrecorded inventory must not be interpreted as absent inventory.

At DinoMart, `buy vegasaurus` and `read vegasaurus` are mapped to the existing
catalogue and encyclopedia handlers. The cold listing describes its visible
price and entry without revealing an unobserved result. Sufficient-funds
purchase behavior was not tested in this batch.

## Saving and stopping

`save park` uses the original native writer, privately under the default name
`zpark`; `--slot` selects another qualified name. `load park` starts a fresh
guest and uses its original OLD GAME loader. To resume from a later Z process,
add `--load-save /private/previous-work/saves/zpark` to the worker command and
choose a new work directory. Native save bundles include their resource
fingerprint and verified field metadata. Original source saves are never
implicitly imported as compiler resources.

The backend protocol's `save`/`load` operations are separate, owned live-session
engine checkpoints used by player live mode. They restore both native state
and scene qualifier metadata, invalidate freshness tokens, and do not promise
cross-process persistence. Native disk changes can invalidate an older live
checkpoint. Use native park save bundles for durable resumption; the acceptance
record below concerns native saves, not a new live-mode acceptance claim.

Requests and responses are bounded; the player has a whole-request deadline.
An unknown post-input outcome returns incomplete and is not retried. Confirmed
purchase events survive a failed follow-up so an agent is not invited to buy
twice. The worker tracks only native processes it owns and terminates them when
the connection is stopped. A known quarter notice can be exposed as its own
context with only its acknowledgment action; this native case remains untested.

See [native verification and open friction](VERIFICATION-DINOPARK-Z-2026-10-29.md)
before treating these bounded scenes as full-game coverage.
