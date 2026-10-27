"""Per-genre drum kits (utils/drumkits.py, presets/kits/*.json) + load_beat channel_map.

Pure logic only (no FL, no audio decode): ranking on synthetic features, the default-kit
exclusion, the committed kit files, and that a channel_map sends beat parts to the kit's
channels instead of the default "808 ..." ones.
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from fl_studio_mcp.tools import preset_v2 as pv2  # noqa: E402
from fl_studio_mcp.tools.genre_v2 import list_packs  # noqa: E402
from fl_studio_mcp.utils import drumkits as dk  # noqa: E402

K = "Drums (ModeAudio)/Kicks/"
FEATS = {
    K + "Power Kick 01.wv": {"dur": 0.85, "cen": 50, "low": 1.0, "click": 0.0005, "peak": 0.9},
    K + "Attack Kick 01.wv": {"dur": 0.28, "cen": 60, "low": 1.0, "click": 0.002, "peak": 0.9},
    K + "HouseGen Kick 01.wv": {"dur": 0.35, "cen": 70, "low": 0.9, "click": 0.012, "peak": 0.9},
    "Drums/Kicks/808 Kick.wav": {"dur": 0.80, "cen": 50, "low": 1.0, "click": 0.0005, "peak": 0.9},
    "Drums (ModeAudio)/Hi Hats/Attack Hat 01.wv": {"dur": 0.09, "cen": 5500, "low": 0, "click": 0.5, "peak": 0.8},
    "Drums (ModeAudio)/Hi Hats/Attack OHat 01.wv": {"dur": 0.45, "cen": 6500, "low": 0, "click": 0.5, "peak": 0.8},
    "Drums (ModeAudio)/Percussion/Collider Sub Conga 01.wv": {"dur": 0.2, "cen": 900, "low": 0.1, "click": 0.1, "peak": 0.8},
    "Drums (ModeAudio)/Percussion/MA Planetary Perc.wv": {"dur": 0.25, "cen": 1000, "low": 0.1, "click": 0.1, "peak": 0.8},
}


class TestPicking(unittest.TestCase):
    def test_flavour_decides_the_kick(self):
        trap = dk.build_kit("trap", feats=FEATS)["roles"]["kick"]["file"]
        afro = dk.build_kit("afrobeats", feats=FEATS)["roles"]["kick"]["file"]
        house = dk.build_kit("house", feats=FEATS)["roles"]["kick"]["file"]
        self.assertIn("Power Kick", trap)          # long sub
        self.assertIn("Attack Kick", afro)         # short, round
        self.assertIn("HouseGen Kick", house)      # beater click + family

    def test_default_808_kit_never_picked(self):
        for g in dk.PROFILES:
            files = [e["file"] for e in dk.build_kit(g, feats=FEATS)["roles"].values()]
            self.assertFalse(any("808 Kick" in f for f in files), g)

    def test_open_hats_are_not_closed_hats(self):
        self.assertEqual(dk.candidates("hat", FEATS), ["Drums (ModeAudio)/Hi Hats/Attack Hat 01.wv"])
        self.assertEqual(dk.candidates("ohat", FEATS), ["Drums (ModeAudio)/Hi Hats/Attack OHat 01.wv"])

    def test_keyword_wins_for_named_percussion(self):
        perc = dk.build_kit("afrobeats", feats=FEATS)["roles"]["perc"]
        self.assertIn("Conga", perc["file"])
        self.assertIsNone(perc["part"])
        self.assertEqual(len(perc["pattern"]), 16)

    def test_used_penalty_spreads_picks(self):
        used: dict[str, int] = {}
        a = dk.build_kit("pop", feats=FEATS, used=used)["roles"]["kick"]["file"]
        self.assertEqual(used[a], 1)

    def test_variant_takes_the_next_candidate(self):
        v0 = dk.build_kit("trap", feats=FEATS)["roles"]["kick"]["file"]
        v1 = dk.build_kit("trap", variant=1, feats=FEATS)["roles"]["kick"]["file"]
        self.assertNotEqual(v0, v1)


class TestCommittedKits(unittest.TestCase):
    def test_every_genre_pack_has_a_kit(self):
        for p in list_packs():
            kit = dk.load_kit_file(p["id"])
            self.assertEqual(kit["id"], p["id"])
            parts = {e["part"] for e in kit["roles"].values()}
            self.assertIn("kick", parts, p["id"])
            names = [e["channel"] for e in kit["roles"].values()]
            self.assertEqual(len(names), len(set(names)))
            for e in kit["roles"].values():
                self.assertFalse(dk.DEFAULT_KIT.match(os.path.basename(e["file"])), e["file"])
                self.assertIn("not auditioned", kit["status"])


class _Conn:
    def __init__(self):
        self.calls = []
        self.chans = [{"index": 0, "name": "808 Kick"}, {"index": 1, "name": "808 Snare"},
                      {"index": 7, "name": "Kick AFRO"}, {"index": 8, "name": "Snare AFRO"}]

    def send_command(self, action, params=None, timeout=None):
        self.calls.append((action, dict(params or {})))
        if action == "channels.getAll":
            return {"success": True, "channels": self.chans}
        return {"success": True}


class TestChannelMap(unittest.TestCase):
    def test_parts_go_to_the_kit_channels(self):
        conn = _Conn()
        with mock.patch.object(pv2, "get_connection", return_value=conn):
            r = pv2.load_beat("afrobeats", fill=False, auto_level=False,
                              channel_map={"kick": "Kick AFRO", "snare": "Snare AFRO"})
        writes = [p for a, p in conn.calls if a == "channels.setStepSequence" and any(p["pattern"])]
        self.assertEqual(sorted({p["channel"] for p in writes}), [7, 8])
        self.assertTrue(any("not in kit" in s for s in r["skipped"]))   # clap/hat: no fallback


if __name__ == "__main__":
    unittest.main()


class TestRackNameButton(unittest.TestCase):
    def test_zoomed_fallback_and_fuzzy_match(self):
        from collections import namedtuple

        from fl_studio_mcp.utils import fl_panels
        B = namedtuple("B", "x y w h text cx cy")
        garbled = [B(122, 382, 50, 10, "KCKATRU", 147, 384), B(117, 407, 60, 10, "Snare AFRO", 147, 414)]
        zoomed = [B(120, 380, 50, 10, "Kick AFR0", 147, 384), B(120, 470, 50, 10, "Hat AFRO", 148, 473)]
        with mock.patch.object(fl_panels.cm, "shot", return_value="x"), \
             mock.patch.object(fl_panels.cm, "ocr_boxes", return_value=garbled), \
             mock.patch.object(fl_panels.cm, "ocr_region", return_value=zoomed):
            self.assertEqual(fl_panels.rack_name_button("Snare AFRO").cy, 414)   # exact, full screen
            self.assertEqual(fl_panels.rack_name_button("Kick AFRO").cy, 384)    # fuzzy, zoomed
            self.assertEqual(fl_panels.rack_name_button("Hat AFRO").cy, 473)
            self.assertIsNone(fl_panels.rack_name_button("Perc AFRO"))
