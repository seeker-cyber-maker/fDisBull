"""Bounded IBM PC controller input; text assumes an unmodified US layout."""
from .debugger import bounded

KEYS = frozenset('abcdefghijklmnopqrstuvwxyz0123456789-=[];\',./\\`') | {
    'enter','escape','esc','tab','backspace','space','left','right','up','down',
    'home','end','insert','delete','pageup','pagedown','shift','ctrl','alt',
    *(f'f{i}' for i in range(1,13))}


def validate_keyboard(*, key=None, text=None, modifiers=(), hold_ms=40, gap_ms=40):
    bounded(hold_ms,'hold_ms',1,1000); bounded(gap_ms,'gap_ms',1,1000)
    if text is not None:
        if not isinstance(text,str) or not 1 <= len(text) <= 64:
            raise ValueError('text requires 1..64 US-layout ASCII characters')
        if any(not (' ' <= char <= '~' or char in '\r\n\t') for char in text):
            raise ValueError('text supports printable US-layout ASCII, Enter and Tab only')
        if key is not None or modifiers:
            raise ValueError('text cannot be combined with key or modifiers')
    else:
        if not isinstance(key,str) or key not in KEYS:
            raise ValueError('Unknown keyboard key; use lowercase physical key names')
        if not isinstance(modifiers,(list,tuple)) or any(m not in ('ctrl','alt','shift') for m in modifiers):
            raise ValueError('modifiers must be a list of ctrl, alt and/or shift')
        if len(set(modifiers))!=len(modifiers) or key in modifiers:
            raise ValueError('Duplicate keyboard key or modifier')


class GuestKeyboard:
    """Namespace shared by Python clients: session.keyboard.press/type/state."""
    def __init__(self, session):
        self.session=session

    def press(self, key, *, modifiers=(), hold_ms=40, gap_ms=40):
        return self.session.keyboard_press(key,modifiers=modifiers,hold_ms=hold_ms,gap_ms=gap_ms)

    def type(self, text, *, hold_ms=40, gap_ms=40):
        return self.session.keyboard_type(text,hold_ms=hold_ms,gap_ms=gap_ms)

    def state(self):
        return self.session.keyboard_state()
