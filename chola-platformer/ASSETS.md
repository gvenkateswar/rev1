# Painted Asset Kit — Chola: Tides of Bronze

The game now has an asset pipeline. Drop PNG files into `chola-platformer/assets/`
using the exact filenames below, open `index.html`, and the renderer uses them
automatically. Any file that is missing falls back to the built-in procedural art,
so you can add assets one at a time and the game keeps working at every step.

## How to generate (ChatGPT / DALL-E / gpt-image)

1. **Start every image request with the STYLE CORE block** (below). Consistency across
   assets comes from repeating it verbatim.
2. **Generate the hero in one conversation.** Make `hero_idle` first, then for each
   other pose say *"Same exact character, same style and colors, now …"* so the model
   keeps the design. Same for the two guard poses.
3. **For characters, textures, and the gate, explicitly request "PNG with transparent
   background"** (characters and gate) or "perfectly seamless tileable texture" (textures).
4. Download, rename to the manifest filename, convert to `.png` if the download is
   `.webp`, and drop it in `assets/`.
5. Test locally by opening `index.html` in a browser (or push and use GitHub Pages).

## Manifest

| File | Size / shape | Transparent? | Used for |
|---|---|---|---|
| `l1_far.png` | 1536×1024 landscape | no | Thanjavur painted backdrop (sky + temple skyline) |
| `l2_far.png` | 1536×1024 landscape | no | Nagapattinam harbor backdrop |
| `l3_far.png` | 1536×1024 landscape | no | Srivijaya jungle backdrop |
| `l1_mid.png` `l2_mid.png` `l3_mid.png` | 1536×1024 | **yes** (advanced, optional) | closer parallax band drawn over the backdrop |
| `tex_stone.png` | 1024×1024 | no, seamless tile | stone platform surfaces |
| `tex_wood.png` | 1024×1024 | no, seamless tile | dock / ship / bridge surfaces |
| `hero_idle.png` | 1024×1536 portrait | **yes** | hero standing |
| `hero_run_a.png` / `hero_run_b.png` | 1024×1536 | **yes** | run cycle (two alternating strides) |
| `hero_jump.png` | 1024×1536 | **yes** | airborne |
| `hero_attack.png` | 1024×1536 | **yes** | sword slash |
| `guard_walk_a.png` / `guard_walk_b.png` | 1024×1536 | **yes** | patrolling guard strides |
| `gate.png` | 1024×1536 portrait | **yes** | the torana crossing gates |

Backdrops are mirror-tiled by the engine, so seams are hidden automatically — but
matching tone on the left and right edges still helps. Characters must face RIGHT;
the engine flips them for the other direction.

---

## STYLE CORE (paste at the top of every prompt)

> Hand-painted 2D video-game concept art in an ink-and-watercolor wash style.
> Muted sepia and parchment palette: warm beige #D9C69A, parchment gold #CDBA8C,
> umber #6B4E33, olive-grey shadows, with a single crimson accent #B5342A used
> sparingly. Soft atmospheric haze, visible dry-brush strokes and watercolor blooms,
> matte gouache finish, painterly soft edges, cinematic side-lighting. The mood of a
> moody stealth-action side-scroller set in medieval South India. No text, no
> watermark, no signature, no border, no photo-realism, no 3D render look.

---

## 1 · `l1_far.png` — Thanjavur backdrop

> [STYLE CORE]
>
> A wide painted background for a 2.5D side-scrolling game, landscape 1536×1024.
> Dawn over Thanjavur, capital of the Chola empire, 1010 CE. The Brihadisvara temple
> dominates the middle distance: a steep pyramidal granite vimana of many diminishing
> tiers crowned by a single round capstone, flanked by smaller tiered gopuram gateway
> towers and long walled courtyards. Architecture rendered as layered watercolor
> silhouettes that fade into warm morning haze — the nearest towers deep umber, the
> farthest almost dissolving into a parchment-gold sky. A pale, hazy sun disc in the
> upper right with soft god-rays. A line of palm crowns and low flat city rooftops
> runs along the bottom edge. One or two tiny crimson temple banners as the only
> saturated accents.
>
> Composition rules: horizon line in the lower third of the frame; the bottom 25% of
> the image stays simple, dark, and low-contrast so game platforms drawn in front of
> it stay readable; no object of interest at the exact left or right edge, and both
> edges close in similar tone and value so the image can repeat sideways.

