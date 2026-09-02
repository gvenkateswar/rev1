# Painted Asset Kit — Chola: Tides of Bronze

The game looks for PNG files in `chola-platformer/assets/` using the exact
filenames below. Any file that is missing falls back to the built-in procedural
art, so you can add assets one at a time and the game keeps working at every step.

## Workflow

1. Copy any block below into ChatGPT, whole. Each block is fully self-contained —
   style, dimensions, PNG requirements, and filename are all inside it.
2. Download the result, rename it to the filename stated at the end of the block
   (convert to `.png` if the download is `.webp`), and drop it in `assets/`.
3. Open `chola-platformer/index.html` in a browser to see it in the game.
4. Consistency tip: the prompts repeat the full character description so they work
   in any order, but generating all five hero poses in one ChatGPT conversation
   (idle first) makes the poses match even better. Same for the two guard poses.
5. Characters must face right — the engine flips them for the other direction.
   If one comes back facing left, regenerate or mirror it in any editor.

The claude.ai artifact build cannot load these files and keeps the procedural
look; the painted version shows when the game runs from the repo, locally or on
GitHub Pages.

---

## 1 · `l1_far.png` — Thanjavur backdrop

```
Generate this image: a wide painted background for a 2.5D side-scrolling video game. Dawn over Thanjavur, capital of the Chola empire, 1010 CE. The Brihadisvara temple dominates the middle distance: a steep pyramidal granite vimana of many diminishing tiers crowned by a single round capstone, flanked by smaller tiered gopuram gateway towers and long walled courtyards. The architecture is rendered as layered watercolor silhouettes that fade into warm morning haze — the nearest towers deep umber, the farthest almost dissolving into a parchment-gold sky. A pale, hazy sun disc in the upper right with soft god-rays. A line of palm crowns and low flat city rooftops runs along the bottom edge. One or two tiny crimson temple banners are the only saturated accents.

Composition rules: horizon line in the lower third of the frame; the bottom 25% of the image stays simple, dark, and low-contrast so game platforms drawn in front of it stay readable; no object of interest at the exact left or right edge, and both edges must close in similar tone and value so the image can repeat sideways.

Style: hand-painted 2D video-game concept art in an ink-and-watercolor wash style. Muted sepia and parchment palette: warm beige #D9C69A, parchment gold #CDBA8C, umber #6B4E33, olive-grey shadows, with a single crimson accent #B5342A used sparingly. Soft atmospheric haze, visible dry-brush strokes and watercolor blooms, matte gouache finish, painterly soft edges, cinematic side-lighting. The mood of a moody stealth-action side-scroller set in medieval South India. No text, no watermark, no signature, no border, no photo-realism, no 3D render look.

Output: a landscape image, 1536×1024 pixels, as a PNG file. I will save this file as: l1_far.png
```

## 2 · `l2_far.png` — Nagapattinam harbor backdrop

```
Generate this image: a wide painted background for a 2.5D side-scrolling video game. Late golden afternoon over Nagapattinam, the great port of the Chola empire, circa 1020 CE. A calm sea horizon in the lower third of the frame, crowded with a fleet of anchored medieval Indian ocean-going ships: broad wooden hulls with high curved prows, single masts, furled and half-furled lateen-style sails, rigging lines. The ships are painted as layered warm-grey and umber silhouettes receding into amber sea haze. Along the bottom edge, hints of a busy quay: piling posts, coiled rope, stacked cargo bales, all in deep shadow. A low hazy sun on the left throws a broken golden path across the water; gulls appear as tiny ink flecks. One crimson pennant on the nearest mast is the only saturated accent.

Composition rules: horizon in the lower third; the bottom 25% of the image stays simple, dark, and low-contrast so game platforms drawn in front of it stay readable; no object of interest at the exact left or right edge, and both edges must close in similar tone and value so the image can repeat sideways.

Style: hand-painted 2D video-game concept art in an ink-and-watercolor wash style. Muted sepia and parchment palette: warm beige #D9C69A, parchment gold #CDBA8C, umber #6B4E33, olive-grey shadows, with a single crimson accent #B5342A used sparingly. Soft atmospheric haze, visible dry-brush strokes and watercolor blooms, matte gouache finish, painterly soft edges, cinematic side-lighting. The mood of a moody stealth-action side-scroller set in medieval South India. No text, no watermark, no signature, no border, no photo-realism, no 3D render look.

Output: a landscape image, 1536×1024 pixels, as a PNG file. I will save this file as: l2_far.png
```

