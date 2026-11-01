# DinoPark text-interface location audit

This is a bounded audit of the pinned DOS game on fDisBull 0.20.0 and the new
native save/load slice on released 0.21.0, not a claim
of exhaustive game coverage or a complete text playthrough. The game runs on
private copies with existing saved games excluded. Visible observations and
financial effects are distinguished from persistent save data.

| Location or activity | Original-game observation | Text-interface status |
| --- | --- | --- |
| Street | Fresh run, post-transaction returns and animated foreground actors observed. | Enter, return, `look` and time advance; strict upper-facade recognition excludes the train, changing signs and the foreground actor path. Known notices/dialogs remain disqualifying. |
| Park office | Fresh startup and bank/street returns observed. | Enter and return; `look`. Other office reports and sale are not exposed. |
| Bank | Full $5,000 repayment and reborrowing observed in the qualified new-game states. | Enter, return, `look`, `repay`, `borrow`; other balances are unqualified. |
| Real Estate | Original land catalogue, map, staging and confirmation observed. | A $500 desert plot can be purchased from the street; the real-estate views are internal to that action, not independently navigable. |
| DinoMart | Closed before land; after land the catalogue and one Coelophysis purchase and placement observed. | Enter, return, `look`, buy one qualified Coelophysis. |
| General Store | Closed before land; catalogue, wood-fence placement and a reopened fenced map observed. | Enter, `look`, exit, buy one qualified wood fence for the occupied pen. |
| Employment office | Closed before land; guide draft and outer roster commit observed. | Enter, return, `look`, and hire one guide in the qualified setup. |
| Dino Diner | Closed before land; 20 separately staged small feeders and original stock/expense/cash commit observed. | Enter, return, `look`, buy 20 small feeders and restock; native commit proof survives food use during confirmation. Current stock is reported separately. |
| Inventory | Original displayed counts observed after dinosaur and fence purchases. | Qualified `check inventory` from the street after the first dinosaur purchase. |
| Window shop | The research guide identifies this separate screen. | Not exposed or freshly tested here. |
| Park operation, reports and events | In a fresh original-game route, entering the park view advanced the day counter; an independent open/closed flag was not identified. | `open park` and `go park` enter the view, `status` reads live state, and `advance time` runs a bounded interval. A recognized quarter notice in the park view can be acknowledged explicitly; parking and other notices, reports and operating controls remain unqualified. |
| Native save/reload | Original Escape menu, name-editor Enter submission, native disk file and fresh OLD GAME loader observed. | `save park NAME`, `list saves`, `load park NAME`, and later-process `--load-save`; checked running-park route only. |
| Connected menu travel | Original transitions through office and street observed. | A named destination can compose verified hops; no selector writes or assumed arbitrary teleport. |
| Auctions, sale and score entry | The handoff records bounded original-game work on these activities. | Not exposed or freshly tested here. |

The initial-state original-location captures are in
`/Users/tiga/Conversions/DinoParkTycoon/dinopark-location-audit-20261028-01`.
The fresh-copy post-land captures are in
`/Users/tiga/Conversions/DinoParkTycoon/dinopark-location-audit-20261028-02`.
The return-control experiment is in
`/Users/tiga/Conversions/DinoParkTycoon/dinopark-location-return-20261028-01`;
it forks private in-session checkpoints, and is not a save/reload game test.
The successful text navigation is recorded in
`/Users/tiga/Conversions/DinoParkTycoon/dinopark-text-locations-20261028-02`.
These cover the specified opening states, not every state-dependent entry or
control. The current interface cannot complete a playthrough: the missing
operations above remain material blockers.
