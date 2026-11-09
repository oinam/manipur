"""Upload each tile pyramid that R2 does not have yet; pyramids never change once named."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

BUCKET = "manipur-tiles"
ACCOUNT_ID = "091e65b116deac24fcc274459b6fbde0"
TILES = Path("out/imphal/tiles").resolve()
DONE = Path("out/imphal/uploaded-pyramids.json")
CACHE_CONTROL = "public, max-age=31536000, immutable"
CONTENT_TYPES = {".webp": "image/webp", ".dzi": "application/xml"}


def put(entries: list[dict], content_type: str) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".json") as listing:
        json.dump(entries, listing)
        listing.flush()
        subprocess.run(
            [
                "pnpm", "exec", "wrangler", "r2", "bulk", "put", BUCKET,
                "--remote", "--force", "--filename", listing.name,
                "--content-type", content_type, "--cache-control", CACHE_CONTROL,
            ],
            cwd="web",
            env={**os.environ, "CLOUDFLARE_ACCOUNT_ID": ACCOUNT_ID},
            check=True,
        )  # fmt: skip


def main() -> None:
    done = set(json.loads(DONE.read_text())) if DONE.exists() else set()
    for pyramid in sorted((TILES / "pyramid").iterdir()):
        if pyramid.name in done:
            continue
        for suffix, content_type in CONTENT_TYPES.items():
            entries = [
                {"key": str(path.relative_to(TILES)), "file": str(path)}
                for path in pyramid.rglob(f"*{suffix}")
            ]
            put(entries, content_type)
        done.add(pyramid.name)
        DONE.write_text(json.dumps(sorted(done)))
        print(f"{pyramid.name}: uploaded", flush=True)


if __name__ == "__main__":
    main()
