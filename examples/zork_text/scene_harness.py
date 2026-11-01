"""A bounded, evidence-first scene contract over the original Zork game.

This is an authored observation contract, not UIL or reconstructed game logic.
"""
import hashlib
import json
import os
from pathlib import Path


PROFILE = {
    "interpreter_sha256": "2a6f366349be71ef4a164e3fc9c31a4a3d8c24ee6ddac93ed345c993c3562514",
    "story_sha256": "0ae5ac229e79094ff368b6669356444af0f35e21d862a1baaa546989085c15fd",
}

SCENES = {"West of House", "North of House"}
ACTIONS = {
    "open_mailbox": ("West of House", "open mailbox", "West of House", "Opening the small mailbox reveals a leaflet."),
    "look_west": ("West of House", "look", "West of House", "West of House"),
    "unknown_word": ("West of House", "blorb", "West of House", "I don't know the word"),
    "go_north": ("West of House", "north", "North of House", "North of House"),
    "try_south": ("North of House", "south", "North of House", "The windows are all boarded."),
    "go_west": ("North of House", "west", "West of House", "West of House"),
}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def scene_of(screen):
    # The status row is presentation, not a claim about hidden world state.
    status = screen.get("status", "").strip()
    candidates = [name for name in SCENES if status.startswith(name + " ")]
    return candidates[0] if len(candidates) == 1 else None


def response_after_command(before, after, command):
    # Match the prior screen's tail to the new screen's head, excluding the
    # replaced prompt and status row. This prevents old echoes being treated
    # as new output. If no overlap survives scrolling, the outcome is unknown.
    old = list(before.get("lines", []))[1:]
    new = list(after.get("lines", []))[1:]
    while old and not old[-1]:
        old.pop()
    if old and old[-1] == ">":
        old.pop()
    while old and not old[-1]:
        old.pop()
    overlap = next((n for n in range(min(len(old), len(new)), 0, -1)
                    if old[-n:] == new[:n] and any(old[-n:])), 0)
    if not overlap:
        return None
    fresh = new[overlap:]
    marker = ">" + command
    if marker not in fresh:
        return None
    return "\n".join(fresh[fresh.index(marker) + 1:]).rstrip()


class SceneHarness:
    def __init__(self, adapter, game_dir, identities, run_id, journal):
        self.adapter = adapter
        self.paths = {"interpreter_sha256": Path(game_dir) / "_ZORK1.COM",
                      "story_sha256": Path(game_dir) / "DATA" / "ZORK1.DAT"}
        self.identities = dict(identities)
        self.run_id = run_id
        self.journal = journal
        self.seq = 0
        self._check_identity()
        self._record("session", identities=self.identities, run=run_id,
                     harness_sha256=sha256(__file__), adapter_sha256=sha256(Path(__file__).with_name("adapter.py")),
                     profile="zork-i-r88-840726", authority="original game",
                     limits=["screen observation only", "input acceptance unknown", "persistence unknown"])

    def _check_identity(self):
        for key, expected in PROFILE.items():
            if self.identities.get(key) != expected or sha256(self.paths[key]) != expected:
                raise ValueError("scene profile source identity mismatch: " + key)

    def _record(self, kind, **fields):
        self.seq += 1
        event = {"format": "fdisbull-zork-scene-event-1", "sequence": self.seq,
                 "run": self.run_id, "kind": kind, **fields}
        self.journal.write(json.dumps(event, ensure_ascii=True, sort_keys=True) + "\n")
        self.journal.flush()
        os.fsync(self.journal.fileno())
        return event

    def act(self, name):
        if name not in ACTIONS:
            return self._record("refused", action=name, reason="unknown action", input="not_sent")
        before = self.adapter.ready
        if before is None:
            return self._record("refused", action=name, reason="prompt unavailable", input="not_sent")
        source, command, destination, expected = ACTIONS[name]
        scene = scene_of(before)
        if scene != source:
            return self._record("refused", action=name, scene=scene, expected_scene=source,
                                reason="scene mismatch or unknown", input="not_sent")
        try:
            self._check_identity()
        except (OSError, ValueError) as exc:
            return self._record("refused", action=name, reason=str(exc), input="not_sent")
        self._record("intent", action=name, command=command, scene=scene,
                     before_screen_sha256=before["screen_sha256"], before_status=before["status"],
                     readiness="display prompt heuristic", input="not_yet_sent")
        try:
            after = self.adapter.command(command)
        except Exception as exc:
            # The caller must not infer that the command had no effect.
            return self._record("indeterminate", action=name, input="delivery_or_outcome_unknown",
                                outcome="unknown", error_type=type(exc).__name__, error=str(exc))
        response = response_after_command(before, after, command)
        observed_scene = scene_of(after)
        if response is None:
            verdict = "unknown"  # The echo may have scrolled off screen.
        elif observed_scene != destination or expected not in response:
            verdict = "unexpected"
        else:
            verdict = "observed_expected_response"
        return self._record("result", action=name, command=command, input="queued_then_drained",
                            acceptance="unknown", scene=observed_scene, response=response,
                            expected_scene=destination, expected_text=expected, verdict=verdict,
                            after_screen_sha256=after["screen_sha256"], after_status=after["status"],
                            prompt="display heuristic", persistence="unknown", screen=after["text"])
