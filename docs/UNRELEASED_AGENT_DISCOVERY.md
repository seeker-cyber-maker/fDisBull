# Unreleased agent discovery follow-up

This local follow-up is separate from the frozen 0.23.0 release commit.
It adds `agent-skill --index` and JSON `{ "index": true }` for a compact guide
chooser. Each entry names a bundled reference and its purpose; no guide text,
project access or backend is needed. Default full export and selective
`--reference` retrieval retain their existing behavior.

The response identifies its schema as `fdisbull-skill-index-1`. Discover the
feature by requesting it; the base checkout's package version is not an index
capability claim.

The option is mutually exclusive with `--reference`. Invalid flag types and
unknown fields are refused. Tests check that every indexed guide is retrievable,
that the reply is substantially smaller than the complete skill, and that
CLI/JSON requests agree without opening a project.

The index is not included in v0.23.0 and has not been pushed or published.