## 2 · `l2_far.png` — Nagapattinam harbor backdrop

> [STYLE CORE]
>
> A wide painted background for a 2.5D side-scrolling game, landscape 1536×1024.
> Late golden afternoon over Nagapattinam, the great port of the Chola empire,
> circa 1020 CE. A calm sea horizon in the lower third, crowded with a fleet of
> anchored medieval Indian ocean-going ships: broad wooden hulls with high curved
> prows, single masts, furled and half-furled lateen-style sails, rigging lines.
> Ships painted as layered warm-grey and umber silhouettes receding into amber sea
> haze. Along the bottom edge, hints of a busy quay: piling posts, coiled rope,
> stacked cargo bales, all in deep shadow. A low hazy sun on the left throws a
> broken golden path across the water; gulls as tiny ink flecks. One crimson
> pennant on the nearest mast as the only saturated accent.
>
> Composition rules: horizon in the lower third; the bottom 25% simple, dark, and
> low-contrast so game platforms read in front; left and right edges similar in tone
> and value so the image can repeat sideways.

## 3 · `l3_far.png` — Srivijaya jungle backdrop

> [STYLE CORE]
>
> A wide painted background for a 2.5D side-scrolling game, landscape 1536×1024.
> Monsoon morning in Srivijaya, maritime Southeast Asia, 1025 CE. Steep jungle
> ridges recede in four or five layered planes of grey-green and olive watercolor
> wash, separated by drifting horizontal mist bands. Rising from the ridgelines,
> the silhouettes of terraced Buddhist stupa sanctuaries — stepped square bases,
> bell-shaped domes, tall spires — in the manner of Borobudur, half swallowed by
> canopy and mist. A pale white-green sun glows high right behind thin cloud.
> Tree crowns and hanging vines frame the very bottom edge in deep shadow.
> A single distant crimson banner on one stupa terrace as the only saturated accent.
>
> Composition rules: horizon in the lower third; bottom 25% simple, dark,
> low-contrast; left and right edges similar in tone and value for sideways repeat.

## 4 · `tex_stone.png` — granite block texture

> [STYLE CORE]
>
> A perfectly seamless, tileable 1024×1024 texture of weathered granite temple
> masonry, hand-painted. Courses of large rectangular blocks in warm grey-brown
> stone, staggered joints, chisel marks and small chips, thin watercolor staining
> and moss shadow in the mortar lines, one or two faint traces of old red lacquer
> paint in recessed carvings. Even, directionless lighting — no cast shadows from
> any single direction, no vignette, no darkening at the edges. All four edges must
> tile seamlessly with themselves. Flat frontal view, no perspective.

## 5 · `tex_wood.png` — teak deck texture

> [STYLE CORE]
>
> A perfectly seamless, tileable 1024×1024 texture of weathered teak ship-deck
> planking, hand-painted. Horizontal planks of warm brown wood, visible grain
> painted with dry-brush strokes, iron nail heads, salt staining, small gaps of
> deep shadow between planks, a rope-worn patch or two. Even, directionless
> lighting — no cast shadows from a single direction, no vignette, no edge
> darkening. All four edges must tile seamlessly. Flat frontal view.

## 6 · `hero_idle.png` — the hero (generate FIRST)

> [STYLE CORE]
>
> A full-body 2D game character on a fully transparent background, PNG, portrait
> 1024×1536. A young Tamil warrior of the Chola navy, athletic build. He wears a
> dark charcoal cotton hooded robe — deep pointed hood up, face mostly in shadow
> with a warm-lit jawline — a knee-length skirted lower robe, and a brilliant
> crimson silk sash wound at the waist with two long tails hanging behind him.
> A bronze-hilted, slightly curved south-Indian sword is sheathed diagonally across
> his back. Bare forearms with a single bronze bangle, simple dark leather sandals.
> Standing alert in relaxed profile FACING RIGHT, knees slightly bent, hands loose
> and ready. Full body visible head to feet with roughly 5% empty margin all
> around; feet at the bottom of the frame. Painterly gouache rendering with soft
> edges, crisp readable silhouette.

## 7 · `hero_run_a.png`

