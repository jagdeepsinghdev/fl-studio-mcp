"""Tests for the generic Edison script (0MCP-Workbench.pyscript) and its host
bridge. The request-baked pyscript is executed against a fake `enveditor`
module (EditorSample + Utils.ShowMessage capture); nothing touches FL."""

from __future__ import annotations

import sys
import types

import pytest

from fl_studio_mcp.utils import edison_bridge as eb


class _Region:
    def __init__(self, name, start, end):
        self.Name, self.SampleStart, self.SampleEnd = name, start, end


class _Sample:
    def __init__(self, length=44100 * 10, sr=44100):
        self.Length, self.SampleRate, self.NumChans = length, sr, 2
        self.regions: list[_Region] = []
        self.loaded = None

    @property
    def RegionCount(self):
        return len(self.regions)

    def GetRegion(self, i):
        return self.regions[i]

    def AddRegion(self, name, start, end):
        self.regions.append(_Region(name, start, end))
        return len(self.regions) - 1

    def DeleteRegion(self, i):
        del self.regions[i]

    def LoadFromFile(self, path):
        self.loaded = path
        self.Length = 44100 * 20


@pytest.fixture
def edison(monkeypatch):
    sample = _Sample()
    shown: list[str] = []
    utils = types.SimpleNamespace(ShowMessage=shown.append)
    monkeypatch.setitem(sys.modules, "enveditor", types.SimpleNamespace(
        EditorSample=sample, Utils=utils, __all__=["EditorSample", "Utils"]))
    return sample, shown


def _run(src):
    exec(compile(src, "0MCP-Workbench", "exec"), {"__name__": "__main__"})


def test_script_loads_clears_and_adds_regions(edison, tmp_path):
    sample, shown = edison
    wav = tmp_path / "clip true null.wav"     # literal-safety: odd path words
    wav.write_bytes(b"RIFF")
    sample.AddRegion("old", 0, 10)
    rid, src = eb.build_script(
        load=str(wav), clear_regions=True,
        regions=[{"name": "kick 1", "start_s": 1.0, "end_s": 1.25},
                 {"name": "hat 1", "start_s": 19.99, "end_s": 30.0},
                 {"name": "late", "start_s": 99.0, "end_s": 99.1}])
    _run(src)
    assert sample.loaded == str(wav.resolve())
    assert [r.Name for r in sample.regions] == ["kick 1", "hat 1"]
    assert (sample.regions[0].SampleStart, sample.regions[0].SampleEnd) == (44100, 55125)
    assert sample.regions[1].SampleEnd == sample.Length - 1   # clamped
    reply = eb.parse_reply(shown[-1])
    assert reply == {"id": rid, "ok": 1, "loaded": 1, "deleted": 1, "added": 2,
                     "count": 2, "len": 44100 * 20, "err": "-"}


def test_template_runs_as_a_noop(edison):
    sample, shown = edison
    _run(eb.SCRIPT_SRC.read_text())
    assert sample.loaded is None and sample.regions == []
    assert eb.parse_reply(shown[-1])["ok"] == 1


def test_script_reports_errors_instead_of_raising(edison, monkeypatch):
    sample, shown = edison
    monkeypatch.setattr(sample, "LoadFromFile",
                        lambda p: (_ for _ in ()).throw(IOError("bad wav")))
    rid, src = eb.build_script(load=eb.SCRIPT_SRC)   # any existing file
    _run(src)
    reply = eb.parse_reply(shown[-1])
    assert reply["ok"] == 0 and "bad_wav" in reply["err"]


def test_parse_reply_survives_ocr_line_wraps():
    text = "Some header\nMCP-EDISON id=ab12 ok=1 loaded=1\ndeleted=0 added=331 count=331 len=8088000 err=-"
    r = eb.parse_reply(text)
    assert r["added"] == 331 and r["id"] == "ab12" and r["err"] == "-"
    assert eb.parse_reply("no reply here") is None


def test_regions_from_hits_names_per_type_and_caps_length():
    hits = [{"t": 1.0, "type": "kick"}, {"t": 1.1, "type": "hat"},
            {"t": 2.0, "type": "kick"}, {"t": None}]
    r = eb.regions_from_hits(hits, max_ms=300)
    assert [x["name"] for x in r] == ["kick 1", "hat 1", "kick 2"]
    assert r[0]["end_s"] == pytest.approx(1.1)      # gap to next onset
    assert r[1]["end_s"] == pytest.approx(1.4)      # max_ms cap
    assert r[2]["end_s"] == pytest.approx(2.3)


def test_build_script_rejects_missing_clip(tmp_path):
    with pytest.raises(FileNotFoundError):
        eb.build_script(load=str(tmp_path / "x.wav"))


def test_install_writes_into_workbench(tmp_path):
    rid, src = eb.build_script()
    dest = eb.install(src, dest_dir=tmp_path / "Workbench")
    assert dest.name == "0MCP-Workbench.pyscript"
    assert rid in dest.read_text()


def _wav_with_regions(path, regions):
    import struct
    fmt = struct.pack("<HHIIHH", 1, 1, 44100, 88200, 2, 16)
    data = b"\0\0" * 100
    cue = struct.pack("<I", len(regions)) + b"".join(
        struct.pack("<II4sIII", k + 1, 0, b"data", 0, 0, start)
        for k, (_, start) in enumerate(regions))
    adtl = b"adtl"
    for k, (name, _) in enumerate(regions):
        txt = name.encode() + b"\0"
        sub = struct.pack("<I", k + 1) + txt
        adtl += b"labl" + struct.pack("<I", len(sub)) + sub + (b"\0" if len(sub) & 1 else b"")

    def chunk(cid, body):
        return cid + struct.pack("<I", len(body)) + body + (b"\0" if len(body) & 1 else b"")

    body = b"WAVE" + chunk(b"fmt ", fmt) + chunk(b"data", data) + chunk(b"cue ", cue) + chunk(b"LIST", adtl)
    path.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)


def test_wav_regions_reads_cues_and_labels(tmp_path):
    p = tmp_path / "drums_2.wav"
    _wav_with_regions(p, [("snare 1", 900), ("hat 1", 10), ("kick 1", 50)])
    got = eb.wav_regions(p)
    assert [r["name"] for r in got] == ["hat 1", "kick 1", "snare 1"]
    assert [r["start"] for r in got] == [10, 50, 900]


def test_wav_regions_rejects_non_wav(tmp_path):
    p = tmp_path / "x.wav"
    p.write_bytes(b"nope")
    with pytest.raises(ValueError):
        eb.wav_regions(p)


def test_newest_sliced_audio(tmp_path):
    import os
    a, b = tmp_path / "a.wav", tmp_path / "b.wav"
    a.write_bytes(b"x"); b.write_bytes(b"x")
    os.utime(a, (100, 100)); os.utime(b, (200, 200))
    assert eb.newest_sliced_audio(150, folder=tmp_path) == b
    assert eb.newest_sliced_audio(300, folder=tmp_path) is None