## 3 · `l3_far.png` — Srivijaya jungle backdrop

```
Generate this image: a wide painted background for a 2.5D side-scrolling video game. Monsoon morning in Srivijaya, maritime Southeast Asia, 1025 CE. Steep jungle ridges recede in four or five layered planes of grey-green and olive watercolor wash, separated by drifting horizontal mist bands. Rising from the ridgelines are the silhouettes of terraced Buddhist stupa sanctuaries — stepped square bases, bell-shaped domes, tall spires — in the manner of Borobudur, half swallowed by canopy and mist. A pale white-green sun glows in the upper right behind thin cloud. Tree crowns and hanging vines frame the very bottom edge in deep shadow. A single distant crimson banner on one stupa terrace is the only saturated accent.

Composition rules: horizon in the lower third; the bottom 25% of the image stays simple, dark, and low-contrast so game platforms drawn in front of it stay readable; no object of interest at the exact left or right edge, and both edges must close in similar tone and value so the image can repeat sideways.

Style: hand-painted 2D video-game concept art in an ink-and-watercolor wash style. Muted sepia and parchment palette: warm beige #D9C69A, parchment gold #CDBA8C, umber #6B4E33, olive-grey shadows, with a single crimson accent #B5342A used sparingly. Soft atmospheric haze, visible dry-brush strokes and watercolor blooms, matte gouache finish, painterly soft edges, cinematic side-lighting. The mood of a moody stealth-action side-scroller set in medieval South India. No text, no watermark, no signature, no border, no photo-realism, no 3D render look.

Output: a landscape image, 1536×1024 pixels, as a PNG file. I will save this file as: l3_far.png
```

## 4 · `tex_stone.png` — granite block texture

```
Generate this image: a perfectly seamless, tileable texture of weathered granite temple masonry, hand-painted. Courses of large rectangular blocks in warm grey-brown stone, staggered joints, chisel marks and small chips, thin watercolor staining and moss shadow in the mortar lines, and one or two faint traces of old red lacquer paint in recessed carvings. Even, directionless lighting — no cast shadows from any single direction, no vignette, no darkening at the edges. All four edges must tile seamlessly with themselves. Flat frontal view, no perspective.

Style: hand-painted 2D video-game concept art in an ink-and-watercolor wash style. Muted sepia and parchment palette: warm beige #D9C69A, parchment gold #CDBA8C, umber #6B4E33, olive-grey shadows, with a single crimson accent #B5342A used sparingly. Visible dry-brush strokes and watercolor blooms, matte gouache finish, painterly soft edges. No text, no watermark, no signature, no border, no photo-realism, no 3D render look.

Output: a square image, 1024×1024 pixels, as a PNG file, seamlessly tileable on all four edges. I will save this file as: tex_stone.png
```

## 5 · `tex_wood.png` — teak deck texture

```
Generate this image: a perfectly seamless, tileable texture of weathered teak ship-deck planking, hand-painted. Horizontal planks of warm brown wood with visible grain painted in dry-brush strokes, iron nail heads, salt staining, small gaps of deep shadow between planks, and a rope-worn patch or two. Even, directionless lighting — no cast shadows from any single direction, no vignette, no darkening at the edges. All four edges must tile seamlessly with themselves. Flat frontal view, no perspective.

Style: hand-painted 2D video-game concept art in an ink-and-watercolor wash style. Muted sepia and parchment palette: warm beige #D9C69A, parchment gold #CDBA8C, umber #6B4E33, olive-grey shadows, with a single crimson accent #B5342A used sparingly. Visible dry-brush strokes and watercolor blooms, matte gouache finish, painterly soft edges. No text, no watermark, no signature, no border, no photo-realism, no 3D render look.

Output: a square image, 1024×1024 pixels, as a PNG file, seamlessly tileable on all four edges. I will save this file as: tex_wood.png
```

