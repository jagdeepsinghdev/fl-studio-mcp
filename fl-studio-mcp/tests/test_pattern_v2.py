"""B5: fl_pattern — validation + routing + the 2-arg rename contract.

Verified offline:
  - create/select/rename/set_len/clone route to the right controller action
  - rename uses the 2-arg setPatternName path (C4: 3-arg CRASHES FL)
  - create defaults (no length/color) and optional length/color
  - range/missing validation rejected pre-FL
  - a write returns state_after + undo_saved
"""


from fl_studio_mcp.tools.pattern_v2 import ACTIONS, _route, fl_pattern, validate

# ---------------------------------------------------------------------------
# Validation (rejected before FL)
# ---------------------------------------------------------------------------


def test_all_five_actions_route():
    cases = {
        "create": ({"name": "Verse", "length_beats": 16, "color": 3},
                   ("patterns.create", {"name": "Verse", "length_beats": 16, "color": 3})),
        "select": ({"pattern": 2}, ("patterns.select", {"pattern": 2})),
        "rename": ({"pattern": 1, "name": "Chorus"},
                   ("patterns.setName", {"pattern": 1, "name": "Chorus"})),
        "set_len": ({"pattern": 3, "beats": 8},
                    ("patterns.setLength", {"index": 2, "beats": 8})),
        "clone": ({"pattern": 2, "name": "Copy"},
                  ("patterns.clone", {"pattern": 2, "name": "Copy"})),
    }
    for action, (give, want) in cases.items():
        got = _route(action, give)
        assert got == want, f"{action}: {got} != {want}"


def test_create_minimal_omits_optional_params():
    ca, cp = _route("create", {"name": "Intro"})
    assert cp == {"name": "Intro"}  # no length_beats / color keys
    assert ca == "patterns.create"


def test_rename_routes_to_two_arg_setname_path():
    """C4: rename must go through the 2-arg setPatternName path (patterns.setName
    handler), NOT a 3-arg call (which crashes FL)."""
    ca, cp = _route("rename", {"pattern": 5, "name": "Bridge"})
    assert ca == "patterns.setName"
    assert cp == {"pattern": 5, "name": "Bridge"}
    # no 'flags' key anywhere in the routed params
    assert "flags" not in cp


def test_create_requires_name():
    assert validate("create", {})
    assert validate("create", {"name": ""})
    assert validate("create", {"name": "Verse"}) == []


def test_rename_requires_name():
    assert validate("rename", {"pattern": 1})
    assert validate("rename", {"pattern": 1, "name": "Chorus"}) == []


def test_pattern_index_must_be_positive():
    assert validate("select", {"pattern": 0})
    assert validate("select", {"pattern": -1})
    assert validate("select", {"pattern": 1}) == []


def test_set_len_beats_must_be_positive():
    assert validate("set_len", {"pattern": 1, "beats": 0})
    assert validate("set_len", {"pattern": 1, "beats": 4}) == []


def test_unknown_action_rejected():
    r = validate("clear", {"pattern": 1})
    assert r[0].startswith("unknown action")
    # clear is deliberately absent (destructive → fl_delete)
    assert "clear" not in ACTIONS


# ---------------------------------------------------------------------------
# Same-trip write contract (mocked connection)
# ---------------------------------------------------------------------------


class _FakeConn:
    def __init__(self):
        self.calls = []

    def send_command(self, action, params=None, timeout=2.0):
        self.calls.append((action, dict(params or {})))
        if action == "patterns.create":
            return {"success": True, "protocol_v2": True,
                    "pattern": 1, "name": params.get("name"),
                    "state_after": {"pattern": 1, "name": params.get("name")},
                    "undo_saved": "fl_create"}
        if action == "patterns.setName":
            return {"success": True, "protocol_v2": True,
                    "pattern": params.get("pattern"),
                    "name": params.get("name"),
                    "state_after": {"pattern": params.get("pattern"),
                                   "name": params.get("name")},
                    "undo_saved": "fl_rename"}
        if action == "patterns.setLength":
            return {"success": True, "protocol_v2": True,
                    "state_after": {"pattern": params.get("pattern"),
                                   "beats": params.get("beats")},
                    "undo_saved": "fl_set_len"}
        return {"success": True, "protocol_v2": True, "state_after": {}}


def test_create_returns_state_after_and_undo():
    conn = _FakeConn()
    r = fl_pattern("create", conn=conn, name="Verse", length_beats=16)
    assert r["success"] is True
    assert r["state_after"]["name"] == "Verse"
    assert r["undo_saved"]
    ca, cp = conn.calls[0]
    assert ca == "patterns.create"
    assert cp.get("_undo_name")  # safety injected the undo


def test_rename_returns_state_after_with_new_name():
    conn = _FakeConn()
    r = fl_pattern("rename", conn=conn, pattern=1, name="Chorus")
    assert r["success"] is True
    assert r["state_after"]["name"] == "Chorus"
    ca, cp = conn.calls[0]
    assert ca == "patterns.setName"
    assert "flags" not in cp  # 2-arg: no flags (3-arg crashes FL)


def test_invalid_call_never_reaches_fl():
    conn = _FakeConn()
    r = fl_pattern("select", conn=conn, pattern=0)
    assert r["success"] is False
    assert "valid_actions" in r
    assert conn.calls == []


class _CloneConn:
    def __init__(self, active, new):
        self.active, self.new, self.calls = active, new, []

    def send_command(self, action, params=None, timeout=None):
        self.calls.append((action, dict(params or {})))
        if action == "probe.patterns":
            return {"success": True, "active_pattern": self.active}
        if action == "patterns.clone":
            return {"success": True, "source": params.get("pattern"),
                    "pattern": self.new, "name": "copy", "undo_saved": "u"}
        return {"success": True}


def test_clone_restores_the_previously_active_pattern():
    """L8 (live): cloning pattern 4 left pattern 5 active — the drill in
    pattern 3 stopped being the playing pattern."""
    conn = _CloneConn(active=3, new=5)
    r = fl_pattern("clone", conn=conn, pattern=4)
    assert ("patterns.select", {"pattern": 3}) in conn.calls
    assert r["result"]["pattern"] == 5  # the clone payload is returned now


def test_clone_before_the_active_pattern_shifts_the_restore_target():
    conn = _CloneConn(active=3, new=2)  # clone of 1 lands in 2, old 3 is now 4
    fl_pattern("clone", conn=conn, pattern=1)
    assert ("patterns.select", {"pattern": 4}) in conn.calls
