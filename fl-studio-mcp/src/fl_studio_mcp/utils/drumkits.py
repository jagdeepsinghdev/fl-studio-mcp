"""Per-genre drum kits from FL Studio's bundled one-shots (Sampler + WAV, no default 808 kit).

Two halves:
  OFFLINE (no FL): `scan()` measures every bundled drum one-shot (length, brightness, low-end share)
  and caches it; `build_kit(genre)` ranks candidates per role against the genre's PROFILE (sound
  targets + preferred sample families + name keywords) and returns a kit dict, written to
  presets/kits/<genre>.json by scripts/build_drumkits.py (paths only, never audio: rule 9).
  ONLINE: `materialize(kit)` converts the picks to WAV under .generated/audio/kits/<genre>/ (FL's
  Open panel cannot resolve files inside the app bundle, and ModeAudio ships .wv); fl_genre load_kit
  loads them into named Sampler channels.

The picks are measured + rule-based, NOT auditioned (skills/README.md rule 9): the owner's ears
decide; `variant=N` takes the next-best candidates. Family -> genre hints are inferred from the
ModeAudio pack names (HouseGen, Downstream, Power, ...), not documented by Image-Line.
"""
from __future__ import annotations

import json
import math
import re
import subprocess
from pathlib import Path

import numpy as np

PACKS = Path("/Applications/FL Studio 2026.app/Contents/Resources/FL/Data/Patches/Packs")
ROOT = Path(__file__).resolve().parents[3]                    # fl-studio-mcp/
KITS_DIR = ROOT / "presets" / "kits"
GEN_DIR = ROOT / ".generated"
CACHE = GEN_DIR / "drumkits" / "features.json"
SR = 22050

# role -> (folders under PACKS, include-name regex, exclude-name regex)
SOURCES = {
    "kick": (["Drums/Kicks", "Drums (ModeAudio)/Kicks"], r"kick", r"$^"),
    "snare": (["Drums/Snares", "Drums (ModeAudio)/Snares"], r"snare|snr", r"rim"),
    "rim": (["Drums/Snares", "Drums (ModeAudio)/Rims"], r"rim", r"$^"),
    "clap": (["Drums (ModeAudio)/Claps", "Drums/Percussion"], r"clap", r"$^"),
    "hat": (["Drums/Hats", "Drums (ModeAudio)/Hi Hats"], r"chat|\bch\b|\bch \d|hat", r"ohat|\boh\b|open"),
    "ohat": (["Drums/Hats", "Drums (ModeAudio)/Hi Hats"], r"ohat|\boh\b|open", r"$^"),
    "shaker": (["Drums (ModeAudio)/Shakers", "Drums/Percussion"], r"shak|egg|cabasa|tamb", r"$^"),
    "perc": (["Drums (ModeAudio)/Percussion", "Drums/Percussion"], r".", r"clap|shak|egg"),
}
# The FL default template kit ("808 Kick", "808 Clap", "808 HiHat", "808 Snare") is never picked:
# owner 2026-10-11 "must not use default drum kit".
DEFAULT_KIT = re.compile(r"^808 (kick|clap|snare|ch|oh|hihat)", re.I)

# Sound targets per role "flavour", calibrated on the measured spread of the 1,487 decodable files
# (2026-10-11): dur = seconds to -40 dB, cen = spectral centroid Hz, click = share of the first 20 ms
# above 1 kHz (kicks only: their centroid is all sub, 45-120 Hz). Convention, not auditioned.
FLAVOURS = {
    "kick_sub": {"dur": 0.80, "click": 0.0005},   # 808-style long sub kick
    "kick_round": {"dur": 0.28, "click": 0.002},  # soft, round (afro / r&b / pop)
    "kick_dusty": {"dur": 0.26, "click": 0.004},  # lo-fi / boom-bap
    "kick_punch": {"dur": 0.35, "click": 0.012},  # four-on-the-floor, audible beater
    "kick_tight": {"dur": 0.20, "click": 0.030},  # dnb
    "snare_crack": {"dur": 0.30, "cen": 3000},
    "snare_soft": {"dur": 0.25, "cen": 1800},
    "snare_long": {"dur": 0.50, "cen": 2500},
    "rim": {"dur": 0.10, "cen": 1100},
    "clap": {"dur": 0.30, "cen": 2200},
    "hat_tight": {"dur": 0.05, "cen": 7500},
    "hat_soft": {"dur": 0.09, "cen": 5500},
    "ohat": {"dur": 0.45, "cen": 6500},
    "shaker": {"dur": 0.20, "cen": 5000},
    "perc": {"dur": 0.25, "cen": 1000},
}

