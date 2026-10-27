"""Protocol v2: request_id matching, legacy tolerance, audit log.

- A response echoing our request_id is accepted.
- A stale response (wrong id) is NOT consumed; the matching one is.
- A pre-v2 response (no id) is accepted but flagged `_legacy_response`.
- Every dispatched command appends one JSONL audit line (FL_MCP_AUDIT=0 disables).
"""

import json
import time

from fl_studio_mcp.utils.midi_connection import PROTOCOL_VERSION, MIDIConnection


class _FakePort:
    """Fake FL: on trigger, writes a response according to a script."""

    def __init__(self, conn: MIDIConnection, responder):
        self._conn = conn
        self._responder = responder

    def send(self, msg):
        cmd = json.loads(self._conn._command_file.read_text())
        time.sleep(0.01)
        self._responder(cmd, self._conn)


def _make_conn(tmp_path, responder, files=("c.json", "r.json")):
    conn = MIDIConnection()
    conn._command_file = tmp_path / files[0]
    conn._response_file = tmp_path / files[1]
    conn._hardware_dir = tmp_path
    conn._port = _FakePort(conn, responder)
    conn._port_name = "fake"
    conn._connected = True
    return conn


def test_command_carries_id_and_version(tmp_path):
    seen = {}

    def responder(cmd, conn):
        seen.update(cmd)
        conn._response_file.write_text(
            json.dumps({"success": True, "request_id": cmd["request_id"],
                        "protocol_version": cmd["protocol_version"]})
        )

    conn = _make_conn(tmp_path, responder)
    r = conn.send_command("transport.start", {}, timeout=5)
    assert r["success"] is True
    assert r["request_id"] == seen["request_id"]
    assert seen["protocol_version"] == PROTOCOL_VERSION


def test_stale_response_not_consumed_then_matching_one_is(tmp_path):
    def responder(cmd, conn):
        # Slow controller: a delayed reply to the PREVIOUS command lands first,
        # then this command's own reply overwrites it. The waiter must skip the
        # stale one (not consume it) and accept the matching reply.
        conn._response_file.write_text(
            json.dumps({"success": True, "request_id": "stale-deadbeef"})
        )
        time.sleep(0.05)
        conn._response_file.write_text(
            json.dumps({"success": True, "request_id": cmd["request_id"]})
        )

    conn = _make_conn(tmp_path, responder)
    r = conn.send_command("probe.exec", {"code": "1"}, timeout=5)
    assert r["success"] is True
    assert r.get("request_id") != "stale-deadbeef"
    assert r["request_id"]  # it's OUR id


def test_legacy_response_accepted_but_flagged(tmp_path):
    def responder(cmd, conn):
        # Pre-v2 controller: no request_id in the reply.
        conn._response_file.write_text(json.dumps({"success": True, "echo": cmd}))

    conn = _make_conn(tmp_path, responder)
    r = conn.send_command("x", {"n": 1}, timeout=5)
    assert r["success"] is True
    assert r.get("_legacy_response") is True


def test_audit_log_written_and_disableable(tmp_path, monkeypatch):
    def responder(cmd, conn):
        conn._response_file.write_text(
            json.dumps({"success": True, "request_id": cmd["request_id"]})
        )

    conn = _make_conn(tmp_path, responder)
    conn.send_command("a", {"n": 1}, timeout=5)
    conn.send_command("b", {"n": 2}, timeout=5)
    lines = [json.loads(l) for l in (tmp_path / "mcp_audit.jsonl").read_text().splitlines()]
    assert [l["action"] for l in lines] == ["a", "b"]
    assert all(l["ok"] is True for l in lines)
    assert all("elapsed_ms" in l and l["request_id"] for l in lines)

    monkeypatch.setenv("FL_MCP_AUDIT", "0")
    conn.send_command("c", {}, timeout=5)
    lines = [json.loads(l) for l in (tmp_path / "mcp_audit.jsonl").read_text().splitlines()]
    assert [l["action"] for l in lines] == ["a", "b"]  # 'c' not audited
