# Decisions

One entry per settled question. Newest at the bottom. Proposals that are not
yet decided live in `PLAN.md` under "Open decisions".

## 2026-11-08 — Procedural rendering, not AI repaint

Google has no 3D mesh for India and there is no derivative-licensed
high-resolution imagery of Imphal, so the tiny.london recipe has no honest
input. The map is rendered from vectors and open rasters. AI restyling is
Phase 5 and parked; the procedural map must stand alone.

## 2026-11-08 — Licence line: no grey zones

Only sources that permit derivative works with attribution. Rendered map
released CC BY-SA 4.0 to satisfy ODbL produced-work obligations cleanly.
Code MIT, copyright Oinam.

## 2026-11-08 — Start with Imphal, specifically a Kangla test patch

Phase 0 renders ~1.5 km around Kangla before any wider work. The go/no-go is
whether the street pattern reads as Imphal.

## 2026-11-08 — Python-first renderer

NumPy + Pillow painter's algorithm for Phases 0–3. Exact pixels, no GPU, easy
for an agent to debug from PNG diffs. Revisit only if Phase 3 is painful.

## 2026-11-08 — Tiles and viewer

512 px WebP Deep Zoom pyramid via libvips; OpenSeadragon, vanilla TypeScript,
Vite; Cloudflare Pages + R2. Same shape as the reference sites so the viewer
code can borrow from isometric-nyc (MIT) where useful.

## 2026-11-08 — Phase 0 plumbing

Python is pinned to 3.12 so the geo stack installs from wheels without GDAL.
Open Buildings is streamed from the S2 level 6 cell and filtered to the area, so
the full cell never touches the disk. 2.5D heights come from the public
`open-buildings-temporal-data` bucket, so no Earth Engine account is needed.

Footprints: Open Buildings polygons need confidence of at least 0.70. One is
a duplicate of an OSM building, which wins, at IoU of at least 0.30 or when at
least 50% of it lies inside the OSM polygon. One at least 50% on mapped water is
dropped. Heights prefer OSM tags, then the 75th percentile of the 2023 raster
inside the footprint (the raster's effective 4 m resolution smears edges), then
3.5 m or 6.5 m by footprint area; all are clamped to 2.5–80 m. Rivers mapped only
as lines default to 30 m wide.

Rendering paints semantic color slots, then applies a palette, so a palette
change never re-renders geometry. Each building's depth is its centroid. DEM is
left out until Phase 3 because the patch is on the flat valley floor.

## 2026-11-08 — Projection, pixel scale, and palette

Brajeshwar chose projection B (2:1 dimetric, 45° rotation), 0.5 m/px, and the
`monsoon` palette from the swatch sheet. The renderer uses these by default.

## 2026-11-08 — Detail crop as the quality test

`manipur detail` styles one 900 px crop to near-final quality, to judge what the
procedural map can become; `render` is unchanged. The `kangla-sw` area is wider
than `kangla` so the crop never runs off the data.

The monsoon palette gains 11 shades derived from its own colors (roof shades,
canopy, water, shadow), for 32 slots in all. Ground stays WorldCover, smoothed by
a box-blur vote, because OSM land use is thin here. Tree positions are procedural:
WorldCover class sets the odds, and OSM `tree_row` lines are followed. Roof type
and color come from a seeded hash, so they are plausible rather than real.

The Shaheed Minar sprite is drawn from shapes in code; no photo pixels are read.
Its position is hand-placed at the center of OSM's park polygon, because no
surveyed coordinate exists, and needs checking by someone who knows the park.

## 2026-11-08 — Phase 0 closed; Phase 1 scale and source

Brajeshwar said to go ahead with Phase 1 after seeing the detail crop.

The municipal bbox in `PLAN.md` is 161 km², not the 35 km² it first said, so the
canvas is about 645 megapixels and is rendered as a grid of frames. OSM comes from
Geofabrik's `north-eastern-zone` extract, read with pyosmium (110 MB, against 1.7 GB
for all of India, on a nearly full disk). Heights are resampled to 2 m for this
area; the raster's effective resolution is about 4 m.

## 2026-11-08 — Phase 1 rendering and tiles

Frames are 2048 px on one integer canvas, each rendered with a 256 px apron and
cropped, so neighbors join without a differing pixel; a test holds that true.
Trees and paddy are anchored to world coordinates. OSM maps no paddy or farmland
here, so WorldCover cropland gets a procedural field lattice.

