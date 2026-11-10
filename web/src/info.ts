// The info panel beside the controls, shown and hidden by the plane button among them. It starts with today's timetable at Imphal, marking
// the flights OpenSky saw nearby. Without a timetable it lists what OpenSky saw instead.

interface Flight {
  callsign: string;
  kind: "arrival" | "departure" | "passing";
  time: number;
  km: number;
}

interface Scheduled {
  number: string;
  callsign?: string;
  airline: string;
  place: string;
  time: number;
  revised?: number;
  status: string;
}

interface Schedule {
  arrivals: Scheduled[];
  departures: Scheduled[];
}

const API = "/api/aircraft";
const RELOAD_MS = 60_000;
const COLLAPSED_KEY = "info-collapsed";
const TIME = new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});
const DATE = new Intl.DateTimeFormat("en-US", {
  timeZone: "Asia/Kolkata",
  month: "short",
  day: "numeric",
  year: "numeric",
});
// A status this long past the scheduled time is likely stale, so it is not shown.
const STALE_STATUS_MS = 3_600_000;
const SEEN_MARK = "✓";
const SIGHTINGS_NOTE =
  "Times in IST, two minutes late, from The OpenSky Network. Its receivers rarely reach the " +
  "valley floor, so most flights show only as passing.";
const SCHEDULE_NOTE =
  `Scheduled times in IST from AeroDataBox; airlines may change them. ${SEEN_MARK} marks a ` +
  "flight OpenSky saw near Imphal, shown on the map two minutes late.";

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

function row(...cells: [string, string?][]): HTMLLIElement {
  const item = document.createElement("li");
  for (const [text, className] of cells) {
    const cell = document.createElement("span");
    cell.textContent = text;
    if (className) {
      cell.className = className;
    }
    item.append(cell);
  }
  return item;
}

function section(title: string, rows: HTMLLIElement[]): HTMLElement[] {
  const heading = document.createElement("h3");
  const list = document.createElement("ul");
  heading.textContent = title;
  list.append(...rows);
  return [heading, list];
}

// Landed or gone: its time has passed, or the airline says so.
function isPast(flight: Scheduled, now: number): boolean {
  return (flight.revised ?? flight.time) < now || ["arrived", "departed"].includes(flight.status);
}

function statusOf(flight: Scheduled, now: number): string {
  if (flight.revised !== undefined) {
    return `now ${TIME.format(flight.revised)}`;
  }
  return now - flight.time < STALE_STATUS_MS ? flight.status : "";
}

function renderSchedule(container: HTMLElement, schedule: Schedule, seen: Set<string>): void {
  const now = Date.now();
  const rows = (flights: Scheduled[], preposition: string) =>
    flights.map((flight) => {
      const item = row(
        [TIME.format(flight.time)],
        [flight.number],
        [`${preposition} ${flight.place}`, "place"],
        [statusOf(flight, now), "kind"],
        [flight.callsign && seen.has(flight.callsign) ? SEEN_MARK : "", "seen"],
      );
      item.classList.toggle("past", isPast(flight, now));
      return item;
    });
  container.replaceChildren(
    ...section("Arrivals", rows(schedule.arrivals, "from")),
    ...section("Departures", rows(schedule.departures, "to")),
  );
}

function renderSightings(container: HTMLElement, flights: Flight[]): void {
  container.replaceChildren(
    ...section(
      "Seen near Imphal",
      flights.map((flight) =>
        row([TIME.format(flight.time)], [flight.callsign], [describe(flight), "kind"]),
      ),
    ),
  );
}

export function startInfo(): void {
  const toggle = element("planes", HTMLButtonElement);
  const panel = element("info", HTMLElement);
  const flights = element("flights", HTMLDivElement);
  const note = element("flights-note", HTMLParagraphElement);
  const title = element("info-title", HTMLHeadingElement);

  const setCollapsed = (collapsed: boolean) => {
    panel.hidden = collapsed;
    toggle.setAttribute("aria-expanded", String(!collapsed));
  };
  setCollapsed(remembered() ?? false);
  toggle.addEventListener("click", () => {
    const collapsed = !panel.hidden;
    setCollapsed(collapsed);
    remember(collapsed);
  });

  const load = async () => {
    title.textContent = `Airplanes (Today, ${DATE.format(Date.now())})`;
    try {
      const response = await fetch(API);
      if (!response.ok) {
        throw new Error(`Aircraft API ${String(response.status)}`);
      }
      const { today = [], schedule } = (await response.json()) as {
        today?: Flight[];
        schedule?: Schedule;
      };
      if (schedule && schedule.arrivals.length + schedule.departures.length > 0) {
        renderSchedule(flights, schedule, new Set(today.map((flight) => flight.callsign)));
        note.textContent = SCHEDULE_NOTE;
      } else {
        renderSightings(flights, today);
        note.textContent = today.length
          ? SIGHTINGS_NOTE
          : `No airline flights seen near Imphal yet today. ${SIGHTINGS_NOTE}`;
      }
    } catch {
      flights.replaceChildren();
      note.textContent = "Plane times are not available right now.";
    }
  };
  void load();
  setInterval(() => void load(), RELOAD_MS);
}
