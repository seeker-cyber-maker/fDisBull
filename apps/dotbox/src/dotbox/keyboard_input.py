"""Bounded US-layout keyboard validation, extracted from fDisBull.

Provenance: fDisBull ce91c303f2fccd1db9b1e3917ecc8c98473bfdb9,
src/fdisbull/keyboard_input.py and debugger.py:bounded. This standalone
subset has no analysis, debugger or fDisBull runtime dependency.
"""


KEYS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-=[];',./\\`") | {
    "enter", "escape", "esc", "tab", "backspace", "space", "left", "right",
    "up", "down", "home", "end", "insert", "delete", "pageup", "pagedown",
    "shift", "ctrl", "alt", "kp5", *(f"f{i}" for i in range(1, 13)),
}


def validate_keyboard(*, key=None, text=None, modifiers=(), hold_ms=40, gap_ms=40):
    for name, value in (("hold_ms", hold_ms), ("gap_ms", gap_ms)):
        if type(value) is not int or not 1 <= value <= 1000:
            raise ValueError(f"{name} must be an integer in 1..1000")
    if text is not None:
        if not isinstance(text, str) or not 1 <= len(text) <= 64:
            raise ValueError("text requires 1..64 US-layout ASCII characters")
        if any(not (" " <= char <= "~" or char in "\r\n\t") for char in text):
            raise ValueError("text supports printable US-layout ASCII, Enter and Tab only")
        if key is not None or modifiers:
            raise ValueError("text cannot be combined with key or modifiers")
    else:
        if not isinstance(key, str) or key not in KEYS:
            raise ValueError("Unknown keyboard key; use lowercase physical key names")
        if not isinstance(modifiers, (list, tuple)) or any(
                m not in ("ctrl", "alt", "shift") for m in modifiers):
            raise ValueError("modifiers must be a list of ctrl, alt and/or shift")
        if len(set(modifiers)) != len(modifiers) or key in modifiers:
            raise ValueError("Duplicate keyboard key or modifier")