Open Buildings polygons at least 50% on a road 8 m or wider are dropped: they are
flyovers and footbridges read as roofs. Tiles are lossless WebP, which measured
smaller than lossy for this flat-color art (41 KB per tile against 65 KB at q60)
and stays pixel-exact, so this differs from the reference sites' q60.

Search uses OSM `name` only. The site's name, its domain, and label scripts are
still open in `PLAN.md`; the viewer's title is a placeholder.

## 2026-11-08 — Domain and labels

Brajeshwar chose `manipur.oinam.com` for the site, and Latin labels for now.

## 2026-11-08 — Hosting

The map is served as Cloudflare Workers static assets in the Oinam account, with
`manipur.oinam.com` as its custom domain. This replaces the planned Pages + R2:
161 MB in about 3,500 files needs no R2, and Wrangler attaches the domain itself.

## 2026-11-08 — Landmarks, labels, and tilt-shift

Landmarks come from the list in `PLAN.md`. A mapped building keeps its real
footprint and gets a painted style (`assets/landmarks.json`); a small point-like
monument is a sprite at its mapped position (`assets/sprites/`). All are drawn in
code from the palette's 32 slots, so the domes are pale rather than true gold. The
gate is drawn 1.7 times scale and the Kangla Sha about 2.5 times, so their forms read.

The two war cemeteries are a ground pattern on their OSM polygons. Grave positions
are a regular grid, not surveyed.

Labels are viewer overlays rather than pixels in the tiles, so changing script
later needs no re-render. Tilt-shift is a CSS blur that appears when zoomed out.

## 2026-11-09 — Versioned tiles

The pyramid lives at `tiles/pyramid/<hash>/`, where the hash covers the frame bytes
and tile settings, and is cached as immutable. `tiles/manifest.json` names the
current hash and is revalidated on every load, as are the pages and the search and
credits files. A re-render therefore gets new tile URLs, and no visitor can see old
and new tiles mixed.

## 2026-11-09 — Second landmark round

The inner Kangla and the Assembly come next because Commons covers them well. OSM
names the Pakhangba temple, the Kangla Museum, and the Assembly at points on their
footprints. It does not name the Uttra Shanglen or the citadel walls. The Uttra
Shanglen is the cruciform footprint beside the Kangla Sha, as a photo shows. The
citadel walls are two adjoining footprints that fit coarse photo geotags, so they
are drawn without a label until someone confirms them.

Dome finials are a spike and ball; the earlier crossbar read as a Christian cross.

## 2026-11-09 — Living water

Flowing water is a viewer layer, so it needs no re-render and leaves the tiles
deterministic. It reads the drawn map to find open water, which keeps it off trees,
bridges, and windows. Rivers and streams move along OSM's way direction, which is
downstream by convention; moats and ponds only shimmer. The viewer now uses
OpenSeadragon's canvas drawer, because the layer has to read its pixels. A map
control turns the motion off; it starts off under the system's Reduce Motion setting.

Live aircraft are planned in `docs/AIRCRAFT.md`; nothing is built yet.

## 2026-11-09 — Opening view

The map opens on central Imphal at image zoom 0.5, with Ima Keithel and Kangla both
in frame, instead of fitting the whole canvas. A URL hash still wins, and the home
button still shows all of Imphal.

## 2026-11-09 — Four viewing directions

The map can be seen from four sides: the chosen 2:1 projection at quarter turns,
later narrowed to 15 degree steps (below). Each is a
full render and its own pyramid, because the art is pre-drawn; free rotation would need
a different renderer. The default view's frames are unchanged. Search and flow stay in
default-view coordinates, and the viewer converts them through the ground plane using
each view's matrix from the manifest. Non-default views add a fourth hash segment, so
older links still open as they did.

## 2026-11-09 — Fifteen degree turns

Brajeshwar asked for 15 degree steps, so the four views become 24, named for the turn
from the default (`0`, `15`, ... `345`). Links using the earlier `sw`, `se`, and `ne`
names still open. Alt or Option reverses the turn. While a new view loads, the last
frame stays on screen.

## 2026-11-09 — Tiles on R2

Twenty-four pyramids need about 68,000 files, over the free Workers limit of 20,000.
Brajeshwar chose R2 (bucket `manipur-tiles`), which fits in its free 10 GB. The bucket
is served directly from its own domain, `manipur-tiles.oinam.com`, so tile requests do
not count against Workers' daily free requests. That domain is one level under
`oinam.com` because Universal SSL does not cover deeper names. The viewer asks for
tiles with CORS, since the water layer reads the drawn pixels. Only the versioned
pyramids move; the manifest and indexes stay with the site. Local builds still read
tiles from `out/`.