# genre -> roles: {role: (flavour, part-for-beat-presets | None, preferred families, name keywords)}
# part = which beat-preset part (kick/snare/clap/hat) this channel plays; None = extra role whose
# steps come from the kit's own "pattern".
_URBAN = ("Power", "Undercover", "MA")
PROFILES: dict[str, dict] = {
    "trap": {"kick": ("kick_sub", "kick", _URBAN, ()), "snare": ("snare_crack", "snare", _URBAN, ()),
             "clap": ("clap", "clap", _URBAN, ()), "hat": ("hat_tight", "hat", _URBAN, ()),
             "ohat": ("ohat", None, _URBAN, ())},
    "drill": {"kick": ("kick_sub", "kick", _URBAN, ()), "snare": ("snare_crack", "snare", _URBAN, ()),
              "clap": ("clap", "clap", _URBAN, ()), "hat": ("hat_tight", "hat", _URBAN, ()),
              "perc": ("perc", None, ("Fracture", "MA"), ("perc",))},
    "phonk": {"kick": ("kick_sub", "kick", ("Power", "Volt"), ()), "snare": ("snare_crack", "snare", ("Power",), ()),
              "clap": ("clap", "clap", ("Power", "Volt"), ()), "hat": ("hat_tight", "hat", ("Power",), ()),
              "perc": ("perc", None, ("Attack", "MA"), ("cowbell", "analogbell", "bell"))},
    "hip-hop": {"kick": ("kick_dusty", "kick", ("Undercover", "Power", "MA"), ()),
                "snare": ("snare_crack", "snare", ("Undercover", "Power", "MA"), ()),
                "clap": ("clap", "clap", _URBAN, ()), "hat": ("hat_soft", "hat", ("Downstream", "MA"), ())},
    "boom-bap": {"kick": ("kick_dusty", "kick", ("Grv", "FPC", "MA"), ()),
                 "snare": ("snare_crack", "snare", ("Grv", "FPC", "MA"), ()),
                 "clap": ("clap", "clap", ("MA",), ()), "hat": ("hat_soft", "hat", ("Grv", "FPC", "Downstream"), ())},
    "lofi": {"kick": ("kick_dusty", "kick", ("Downstream", "Grv", "MA"), ()),
             "snare": ("snare_soft", "snare", ("Downstream", "Grv"), ()),
             "rim": ("rim", None, ("Downstream", "MA"), ()), "hat": ("hat_soft", "hat", ("Downstream",), ()),
             "shaker": ("shaker", None, ("MA", "Attack"), ())},
    "rnb": {"kick": ("kick_round", "kick", ("Undercover", "Downstream", "MA"), ()),
            "snare": ("snare_soft", "snare", ("Undercover", "Downstream", "MA"), ()),
            "clap": ("clap", "clap", ("Undercover", "MA"), ()), "hat": ("hat_soft", "hat", ("Downstream", "MA"), ()),
            "perc": ("perc", None, ("Attack", "MA"), ("snap",))},
    "pop": {"kick": ("kick_round", "kick", ("Attack", "Hyper"), ()), "snare": ("snare_crack", "snare", ("Attack", "Hyper"), ()),
            "clap": ("clap", "clap", ("Attack", "Hyper"), ()), "hat": ("hat_soft", "hat", ("Attack", "Hyper"), ()),
            "shaker": ("shaker", None, ("Attack", "Hyper"), ())},
    "afrobeats": {"kick": ("kick_round", "kick", ("Attack", "MA", "Undercover"), ()),
                  "snare": ("rim", "snare", ("Fracture", "Volt", "MA"), ()),       # rim plays the snare part
                  "clap": ("clap", "clap", ("Attack", "MA"), ()), "hat": ("hat_soft", "hat", ("Attack", "MA"), ()),
                  "shaker": ("shaker", None, ("Attack", "HouseGen", "MA"), ()),
                  "perc": ("perc", None, ("Collider", "FPC", "808"), ("conga", "talker", "wood", "clave"))},
    "reggaeton": {"kick": ("kick_round", "kick", ("Attack", "Power"), ()), "snare": ("snare_crack", "snare", ("Attack", "Power"), ()),
                  "hat": ("hat_soft", "hat", ("Attack",), ()),
                  "perc": ("perc", None, ("Attack", "Collider"), ("timbale", "clave", "cowbell"))},
    "punjabi": {"kick": ("kick_round", "kick", ("Power", "MA"), ()), "snare": ("snare_crack", "snare", ("Power", "MA"), ()),
                "clap": ("clap", "clap", ("Power", "MA"), ()), "hat": ("hat_soft", "hat", ("MA",), ()),
                "perc": ("perc", None, ("Collider", "FPC"), ("tamb", "wood", "clave"))},
    "house": {"kick": ("kick_punch", "kick", ("HouseGen",), ()), "snare": ("snare_soft", "snare", ("HouseGen",), ()),
              "clap": ("clap", "clap", ("HouseGen",), ()), "hat": ("hat_tight", "hat", ("HouseGen",), ()),
              "ohat": ("ohat", None, ("HouseGen",), ()), "shaker": ("shaker", None, ("HouseGen",), ())},
    "techno": {"kick": ("kick_punch", "kick", ("Volt", "909", "HouseGen"), ()), "snare": ("snare_crack", "snare", ("Volt", "909"), ()),
               "clap": ("clap", "clap", ("Volt",), ()), "hat": ("hat_tight", "hat", ("Volt", "909"), ()),
               "ohat": ("ohat", None, ("Volt", "909"), ())},
    "future-bass": {"kick": ("kick_round", "kick", ("Hyper", "Attack"), ()), "snare": ("snare_long", "snare", ("Hyper", "Attack"), ()),
                    "clap": ("clap", "clap", ("Hyper", "Attack"), ()), "hat": ("hat_tight", "hat", ("Hyper",), ())},
    "drum-and-bass": {"kick": ("kick_tight", "kick", ("Fracture", "Collider"), ()),
                      "snare": ("snare_crack", "snare", ("Fracture", "Collider"), ()),
                      "clap": ("clap", "clap", ("Fracture",), ()), "hat": ("hat_tight", "hat", ("Fracture", "Collider"), ()),
                      "shaker": ("shaker", None, ("Collider", "MA"), ())},
    "dubstep": {"kick": ("kick_punch", "kick", ("Volt", "Fracture"), ()), "snare": ("snare_long", "snare", ("Volt", "Fracture"), ()),
                "clap": ("clap", "clap", ("Volt",), ()), "hat": ("hat_tight", "hat", ("Volt", "Fracture"), ())},
}

