# Independent review verification, 2026-10-31

This is a source and authored-fixture verification of a supplied third-party
review. The review is evidence to check, not authority. Remote branch objects
and pull-request metadata were refreshed for this investigation. No original
game files or local-host installations were inspected.

## Release decision

Frozen current candidate #55 is `90e748c8bc6a4f068f9136f4d4ec989672421a03`,
based on main `f94a5cd74b153b58f56c9fdb6c653d2e295f5ee6`.
The reported DOS compiler and UDC runtime defects are in deferred stacks,
not this candidate. Fix them before admitting those stacks to the next release;
do not import their unrelated features into the current release to obtain fixes.
The terminal-resource omission gate below is a low-risk current-candidate
validation improvement, not a demonstrated missing shipped resource or release
blocker. This branch does not modify #55.

## Verified assertions

| Assertion | Verdict and evidence | Priority |
| --- | --- | --- |
| DOS data receipt hashes input before near-pointer patches | Confirmed on #54 `5556f8181be656b29db6297913ae9ae0a82cd859` and #57 `b6051fe212c9e17a490e9955e97ed657b0518a78`; affected module identical. Authored near-pointer regression fails on the final-region digest before the fix. | Fix before next-release DOS integration. |
| Negative i16 module returns are zero-extended | Confirmed on #38 `2857c42c5b0754e77ed36ab0a7ee9d258e8b9fa3` and descendants. C adapter begins in Linux stack #42 `30d06bc85fe02ad082e29b18863c7fc0571ddfb3`. Negative boundary return regressions distinguish sign extension from unsigned behavior. | Fix before next-release UDC integration. |
| Layer event comparison includes implementation provenance | Confirmed on #38 and descendants. Qualification excludes block_id/evidence while run_layer compares raw events. Metadata-only replacement fails despite equal public events. Payload/order/resource differences must continue to fail. | Fix before next-release UDC integration. |
| Game/Civ/friction branches lack portable high-FD test | Confirmed on #47 `2b8d4db9fda90edc11dfedf77b8acab1e4d1474c`, current #50 `fcff5549c18a54bf9fa4cbb3594ca67e46e0ef6b`, and current #48 `09344df29b8f773718ed367561c255c165f7653f`. Forced dash FD64 reproduces Bad fd number. Linux #42 already contains the repair; descendants forked earlier. | Repair next-release stack acceptance without blind cherry-picks. |
| Five UDC tests import pruned examples unconditionally | Confirmed on current Civ stack; actual tool ZIP collection also reveals three inherited Civ example modules, eight collection errors total. | Repair next-release source-package collection. |
| Exhaustive interpreted dice loop takes 25 minutes | Not reproduced: all 196608 executions completed in 11.58 seconds in this cloud environment. Historical hosted duration and attribution remain unverified; different hardware/run conditions can differ. Full interpreted coverage is preserved. | No unsupported optimization. |
| NE branch lacks sibling type catalog / 0.26.1 guides | Historically true on `cd9b4f892b549209020c8b74890a818e11462d2a`; resolved in candidate, which contains both NE and type catalog, all eight guide files, and integration-0261 evidence. | No current fix. |
| Source catalog adds dependencies/evidence | Confirmed on #52 `204bc05994cc24206c9d30d3577e8647faec14ba`: unicorn 2.1.4, tree-sitter 0.25.2, tree-sitter-c 0.24.1, source extra, CivD/source-map evidence. Deferred from candidate. | Preserve at future integration. |
| Ghidra resource is absent from required lists | Confirmed on #49 `5b778238df5e4947e8c2758a4388a42dd52771d1`. data/*.txt selects it, but authored ZIP without it passes the checker. Gate gap, not observed shipping omission. | Next-release gate hardening on #49 base. |
| Console Java/vectors/evidence need reconciliation | Feature inventory confirmed, reviewed head stale. Current `988e57dea9db06dacf755818f883cb8aed4def83` includes both Java resources, vectors and six evidence files in package lists. No missing-package defect demonstrated; absent from candidate. | Future integration inventory. |
| Latest DinoPark audio commits skip CI | Confirmed on `ee49111ab3993b23dd9ccb008a9a1f56a000d963`: e6257bd/d8f02d0/ee49111 have skip-ci markers. Candidate intentionally pins earlier 16d4704 and excludes this audio work. | Qualify deferred changes before admission. |
| Terminal JSON is not required by check_dist | Confirmed on DinoPark head and candidate. data/*.json already ships it; authored otherwise-valid archive lacking it passes the original checker. Fixed here with required resource and omission regression. | Current validation improvement; no runtime blocker. |
| Checkpoint #37 never reached main | True for main, resolved in candidate. #37 `43d24a73d744516653d53d3bc8828787c499d299` is included in candidate with checkpoint reconciliation tests. Its merge commit brings the baseline into the feature branch; it does not mean main merged #37. | No current fix. |
| Zork branch lacks 0.26.1 guide reconciliation | Stale: current `4be05579bc623aa65bfe554a9ecd62dc4b90bd0e` merges 0.26.1 and includes eight guide resources, scene-recovery reference and three scene-methodology receipts. Candidate defers this stack. | Future integration inventory. |
| Older review27 reconciliation document/tests dropped | Unsupported: `0fcd399` is ancestor of main and candidate. Document blob retained; output CLI artifact round-trip coverage retained and extended to both skills. | No fix. |
| Skill exact lists / manifests can collide | Future integration risk confirmed; current candidate skill set equals required set exactly. Deferred block-orchestration, source-and-concepts and scene-recovery references require unioning during future integration. Additional #52 gap: source-and-concepts is exposed and tested but not check_dist-required. | Next-release gate hardening and integration checks. |
| Main still declares 0.26.1 | True, not a defect: separate candidate declares 0.27.0. | No fix. |
| Local checkout/archive/installation drift | Unverifiable from authorized cloud scope; no local-host access attempted. Not prerequisite for isolated qualification. | No local action. |

## Current CI evidence and limits

The candidate's complete PR ordinary run 41148114084 and native run 41148114073
passed. A separate push run 41148109625 failed while compiling a synthetic Rust
fixture with a 30-second timeout, before its assertion. The helper/test was
unchanged from base. This remains an unresolved stability caveat, not evidence
that every candidate run failed or that a product regression is established.

This review does not change CI optimization #58 at 737d9c1f932a6162ae565b48d19ab8a40ce27851
or sweding guidance #59 at 09ab554ce0d27a0e755707be2f2ed9951655de53.
Fresh artifact download 403 and cancellation authorization failures are outside
this work; neither operation was retried. No merge, tag, release, installation,
credential, or environment publication is authorized by these fixes.

Each draft fix records its authored red/green regression, focused/package checks,
exact head and remaining hosted/native qualification. Distinct dependency bases
are intentional; a fresh integration SHA still needs complete qualification.

## Fix map and fresh local evidence

| Draft | Base / final fix head | Local evidence |
| --- | --- | --- |
| [#61 DOS receipts](https://github.com/seeker-cyber-maker/fDisBull/pull/61) | #54 / `0dc3790f5f71ff5128c857e0c38b816657ec1d5e` | Authored red/green; focused 76 passed/4 skipped; installed-wheel regression passed; all package/skill gates passed. Broad run 2134 passed/120 skipped/32 environment-path failures; affected-file rerun outside injected Git ancestors 73 passed/1 skipped. Coordinator layout/CLI/distribution rerun 55 passed. |
| [#62 typed returns and events](https://github.com/seeker-cyber-maker/fDisBull/pull/62) | #42 / `eb8905b3214dae82d39e882a24011f81b79f421e` | Authored red 5 failed/15 passed; focused 55 passed/24 skipped; committed-head full 2236 passed/130 skipped; package/skill gates passed. Coordinator return/layer rerun 24 passed/4 compiler skips. |
| [#63 source-package collection and FD64](https://github.com/seeker-cyber-maker/fDisBull/pull/63) | #50 / `cb976470f73149342108f4125e70e0bb332d6a84` | Eight actual packaged collection errors and FD64 red reproduced; fixed full 2211 passed/159 skipped; actual ZIP/sdist collection and all package/skill gates passed. Exhaustive dice unchanged. |
| [#64 Ghidra resource](https://github.com/seeker-cyber-maker/fDisBull/pull/64) | #49 / `fcef2877320e0981d5b979ad9bba1e1d1dcbd488` | Source/wheel omission red/green; distribution 30 passed; all package/skill gates passed. |
| [#65 source guide resource](https://github.com/seeker-cyber-maker/fDisBull/pull/65) | #52 / `6fef4ec49acb3ab70bcc8bea85d62aa37897ecdb` | Source/wheel omission red/green; distribution 27 passed; all package/skill gates passed. |

The terminal omission regression failed before the checker change and passes
with the resource required. Focused distribution suite: 33 passed. Wheel,
sdist and tool ZIP were built and passed the resource/privacy checker.
Local compiler/backend absence remains explicitly skipped; it is not native
qualification. Hosted checks are tracked separately per immutable fix head.
