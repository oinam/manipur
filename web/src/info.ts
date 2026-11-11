// The info panel at the bottom left. It has tabs, and collapses to just them. One tab holds places to go to; the other holds
// today's timetable at Imphal, marking the flights OpenSky heard nearby, or without a
// timetable what OpenSky saw instead.

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
const TAB_KEY = "info-tab";
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
// A flight this close to its time is about to land or leave, or just has.
const NEAR_MS = 10 * 60_000;
// A status this long past the scheduled time is likely stale, so it is not shown.
const STALE_STATUS_MS = 3_600_000;
const SEEN_MARK = "✓";
const SIGHTINGS_NOTE =
  "Times in IST, two minutes late, from The OpenSky Network. Its receivers rarely reach the " +
  "valley floor, so most flights show only as passing.";
const SCHEDULE_NOTE =
  `Scheduled times in IST from AeroDataBox, landing and leaving at Imphal; airlines may change ` +
  `them. ${SEEN_MARK} marks a flight OpenSky heard within 150 km. Its receivers lose most ` +
  "flights over the hills, so a plane rarely reaches the map.";

function element<T extends HTMLElement>(id: string, type: new () => T): T {
  const found = document.getElementById(id);
  if (!(found instanceof type)) {
    throw new Error(`Missing #${id}`);
  }
  return found;
}

function remembered(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function remember(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // the panel still works; it just opens in its default state next time
  }
}

// Tabs that select on click, collapse the panel when the open one is clicked again, and move
// with the arrow keys.
function startTabs(panel: HTMLElement): void {
  const body = element("info-tabs", HTMLDivElement);
  const collapse = element("info-collapse", HTMLButtonElement);
  const tabs = [...panel.querySelectorAll<HTMLButtonElement>('[role="tab"]')];
  const pane = (tab: HTMLButtonElement) =>
    element(tab.getAttribute("aria-controls") ?? "", HTMLElement);

  const setCollapsed = (collapsed: boolean) => {
    body.hidden = collapsed;
    panel.classList.toggle("collapsed", collapsed);
    const label = collapsed ? "Expand the panel" : "Collapse the panel";
    collapse.setAttribute("aria-expanded", String(!collapsed));
    collapse.setAttribute("aria-label", label);
    collapse.title = label;
    remember(COLLAPSED_KEY, String(collapsed));
  };
  const choose = (chosen: HTMLButtonElement) => {
    for (const tab of tabs) {
      const selected = tab === chosen;
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
      pane(tab).hidden = !selected;
    }
    remember(TAB_KEY, chosen.id);
  };

  for (const [index, tab] of tabs.entries()) {
    tab.addEventListener("click", () => {
      const open = tab.getAttribute("aria-selected") === "true" && !body.hidden;
      choose(tab);
      setCollapsed(open);
    });
    tab.addEventListener("keydown", (event) => {
      const step = { ArrowLeft: -1, ArrowRight: 1 }[event.key];
      if (step) {
        const next = tabs[(index + step + tabs.length) % tabs.length];
        if (next) {
          choose(next);
          next.focus();
        }
      }
    });
  }
  collapse.addEventListener("click", () => {
    setCollapsed(!body.hidden);
  });
  const first = tabs.find((tab) => tab.id === remembered(TAB_KEY)) ?? tabs[0];
  if (first) {
    choose(first);
  }
  setCollapsed(remembered(COLLAPSED_KEY) === "true");
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

function renderSchedule(
  container: HTMLElement,
  schedule: Schedule,
  seen: Set<string>,
  focus: (callsign?: string) => void,
): void {
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
      const near = Math.abs((flight.revised ?? flight.time) - now) <= NEAR_MS;
      item.classList.toggle("past", isPast(flight, now) && !near);
      if (near) {
        item.classList.add("near");
        item.tabIndex = 0;
        item.setAttribute("role", "button");
        item.title = "Show on the map";
        const show = () => {
          focus(flight.callsign);
        };
        item.addEventListener("click", show);
        item.addEventListener("keydown", (event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            show();
          }
        });
      }
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

export function startInfo(focus: (callsign?: string) => void): void {
  const panel = element("info", HTMLElement);
  const flights = element("flights", HTMLDivElement);
  const note = element("flights-note", HTMLParagraphElement);
  const title = element("info-title", HTMLHeadingElement);

  startTabs(panel);

  const load = async () => {
    title.textContent = `Today, ${DATE.format(Date.now())}`;
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
        renderSchedule(flights, schedule, new Set(today.map((flight) => flight.callsign)), focus);
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
