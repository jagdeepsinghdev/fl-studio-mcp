"""Host side of the generic Edison script (scripts/0MCP-Workbench.pyscript).

Edison's embedded Python has no file I/O (open() raises "io.FileIO returned
NULL"; live probe 2026-10-01), so there is no JSON mailbox. Instead the
request is baked into the fixed-name script before each run (the menu target
never changes) and the script replies with one Utils.ShowMessage line,
"MCP-EDISON id=… ok=1 added=… count=…", which the host OCRs (parse_reply)
and dismisses.
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

SCRIPT_NAME = "0MCP-Workbench"
WORKBENCH = (Path.home() / "Documents" / "Image-Line" / "FL Studio"
             / "Settings" / "Audio scripts" / "Workbench")
SCRIPT_SRC = (Path(__file__).resolve().parents[3] / "scripts"
              / f"{SCRIPT_NAME}.pyscript")
_REQUEST_LINE = re.compile(r"^REQUEST = .*# MCP-REQUEST.*$", re.M)
_REPLY = re.compile(r"MCP-EDISON\s+(.*)")


def build_script(load: str | None = None, regions: list[dict] | None = None,
                 clear_regions: bool = False,
                 template: Path = SCRIPT_SRC) -> tuple[str, str]:
    """Return (request_id, script source) with the request baked in."""
    if load is not None:
        p = Path(load).expanduser().resolve()
        if not p.is_file():
            raise FileNotFoundError(p)
        load = str(p)
    rid = uuid.uuid4().hex[:8]
    req = {"request_id": rid, "load": load, "clear_regions": clear_regions,
           "regions": regions or []}
    src = template.read_text()
    if not _REQUEST_LINE.search(src):
        raise ValueError(f"no '# MCP-REQUEST' line in {template}")
    lit = repr(req)  # a plain Python literal (str/bool/None/float/list/dict)
    src = _REQUEST_LINE.sub(lambda _: f"REQUEST = {lit}  # MCP-REQUEST", src)
    compile(src, SCRIPT_NAME, "exec")
    return rid, src


def install(src: str, dest_dir: Path = WORKBENCH) -> Path:
    """Write the (request-baked) script into Edison's Workbench folder."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{SCRIPT_NAME}.pyscript"
    dest.write_text(src, encoding="utf-8")
    return dest


def parse_reply(text: str) -> dict | None:
    """Parse the script's ShowMessage line (OCR text, possibly wrapped)."""
    m = _REPLY.search(" ".join(text.split()))
    if not m:
        return None
    out: dict = {}
    for tok in m.group(1).split():
        if "=" not in tok:
            continue
        k, v = tok.split("=", 1)
        numeric = k not in ("id", "err") and re.fullmatch(r"-?\d+", v)
        out[k] = int(v) if numeric else v
    return out


def regions_from_hits(hits: list[dict], max_ms: float = 300.0,
                      min_ms: float = 20.0) -> list[dict]:
    """One region per onset, named '<type> <n>' (per-type counter), lasting
    up to max_ms or the gap to the next onset, whichever is shorter."""
    hits = sorted((h for h in hits if h.get("t") is not None),
                  key=lambda h: float(h["t"]))
    counters: dict[str, int] = {}
    out = []
    for k, h in enumerate(hits):
        t = float(h["t"])
        dur = max_ms / 1000.0
        if k + 1 < len(hits):
            dur = min(dur, float(hits[k + 1]["t"]) - t)
        dur = max(min_ms / 1000.0, dur)
        kind = str(h.get("type") or "onset")
        counters[kind] = counters.get(kind, 0) + 1
        out.append({"name": f"{kind} {counters[kind]}",
                    "start_s": round(t, 6), "end_s": round(t + dur, 6)})
    return out


def regions_from_json(path: Path, max_ms: float = 300.0) -> list[dict]:
    """Regions from an analysis JSON with hits[] (drums.json)."""
    d = json.loads(Path(path).read_text())
    hits = d.get("hits")
    if not hits:
        raise ValueError(f"no hits[] in {path}")
    return regions_from_hits(hits, max_ms=max_ms)


SLICED_AUDIO = (Path.home() / "Documents" / "Image-Line" / "FL Studio"
                / "Audio" / "Sliced audio")


def wav_regions(path: Path) -> list[dict]:
    """Regions stored in a WAV by Edison: 'cue ' points (sample offsets)
    named by LIST/adtl 'labl' chunks. Edison's send-to-channel writes these
    into <FL>/Audio/Sliced audio/<name>_N.wav (live 2026-10-01: 331/331)."""
    import struct

    d = Path(path).read_bytes()
    if d[:4] != b"RIFF" or d[8:12] != b"WAVE":
        raise ValueError(f"not a RIFF/WAVE file: {path}")
    cues: dict[int, int] = {}
    names: dict[int, str] = {}
    i = 12
    while i + 8 <= len(d):
        cid, n = d[i:i + 4], struct.unpack("<I", d[i + 4:i + 8])[0]
        body = d[i + 8:i + 8 + n]
        if cid == b"cue ":
            for k in range(struct.unpack("<I", body[:4])[0]):
                rec = body[4 + 24 * k:4 + 24 * (k + 1)]
                cue_id, _pos, _chunk, _cs, _bs, offset = struct.unpack("<II4sIII", rec)
                cues[cue_id] = offset
        elif cid == b"LIST" and body[:4] == b"adtl":
            j = 4
            while j + 8 <= len(body):
                sid, sn = body[j:j + 4], struct.unpack("<I", body[j + 4:j + 8])[0]
                if sid == b"labl":
                    cue_id = struct.unpack("<I", body[j + 8:j + 12])[0]
                    names[cue_id] = body[j + 12:j + 8 + sn].split(b"\0")[0].decode("latin1")
                j += 8 + sn + (sn & 1)
        i += 8 + n + (n & 1)
    return [{"name": names.get(c, ""), "start": off}
            for c, off in sorted(cues.items(), key=lambda kv: kv[1])]


def newest_sliced_audio(since: float, folder: Path = SLICED_AUDIO) -> Path | None:
    """The newest .wav FL wrote to Sliced audio after `since` (epoch secs)."""
    if not folder.is_dir():
        return None
    wavs = [p for p in folder.glob("*.wav") if p.stat().st_mtime >= since]
    return max(wavs, key=lambda p: p.stat().st_mtime) if wavs else None
