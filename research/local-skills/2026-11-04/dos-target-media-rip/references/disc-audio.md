# Disc and CD-audio handling

Read the CUE/descriptor and sector headers, not just the filename extension.
Record track types, sector size, indexes, pregaps, source hashes, and all track
start positions. A `.GOG` file can be raw MODE1/2352 rather than a cooked ISO.

## Data track

Inventory the ISO9660 volume through its sector payloads without making a large
temporary raw copy. Compare dual-endian fields, bound extents to the volume, and
reject unsupported multi-extent or special layouts. The bundled
`scripts/disc_data_track.py` supports the ordinary layouts it explicitly validates.
It converts declared data sectors into ISO/2048 and reparses the result, comparing
every file's size and SHA-256. Tail sectors are reported, not assumed to be audio.

Keep executable files byte-identical, including any overlays or code appended
past the initial DOS load module. Selecting only a data track omits separate
audio tracks; report that separately from any movie or filesystem savings.

## Full compressed audio

Prefer a full compressed working track when future native/dot-mode sound matters.
One shared MP3 at approximately 160 kb/s was useful in the existing Lost in Time
package; bitrate/format can differ when quality or backend support warrants it.
An MP3 is a lossy derivative, not a lossless preservation copy.

Establish the original PCM byte order, sample rate and channels before encoding.
Decode the resulting file completely and compare sample count/duration with the
source, accounting for codec delay/padding. Keep source audio in the untouched
archive or one preserved lossless carrier. Prefer relative symlinks to the one
compressed working track instead of copying it into several game folders.

Validate the chosen virtual-CD backend's support for compressed audio. Record
mounting/TOC, audible playback, game-driven seeks, and synchronization as separate
checks. Headless dummy-audio success does not establish audible sound.

A smaller data image can change the absolute start of following audio tracks.
Preserve original TOC/track positions and pregaps in a combined layout and test
seeks. Do not silently rebase track starts or remove required blank sectors.

## Bounded browser downloads

For an owned installer delivered through an authenticated browser, arrange the
documented download event listener before clicking its real backup-installer
link. Retain the returned saved path and verify the complete installer before
extraction. A timeout or temporary filename is not a completed download. Inspect
the outcome before retrying; do not work around browser-policy refusals or solve
them by reading hidden browser state. Source archives are extracted, not run,
when ordinary archive tools can recover the game files.

Large downloads can exceed a browser-control cell's lifetime. Allow an appropriate
bounded call duration and inspect the completed named file after a timeout before
clicking again. A lost browser callback does not mean a transfer failed. Validate
the complete installer and its hash; never treat a `.crdownload` as saved input.