## 2026-11-09 — Compass

A compass control turns the map to view `315`, the one with true north at the top. Its
needle always points north, using the angle from each view's matrix. It is not the
opening view; the default stays the one Brajeshwar chose.

## 2026-11-09 — Local buildings

Brajeshwar chose "recognizably Imphal" as the realism target and, from a rendered
comparison, local buildings ahead of street life. Pitched houses under 160 m² are now
low tin houses with a veranda on their near long side, and two-thirds of flat roofs of
at least 25 m² carry a black water tank. Which houses get them comes from the existing
seeded hash, so they are plausible rather than surveyed.

## 2026-11-09 — Settings

A gear opens a settings panel. Its first entry, Animation, replaces the water button
and is the one switch for moving things: water now, aircraft if they are built. It
keeps the saved water choice and still starts off under Reduce Motion.

## 2026-11-10 — Aircraft: airlines only, two minutes late

Brajeshwar decided that live aircraft, if built, show only scheduled airline flights
and run two minutes behind. Military, government, and unidentified aircraft are
dropped on the server. How each works is in `docs/AIRCRAFT.md`.

## 2026-11-10 — Aircraft from adsb.lol, not OpenSky

OpenSky's terms require a written license for any live product or automated system,
even a non-profit one, so it is not used. adsb.lol publishes its API under ODbL 1.0
for everyone, the license the map already follows for OpenStreetMap, and needs no
key. Its API cannot return past positions, so the two-minute delay is a Durable
Object that polls by need and keeps a few minutes of snapshots.

## 2026-11-10 — OpenSky, locally until licensed

Brajeshwar chose to build on OpenSky after all and created an API client. On the
first test it saw two flights near Imphal that adsb.lol missed. Its terms cover
research use, so it runs on Brajeshwar's machine; the public site waits for
OpenSky's written license. The secrets live in `.env` and, once deployed, as Worker
secrets.

The aircraft server is the site's existing Worker, given a `main` script and a
SQLite-backed Durable Object. The Worker answers `/api/aircraft` and hands every
other path to the static assets. The viewer starts planes only with
`?aircraft=live` or `?aircraft=demo` until publishing is decided.

## 2026-11-10 — Plane style

Brajeshwar chose style C from the options sheet: an A320-sized airliner with body,
fin, and engines, drawn at twice real size. It is projected from a model in meters
rather than drawn as sprites, so it turns smoothly in all 24 views.

## 2026-11-10 — Planes are not animation

Brajeshwar decided that planes show even with Animation off, because a plane is a
real event rather than decoration. This narrows the Settings entry above: Animation
covers the water, and planes may get a switch of their own later.

## 2026-11-10 — mise

Brajeshwar asked for mise. `mise.toml` pins uv, Node, and pnpm to the versions
already in use, loads `.env` for secrets such as the OpenSky client, and names the
project's commands as tasks. uv and pnpm still install the packages, and CI is
unchanged.

## 2026-11-10 — Deploy on push

Brajeshwar asked for the site to deploy when `main` is pushed. A `deploy` job in
GitHub Actions runs `pnpm run deploy` after the lint and test jobs pass, with a
Cloudflare API token as a repository secret. GitHub cannot render the map, so the
map's data no longer ships with the site: the manifest, search, flow, and credits
files join the pyramids on R2, uploaded last by `tools/upload_tiles.py` with
`no-cache`. The Worker's assets are now `web/dist`, and `.assetsignore` keeps the
local tiles link out of it.

## 2026-11-10 — Live planes on the site

Brajeshwar wrote to OpenSky for a license and got an automated reply that use is
fine within the API's credit limit, so live planes are on by default. The Worker
keeps under OpenSky's 4,000 daily credits: it polls at the 20 second rate for at
most 3,600 polls a UTC day and at the 5 minute rate after that, and it stops
polling ten minutes after the last request for planes, so nobody watching costs
nothing. `AIRCRAFT_FEED` in `web/wrangler.jsonc` still switches the feed off, and
`?aircraft=off` hides planes in the viewer. A written license is still welcome,
and the record of what was granted is the row in `docs/DATA.md`.

## 2026-11-10 — The Mac relays OpenSky

