"""Cut the link-preview picture, Kangla in the north-up view, from the finished tile pyramid.

The crop is 1200 x 630 px, the size link previews ask for, centered where the site opens
and shown at the same half scale. It reads only the rendered tiles, so it changes when the
map is re-rendered and this is run again. Writes web/public/og.png.
"""

import json
import sys
from pathlib import Path

from PIL import Image

AREA = sys.argv[1] if len(sys.argv) > 1 else "valley"
VIEW = "315"
# The opening view's center in the north-up view's image pixels, as the site's link writes it.
LINK_CENTER = (11901, 5988)
SIZE = (1200, 630)
TILE = 512
OUT = Path("web/public/og.png")


def main() -> None:
    tiles = Path("out", AREA, "tiles")
    view = json.loads((tiles / "views.json").read_text())[VIEW]
    dx, dy = view.get("hash_shift", [0, 0])
    files = tiles / "pyramid" / view["pyramid"] / f"{AREA}_files"
    # Half scale is one level below full size.
    level = max(int(path.name) for path in files.iterdir() if path.name.isdigit()) - 1
    cx, cy = (LINK_CENTER[0] - dx) // 2, (LINK_CENTER[1] - dy) // 2
    left, top = cx - SIZE[0] // 2, cy - SIZE[1] // 2
    picture = Image.new("RGB", SIZE, "#1f2a2e")
    for column in range(left // TILE, (left + SIZE[0]) // TILE + 1):
        for row in range(top // TILE, (top + SIZE[1]) // TILE + 1):
            path = files / str(level) / f"{column}_{row}.webp"
            if path.exists():
                with Image.open(path) as tile:
                    picture.paste(tile.convert("RGB"), (column * TILE - left, row * TILE - top))
    picture.save(OUT, optimize=True)
    print(f"{OUT}: {OUT.stat().st_size // 1024} KB, level {level}")


if __name__ == "__main__":
    main()
