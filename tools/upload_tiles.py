"""Upload each tile pyramid that R2 does not have yet; pyramids never change once named.

Batches are recorded as they finish, so a stopped run picks up where it left off. The
index files go last, so the manifest never names a pyramid R2 does not have yet. Only the
pyramids of views the build has recorded as finished go up, so it is safe to run while
`manipur build` is still working. With --pyramids-only it stops before the index files,
which switch the live site over; send those once the code that reads them is deployed.
With --until=HH:MM it stops starting new batches at that local time, so the nightly job
(launchd/com.oinam.manipur.upload.plist) keeps to its window. Cloudflare's API allows
about four requests a second; uploads keep to half that, so they never trip its limit.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from itertools import batched
from pathlib import Path

BUCKET = "manipur-tiles"
ACCOUNT_ID = "091e65b116deac24fcc274459b6fbde0"
ARGS = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
AREA = ARGS[0] if ARGS else "valley"
PYRAMIDS_ONLY = "--pyramids-only" in sys.argv
UNTIL = next((arg.removeprefix("--until=") for arg in sys.argv if arg.startswith("--until=")), None)
TILES = Path("out", AREA, "tiles").resolve()
DONE = Path("out", AREA, "uploaded-pyramids.json")
CACHE_CONTROL = "public, max-age=31536000, immutable"
INDEX_CACHE_CONTROL = "no-cache"
CONTENT_TYPES = {".webp": "image/webp", ".dzi": "application/xml"}
VIEWS_RECORD = TILES / "views.json"
INDEXES = ("manifest.json", "search.json", "flow.json", "credits.json")
BATCH_FILES = 200
# wrangler's default of 20 at once drew "429: Too Many Requests" on most batches.
CONCURRENCY = 2
FILES_PER_SECOND = 2
ATTEMPTS = 8
RETRY_SECONDS = 20


def put_with_retries(
    entries: list[dict], content_type: str, cache_control: str = CACHE_CONTROL
) -> None:
    for attempt in range(1, ATTEMPTS + 1):
        try:
            put(entries, content_type, cache_control)
            return
        except subprocess.CalledProcessError:
            if attempt == ATTEMPTS:
                raise
            print(f"batch failed, retry {attempt}", flush=True)
            time.sleep(RETRY_SECONDS * attempt)


def put(entries: list[dict], content_type: str, cache_control: str) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".json") as listing:
        json.dump(entries, listing)
        listing.flush()
        subprocess.run(
            [
                "pnpm", "exec", "wrangler", "r2", "bulk", "put", BUCKET,
                "--remote", "--force", "--filename", listing.name,
                "--content-type", content_type, "--cache-control", cache_control,
                "--concurrency", str(CONCURRENCY),
            ],
            cwd="web",
            env={**os.environ, "CLOUDFLARE_ACCOUNT_ID": ACCOUNT_ID},
            check=True,
        )  # fmt: skip


def deadline() -> datetime | None:
    """The next time the clock reads --until, today or tomorrow."""
    if not UNTIL:
        return None
    hour, minute = (int(part) for part in UNTIL.split(":"))
    now = datetime.now()
    stop = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return stop if stop > now else stop + timedelta(days=1)


def ready(finished: set[str], done: set[str]) -> bool:
    """True once the build has written a manifest of every view and R2 has all of them.

    The build rewrites the manifest only once every view is finished; until then it may
    name fewer views than are done, or pyramids R2 does not have.
    """
    manifest = json.loads((TILES / INDEXES[0]).read_text())
    named = {view["pyramid"] for view in manifest["views"].values()}
    return named == finished and named <= done


def main() -> None:
    done = set(json.loads(DONE.read_text())) if DONE.exists() else set()
    finished = {view["pyramid"] for view in json.loads(VIEWS_RECORD.read_text()).values()}
    stop = deadline()
    for pyramid in sorted((TILES / "pyramid").iterdir()):
        if pyramid.name in done or pyramid.name not in finished:
            continue
        for suffix, content_type in CONTENT_TYPES.items():
            entries = [
                {"key": str(path.relative_to(TILES)), "file": str(path)}
                for path in sorted(pyramid.rglob(f"*{suffix}"))
            ]
            for index, batch in enumerate(batched(entries, BATCH_FILES)):
                mark = f"{pyramid.name}{suffix}:{index}"
                if mark in done:
                    continue
                if stop and datetime.now() >= stop:
                    print(f"stopped at {UNTIL}, {len(finished & done)} of {len(finished)} uploaded")
                    return
                started = time.monotonic()
                put_with_retries(list(batch), content_type)
                time.sleep(max(0, len(batch) / FILES_PER_SECOND - (time.monotonic() - started)))
                done.add(mark)
                DONE.write_text(json.dumps(sorted(done)))
        done.add(pyramid.name)
        DONE.write_text(json.dumps(sorted(done)))
        print(f"{pyramid.name}: uploaded", flush=True)
    if PYRAMIDS_ONLY:
        print(f"{len(finished & done)} of {len(finished)} finished pyramids uploaded")
        if ready(finished, done):
            print("every view is on R2: push, then upload again without --pyramids-only")
        return
    if not ready(finished, done):
        sys.exit("The manifest is not ready to publish: wait for the build, then upload again.")
    indexes = [{"key": name, "file": str(TILES / name)} for name in INDEXES]
    put_with_retries(indexes, "application/json", INDEX_CACHE_CONTROL)
    print("indexes: uploaded", flush=True)


if __name__ == "__main__":
    main()
