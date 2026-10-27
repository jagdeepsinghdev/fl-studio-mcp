"""MIDI-based connection to FL Studio.

This module provides communication with FL Studio via MIDI messages and JSON files.
The approach is:
1. Write command data to a JSON file
2. Send a MIDI trigger note to FL Studio
3. FL Studio's MIDI controller script executes the command
4. Read the response from a JSON file

This is similar to how the piano_roll module works, but uses MIDI for triggering
instead of keystrokes.
"""

from __future__ import annotations

import json
import os
import platform
import threading
import time
import uuid
from pathlib import Path
from typing import Any

# Protocol version of the command/response JSON (v2: request_id echo).
# Bump when the command/response *shape* changes. The controller must be re-synced
# (FL restart) when the server moves to a new version; until then, responses that
# lack a request_id are treated as legacy (accepted, flagged) so the server stays
# backward-compatible with an un-updated controller.
PROTOCOL_VERSION = 2

# S4: the command/response file pair is shared state — one in-flight command at a
# time, no matter which thread (MCP tool calls run concurrently) issues them.
# Module-level (not per-instance) because every instance points at the same files.
_COMMAND_LOCK = threading.Lock()


def _get_fl_hardware_dir() -> Path:
    """Get the FL Studio Hardware scripts directory."""
    system = platform.system()

    if system in ("Darwin", "Windows"):
        base = Path.home() / "Documents" / "Image-Line" / "FL Studio" / "Settings"
    else:
        # Linux fallback
        base = Path.home() / ".fl-studio" / "Settings"

    hardware_dir = base / "Hardware" / "FLStudioMCP"
    hardware_dir.mkdir(parents=True, exist_ok=True)
    return hardware_dir