# Steps (16 per bar) for the extra roles (part None). Convention, not auditioned.
EXTRA_PATTERNS = {
    "shaker": [1, 1, 1, 1] * 4,
    "ohat": [0, 0, 1, 0] * 4,
    "rim": [0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0],
    "perc": {"afrobeats": [0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 1, 0, 1],
             "reggaeton": [0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 1, 0],
             "punjabi": [0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 1],
             "drill": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0],
             "phonk": [1, 0, 0, 1, 0, 0, 1, 0, 1, 0, 0, 1, 0, 0, 1, 0],
             "rnb": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0]},
}
# Channel names: "<Role> <GENRE tag>" so beat presets can be pointed at them (kit-aware resolver).
ROLE_LABEL = {"kick": "Kick", "snare": "Snare", "rim": "Rim", "clap": "Clap", "hat": "Hat",
              "ohat": "Open Hat", "shaker": "Shaker", "perc": "Perc"}


GENRE_TAG = {"afrobeats": "AFRO", "boom-bap": "BOOMBAP", "drill": "DRILL", "drum-and-bass": "DNB",
             "dubstep": "DUBSTEP", "future-bass": "FBASS", "hip-hop": "HIPHOP", "house": "HOUSE",
             "lofi": "LOFI", "phonk": "PHONK", "pop": "POP", "punjabi": "PUNJABI",
             "reggaeton": "REGGAETON", "rnb": "RNB", "techno": "TECHNO", "trap": "TRAP"}


