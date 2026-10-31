"""Use additive sources alongside the supplied installed fDisBull wheel."""
from pathlib import Path
import fdisbull
local = str(Path(__file__).resolve().parents[2] / 'src' / 'fdisbull')
if local not in fdisbull.__path__:
    fdisbull.__path__.insert(0, local)
