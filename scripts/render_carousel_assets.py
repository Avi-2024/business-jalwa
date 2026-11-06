#!/usr/bin/env python3
"""Render five authored 4:5 SVG carousel slides as public JPEG assets."""
from __future__ import annotations
import argparse
from io import BytesIO
from pathlib import Path
import re
import cairosvg
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
KEY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-post-\d{3}$")
EXPECTED = [f"slide-{n:02d}" for n in range(1, 6)]
SIZE = (1080, 1350)

def verify(key: str) -> None:
    target = ROOT / "assets" / "approved" / key
    actual = sorted(p.stem for p in target.glob("slide-*.jpg"))
    if actual != EXPECTED:
        raise SystemExit(f"{key}: expected exactly five JPEGs, found {actual}")
    for stem in EXPECTED:
        path = target / f"{stem}.jpg"
        with Image.open(path) as image:
            image.load()
            if image.format != "JPEG" or image.size != SIZE:
                raise SystemExit(f"{path}: expected JPEG {SIZE}, got {image.format} {image.size}")
    print(f"Verified {key}: five 1080x1350 JPEG slides")

def render(key: str) -> None:
    source = ROOT / "assets" / "source" / key
    expected_files = [source / f"{stem}.svg" for stem in EXPECTED]
    actual_files = sorted(source.glob("slide-*.svg"))
    if actual_files != expected_files:
        raise SystemExit(f"{key}: source must contain exactly slide-01.svg through slide-05.svg")
    target = ROOT / "assets" / "approved" / key
    target.mkdir(parents=True, exist_ok=True)
    for svg_path in expected_files:
        svg_text = svg_path.read_text(encoding="utf-8")
        if 'width="1080"' not in svg_text or 'height="1350"' not in svg_text:
            raise SystemExit(f"{svg_path}: source canvas must be 1080x1350 (4:5)")
        png_bytes = cairosvg.svg2png(bytestring=svg_text.encode("utf-8"), output_width=SIZE[0], output_height=SIZE[1])
        with Image.open(BytesIO(png_bytes)) as rendered:
            image = rendered.convert("RGB")
        if image.size != SIZE:
            raise SystemExit(f"{svg_path}: rendered unexpected size {image.size}")
        image.save(target / f"{svg_path.stem}.jpg", format="JPEG", quality=92, optimize=True, progressive=True, subsampling=1)
    verify(key)

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("post_key", help="Queue asset key, e.g. 2026-11-20-post-088")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if not KEY_RE.fullmatch(args.post_key):
        raise SystemExit("post_key must match YYYY-MM-DD-post-NNN")
    verify(args.post_key) if args.verify_only else render(args.post_key)

if __name__ == "__main__":
    main()