OpenSky's login server times out for requests from Cloudflare (error 522) while it
answers a home connection at once, so the Worker cannot poll it. Brajeshwar chose a
relay on the home Mac: the aircraft logger, run as `mise run relay`, posts each OpenSky
reply to `POST /api/aircraft` with a bearer token that matches the Worker secret
`RELAY_TOKEN`. The Worker filters it to airline flights exactly as before and serves
it two minutes late. While the relay has posted in the last ten minutes the Worker
leaves OpenSky alone; otherwise it tries OpenSky itself, which costs nothing when it
fails. Planes show only while the Mac runs the relay. The relay keeps the same
daily cap of 3,600 busy polls, and since it is now the only poller, the Worker and
the logger no longer share the credits.

## 2026-11-10 — Info panel, starting with planes

Brajeshwar asked for a collapsible, see-through info panel beside the controls at the
top right, starting with the day's planes. The Worker keeps a log of each airline
flight's first, last, and closest sightings for the day in Imphal time, folding in a
snapshot only once it is two minutes old, and `/api/aircraft` returns it as `today`.
A flight last seen within 40 km and 3,000 m above the field, lower than it was first
seen, landed; one first seen like that and climbing took off; anything else passed,
with its closest distance. On the first day's log no airline flight came within
121 km or below 2,000 m, because OpenSky's receivers do not reach the valley, so
today the list is honest but mostly "passed". The collapse state is remembered per
browser, and the panel starts collapsed on narrow screens.

## 2026-11-10 — Timetable from AeroDataBox

OpenSky cannot see planes land at Imphal, so Brajeshwar chose AeroDataBox's free
plan, through RapidAPI, for the day's timetable. Its terms allow showing the data
inside an application like this map, for non-commercial use, but not passing it on
as a feed, and they limit how long it may be kept. The Worker keeps only today's
board, in two halves of the day, and replaces it each day. The plan has 400 units a
month and a board request costs 2, so the Worker makes at most six requests a day
(both halves, then refreshes after three hours) and stops if fewer than 20 units are
left. The info panel lists arrivals and departures with their scheduled times,
hides a status more than an hour past its time because the free data rarely updates
it, and ticks a flight OpenSky saw nearby. Without a timetable the panel falls back
to the OpenSky sightings. The local Worker draws on the same monthly units.

## 2026-11-10 — Toolbox defaults

Brajeshwar asked for animation on by default and for planes to work regardless of it.
Animation now starts on even when the system asks for reduced motion, and the switch
in Settings remembers a visitor's choice under a new key, so earlier choices start
over. Planes never read the switch. The home button goes to the opening view, in the
current direction, instead of fitting all of Imphal, which was too small to read.

## 2026-11-10 — A top-down check of the whole state

Before Phase 3 puts terrain into the isometric renderer, `manipur overview --area manipur`
draws the state top-down at 100 m/px. WorldCover classes are mapped to the `monsoon`
palette's ground colors, and they're shaded in six flat bands from the Copernicus DEM,
lit from the northwest. The OSM state and district lines, rivers, and towns come from
the cached Geofabrik extract. Outside the state is faded toward paper. Land cover and
elevation are read at about 60 m into `data/raw/manipur/`, not at full resolution, so
the fetch stays small. This is a check render, not the coarse layer for Phase 4; how
that layer looks is Brajeshwar's call.

## 2026-11-11 — Planes from the timetable

OpenSky never heard a flight closer than 125 km from Imphal, so Brajeshwar chose to draw
planes from the timetable, labeled "scheduled, not live", next to any live ones. Arrivals
land and departures take off at their listed times, both on runway 22 toward the
southwest. Which runway is in use isn't known, and the listed times are gate times, so
both are simplifications; the label says the plane is not live. Details are in
`docs/AIRCRAFT.md`.

Brajeshwar asked the same day that a landed plane stay parked until it leaves, since
Imphal has no hangar for airliners, rather than appearing from nothing. Each departure is
now paired with the same airline's earliest earlier arrival at least 20 minutes before
it, and the plane taxis, parks, and taxis out between the two. Pairing by airline is a
guess at which aircraft turns around; the timetable does not say.

## 2026-11-11 — One canvas from Imphal to Loktak

Brajeshwar chose to join Loktak to the Imphal map rather than give it a map of its own.
The site's area is now `valley` (24.42–24.86 N, 93.74–94.00 E, about 1,300 km²), which
takes in Imphal, Loktak, Keibul Lamjao, Moirang, Bishnupur, Thoubal, and Kakching. The
`imphal` area stays for comparison.

