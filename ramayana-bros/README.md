# Ramayana Bros.

A side-scrolling platformer in the shape of the 1985 classic, cast with
characters from the Ramayana. Rama runs east through the Dandaka forest,
over the mountains of Kishkindha and into Lanka, where Ravana holds the
last gate.

Plain HTML5 canvas and vanilla JavaScript — no build step, no
dependencies, and no asset files. Every sprite, tile, backdrop and sound
is generated in code.

## Play

```sh
# open it directly
xdg-open ramayana-bros/index.html      # or: open index.html on macOS

# ...or serve it, if your browser is strict about file:// URLs
python3 -m http.server -d ramayana-bros 8000   # then visit localhost:8000
```

A single-file build is also checked in at
[`dist/ramayana-bros.html`](dist/ramayana-bros.html) — one HTML file with
everything inlined, which you can e-mail, drop on any static host, or open
straight off disk.

## Controls

| | |
|---|---|
| `←` `→` or `A` `D` | walk |
| `Z` / `Space` | jump — hold it longer to jump higher |
| `X` / `Shift` | run, and loose an arrow once you carry the bow |
| `↓` | duck (only when Rama is tall) |
| `P` / `Esc` | pause — and set the speed |
| `M` | mute |
| `Enter` | start / continue |

On a phone or tablet an on-screen D-pad and A/B buttons appear.

## Speed

Pause and press `←` / `→` to move between **calm**, **steady** (the
default) and **brisk**. The choice is remembered.

This is a change of time scale rather than a difficulty setting: every
velocity is multiplied by the tempo and every acceleration by its square,
which slows the game down without moving a single jump arc. A jump reaches
exactly the same height and carries exactly the same distance at all three
settings — measured at 140px apex and 3.9 tiles walking, 7.2 running — so
the same gaps clear and the same pillars are reachable whichever you pick.
The stage clock counts ground covered rather than seconds, so a slower
setting is not also a tighter time limit.

## The cast

**Rama** starts small. The three power-ups are hidden in lotus blocks:

| | |
|---|---|
| **Sanjeevani herb** | the healing herb Hanuman carried from the mountain — Rama grows tall and can take a hit and smash bricks |
| **Kodanda** | Rama's great bow — press run to shoot arrows |
| **Hanuman's blessing** | brief invincibility; anything Rama touches is scattered |

A lotus block gives the herb to small Rama and the bow to tall Rama, the
way the mushroom block gives the flower in the original. The blessing only
ever comes out of a block placed as one, so it never crowds out the bow.

Against him:

| | |
|---|---|
| **Rakshasas** | forest demons that trudge back and forth. Stomp them. |
| **Maricha** | the golden deer. Stomp him once and he curls up; kick the curled deer and he scythes through everything in his path — including Rama on the way back. |
| **Kakasura** | crow demons that circle in the air. Stompable, but they sit exactly where you want to jump. |
| **Ravana** | the ten-headed king of Lanka. Six hits — arrows, a stomp on the heads, or a kicked deer — and his ward over the ashoka grove falls. Then reach Sita. |

Coins are worth 200 and every hundred of them is an extra life; the clock
pays out 50 a tick at the shrine that ends each stage.

## The three kandas

| | | |
|---|---|---|
| **1-1** | Dandaka Forest | gaps, pillars and a first look at the golden deer |
| **1-2** | Kishkindha Heights | rope bridges over open water, and the bow |
| **1-3** | Lanka | molten rock, the gate of the fortress, and Ravana |

Each stage has a **stepwell** — a covered kerb somewhere along the road.
Stand on it and press `↓` to drop into a lamplit room of stone arches,
full of coins and with a power-up in the blocks. Walk into the archway at
the far end and Rama climbs out well down the stage, past whatever he
skipped. The surface is set aside whole while he is down there — spent
blocks, smashed bricks, enemies where he left them — and put back exactly
as it was.

The stage ends at a **gopuram**, a stepped temple tower with a lamp in the
sanctum that lights as Rama reaches it.

## Layout

```
index.html              page shell, touch controls
css/style.css           frame, D-pad, page chrome
js/audio.js             WebAudio sound effects and the looping tunes
js/sprites.js           every sprite, tile and backdrop, drawn as pixels
js/levels.js            the three level grids, built through a small helper
js/game.js              engine: physics, entities, camera, HUD, game loop
tools/bundle.js         inlines everything into dist/ramayana-bros.html
dist/ramayana-bros.html the single-file build
```

Nothing is minified or generated except `dist/`. To rebuild it after a
change:

```sh
node tools/bundle.js
```

## Notes on the code

**Levels** are 15-row tile grids assembled by a builder
(`g.ground()`, `g.pillar()`, `g.stair()`, `g.put()`) rather than by
hand-aligned ASCII, so a feature can be moved by changing one column
number. The comment at the top of `js/levels.js` lists the tile legend and
the geometry rules the layouts obey — a held jump clears about 54px, so
pillars are never more than three tiles tall and gaps never more than
three tiles wide.

**Physics** runs on a fixed 60-tick timestep that is independent of the
display: the same 60 ticks a second on a 60Hz panel and on a 240Hz one.
There are three gravities, as the original had: light while the jump
button is held, heavier once it is released, heaviest on the way down. A
tap clears about two tiles and a held jump about three and a half. Ground
contact carries six frames of coyote time and the jump button is buffered
for eight, so jumps at the edge of a ledge or a beat early still fire. Pace
comes from `TEMPO` alone (see **Speed** above), so retuning the feel never
invalidates a level.

**Sprites** are plotted as rectangles on the 16px grid through a pen that
mirrors horizontally, so each character is only ever drawn facing right.

**Scenes** are just grids of rows, so a stepwell room loads through the
same `loadScene()` as a whole stage. Going underground pushes the surface
onto `G.surface` — its tiles, entities and markers by reference — and
climbing out restores it, which is why the room can never lose progress
made above it.

While the page is open, `RamayanaBros` in the browser console is the live
game state — `RamayanaBros.warp(2)` jumps straight to Lanka,
`RamayanaBros.setSpeed(0)` drops to the calm tempo, and
`RamayanaBros.player.bow = true` hands Rama the Kodanda. Useful when
editing levels.
