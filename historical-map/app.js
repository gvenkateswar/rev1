/* World History Atlas
 *
 * Boundary data: aourednik/historical-basemaps (CC BY-NC-SA), simplified.
 * The dataset is a series of snapshot years; for any year on the slider we
 * show the snapshot that was in effect at that moment and crossfade between
 * snapshots as the slider crosses a boundary. Colors are keyed to the
 * sovereign power, so a state keeps its color as its territory grows or
 * shrinks across snapshots.
 */
"use strict";

const SNAPSHOT_YEARS = [
  1000, 1100, 1200, 1279, 1300, 1400, 1492, 1500, 1530, 1600, 1650, 1700,
  1715, 1783, 1800, 1815, 1880, 1900, 1914, 1920, 1930, 1938, 1945, 1960,
  1994, 2000, 2010,
];

// A snapshot normally takes effect at its own year, but a few represent a
// change the world dates differently: the 1783 (Treaty of Paris) borders are
// shown from 1776, when the United States declared independence.
const EFFECTIVE_FROM = { 1783: 1776 };

const MIN_YEAR = 1000;
const MAX_YEAR = 2025;
const FADE_MS = 450;
const PLAY_STEP_MS = 90;

const SNAPSHOTS = SNAPSHOT_YEARS.map((y) => ({
  year: y,
  from: EFFECTIVE_FROM[y] ?? y,
  url: `data/world_${y}.json`,
}));

// ---------------------------------------------------------------- colors

// Recognizable colors for major powers; everything else gets a stable
// pastel derived from a hash of its name.
const FIXED_COLORS = {
  "United Kingdom": "#e08896",
  "Great Britain": "#e08896",
  England: "#e08896",
  "British Empire": "#e08896",
  "United States of America": "#6f9fd8",
  France: "#8584d8",
  Spain: "#e0c45c",
  Portugal: "#6fbf8f",
  Russia: "#9fce7f",
  "Russian Empire": "#9fce7f",
  "Soviet Union": "#d2766a",
  "Ottoman Empire": "#c9a06a",
  China: "#e0a96a",
  "Qing China": "#e0a96a",
  "Holy Roman Empire": "#d8c79a",
  Netherlands: "#e9a35c",
  Japan: "#e6e0d0",
};

