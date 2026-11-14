"""Log every aircraft adsb.lol and OpenSky report near Imphal airport, to compare coverage.

A private check that stays on this machine; the site shows none of it. Polls by need:
every 5 minutes while neither source has an airline
flight within range, every 20 seconds while one does. Each poll appends one line per
source to data/raw/aircraft/<UTC date>.jsonl, which is not committed. OpenSky is used
only when OPENSKY_CLIENT_ID and OPENSKY_CLIENT_SECRET are set, as mise does from .env.

OpenSky allows 4,000 credits a day, so after 3,600 polls in a UTC day it polls at the
idle rate whatever is flying.
"""

import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

AIRPORT = (24.7600, 93.8967)  # Bir Tikendrajit International Airport, VEIM
RADIUS_NM = 81  # 150 km
BOX_DEGREES = (1.35, 1.49)  # about 150 km of latitude and longitude; one OpenSky credit
IDLE_SECONDS = 300
BUSY_SECONDS = 20
AIRLINES = ("IGO", "AIC", "AXB", "SEJ", "LLR", "AKJ")
AIRLINE_CALLSIGN = re.compile(rf"^({'|'.join(AIRLINES)})\d")
MILITARY = 1  # bit in adsb.lol's dbFlags
ADSB_LOL = "https://api.adsb.lol/v2/point/{}/{}/{}".format(*AIRPORT, RADIUS_NM)
OPENSKY = "https://opensky-network.org/api/states/all"
OPENSKY_TOKEN = (
    "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
)
TOKEN_MARGIN_SECONDS = 60
DAILY_BUSY_CREDITS = 3_600
USER_AGENT = "manipur.oinam.com map (brajeshwar@oinam.com)"
LOG = Path("data/raw/aircraft")


def is_airline(callsign: str, military: bool = False) -> bool:
    return bool(AIRLINE_CALLSIGN.match(callsign.strip())) and not military


def fetch_json(request: urllib.request.Request) -> dict:
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


# Each poll returns the raw aircraft, every callsign, and the airline flights among them.
def poll_adsb_lol() -> tuple[list, list[str], list[str]]:
    snapshot = fetch_json(urllib.request.Request(ADSB_LOL, headers={"User-Agent": USER_AGENT}))
    aircraft = snapshot.get("ac", [])
    names = [a.get("flight", "?").strip() for a in aircraft]
    airline = [
        a["flight"].strip()
        for a in aircraft
        if is_airline(a.get("flight", ""), bool(a.get("dbFlags", 0) & MILITARY))
    ]
    return aircraft, names, airline


class OpenSky:
    def __init__(self, client_id: str, client_secret: str) -> None:
        self.credentials = {"client_id": client_id, "client_secret": client_secret}
        self.token = ""
        self.expires = 0.0

    def bearer(self) -> str:
        if time.time() > self.expires - TOKEN_MARGIN_SECONDS:
            form = urllib.parse.urlencode({"grant_type": "client_credentials", **self.credentials})
            reply = fetch_json(urllib.request.Request(OPENSKY_TOKEN, data=form.encode()))
            self.token = reply["access_token"]
            self.expires = time.time() + reply["expires_in"]
        return self.token

    def poll(self) -> tuple[list, list[str], list[str]]:
        (lat, lon), (dlat, dlon) = AIRPORT, BOX_DEGREES
        box = {"lamin": lat - dlat, "lamax": lat + dlat, "lomin": lon - dlon, "lomax": lon + dlon}
        url = f"{OPENSKY}?{urllib.parse.urlencode(box)}"
        headers = {"Authorization": f"Bearer {self.bearer()}", "User-Agent": USER_AGENT}
        states = fetch_json(urllib.request.Request(url, headers=headers)).get("states") or []
        names = [(state[1] or "?").strip() for state in states]
        return states, names, [name for name in names if is_airline(name)]


def main() -> None:
    LOG.mkdir(parents=True, exist_ok=True)
    sources = {"adsb.lol": poll_adsb_lol}
    if os.environ.get("OPENSKY_CLIENT_ID") and os.environ.get("OPENSKY_CLIENT_SECRET"):
        sources["opensky"] = OpenSky(
            os.environ["OPENSKY_CLIENT_ID"], os.environ["OPENSKY_CLIENT_SECRET"]
        ).poll
    print("sources:", ", ".join(sources))
    polls: dict[str, int] = {}
    while True:
        now = datetime.now(UTC)
        day = f"{now:%Y-%m-%d}"
        busy = False
        for name, poll in sources.items():
            record = {"t": now.isoformat(timespec="seconds"), "source": name}
            try:
                aircraft, names, airline = poll()
                record["ac"] = aircraft
                busy = busy or bool(airline)
                if name == "opensky":
                    polls[day] = polls.get(day, 0) + 1
                print(f"{now:%H:%M:%S} {name}: {len(aircraft)} aircraft {', '.join(sorted(names))}")
            except Exception as error:  # a failed poll is logged and retried
                record["error"] = str(error)
                print(f"{now:%H:%M:%S} {name} error: {error}")
            with (LOG / f"{now:%Y-%m-%d}.jsonl").open("a") as log:
                log.write(json.dumps(record) + "\n")
        within_credits = polls.get(day, 0) < DAILY_BUSY_CREDITS
        time.sleep(BUSY_SECONDS if busy and within_credits else IDLE_SECONDS)


if __name__ == "__main__":
    main()
