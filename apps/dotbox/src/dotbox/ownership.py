"""Receiver-owned evidence deadlines and leases for cooperating desktop callers.

This state never transfers native input or authenticates a publisher. Its caller
must authenticate, bind the selected viewer, and serialize all access. ``fresh``
means a current observation exists; an unknown owner/connection still denies a
turn. No state or token is restored across receiver restarts.
"""

import math
import re
import secrets
import time


class OwnershipState:
    EVENT_FIELDS = {"stream_id", "challenge", "sequence", "owner", "viewer_mode", "connection"}
    LEASE_FIELDS = {"viewer_id", "stream_id", "epoch", "sequence", "controller_id",
                    "lease_id", "expires_in_ms"}

    def __init__(self, viewer_id, *, clock=time.monotonic, ttl=3.0):
        if not isinstance(viewer_id, str) or re.fullmatch(r"[0-9a-f]{64}", viewer_id) is None:
            raise ValueError("viewer_id must be an exact lowercase SHA-256 binding")
        try:
            valid_ttl = type(ttl) in (int, float) and math.isfinite(ttl) and ttl > 0
        except OverflowError:
            valid_ttl = False
        if not valid_ttl:
            raise ValueError("ttl must be a positive finite receiver duration")
        if not callable(clock):
            raise ValueError("clock must be callable")
        self.viewer_id, self._clock, self._ttl = viewer_id, clock, float(ttl)
        self._stream = None
        self._sequence = self._epoch = 0
        self._owner = self._mode = self._connection = "unknown"
        self._deadline = self._challenge = self._lease = None

    def _now(self):
        now = self._clock()
        if type(now) not in (int, float) or not math.isfinite(now):
            raise ValueError("Receiver clock must return finite monotonic time")
        return now

    @staticmethod
    def _remaining(deadline, now):
        remaining = max(0, deadline - now) if deadline is not None else 0
        return int(remaining) * 1000 + int((remaining % 1) * 1000)

    def _invalidate(self):
        self._epoch += 1
        self._owner = self._mode = self._connection = "unknown"
        self._deadline = self._lease = None

    def _expire(self, now):
        if self._deadline is not None and now >= self._deadline:
            self._invalidate()
        elif self._lease is not None and now >= self._lease["deadline"]:
            self._epoch += 1
            self._lease = None
        if self._challenge is not None and now >= self._challenge["deadline"]:
            self._challenge = None

    def _require_stream(self, stream_id):
        if not isinstance(stream_id, str) or self._stream is None or stream_id != self._stream:
            raise ValueError("Unknown or replaced publisher stream")

    def _status(self, now):
        return {"owner": self._owner,
                "source": "codex-viewer-ui" if self._stream is not None else "unavailable",
                "viewer_id": self.viewer_id, "epoch": self._epoch,
                "stream_id": self._stream, "sequence": self._sequence,
                "fresh": self._deadline is not None and now < self._deadline,
                "expires_in_ms": self._remaining(self._deadline, now),
                "viewer_mode": self._mode, "connection": self._connection}

    def status(self):
        now = self._now()
        self._expire(now)
        return self._status(now)

    def open(self, viewer_id):
        if viewer_id != self.viewer_id:
            raise ValueError("Publisher does not match the selected viewer")
        self._invalidate()
        self._stream = secrets.token_hex(32)
        self._sequence = 0
        self._challenge = None
        return self.status()

    def challenge(self, stream_id):
        now = self._now()
        self._expire(now)
        self._require_stream(stream_id)
        deadline = now + self._ttl
        if not math.isfinite(deadline):
            raise ValueError("Observation deadline is outside the receiver clock range")
        self._challenge = {"token": secrets.token_hex(32), "deadline": deadline,
                           "sequence": self._sequence + 1}
        return {"stream_id": self._stream, "challenge": self._challenge["token"],
                "sequence": self._challenge["sequence"],
                "expires_in_ms": self._remaining(deadline, now)}

    def invalidate(self, stream_id):
        """An authenticated publisher reports EOF/error without preserving a grant."""
        self._require_stream(stream_id)
        self._invalidate()
        self._challenge = None
        return self.status()

    def observe(self, params):
        if not isinstance(params, dict) or set(params) != self.EVENT_FIELDS:
            raise ValueError("Observation requires exactly the documented event fields")
        if (type(params["sequence"]) is not int or params["sequence"] < 1
                or not isinstance(params["challenge"], str)
                or re.fullmatch(r"[0-9a-f]{64}", params["challenge"]) is None
                or params["owner"] not in ("human", "dot", "unknown")
                or params["viewer_mode"] not in ("observe", "control", "unknown")
                or params["connection"] not in ("live", "unknown", "disconnected")):
            raise ValueError("Invalid ownership observation fields")
        now = self._now()
        self._expire(now)
        self._require_stream(params["stream_id"])
        pending = self._challenge
        if (pending is None or params["sequence"] != pending["sequence"]
                or not secrets.compare_digest(params["challenge"], pending["token"])):
            raise ValueError("Expired, replaced or replayed observation challenge")
        self._challenge = None
        self._sequence = params["sequence"]
        owner, mode, connection = (params[k] for k in ("owner", "viewer_mode", "connection"))
        if (owner == "dot" and (mode != "observe" or connection != "live")
                or owner == "human" and mode == "unknown"):
            self._invalidate()
            raise ValueError("Contradictory ownership observation; obtain fresh evidence")
        if (owner, mode, connection) != (self._owner, self._mode, self._connection):
            self._epoch += 1
            self._lease = None
        self._owner, self._mode, self._connection = owner, mode, connection
        self._deadline = pending["deadline"]
        return self._status(now)

    def _can_act(self, now):
        return (self._deadline is not None and now < self._deadline
                and (self._owner, self._mode, self._connection) == ("dot", "observe", "live"))

    def claim(self, controller_id):
        """Issue an opaque receipt; repeated claims never renew its initial TTL."""
        if (not isinstance(controller_id, str)
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", controller_id) is None):
            raise ValueError("controller_id must be a bounded stable identifier")
        now = self._now()
        self._expire(now)
        if not self._can_act(now) or self._remaining(self._deadline, now) < 1:
            raise ValueError("Fresh Dot ownership evidence is required for an agent turn")
        if self._lease is not None:
            if self._lease["receipt"]["controller_id"] != controller_id:
                raise ValueError("Another cooperating controller holds the turn lease")
            return dict(self._lease["receipt"])
        receipt = {"viewer_id": self.viewer_id, "stream_id": self._stream,
                   "epoch": self._epoch, "sequence": self._sequence,
                   "controller_id": controller_id, "lease_id": secrets.token_hex(32),
                   "expires_in_ms": self._remaining(self._deadline, now)}
        self._lease = {"receipt": receipt, "deadline": self._deadline}
        return dict(receipt)

    def check(self, lease):
        """Check the unchanged receipt against the receiver's private deadline."""
        now = self._now()
        self._expire(now)
        if (not isinstance(lease, dict) or set(lease) != self.LEASE_FIELDS
                or any(type(lease[k]) is not int for k in ("epoch", "sequence", "expires_in_ms"))
                or self._lease is None or lease != self._lease["receipt"]
                or not self._can_act(now)):
            raise ValueError("Turn lease is invalid, replaced or expired")
        return self._status(now)

    def release(self, lease):
        self.check(lease)
        self._lease = None
        self._epoch += 1
        return self.status()
