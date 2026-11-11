"""Render the phumdi styles side by side at two places on Loktak, for Brajeshwar to choose.

Rows are styles, columns are places: Keibul Lamjao, where the mats make up the park, and the
open lake off Thanga. Each crop is the near-final renderer at the map's 0.5 m/px. Writes
out/loktak/phumdi-options.png.
"""

from pathlib import Path

from PIL import Image, ImageDraw
from pyproj import Transformer

from manipur import detail
from manipur.areas import get_area

OUT = Path("out/loktak/phumdi-options.png")
CROP = 600
LABEL_H = 24
PLACES = {
    "Keibul Lamjao": (93.8160, 24.4790),
    "Open lake off Thanga": (93.8250, 24.5420),
}
STYLES = {
    "flat": "A. flat mats",
    "mats": "B. mats with pools",
    "rings": "C. mats, pools, and athaphum rings",
}


def main() -> None:
    scene = detail.load_scene(get_area("loktak"))
    to_metric = Transformer.from_crs(4326, detail.METRIC_CRS, always_xy=True)
    lookup = detail.detail_lookup()
    sheet = Image.new("RGB", (CROP * len(PLACES), (CROP + LABEL_H) * len(STYLES)), "#1f2a2e")
    draw = ImageDraw.Draw(sheet)
    for row, (style, title) in enumerate(STYLES.items()):
        detail.PHUMDI_STYLE = style
        for column, (place, center) in enumerate(PLACES.items()):
            x, y = to_metric.transform(*center)
            view = detail.centered_viewport(detail.PROJECTION, x, y, CROP, CROP)
            crop = Image.fromarray(detail.render_detail(scene, view), mode="P")
            crop.putpalette(lookup)
            top = row * (CROP + LABEL_H)
            sheet.paste(crop.convert("RGB"), (column * CROP, top + LABEL_H))
            draw.text((column * CROP + 8, top + 6), f"{title}: {place}", fill="#e8dfb8")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(OUT)
    print(OUT)


if __name__ == "__main__":
    main()
