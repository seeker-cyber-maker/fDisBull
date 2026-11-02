"""Public names for full native saved states; existing formats stay unchanged."""


class AnchorStoneSessionMixin:
    def save_anchor_stone(self, name='anchor-stone.sav', *, max_bytes=None):
        """Save a full native Anchor Stone through the selected backend."""
        options = {'name': name}
        if max_bytes is not None:
            options['max_bytes'] = max_bytes
        return self.save_state(**options)

    def load_anchor_stone(self, artifact):
        """Jump directly to an Anchor Stone using the guarded native restore."""
        return self.load_state(artifact)