## 6 · `hero_idle.png` — the hero, standing (generate this one first)

```
Generate this image: a full-body 2D video-game character on a fully transparent background.

The character: a young Tamil warrior of the Chola navy, athletic build. He wears a dark charcoal cotton hooded robe — the deep pointed hood is up, his face mostly in shadow with a warm-lit jawline — a knee-length skirted lower robe, and a brilliant crimson silk sash wound at the waist with two long tails hanging behind him. A bronze-hilted, slightly curved south-Indian sword is sheathed diagonally across his back. Bare forearms with a single bronze bangle, simple dark leather sandals.

The pose: standing alert in relaxed profile, FACING RIGHT, knees slightly bent, hands loose and ready. Full body visible from head to feet with roughly 5% empty margin all around; feet at the bottom of the frame.

Style: hand-painted 2D video-game concept art in an ink-and-watercolor wash style. Muted sepia and parchment palette with the crimson sash as the strongest accent (#B5342A). Visible dry-brush strokes, matte gouache finish, painterly soft edges, crisp readable silhouette, cinematic side-lighting. No text, no watermark, no signature, no border, no photo-realism, no 3D render look.

Output: a portrait image, 1024×1536 pixels, as a PNG file with a fully transparent background. I will save this file as: hero_idle.png
```

## 7 · `hero_run_a.png` — the hero, run stride A

```
Generate this image: a full-body 2D video-game character on a fully transparent background.

The character: a young Tamil warrior of the Chola navy, athletic build. He wears a dark charcoal cotton hooded robe — the deep pointed hood is up, his face mostly in shadow with a warm-lit jawline — a knee-length skirted lower robe, and a brilliant crimson silk sash wound at the waist with two long tails hanging behind him. A bronze-hilted, slightly curved south-Indian sword is sheathed diagonally across his back. Bare forearms with a single bronze bangle, simple dark leather sandals.

The pose: a full sprint in profile, FACING RIGHT — right leg extended far forward, left leg trailing bent behind, torso leaning into the run, both sash tails and the hood streaming horizontally behind him, arms pumping. Full body visible with roughly 5% empty margin; feet near the bottom of the frame.

Style: hand-painted 2D video-game concept art in an ink-and-watercolor wash style. Muted sepia and parchment palette with the crimson sash as the strongest accent (#B5342A). Visible dry-brush strokes, matte gouache finish, painterly soft edges, crisp readable silhouette, cinematic side-lighting. No text, no watermark, no signature, no border, no photo-realism, no 3D render look.

Output: a portrait image, 1024×1536 pixels, as a PNG file with a fully transparent background. I will save this file as: hero_run_a.png
```

## 8 · `hero_run_b.png` — the hero, run stride B

```
Generate this image: a full-body 2D video-game character on a fully transparent background.

The character: a young Tamil warrior of the Chola navy, athletic build. He wears a dark charcoal cotton hooded robe — the deep pointed hood is up, his face mostly in shadow with a warm-lit jawline — a knee-length skirted lower robe, and a brilliant crimson silk sash wound at the waist with two long tails hanging behind him. A bronze-hilted, slightly curved south-Indian sword is sheathed diagonally across his back. Bare forearms with a single bronze bangle, simple dark leather sandals.

The pose: the opposite moment of a sprint stride in profile, FACING RIGHT — left leg planted under the body taking his weight, right leg folded and swinging through, arms in the opposite pumping position, sash tails swinging lower behind him. Full body visible with roughly 5% empty margin; feet near the bottom of the frame.

Style: hand-painted 2D video-game concept art in an ink-and-watercolor wash style. Muted sepia and parchment palette with the crimson sash as the strongest accent (#B5342A). Visible dry-brush strokes, matte gouache finish, painterly soft edges, crisp readable silhouette, cinematic side-lighting. No text, no watermark, no signature, no border, no photo-realism, no 3D render look.

Output: a portrait image, 1024×1536 pixels, as a PNG file with a fully transparent background. I will save this file as: hero_run_b.png
```

## 9 · `hero_jump.png` — the hero, airborne

