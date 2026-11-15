// The weather over Imphal right now, shown in the info panel's bar. It comes from
// Open-Meteo: free, no key, and refreshed every 15 minutes at their end. The air
// quality beside it is Open-Meteo's reading of CAMS, a model about 45 km across, so it
// is the valley's air, not one street's.

// Kangla, the middle of the city.
const WEATHER_URL =
  "https://api.open-meteo.com/v1/forecast?latitude=24.8080&longitude=93.9440" +
  "&current=temperature_2m,weather_code,wind_speed_10m&timezone=Asia%2FKolkata";
const AIR_URL =
  "https://air-quality-api.open-meteo.com/v1/air-quality?latitude=24.8080&longitude=93.9440" +
  "&current=us_aqi,pm2_5&timezone=Asia%2FKolkata";
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

// US AQI bands, each row naming every value up to its number.
const AIRS: [number, string][] = [
  [50, "good"],
  [100, "moderate"],
  [150, "unhealthy for sensitive groups"],
  [200, "unhealthy"],
  [300, "very unhealthy"],
  [Infinity, "hazardous"],
];

interface Current {
  temperature_2m: number;
  weather_code: number;
  wind_speed_10m: number;
}

interface Air {
  us_aqi: number | null;
  pm2_5: number | null;
}

async function read<T>(url: string): Promise<T | undefined> {
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(TIMEOUT_MS) });
    return response.ok ? ((await response.json()) as { current: T }).current : undefined;
  } catch {
    return undefined;
  }
}

export function startWeather(line: HTMLElement): void {
  const load = async () => {
    if (document.hidden) {
      return;
    }
    // offline or blocked: the last reading stays, or the bar shows none
    const [current, air] = await Promise.all([read<Current>(WEATHER_URL), read<Air>(AIR_URL)]);
    if (!current) {
      return;
    }
    const sky = SKIES.find(([until]) => current.weather_code <= until)?.[1] ?? "";
    const degrees = `${String(Math.round(current.temperature_2m))}°C`;
    const parts = sky ? [degrees, sky] : [degrees];
    let title =
      `Imphal now: ${parts.join(" · ")}, wind ` +
      `${String(Math.round(current.wind_speed_10m))} km/h. Weather by Open-Meteo.`;
    if (air?.us_aqi != null) {
      const aqi = Math.round(air.us_aqi);
      const band = AIRS.find(([until]) => aqi <= until)?.[1] ?? "";
      const pm = air.pm2_5 == null ? "" : `, PM2.5 ${String(Math.round(air.pm2_5))} µg/m³`;
      parts.push(`AQI ${String(aqi)}`);
      title +=
        ` Air: ${String(aqi)} on the US AQI, ${band}${pm}. A valley-wide estimate ` +
        "from the Copernicus Atmosphere Monitoring Service, through Open-Meteo.";
    }
    line.textContent = parts.join(" · ");
    line.title = title;
  };
  void load();
  setInterval(() => void load(), RELOAD_MS);
  document.addEventListener("visibilitychange", () => void load());
}
