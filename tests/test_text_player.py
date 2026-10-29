import copy
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "player"))
from fdisbull_player import LocalRuntime, Player


def obj(id, label, verbs, aliases=()):
    return {"id": id, "label": label, "aliases": list(aliases), "description": label + " description", "verbs": verbs}


def package():
    return {"format": "fdisbull-text-slice-1", "state": {"health": 10, "position": 0, "hidden": False},
            "context": {"id": "room", "title": "Room", "description": "A room."},
            "objects": [obj("east", "east", ["go"]), obj("key1", "brass key", ["take"], ["key"]),
                        obj("key2", "iron key", ["take"], ["key"])], "inventory": [], "partial": True,
            "actions": [{"verb": "go", "target": "east", "item": None, "steps": [
                {"effects": [{"op": "add", "key": "position", "value": 1}], "ticks": 1},
                {"effects": [{"op": "add", "key": "position", "value": 1}], "ticks": 1}], "message": "Moved east."}],
            "scheduled": [{"tick": 2, "effects": [{"op": "add", "key": "health", "value": -2}, {"op": "event", "name": "hazard"}]}]}


def test_hidden_state_and_private_fields_never_appear():
    a = package(); b = copy.deepcopy(a); b["state"]["hidden"] = True
    a["context"]["private"] = "secret"; b["objects"][0]["private"] = "other secret"
    p, q = Player(LocalRuntime(a)), Player(LocalRuntime(b))
    for command in ("look", "inventory", "help", "examine east", "take invisible"):
        assert p.execute(command) == q.execute(command)
        assert "secret" not in p.execute(command)


def test_ambiguity_and_staleness_do_not_act():
    runtime = LocalRuntime(package()); player = Player(runtime)
    assert player.execute("take key").startswith("Which one?")
    assert runtime.tick == 0
    runtime.revision += 1
    assert "Context changed" in player.execute("1")
    assert runtime.tick == 0 and runtime.state["position"] == 0


def test_two_steps_and_scheduled_event_and_passive_reads():
    runtime = LocalRuntime(package()); player = Player(runtime)
    player.execute("look"); player.execute("inventory")
    assert runtime.tick == 0
    assert player.execute("go east") == "Success: Moved east."
    assert (runtime.tick, runtime.state["position"], runtime.state["health"]) == (2, 2, 8)
    assert runtime.events == [{"tick": 2, "name": "hazard"}]


def test_unknown_effect_prevents_all_effects_and_partial_stop_preserves_them():
    p = package(); p["actions"][0]["steps"][1]["effects"].append({"op": "unknown"})
    runtime = LocalRuntime(p)
    assert Player(runtime).execute("go east").startswith("Incomplete")
    assert runtime.tick == 0 and runtime.state["position"] == 0
    p = package(); p["actions"][0]["steps"][1]["effects"].append({"op": "stop"})
    runtime = LocalRuntime(p)
    assert Player(runtime).execute("go east").startswith("Incomplete")
    assert runtime.tick == 1 and runtime.state["position"] == 2


def test_backend_outcome_is_not_invented():
    p = package(); p["actions"][0].update(status="rejected", message="Ignored.", steps=[])
    runtime = LocalRuntime(p)
    assert Player(runtime).execute("go east") == "Rejected: Ignored."
    assert runtime.state["position"] == 0


def test_separate_player_displays_spatial_policy_without_guard_details():
    runtime=LocalRuntime(package())
    runtime.act=lambda request:{'status':'success','complete':True,'message':'Moved.',
        'assistance':{'kind':'spatial','mode':'story'},'private_guard':'SECRET'}
    reply=Player(runtime).execute('go east')
    assert reply=='Success: Moved.\nSpatial policy: story.' and 'SECRET' not in reply


def test_standalone_module_cli(tmp_path):
    path = tmp_path / "slice.json"; path.write_text(json.dumps(package()))
    proc = subprocess.run([sys.executable, "-m", "fdisbull_player", "--package", str(path)],
                          input="go east\nquit\n", text=True, capture_output=True,
                          cwd=Path(__file__).resolve().parents[1] / "player")
    assert proc.returncode == 0 and "Success: Moved east." in proc.stdout


