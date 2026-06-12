# World History Atlas

An interactive map of world states and territories with a timeline slider
(1000–2025). Drag the slider — or press play — and political boundaries
crossfade in real time to show the world as it existed at that moment.

- At **1770** the east coast of North America shows the **British American
  colonies** (part of the United Kingdom).
- At **1776** it becomes the **United States of America**.
- Through the **1800s** you can watch the US expand westward, empires rise
  and fall, and the modern map take shape.

## Run it

No build step — it's a fully self-contained static site (Leaflet and all
boundary data are vendored, no internet needed):

```bash
cd historical-map
python3 -m http.server 8000
# open http://localhost:8000
```

## Controls

| Control | Action |
| --- | --- |
| Timeline slider | Scrub to any year |
| ▶ button / Space | Play / pause the animation |
| ← / → (Shift for ±10) | Step through years |
| Hover a territory | Name + sovereign ("part of …") |
| Scroll / drag on map | Zoom and pan |

## How it works

- **Data**: 27 world snapshots from
  [aourednik/historical-basemaps](https://github.com/aourednik/historical-basemaps)
  (CC BY-NC-SA), topologically simplified with mapshaper to ~6 MB total
  (`data/world_<year>.json`). Tick marks on the slider show where snapshots are.
- **Year → snapshot**: each year displays the most recent snapshot in effect.
  A small override table handles cases the world dates differently than the
  source data — e.g. the 1783 (Treaty of Paris) boundaries are shown starting
  in 1776, when independence was declared.
- **Seamless transitions**: two stacked map panes crossfade when the slider
  crosses a snapshot boundary, and each sovereign state gets a stable,
  deterministic color, so a country keeps its color as its territory changes —
  borders appear to flow rather than flicker.
- **No tile server**: the polygons *are* the map, drawn on canvas over a
  solid ocean, so the app works completely offline.

## Caveats

Boundary precision is inherently limited for older eras, and the world only
changes when a snapshot changes (e.g. nothing moves between 1494 and 1499).
Adding more snapshot years from the source dataset is just a matter of
dropping another `world_<year>.json` into `data/` and adding the year to
`SNAPSHOT_YEARS` in `app.js`.
