// The weather over Imphal right now, shown in the info panel's bar. It comes from
// Open-Meteo: free, no key, and refreshed every 15 minutes at their end.

// Kangla, the middle of the city.
const WEATHER_URL =
  "https://api.open-meteo.com/v1/forecast?latitude=24.8080&longitude=93.9440" +
  "&current=temperature_2m,weather_code,wind_speed_10m&timezone=Asia%2FKolkata";
const RELOAD_MS = 10 * 60_000;
const TIMEOUT_MS = 8000;
// Weather codes (WMO), each row naming every code up to its number.
const SKIES: [number, string][] = [
  [0, "clear sky"],
  [1, "mostly clear"],
  [2, "partly cloudy"],
  [3, "overcast"],
  [48, "fog"],
  [57, "drizzle"],
  [67, "rain"],
  [77, "snow"],
  [82, "showers"],
  [86, "snow"],
  [99, "thunderstorm"],
];

interface Current {
  temperature_2m: number;
  weather_code: number;
  wind_speed_10m: number;
}

export function startWeather(line: HTMLElement): void {
  const load = async () => {
    if (document.hidden) {
      return;
    }
    try {
      const response = await fetch(WEATHER_URL, { signal: AbortSignal.timeout(TIMEOUT_MS) });
      if (!response.ok) {
        return;
      }
      const { current } = (await response.json()) as { current: Current };
      const sky = SKIES.find(([until]) => current.weather_code <= until)?.[1] ?? "";
      const degrees = `${String(Math.round(current.temperature_2m))}°C`;
      line.textContent = sky ? `${degrees} · ${sky}` : degrees;
      line.title =
        `Imphal now: ${line.textContent}, wind ` +
        `${String(Math.round(current.wind_speed_10m))} km/h. Weather by Open-Meteo.`;
    } catch {
      // offline or blocked: the last reading stays, or the bar shows none
    }
  };
  void load();
  setInterval(() => void load(), RELOAD_MS);
  document.addEventListener("visibilitychange", () => void load());
}
