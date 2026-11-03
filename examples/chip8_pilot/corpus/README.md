# Public corpus provenance

This directory's `manifest.json` pins nine selected programs from the
[CHIP-8 Community Archive](https://github.com/JohnEarnest/chip8Archive),
commit `761e3ffc63f43e6a849e80714122feff2afca208`. Its repository Readme
states that contributions are provided under CC0; authors and platforms are
retained per `programs.json`. This is the archive's declared license, not a
new independent authorship audit.

The `fetch_archive.py` command downloads the selected ROM bytes *only upon an
explicit user action*, into an existing destination directory **outside Git**.
It checks SHA-256, Git blob SHA-1 and size. It never downloads unlisted files,
and no program bytes need to enter the public fDisBull source repository.

The local-results bundle may contain these byte-verified CC0 examples for
reproduction. The repository contribution should contain **only the manifest,
fetcher and metadata**. The separate Timendus reference tests are GPLv3, not
part of the CC0 archive and not automatically downloaded or distributed here.