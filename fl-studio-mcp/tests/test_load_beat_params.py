"""S2.3: per-step parameters from generated variations (P4's setStepParameter).

`_apply_step_params` (exec_python) is the S2.3 writer: a generated variation's
part spec carries arrays aligned to its pattern — `velocities` / `shifts` /
`repeats` — and each non-zero value on an ACTIVE step becomes one
`channels.setStepParameter` call (pVelocity=1, pShift=7, pRepeat=8; P4: a
step param only takes effect on an active step). Plain presets (no arrays)
must be a no-op.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# S2.3: the per-step param writer lives in preset_v2 (the always-on fl_preset
# tool); the legacy exec_python re-export was retired with R5 (2026-10-01).
from fl_studio_mcp.tools.preset_v2 import _apply_step_params  # noqa: E402


class _RecConn:
    """Fake connection: records every send_command call."""

    def __init__(self):
        self.calls = []

    def send_command(self, action, params, timeout=None):
        self.calls.append((action, dict(params)))
        return {"success": True}


# A 16-step part: hits at 0, 4, 8, 12; ghost-ish velocities on 4/12.
SPEC = {
    "name": "808 Kick",
    "pattern": [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0],
    "velocities": [120, 0, 0, 0, 64, 0, 0, 0, 110, 0, 0, 0, 70, 0, 0, 0],
    "shifts": [0, 0, 0, 0, 8, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    "repeats": [0, 0, 0, 0, 0, 0, 0, 0, 3, 0, 0, 0, 0, 0, 0, 0],
}


class TestApplyStepParams(unittest.TestCase):
    def _run(self, spec, pattern=None):
        conn = _RecConn()
        counts, errors = _apply_step_params(
            conn, 7, pattern or [bool(x) for x in spec["pattern"]], spec, 3)
        return sum(counts.values()), conn.calls

    def test_writes_only_active_nonzero_steps(self):
        n, calls = self._run(SPEC)
        # active steps 0, 4, 8, 12: velocities 120/64/110/70 -> 4 vel writes;
        # shift 8 on step 4 -> 1; repeat 3 on step 8 -> 1 pRepeat (v45 const 8,
        # known issue #1). Total 6.
        self.assertEqual(n, 6)
        params = [c for c in calls if c[0] == "channels.setStepParameter"]
        self.assertEqual(len(params), 6)
        (act, p) = params[0]
        self.assertEqual(p, {"channel": 7, "step": 0, "param": "pVelocity",
                             "value": 120, "target_pattern": 3})
        by = {(p["step"], p["param"]): p["value"] for _, p in params}
        self.assertEqual(by, {(0, "pVelocity"): 120, (4, "pVelocity"): 64,
                              (4, "pShift"): 8, (8, "pVelocity"): 110,
                              (8, "pRepeat"): 3, (12, "pVelocity"): 70})

    def test_plain_preset_is_noop(self):
        spec = {"name": "808 Kick", "pattern": [1, 0, 1, 0] * 4}
        n, calls = self._run(spec)
        self.assertEqual(n, 0)
        self.assertEqual(calls, [])

    def test_skips_when_step_inactive(self):
        # velocity array says 127 on step 0 but the grid bit is off there
        spec = dict(SPEC)
        spec["pattern"] = [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0]
        n, calls = self._run(spec)
        by = {(p["step"], p["param"]) for _, p in calls}
        self.assertNotIn((0, "pVelocity"), by)
        # the remaining active steps (4, 12) still get their params
        self.assertEqual(n, 3)  # vel 4, vel 12, shift 4 (step 8 is inactive now)

    def test_zero_values_skipped(self):
        spec = dict(SPEC)
        spec["shifts"] = [0] * 16
        spec["repeats"] = [0] * 16
        n, calls = self._run(spec)
        self.assertEqual(n, 4)  # velocities only
        self.assertTrue(all(p["param"] == "pVelocity" for _, p in calls))

    def test_short_array_is_safe(self):
        spec = {"name": "hat", "pattern": [1, 1, 1, 1] * 4,
                "velocities": [100, 90]}  # shorter than the pattern
        n, calls = self._run(spec)
        self.assertEqual(n, 2)
        self.assertEqual({p["step"] for _, p in calls}, {0, 1})


if __name__ == "__main__":
    unittest.main()