> Same exact character, same style, colors, and framing, PNG with transparent
> background, portrait 1024×1536, still FACING RIGHT: now in a full sprint —
> right leg extended far forward, left leg trailing bent behind, torso leaning
> into the run, both sash tails and the hood streaming horizontally behind him,
> arms pumping. Feet near the bottom of the frame, full body visible.

## 8 · `hero_run_b.png`

> Same exact character, same style, colors, and framing, PNG with transparent
> background, portrait 1024×1536, still FACING RIGHT: the opposite moment of the
> sprint stride — left leg planted under the body taking weight, right leg folded
> and swinging through, arms in the opposite pumping position, sash tails swinging
> lower. Feet near the bottom of the frame, full body visible.

## 9 · `hero_jump.png`

> Same exact character, same style, colors, and framing, PNG with transparent
> background, portrait 1024×1536, still FACING RIGHT: airborne mid-leap — knees
> tucked, body arched slightly forward, arms spread for balance, the robe skirt
> and both crimson sash tails billowing upward behind him. Centered in frame with
> clear space below the feet.

## 10 · `hero_attack.png`

> Same exact character, same style, colors, and framing, PNG with transparent
> background, portrait 1024×1536, still FACING RIGHT: mid sword-slash — the curved
> blade drawn and sweeping forward at shoulder height in his right hand, a faint
> pale arc of motion behind the blade, weight on the front foot, robe and sash
> swinging with the strike. Full body visible, feet near the bottom.

## 11 · `guard_walk_a.png` — Chola guard (new conversation is fine)

> [STYLE CORE]
>
> A full-body 2D game enemy character on a fully transparent background, PNG,
> portrait 1024×1536. A Chola imperial guard in deep crimson lamellar armor —
> horizontal rows of small rectangular lacquered plates over a dark tunic — a
> conical bronze helmet with a short red plume, a round dark-wood shield slung on
> his back, and a long spear with a leaf-shaped iron head held upright in his right
> hand. Stocky, vigilant, mid-patrol stride FACING RIGHT: right leg forward taking
> weight, left leg pushing off behind. Full body visible with about 5% margin,
> feet at the bottom of the frame. Painterly gouache, crisp silhouette.

## 12 · `guard_walk_b.png`

> Same exact guard, same style, colors, and framing, PNG with transparent
> background, portrait 1024×1536, still FACING RIGHT: the opposite patrol stride —
> left leg forward planted, right leg trailing, spear still upright, shield
> catching a touch of rim light. Full body, feet near the bottom.

## 13 · `gate.png` — the torana crossing gate

> [STYLE CORE]
>
> A free-standing carved stone gateway on a fully transparent background, PNG,
> portrait 1024×1536, straight-on front view. A small South Indian torana: two
> weathered granite pillars with carved lotus bands, supporting a single curved
> stone lintel whose ends sweep gently upward. A narrow crimson cloth pennant
> hangs from the center of the lintel, swaying slightly. A small burning brass oil
> lamp sits in a niche on each pillar, casting a warm glow on the stone around it.
> Faded traces of red lacquer in the carvings. The whole structure fills the frame
> height with small margins; the pillar bases end cleanly at the bottom edge.
> Painterly gouache, soft edges, readable silhouette, nothing behind it.

---

## Optional advanced: `l1_mid.png`, `l2_mid.png`, `l3_mid.png`

These draw in front of the backdrop at stronger parallax and need large fully
transparent regions, which image models get wrong more often — attempt these last.
Ask for: *"a sparse horizontal band of [palm trunks and crowns / dock pilings with
rope / jungle trees and hanging vines] occupying only the bottom half of the frame,
painted as dark umber silhouettes in the same style, on a FULLY transparent
background, 1536×1024, nothing in the top half."*

## Notes

- The engine scales everything, so exact pixel sizes matter less than aspect ratio:
  landscape for backdrops, square for textures, portrait for characters and the gate.
- If a character comes back facing left, either regenerate or mirror it in any editor —
  the engine assumes right-facing art.
- Keep total repo asset weight reasonable (a few MB each is fine); PNG or converted-to-PNG only.
- The claude.ai artifact build can't reach these files, so it keeps the procedural
  look; the painted version shows when the game runs from the repo (locally or via
  GitHub Pages).
