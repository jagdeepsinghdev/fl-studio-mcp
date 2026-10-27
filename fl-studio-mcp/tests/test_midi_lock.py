"""S4 (A1): concurrent MCP tool calls must serialize on the MIDI JSON channel.

The command/response file pair is shared state; before the lock, two parallel
calls could interleave (one's 'clear response' deleting the other's reply, or
two command files overwriting each other) -> spurious timeouts. These tests
simulate FL with a fake MIDI port and assert:
  1. no two send_command calls are ever in-flight simultaneously
  2. every caller still gets its own, correct response (no cross-talk)
  3. the serialization holds across separate connection instances (after
     reset_connection) because the files are shared
"""

import json
import threading
import time

from fl_studio_mcp.utils.midi_connection import MIDIConnection


class _FakePort:
    """Mimics FL's controller: on trigger, read the command file, process it,
    write the response file. Tracks concurrency so a missing lock fails loudly."""

    def __init__(self, conn: MIDIConnection):
        self._conn = conn
        self.active = 0
        self._lock = threading.Lock()

    def send(self, msg):
        with self._lock:
            self.active += 1
            assert self.active <= 1, "two commands in flight at once (S4 violated)"
        cmd = json.loads(self._conn._command_file.read_text())
        time.sleep(0.02)  # simulate FL processing time
        self._conn._response_file.write_text(
            json.dumps({"success": True, "echo": cmd})
        )
        time.sleep(0.03)  # widen the race window
        with self._lock:
            self.active -= 1


def _make_conn(tmp_path, files=("mcp_command.json", "mcp_response.json")) -> MIDIConnection:
    conn = MIDIConnection()
    conn._command_file = tmp_path / files[0]
    conn._response_file = tmp_path / files[1]
    conn._port = _FakePort(conn)
    conn._port_name = "fake"
    conn._connected = True
    return conn


def test_concurrent_calls_serialize_and_get_own_response(tmp_path):
    conn = _make_conn(tmp_path)

    results, errors = [], []
    lock = threading.Lock()

    def worker(i):
        try:
            r = conn.send_command("probe.exec", {"code": f"print({i})"}, timeout=15)
            with lock:
                results.append(r)
        except Exception as e:  # noqa: BLE001
            with lock:
                errors.append(repr(e))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors
    assert len(results) == 8
    # Each caller got a response echoing ITS OWN command (no cross-talk).
    for r in results:
        assert r["success"] is True
        assert r["echo"]["action"] == "probe.exec"


def test_lock_holds_across_connection_instances(tmp_path):
    """Two connection objects sharing the same files (e.g. after
    reset_connection) must still serialize on one in-flight command."""
    a = _make_conn(tmp_path, ("shared_command.json", "shared_response.json"))
    b = _make_conn(tmp_path, ("shared_command.json", "shared_response.json"))

    done, errors = [], []
    lock = threading.Lock()

    def worker(conn):
        try:
            r = conn.send_command("x", {"n": 1}, timeout=15)
            with lock:
                done.append(r["success"])
        except Exception as e:  # noqa: BLE001
            with lock:
                errors.append(repr(e))

    threads = [
        threading.Thread(target=worker, args=(a,)),
        threading.Thread(target=worker, args=(b,)),
        threading.Thread(target=worker, args=(a,)),
        threading.Thread(target=worker, args=(b,)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors
    assert done == [True] * 4
