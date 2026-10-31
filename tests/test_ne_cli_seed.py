"""The documented NE logical seed form works through the fresh CLI process."""

from test_le_workflow import command
from test_ne_loader import ne_file


def test_cli_analyze_accepts_documented_ne_logical_seed(tmp_path):
    source = tmp_path / "authored.exe"
    source.write_bytes(ne_file())
    path = tmp_path / "seed.fdb"
    command("import", source, path, "--image", "ne")
    result = command("analyze", path, "--start", "ne:1:0", "--max-instructions", "100")
    assert result["decoded"] >= 1