def test_reobserve_detects_stale_and_no_dispatch():
    class ChangingBackend:
        def __init__(self):
            self.runtime = LocalRuntime(package()); self.calls = 0; self.acted = False
        def observe(self):
            self.calls += 1
            if self.calls == 2:
                self.runtime.revision += 1
            return self.runtime.observe()
        def act(self, request):
            self.acted = True
            return self.runtime.act(request)
    backend = ChangingBackend()
    assert "no action sent" in Player(backend).execute("go east")
    assert not backend.acted and backend.runtime.tick == 0


def test_incomplete_observation_withholds_action():
    runtime = LocalRuntime(package())
    original = runtime.observe
    runtime.observe = lambda: {**original(), "complete": False}
    assert "Observation incomplete" in Player(runtime).execute("go east")
    assert runtime.tick == 0


def test_partial_inventory_does_not_claim_nothing_and_partial_success_is_incomplete():
    runtime=LocalRuntime(package());player=Player(runtime)
    assert player.execute('inventory')=='No inventory items are recorded in this partial view.'
    runtime.act=lambda request:{'status':'success','complete':False,'message':'Capture missing.'}
    assert player.execute('go east')=='Incomplete: Capture missing.'


def test_multiple_contexts_transition_and_context_specific_actions():
    p = package()
    room = {"context": p.pop("context"), "objects": p.pop("objects"), "partial": True}
    other = {"context": {"id": "hall", "title": "Hall", "description": "A hall."},
             "objects": [obj("west", "west", ["go"])], "partial": False}
    p.update(contexts={"room": room, "hall": other}, initial_context="room")
    p["actions"][0]["context"] = "room"
    p["actions"][0]["steps"].append({"effects": [{"op": "context", "id": "hall"}]})
    p["actions"].append({"context": "hall", "verb": "go", "target": "west", "item": None,
                         "steps": [{"effects": [{"op": "context", "id": "room"}]}], "message": "Back."})
    runtime = LocalRuntime(p); player = Player(runtime)
    token = runtime.observe()["context"]["token"]
    assert player.execute("go east").startswith("Success")
    assert "Hall" in player.execute("look") and "west" in player.execute("look")
    assert "no action sent" in player.execute("go east")
    assert runtime.act({"verb": "go", "target": "west", "item": None, "context_token": token})["status"] == "rejected"
    assert player.execute("go west") == "Success: Back."
    assert "Room" in player.execute("look")


def test_hidden_only_state_has_identical_public_projection_including_token():
    a = package(); b = copy.deepcopy(a); b["state"]["hidden"] = True
    assert LocalRuntime(a).observe() == LocalRuntime(b).observe()


def test_unknown_guard_missing_capture_and_unknown_wait_fail_before_effects():
    for change in (lambda a: a.update(guards=[{"key": "missing_capture", "equals": True}]),
                   lambda a: a["steps"][1].update(wait={"kind": "unknown"}),
                   lambda a: a["steps"][1]["effects"].append({"op": "set", "key": "missing_capture", "value": 1})):
        p = package(); change(p["actions"][0]); runtime = LocalRuntime(p)
        assert Player(runtime).execute("go east").startswith("Incomplete")
        assert runtime.tick == 0 and runtime.state["position"] == 0


def test_event_order_and_overflow_are_checked_before_effects():
    p = package()
    p["actions"][0]["steps"][0]["effects"].insert(0, {"op": "event", "name": "start"})
    p["scheduled"][0]["effects"].append({"op": "event", "name": "after"})
    runtime = LocalRuntime(p); Player(runtime).execute("go east")
    assert runtime.events == [{"tick": 0, "name": "start"}, {"tick": 2, "name": "hazard"},
                              {"tick": 2, "name": "after"}]
    p = package(); p["state"]["position"] = 2**63 - 2
    runtime = LocalRuntime(p)
    assert Player(runtime).execute("go east").startswith("Incomplete")
    assert runtime.state["position"] == 2**63 - 2 and runtime.tick == 0