```
Generate this image: a full-body 2D video-game character on a fully transparent background.

The character: a young Tamil warrior of the Chola navy, athletic build. He wears a dark charcoal cotton hooded robe — the deep pointed hood is up, his face mostly in shadow with a warm-lit jawline — a knee-length skirted lower robe, and a brilliant crimson silk sash wound at the waist with two long tails hanging behind him. A bronze-hilted, slightly curved south-Indian sword is sheathed diagonally across his back. Bare forearms with a single bronze bangle, simple dark leather sandals.

The pose: airborne mid-leap in profile, FACING RIGHT — knees tucked, body arched slightly forward, arms spread for balance, the robe skirt and both crimson sash tails billowing upward behind him. Centered in the frame with clear empty space below the feet.

Style: hand-painted 2D video-game concept art in an ink-and-watercolor wash style. Muted sepia and parchment palette with the crimson sash as the strongest accent (#B5342A). Visible dry-brush strokes, matte gouache finish, painterly soft edges, crisp readable silhouette, cinematic side-lighting. No text, no watermark, no signature, no border, no photo-realism, no 3D render look.

Output: a portrait image, 1024×1536 pixels, as a PNG file with a fully transparent background. I will save this file as: hero_jump.png
```

## 10 · `hero_attack.png` — the hero, sword slash

```
Generate this image: a full-body 2D video-game character on a fully transparent background.

The character: a young Tamil warrior of the Chola navy, athletic build. He wears a dark charcoal cotton hooded robe — the deep pointed hood is up, his face mostly in shadow with a warm-lit jawline — a knee-length skirted lower robe, and a brilliant crimson silk sash wound at the waist with two long tails hanging behind him. Bare forearms with a single bronze bangle, simple dark leather sandals. His bronze-hilted, slightly curved south-Indian sword is drawn and in his hand; the empty scabbard hangs across his back.

The pose: mid sword-slash in profile, FACING RIGHT — the curved blade sweeping forward at shoulder height in his right hand, a faint pale arc of motion behind the blade, weight on the front foot, robe and sash swinging with the strike. Full body visible with roughly 5% empty margin; feet near the bottom of the frame.

Style: hand-painted 2D video-game concept art in an ink-and-watercolor wash style. Muted sepia and parchment palette with the crimson sash as the strongest accent (#B5342A). Visible dry-brush strokes, matte gouache finish, painterly soft edges, crisp readable silhouette, cinematic side-lighting. No text, no watermark, no signature, no border, no photo-realism, no 3D render look.

Output: a portrait image, 1024×1536 pixels, as a PNG file with a fully transparent background. I will save this file as: hero_attack.png
```

## 11 · `guard_walk_a.png` — Chola guard, stride A

```
Generate this image: a full-body 2D video-game enemy character on a fully transparent background.

The character: a Chola imperial guard, stocky and vigilant. He wears deep crimson lamellar armor — horizontal rows of small rectangular lacquered plates over a dark tunic — a conical bronze helmet with a short red plume, and a round dark-wood shield slung on his back. He holds a long spear with a leaf-shaped iron head upright in his right hand.

The pose: mid-patrol stride in profile, FACING RIGHT — right leg forward taking his weight, left leg pushing off behind, spear upright. Full body visible with roughly 5% empty margin; feet at the bottom of the frame.

Style: hand-painted 2D video-game concept art in an ink-and-watercolor wash style. Muted sepia and parchment palette; his crimson armor (#B5342A family) is the strongest accent. Visible dry-brush strokes, matte gouache finish, painterly soft edges, crisp readable silhouette, cinematic side-lighting. No text, no watermark, no signature, no border, no photo-realism, no 3D render look.

Output: a portrait image, 1024×1536 pixels, as a PNG file with a fully transparent background. I will save this file as: guard_walk_a.png
```

## 12 · `guard_walk_b.png` — Chola guard, stride B

