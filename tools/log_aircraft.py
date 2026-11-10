"""Log every aircraft adsb.lol reports near Imphal airport, to measure coverage.

Polls by need, as the server will: every 5 minutes while no airline flight is within
range, every 20 seconds while one is. Each poll appends one line to
data/raw/aircraft/<UTC date>.jsonl, which is not committed.
"""

import json
import re
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

AIRPORT = (24.7600, 93.8967)  # Bir Tikendrajit International Airport, VEIM
RADIUS_NM = 81  # 150 km
IDLE_SECONDS = 300
BUSY_SECONDS = 20
AIRLINES = ("IGO", "AIC", "AXB", "SEJ", "LLR", "AKJ")
AIRLINE_CALLSIGN = re.compile(rf"^({'|'.join(AIRLINES)})\d")
MILITARY = 1  # bit in adsb.lol's dbFlags
URL = "https://api.adsb.lol/v2/point/{}/{}/{}".format(*AIRPORT, RADIUS_NM)
USER_AGENT = "manipur.oinam.com map (brajeshwar@oinam.com)"
LOG = Path("data/raw/aircraft")


def is_airline(aircraft: dict) -> bool:
    callsign = aircraft.get("flight", "").strip()
    return bool(AIRLINE_CALLSIGN.match(callsign)) and not aircraft.get("dbFlags", 0) & MILITARY


def poll() -> dict:
    request = urllib.request.Request(URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main() -> None:
    LOG.mkdir(parents=True, exist_ok=True)
    while True:
        now = datetime.now(UTC)
        try:
            snapshot = poll()
            aircraft = snapshot.get("ac", [])
            airline = [a for a in aircraft if is_airline(a)]
            record = {"t": now.isoformat(timespec="seconds"), "ac": aircraft}
            names = ", ".join(sorted(a.get("flight", "?").strip() for a in aircraft))
            print(f"{now:%H:%M:%S} {len(aircraft)} aircraft, {len(airline)} airline {names}")
        except Exception as error:  # a failed poll is logged and retried
            airline = []
            record = {"t": now.isoformat(timespec="seconds"), "error": str(error)}
            print(f"{now:%H:%M:%S} error: {error}")
        with (LOG / f"{now:%Y-%m-%d}.jsonl").open("a") as log:
            log.write(json.dumps(record) + "\n")
        time.sleep(BUSY_SECONDS if airline else IDLE_SECONDS)


if __name__ == "__main__":
    main()