def channel_name(genre: str, role: str) -> str:
    return f"{ROLE_LABEL[role]} {GENRE_TAG.get(genre, genre.upper()[:6])}"


# ---------------------------------------------------------------- offline analysis
def _decode(path: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32)


def features(path: Path) -> dict | None:
    try:
        y = _decode(path)
    except subprocess.CalledProcessError:
        return None
    if y.size < 64 or not np.any(y):
        return None
    peak = float(np.max(np.abs(y)))
    env = np.abs(y)
    above = np.nonzero(env > peak * 10 ** (-40 / 20))[0]
    dur = float(above[-1] / SR) if above.size else 0.0
    seg = y[: max(256, int(min(dur, 1.0) * SR))]
    spec = np.abs(np.fft.rfft(seg * np.hanning(seg.size))) ** 2
    freqs = np.fft.rfftfreq(seg.size, 1 / SR)
    tot = float(spec.sum()) or 1.0
    # click: share of the first 20 ms above 1 kHz (a kick's beater/transient; centroid alone is all sub)
    a0 = int(np.argmax(env > peak * 0.1))          # onset, not the (later) sub peak
    head = y[a0: a0 + int(0.02 * SR)]
    head = head if head.size >= 64 else y[:441]
    hs = np.abs(np.fft.rfft(head * np.hanning(head.size))) ** 2
    hf = np.fft.rfftfreq(head.size, 1 / SR)
    return {"dur": round(dur, 3), "cen": round(float((freqs * spec).sum() / tot), 1),
            "low": round(float(spec[freqs < 120].sum() / tot), 3),
            "click": round(float(hs[hf > 1000].sum() / (float(hs.sum()) or 1.0)), 4),
            "peak": round(peak, 3)}


def scan(refresh: bool = False) -> dict[str, dict]:
    """{relative path: features} for every candidate file (cached in .generated/)."""
    cache = {} if refresh or not CACHE.is_file() else json.loads(CACHE.read_text())
    folders = sorted({f for fs, _, _ in SOURCES.values() for f in fs})
    changed = False
    for folder in folders:
        for p in sorted((PACKS / folder).glob("*")):
            if p.suffix.lower() not in (".wav", ".wv"):
                continue
            rel = str(p.relative_to(PACKS))
            if rel not in cache:
                cache[rel] = features(p)
                changed = True
    if changed:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(cache, indent=0, sort_keys=True))
    return cache


def family(rel: str) -> str:
    """ModeAudio family (first word: Attack, Power, ...) or the FL pack prefix (Grv, FPC, 909)."""
    return Path(rel).stem.split(" ")[0]


def candidates(role: str, feats: dict[str, dict]) -> list[str]:
    folders, inc, exc = SOURCES[role]
    out = []
    for rel, f in feats.items():
        if f is None or not any(rel.startswith(fo + "/") for fo in folders):
            continue
        name = Path(rel).stem.lower()
        if DEFAULT_KIT.match(Path(rel).stem) or not re.search(inc, name) or re.search(exc, name):
            continue
        out.append(rel)
    return out


