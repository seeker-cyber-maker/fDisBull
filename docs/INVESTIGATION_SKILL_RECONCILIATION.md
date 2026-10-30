# Investigation skill: depth, reuse and compatible PR guidance

Reviewed against accepted main
`031b53eb953bfdc1d0e23c0ed49441031bad6e06`, 29 October 2026.
This change incorporates reusable investigation methods into the packaged
`fdisbull-investigate` skill. It preserves current runtime/schema contracts
and separates an implemented method from a proposed tool capability.

## Change contract

Keep the evidence depth required by the user's outcome fixed. Reduce redundant
setup, repeated settled probes, lost findings, unnecessary full-reference reads
and serialization of independent work. A cheap observation is useful only when
it can distinguish the alternatives that matter. A bounded probe or accepted
partial slice does not silently narrow a broader authorized task.

The entrypoint routes to nine focused references. New
`references/semantic-contracts.md` covers complete intent contracts and
projection comparisons; `references/formats-and-media.md` covers containers,
mapping, release differences and media reduction. Existing guides gain the
specific procedures below. Target-specific addresses, waits and pixel samples
remain outside the reusable skill.

## Reconciliation matrix

| Source | Incorporated guidance | Boundary retained |
| --- | --- | --- |
| [#2](https://github.com/seeker-cyber-maker/fDisBull/pull/2), [#8](https://github.com/seeker-cyber-maker/fDisBull/pull/8) | Claim coverage, discriminating probes, evidence packets, selective reuse and dependent work. | Preserve required resource/identity checks and live requalification. No new acceptance cache or scheduler API. |
| [#1](https://github.com/seeker-cyber-maker/fDisBull/pull/1), [#4](https://github.com/seeker-cyber-maker/fDisBull/pull/4) | Bounded input-duration comparisons; uninterrupted, same-session and fresh-session restore trials when relevant. | Guest consumption differs from delivery/queue state. No universal timing default or mandatory triplication of every test. |
| [#5](https://github.com/seeker-cyber-maker/fDisBull/pull/5) | Pre-input, post-dispatch, post-state, post-interface and post-persistence capture boundaries; preserve immediate failure evidence. | Screenshot hooks do not automatically establish application readiness; later capture failure does not erase a commit. |
| [#6](https://github.com/seeker-cyber-maker/fDisBull/pull/6), [#8](https://github.com/seeker-cyber-maker/fDisBull/pull/8) | Separate imported-image layers, witnessed runtime reads and reusable resource transformations; require qualified resolution/restoration and explicit fallbacks. | Existing runtime reads remain available. A heap binding or direct experiment does not supply a generic persistent resource-layer API. |
| [#9](https://github.com/seeker-cyber-maker/fDisBull/pull/9) | Document existing requested/displayed/ready admission checks, animation and negative-page calibration, explicit destination evidence. | `outcome_phase` remains descriptive; it does not add checks. Historical E43 findings are not new target acceptance. |
| [#7](https://github.com/seeker-cyber-maker/fDisBull/pull/7) | Link context/control/action identities, semantic events, displayed fields and completion order in an investigation ledger. | The provisional interface extension and canonical export/intake schema are not introduced. |
| [#10](https://github.com/seeker-cyber-maker/fDisBull/pull/10) | Separate facts, knowledge, affordances, transitions, time/RNG, narrative payload and unresolved meaning in both projection directions. | Use finite inventories and explicit denominators; no automatic loss scorer or hidden-state reconstruction from prose. |
| [#11](https://github.com/seeker-cyber-maker/fDisBull/pull/11) | Bind proof subjects, numeric domains, assumptions, correspondence and excluded effects; preserve unknown knowledge. | Keep actual solver statuses/errors and existing narrow builders. World/containment/trace validators remain proposed. |
| [#3](https://github.com/seeker-cyber-maker/fDisBull/pull/3), [#13](https://github.com/seeker-cyber-maker/fDisBull/pull/13), [#14](https://github.com/seeker-cyber-maker/fDisBull/pull/14), [#17](https://github.com/seeker-cyber-maker/fDisBull/pull/17) | Intent contracts, signal/event/queue distinctions, partial effects, clock and save boundaries, public/investigator views, accepted compiler priority. | Preserve original-backed DOS first, current UDL/UIL role semantics, `original_bytes_only` and narrow supported lifts. No general translator or compiler learning is claimed. |
| [#15](https://github.com/seeker-cyber-maker/fDisBull/pull/15) | Watch-stop granularity, transaction versus background effects, partial-result continuation and native-save identity. | Interpret raw evidence without claiming the current watch normalizer or all DinoPark issues are fixed. |
| [#16](https://github.com/seeker-cyber-maker/fDisBull/pull/16) | Separate memory/rendered arrival, range, original exit and stopped input; preserve immediate failures and matched benchmark preparation. | Assistance is declared; geometry and one successful route do not prove universal native traversal. |
| [#20](https://github.com/seeker-cyber-maker/fDisBull/pull/20) | Guide-derived conjectures, typed retained meanings, claim-scoped dependency closure, adaptive workers and fair recovery comparisons. | One controller per guest. Source adapters, shared knowledge schemas and automatic scheduling remain conditional; no schedule is declared universally faster. |
| [#21](https://github.com/seeker-cyber-maker/fDisBull/pull/21) | Media/container validity plus caller completion/timing obligations; preserve unqualified audio duration and identify the selected music player before shortening it. | Rapid EOF/restart and CPU load remain risks to investigate. No native reproduction or media-rewriter capability is claimed. |
| [#22](https://github.com/seeker-cyber-maker/fDisBull/pull/22) | Typed observations with coverage/freshness, explicit unknowns and consistent information policy across consumers. | Historical observations do not restore a guest. Profiles, baseline/delta protocols and synthetic HUDs are not assumed installed APIs. |
| [#23](https://github.com/seeker-cyber-maker/fDisBull/pull/23) | Qualify extraction without executing an installer, multipart provenance, a new private destination and actual extracted inventory. | Discover optional commands in the installed version. Extraction does not provide missing game or loader support. |
| [#24](https://github.com/seeker-cyber-maker/fDisBull/pull/24) | Preserve working low-level IR and reference checks while recovering one complete interaction with explicit UDL correspondence. | Executable conversion and finite transcript agreement do not establish recovered intent or all-path equivalence. |
| [#25](https://github.com/seeker-cyber-maker/fDisBull/pull/25) | Separate container/loader, ISA/mode and guest language; preserve alternate mappings/tails; qualify fixup writes and bounded analysis counts. | Loader-only qualification can be static. This skill update does not add LE support or broaden the UDC source profile. |
| [#26](https://github.com/seeker-cyber-maker/fDisBull/pull/26) | Actual post-notice context, stable recognition plus semantic preflight, observation perturbation, and slot/title/backup identity. | Pending parking continuation is not presented as qualified. Target-specific delays and requested audio silence do not become global defaults. |

The open source heads reviewed were:

| PR | Head |
| --- | --- |
| #7 | `82ab246c7e4e6959957329f2b564c7db45c7f2c6` |
| #9 | `04dd0005619915991c6344ca1f85c2e2277706fe` |
| #10 | `ae39d078595b7557e090b56a036853680374f1e5` |
| #11 | `dd56b46b933b2a373d5e3159ea8e3437118ab908` |
| #15 | `5d9118ae6c967439c935471c1ca4e992ce2fcdfb` |
| #16 | `96c0d8110bf2d07acf173ec2fae6e94f92efffd8` |
| #20 | `0ca7c7231b83d49f9f9d07ddfc522556afa7debe` |
| #21 | `d4dd4559a40f596fd677c7087a0cf9078e87a258` |
| #22 | `27f66db00c652ccc41d99c5185d058c67997e738` |
| #23 | `0778ea4b08cca69b5aa8c8f72b9fb9588c886024` |
| #24 | `20f9d79052dcb8977e2bd52b218a42851eb26916` |
| #25 | `5224d7c6d60c3977baaba0aa4d9a0535e9ff9f72` |
| #26 | `3ecdd76b905f2b8dc5f52096a72f8a648fbc2ae8` |

## Accepted-content decisions

The accepted main roadmap supersedes the old language-first priority in #17:
original native DOS backings and qualified ASM mappings come first; the
supported reduced-C view shares that decoder lineage. Authored cross-language
examples do not become automatic translators.

Investigation ledgers are prose/evidence records, not new fields in strict
scene, proof or IL formats. Native calls can leave partial effects and do not
inherit the pure evaluator's transactional behavior. Player-information policy
is separate from control assistance and from the authorized investigator's
access. Existing refusal, source/version and resource-drift rules remain intact.

The guidance update does not resolve the broader runtime implementation scopes
of the contributing open PRs. Their missing features and target acceptance stay
with those PRs.

## Delivery and verification

All ten Markdown resources are indexed and individually retrievable without a
project. New references are required in wheels and source archives. The full
bundle exceeds the ordinary 64 KiB inline budget; the existing output-artifact
route retains it. The limit is unchanged. The quickstart explains selective
retrieval and full-export recovery.

The focused suite checks discovery, front matter/link integrity, distribution
membership and missing-resource refusal, projectless access, bounded output,
fresh-process full export and escaped-pointer selection:

```sh
python -m pytest -q \
  tests/test_agent_skill_gate.py tests/test_agent_discovery.py \
  tests/test_distribution.py \
  tests/test_scenes.py::test_bundled_investigation_skill_is_readable_without_project \
  tests/test_scenes.py::test_bundled_skill_selective_read_and_invalid_paths \
  tests/test_output_cli.py
```

The integrated focused run passed **52 tests**. In an environment whose default
temporary directory has Git ancestry, select a fresh private non-Git directory
with `--basetemp`; the artifact guard must remain enabled. The new export test
uses the existing 16 KiB selection maximum.

Package qualification uses the existing `scripts/check_dist.py` and
`scripts/check_agent_skill.py` against a newly installed wheel, with isolated
Python outside the checkout. This checks actual delivery rather than matching
phrases in documentation. Build/run receipts and their results belong in the PR
verification record.

An independent diff review found no material conflict with accepted main.
Separate skill-use exercises covered four authored scenarios: committed effects
with failed presentation; limited equivalence and unresolved intent; loader and
media boundaries; and parallel work around one live guest. A fresh follow-up
checked the clarified distinction between static loader qualification and native
execution. These are guidance-use checks, not native-game tests, measured
investigation speedups or proof of general recovery performance.
