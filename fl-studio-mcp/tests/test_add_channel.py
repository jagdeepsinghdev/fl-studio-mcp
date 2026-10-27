"""utils/add_channel.py — native Add-menu channel creation (mocked; no clicks)."""

from __future__ import annotations

from fl_studio_mcp.utils import add_channel as ac


class _Conn:
    def __init__(self, chans):
        self.chans = chans
        self.calls = []

    def send_command(self, action, params=None, timeout=None):
        self.calls.append((action, dict(params or {})))
        if action == "channels.getAll":
            return {"channels": list(self.chans)}
        return {"success": True}


def _env(monkeypatch, conn, grows=True):
    monkeypatch.setattr(ac, "get_connection", lambda: conn)
    monkeypatch.setattr(ac.time, "sleep", lambda s: None)

    def click(name):
        if grows:
            conn.chans.append({"index": len(conn.chans), "name": name,
                               "target_fx_track": 0})
        return True, "ok"
    monkeypatch.setattr(ac, "_click_add_menu_item", click)


def test_setup_routes_to_first_free_mixer_track_and_renames(monkeypatch):
    conn = _Conn([{"index": i, "name": f"c{i}", "target_fx_track": i + 1}
                  for i in range(6)])          # tracks 1..6 used
    _env(monkeypatch, conn)
    r = ac.setup_instrument("3x Osc", "808")
    assert r["ok"] and r["index"] == 6 and r["mixer_track"] == 7
    actions = [a for a, _ in conn.calls]
    assert ("channels.routeToMixer", {"channel_index": 6, "mixer_track": 7}) in conn.calls
    assert ("channels.setName", {"index": 6, "name": "808", "use_global": True}) in conn.calls
    assert actions[-1] == "channels.selectOne"


def test_add_fails_when_no_channel_appears(monkeypatch):
    conn = _Conn([{"index": 0, "name": "k", "target_fx_track": 1}])
    _env(monkeypatch, conn, grows=False)
    r = ac.setup_instrument("3x Osc", "808")
    assert r["ok"] is False and "no channel appeared" in r["error"]
    assert not any(a == "channels.setName" for a, _ in conn.calls)


def test_add_fails_when_fl_unreachable(monkeypatch):
    class Dead:
        def send_command(self, *a, **k):
            return {"success": False, "error": "timeout"}
    monkeypatch.setattr(ac, "get_connection", lambda: Dead())
    assert ac.add_instrument("FLEX")["ok"] is False
