"""A deterministic player which exposes only the declared public projection."""
import json
import re


def _text(value):
    return value if isinstance(value, str) else ""


def public_observation(raw):
    if not isinstance(raw, dict):
        return None
    c = raw.get("context")
    coverage = raw.get("coverage")
    if (raw.get("complete") is not True or not isinstance(c, dict)
            or not isinstance(c.get("id"), str) or not c["id"]
            or not isinstance(c.get("token"), str) or not c["token"]
            or not isinstance(coverage, dict) or not isinstance(coverage.get("partial"), bool)):
        return None
    result = {"context": {k: _text(c.get(k)) for k in ("id", "token", "title", "description")},
              "coverage": {"partial": coverage["partial"]}}
    seen = set()
    for group in ("objects", "inventory"):
        values = raw.get(group)
        if not isinstance(values, list):
            return None
        result[group] = []
        for obj in values:
            if (not isinstance(obj, dict) or not isinstance(obj.get("id"), str)
                    or not obj["id"] or obj["id"] in seen or not isinstance(obj.get("label"), str)
                    or not obj["label"] or not isinstance(obj.get("aliases"), list)
                    or not all(isinstance(x, str) for x in obj["aliases"])
                    or not isinstance(obj.get("verbs"), list)
                    or not all(isinstance(x, str) for x in obj["verbs"])):
                return None
            seen.add(obj["id"])
            result[group].append({"id": obj["id"], "label": obj["label"],
                                  "aliases": list(obj["aliases"]), "description": _text(obj.get("description")),
                                  "verbs": list(obj["verbs"])})
    return result


