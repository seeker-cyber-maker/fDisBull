# Local UDC registry planning study

This authored example connects **find existing representations → identify a
missing association → register it → find the plan after reopening the database**.
It reuses the current fDisBull semantic catalog and module/provider validators.
It adds a private SQLite index and deterministic guidance, without changing an
existing UIL format or installing an executable provider.

Status: experimental, local, declarative planning. Every response has
`execution_authorized: false`. The example does not claim compiler output,
native execution, verified submitted evidence, or permission to redistribute
the indexed documents.

## Run

From a source checkout with fDisBull's ordinary dependencies installed:

```sh
PYTHONPATH=src python examples/udc_registry/demo.py
PYTHONPATH=src python -m pytest -q examples/udc_registry/test_registry.py
```

The demo uses a temporary private database, closes it, reopens it, prints the
results, and removes the temporary directory. To retain the database, pass a
new path outside Git:

```sh
PYTHONPATH=src python examples/udc_registry/demo.py --database /private/work/registry.sqlite
```

The directory must already exist. The example refuses an existing destination
on create and a destination under an observed Git checkout. It stores no raw
game files, invokes no compiler, downloads nothing, and loads no submitted code.
Its only source fixtures are the authored arithmetic statements in `demo.py`.

## What the demonstration actually does

1. The existing `uil_catalog.build_catalog` imports an authored C increment and
   an explicitly masked Python increment. The exact normalized models share
   one `semantic:` identity and retain two `implementation:` identities.
2. The index admits that existing validated catalog. There are no representation
   sidecar records, so a query with an explicit full typed domain returns
   `assess-bind-existing` and exposes both known source/model descriptors.
   An absent association does not mean that the implementation is missing.
3. The author-supplied module/provider and C representation declaration are
   registered. This is structural intake; no agent was asked to generate code.
4. After the database is reopened, the same query finds the source-present
   declaration and returns `build`, while retaining the other unbound descriptor.
5. The author explicitly requests an additional implementation experiment.
   `generate_swede_task` creates a contract-bound task packet with the declared
   reason, candidate exclusions and both known alternatives. It does not claim
   the existing implementations were proved incompatible or absent.

The generic example provider is **not a newly installed native backend**. A
build plan must still pass the real backend's admission. The production native
builder deliberately admits only its reconstructed built-in provider IDs.
The example's `backend: available` value is a submitted assertion, not an
environment probe or proof that this generic provider can be emitted.

## Existing identities remain authoritative

The index stores unmodified `fdisbull-uil-catalog-1` documents and existing
`fdisbull-udc-link-module-1` / `fdisbull-udc-link-provider-1` documents.
`validate_catalog` and `describe_components` perform their existing checks.
Query resolution calls `resolve_modules` and retains its exact pinning,
dependency, target, ABI, profile, ownership, version, ambiguity and cycle rules.

An `implementation:` identity describes an admitted source/model representation.
It is not a compiled object identity. A representation study record separately
references that implementation, an owning module, an associated provider, a
target, and optionally an artifact digest. The module/provider relationship is
explicitly a **submitted declaration**; this example does not prove that the
module realizes the complete model merely because it supplies matching typed
intrinsics. Artifact hashes likewise identify claimed artifacts without opening
or executing them.

Sidecar identities use `catalog-study:` and `representation-study:` prefixes.
Existing strict catalog, orchestration and link schemas gain no extra fields.
Record changes produce new identities; older records remain visible. Imports
are idempotent and writes are transactional. Each query runs within one SQLite
read transaction and returns exact query and snapshot digests. Ordering is
deterministic for that captured view. Reads revalidate catalog/component
identities and sidecar document digests.

## Agent guidance

| Observed planning condition | Next action |
| --- | --- |
| Contract is absent from admitted catalogs | `recover-contract` |
| Query did not declare its domain | `declare-domain` |
| Known source/model descriptors have no sidecar association | `assess-bind-existing` |
| A recorded realization targets another architecture | `assess-target` |
| Module association cannot resolve with exact existing contracts | `repair-module-plan` |
| Requested domain differs from the recorded declaration | `qualify-domain` |
| Backend availability is unknown or declared unavailable | `prepare-backend` |
| Only a metadata record is available | `locate-source` |
| Source is declared present but no artifact is declared | `build` |
| Artifact is declared present without evidence references | `qualify` |
| Artifact and evidence references were supplied | `review-evidence` |

For multiple records, these are deterministic next-work priorities, **not a
performance ranking or equivalence confidence score**. Results retain each
record's reasons and every known matching catalog implementation, including
unbound ones. The query does not silently choose an executable, infer that
source cannot be recompiled for another target, or evaluate benchmark claims.
A complete application should supply its own explicitly declared selection
policy after qualification.

The prototype never treats its incomplete index as proof of global absence.
Sweding is an explicit `generate_swede_task` operation requiring a known
validated contract, a domain, a reason and a list of candidate exclusions.
Exclusions are caller declarations and reference exact known candidates; they
do not hide those candidates or prove incompatibility. An empty exclusion list
is permitted when the author deliberately requests another backing while
retaining all alternatives. The task and query both retain
`absence_established: false`. The complete production workflow must assess
compiler recipes and target portability before concluding that new code is
needed.

Domain matching here is exact declaration equality. A free-text restricted
domain is not evaluated, and no subset/implication inference is made. All
qualification references retain `evidence_status: unverified-references`.
A caller cannot add `qualified: true` or `passed: true` and acquire authority;
the strict study schema rejects those fields. Receipt ingestion and verification
belong to a later integration with the existing qualification machinery.

## Local intake and distribution boundary

Catalogs are admitted locally through the real validator. Components are
admitted locally through the real component-description API. A representation
must refer to existing exact IDs and passes strict sidecar validation before it
is registered. This implements structural local intake only.

`distribution` accepts `local-only` or `authored-review-requested`. The latter is
a request for review, not approval or an assertion of ownership. There is no
publication, network synchronization or export command. A stored UIL model,
text constant, resource association or provenance annotation can itself require
private handling even when it contains no original executable bytes. Keep the
database outside Git and distribution packages.

The production contribution workflow must independently establish which
individual files, metadata, evidence and dependency closures may be shared.
Purchasing a game, supplying a purchase receipt, successful semantic testing,
or assigning a digest does not establish redistribution permission in this
study. The index neither checks purchases nor asks agents to manufacture a
rights declaration.

## Deliberate limits

- Supported target vocabulary is inherited from the existing native link API:
  Linux x64, Windows x64 and macOS arm64. This is not a universal target registry.
- The index is bounded to 512 stored documents and 1 MiB per document; these
  study limits are additional to existing core validation limits.
- No cross-profile conversion, algebraic equivalence discovery, swede generation,
  remote catalog federation, compiler execution, timing comparison, contributor
  authentication, license adjudication, or publishable bundle construction is
  implemented.
- Source/availability claims and provider associations are declarations. Native
  execution readiness requires the actual supported backend and its gates.
- This study adds no production CLI command, plugin loader, database migration,
  installed skill or API method. Its Python API and `demo.py` are the entry points.

The tests exercise actual core validators, persistence/reopen, deterministic
ordering, duplicate intake, immutable revisions, missing/invalid identities,
target and ABI mismatch, provider ambiguity/cycles, tamper detection, private
destination checks, and the distinction between evidence references and
authority. They also check that a missing join never hides known implementations,
that a different target prompts portability assessment, and that explicit swede
tasks retain known alternatives without inventing an absence proof.
