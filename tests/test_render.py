"""Public export behavior: real image bytes, safe markup, explicit bounds."""
import xml.etree.ElementTree as ET

from PIL import Image
import pytest

from fdisbull.render import render_snapshot


def snapshot():
    return {
        "title": "fixture.bin", "arch": "x86", "bits": 64,
        "version": 2, "sha256": "a" * 64,
        "instructions": [{
            "address": "0x140001000", "bytes": "4889e5", "mnemonic": "mov",
            "operands": "rbp, rsp", "name": "entry", "comment": "stack frame",
            "xrefs": [{"kind": "call", "source": "0x140000100", "target": "0x140001000"}],
        }],
    }


def test_png_is_a_complete_readable_image_with_reported_dimensions(tmp_path):
    result = render_snapshot(snapshot(), tmp_path / "nested" / "listing.png")
    with Image.open(result["path"]) as image:
        image.load()
        assert image.format == "PNG"
        assert image.size == (result["width"], result["height"])
        assert image.width >= 1000 and image.height >= 200
        assert image.getbbox() == (0, 0, image.width, image.height)
        assert len(image.getcolors(image.width * image.height)) > 3


def test_svg_treats_hostile_names_and_comments_as_text(tmp_path):
    view = snapshot()
    view["title"] = 'binary <script>alert("title")</script> & source'
    view["instructions"][0]["name"] = '<script>alert("name")</script>'
    view["instructions"][0]["comment"] = '</text><image href="https://invalid/"/> & annotation'
    result = render_snapshot(view, tmp_path / "listing.svg")
    tree = ET.parse(result["path"])
    root = tree.getroot()
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    assert not root.findall(".//{http://www.w3.org/2000/svg}script")
    assert not root.findall(".//{http://www.w3.org/2000/svg}image")
    text = " ".join(root.itertext())
    assert view["instructions"][0]["name"] in text
    assert view["instructions"][0]["comment"] in text
    assert "VERSION 2" in text
    assert "a" * 64 in text


def test_unsupported_format_fails_without_writing_a_disguised_file(tmp_path):
    destination = tmp_path / "listing.html"
    with pytest.raises(ValueError, match="format must be png or svg"):
        render_snapshot(snapshot(), destination)
    assert not destination.exists()


def test_oversized_snapshot_fails_without_silently_dropping_rows(tmp_path):
    view = snapshot()
    view["instructions"] *= 201
    destination = tmp_path / "oversized.png"
    with pytest.raises(ValueError, match="at most 200"):
        render_snapshot(view, destination)
    assert not destination.exists()


def test_control_characters_cannot_corrupt_svg_or_reverse_its_text(tmp_path):
    view = snapshot()
    view["instructions"][0]["comment"] = "safe\x00\x1b\u202eevil\nnext"
    result = render_snapshot(view, tmp_path / "listing.svg")
    tree = ET.parse(result["path"])
    text = " ".join(tree.getroot().itertext())
    assert "safeevil next" in text
    assert "\x00" not in text and "\x1b" not in text and "\u202e" not in text
