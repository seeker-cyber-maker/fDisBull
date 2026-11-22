# DotBox 0.1.0.dev10 development package

This release candidate prepares the current shared-source DotBox for delivery
to Dot on Linux x86_64. The new development version distinguishes this package
from earlier standalone `0.1.0.dev9` wheels. It is not a stable `0.1.0` release.

## Package changes

- Set the distribution and runtime version to `0.1.0.dev10`.
- Correct standalone installation instructions to the actual
  `fdisbull-core==0.1.0.dev7` dependency and an offline wheelhouse installation.
- Retain the shared-core version and bind its exact wheel hash in the release
  inventory, avoiding an unrelated cross-product version change.
- Document DOSBox-X as the base runtime and an optional AGI CPU analysis
  companion as a separate tool, without changing `dotbox serve`.
- Add an offline bundle builder, a fresh-prefix installer, verified payload
  inventories and launchers for the retained native loader/library closure.

This metadata change does not modify game execution, native patches, input
ownership, resource decoders or the scene/harness APIs. The package carries the
existing incremental learning kit and shared memory-search/transport machinery.

## Delivery contents and requirements

The offline delivery should include the DotBox and matching shared-core wheels,
their required Python dependency wheels, the compatible DotBox DOSBox-X runtime
and required platform libraries, startup instructions, an integrity inventory,
and the corresponding native source and notices. Keep original game files,
saves, credentials and private runtime evidence outside the tool package.

The source package requires Python 3.12 or later. This offline binary bundle
targets **CPython 3.12 on Linux x86_64**. Runtime dependencies remain
`Pillow>=10,<13`, `iced-x86==1.22.0` and `fdisbull-core==0.1.0.dev7`.
The ownership connector is optional and is not needed for the base offline kit.
The final delivery receipt must name the interpreter, platform, source commit,
wheel hashes, native inputs and binary actually tested.

## Qualification boundaries

A fresh installation must succeed using only the delivered wheelhouse, outside
the source checkout, with no full fDisBull application or source-path injection.
The installed `dotbox doctor` checks offline resource and tool readiness; native
execution requires the separately identified executable and native checks.
Retain the exact native recipe/input identities when reusing an existing binary.
This Python/documentation change does not itself require a native rebuild.

Visible play, supported desktop takeover and audio on Dot's actual computer
remain separate acceptance checks. The AGI companion, when supplied, retains its
own source and qualification limits; its presence does not integrate an AGI
backend into `dotbox serve`. Packaging and local verification do not by
themselves establish a public release upload, a stable tag or hosted CI.
