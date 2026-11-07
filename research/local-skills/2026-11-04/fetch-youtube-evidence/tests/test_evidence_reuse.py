from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import fetch_youtube_batch_evidence as batch  # noqa: E402
import fetch_youtube_catalog_metadata as catalog  # noqa: E402
import fetch_youtube_evidence as evidence  # noqa: E402
import import_browser_transcript as browser_import  # noqa: E402


class EvidenceReuseTests(unittest.TestCase):
    def make_partial_packet(self, root: Path) -> Path:
        video_id = "abcdefghijk"
        names = [
            f"{video_id}.metadata.json",
            f"{video_id}.en.json3",
            f"{video_id}.en.transcript.json",
            f"{video_id}.en.transcript.txt",
        ]
        artifacts = []
        for index, name in enumerate(names):
            path = root / name
            path.write_text(f"artifact-{index}\n", encoding="utf-8")
            artifacts.append(
                {
                    "path": name,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
        manifest = {
            "schema": "youtube-evidence/2",
            "source_url": f"https://www.youtube.com/watch?v={video_id}",
            "video_id": video_id,
            "selected_caption": {"language": "en", "kind": "automatic"},
            "transcript_integrity": {
                "complete_timing_coverage": False,
                "end_gap_seconds": 125.12,
            },
            "warnings": ["partial"],
            "artifacts": artifacts,
        }
        manifest_path = root / f"{video_id}.evidence.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return manifest_path

    def test_hash_valid_partial_packet_is_reusable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected = self.make_partial_packet(root)
            actual = evidence.verified_existing_packet(root, "abcdefghijk", True)
            self.assertEqual(actual, expected)

    def test_partial_packet_status_remains_explicit(self) -> None:
        manifest = {
            "selected_caption": {"language": "en"},
            "transcript_integrity": {"complete_timing_coverage": False},
        }
        self.assertEqual(evidence.manifest_evidence_status(manifest), "partial_transcript")

    def test_tampered_partial_packet_is_not_reused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_partial_packet(root)
            (root / "abcdefghijk.en.transcript.txt").write_text("tampered\n", encoding="utf-8")
            self.assertIsNone(evidence.verified_existing_packet(root, "abcdefghijk", True))

    def test_hash_valid_negative_caption_result_is_reusable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video_id = "abcdefghijk"
            metadata_path = root / f"{video_id}.metadata.json"
            metadata_path.write_text("{}\n", encoding="utf-8")
            manifest = {
                "schema": "youtube-evidence/2",
                "source_url": f"https://www.youtube.com/watch?v={video_id}",
                "video_id": video_id,
                "selected_caption": None,
                "caption_acquisition_requested": True,
                "transcript_integrity": None,
                "evidence_status": "metadata_without_usable_transcript",
                "artifacts": [
                    {
                        "path": metadata_path.name,
                        "sha256": hashlib.sha256(metadata_path.read_bytes()).hexdigest(),
                    }
                ],
            }
            manifest_path = root / f"{video_id}.evidence.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertEqual(
                evidence.verified_existing_packet(root, video_id, True), manifest_path
            )

    def test_batch_selection_is_case_insensitive_and_bounded(self) -> None:
        catalog = {
            "records": [
                {"video_id": "abcdefghij1", "title": "Vibe Coding - Day 1"},
                {"video_id": "abcdefghij2", "title": "Other video"},
                {"video_id": "abcdefghij3", "title": "VIBE CODING - Day 2"},
            ]
        }
        selected, total = batch.select_records(catalog, r"vibe coding", 1)
        self.assertEqual(total, 2)
        self.assertEqual([row["video_id"] for row in selected], ["abcdefghij1"])

    def test_batch_selection_can_order_and_preserve_duplicate_days(self) -> None:
        catalog = {
            "records": [
                {"video_id": "abcdefghij1", "title": "Series Day 10"},
                {"video_id": "abcdefghij2", "title": "Series Day 2"},
                {"video_id": "abcdefghij3", "title": "Series Day 2 - recap"},
            ]
        }
        selected, total = batch.select_records(
            catalog, r"series", 10, r"Day +([0-9]+(?:[.][0-9]+)?)"
        )
        self.assertEqual(total, 3)
        self.assertEqual(
            [row["series_ordinal"] for row in selected], [2.0, 2.0, 10.0]
        )

    def test_batch_cache_revalidates_manifest_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            packet = root / "videos" / "abcdefghijk"
            packet.mkdir(parents=True)
            artifact = packet / "abcdefghijk.metadata.json"
            artifact.write_text("{}\n", encoding="utf-8")
            manifest = packet / "abcdefghijk.evidence.json"
            manifest.write_text(
                json.dumps(
                    {
                        "artifacts": [
                            {
                                "path": artifact.name,
                                "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            record = {
                "manifest": str(manifest.relative_to(root)),
                "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
            }
            self.assertTrue(batch.cached_record_valid(record, root))
            artifact.write_text("tampered\n", encoding="utf-8")
            self.assertFalse(batch.cached_record_valid(record, root))

    def test_search_supplement_is_channel_scoped_and_deduplicated(self) -> None:
        rows = [{"video_id": "abcdefghij1", "title": "Current"}]
        supplemental = [
            {"video_id": "abcdefghij1", "title": "Duplicate", "channel_id": "wanted"},
            {"video_id": "abcdefghij2", "title": "Recovered", "channel_id": "wanted"},
            {"video_id": "abcdefghij3", "title": "Other channel", "channel_id": "other"},
        ]
        merged, added = catalog.merge_search_rows(rows, supplemental, "wanted")
        self.assertEqual(added, 1)
        self.assertEqual([row["video_id"] for row in merged], ["abcdefghij1", "abcdefghij2"])

    def test_browser_export_builds_reusable_complete_packet(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            exported = root / "browser.txt"
            exported.write_text(
                "YouTube transcript\n"
                "Video ID: abcdefghijk\n"
                "Language: en\n"
                "Captions: auto-generated\n\n"
                "[0:00] First cue\n"
                "[1:59] Final cue\n",
                encoding="utf-8",
            )
            packet = root / "packet"
            manifest_path = browser_import.build_packet(
                exported,
                "https://www.youtube.com/watch?v=abcdefghijk",
                packet,
                120.0,
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["evidence_status"], "complete_transcript")
            self.assertTrue(manifest["transcript_complete"])
            self.assertEqual(manifest["selected_caption"]["kind"], "automatic")
            collection = json.loads((packet / "collection.json").read_text(encoding="utf-8"))
            self.assertEqual(collection["schema"], "youtube-evidence-collection/1")
            self.assertEqual(collection["records"][0]["status"], "complete_transcript")
            self.assertEqual(
                collection["records"][0]["manifest_sha256"],
                hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            )
            self.assertEqual(
                evidence.verified_existing_packet(packet, "abcdefghijk", True),
                manifest_path,
            )

    def test_browser_export_without_duration_remains_partial(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            exported = root / "browser.txt"
            exported.write_text(
                "YouTube transcript\n"
                "Video ID: abcdefghijk\n"
                "Language: en\n"
                "Captions: manual\n\n"
                "[0:00] One cue\n",
                encoding="utf-8",
            )
            manifest_path = browser_import.build_packet(
                exported, "abcdefghijk", root / "packet", None
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["evidence_status"], "partial_transcript")
            self.assertFalse(manifest["transcript_complete"])

    def test_browser_export_rejects_mismatched_video_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            exported = root / "browser.txt"
            exported.write_text(
                "YouTube transcript\n"
                "Video ID: abcdefghijk\n"
                "Language: en\n"
                "Captions: auto-generated\n\n"
                "[0:00] One cue\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "video IDs do not match"):
                browser_import.build_packet(
                    exported, "https://youtu.be/zyxwvutsrqp", root / "packet", 1.0
                )


if __name__ == "__main__":
    unittest.main()
