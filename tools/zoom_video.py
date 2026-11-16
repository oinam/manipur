"""Make the short zoom-in film for sharing: the whole valley down to Kangla, from the tiles.

Each frame is cut from the north-up view's finished pyramid, from the level just finer than
the frame needs, so nothing is captured from a screen and the film is the same every run.
It eases from the whole valley into Kangla at full size, holds, and is encoded to H.264 with
ffmpeg. Writes web/public/zoom.mp4, served at https://manipur.oinam.com/zoom.mp4.
"""

import json
import math
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image

AREA = sys.argv[1] if len(sys.argv) > 1 else "valley"
VIEW = "315"
# Kangla, where the site opens, in the north-up view's link pixels.
LINK_TARGET = (11901, 5988)
SIZE = (1280, 720)
FPS = 30
ZOOM_SECONDS = 7
HOLD_SECONDS = 2
TILE = 512
BACKGROUND = "#1f2a2e"
OUT = Path("web/public/zoom.mp4")


def ease(t: float) -> float:
    return t * t * (3 - 2 * t)


class Pyramid:
    def __init__(self, files: Path) -> None:
        self.files = files
        self.top = max(int(path.name) for path in files.iterdir() if path.name.isdigit())
        self.cache: dict[tuple[int, int, int], Image.Image | None] = {}

    def tile(self, level: int, column: int, row: int) -> Image.Image | None:
        key = (level, column, row)
        if key not in self.cache:
            path = self.files / str(level) / f"{column}_{row}.webp"
            self.cache[key] = Image.open(path).convert("RGB") if path.exists() else None
        return self.cache[key]

    def frame(self, cx: float, cy: float, scale: float) -> Image.Image:
        """The view centered on full-size pixel (cx, cy), with full-size pixels shown at scale."""
        level = min(self.top, self.top + math.ceil(math.log2(scale)))
        factor = 2 ** (self.top - level)
        # The frame's footprint in this level's pixels.
        width, height = SIZE[0] / scale / factor, SIZE[1] / scale / factor
        left, top = cx / factor - width / 2, cy / factor - height / 2
        x0, y0 = math.floor(left), math.floor(top)
        x1, y1 = math.ceil(left + width), math.ceil(top + height)
        patch = Image.new("RGB", (x1 - x0, y1 - y0), BACKGROUND)
        for column in range(x0 // TILE, (x1 - 1) // TILE + 1):
            for row in range(y0 // TILE, (y1 - 1) // TILE + 1):
                tile = self.tile(level, column, row)
                if tile is not None:
                    patch.paste(tile, (column * TILE - x0, row * TILE - y0))
        box = (left - x0, top - y0, left - x0 + width, top - y0 + height)
        crisp = scale / (1 / factor) >= 1
        method = Image.Resampling.NEAREST if crisp else Image.Resampling.LANCZOS
        return patch.resize(SIZE, method, box=box)


def main() -> None:
    tiles = Path("out", AREA, "tiles")
    view = json.loads((tiles / "views.json").read_text())[VIEW]
    dx, dy = view.get("hash_shift", [0, 0])
    pyramid = Pyramid(tiles / "pyramid" / view["pyramid"] / f"{AREA}_files")
    dzi = (tiles / "pyramid" / view["pyramid"] / f"{AREA}.dzi").read_text()
    width, height = (int(re.search(rf'{name}="(\d+)"', dzi)[1]) for name in ("Width", "Height"))
    target = (LINK_TARGET[0] - dx, LINK_TARGET[1] - dy)
    start = (width / 2, height / 2)
    # Start a little inside the map, so its ragged edge stays out of frame.
    first, last = 1.25 * SIZE[0] / width, 1.0
    frames = FPS * ZOOM_SECONDS
    command = [
        "ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{SIZE[0]}x{SIZE[1]}", "-r", str(FPS), "-i", "-",
        "-c:v", "libx264", "-preset", "veryslow", "-crf", "30", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(OUT),
    ]  # fmt: skip
    encoder = subprocess.Popen(command, stdin=subprocess.PIPE)
    assert encoder.stdin
    for index in range(frames + FPS * HOLD_SECONDS):
        t = ease(min(1.0, index / frames))
        scale = first * (last / first) ** t
        # Kangla's offset from the center shrinks as the map grows, so it drifts in smoothly,
        # and reaches nothing at full size.
        pull = (first / scale - first / last) / (1 - first / last)
        cx = target[0] + (start[0] - target[0]) * pull
        cy = target[1] + (start[1] - target[1]) * pull
        encoder.stdin.write(pyramid.frame(cx, cy, scale).tobytes())
        if len(pyramid.cache) > 400:
            pyramid.cache.clear()
    encoder.stdin.close()
    encoder.wait()
    print(f"{OUT}: {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
