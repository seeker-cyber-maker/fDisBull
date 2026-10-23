# Reconstructed release history

Each import comes from a saved `fDisBull-VERSION.zip`. Commits were created during repository preparation; their timestamps are not backdated to imitate original development.

Available snapshots: 0.1.0, 0.2.0, 0.3.0, 0.4.0, 0.5.0, 0.8.0, 0.8.1, and 0.8.2. No exact 0.6.0/0.7.0 source snapshots were available, so no commits or tags were fabricated for them.

`releases.json` records source archive hashes and reconstructed local commit IDs. Each imported version's `history/snapshot.json` records members and normalization. If a hosting API recreates commits, their tree content and order remain authoritative while commit IDs may differ.

Tool source/tests are retained byte-for-byte. Publication normalization relocates DinoPark layouts, notes and selected images; excludes original binaries, resource/save files, byte-retaining databases, wheels and generated reports; and removes private sample-sharing URLs from documentation. A final packaging/documentation commit makes this separation explicit for current users.

The unfinished DOSBox work is preserved on a separate experimental branch with its upstream baseline and GPL license, outside every completed fDisBull release.