class Player:
    """Reads are passive; only resolved non-read commands reach backend.act."""
    def __init__(self, backend):
        self.backend = backend
        self.pending = None
        self.last_status = "complete"

    def _observe(self):
        return public_observation(self.backend.observe())

    @staticmethod
    def _lookup(obs, name):
        name = name.casefold().strip()
        return [o for o in obs["objects"] + obs["inventory"]
                if name in [o["label"].casefold()] + [a.casefold() for a in o["aliases"]]]

    def execute_structured(self, command):
        """Return the existing public text with a machine-readable outcome status."""
        message = self.execute(command)
        return {"outcome": message, "status": self.last_status}

    def execute(self, command):
        self.last_status = "complete"
        command = command.strip()
        if not command:
            return "Enter a command."
        obs = self._observe()
        if obs is None:
            self.pending = None
            self.last_status = "incomplete"
            return "Observation incomplete; no action sent."
        if self.pending:
            pending = self.pending
            self.pending = None
            if obs["context"]["id"] != pending["context"] or obs["context"]["token"] != pending["token"]:
                return "Context changed; no action sent. Look again."
            choices = pending["choices"]
            selection = int(command) - 1 if command.isdecimal() else -1
            if not 0 <= selection < len(choices):
                return "Clarification cancelled; no action sent."
            target = choices[selection]
            current = [o for o in obs["objects"] + obs["inventory"] if o["id"] == target]
            if not current:
                return "Target no longer visible; no action sent."
            return self._resolve(obs, pending["verb"], pending["target"], pending["item"],
                                 pending["slot"], target, pending["resolved"])
        lower = command.casefold()
        if lower in ("look", "l"):
            c = obs["context"]
            lines = [c["title"], c["description"]]
            if obs["objects"]:
                lines.append("Visible: " + ", ".join(o["label"] for o in obs["objects"]) + ".")
            if obs["coverage"]["partial"]:
                lines.append("Observation coverage is partial.")
            return "\n".join(x for x in lines if x)
        if lower in ("inventory", "i"):
            if not obs["inventory"] and obs["coverage"]["partial"]:
                return "No inventory items are recorded in this partial view."
            return "Carrying: " + (", ".join(o["label"] for o in obs["inventory"]) or "nothing") + "."
        if lower in ("help", "?"):
            return "Passive reads: look, examine <object>, inventory, help. Actions: <verb> <object>, go <direction>, use <item> on <target>. Clarify by number."
        match = re.fullmatch(r"(?:examine|x)\s+(.+)", command, re.I)
        if match:
            found = self._lookup(obs, match.group(1))
            if len(found) != 1:
                return "Object is ambiguous or not visible."
            return found[0]["description"] or "No description available."
        match = re.fullmatch(r"use\s+(.+?)\s+on\s+(.+)", command, re.I)
        if match:
            return self._resolve(obs, "use", match.group(2), match.group(1))
        match = re.fullmatch(r"([\w-]+)(?:\s+(.+))?", command)
        if not match:
            return "Command not understood; no action sent."
        if match.group(2) is None:
            return "Action requires a visible target; no action sent."
        return self._resolve(obs, match.group(1).casefold(), match.group(2), None)

    def _resolve(self, obs, verb, target_name, item_name, selected_slot=None, selected_id=None, resolved=None):
        ids = dict(resolved or {})
        if selected_slot:
            ids[selected_slot] = selected_id
        for slot, name in (("target", target_name), ("item", item_name)):
            if name is None:
                ids[slot] = None
                continue
            found = self._lookup(obs, name)
            if slot in ids:
                found = [o for o in found if o["id"] == ids[slot]]
            if not found:
                return "Target is not visible or supported; no action sent."
            if len(found) > 1:
                self.pending = {"context": obs["context"]["id"], "token": obs["context"]["token"],
                                "verb": verb, "target": target_name, "item": item_name,
                                "slot": slot, "choices": [o["id"] for o in found], "resolved": dict(ids)}
                return "Which one? " + "; ".join(f"{i}. {o['label']}" for i, o in enumerate(found, 1))
            ids[slot] = found[0]["id"]
            if slot == "target" and verb not in [v.casefold() for v in found[0]["verbs"]]:
                return "Action is not supported for that target; no action sent."
        fresh = self._observe()
        if fresh is None or fresh["context"]["id"] != obs["context"]["id"] or fresh["context"]["token"] != obs["context"]["token"]:
            if fresh is None:
                self.last_status = "incomplete"
            return "Context changed or observation incomplete; no action sent."
        for slot, name in (("target", target_name), ("item", item_name)):
            if name is not None and not any(o["id"] == ids[slot] for o in self._lookup(fresh, name)):
                return "Target no longer visible; no action sent."
        if ids["target"] is not None:
            target = next(o for o in fresh["objects"] + fresh["inventory"] if o["id"] == ids["target"])
            if verb not in [v.casefold() for v in target["verbs"]]:
                return "Action is no longer supported; no action sent."
        result = self.backend.act({"verb": verb, **ids, "context_token": fresh["context"]["token"]})
        if not isinstance(result, dict) or result.get("status") not in ("success", "rejected", "incomplete", "accepted") or not isinstance(result.get("complete"), bool):
            self.last_status = "incomplete"
            return "Action outcome unavailable."
        message = _text(result.get("message"))
        status = 'incomplete' if result['status']=='success' and not result['complete'] else result['status']
        self.last_status = status if result['complete'] else 'incomplete'
        output = f"{status.capitalize()}{' (incomplete)' if not result['complete'] and status!='incomplete' else ''}: {message}".rstrip()
        assistance = result.get("assistance")
        if isinstance(assistance, dict) and assistance.get("kind") in ("movement", "assisted-travel"):
            output += f"\nAssistance: {assistance['kind']}."
        if isinstance(assistance, dict) and assistance.get('kind') == 'spatial' and assistance.get('mode') in ('physical','assisted','story'):
            output += f"\nSpatial policy: {assistance['mode']}."
        return output


class JsonLineBackend:
    """One JSON request/response per line over caller-owned text streams."""
    def __init__(self, reader, writer):
        self.reader, self.writer = reader, writer

    def _request(self, payload):
        encoded = json.dumps(payload, separators=(",", ":")) + "\n"
        if len(encoded.encode("utf-8")) > 1024 * 1024:
            raise ValueError("Backend request exceeds the line limit")
        self.writer.write(encoded)
        self.writer.flush()
        line = self.reader.readline(1024 * 1024 + 1)
        if not line:
            raise EOFError("Backend closed connection")
        if not line.endswith("\n") or len(line.encode("utf-8")) > 1024 * 1024:
            raise ValueError("Backend response exceeds the line limit or is incomplete")
        return json.loads(line)

    def observe(self):
        return self._request({"op": "observe"})

    def act(self, request):
        return self._request({"op": "act", "action": request})

    def save(self, slot="live"):
        return self._request({"op": "save", "slot": slot})

    def load(self, checkpoint="live"):
        return self._request({"op": "load", "checkpoint": checkpoint})
