/* ------------------------------------------------------------------
 * Ramayana Bros. -- sprite art.
 *
 * Everything is still plotted as coloured rectangles on the 16px grid,
 * so the game ships as source with no binary assets. What makes it read
 * as a 16-bit game rather than an 8-bit one is how those rectangles are
 * coloured and composited:
 *
 *   - every material is a five-step ramp (shadow to highlight) instead
 *     of one or two flat colours, so surfaces turn in the light
 *   - characters carry a one-pixel keyline, dilated from their own
 *     silhouette, which is what separates a sprite from its background
 *   - tiles are bevelled and come in several variants, so a wall is not
 *     the same stamp repeated
 *   - backdrops are built from four or five parallax layers with
 *     atmospheric haze, gradients and bloom
 *
 * Sprites are drawn once into offscreen canvases and cached by every
 * parameter that changes their appearance, so the outline pass and the
 * shading cost nothing after the first frame that needs them.
 * ------------------------------------------------------------------ */

var Sprites = (function () {

  /* ============================ palettes ============================
   * Each ramp runs [shadow, dark, base, light, highlight].            */

  var R = {
    skin:   ['#1e4478', '#3a72b8', '#5b9de0', '#8fc4f5', '#c4e4ff'],
    hair:   ['#07060e', '#12101f', '#1e1a30', '#2e2848', '#463c68'],
    gold:   ['#7a4f06', '#b8730a', '#f0a81c', '#ffd042', '#fff2b0'],
    cloth:  ['#8a4a06', '#c2740c', '#f0a81c', '#ffc23d', '#ffe6a8'],
    white:  ['#8f8f9e', '#c0c0cc', '#e4e4ec', '#f4f4f8', '#ffffff'],
    red:    ['#5e1010', '#96201c', '#d0342c', '#f0685a', '#ff9c8c'],
    demon:  ['#1a3a14', '#2f6124', '#4e8c3a', '#74b356', '#a3d47c'],
    bone:   ['#8a7a4e', '#b8a878', '#dccfa2', '#f0e6c8', '#fffbe8'],
    deer:   ['#7a4c08', '#b8801e', '#f0b53c', '#ffd98a', '#fff0c8'],
    crow:   ['#0d0a16', '#1c1730', '#2f2748', '#473c6a', '#665896'],
    rav:    ['#1b0f2c', '#2e1c45', '#4a2f63', '#6b4a8a', '#8f6bb0'],
    ravskin:['#3d1f52', '#5c3378', '#7b4f9c', '#9d76bc', '#c0a3d8'],
    sari:   ['#0f4a2c', '#1d7346', '#3fa66b', '#6fc994', '#a6e6c0'],
    sariR:  ['#6b1420', '#a32633', '#d9434f', '#f0808a', '#ffb8bd'],
    steel:  ['#2c2f3e', '#4a4e63', '#6f7488', '#9aa0b4', '#c9d0dd'],
    wood:   ['#3a2410', '#5c3a18', '#8b5a2b', '#b8834a', '#d9a86e'],
    stone:  ['#3f3a44', '#6a6470', '#9a939f', '#c0b9c4', '#e4dee6'],
    sand:   ['#7a6a44', '#a8956a', '#cfc092', '#e8dcbc', '#faf2dc'],
    flame:  ['#8a2000', '#d04a08', '#ff8a2b', '#ffc23d', '#fff0b0']
  };

  var INK = '#0b0812';                 // the keyline every character wears

  /* Palette swaps while Hanuman's blessing is burning. */
  var STAR_SETS = [
    { skin: R.gold,  cloth: R.flame },
    { skin: R.demon, cloth: R.gold },
    { skin: R.sariR, cloth: R.skin },
    { skin: R.rav,   cloth: R.red }
  ];

  /* ============================ plumbing ============================ */

  function surface(w, h) {
    var c = document.createElement('canvas');
    c.width = w; c.height = h;
    var x = c.getContext('2d');
    x.imageSmoothingEnabled = false;
    return { canvas: c, ctx: x };
  }

  /* A pen in sprite-local pixels. Sprites are only ever authored facing
     right; `flip` mirrors them on the way out. */
  function pen(ctx, ox, oy, w, flip) {
    if (flip) {
      return function (x, y, pw, ph, col) {
        ctx.fillStyle = col;
        ctx.fillRect(ox + (w - x - pw), oy + y, pw, ph);
      };
    }
    return function (x, y, pw, ph, col) {
      ctx.fillStyle = col;
      ctx.fillRect(ox + x, oy + y, pw, ph);
    };
  }

  /* Bevelled block: lit from the upper left, in shadow on the lower right. */
  function bevel(r, x, y, w, h, ramp, lift) {
    r(x, y, w, h, ramp[lift ? 3 : 2]);
    r(x, y, w, 1, ramp[4]);
    r(x, y, 1, h, ramp[3]);
    r(x, y + h - 1, w, 1, ramp[0]);
    r(x + w - 1, y, 1, h, ramp[1]);
  }

  /* A rounded, shaded limb or body part. */
  function limb(r, x, y, w, h, ramp) {
    r(x, y, w, h, ramp[2]);
    r(x, y, w, 1, ramp[3]);
    r(x, y + h - 1, w, 1, ramp[1]);
    r(x + w - 1, y + 1, 1, h - 2, ramp[1]);
  }

  var cache = Object.create(null);
  var PAD = 1;

  /* Renders once, then blits. `draw` receives (ctx, ox, oy). Characters
     ask for an outline: the silhouette is dilated by a pixel in the four
     directions, filled with the ink colour and laid underneath. */
  function stamp(key, w, h, outline, draw) {
    var got = cache[key];
    if (got) return got;

    var art = surface(w + PAD * 2, h + PAD * 2);
    draw(art.ctx, PAD, PAD);

    var out;
    if (outline) {
      out = surface(w + PAD * 2, h + PAD * 2);
      var o = out.ctx;
      o.drawImage(art.canvas, -1, 0);
      o.drawImage(art.canvas, 1, 0);
      o.drawImage(art.canvas, 0, -1);
      o.drawImage(art.canvas, 0, 1);
      o.globalCompositeOperation = 'source-in';
      o.fillStyle = INK;
      o.fillRect(0, 0, w + PAD * 2, h + PAD * 2);
      o.globalCompositeOperation = 'source-over';
      o.drawImage(art.canvas, 0, 0);
    } else {
      out = art;
    }
    cache[key] = out.canvas;
    return out.canvas;
  }

  function blit(ctx, img, x, y) { ctx.drawImage(img, x - PAD, y - PAD); }

  /* ============================ Rama ============================ */

  function heroSize(o) {
    if (o.state === 'duck') return { w: 16, h: o.big ? 18 : 16 };
    return { w: 16, h: o.big ? 28 : 16 };
  }

  function paintHero(c, ox, oy, o) {
    var big = !!o.big, duck = o.state === 'duck' && big;
    var W = 16, H = duck ? 18 : (big ? 28 : 16);
    var r = pen(c, ox, oy, W, o.dir < 0);

    var skin = R.skin, cloth = R.cloth, crown = R.gold;
    if (o.bow) cloth = R.white;
    if (o.star != null) {
      var s = STAR_SETS[o.star];
      skin = s.skin; cloth = s.cloth; crown = R.white;
    }

    var crownH = big ? 4 : 3;
    var headH  = big ? 9 : 6;
    var torsoH = big ? 8 : 4;
    if (duck) { crownH = 3; headH = 6; torsoH = 6; }
    var crownY = 0, headY = crownY + crownH, torsoY = headY + headH;
    var legY = torsoY + torsoH, legH = H - legY;
    var hairH = big ? 2 : 1;

    // ---- mukuta
    r(7, crownY, 3, 1, crown[4]);
    r(6, crownY + 1, 5, crownH - 2, crown[3]);
    r(4, crownY + 1, 2, crownH - 2, crown[2]);
    r(11, crownY + 1, 2, crownH - 2, crown[1]);
    r(8, crownY + 1, 2, 1, R.red[3]);
    r(3, crownY + crownH - 1, 11, 1, crown[1]);
    r(3, crownY + crownH - 1, 6, 1, crown[2]);

    // ---- head
    r(3, headY, 11, hairH, R.hair[2]);
    r(4, headY, 7, 1, R.hair[3]);
    r(3, headY, 2, headH - 1, R.hair[1]);
    r(5, headY + hairH, 9, headH - hairH - 1, skin[2]);
    r(5, headY + hairH, 8, 1, skin[3]);           // forehead catches light
    r(13, headY + hairH + 1, 1, headH - hairH - 2, skin[1]);
    r(5, headY + headH - 1, 9, 1, skin[0]);       // jaw shadow
    r(4, headY + hairH + 1, 1, 2, R.hair[2]);
    r(8, headY + hairH, 1, 2, R.red[3]);          // tilak
    var eyeY = headY + hairH + 1;
    if (o.state === 'dead') {
      r(10, eyeY, 3, 1, R.hair[0]);
      r(10, eyeY + 2, 3, 1, skin[1]);
    } else {
      r(10, eyeY, 3, 1, R.hair[1]);               // brow
      r(10, eyeY + 1, 2, big ? 2 : 1, R.white[4]);
      r(11, eyeY + 1, 1, big ? 2 : 1, R.hair[0]); // pupil
      r(12, eyeY + 1, 1, big ? 2 : 1, skin[1]);
      if (big) { r(11, headY + headH - 2, 2, 1, skin[1]); r(12, headY + headH - 3, 1, 1, skin[3]); }
    }

    // ---- torso
    var tw = big ? 10 : 8, tx = big ? 3 : 4;
    limb(r, tx, torsoY, tw, torsoH, skin);
    r(tx + 1, torsoY, tw - 2, 1, crown[3]);       // necklace
    r(tx + 2, torsoY + 1, tw - 4, 1, crown[1]);
    for (var i = 0; i < torsoH - 2; i++) r(tx + 2 + i, torsoY + i, 1, 1, R.white[4]);
    r(tx, torsoY + torsoH - 2, tw, 2, cloth[2]);  // waist cloth
    r(tx, torsoY + torsoH - 2, tw, 1, cloth[3]);
    r(tx, torsoY + torsoH - 1, tw, 1, cloth[1]);

    // ---- arms
    var armH = big ? 5 : 3, swing = 0;
    if (o.state === 'walk') swing = (o.frame % 4 === 1) ? -1 : (o.frame % 4 === 3 ? 1 : 0);
    if (o.state === 'jump') {
      limb(r, 1, torsoY - 1, 2, armH, skin);
      limb(r, 13, torsoY - 2, 2, armH, skin);
    } else if (o.state === 'dead') {
      limb(r, 1, torsoY - 3, 2, armH, skin);
      limb(r, 13, torsoY - 3, 2, armH, skin);
    } else if (duck) {
      limb(r, 2, torsoY + 1, 3, 2, skin);
      limb(r, 12, torsoY + 1, 3, 2, skin);
    } else {
      limb(r, 1, torsoY + 1 + swing, 2, armH, skin);
      limb(r, 13, torsoY + 1 - swing, 2, armH, skin);
    }

    // ---- the Kodanda
    if (o.bow && o.state !== 'dead') {
      var by = torsoY - 2, bh = big ? 11 : 8;
      r(14, by + 2, 1, bh - 3, R.gold[3]);
      r(15, by + 3, 1, bh - 5, R.gold[1]);
      r(13, by + 1, 1, 1, R.gold[3]); r(13, by + bh - 1, 1, 1, R.gold[3]);
      r(12, by, 1, 1, R.gold[2]);     r(12, by + bh, 1, 1, R.gold[2]);
      r(12, by + 1, 1, bh - 1, R.bone[4]);
    }

    // ---- legs
    if (o.state === 'dead') {
      limb(r, 5, legY, 3, legH, skin); limb(r, 9, legY, 3, legH, skin);
      r(4, legY + legH - 1, 4, 1, R.wood[1]); r(9, legY + legH - 1, 4, 1, R.wood[1]);
    } else if (duck) {
      r(3, legY, 11, legH - 1, cloth[2]);
      r(3, legY, 11, 1, cloth[3]);
      r(3, legY + legH - 2, 11, 1, cloth[0]);
      r(3, legY + legH - 1, 5, 1, R.wood[1]);
      r(9, legY + legH - 1, 5, 1, R.wood[1]);
    } else {
      r(3, legY, 11, 1, cloth[2]);
      r(3, legY, 6, 1, cloth[3]);
      var pose;
      if (o.state === 'jump') pose = [2, 9];
      else if (o.state === 'walk') pose = [[4, 9], [1, 10], [5, 8], [1, 10]][o.frame % 4];
      else pose = [4, 9];
      limb(r, pose[0], legY + 1, 3, legH - 1, skin);
      limb(r, pose[1], legY + 1, 3, legH - 1, skin);
      r(pose[0] - 1, legY + legH - 1, 4, 1, R.wood[2]);
      r(pose[1], legY + legH - 1, 4, 1, R.wood[2]);
      r(pose[0] - 1, legY + legH - 1, 4, 1, R.wood[2]);
    }
  }

  function drawHero(ctx, x, y, o) {
    var star = o.star ? (o.t >> 1) % STAR_SETS.length : null;
    var sz = heroSize(o);
    var key = 'h' + (o.big ? 1 : 0) + (o.bow ? 1 : 0) + o.state +
              (o.frame % 4) + (o.dir < 0 ? 1 : 0) + (star == null ? 'n' : star);
    var opts = { big: o.big, bow: o.bow, state: o.state, frame: o.frame,
                 dir: o.dir, star: star };
    blit(ctx, stamp(key, sz.w, sz.h, true, function (c, ox, oy) {
      paintHero(c, ox, oy, opts);
    }), x, y);
  }

  /* ============================ rakshasa ============================ */

  function paintRakshasa(c, ox, oy, frame, dir, squashed) {
    var r = pen(c, ox, oy, 16, dir < 0);
    if (squashed) {
      r(1, 10, 14, 4, R.demon[1]);
      r(1, 10, 14, 1, R.demon[2]);
      r(3, 8, 10, 2, R.demon[2]);
      r(2, 8, 1, 2, R.bone[3]); r(13, 8, 1, 2, R.bone[3]);
      r(4, 11, 2, 1, R.gold[3]); r(10, 11, 2, 1, R.gold[3]);
      return;
    }
    // horns
    r(2, 0, 1, 1, R.bone[4]); r(2, 1, 2, 3, R.bone[3]); r(3, 2, 1, 2, R.bone[1]);
    r(13, 0, 1, 1, R.bone[4]); r(12, 1, 2, 3, R.bone[3]); r(12, 2, 1, 2, R.bone[1]);
    // body, rounded
    r(3, 3, 10, 9, R.demon[2]);
    r(2, 5, 12, 6, R.demon[2]);
    r(4, 3, 8, 1, R.demon[3]);
    r(2, 5, 1, 5, R.demon[3]);
    r(3, 4, 9, 1, R.demon[3]);
    r(13, 5, 1, 6, R.demon[0]);
    r(3, 10, 10, 2, R.demon[1]);
    r(4, 11, 8, 1, R.demon[0]);
    // brow and eyes
    r(4, 5, 3, 1, R.demon[0]); r(9, 5, 3, 1, R.demon[0]);
    r(4, 6, 3, 2, R.gold[4]); r(9, 6, 3, 2, R.gold[4]);
    r(4, 6, 3, 1, R.gold[2]); r(9, 6, 3, 1, R.gold[2]);
    r(5, 7, 1, 1, R.hair[0]); r(10, 7, 1, 1, R.hair[0]);
    // maw
    r(5, 9, 6, 2, '#2a0f18');
    r(5, 9, 6, 1, '#160810');
    r(5, 9, 1, 1, R.white[4]); r(10, 9, 1, 1, R.white[4]);
    r(7, 10, 2, 1, R.red[2]);
    // feet
    var f = frame % 2;
    var lx = f ? 1 : 2, rx = f ? 10 : 9;
    r(lx, 12, 5, 4, R.demon[1]);
    r(rx, 12, 5, 4, R.demon[1]);
    r(lx, 12, 5, 1, R.demon[2]);
    r(rx, 12, 5, 1, R.demon[2]);
    r(lx, 15, 5, 1, R.demon[0]); r(rx, 15, 5, 1, R.demon[0]);
  }

  function drawRakshasa(ctx, x, y, frame, dir, squashed) {
    var key = 'g' + (frame % 2) + (dir < 0 ? 1 : 0) + (squashed ? 's' : 'n');
    blit(ctx, stamp(key, 16, 16, true, function (c, ox, oy) {
      paintRakshasa(c, ox, oy, frame, dir, squashed);
    }), x, y);
  }

  /* ============================ Maricha ============================ */

  function paintDeer(c, ox, oy, frame, dir) {
    var r = pen(c, ox, oy, 16, dir < 0);
    // antlers
    r(9, 0, 1, 3, R.deer[0]); r(8, 1, 1, 1, R.deer[0]); r(10, 1, 1, 1, R.deer[1]);
    r(12, 0, 1, 3, R.deer[0]); r(13, 1, 1, 1, R.deer[1]);
    // head
    limb(r, 9, 3, 5, 5, R.deer);
    r(13, 6, 3, 2, R.deer[3]);
    r(14, 7, 2, 1, R.deer[1]);
    r(15, 6, 1, 1, R.hair[0]);
    r(11, 4, 1, 2, R.hair[0]);
    r(11, 4, 1, 1, R.white[4]);
    r(9, 3, 4, 1, R.deer[3]);
    // neck and body
    limb(r, 8, 7, 3, 4, R.deer);
    r(2, 9, 11, 7, R.deer[2]);
    r(2, 9, 11, 1, R.deer[3]);
    r(3, 10, 9, 1, R.deer[4]);
    r(2, 14, 11, 2, R.deer[1]);
    r(3, 15, 9, 1, R.deer[0]);
    r(12, 10, 1, 5, R.deer[1]);
    // dapples
    r(4, 11, 2, 1, R.white[4]); r(7, 10, 2, 1, R.white[3]); r(9, 12, 2, 1, R.white[4]);
    r(5, 13, 1, 1, R.white[3]);
    r(1, 9, 2, 3, R.deer[3]);                      // tail
    // legs
    var f = frame % 2;
    var lx = f ? 2 : 4, rx = f ? 11 : 9;
    limb(r, lx, 16, 2, 6, R.deer);
    limb(r, rx, 16, 2, 6, R.deer);
    r(lx, 21, 3, 1, R.deer[0]); r(rx, 21, 3, 1, R.deer[0]);
  }

  function drawDeer(ctx, x, y, frame, dir) {
    var key = 'd' + (frame % 2) + (dir < 0 ? 1 : 0);
    blit(ctx, stamp(key, 16, 22, true, function (c, ox, oy) {
      paintDeer(c, ox, oy, frame, dir);
    }), x, y);
  }

  function paintShell(c, ox, oy, frame, spinning) {
    var r = pen(c, ox, oy, 16, false);
    r(3, 1, 10, 3, R.deer[2]);
    r(4, 1, 8, 1, R.deer[3]);
    r(1, 3, 14, 8, R.deer[2]);
    r(2, 3, 12, 1, R.deer[4]);
    r(1, 4, 1, 6, R.deer[3]);
    r(14, 4, 1, 6, R.deer[0]);
    r(1, 10, 14, 3, R.deer[1]);
    r(2, 12, 12, 1, R.deer[0]);
    r(2, 0, 1, 2, R.deer[1]); r(13, 0, 1, 2, R.deer[1]);
    var o = spinning ? (frame % 4) : 0;
    r(3 + o, 5, 2, 2, R.white[4]);
    r(8 + o, 7, 2, 2, R.white[3]);
    r(11 - o, 4, 1, 1, R.white[4]);
  }

  function drawDeerShell(ctx, x, y, frame, spinning) {
    var key = 'ds' + (spinning ? (frame % 4) : 'i');
    blit(ctx, stamp(key, 16, 14, true, function (c, ox, oy) {
      paintShell(c, ox, oy, frame, spinning);
    }), x, y);
  }

  /* ============================ Kakasura ============================ */

  function paintCrow(c, ox, oy, frame, dir) {
    var r = pen(c, ox, oy, 16, dir < 0);
    var up = (frame % 2) === 0;
    if (up) {
      r(2, 0, 7, 4, R.crow[3]);
      r(3, 0, 5, 1, R.crow[4]);
      r(1, 2, 4, 2, R.crow[2]);
    } else {
      r(1, 7, 8, 4, R.crow[3]);
      r(2, 10, 6, 1, R.crow[1]);
      r(2, 6, 5, 2, R.crow[2]);
    }
    r(4, 4, 8, 6, R.crow[2]);
    r(4, 4, 8, 1, R.crow[3]);
    r(5, 5, 5, 1, R.crow[4]);                    // oil-slick sheen
    r(4, 9, 8, 1, R.crow[0]);
    r(9, 2, 5, 4, R.crow[2]);
    r(9, 2, 4, 1, R.crow[3]);
    r(13, 4, 3, 2, R.gold[3]);
    r(13, 5, 3, 1, R.gold[1]);
    r(11, 3, 1, 1, R.red[3]);
    r(0, 5, 4, 2, R.crow[1]);
    r(0, 5, 4, 1, R.crow[2]);
    r(6, 9, 2, 3, R.gold[2]);
  }

  function drawCrow(ctx, x, y, frame, dir) {
    var key = 'c' + (frame % 2) + (dir < 0 ? 1 : 0);
    blit(ctx, stamp(key, 16, 14, true, function (c, ox, oy) {
      paintCrow(c, ox, oy, frame, dir);
    }), x, y);
  }

  /* ============================ Ravana ============================ */

  function paintRavana(c, ox, oy, frame, dir, flash) {
    var r = pen(c, ox, oy, 32, dir < 0);
    var skin = flash ? R.white : R.ravskin;
    var robe = flash ? R.sariR : R.rav;

    // the ten heads: nine in two ranks behind the crowned face
    for (var i = 0; i < 5; i++) {
      var hx = 1 + i * 6;
      r(hx, 4, 5, 6, robe[0]);
      r(hx, 4, 5, 1, robe[1]);
      r(hx + 1, 5, 3, 4, skin[1]);
      r(hx + 1, 5, 3, 1, skin[2]);
      r(hx + 1, 6, 1, 1, R.red[2]); r(hx + 3, 6, 1, 1, R.red[2]);
      r(hx, 3, 5, 1, R.gold[2]);
    }
    for (var j = 0; j < 4; j++) {
      var bx = 4 + j * 6;
      r(bx, 0, 5, 5, robe[0]);
      r(bx + 1, 1, 3, 3, skin[1]);
      r(bx + 1, 2, 1, 1, R.red[2]); r(bx + 3, 2, 1, 1, R.red[2]);
      r(bx, 0, 5, 1, robe[1]);
    }
    // the face
    r(11, 6, 10, 10, robe[0]);
    limb(r, 12, 8, 8, 7, skin);
    r(12, 8, 8, 1, skin[3]);
    r(11, 5, 10, 2, R.gold[3]);
    r(11, 5, 10, 1, R.gold[4]);
    r(13, 4, 6, 1, R.gold[3]);
    r(15, 5, 2, 1, R.red[3]);
    r(13, 10, 2, 2, R.red[3]); r(17, 10, 2, 2, R.red[3]);
    r(13, 10, 2, 1, R.red[4]); r(17, 10, 2, 1, R.red[4]);
    r(12, 13, 8, 1, R.hair[0]);
    r(14, 14, 4, 1, R.white[4]);
    // torso
    var f = frame % 2;
    bevel(r, 7, 16, 18, 3, R.gold);
    r(8, 19, 16, 9, robe[2]);
    r(8, 19, 16, 1, robe[3]);
    r(8, 19, 1, 9, robe[3]);
    r(23, 19, 1, 9, robe[0]);
    r(9, 27, 14, 1, robe[0]);
    r(10, 20, 12, 1, R.gold[1]);
    bevel(r, 14, 21, 4, 4, R.gold);
    r(15, 22, 2, 2, R.red[3]);
    r(8, 26, 16, 2, R.gold[1]);
    limb(r, 4, 18, 4, 8, skin); limb(r, 24, 18, 4, 8, skin);
    r(4, 17, 4, 1, R.gold[3]); r(24, 17, 4, 1, R.gold[3]);
    r(3, 25, 5, 4, robe[1]); r(24, 25, 5, 4, robe[1]);
    // mace
    r(27, 10 + f, 3, 16, R.steel[1]);
    r(27, 10 + f, 1, 16, R.steel[2]);
    bevel(r, 25, 6 + f, 7, 6, R.steel);
    r(24, 8 + f, 1, 2, R.steel[1]); r(31, 8 + f, 1, 2, R.steel[1]);
    // legs
    r(9, 28, 6, 12 + (f ? 0 : 1), robe[2]);
    r(17, 28, 6, 13 - (f ? 0 : 1), robe[2]);
    r(9, 28, 1, 12, robe[3]); r(17, 28, 1, 12, robe[3]);
    r(14, 28, 1, 12, robe[0]); r(22, 28, 1, 12, robe[0]);
    r(8, 40, 8, 4, robe[0]); r(16, 40, 8, 4, robe[0]);
    r(8, 40, 8, 1, robe[1]); r(16, 40, 8, 1, robe[1]);
    r(8, 43, 8, 1, R.gold[2]); r(16, 43, 8, 1, R.gold[2]);
  }

  function drawRavana(ctx, x, y, o) {
    var key = 'R' + (o.frame % 2) + (o.dir < 0 ? 1 : 0) + (o.flash ? 'f' : 'n');
    blit(ctx, stamp(key, 32, 44, true, function (c, ox, oy) {
      paintRavana(c, ox, oy, o.frame, o.dir, o.flash);
    }), x, y);
  }

  /* ============================ Sita ============================ */

  function paintSita(c, ox, oy) {
    var r = pen(c, ox, oy, 16, false);
    r(4, 0, 8, 3, R.hair[2]);
    r(5, 0, 6, 1, R.hair[3]);
    r(3, 2, 10, 2, R.hair[1]);
    limb(r, 4, 3, 8, 6, ['#a86a3c', '#c98a55', '#efc08a', '#ffd9ac', '#ffeed4']);
    r(4, 3, 2, 6, R.hair[2]); r(11, 3, 2, 5, R.hair[1]);
    r(7, 5, 1, 1, R.hair[0]); r(10, 5, 1, 1, R.hair[0]);
    r(7, 5, 1, 1, R.hair[0]); r(9, 4, 1, 1, R.red[3]);
    r(8, 4, 1, 1, R.red[3]);
    r(5, 2, 6, 1, R.gold[3]);
    r(4, 9, 8, 2, R.gold[3]);
    r(5, 10, 6, 1, R.gold[1]);
    r(3, 10, 10, 8, R.sari[2]);
    r(3, 10, 10, 1, R.sari[3]);
    r(3, 10, 1, 8, R.sari[3]);
    r(12, 11, 1, 7, R.sari[0]);
    r(3, 10, 10, 2, R.sariR[2]);
    r(9, 12, 4, 6, R.sariR[2]);
    r(9, 12, 1, 6, R.sariR[3]);
    r(3, 17, 10, 1, R.gold[2]);
    limb(r, 2, 12, 2, 4, ['#a86a3c', '#c98a55', '#efc08a', '#ffd9ac', '#ffeed4']);
    limb(r, 12, 12, 2, 4, ['#a86a3c', '#c98a55', '#efc08a', '#ffd9ac', '#ffeed4']);
    r(5, 18, 3, 3, R.sari[1]); r(9, 18, 3, 3, R.sari[1]);
    r(5, 21, 3, 1, '#c98a55'); r(9, 21, 3, 1, '#c98a55');
  }

  function drawSita(ctx, x, y, t) {
    var bob = Math.floor(t / 20) % 2;
    blit(ctx, stamp('sita', 16, 24, true, paintSita), x, y + bob);
  }

  /* ============================ items ============================ */

  function drawSanjeevani(ctx, x, y) {
    blit(ctx, stamp('herb', 16, 16, true, function (c, ox, oy) {
      var r = pen(c, ox, oy, 16, false);
      var leaf = ['#1d5c1c', '#2f7d28', '#4faa38', '#79cf5c', '#a8e88a'];
      r(4, 2, 8, 2, leaf[2]);
      r(5, 2, 6, 1, leaf[3]);
      r(2, 4, 12, 5, leaf[2]);
      r(3, 4, 10, 1, leaf[4]);
      r(2, 8, 12, 1, leaf[0]);
      r(1, 6, 2, 3, leaf[1]); r(13, 6, 2, 3, leaf[1]);
      r(1, 6, 1, 1, leaf[3]);
      r(6, 5, 4, 3, R.red[2]);
      r(6, 5, 3, 1, R.red[3]);
      r(7, 5, 1, 1, R.red[4]);
      r(6, 7, 4, 1, R.red[0]);
      r(3, 9, 10, 2, leaf[1]);
      r(3, 9, 10, 1, leaf[2]);
      bevel(r, 5, 11, 6, 3, R.wood);
      bevel(r, 4, 14, 8, 2, R.wood, true);
    }), x, y);
  }

  function drawBow(ctx, x, y, t) {
    var ph = (t >> 3) % 2;
    blit(ctx, stamp('bow' + ph, 16, 16, true, function (c, ox, oy) {
      var r = pen(c, ox, oy, 16, false);
      var g = ph ? R.gold[4] : R.gold[3];
      r(6, 0, 3, 1, g); r(4, 1, 2, 1, g);
      r(3, 2, 2, 2, g); r(2, 4, 2, 8, g);
      r(3, 12, 2, 2, g); r(4, 14, 2, 1, g); r(6, 15, 3, 1, g);
      r(2, 5, 1, 6, R.gold[4]);
      r(4, 5, 1, 6, R.gold[1]);
      r(3, 7, 3, 2, R.gold[0]);
      r(9, 1, 1, 14, R.bone[4]);
      r(6, 7, 8, 2, R.wood[3]);
      r(6, 7, 8, 1, R.wood[4]);
      r(13, 6, 3, 4, R.steel[3]);
      r(13, 6, 3, 1, R.steel[4]);
      r(6, 6, 1, 1, R.white[4]); r(6, 9, 1, 1, R.white[3]);
    }), x, y);
  }

  function drawBlessing(ctx, x, y, t) {
    var ph = (t >> 2) % 4;
    // a soft bloom, then the star itself
    var g = ctx.createRadialGradient(x + 8, y + 8, 1, x + 8, y + 8, 13);
    g.addColorStop(0, 'rgba(255,200,90,0.42)');
    g.addColorStop(1, 'rgba(255,140,40,0)');
    ctx.fillStyle = g;
    ctx.fillRect(x - 6, y - 6, 28, 28);
    blit(ctx, stamp('bless' + ph, 16, 16, true, function (c, ox, oy) {
      var r = pen(c, ox, oy, 16, false);
      var a = [R.flame[2], R.flame[3], R.gold[3], R.flame[1]][ph];
      var b = [R.gold[3], R.gold[4], R.flame[2], R.gold[3]][ph];
      r(7, 0, 2, 3, a); r(6, 3, 4, 2, a);
      r(1, 5, 14, 2, a); r(2, 7, 12, 2, b); r(3, 9, 10, 2, a);
      r(2, 11, 4, 3, a); r(10, 11, 4, 3, a);
      r(1, 14, 3, 2, a); r(12, 14, 3, 2, a);
      r(2, 5, 12, 1, R.gold[4]);
      r(3, 10, 10, 1, R.flame[0]);
      r(6, 6, 4, 4, R.white[4]);
      r(7, 7, 2, 2, R.flame[1]);
    }), x, y);
  }

  var COIN_W = [8, 6, 4, 2, 4, 6];
  function drawCoin(ctx, x, y, frame) {
    var f = ((frame % COIN_W.length) + COIN_W.length) % COIN_W.length;
    blit(ctx, stamp('coin' + f, 16, 16, true, function (c, ox, oy) {
      var r = pen(c, ox, oy, 16, false);
      var w = COIN_W[f], cx = 8 - Math.floor(w / 2);
      if (w > 2) {
        r(cx + 1, 2, w - 2, 1, R.gold[1]);
        r(cx + 1, 13, w - 2, 1, R.gold[0]);
      }
      r(cx, 3, w, 10, R.gold[2]);
      r(cx, 3, w, 1, R.gold[3]);
      r(cx, 12, w, 1, R.gold[0]);
      if (w > 3) {
        r(cx + 1, 4, 1, 8, R.gold[4]);
        r(cx + w - 2, 4, 1, 8, R.gold[1]);
        r(cx + Math.floor(w / 2), 6, 1, 4, R.gold[1]);
      }
    }), x, y);
  }

  function drawArrow(ctx, x, y, dir) {
    blit(ctx, stamp('arw' + (dir < 0 ? 1 : 0), 8, 8, true, function (c, ox, oy) {
      var r = pen(c, ox, oy, 8, dir < 0);
      r(0, 3, 6, 2, R.wood[3]);
      r(0, 3, 6, 1, R.wood[4]);
      r(6, 2, 2, 4, R.steel[3]);
      r(6, 2, 2, 1, R.steel[4]);
      r(0, 1, 2, 2, R.white[4]); r(0, 5, 2, 2, R.white[2]);
    }), x, y);
  }

  function drawFireball(ctx, x, y, t) {
    var f = (t >> 2) % 2;
    var g = ctx.createRadialGradient(x + 5, y + 5, 1, x + 5, y + 5, 9);
    g.addColorStop(0, 'rgba(255,150,40,0.5)');
    g.addColorStop(1, 'rgba(255,80,0,0)');
    ctx.fillStyle = g;
    ctx.fillRect(x - 4, y - 4, 18, 18);
    blit(ctx, stamp('fire' + f, 10, 10, false, function (c, ox, oy) {
      var r = pen(c, ox, oy, 10, false);
      r(2, 2, 6, 6, R.flame[2]);
      r(3, 2, 4, 1, R.flame[3]);
      r(3, 3, 4, 4, R.flame[3]);
      r(4, 4, 2, 2, R.flame[4]);
      r(2, 7, 6, 1, R.flame[1]);
      r(f ? 0 : 1, 3, 2, 4, R.flame[1]);
      r(8, f ? 2 : 4, 2, 3, R.flame[1]);
    }), x, y);
  }

  /* ============================ tiles ============================ */

  var THEME = {
    forest: {
      dirt:  ['#4a2408', '#6d3d12', '#9c5a2b', '#b8763f', '#d19257'],
      grass: ['#1c5218', '#2f7a2b', '#4aa83f', '#6fc95c', '#9ee88a'],
      brick: ['#5a2a0c', '#8a4520', '#c1682f', '#d98a4c', '#efb07a'],
      stone: ['#4a463f', '#6f6a63', '#a9a29a', '#c9c3bb', '#e8e3db']
    },
    mountain: {
      dirt:  ['#33313f', '#535163', '#7d7b8c', '#9c9aac', '#bebccc'],
      grass: ['#5a5870', '#7d7b8c', '#b8b3c6', '#d4d0e0', '#f0edf7'],
      brick: ['#3d3849', '#5d566b', '#8d8598', '#a9a2b6', '#c7c1d4'],
      stone: ['#484252', '#6f6a7a', '#b0aab8', '#cac5d2', '#e8e4ee']
    },
    lanka: {
      dirt:  ['#1a0d14', '#2c1723', '#4a2b3a', '#63404f', '#7d5666'],
      grass: ['#2e0f18', '#4a1a24', '#7a2f3c', '#9b4552', '#bd5e6c'],
      brick: ['#310f18', '#4d1c27', '#7b3140', '#9c4756', '#bd6070'],
      stone: ['#241d2c', '#3f3547', '#6a5a72', '#87768f', '#a494ac']
    },
    cave: {
      dirt:  ['#15112a', '#2b2440', '#4a4064', '#61567e', '#7d7099'],
      grass: ['#241d3c', '#3a3158', '#5d5280', '#7a6ea0', '#9a8dc0'],
      brick: ['#1a1530', '#2e2748', '#4f4470', '#685c8c', '#8478a8'],
      stone: ['#231d38', '#3b3358', '#655a86', '#8074a4', '#9d92c0']
    }
  };

  function paintTile(c, ox, oy, ch, theme, ph, openAbove, nb, v) {
    var T = THEME[theme] || THEME.forest;
    var r = pen(c, ox, oy, 16, false);
    var i;
    switch (ch) {
      case '#':
        r(0, 0, 16, 16, T.dirt[2]);
        r(0, 0, 16, 1, T.dirt[3]);
        r(0, 15, 16, 1, T.dirt[0]);
        r(15, 0, 1, 16, T.dirt[1]);
        // scattered grit, laid out differently per variant
        var grit = [[3, 4], [10, 7], [6, 11], [13, 3]];
        for (i = 0; i < 3; i++) {
          var gx = grit[(i + v) % 4][0], gy = grit[(i + v) % 4][1];
          r(gx, gy, 2, 2, T.dirt[1]);
          r(gx, gy, 1, 1, T.dirt[3]);
        }
        if (openAbove) {
          r(0, 0, 16, 5, T.grass[2]);
          r(0, 0, 16, 1, T.grass[3]);
          r(0, 5, 16, 1, T.grass[0]);
          // blades breaking the edge, so the ground is not a ruled line
          var tuft = [[1, 2], [6, 3], [12, 2], [9, 3]];
          for (i = 0; i < 2; i++) {
            var tx = tuft[(i * 2 + v) % 4][0], th = tuft[(i * 2 + v) % 4][1];
            r(tx, -th, 2, th, T.grass[2]);
            r(tx, -th, 1, 1, T.grass[4]);
          }
          r(2, 1, 3, 1, T.grass[4]); r(9, 2, 4, 1, T.grass[3]);
        }
        break;

      case 'S':
        bevel(r, 0, 0, 16, 16, T.stone);
        r(2, 2, 12, 12, T.stone[2]);
        r(2, 2, 12, 1, T.stone[3]);
        r(2, 13, 12, 1, T.stone[1]);
        r(3, 3, 10, 1, T.stone[4]);
        if (v & 1) { r(5, 6, 6, 1, T.stone[1]); r(6, 9, 4, 1, T.stone[1]); }
        else { r(4, 5, 3, 1, T.stone[1]); r(8, 10, 5, 1, T.stone[1]); }
        break;

      case 'B':
        r(0, 0, 16, 16, T.brick[2]);
        // three courses, offset, each with its own light and shade
        for (i = 0; i < 3; i++) {
          var by = i * 6 - 1;
          r(0, by, 16, 1, T.brick[4]);
          r(0, by + 4, 16, 1, T.brick[0]);
        }
        r(7, 0, 1, 5, T.brick[0]); r(8, 0, 1, 5, T.brick[3]);
        r(3, 5, 1, 6, T.brick[0]); r(4, 5, 1, 6, T.brick[3]);
        r(11, 5, 1, 6, T.brick[0]); r(12, 5, 1, 6, T.brick[3]);
        r(7, 11, 1, 5, T.brick[0]); r(8, 11, 1, 5, T.brick[3]);
        r(0, 15, 16, 1, T.brick[0]);
        r(0, 0, 1, 16, T.brick[3]);
        break;

      case '?': case 'M': case 'W': case 'T':
        var lit = ph === 3;
        bevel(r, 0, 0, 16, 16, R.gold, lit);
        r(2, 2, 12, 12, lit ? R.gold[4] : R.gold[3]);
        r(2, 2, 12, 1, R.gold[4]);
        r(2, 13, 12, 1, R.gold[1]);
        r(1, 1, 2, 2, R.gold[1]); r(13, 1, 2, 2, R.gold[1]);
        r(1, 13, 2, 2, R.gold[1]); r(13, 13, 2, 2, R.gold[1]);
        // a lotus cut in relief
        var d = lit ? R.gold[1] : R.gold[0], u = lit ? R.gold[4] : R.gold[3];
        r(7, 3, 2, 5, d);                      // centre petal
        r(5, 5, 2, 3, d); r(9, 5, 2, 3, d);    // inner petals
        r(3, 7, 2, 3, d); r(11, 7, 2, 3, d);   // outer petals
        r(4, 9, 8, 2, d);                      // the bowl it sits in
        r(7, 3, 2, 1, u); r(5, 5, 1, 1, u); r(10, 5, 1, 1, u);
        r(3, 7, 1, 1, u); r(12, 7, 1, 1, u); r(4, 9, 8, 1, u);
        // a shimmer sweeping across the face
        r(2 + ph * 3, 2, 1, 12, 'rgba(255,255,255,0.28)');
        break;

      case 'U':
        bevel(r, 0, 0, 16, 16, T.stone);
        r(3, 3, 10, 10, T.stone[1]);
        r(3, 3, 10, 1, T.stone[2]);
        r(5, 5, 2, 2, T.stone[0]); r(9, 8, 2, 2, T.stone[0]);
        break;

      case 'P': case 'p':
        // a fluted column, lit down one side
        r(0, 0, 16, 16, R.sand[2]);
        r(0, 0, 3, 16, R.sand[3]);
        r(1, 0, 1, 16, R.sand[4]);
        r(12, 0, 4, 16, R.sand[1]);
        r(15, 0, 1, 16, R.sand[0]);
        r(6, 0, 1, 16, R.sand[3]);
        r(9, 0, 1, 16, R.sand[1]);
        if (ch === 'P') {
          r(-1, 0, 18, 5, R.sand[3]);
          r(-1, 0, 18, 1, R.sand[4]);
          r(-1, 1, 18, 1, R.gold[3]);
          r(-1, 4, 18, 1, R.sand[0]);
          r(-1, 5, 18, 1, R.sand[1]);
        } else {
          r(0, 5, 16, 1, R.sand[1]); r(0, 6, 16, 1, R.sand[3]);
          r(0, 11, 16, 1, R.sand[1]); r(0, 12, 16, 1, R.sand[3]);
        }
        break;

      case '=':
        // planks lashed over rope
        r(0, 0, 16, 6, R.wood[2]);
        r(0, 0, 16, 1, R.wood[4]);
        r(0, 1, 16, 1, R.wood[3]);
        r(0, 5, 16, 1, R.wood[0]);
        r(5, 1, 1, 4, R.wood[1]); r(6, 1, 1, 4, R.wood[3]);
        r(11, 1, 1, 4, R.wood[1]); r(12, 1, 1, 4, R.wood[3]);
        r(0, 6, 16, 1, 'rgba(0,0,0,0.22)');
        r(2, 6, 2, 2, R.wood[1]); r(12, 6, 2, 2, R.wood[1]);
        break;

      case 'D':
        var right = !!(nb & 1);
        r(0, 0, 16, 16, '#0b0a14');
        r(0, 0, 16, 4, R.sand[3]);
        r(0, 0, 16, 1, R.sand[4]);
        r(0, 1, 16, 1, R.gold[3]);
        r(0, 4, 16, 1, R.sand[0]);
        r(right ? 12 : 0, 4, 4, 12, R.sand[2]);
        r(right ? 15 : 0, 4, 1, 12, right ? R.sand[0] : R.sand[4]);
        r(right ? 12 : 3, 4, 1, 12, right ? R.sand[3] : R.sand[1]);
        r(right ? 8 : 4, 7, 4, 2, R.sand[1]);
        r(right ? 8 : 4, 7, 4, 1, R.sand[2]);
        r(6, 11, 4, 2, '#2a2440');
        break;

      case 'E':
        var rr = !!(nb & 1), low = !!(nb & 2);
        r(0, 0, 16, 16, T.stone[0]);
        var gy = low ? 0 : 4, gh = low ? 16 : 12;
        for (i = 0; i < gh; i++) {
          var k = (gy + i) / 16 + (low ? 0.5 : 0);
          r(rr ? 0 : 4, gy + i, 12, 1,
            'rgb(' + Math.round(150 + 105 * k) + ',' + Math.round(90 + 130 * k) + ',' + Math.round(30 + 90 * k) + ')');
        }
        if (!low) {
          r(rr ? 12 : 0, 4, 4, 3, T.stone[0]);
          r(rr ? 13 : 0, 7, 3, 2, T.stone[0]);
        }
        r(rr ? 14 : 0, 0, 2, 16, R.sand[2]);
        r(rr ? 15 : 0, 0, 1, 16, R.sand[3]);
        if (!low) {
          r(0, 0, 16, 3, R.sand[2]);
          r(0, 0, 16, 1, R.sand[3]);
          r(0, 1, 16, 1, R.gold[3]);
        }
        break;

      case '~':
        var deep = theme === 'lanka' ? ['#5e0f06', '#8e1f12', '#c8321e'] : ['#0f2f66', '#1e4f9c', '#2f6fd0'];
        var crest = theme === 'lanka' ? R.flame[2] : '#5fa0f0';
        var foam = theme === 'lanka' ? R.gold[3] : '#c8e4ff';
        if (!openAbove) {
          r(0, 0, 16, 16, deep[0]);
          r(0, 0, 16, 1, deep[1]);
          break;
        }
        var w = Math.round(Math.sin(ph / 8 * Math.PI * 2) * 1.5);
        r(0, 0, 16, 16, deep[2]);
        r(0, 0, 16, 2 + w, deep[1]);
        r(0, 1 + w, 16, 2, crest);
        r(0, 1 + w, 16, 1, foam);
        r((ph * 2) % 14, 3 + w, 3, 1, foam);
        r((ph * 3 + 7) % 14, 6, 2, 1, 'rgba(255,255,255,0.25)');
        r(0, 12, 16, 4, deep[0]);
        break;
    }
  }

  function drawTile(ctx, x, y, ch, theme, t, openAbove, nb, variant) {
    var v = (variant || 0) & 3;
    var ph = 0;
    if (ch === '?' || ch === 'M' || ch === 'W' || ch === 'T') ph = (t >> 3) % 4;
    else if (ch === '~') ph = (t >> 2) % 8;
    var key = 't' + ch + theme + ph + (openAbove ? 1 : 0) + (nb || 0) + v;
    var img = stamp(key, 16, 16, false, function (c, ox, oy) {
      paintTile(c, ox, oy, ch, theme, ph, openAbove, nb || 0, v);
    });
    ctx.drawImage(img, x - PAD, y - PAD);
  }

  function drawChunk(ctx, x, y, theme, rot) {
    var T = THEME[theme] || THEME.forest;
    blit(ctx, stamp('ch' + theme + (rot % 2), 6, 6, false, function (c, ox, oy) {
      var r = pen(c, ox, oy, 6, false);
      r(0, 0, 6, 6, T.brick[2]);
      r(0, 0, 6, 1, T.brick[4]);
      r(0, 5, 6, 1, T.brick[0]);
      r(rot % 2 ? 1 : 4, 1, 1, 4, T.brick[1]);
    }), x, y);
  }

  /* ============================ the goal shrine ============================ */

  function drawShrine(ctx, x, y, t, lit) {
    var top = y - 152;
    var S = R.sand;

    if (lit) {                                   // the sanctum catches light
      var gl = ctx.createRadialGradient(x + 24, top + 116, 4, x + 24, top + 116, 46);
      gl.addColorStop(0, 'rgba(255,208,66,0.5)');
      gl.addColorStop(1, 'rgba(255,150,40,0)');
      ctx.fillStyle = gl;
      ctx.fillRect(x - 24, top + 68, 96, 96);
    }
    var r = pen(ctx, x, top, 48, false);

    r(0, 142, 48, 10, S[1]);
    r(0, 142, 48, 2, S[3]);
    r(0, 150, 48, 2, S[0]);
    r(3, 84, 42, 58, S[2]);
    r(3, 84, 42, 3, S[4]);
    r(3, 84, 3, 58, S[3]);
    r(42, 84, 3, 58, S[1]);
    r(9, 92, 3, 50, S[3]); r(36, 92, 3, 50, S[1]);
    r(10, 92, 1, 50, S[4]);
    r(15, 100, 18, 42, S[1]);
    r(17, 104, 14, 38, '#2a1832');
    r(17, 104, 14, 2, '#170d1e');
    r(21, 112, 6, 12, lit ? R.gold[3] : '#6b4a8a');
    if (lit) { r(22, 114, 4, 6, R.gold[4]); r(22, 110, 4, 2, R.gold[2]); }

    for (var i = 0; i < 6; i++) {
      var tw = 40 - i * 5, ty = 84 - (i + 1) * 12, tx = 24 - tw / 2;
      r(tx, ty, tw, 12, S[2]);
      r(tx, ty, tw, 1, S[4]);
      r(tx, ty + 1, tw, 1, S[3]);
      r(tx, ty + 10, tw, 2, S[1]);
      r(tx, ty + 11, tw, 1, S[0]);
      r(tx, ty, 1, 12, S[3]);
      r(tx + tw - 1, ty, 1, 12, S[1]);
      for (var n = 0; n < 3; n++) {
        var nx = tx + 3 + n * (tw - 8) / 2;
        r(nx, ty + 3, 3, 5, S[1]);
        r(nx, ty + 3, 3, 1, S[0]);
      }
    }
    r(18, 6, 12, 6, S[3]);
    r(18, 6, 12, 1, S[4]);
    r(20, 0, 8, 7, R.gold[3]);
    r(20, 0, 8, 1, R.gold[4]);
    r(20, 6, 8, 1, R.gold[1]);
    r(23, -5, 2, 6, R.gold[4]);
    r(22, -7, 4, 2, R.gold[3]);

    var wave = Math.round(Math.sin(t / 8) * 1.5);
    r(45, 30, 2, 60, S[1]);
    r(47, 34 + wave, 12, 9, R.red[2]);
    r(47, 34 + wave, 12, 1, R.red[3]);
    r(47, 42 + wave, 12, 1, R.red[0]);
    r(49, 37 + wave, 8, 2, R.gold[3]);
  }

  /* ============================ backdrops ============================
   * Four or five parallax layers each, with the far ones washed toward
   * the sky colour so distance reads as haze rather than as smaller
   * copies of the same thing.                                          */

  function hash(n) { var s = Math.sin(n * 127.1) * 43758.5453; return s - Math.floor(s); }

  function grad(ctx, stops) {
    var g = ctx.createLinearGradient(0, 0, 0, 240);
    for (var i = 0; i < stops.length; i++) g.addColorStop(stops[i][0], stops[i][1]);
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, 256, 240);
  }

  function bloom(ctx, x, y, rad, inner, outer) {
    var g = ctx.createRadialGradient(x, y, 1, x, y, rad);
    g.addColorStop(0, inner);
    g.addColorStop(1, outer);
    ctx.fillStyle = g;
    ctx.fillRect(x - rad, y - rad, rad * 2, rad * 2);
  }

  function cloud(ctx, x, y, s, col, shade) {
    var w = Math.round(34 * s), h = Math.round(8 * s);
    ctx.fillStyle = col;
    ctx.fillRect(x + w * 0.18, y, w * 0.6, h);
    ctx.fillRect(x, y + h * 0.6, w, h);
    ctx.fillRect(x + w * 0.35, y - h * 0.5, w * 0.35, h * 0.7);
    ctx.fillStyle = shade;
    ctx.fillRect(x, y + h * 1.5, w, Math.max(1, h * 0.3));
  }

  function tree(ctx, x, y, s, pal) {
    var w = Math.round(34 * s), h = Math.round(46 * s);
    ctx.fillStyle = pal[0];
    ctx.fillRect(x + w / 2 - 3 * s, y + h - 20 * s, 6 * s, 26 * s);
    ctx.fillStyle = pal[1];
    ctx.fillRect(x + w / 2 - 3 * s, y + h - 20 * s, 2 * s, 26 * s);
    ctx.fillStyle = pal[2];
    ctx.fillRect(x + 4 * s, y + 12 * s, w - 8 * s, h - 26 * s);
    ctx.fillRect(x, y + 20 * s, w, h - 36 * s);
    ctx.fillRect(x + 6 * s, y + 6 * s, w - 12 * s, 16 * s);
    ctx.fillRect(x + 10 * s, y, w - 20 * s, 10 * s);
    ctx.fillStyle = pal[3];
    ctx.fillRect(x + 8 * s, y + 2 * s, w - 20 * s, 6 * s);
    ctx.fillRect(x + 2 * s, y + 21 * s, 8 * s, 4 * s);
    ctx.fillStyle = pal[4];
    ctx.fillRect(x + 11 * s, y + 2 * s, 5 * s, 3 * s);
    ctx.fillStyle = pal[0];
    ctx.fillRect(x + 4 * s, y + h - 18 * s, w - 8 * s, 3 * s);
  }

  function ridge(ctx, off, span, base, peak, col, snow, seed) {
    ctx.fillStyle = col;
    var start = Math.floor(off / span) - 1;
    for (var m = start; m < start + 6; m++) {
      var mx = m * span - off + Math.floor(off / span) * span;
      var v = hash(m * 3.7 + seed);
      var pk = peak + (base - peak) * v * 0.34;   // no two summits alike
      var lean = (hash(m * 5.1 + seed) - 0.5) * span * 0.16;
      var apex = mx + span * 0.35 + lean;
      ctx.beginPath();
      ctx.moveTo(mx - span * 0.15, base);
      ctx.lineTo(apex, pk);
      ctx.lineTo(mx + span * 0.85, base);
      ctx.closePath();
      ctx.fill();
      if (snow) {
        ctx.fillStyle = snow;
        ctx.beginPath();
        var cap = pk + (base - pk) * 0.22;
        ctx.moveTo(apex - span * 0.11, cap);
        ctx.lineTo(apex, pk);
        ctx.lineTo(apex + span * 0.11, cap);
        ctx.closePath();
        ctx.fill();
        ctx.fillStyle = col;
      }
    }
  }

  function haze(ctx, y, h, col) {
    var g = ctx.createLinearGradient(0, y, 0, y + h);
    g.addColorStop(0, 'rgba(0,0,0,0)');
    g.addColorStop(1, col);
    ctx.fillStyle = g;
    ctx.fillRect(0, y, 256, h);
  }

  function background(ctx, theme, camX, t) {
    var off, i, x;

    if (theme === 'cave') {
      grad(ctx, [[0, '#07060f'], [0.55, '#0d0a18'], [1, '#161027']]);
      // three ranks of arches, each nearer and less washed out
      var depths = [[0.18, '#150f26', 40, 84], [0.32, '#1d1533', 34, 96], [0.5, '#241a40', 28, 110]];
      for (var d = 0; d < depths.length; d++) {
        var dp = depths[d];
        off = (camX * dp[0]) % 72;
        for (i = -1; i < 6; i++) {
          x = i * 72 - off;
          ctx.fillStyle = dp[1];
          ctx.fillRect(x, dp[3] - dp[2], 60, dp[2] + 60);
          ctx.fillStyle = d === 2 ? '#0b0814' : (d === 1 ? '#100b1c' : '#0a0713');
          ctx.fillRect(x + 10, dp[3] - dp[2] + 14, 40, dp[2] + 40);
          ctx.fillRect(x + 16, dp[3] - dp[2] + 6, 28, 12);
          ctx.fillStyle = 'rgba(255,190,110,0.05)';
          ctx.fillRect(x, dp[3] - dp[2], 60, 2);
        }
      }
      // lamps set into the wall, with their pools of light
      off = (camX * 0.5) % 72;
      for (i = -1; i < 6; i++) {
        x = i * 72 - off + 30;
        var fl = ((t + i * 17) >> 3) % 3;
        bloom(ctx, x, 96, 34 + fl, 'rgba(255,170,60,0.20)', 'rgba(255,120,20,0)');
        ctx.fillStyle = '#6b3a1c'; ctx.fillRect(x - 4, 98, 9, 4);
        ctx.fillStyle = '#8a4a24'; ctx.fillRect(x - 4, 98, 9, 1);
        ctx.fillStyle = R.flame[3]; ctx.fillRect(x - 1, 92 - (fl === 1 ? 1 : 0), 3, 6);
        ctx.fillStyle = R.flame[4]; ctx.fillRect(x, 94, 1, 3);
      }
      // shafts of daylight finding their way down
      off = (camX * 0.6) % 128;
      for (i = -1; i < 4; i++) {
        x = i * 128 - off + 40;
        var sg = ctx.createLinearGradient(x, 0, x + 26, 200);
        sg.addColorStop(0, 'rgba(255,225,170,0.10)');
        sg.addColorStop(1, 'rgba(255,200,120,0)');
        ctx.fillStyle = sg;
        ctx.beginPath();
        ctx.moveTo(x, 0); ctx.lineTo(x + 14, 0); ctx.lineTo(x + 34, 200); ctx.lineTo(x + 8, 200);
        ctx.closePath(); ctx.fill();
      }
      return;
    }

    if (theme === 'lanka') {
      grad(ctx, [[0, '#0a0616'], [0.35, '#1d0a24'], [0.68, '#4a1226'], [0.88, '#8a1e1c'], [1, '#c2411c']]);
      // moon
      bloom(ctx, 206 - camX * 0.02, 40, 34, 'rgba(246,217,160,0.22)', 'rgba(246,217,160,0)');
      ctx.fillStyle = '#f6d9a0';
      ctx.beginPath(); ctx.arc(206 - camX * 0.02, 40, 14, 0, 7); ctx.fill();
      ctx.fillStyle = '#e8c489';
      ctx.beginPath(); ctx.arc(210 - camX * 0.02, 44, 4, 0, 7); ctx.fill();
      ctx.fillStyle = '#1d0a24';
      ctx.beginPath(); ctx.arc(199 - camX * 0.02, 34, 12, 0, 7); ctx.fill();
      for (i = 0; i < 26; i++) {
        var tw = (t + i * 31) % 180 < 90 ? 0.8 : 0.35;
        ctx.fillStyle = 'rgba(255,240,220,' + tw + ')';
        ctx.fillRect(Math.floor(hash(i) * 256), Math.floor(hash(i + 40) * 90), 1, 1);
      }
      // three depths of the fortress
      var city = [[0.16, '#2a0f22', 168, 1.0], [0.3, '#1e0a1a', 150, 0.85], [0.48, '#140611', 132, 0.7]];
      for (var ci = 0; ci < city.length; ci++) {
        var cy = city[ci];
        off = (camX * cy[0]) % 96;
        for (i = -1; i < 5; i++) {
          x = i * 96 - off;
          ctx.fillStyle = cy[1];
          ctx.fillRect(x + 8, cy[2], 30, 240 - cy[2]);
          ctx.fillRect(x + 46, cy[2] - 22, 22, 240 - cy[2] + 22);
          ctx.fillRect(x + 74, cy[2] + 12, 26, 240 - cy[2]);
          ctx.beginPath();
          ctx.moveTo(x + 46, cy[2] - 22); ctx.lineTo(x + 57, cy[2] - 46); ctx.lineTo(x + 68, cy[2] - 22);
          ctx.closePath(); ctx.fill();
          ctx.fillStyle = 'rgba(255,179,71,' + (0.75 * cy[3]) + ')';
          ctx.fillRect(x + 14, cy[2] + 12, 4, 5); ctx.fillRect(x + 26, cy[2] + 12, 4, 5);
          ctx.fillRect(x + 52, cy[2] - 8, 4, 5); ctx.fillRect(x + 82, cy[2] + 26, 4, 5);
        }
      }
      haze(ctx, 150, 90, 'rgba(180,50,20,0.30)');
      bloom(ctx, 128, 244, 150, 'rgba(255,120,30,0.28)', 'rgba(255,80,0,0)');
      for (var e = 0; e < 22; e++) {
        var ex = (hash(e) * 256 + t * (0.2 + hash(e + 9) * 0.3)) % 256;
        var ey = 230 - ((t * (0.4 + hash(e) * 0.5) + hash(e + 3) * 210) % 230);
        ctx.fillStyle = e % 3 ? 'rgba(255,138,43,0.9)' : 'rgba(255,208,66,0.9)';
        ctx.fillRect(Math.floor(ex), Math.floor(ey), 2, 2);
      }
      return;
    }

    if (theme === 'mountain') {
      grad(ctx, [[0, '#141238'], [0.28, '#3a2a63'], [0.5, '#7a4a7a'], [0.72, '#d0705a'],
                 [0.88, '#f0a860'], [1, '#f7c98a']]);
      for (i = 0; i < 30; i++) {
        var b = (t + i * 23) % 200 < 120 ? 0.9 : 0.4;
        ctx.fillStyle = 'rgba(255,255,255,' + b + ')';
        ctx.fillRect(Math.floor(hash(i) * 256), Math.floor(hash(i + 40) * 80), 1, 1);
      }
      bloom(ctx, 60 - camX * 0.02, 54, 30, 'rgba(255,233,192,0.30)', 'rgba(255,233,192,0)');
      ctx.fillStyle = '#ffe9c0';
      ctx.beginPath(); ctx.arc(60 - camX * 0.02, 54, 11, 0, 7); ctx.fill();
      ctx.fillStyle = '#f0d5a4';
      ctx.beginPath(); ctx.arc(63 - camX * 0.02, 57, 4, 0, 7); ctx.fill();
      // far, middle and near ranges
      ridge(ctx, camX * 0.1, 150, 212, 106, '#6e5a94', '#cfc4e8', 3);
      haze(ctx, 120, 96, 'rgba(200,140,150,0.34)');
      ridge(ctx, camX * 0.22, 128, 216, 114, '#4a3a6e', '#d8d0e8', 17);
      haze(ctx, 150, 70, 'rgba(160,100,120,0.26)');
      ridge(ctx, camX * 0.4, 104, 224, 152, '#33254f', null, 41);
      // pines along the near ridge
      off = (camX * 0.6) % 40;
      for (i = -1; i < 8; i++) {
        x = i * 40 - off + 6;
        ctx.fillStyle = '#241a3a';
        ctx.fillRect(x + 5, 196, 3, 18);
        for (var k = 0; k < 3; k++) {
          var pw = 16 - k * 4;
          ctx.beginPath();
          ctx.moveTo(x + 6 - pw / 2, 200 - k * 10);
          ctx.lineTo(x + 6, 182 - k * 10);
          ctx.lineTo(x + 6 + pw / 2, 200 - k * 10);
          ctx.closePath(); ctx.fill();
        }
      }
      ctx.fillStyle = '#1d1430'; ctx.fillRect(0, 210, 256, 30);
      ctx.fillStyle = '#2a1e42'; ctx.fillRect(0, 210, 256, 2);
      return;
    }

    // ---- forest
    grad(ctx, [[0, '#2f7fd8'], [0.3, '#5aa8f0'], [0.62, '#9ed3f7'], [0.84, '#cfeaf7'], [1, '#e8f5d8']]);
    bloom(ctx, 212 - camX * 0.02, 36, 46, 'rgba(255,246,190,0.42)', 'rgba(255,240,150,0)');
    ctx.fillStyle = '#fff3b0';
    ctx.beginPath(); ctx.arc(212 - camX * 0.02, 36, 16, 0, 7); ctx.fill();
    ctx.fillStyle = '#fffbd8';
    ctx.beginPath(); ctx.arc(212 - camX * 0.02, 36, 11, 0, 7); ctx.fill();

    off = (camX * 0.06) % 150;                    // high thin cloud
    for (i = -1; i < 4; i++) {
      cloud(ctx, i * 150 - off + 20, 22 + Math.sin(t / 90 + i) * 2, 1.5,
            'rgba(255,255,255,0.55)', 'rgba(214,234,247,0.4)');
    }
    off = (camX * 0.18) % 120;                    // nearer cumulus
    for (i = -1; i < 4; i++) {
      x = i * 120 - off;
      cloud(ctx, x + 10, 34 + Math.sin(t / 60 + i) * 2, 1, '#ffffff', '#dceaf7');
      cloud(ctx, x + 74, 64 + Math.sin(t / 50 + i) * 2, 0.8, '#ffffff', '#dceaf7');
    }
    // distant hills
    off = (camX * 0.22) % 170;
    ctx.fillStyle = '#8fc0d8';
    for (i = -1; i < 4; i++) {
      x = i * 170 - off;
      ctx.beginPath();
      ctx.moveTo(x, 190); ctx.quadraticCurveTo(x + 45, 128, x + 92, 190);
      ctx.closePath(); ctx.fill();
      ctx.beginPath();
      ctx.moveTo(x + 70, 190); ctx.quadraticCurveTo(x + 120, 142, x + 172, 190);
      ctx.closePath(); ctx.fill();
    }
    haze(ctx, 140, 60, 'rgba(190,225,240,0.55)');

    var far = ['#3c5a3a', '#4e6e48', '#6d9c66', '#89b880', '#a3cc98'];
    var near = ['#3a2410', '#5c3a18', '#245c2c', '#2d7136', '#3d8a44'];
    off = (camX * 0.38) % 58;                     // middle wood
    for (i = -1; i < 7; i++) tree(ctx, i * 58 - off + 4, 142, 0.75, far);
    haze(ctx, 168, 44, 'rgba(180,215,230,0.34)');
    off = (camX * 0.62) % 64;                     // near wood
    for (i = -1; i < 7; i++) {
      x = i * 64 - off;
      tree(ctx, x + 6, 150, 1, near);
      tree(ctx, x + 38, 162, 0.8, near);
    }
    ctx.fillStyle = '#25611f'; ctx.fillRect(0, 206, 256, 34);
    ctx.fillStyle = '#2f7a2b'; ctx.fillRect(0, 206, 256, 3);
  }

  return {
    R: R,
    heroSize: heroSize,
    hero: drawHero,
    rakshasa: drawRakshasa,
    deer: drawDeer,
    shell: drawDeerShell,
    crow: drawCrow,
    ravana: drawRavana,
    sita: drawSita,
    sanjeevani: drawSanjeevani,
    bow: drawBow,
    blessing: drawBlessing,
    coin: drawCoin,
    arrow: drawArrow,
    fireball: drawFireball,
    tile: drawTile,
    chunk: drawChunk,
    shrine: drawShrine,
    background: background
  };
})();