function hashStr(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function sovereignOf(props) {
  return props.SUBJECTO || props.PARTOF || props.NAME || "unclaimed";
}

function colorFor(props) {
  const key = sovereignOf(props);
  if (FIXED_COLORS[key]) return FIXED_COLORS[key];
  const h = hashStr(key);
  const hue = h % 360;
  const sat = 38 + ((h >>> 9) % 24);
  const light = 52 + ((h >>> 17) % 16);
  return `hsl(${hue}, ${sat}%, ${light}%)`;
}

function baseStyle(feature) {
  return {
    fillColor: colorFor(feature.properties),
    fillOpacity: 0.88,
    color: "rgba(12, 34, 53, 0.85)", // border = ocean color, reads as a gap
    weight: 0.8,
  };
}

const HIGHLIGHT_STYLE = { weight: 2.2, color: "#f3e9d2", fillOpacity: 1 };

// ---------------------------------------------------------------- map

const map = L.map("map", {
  zoomControl: true,
  attributionControl: true,
  worldCopyJump: false,
  minZoom: 1.5,
  maxZoom: 9,
  zoomSnap: 0.25,
  maxBounds: [
    [-87, -220],
    [87, 220],
  ],
  maxBoundsViscosity: 0.7,
});
map.setView([28, 5], 2.25);
map.attributionControl.setPrefix(false);
map.attributionControl.addAttribution(
  'Boundaries: <a href="https://github.com/aourednik/historical-basemaps" target="_blank" rel="noopener">historical-basemaps</a> (CC BY-NC-SA)'
);

// Two stacked panes; the incoming snapshot fades in on top of the outgoing one.
const paneSlots = [0, 1].map((i) => {
  const pane = map.createPane(`snapshot-${i}`);
  pane.classList.add("snapshot-pane");
  pane.style.zIndex = 400 + i;
  pane.style.opacity = "0";
  return { paneName: `snapshot-${i}`, pane, layer: null, renderer: null };
});
let frontSlot = -1; // slot currently visible

// ---------------------------------------------------------------- data

const cache = new Map(); // snapshot index -> Promise<GeoJSON>
const loadingBadge = document.getElementById("loading-badge");
let pendingLoads = 0;

function loadSnapshot(idx) {
  if (!cache.has(idx)) {
    pendingLoads++;
    loadingBadge.hidden = false;
    const p = fetch(SNAPSHOTS[idx].url)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status} for ${SNAPSHOTS[idx].url}`);
        return r.json();
      })
      .finally(() => {
        pendingLoads--;
        if (pendingLoads <= 0) loadingBadge.hidden = true;
      });
    p.catch(() => cache.delete(idx)); // allow retry after a failure
    cache.set(idx, p);
  }
  return cache.get(idx);
}

function prefetchAll() {
  let i = 0;
  const next = () => {
    while (i < SNAPSHOTS.length && cache.has(i)) i++;
    if (i >= SNAPSHOTS.length) return;
    loadSnapshot(i++).catch(() => {}).then(() => setTimeout(next, 50));
  };
  next();
}

// ---------------------------------------------------------------- layers

function tooltipHtml(props) {
  const name = props.NAME || "Terra incognita";
  const sovereign = sovereignOf(props);
  let html = `<b>${name}</b>`;
  if (sovereign && sovereign !== name) {
    html += `<div class="tip-sub">part of ${sovereign}</div>`;
  }
  return html;
}

function buildLayer(geojson, slot) {
  const renderer = L.canvas({ pane: slot.paneName });
  return L.geoJSON(geojson, {
    renderer,
    pane: slot.paneName,
    style: baseStyle,
    onEachFeature: (feature, layer) => {
      layer.bindTooltip(tooltipHtml(feature.properties), {
        sticky: true,
        direction: "top",
        className: "territory-tip",
        opacity: 1,
      });
      layer.on("mouseover", () => layer.setStyle(HIGHLIGHT_STYLE));
      layer.on("mouseout", () => layer.setStyle(baseStyle(feature)));
    },
  });
}

let shownIdx = -1; // snapshot index currently requested/visible
let removeTimer = null;

async function showSnapshot(idx) {
  if (idx === shownIdx) return;
  shownIdx = idx;

  let geojson;
  try {
    geojson = await loadSnapshot(idx);
  } catch (err) {
    console.error("Failed to load snapshot", SNAPSHOTS[idx].year, err);
    return;
  }
  if (shownIdx !== idx) return; // superseded while loading

  const back = paneSlots[frontSlot === 0 ? 1 : 0];
  const front = frontSlot >= 0 ? paneSlots[frontSlot] : null;

  // If a previous fade-out is still pending, finish it now.
  if (removeTimer) {
    clearTimeout(removeTimer);
    removeTimer = null;
  }
  if (back.layer) {
    map.removeLayer(back.layer);
    back.layer = null;
  }

  back.layer = buildLayer(geojson, back);
  back.layer.addTo(map);
  back.pane.style.zIndex = "401";
  if (front) front.pane.style.zIndex = "400";

  // Force a style flush so the opacity transition actually runs.
  back.pane.style.opacity = "0";
  void back.pane.offsetWidth;
  back.pane.style.opacity = "1";
  if (front) front.pane.style.opacity = "0";

  frontSlot = paneSlots.indexOf(back);

  if (front) {
    removeTimer = setTimeout(() => {
      removeTimer = null;
      if (front.layer && paneSlots.indexOf(front) !== frontSlot) {
        map.removeLayer(front.layer);
        front.layer = null;
      }
    }, FADE_MS + 80);
  }
}

// ---------------------------------------------------------------- timeline

const slider = document.getElementById("year-slider");
const yearLabel = document.getElementById("year-label");
const snapshotLabel = document.getElementById("snapshot-label");
const playBtn = document.getElementById("play-btn");

slider.min = MIN_YEAR;
slider.max = MAX_YEAR;

function snapshotIndexFor(year) {
  let idx = 0;
  for (let i = 0; i < SNAPSHOTS.length; i++) {
    if (SNAPSHOTS[i].from <= year) idx = i;
    else break;
  }
  return idx;
}

function setYear(year, fromSlider) {
  year = Math.max(MIN_YEAR, Math.min(MAX_YEAR, Math.round(year)));
  if (!fromSlider) slider.value = year;
  yearLabel.textContent = year;
  const idx = snapshotIndexFor(year);
  const snap = SNAPSHOTS[idx];
  snapshotLabel.textContent =
    snap.from !== snap.year
      ? `boundaries of ${snap.year} (in effect from ${snap.from})`
      : `boundaries as of ${snap.year}`;
  showSnapshot(idx);
}

slider.addEventListener("input", () => setYear(+slider.value, true));

// tick marks at each snapshot's effective year
const ticksEl = document.getElementById("ticks");
for (const snap of SNAPSHOTS) {
  const pct = ((snap.from - MIN_YEAR) / (MAX_YEAR - MIN_YEAR)) * 100;
  const tick = document.createElement("div");
  tick.className = "tick";
  tick.style.left = `${pct}%`;
  ticksEl.appendChild(tick);
  if ([1000, 1300, 1600, 1776, 1900, 2010].includes(snap.from)) {
    const label = document.createElement("div");
    label.className = "tick-label";
    label.style.left = `${pct}%`;
    label.textContent = snap.from;
    ticksEl.appendChild(label);
  }
}

// ---------------------------------------------------------------- playback

let playTimer = null;

function stopPlayback() {
  if (playTimer) clearInterval(playTimer);
  playTimer = null;
  playBtn.innerHTML = "&#9654;";
  playBtn.setAttribute("aria-label", "Play");
}

function startPlayback() {
  if (+slider.value >= MAX_YEAR) setYear(MIN_YEAR);
  playTimer = setInterval(() => {
    const y = +slider.value + 1;
    setYear(y);
    if (y >= MAX_YEAR) stopPlayback();
  }, PLAY_STEP_MS);
  playBtn.innerHTML = "&#10074;&#10074;";
  playBtn.setAttribute("aria-label", "Pause");
}

playBtn.addEventListener("click", () => (playTimer ? stopPlayback() : startPlayback()));

document.addEventListener("keydown", (e) => {
  if (e.target === slider) return; // native arrows already work there
  if (e.code === "Space") {
    e.preventDefault();
    playTimer ? stopPlayback() : startPlayback();
  } else if (e.key === "ArrowRight") {
    setYear(+slider.value + (e.shiftKey ? 10 : 1));
  } else if (e.key === "ArrowLeft") {
    setYear(+slider.value - (e.shiftKey ? 10 : 1));
  }
});

// ---------------------------------------------------------------- start

setYear(+slider.value);
prefetchAll();
