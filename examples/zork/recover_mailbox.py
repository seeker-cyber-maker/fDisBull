"""Source-checkout entry point for the packaged, qualified recovery profile."""
from fdisbull.zork_recovery import recover_mailbox, state_from_ram

__all__ = ["recover_mailbox", "state_from_ram"]