At about 1.0 GB of tiles and half an hour per view, the 24 views need about 24 GB and
11 hours, more than the free disk could hold alongside every view's frames. So `manipur
build` renders and tiles one view at a time, deletes that view's frames, and records each
finished view so a stopped run resumes. The default view's frames stay for the option
sheets.

Links keep their pixel positions in the original Imphal canvas: `assets/hash_origin.json`
holds that canvas's offsets for each view, each view in the manifest carries the shift to
its own canvas, and the viewer applies it when reading and writing the address. Links
shared before the map grew still land in the same place.

Phumdis are drawn in style C, mats with pools and athaphum rings, inside lakes over
1 km² and OSM's phumdi and national park areas, with open water where WorldCover says
water. Herds of Sangai, drawn at three times real size with a dark edge, wander near the
Sangai viewpoint in Keibul Lamjao.

## 2026-11-11 — Renders live on an external drive

The Mac's disk could not hold the valley's 24 views (about 24 GB of tiles) beside
everything else, so every render now lives on the external drive, and this checkout keeps
only code and data. `out/` is a link to `/Volumes/2021OCT-5TB/Scratch/manipur/out`.
`Scratch` is meant for any project's bulky output. The pipeline, the dev server, and the
upload all read and write `out/` as before, through the link, so none of them changed.
`.gitignore` ignores `/out` rather than `out/`, because git sees a link as a file.

Nothing in `out/` is precious: it all rebuilds from `data/raw/`, and the published tiles
are also in R2. Without the drive plugged in, anything that reads or writes `out/`
fails; plug it back in and rerun, and `manipur build` resumes from the last finished
view. On a computer with room to spare, bring the renders back with
`rm out && rsync -a /Volumes/2021OCT-5TB/Scratch/manipur/out ./`, or simply let `out/` be
a plain folder and render again.

## 2026-11-11 — Tiles go up overnight, slowly

The valley's 24 views are about 516,000 tile files. `wrangler r2 bulk put` sends each one
through Cloudflare's API, which allows about four requests a second; at wrangler's
default of 20 at once, most batches came back "429: Too Many Requests". Brajeshwar would
rather the upload take days than lean on Cloudflare, so `tools/upload_tiles.py` now sends
two at a time and paces itself to two files a second, half the limit.

At that pace a view takes about three hours, so the upload runs while Brajeshwar sleeps:
a launchd agent (`launchd/com.oinam.manipur.upload.plist`, installed with `mise run
schedule-on`) starts `mise run upload-night` at 22:00, which uploads the finished views'
pyramids and stops starting batches at 5:00. Started outside that window, as when the Mac
wakes late, it does nothing. About 50,000 files a night puts the valley up in about ten
nights. Each run is logged in `logs/upload-night.log`.

Pyramids alone change nothing on the live site, since the manifest does not name them
yet. When every view is up, the job posts a macOS notification; then push the code, wait
for the deploy, and run `mise run upload` to send the index files, which switches the site
over in seconds. That last step stays by hand, because it publishes. `mise run
schedule-off` removes the agent.

The first night uploaded nothing. The agent ran as `ProcessType` Background, which puts
its disk reads behind everyone else's on the same drive; the valley build was writing
tiles there until 01:14, and the uploader sat in its first read of `out/` from 22:00 until
a foreground `ls` of the drive at 06:08 freed it, with 3 seconds of CPU in eight hours.
Why it stayed stuck after the build finished is not known. That read came before the
uploader worked out its 5:00 deadline, so it took the next 5:00, a day later, and kept
going through the morning. The agent now runs as Standard, since it is paced by the
network and gains nothing from a lower tier, and the deadline is fixed before the first
read.

## 2026-11-12 — Tiles go up through R2's S3 endpoint

Two files a second meant about ten nights for the valley. The four-a-second limit belongs
to Cloudflare's account API, which `wrangler r2 bulk put` goes through; R2's
S3-compatible endpoint does not share it. `tools/upload_tiles.py` now copies each
finished pyramid with rclone over that endpoint, 32 files at a time, which should put the
valley up in an hour or two. rclone lists what the bucket has and sends only what is
missing, so the per-batch records are gone and a pyramid is recorded once it is complete.
Headers stay as before: a year's immutable caching for tiles, `no-cache` for the index
files, which still go last.

It needs an R2 API token limited to Object Read & Write on `manipur-tiles`, kept in
`.env` as `R2_ACCESS_KEY_ID` and `R2_SECRET_ACCESS_KEY`; rclone is pinned in mise and
configured from those, with no config file. The first run sent the rest of the valley,
570,704 files in all, in under four hours, so the nightly schedule, its launchd agent,
and the `upload-night` and `schedule-*` tasks are gone.

## 2026-11-12 — River names ride along their rivers

Rivers are labeled in the viewer, not baked into the tiles, so a name can follow the
river as the map moves. `flow.json`, which already carries every waterway for the water
animation, now also names the 19 named rivers (OSM `waterway=river`), so no new file or
source is needed. Each river gets one label, set on the point of the river nearest the
middle of the screen and turned along it, never upside down; panning slides it along
the river. Longer rivers claim their spot first when two labels would meet, and none
show when the whole valley is in view. They are italic and pale blue, a placeholder
style for Brajeshwar to settle.

## 2026-11-12 — Four views, north up

Brajeshwar cut the turns from 24 views in 15 degree steps to four quarter turns, since
every view is rendered, stored, and uploaded for every place the map grows to: about
1 GB and half an hour per view for the valley. The site shows 315 (north up, where it
now opens), 45, 135, and 225; `RENDERED_VIEWS` in `detail.py` names them, and `frames`
and `build` render only those.

View 0 is still the frame that search places, flow lines, and links are written in, so
none of those files changed. It is planned, its canvas and offsets written to
`manifest.json`, but never rendered. Links shared earlier can name any of the 24 views;
the site manifest now carries every view's frame in the original Imphal canvas
(`links`, from `assets/hash_origin.json`), and the viewer opens such a link at the same
spot in the nearest view it shows, north up when two are as near. A bare link, which
meant view 0, opens north up.

The other 20 views' pyramids are gone from R2. Their local copies, about 20 GB, are in
`out/valley/retired/` on the external drive, with the full 24-view `views.json`, outside
`tiles/` so a re-tile cannot delete them. To bring one back, move its pyramid into
`tiles/pyramid/`, add it to `RENDERED_VIEWS` and `tiles/views.json`, and upload.

The viewer reads its views from the manifest instead of a fixed list, so it works with
either manifest, which set the order: push and deploy, upload the four-view manifest,
check the site, then delete from R2.

On 2026-11-12 Brajeshwar had every pyramid the live manifest does not name deleted from
R2: the old Imphal map's 24 (about 3.5 GB; local copies stay in
`out/imphal/tiles/pyramid/`) and `1b7ede2a65`, an unfinished upload with no `.dzi` and
no local copy. The bucket now holds only the four live views and the index files.

## 2026-11-14 — Weather in the info panel, read by the browser

Brajeshwar asked for the current weather in the info panel, as on his Greenage map. The
viewer asks Open-Meteo for Imphal's temperature, weather code, and wind when the page
opens and every ten minutes after, and shows them in words in the panel's bar, where
they stay when the panel is collapsed. The browser asks Open-Meteo directly, not through
the Worker: there is no key to hide, each visitor's calls count against their own
address and not one shared one, and a failed lookup just leaves the bar without a
reading. The weather is words only; it does not change the map.

The panel now drags by its bar and remembers where it was left, in the browser's own
storage. It is placed by its left and bottom edges, so collapsing still folds it
downward. A double click on the bar puts it back in its corner.

## 2026-11-14 — OpenSky off the site

OpenSky's staff answered the license request on 2026-11-11: a live public site needs a
written license even when it is non-commercial and ad-free, they have no free one, and
theirs costs $99 a month. That overrides the automated reply the site had relied on.
Its receivers never heard a flight within 125 km of Imphal anyway, so Brajeshwar chose
not to pay and to take OpenSky out. This replaces "Live planes on the site" and "The
Mac relays OpenSky" above.

The Worker now serves only AeroDataBox's timetable. It no longer polls OpenSky or
accepts the relay's posts, and the first request after the deploy deletes the snapshots
and sightings it had kept. The viewer draws planes from the timetable alone, labeled
"scheduled, not live"; the "2 min ago" planes, the panel's ticks, and its list of
sightings are gone, with OpenSky's credit. `tools/log_aircraft.py` stays as a private
coverage check and no longer posts to the site. A receiver near the airport is still
the only way to real approaches, and is still open in `docs/AIRCRAFT.md`.

## 2026-11-14 — Arrivals land from the southwest

Brajeshwar pointed out that planes at Imphal land from the other end than the map
showed. Arrivals now come in from the southwest and land on runway 04, heading
northeast; departures still take off on 22 toward the southwest, which he confirmed is
right. So planes arrive and leave over the same side. This replaces "both
on runway 22" in "Planes from the timetable" above. A landing plane still leaves by the
southern taxiway, which it now reaches about 1,500 m past the threshold.
