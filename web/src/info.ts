// The info panel, which opens at the bottom left and can be dragged elsewhere. It has
// tabs, and collapses to just them and the weather. One tab holds places to go to; the
// other holds today's timetable at Imphal.

import { flightId } from "./timetable";
import { startWeather } from "./weather";

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

// Where a dragged panel sits: its left and bottom edges, in pixels from the screen's.
interface Spot {
  left: number;
  bottom: number;
}

const API = "/api/aircraft";
const RELOAD_MS = 60_000;
const COLLAPSED_KEY = "info-collapsed";
const TAB_KEY = "info-tab";
const POSITION_KEY = "info-position";
// A press that moves less than this is a click, not a drag.
const DRAG_START_PX = 4;
// The gap a dragged panel keeps from the edge of the screen.
const EDGE_PX = 8;
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
const SCHEDULE_NOTE =
  "Scheduled times in IST from AeroDataBox, landing and leaving at Imphal; airlines may change " +
  "them. Each flight is drawn on the map landing or taking off at its time, labeled " +
  '"scheduled, not live".';

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

function forget(key: string): void {
  try {
    localStorage.removeItem(key);
  } catch {
    // nothing was kept, so there is nothing to forget
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

// The panel moves by its bar, and a double click on the bar sends it back to its corner.
// It is placed by its left and bottom edges, so it still folds downward wherever it
// sits, and it is kept on screen.
function startDrag(panel: HTMLElement): void {
  const bar = element("info-bar", HTMLDivElement);
  let spot: Spot | null = null;

  const place = (left: number, bottom: number) => {
    panel.classList.add("moved");
    const limit = (value: number, most: number) =>
      Math.round(Math.max(EDGE_PX, Math.min(value, most - EDGE_PX)));
    spot = {
      left: limit(left, innerWidth - panel.offsetWidth),
      bottom: limit(bottom, innerHeight - panel.offsetHeight),
    };
    panel.style.left = `${String(spot.left)}px`;
    panel.style.bottom = `${String(spot.bottom)}px`;
  };
  const replace = () => {
    if (spot) {
      place(spot.left, spot.bottom);
    }
  };

  bar.addEventListener("pointerdown", (down) => {
    if (down.button !== 0) {
      return;
    }
    const box = panel.getBoundingClientRect();
    const drag = new AbortController();
    let dragging = false;
    // On the window, since a quick pointer leaves the bar before the drag has begun.
    addEventListener(
      "pointermove",
      (move) => {
        const dx = move.clientX - down.clientX;
        const dy = move.clientY - down.clientY;
        if (!dragging && Math.hypot(dx, dy) < DRAG_START_PX) {
          return;
        }
        if (!dragging) {
          dragging = true;
          bar.setPointerCapture(down.pointerId);
          panel.classList.add("dragging");
        }
        place(box.left + dx, innerHeight - box.bottom - dy);
      },
      { signal: drag.signal },
    );
    const end = () => {
      drag.abort();
      panel.classList.remove("dragging");
      if (!dragging) {
        return;
      }
      remember(POSITION_KEY, JSON.stringify(spot));
      // The release would otherwise count as a click on the tab the drag began on.
      const swallow = new AbortController();
      addEventListener(
        "click",
        (click) => {
          click.stopPropagation();
          click.preventDefault();
        },
        { capture: true, once: true, signal: swallow.signal },
      );
      setTimeout(() => {
        swallow.abort();
      });
    };
    addEventListener("pointerup", end, { signal: drag.signal });
    addEventListener("pointercancel", end, { signal: drag.signal });
  });
  bar.addEventListener("dblclick", (event) => {
    if (event.target instanceof Element && event.target.closest("button")) {
      return;
    }
    spot = null;
    panel.classList.remove("moved");
    panel.style.left = "";
    panel.style.bottom = "";
    forget(POSITION_KEY);
  });

  try {
    const saved = JSON.parse(remembered(POSITION_KEY) ?? "null") as Spot | null;
    if (saved && Number.isFinite(saved.left) && Number.isFinite(saved.bottom)) {
      place(saved.left, saved.bottom);
    }
  } catch {
    // an unreadable position: the panel opens in its corner
  }
  // The window, the open tab, and collapsing all change how much room the panel has.
  addEventListener("resize", replace);
  new ResizeObserver(replace).observe(panel);
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
  focus: (id: string) => void,
): void {
  const now = Date.now();
  const rows = (flights: Scheduled[], preposition: string) =>
    flights.map((flight) => {
      const item = row(
        [TIME.format(flight.time)],
        [flight.number],
        [`${preposition} ${flight.place}`, "place"],
        [statusOf(flight, now), "kind"],
      );
      const near = Math.abs((flight.revised ?? flight.time) - now) <= NEAR_MS;
      item.classList.toggle("past", isPast(flight, now) && !near);
      if (near) {
        item.classList.add("near");
        item.tabIndex = 0;
        item.setAttribute("role", "button");
        item.title = "Show on the map";
        const show = () => {
          focus(flightId(flight));
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

export function startInfo(focus: (id: string) => void): void {
  const panel = element("info", HTMLElement);
  const flights = element("flights", HTMLDivElement);
  const note = element("flights-note", HTMLParagraphElement);
  const title = element("info-title", HTMLHeadingElement);

  startTabs(panel);
  startDrag(panel);
  startWeather(element("weather", HTMLSpanElement));

  const load = async () => {
    title.textContent = `Today, ${DATE.format(Date.now())}`;
    try {
      // Browsers may still hold a copy from Nov 11 under a one-year header; always ask again.
      const response = await fetch(API, { cache: "no-cache" });
      if (!response.ok) {
        throw new Error(`Aircraft API ${String(response.status)}`);
      }
      const { schedule } = (await response.json()) as { schedule?: Schedule };
      if (schedule && schedule.arrivals.length + schedule.departures.length > 0) {
        renderSchedule(flights, schedule, focus);
        note.textContent = SCHEDULE_NOTE;
      } else {
        flights.replaceChildren();
        note.textContent = "Today's timetable at Imphal is not available yet.";
      }
    } catch {
      flights.replaceChildren();
      note.textContent = "Plane times are not available right now.";
    }
  };
  void load();
  setInterval(() => void load(), RELOAD_MS);
}