```
Generate this image: a full-body 2D video-game enemy character on a fully transparent background.

The character: a Chola imperial guard, stocky and vigilant. He wears deep crimson lamellar armor — horizontal rows of small rectangular lacquered plates over a dark tunic — a conical bronze helmet with a short red plume, and a round dark-wood shield slung on his back. He holds a long spear with a leaf-shaped iron head upright in his right hand.

The pose: the opposite patrol stride in profile, FACING RIGHT — left leg forward and planted, right leg trailing behind, spear still upright, the shield on his back catching a touch of rim light. Full body visible with roughly 5% empty margin; feet at the bottom of the frame.

Style: hand-painted 2D video-game concept art in an ink-and-watercolor wash style. Muted sepia and parchment palette; his crimson armor (#B5342A family) is the strongest accent. Visible dry-brush strokes, matte gouache finish, painterly soft edges, crisp readable silhouette, cinematic side-lighting. No text, no watermark, no signature, no border, no photo-realism, no 3D render look.

Output: a portrait image, 1024×1536 pixels, as a PNG file with a fully transparent background. I will save this file as: guard_walk_b.png
```

## 13 · `gate.png` — the torana crossing gate

```
Generate this image: a free-standing carved stone gateway on a fully transparent background, straight-on front view, for use as a 2D video-game prop.

The structure: a small South Indian torana gateway — two weathered granite pillars with carved lotus bands, supporting a single curved stone lintel whose ends sweep gently upward. A narrow crimson cloth pennant hangs from the center of the lintel, swaying slightly. A small burning brass oil lamp sits in a niche on each pillar, casting a warm glow on the stone around it. Faded traces of red lacquer remain in the carvings. The whole structure fills the frame height with small margins, and the pillar bases end cleanly at the bottom edge. Nothing behind the structure.

Style: hand-painted 2D video-game concept art in an ink-and-watercolor wash style. Muted sepia and parchment palette: warm beige #D9C69A, umber #6B4E33, olive-grey shadows, with the crimson pennant (#B5342A) as the strongest accent. Visible dry-brush strokes, matte gouache finish, painterly soft edges, crisp readable silhouette. No text, no watermark, no signature, no border, no photo-realism, no 3D render look.

Output: a portrait image, 1024×1536 pixels, as a PNG file with a fully transparent background. I will save this file as: gate.png
```

## 14 · `l1_mid.png` — Thanjavur mid-parallax band (advanced, attempt last)

```
Generate this image: a sparse horizontal band of palm trunks and palm crowns occupying ONLY the bottom half of the frame, painted as dark umber silhouettes with soft watercolor edges, for use as a parallax layer in a 2D video game. Nothing at all in the top half of the image — it must stay fully transparent. Left and right edges similar in density so the band can repeat sideways.

Style: hand-painted 2D video-game concept art in an ink-and-watercolor wash style, muted sepia and umber tones, visible dry-brush strokes, matte gouache finish. No text, no watermark, no signature, no border.

Output: a landscape image, 1536×1024 pixels, as a PNG file with a fully transparent background. I will save this file as: l1_mid.png
```

## 15 · `l2_mid.png` — Nagapattinam mid-parallax band (advanced)

```
Generate this image: a sparse horizontal band of wooden dock pilings with coiled rope and hanging fishing nets occupying ONLY the bottom half of the frame, painted as dark umber silhouettes with soft watercolor edges, for use as a parallax layer in a 2D video game. Nothing at all in the top half of the image — it must stay fully transparent. Left and right edges similar in density so the band can repeat sideways.

Style: hand-painted 2D video-game concept art in an ink-and-watercolor wash style, muted sepia and umber tones, visible dry-brush strokes, matte gouache finish. No text, no watermark, no signature, no border.

Output: a landscape image, 1536×1024 pixels, as a PNG file with a fully transparent background. I will save this file as: l2_mid.png
```

## 16 · `l3_mid.png` — Srivijaya mid-parallax band (advanced)

```
Generate this image: a sparse horizontal band of jungle trees and hanging vines occupying ONLY the bottom half of the frame, painted as dark olive-umber silhouettes with soft watercolor edges, for use as a parallax layer in a 2D video game. Nothing at all in the top half of the image — it must stay fully transparent. Left and right edges similar in density so the band can repeat sideways.

Style: hand-painted 2D video-game concept art in an ink-and-watercolor wash style, muted grey-green and umber tones, visible dry-brush strokes, matte gouache finish. No text, no watermark, no signature, no border.

Output: a landscape image, 1536×1024 pixels, as a PNG file with a fully transparent background. I will save this file as: l3_mid.png
```