def score(f: dict, target: dict, fam: str, families: tuple, keywords: tuple, name: str) -> float:
    """Lower = better: distance to the flavour + family / keyword bonuses."""
    d = abs(math.log((f["dur"] + 0.02) / (target["dur"] + 0.02)))
    if "click" in target:
        d *= 1.5                   # a kick's length is its character (808 sub vs short thump)
        d += 0.5 * abs(math.log((f.get("click", 0) + 0.0005) / (target["click"] + 0.0005)))
    else:
        d += abs(math.log((f["cen"] + 50) / (target["cen"] + 50)))
    if fam in families:
        d -= 0.8 * (1.0 - 0.15 * families.index(fam))
    if keywords and any(k in name for k in keywords):
        d -= 2.0                   # named instrument wanted (conga, timbale, snap...)
    if f["peak"] < 0.1:            # nearly silent file
        d += 2.0
    return d


def build_kit(genre: str, variant: int = 0, feats: dict | None = None,
              used: dict[str, int] | None = None) -> dict:
    """`used` (file -> times picked by other kits) adds 0.35 per use, so genres don't all share
    one snare; scripts/build_drumkits.py passes it while building every kit in turn."""
    gid = genre.strip().lower().replace(" ", "-")
    if gid not in PROFILES:
        raise ValueError(f"no drum profile for {genre!r}; have {sorted(PROFILES)}")
    feats = feats if feats is not None else scan()
    roles = {}
    for role, (flav, part, fams, kws) in PROFILES[gid].items():
        src_role = "rim" if flav == "rim" else role
        cands = candidates(src_role, feats)
        used = used if used is not None else {}
        ranked = sorted(cands, key=lambda r: (score(feats[r], FLAVOURS[flav], family(r), fams, kws,
                                                     Path(r).stem.lower())
                                               + 0.35 * used.get(r, 0), r))
        if not ranked:
            continue
        pick = ranked[min(variant, len(ranked) - 1)]
        used[pick] = used.get(pick, 0) + 1
        entry = {"file": pick, "flavour": flav, "part": part, "channel": channel_name(gid, role),
                 "features": feats[pick], "alternatives": ranked[variant + 1: variant + 4]}
        if part is None:
            pat = EXTRA_PATTERNS.get(role)
            entry["pattern"] = pat.get(gid, [0] * 16) if isinstance(pat, dict) else pat
        roles[role] = entry
    return {"id": gid, "variant": variant, "source": "FL Studio bundled packs (Packs/Drums, "
            "Packs/Drums (ModeAudio)); the default 808 kit is excluded",
            "status": "auto-picked by measured features + genre rules; convention, not auditioned",
            "roles": roles}


def load_kit_file(genre: str) -> dict:
    f = KITS_DIR / f"{genre.strip().lower().replace(' ', '-')}.json"
    if not f.is_file():
        raise ValueError(f"no kit {f.name}; run scripts/build_drumkits.py")
    return json.loads(f.read_text())


def materialize(kit: dict) -> dict[str, str]:
    """role -> absolute WAV path under .generated/audio/kits/<id>[-vN]/ (converted once)."""
    tag = kit["id"] + (f"-v{kit['variant']}" if kit.get("variant") else "")
    out_dir = GEN_DIR / "audio" / "kits" / tag
    out_dir.mkdir(parents=True, exist_ok=True)
    out = {}
    for role, e in kit["roles"].items():
        src = PACKS / e["file"]
        dst = out_dir / f"{ROLE_LABEL[role].replace(' ', '')} {Path(e['file']).stem}.wav"
        if not dst.is_file():
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-ar", "44100",
                            "-c:a", "pcm_s16le", str(dst)], check=True)
        out[role] = str(dst)
    return out