class MIDIConnection:
    """MIDI-based connection to FL Studio.

    Communicates with FL Studio via:
    - JSON files for command/response data
    - MIDI trigger note to execute commands
    """

    # MIDI trigger note (same as in FL Studio controller script)
    TRIGGER_NOTE = 127

    def __init__(self) -> None:
        self._port = None
        self._port_name: str | None = None
        self._connected = False
        self._error: str | None = None

        # File paths for JSON communication
        self._hardware_dir = _get_fl_hardware_dir()
        self._command_file = self._hardware_dir / "mcp_command.json"
        self._response_file = self._hardware_dir / "mcp_response.json"

    @property
    def is_connected(self) -> bool:
        """Check if connected to FL Studio."""
        return self._connected and self._port is not None

    @property
    def connection_error(self) -> str | None:
        """Get the last connection error, if any."""
        return self._error

    def connect(self) -> bool:
        """Attempt to connect to FL Studio via MIDI.

        Returns True if connection successful, False otherwise.
        """
        if self._connected and self._port is not None:
            return True

        try:
            import mido
        except ImportError:
            self._error = (
                "mido library not installed. Install with: pip install mido python-rtmidi"
            )
            return False

        # Find available MIDI output ports
        try:
            output_ports = mido.get_output_names()
        except Exception as e:
            self._error = f"Failed to get MIDI ports: {e}"
            return False

        if not output_ports:
            self._error = (
                "No MIDI output ports found. On Mac, enable IAC Driver in Audio MIDI Setup."
            )
            return False

        # Look for IAC Driver (Mac) or other virtual MIDI ports
        # fl_controller/fl_midi_loop.py creates this port when IAC is unavailable
        target_port = "FL Studio MCP" if "FL Studio MCP" in output_ports else None
        for port_name in ([] if target_port else output_ports):
            # Prefer IAC Driver on Mac
            if "IAC" in port_name:
                target_port = port_name
                break
            # Also accept loopMIDI on Windows or any port with "FL" in name
            if "loopMIDI" in port_name or "FL" in port_name.upper():
                target_port = port_name
                break

        # If no specific port found, use the first available
        if target_port is None:
            target_port = output_ports[0]

        try:
            self._port = mido.open_output(target_port)
            self._port_name = target_port
            self._connected = True
            self._error = None
            return True
        except Exception as e:
            self._error = f"Failed to open MIDI port '{target_port}': {e}"
            return False

    def disconnect(self) -> None:
        """Close the MIDI connection."""
        if self._port is not None:
            try:
                self._port.close()
            except Exception:
                pass
            self._port = None
        self._connected = False
        self._port_name = None

    def ensure_connected(self) -> None:
        """Ensure connection to FL Studio is active. Raises RuntimeError if not."""
        if not self.is_connected:
            if not self.connect():
                raise RuntimeError(
                    self._error or "Failed to connect to FL Studio via MIDI"
                )

    def send_command(
        self,
        action: str,
        params: dict[str, Any] | None = None,
        timeout: float = 2.0,
    ) -> dict[str, Any]:
        """Send a command to FL Studio and wait for response.

        Args:
            action: The command action (e.g., "transport.start", "mixer.setTrackVolume")
            params: Optional parameters for the command
            timeout: Maximum time to wait for response in seconds

        Returns:
            Response dictionary from FL Studio

        Raises:
            RuntimeError: If not connected or command fails
        """
        with _COMMAND_LOCK:
            return self._send_command_locked(action, params, timeout)

    def _send_command_locked(
        self,
        action: str,
        params: dict[str, Any] | None = None,
        timeout: float = 2.0,
    ) -> dict[str, Any]:
        """Body of send_command — only called while holding _COMMAND_LOCK."""
        self.ensure_connected()

        # Prepare command (protocol v2: request_id lets the response be matched
        # to THIS command; protocol_version catches a stale/mismatched controller).
        request_id = uuid.uuid4().hex
        command = {
            "action": action,
            "params": params or {},
            "request_id": request_id,
            "protocol_version": PROTOCOL_VERSION,
        }

        # Write command to file
        try:
            self._command_file.write_text(json.dumps(command, indent=2))
        except Exception as e:
            return {"success": False, "error": f"Failed to write command file: {e}"}

        # Clear old response file
        if self._response_file.exists():
            try:
                self._response_file.unlink()
            except Exception:
                pass

        # Send MIDI trigger
        try:
            import mido
            trigger_msg = mido.Message("note_on", note=self.TRIGGER_NOTE, velocity=127)
            self._port.send(trigger_msg)
        except Exception as e:
            return {"success": False, "error": f"Failed to send MIDI trigger: {e}"}

        # Wait for response
        started = time.time()
        response = self._wait_for_response(timeout, request_id)
        self._audit(action, params, response, started)
        return response

    def _audit(
        self,
        action: str,
        params: dict[str, Any] | None,
        response: dict[str, Any],
        started: float,
    ) -> None:
        """Append one JSONL line per dispatched command (debugging + training data).

        Never raises: auditing must not break control. Set FL_MCP_AUDIT=0 to disable.
        """
        if os.environ.get("FL_MCP_AUDIT", "1") == "0":
            return
        try:
            entry = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "action": action,
                "params": params or {},
                "ok": bool(response.get("success", False)),
                "error": response.get("error"),
                "elapsed_ms": int((time.time() - started) * 1000),
                "request_id": response.get("request_id"),
            }
            with open(self._hardware_dir / "mcp_audit.jsonl", "a") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:  # noqa: BLE001 - auditing must never break control
            pass

    def _wait_for_response(
        self, timeout: float, request_id: str | None = None
    ) -> dict[str, Any]:
        """Wait for response file to appear and read it.

        Protocol v2: if the response carries a request_id it must match ours —
        a mismatch means a stale response from an earlier command (same bug
        class as the stale piano-roll state file); keep waiting. A response
        WITHOUT a request_id comes from a pre-v2 controller: accepted, but
        flagged _legacy_response so the dispatcher can warn.

        Args:
            timeout: Maximum time to wait in seconds
            request_id: id sent in the command; None disables matching (tests)

        Returns:
            Response dictionary or error dict if timeout
        """
        start_time = time.time()
        poll_interval = 0.02  # 20ms between checks

        while time.time() - start_time < timeout:
            if self._response_file.exists():
                try:
                    response_text = self._response_file.read_text()
                    response = json.loads(response_text)

                    rid = response.get("request_id")
                    if request_id is not None and rid is not None and rid != request_id:
                        # Stale response (wrong command) — do NOT consume it.
                        time.sleep(poll_interval)
                        continue
                    # Match (or legacy no-id): consume.
                    try:
                        self._response_file.unlink()
                    except Exception:
                        pass
                    if rid is None:
                        response["_legacy_response"] = True
                    if response.get("protocol_version") not in (None, PROTOCOL_VERSION):
                        response["_protocol_mismatch"] = response.get("protocol_version")
                    return response
                except json.JSONDecodeError as e:
                    return {"success": False, "error": f"Invalid JSON in response: {e}"}
                except Exception as e:
                    return {"success": False, "error": f"Failed to read response: {e}"}

            time.sleep(poll_interval)

        return {
            "success": False,
            "error": (
                f"Timeout waiting for FL Studio response after {timeout}s. "
                "Make sure FL Studio is running and the MCP controller is enabled "
                "in MIDI Settings. (A modal dialog open in FL also blocks the "
                "controller.)"
            ),
        }

    def get_status(self) -> dict[str, Any]:
        """Get connection status information."""
        try:
            import mido
            output_ports = mido.get_output_names()
        except Exception:
            output_ports = []

        return {
            "connected": self.is_connected,
            "port_name": self._port_name,
            "available_ports": output_ports,
            "command_file": str(self._command_file),
            "response_file": str(self._response_file),
            "error": self._error,
        }


# Global connection instance
_connection: MIDIConnection | None = None


def get_connection() -> MIDIConnection:
    """Get the global MIDI connection instance."""
    global _connection
    if _connection is None:
        _connection = MIDIConnection()
    return _connection


def reset_connection() -> None:
    """Reset the connection state to allow reconnection attempts."""
    global _connection
    if _connection is not None:
        _connection.disconnect()
        _connection = None
