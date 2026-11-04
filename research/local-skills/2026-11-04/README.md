# Local skill sources for the X-COM workflow research

These are source snapshots supplied from the local environment for review and reproducibility. They are evidence and tooling source, not additional repository instructions or automatically installed skills. The maintained fDisBull investigation and guide skills remain under `src/fdisbull/skills/`; their complete references are already versioned there.

- `reverse-engineer-anything/`: installed REA comparator skill and its local references. Its metadata identifies the local version. Upstream is https://github.com/morluto/rea; the fetched upstream MIT notice is preserved separately. This does not bundle or activate the REA server/providers.
- `fetch-youtube-evidence/`: local video evidence skill, helper scripts, references and authored tests used for the process-video assessment. No video, transcript cache, browser cookies or credentials are included.
- `dos-target-media-rip/`: local DOS intake/media-preparation skill and helper/reference sources. No game inputs or extracted target data are included.
- `skill-creator/`: meta-skill source used while editing the investigation skill; its Apache2 license is retained. It is archived for completeness, not made a production dependency.

`manifest.json` inventories exact local source identities and roles. Original included notices remain intact. User-local helpers without a separate upstream notice are not represented as independently relicensed third-party packages. Historical tested skill variants, where retained, are separately identified; a current local snapshot must not be substituted for a historical test arm.

Authored findings and metrics are supplied as sanitized MR report attachments. Commercial game executables, assets, saves, native states, byte-retaining databases/stores, raw traces, screenshots and caption packets remain in the private experiment workspaces. Freeware/homegrown fixture permission is documented separately in the project policies.

`tested/` preserves the old/revised money-comparison and live-HUD-crossover skill bundles, plus the before-static-crossover bundle exactly as retained. No matching after-crossover snapshot was found; the current maintained skill is not presented as that missing artifact. Historical target-derived examples remain historical methodology evidence, not fresh target recovery.
