#!/usr/bin/env python3
"""Generate ``seed_browser/icon.png`` — a 48×48 list-style placeholder.

Stdlib-only (struct + zlib) so the build doesn't need Pillow. Re-run
this whenever the design changes; the resulting PNG is committed.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

W, H = 48, 48
BG = (35, 47, 65, 255)
FG = (220, 230, 245, 255)
BAR_Y_RANGES = ((10, 14), (22, 26), (34, 38))
BAR_X_RANGE = (8, 40)
CORNER_RADIUS = 5


def _in_rounded_square(x: int, y: int) -> bool:
    r = CORNER_RADIUS
    for cx, cy in ((r, r), (W - r - 1, r), (r, H - r - 1), (W - r - 1, H - r - 1)):
        if abs(x - cx) >= r or abs(y - cy) >= r:
            continue
        # actually outside the rounded corner region (inside the rectangle
        # but outside the inscribed circle's quadrant)
        dx, dy = x - cx, y - cy
        if (
            (cx <= r and cy <= r and dx <= 0 and dy <= 0)
            or (cx >= W - r - 1 and cy <= r and dx >= 0 and dy <= 0)
            or (cx <= r and cy >= H - r - 1 and dx <= 0 and dy >= 0)
            or (cx >= W - r - 1 and cy >= H - r - 1 and dx >= 0 and dy >= 0)
        ):
            if dx * dx + dy * dy > r * r:
                return False
    return True


def _pixel(x: int, y: int) -> tuple[int, int, int, int]:
    if not _in_rounded_square(x, y):
        return (0, 0, 0, 0)
    x0, x1 = BAR_X_RANGE
    for y0, y1 in BAR_Y_RANGES:
        if x0 <= x < x1 and y0 <= y < y1:
            return FG
    return BG


def _chunk(tag: bytes, data: bytes) -> bytes:
    payload = tag + data
    return struct.pack(">I", len(data)) + payload + struct.pack(">I", zlib.crc32(payload))


def build_png() -> bytes:
    scanlines = bytearray()
    for y in range(H):
        scanlines.append(0)  # filter: None
        for x in range(W):
            scanlines.extend(_pixel(x, y))
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", W, H, 8, 6, 0, 0, 0)
    idat = zlib.compress(bytes(scanlines), level=9)
    return sig + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "seed_browser" / "icon.png"
    out.write_bytes(build_png())
    print(f"wrote {out} ({out.stat().st_size} bytes)")
