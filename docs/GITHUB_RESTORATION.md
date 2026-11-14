# Original GitHub restoration

Original GitHub `seeker-cyber-maker/fDisBull`, stable repository ID `1431097789`, is the preferred source/review platform. The user confirmed the specific-repository Trust & Safety exemption and approved granting connected account `TiGa-RCE` Write access. The invitation was accepted and read back through the ChatGPT connector. `TiGa-RCE/fdisbull` remains a separate partial source import; do not treat it as a mirror or overwrite it.

## Current routes

Push ordinary contributions to `origin` (original GitHub) or `local-hub`. One installed LaunchAgent serializes GitHub ↔ local-hub and GitLab ↔ local-hub, preserving the prior GitLab history and deletion observations. GitHub changes reach GitLab in the ordered passes; GitLab changes receive a bounded GitHub followup when time remains, otherwise the next scheduled run continues. Working checkouts are not advanced automatically. Never use provider push options for GitHub or local-hub; GitLab pushes use `-o ci.skip`.

The existing legacy `scripts/sync_mirrors.py` helper handles only local/GitLab operations. It does not replace the guarded three-way service or manage original GitHub.

## Peer opt-in and installation

The existing v1 config remains valid. The optional `github` object has exactly these keys:

```json
{
  "url": "https://github.com/seeker-cyber-maker/fDisBull.git",
  "cache": "/Volumes/CODEX/Codex_Projects/active/fDisBull-mirror-sync/github-transport.git",
  "state_dir": "/Users/tiga/.local/state/fdisbull-mirror-github",
  "tag_exceptions": [
    {
      "ref": "refs/tags/v0.27.0",
      "hub_oid": "063c09a9492b5660adbd277470504f8843608f29",
      "peer_oid": "01715cf125572c5a4fae11073eea0d1eb1e6c9fe",
      "peeled_commit": "90e748c8bc6a4f068f9136f4d4ec989672421a03"
    }
  ]
}
```

Only this exact GitHub URL is accepted. State/cache directories must be separate from the GitLab pair. Each pair reuses the qualified v1 engine and archive/tombstone format: its internal remote-side key remains `gitlab` for compatibility, while the outer receipt explicitly identifies `github` or `gitlab`. Do not edit a pair's existing refs/deletion history to obtain parity.

For the one-time opt-in, take a backup, hold the existing installation/worker lock, atomically install reviewed runtime/config bytes and record their hashes in the installation manifest. Preserve the LaunchAgent, hook, storage checker and old GitLab refs state. Initialize only the new pair with `mirror_sync_service.py --config <installed-config> --initialize-github`. This captures its baseline without reinitializing the established GitLab state or pushing refs. Normal managed upgrades retain an existing opted-in GitHub config; the installer still rejects unreviewed managed-file hash changes.

Normal runs acquire `topology.lock` before either pair and retain existing per-pair `run.lock` protection. Storage admission, volume UUID checks, cache identity, bounded commands, exact destination leases with ancestry guards, checked-out-branch protection, immutable tag handling and deletion/ambiguous-creation holds remain active. A missing/changed volume or malformed reading holds the affected invocation. No token is stored in config; use the user's existing authenticated Git credential route.

## Historical tag preservation

`v0.27.0` has two distinct annotated tag objects identifying the same commit. Preserve each provider's original canonical tag. Both objects also have portable aliases on all endpoints:

- `archive/github-original/v0.27.0`: `01715cf125572c5a4fae11073eea0d1eb1e6c9fe`.
- `archive/gitlab-local/v0.27.0`: `063c09a9492b5660adbd277470504f8843608f29`.

The exception is accepted only for that exact ref/OID pair and only while both independently peel to the recorded commit. Any other mismatch remains held. This is an explicit historical metadata difference, not a force update or blanket tag exemption. GitHub-managed `refs/pull/*` remain provider-managed and are not copied into branch/tag namespaces.

## CI and release boundary

n8n is the CI owner. The manual GitHub → OVH route was demonstrated by [run 43512305780](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/43512305780), attempt 1, on 2026-11-13. Actions is enabled for the manual-only `ovh-bootstrap.yml`; legacy workflow IDs `394106283` and `394474280` remain disabled. The finite runner uses the shared OVH executor lock and released it after successful cleanup. Other workers must not change Actions settings, dispatch builds, register runners or duplicate CI polling.

The independently verified artifact records control commit `96240c033dcd1860118358d116e23fe3791c440f` and PR #84 candidate `3a7bafa2f4025f7a0a1121807de6604b4c6f758e`. Its real qualification check refused missing ordinary/native receipts: `release_ready=false`. The [PR handoff](https://github.com/seeker-cyber-maker/fDisBull/pull/84#issuecomment-6865708771) therefore establishes infrastructure and artifact delivery only. Existing GitLab/local candidate qualification retains its exact source/scope. This is not a QEMU migration qualification, new release, or offline package acceptance.

## Verification and receipts

Focused local bare-Git witnesses cover GitHub-origin, GitLab-origin and local-origin updates, provider-specific push options, global serialization, exact tag exception checks and legacy compatibility. Before source restoration, all endpoint refs were inventoried; only fast-forward branch updates and new refs were published. Original tag objects and GitHub-only source work were preserved. No refs were deleted.

The private operational receipts live outside Git at `/Volumes/CODEX/Codex_Projects/fDisBull-private/repository-restoration-20261113/`. They contain the source/target inventories, access readback, Actions activation and bootstrap verification, deployment backup and final live topology receipt. A connector repository-list error mentioning missing `link_id` is distinct from repository permissions; exact get/fetch/write/PR operations should be verified through their supported connector tools.

The deployed operational implementation is in [draft PR #84](https://github.com/seeker-cyber-maker/fDisBull/pull/84), based on the existing mirror-service stack. Its deployment does not merge that implementation into product main or qualify a release.
