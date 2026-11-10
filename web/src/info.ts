// The info panel beside the controls. It starts with today's airline flights at Imphal,
// as the Worker sorted them: arrivals, departures, and flights that only passed nearby.

interface Flight {
  callsign: string;
  kind: "arrival" | "departure" | "passing";
  time: number;
  km: number;
}

const API = "/api/aircraft";
const RELOAD_MS = 60_000;
const COLLAPSED_KEY = "info-collapsed";
const NARROW = "(max-width: 700px)";
const TIME = new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});
const NOTE =
  "Times in IST, two minutes late, from The OpenSky Network. Its receivers rarely reach the " +
  "valley floor, so most flights show only as passing.";

function element<T extends HTMLElement>(id: string, type: new () => T): T {
  const found = document.getElementById(id);
  if (!(found instanceof type)) {
    throw new Error(`Missing #${id}`);
  }
  return found;
}

function remembered(): boolean | null {
  try {
    const value = localStorage.getItem(COLLAPSED_KEY);
    return value === null ? null : value === "true";
  } catch {
    return null;
  }
}

function remember(collapsed: boolean): void {
  try {
    localStorage.setItem(COLLAPSED_KEY, String(collapsed));
  } catch {
    // the panel still works; it just opens in its default state next time
  }
}

function describe(flight: Flight): string {
  if (flight.kind === "arrival") {
    return "landed";
  }
  if (flight.kind === "departure") {
    return "took off";
  }
  return `passed, ${String(flight.km)} km`;
}

function render(list: HTMLUListElement, flights: Flight[]): void {
  list.replaceChildren(
    ...flights.map((flight) => {
      const item = document.createElement("li");
      const time = document.createElement("span");
      const callsign = document.createElement("span");
      const kind = document.createElement("span");
      time.textContent = TIME.format(flight.time);
      callsign.textContent = flight.callsign;
      kind.textContent = describe(flight);
      kind.className = "kind";
      item.append(time, callsign, kind);
      return item;
    }),
  );
}

export function startInfo(): void {
  const toggle = element("info-toggle", HTMLButtonElement);
  const body = element("info-body", HTMLDivElement);
  const list = element("flights", HTMLUListElement);
  const note = element("flights-note", HTMLParagraphElement);

  const setCollapsed = (collapsed: boolean) => {
    body.hidden = collapsed;
    toggle.setAttribute("aria-expanded", String(!collapsed));
    toggle.setAttribute(
      "aria-label",
      collapsed ? "Expand the info panel" : "Collapse the info panel",
    );
  };
  setCollapsed(remembered() ?? matchMedia(NARROW).matches);
  toggle.addEventListener("click", () => {
    const collapsed = !body.hidden;
    setCollapsed(collapsed);
    remember(collapsed);
  });

  const load = async () => {
    try {
      const response = await fetch(API);
      if (!response.ok) {
        throw new Error(`Aircraft API ${String(response.status)}`);
      }
      const { today = [] } = (await response.json()) as { today?: Flight[] };
      render(list, today);
      note.textContent = today.length
        ? NOTE
        : `No airline flights seen near Imphal yet today. ${NOTE}`;
    } catch {
      list.replaceChildren();
      note.textContent = "Plane times are not available right now.";
    }
  };
  void load();
  setInterval(() => void load(), RELOAD_MS);
}
