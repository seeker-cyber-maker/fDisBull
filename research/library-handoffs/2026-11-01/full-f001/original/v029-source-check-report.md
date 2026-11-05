# fDisBull 0.29.0: Syndicate compatibility check

## Outcome

The release exists on GitLab. The Syndicate scene/ASCII example is included unchanged,
and 63 authored checks pass against the exact Player implementation from the release tag.
The complete v0.29.0 runtime is **not installed in this sandbox**. No release wheel or
native offline kit was downloaded, no native game was run, and no host/shared installation
was changed. This is a verified source-slice compatibility check, not wheel/native acceptance.

## Identity

- Tag: `v0.29.0`, commit `09a820952ad3f54d0d0707db0515a8010f7eceb1`.
- Released: 2026-11-01 15:48:32 UTC.
- Published package build source: `c03dc4f9d4b5b9d0b374f6423e21962bfb0b07c9`.
- The authenticated comparison spans seven subsequent commits. Returned differences
  affect documentation, recorded installation evidence, AGENTS instructions, and a local
  installation-check script. They do not alter `src/`, `player/`, or `examples/`.
  Package archive bytes themselves have not been compared here.

Primary sources:
[release](https://gitlab.com/brewster-jennings-group/fdisbull/-/releases/v0.29.0),
[tagged notes](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/v0.29.0/docs/RELEASE-0.29.0.md),
[build/tag comparison](https://gitlab.com/brewster-jennings-group/fdisbull/-/compare/c03dc4f9d4b5b9d0b374f6423e21962bfb0b07c9..09a820952ad3f54d0d0707db0515a8010f7eceb1).

## What the release adds

The notes identify Civilization I read-only world snapshots and the Z world-language
parser/writer/validator with a Zork I room/object/exit graph as the new 0.29.0 items.
Z is not Z-machine bytecode and the new world model does not execute gameplay.
The carried 0.28 scope includes capabilities reporting, bounded macOS ARM64 work,
DinoPark recovery improvements, AIL inspection, and our Syndicate spatial Z example.
The release notes state no project-schema change relative to the preceding 0.28 scope;
this is not a claim that old 0.26 byte-containing projects require no migration.

For Syndicate, all 20 files under `examples/syndicate_z_scene/` match the previously
saved proposed sources by their complete Git blob IDs. The exact-coordinate ASCII map,
stacked-cell/elevation display, approach planner, watchdog, guarded relocation model,
and graphical rendering tools are retained. This release does not itself establish
native walking, car boarding, door behavior, whole-map clearance or complete game recovery.

## Fresh local checks

The actual `player/fdisbull_player/player.py` from the tag was retrieved through the
connector. A local copy was reconstructed from the available old file and the retrieved
text, then checked against full Git blob `97410f738a90b011cc7f3a0dc0d2a3c4ce5349bb`.
The match covers the entire 15,669-byte file, not selected lines or inferred semantics.
The scene tests import this exact source module directly. Package initialization,
other release modules, wheel metadata, CLI installation and native backends were not tested.

- 63 authored tests passed, no failures, errors or skips.
- Seven additional commands exercised the actual source Player against an authored,
  in-memory scene: look, map, car route, mission-target path, inventory, reconcile,
  and a refused offline teleport.
- All six read/reconciliation commands sent no action; the authored scene was unchanged.
- The new `reconcile` command correctly reported that this scene provider lacks that
  optional operation. Its availability in the Player does not implement Syndicate recovery.
- Teleport without a live controller was refused. No original game state or file was used.

See `evidence/verification.json`, `scene-tests.txt`, `player-smoke.json` and
`source-identity.json`. `run_source_checks.py` repeats the source-slice check with only
Python's standard library; it is not an installer and makes no network calls.

## Publisher evidence, not rerun here

The release reports 2,600 passing local Linux-container tests with 156 skips; 818 passing
installed macOS tests; 60 passing rebuilt Linux-backend tests; and a macOS full-suite
result of 2,596 passed, 127 skipped, three failures and 23 errors attributed to reproduced
platform fixtures. Hosted CI/native-matrix qualification remains pending. The macOS
backend was reused and requalified rather than rebuilt. These results stay attributed
to the publisher and are not new results from this check.

## Documentation inconsistency worth retaining

The live release and tag are published, but some candidate evidence still says
`published:false`/`tag:null`, and the installation document has pending-publication prose.
The current release object and top-level publication status resolve the existence question.
Do not rewrite historical test results, but reconcile those stale status fields before
using them for automated publication gates. No remote edit or new PR was made here.

## Full runtime transfer still needed

The GitLab connection reads source/release metadata. Its available download action accepts
Markdown upload links, not generic-package registry files. The connected browser was not
available, and this shell has no GitLab CLI/token authentication. The archive download helper
refused before issuing an HTTP download. No access control was bypassed and no credentials
were requested or included.

Download `fdisbull-0.29.0-linux-x86_64-offline.tar.gz` from the
[release package page](https://gitlab.com/brewster-jennings-group/fdisbull/-/packages/74791804)
and attach it to the chat for full sandbox installation. Publisher size: 103,013,282 bytes.
Publisher SHA-256:

```text
b6f43aa6933c8e4e12b643f1dead105d96e5ac0a0bb6c9671032c31fffd97a3f
```

The already-authored download utility in `download/` was recovered from the Library,
reviewed, and retained unchanged. It was **not run** here. It uses your local GitLab
CLI/environment authentication on your own machine; do not put tokens in the conversation.
The inventory in that directory is a prior publisher inventory, not a fresh binary receipt.

## Continuation

After the kit is available, verify the archive and installed core/player/backend identities,
use a separate prefix, run the authored native diagnostic, and requalify scene/session
binding on that backend before resuming native interactions. Keep the already verified
ASCII/planning layer and focus the next game work on door/vehicle approach semantics and
physical traversal feedback. Do not relabel old DOSBox results as v0.29 results.
