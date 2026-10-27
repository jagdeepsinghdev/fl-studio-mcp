"""Build presets/kits/<genre>.json for every genre profile (offline, no FL needed).

    uv run python scripts/build_drumkits.py [--genre afrobeats] [--variant 1] [--refresh]

Measures FL's bundled drum one-shots once (cached in .generated/drumkits/features.json, ~1 min),
then picks each genre's kit by sound targets + sample family + name keywords
(src/fl_studio_mcp/utils/drumkits.py). Writes paths only, never audio. The default 808 kit is
never picked. Picks are measured + rule-based, not auditioned: listen, then rebuild with
--variant N (next-best candidates) or edit the JSON's "file" by hand (any role's
"alternatives" are the next three candidates).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fl_studio_mcp.utils import drumkits as dk  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--genre", help="one genre (default: all)")
    ap.add_argument("--variant", type=int, default=0)
    ap.add_argument("--refresh", action="store_true", help="re-measure every file")
    a = ap.parse_args()
    feats = dk.scan(refresh=a.refresh)
    print(f"{sum(v is not None for v in feats.values())} decodable one-shots "
          f"({sum(v is None for v in feats.values())} FL-compressed WAVs skipped)")
    dk.KITS_DIR.mkdir(parents=True, exist_ok=True)
    used: dict[str, int] = {}
    for g in [a.genre] if a.genre else sorted(dk.PROFILES):
        kit = dk.build_kit(g, a.variant, feats, used)
        (dk.KITS_DIR / f"{kit['id']}.json").write_text(json.dumps(kit, indent=2) + "\n")
        print(f"{kit['id']:13} " + "; ".join(f"{r}={Path(e['file']).stem}" for r, e in kit["roles"].items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
