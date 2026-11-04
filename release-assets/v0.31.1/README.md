# fDisBull v0.31.1 complete offline download

This is the public, unauthenticated download for the complete 0.31.1 Linux
x86-64 offline kit. No GitLab token or login is required.

## One file

- [fdisbull-0.31.1-offline-kit-20261104.zip](https://gitlab.com/api/v4/projects/88349936/packages/generic/fdisbull-release-packages/0.31.1-20261104/fdisbull-0.31.1-offline-kit-20261104.zip)
  — 276,034,060 bytes
- SHA-256: `d0a0ca6d2c580d37da1ef702fb6c5f915edee196e064519967953d517223e5c2`
- [ZIP checksum file](https://gitlab.com/api/v4/projects/88349936/packages/generic/fdisbull-release-packages/0.31.1-20261104/fdisbull-0.31.1-offline-kit-20261104.zip.sha256)

The ZIP contains the published 0.31.1 wheel, player wheel, sdist and tool ZIP;
the complete Linux x86-64 native offline kit; the reusable dependency bundle;
the source companion; licenses, evidence and checksums. It requires Python
3.13.5 on Linux x86-64.

```sh
curl -fL -o fdisbull-0.31.1-offline-kit-20261104.zip \
  https://gitlab.com/api/v4/projects/88349936/packages/generic/fdisbull-release-packages/0.31.1-20261104/fdisbull-0.31.1-offline-kit-20261104.zip
sha256sum fdisbull-0.31.1-offline-kit-20261104.zip
# expected: d0a0ca6d2c580d37da1ef702fb6c5f915edee196e064519967953d517223e5c2
unzip fdisbull-0.31.1-offline-kit-20261104.zip
```

## Individual package files

The same files are available individually from the
[package group](https://gitlab.com/brewster-jennings-group/fdisbull/-/packages/75295776)
or from the direct generic URLs recorded in
[the inventory](fdisbull-v0.31.1-release-inventory.json):

- `fdisbull-0.31.1-offline-kit-20261104.zip`
- `fdisbull-0.31.1-linux-x86_64-offline.tar.gz`
- `fdisbull-0.31.1-linux-x86_64-dependencies.tar.gz`
- `fdisbull-0.31.1-linux-x86_64-source-companion.tar`
- `fdisbull-0.31.1-py3-none-any.whl`
- `fdisbull_player-0.31.1-py3-none-any.whl`
- `fdisbull-0.31.1.tar.gz`
- `fdisbull-0.31.1-tool.zip`
- `PACKAGE-SHA256SUMS`
- `BUILD.json`

All direct URLs use this form:

```text
https://gitlab.com/api/v4/projects/88349936/packages/generic/fdisbull-release-packages/0.31.1-20261104/<filename>
```

## Identity

- Release tag: `v0.31.1`, commit `e94bae0fca9d6ffc090991e8daad04772a5ff32c`
- Published app artifacts: 0.31.1 at `27b388d38cc14f04842a81b8ec1a113460900f53`
- Native backend: DOSBox-X baseline `029bd65c…` with the v0.31.1 layers patch
  `bce55cff…`; it passed 2,544 native tests in local Linux qualification.
- Dependency bundle: reused 0.29.0 bundle because the 0.31.1 constraints
  fingerprint is identical (`ea2a9ca4…`).

The complete kit is self-contained for Linux x86-64/Python 3.13.5. It contains
no game files, saves, project databases or private target data.