def adventure_package():
    key = obj('key', 'brass key', ['take', 'drop'], ['key'])
    gate = obj('gate', 'gate', ['use'])
    east = obj('east', 'east', ['go'])
    west = obj('west', 'west', ['go'])
    return {'format':'fdisbull-text-slice-1', 'state':{'unlocked':False,'private':False},
            'initial_context':'yard', 'contexts':{
                'yard':{'context':{'id':'yard','title':'Yard','description':'A yard.'},'objects':[key,gate,east]},
                'hall':{'context':{'id':'hall','title':'Hall','description':'A hall.'},'objects':[west]}},
            'inventory':[], 'actions':[
                {'context':'yard','verb':'take','target':'key','item':None,
                 'steps':[{'effects':[{'op':'carry','id':'key'}], 'ticks':1}], 'message':'Taken.'},
                {'context':'yard','verb':'use','target':'gate','item':'key',
                 'guards':[{'carrying':'key'}], 'rejected_message':'You must carry the key.',
                 'steps':[{'effects':[{'op':'set','key':'unlocked','value':True}], 'ticks':1}], 'message':'The gate unlocks.'},
                {'context':'yard','verb':'go','target':'east','item':None,
                 'guards':[{'key':'unlocked','equals':True}], 'rejected_message':'The gate is locked.',
                 'steps':[{'effects':[{'op':'context','id':'hall'}], 'ticks':1}], 'message':'You enter the hall.'},
                {'context':'hall','verb':'drop','target':'key','item':None,
                 'steps':[{'effects':[{'op':'drop','id':'key'}]}], 'message':'Dropped.'},
                {'context':'hall','verb':'take','target':'key','item':None,
                 'steps':[{'effects':[{'op':'carry','id':'key'}]}], 'message':'Taken.'},
                {'context':'hall','verb':'go','target':'west','item':None,
                 'steps':[{'effects':[{'op':'context','id':'yard'}]}], 'message':'You return to the yard.'}],
            'scheduled':[]}


def test_synthetic_two_room_key_and_gate():
    runtime=LocalRuntime(adventure_package()); player=Player(runtime)
    assert 'Yard' in player.execute('look') and 'brass key' in player.execute('look')
    assert player.execute('examine key') == 'brass key description'
    assert player.execute('use key on gate') == 'Rejected: You must carry the key.'
    assert player.execute('go east') == 'Rejected: The gate is locked.'
    assert runtime.tick == 0 and runtime.context_id == 'yard'
    assert player.execute('take key') == 'Success: Taken.'
    assert player.execute('inventory') == 'Carrying: brass key.'
    assert player.execute('use key on gate') == 'Success: The gate unlocks.'
    assert player.execute('go east') == 'Success: You enter the hall.'
    assert 'Hall' in player.execute('look')
    assert player.execute('drop key') == 'Success: Dropped.'
    assert player.execute('inventory') == 'Carrying: nothing.'
    assert 'brass key' in player.execute('look')
    assert player.execute('take key') == 'Success: Taken.'
    assert player.execute('go west') == 'Success: You return to the yard.'
    assert player.execute('inventory') == 'Carrying: brass key.'
    assert runtime.tick == 3


def test_bad_inventory_effects_have_no_partial_side_effects():
    p=adventure_package(); action=p['actions'][0]
    action['steps'][0]['effects'].insert(0, {'op':'set','key':'unlocked','value':True})
    action['steps'][0]['effects'].append({'op':'carry','id':'unknown'})
    r=LocalRuntime(p)
    assert Player(r).execute('take key').startswith('Incomplete')
    assert not r.state['unlocked'] and r.tick==0 and not r.inventory
    action['steps'][0]['effects'][-1]={'op':'carry','id':'key'}
    r=LocalRuntime(p)
    assert Player(r).execute('take key').startswith('Incomplete')
    assert not r.state['unlocked'] and r.tick==0 and not r.inventory


def test_text_protocol_line_limit():
    from io import StringIO
    from fdisbull_player import JsonLineBackend
    backend=JsonLineBackend(StringIO('x' * (1024*1024) + '\n'), StringIO())
    import pytest
    with pytest.raises(ValueError, match='line limit'):
        backend.observe()
