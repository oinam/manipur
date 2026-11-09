# Contributing

This map gets better when people who know Imphal correct it. The most useful
help doesn't involve any code.

## Fix the map

| What you know | Where it goes |
|---|---|
| Where a road, wall, or building is, or what it's called | [OpenStreetMap](https://www.openstreetmap.org). This map is built from it, so a fix there appears here on the next rebuild. |
| A photo of a landmark we can't draw yet | [Wikimedia Commons](https://commons.wikimedia.org), under CC BY, CC BY-SA, CC0, or public domain, then link it in an issue. |
| A wrong spelling or label, or anything else | [Open an issue](https://github.com/oinam/manipur/issues/new), or use "Suggest a correction" on the map, which fills in the location for you. |

Please don't copy details from Google Maps or other proprietary maps. Their
licenses don't allow it, and one copied detail can taint the open data.

## Change the code

```
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
pnpm --dir web install
pnpm --dir web run lint
```

Rendering the map also needs the source data; `CLAUDE.md` lists each stage.
`docs/DATA.md` records every source and its license. A new source needs a row
there before any code uses it.
