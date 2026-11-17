# WAD decoder publication and Agent BBS handoff

Date: 2026-11-17. Documentation-only recovery checkpoint. No runtime changes,
merge, release, hosted CI or shared installation are performed by this commit.

## Existing submission, not a duplicate

The interrupted publication created dedicated MR !120. Its source is
`agent/wad-media-decoder-20261108`; its target is the parser contribution branch
`agent/structural-console-intents-20261108` under !119. Preserve that separation.

Checked implementation head: `73ec8dfc033a6e83db484e4632690eb816dcf0fe`.
Checked target head: `c16f3fc9a11fac715f52b2cf254c4ea5f5e8463a`.

Only the three WAD core files were published at that implementation head.
Fresh local Git-blob calculations match the remote repository tree exactly:

| File | Verified Git blob |
|---|---|
| `src/fdisbull/wad_archive.py` | `6e2c6a5197eb5c62ab20a743df4b21626407e0e1` |
| `src/fdisbull/wad_codecs.py` | `0adf272df71651833765299d6c0f54c5e0443d5d` |
| `src/fdisbull/wad_media.py` | `9dcea0b1f9f9973262b2d4ffd379e8ee0fbec286` |

The complete retained WAD add-on changes 17 files. These 14 changes still need
reconciliation and publication; this documentation commit does not install them:

- `README.md`
- `docs/WAD_MEDIA.md`
- `scripts/verify_wad_media.py`
- `src/fdisbull/capabilities.py`
- `src/fdisbull/cli.py`
- `src/fdisbull/format_media.py`
- `src/fdisbull/format_registry.py`
- `src/fdisbull/media.py`
- `src/fdisbull/skills/fdisbull-investigate/SKILL.md`
- `src/fdisbull/skills/fdisbull-investigate/references/media-modules.md`
- `src/fdisbull/skills/fdisbull-investigate/references/wad-media.md`
- `src/fdisbull/structure_wad.py`
- `tests/test_media_modules.py`
- `tests/test_wad_media.py`

## Retained package

`fdisbull-wad-media-20261108.zip`, 446159 bytes.

SHA-256: `1c94bd728833ee47e26351929872eb0a335331ef9c77b404b443078cc7124787`.

All 50 contributed files match their local manifest size and SHA-256. This is
fresh integrity verification, not a fresh test suite or original-game run.
The source archive is retained in the owner's Library results checkpoint dated
2026-11-17. Its `proposed/` directory is a partial contribution, not a checkout.
The add-on patch and consolidated patch are alternatives; do not apply both.
The add-on predates the three published core files: reconcile those identical
create hunks rather than blindly creating them again. Never replace newer
integration files with older complete-file snapshots.

## Actual BBS records

Task board: https://charm.ing/mossy-owl-1564/agent-bbs-pilot

Project: `fdb`. Stable role: `fdb-wad-media`.

Thread: `e-3f05bbcb131cfbf295ab408d14a3501941d2baf2fb435baa0fe872d4d17d20f3`

Title: **WAD decoder !120: complete source publication and qualification**.
Status: open; source restoration and exact-head qualification are unfinished.

The following files are actual stored reports, attached to the thread. Each was
retrieved by stable report ID and returned `sha256_verified`:

| Stored file | Report ID | SHA-256 |
|---|---|---|
| `fdisbull-wad-media-report-20261108.md` | `report-e8bd7459-1c95-4c4d-94b9-a45c3e17ad3c` | `f16977595f7874bcd008ae3d06aa4aab8ed2e73c3a9b14c5380d7803d87a59b2` |
| `WAD_SOURCE_INDEX.json` | `report-2b49bd3a-97d2-4040-9fdf-02055d5c7e37` | `52d9592fc057b23d8a325675ec4f617f150715b341d1771f0422f778a782def4` |
| `DISCOVERY_WAD_HANDOFF_2026-11-17.md` | `report-8a3c6405-e3de-45cc-8126-06707bbf5e00` | `f649ab57bd3004e469416cab1d2535e86cef8e89d82122faec038b76db0866c1` |

Use `read_thread` and `read_report`, not expiring download URLs. The separate
native BBS guide says task-thread migration has not cut over; no parallel thread
or roster migration was created there. A posted message is not a peer wakeup.

The original BBS supports text reports up to 256 KiB and PDF/PNG/JPEG up to 2 MiB,
but not ZIP or .patch report attachments. The complete source ZIP and private
assets were not uploaded there. Their locations and exact identities are indexed.
No BBS source, visibility or access settings were changed.

## Next work and acceptance

Read current !119/!120 heads before editing. Reconcile and publish the remaining
14 changes; run the source and installed-candidate tests on the actual branch;
verify every published file/tree against the tested source. Keep failures/skips
and historical original-WAD extraction results separate. Remain Draft until
integration is explicitly requested. Do not publish original-derived media,
private captures, saves, ROMs, executable data or credentials.

MIDI-to-WAV pre-rendering remains requested but unimplemented. Preserve MUS/MIDI
originals; explicitly select and pin the renderer, instrument bank and parameters,
cache provenance and loop/tail policy. A chosen synthesized rendition is not
a claim of original sound-card reproduction. Existing sound-effect WAV files
are not synthesized music output.
