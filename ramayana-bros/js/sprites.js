/* ------------------------------------------------------------------
 * Ramayana Bros. -- sprite art.
 *
 * Every character, item, tile and backdrop is plotted as coloured
 * rectangles on the 256x240 pixel grid, so the whole game ships as
 * source with no binary assets. Each draw*() call takes the top-left
 * corner of the sprite box and draws inside it.
 * ------------------------------------------------------------------ */

var Sprites = (function () {

  var C = {
    // Rama
    skin: '#5b9de0', skinD: '#3d78b8', skinL: '#8fc4f5',
    hair: '#181528', dhoti: '#ffb327', dhotiD: '#cf7f0d',
    gold: '#ffd042', goldD: '#c8901a', goldL: '#fff2b0',
    white: '#fdfdfd', black: '#12101a', red: '#e0403a', sandal: '#5a3a1c',
    // rakshasa
    demon: '#4e8c3a', demonD: '#2f5f26', bone: '#e8dbb4', eyeY: '#ffe24a',
    // deer
    deer: '#f0b53c', deerL: '#ffdd97', deerD: '#a9741a',
    // crow
    crow: '#2b2438', crowL: '#453a5e', beak: '#f0a83c',
    // ravana
    rav: '#4a2f63', ravD: '#2e1c3f', ravL: '#6b4a8a', ravSkin: '#7b4f9c',
    // sita
    sari: '#3fa66b', sariD: '#2b7a4c', sariR: '#d9434f'
  };

  /* Palette swaps used while the Hanuman blessing (star) is active. */
  var STAR_SETS = [
    { skin: '#ffe066', dhoti: '#ff6a3d', gold: '#fff6c9' },
    { skin: '#8ef0a0', dhoti: '#ffd042', gold: '#ffffff' },
    { skin: '#ff9de0', dhoti: '#6ec8ff', gold: '#fff2b0' },
    { skin: '#c0a6ff', dhoti: '#ff5f6d', gold: '#ffe066' }
  ];

  function shade(base, key, on) { return on ? on[key] || base[key] : base[key]; }

  /* ---------------- low level ---------------- */

  function makePen(ctx, x, y, w, flip) {
    // Returns r(px,py,pw,ph,colour) in sprite-local coords, mirrored when
    // the sprite faces left so every sprite only needs a right-facing pose.
    if (flip) {
      return function (px, py, pw, ph, c) {
        ctx.fillStyle = c;
        ctx.fillRect(x + (w - px - pw), y + py, pw, ph);
      };
    }
    return function (px, py, pw, ph, c) {
      ctx.fillStyle = c;
      ctx.fillRect(x + px, y + py, pw, ph);
    };
  }

  /* ---------------- Rama (the player) ----------------
   * o = { big, bow, state:'stand'|'walk'|'jump'|'duck'|'dead'|'climb',
   *       frame, dir, star, t }                                        */

  function heroSize(o) {
    if (o.state === 'duck') return { w: 16, h: o.big ? 18 : 16 };
    return { w: 16, h: o.big ? 28 : 16 };
  }

  function drawHero(ctx, x, y, o) {
    var big = !!o.big, duck = o.state === 'duck' && big;
    var W = 16, H = duck ? 18 : (big ? 28 : 16);
    var p = makePen(ctx, x, y, W, o.dir < 0);

    // palette: cycles while invincible, pales while the bow is held
    var sk = C.skin, skD = C.skinD, dh = C.dhoti, gd = C.gold;
    if (o.bow) { dh = '#f4f4f8'; }
    if (o.star) {
      var st = STAR_SETS[(o.t >> 1) % STAR_SETS.length];
      sk = st.skin; dh = st.dhoti; gd = st.gold;
    }

    var crownH = big ? 4 : 3;
    var headH  = big ? 9 : 6;
    var torsoH = big ? 8 : 4;
    if (duck) { crownH = 3; headH = 6; torsoH = 6; }
    var crownY = 0, headY = crownY + crownH, torsoY = headY + headH;
    var legY = torsoY + torsoH, legH = H - legY;
    var hairH = big ? 2 : 1;

    // ---- crown (mukuta)
    p(7, crownY, 3, 1, gd);
    p(5, crownY + 1, 7, crownH - 2, gd);
    p(8, crownY + 1, 2, 1, C.red);
    p(3, crownY + crownH - 1, 11, 1, C.goldD);

    // ---- head
    p(3, headY, 11, hairH, C.hair);              // hair
    p(3, headY, 2, headH - 1, C.hair);           // hair falling behind
    p(5, headY + hairH, 9, headH - hairH - 1, sk);
    p(5, headY + headH - 1, 9, 1, skD);          // jaw shadow
    p(4, headY + hairH + 1, 1, 2, C.hair);       // ear lock
    p(8, headY + hairH, 1, 2, C.red);            // tilak
    if (o.state === 'dead') {
      p(10, headY + hairH + 1, 3, 1, C.black);   // closed eyes
      p(10, headY + headH - 2, 2, 1, skD);
    } else {
      p(10, headY + hairH + 1, 2, big ? 3 : 2, C.white);
      p(11, headY + hairH + 1, 1, big ? 2 : 1, C.black);
      if (big) p(11, headY + headH - 2, 2, 1, skD);
    }

    // ---- torso
    var tw = big ? 10 : 8, tx = big ? 3 : 4;
    p(tx, torsoY, tw, torsoH, sk);
    p(tx + 1, torsoY, tw - 2, 1, gd);            // necklace
    for (var i = 0; i < torsoH - 2; i++) p(tx + 2 + i, torsoY + i, 1, 1, C.white);
    p(tx, torsoY + torsoH - 2, tw, 2, dh);       // waist cloth
    p(tx, torsoY + torsoH - 2, tw, 1, C.goldD);  // belt

    // ---- arms
    var armH = big ? 5 : 3, swing = 0;
    if (o.state === 'walk') swing = (o.frame % 4 === 1) ? -1 : (o.frame % 4 === 3 ? 1 : 0);
    if (o.state === 'jump') {
      p(1, torsoY - 1, 2, armH, sk);
      p(13, torsoY - 2, 2, armH, sk);
    } else if (o.state === 'dead') {
      p(1, torsoY - 3, 2, armH, sk);
      p(13, torsoY - 3, 2, armH, sk);
    } else if (duck) {
      p(2, torsoY + 1, 3, 2, sk);
      p(12, torsoY + 1, 3, 2, sk);
    } else {
      p(1, torsoY + 1 + swing, 2, armH, sk);
      p(13, torsoY + 1 - swing, 2, armH, sk);
    }

    // ---- the Kodanda bow, carried in the forward hand
    if (o.bow && o.state !== 'dead') {
      var by = torsoY - 2, bh = big ? 11 : 8;
      p(14, by + 2, 1, bh - 3, gd);
      p(13, by + 1, 1, 1, gd); p(13, by + bh - 1, 1, 1, gd);
      p(12, by, 1, 1, gd);     p(12, by + bh, 1, 1, gd);
      p(12, by + 1, 1, bh - 1, '#efe6cc');       // string
    }

    // ---- legs
    if (o.state === 'dead') {
      p(5, legY, 3, legH, sk); p(9, legY, 3, legH, sk);
      p(4, legY + legH - 1, 4, 1, C.sandal); p(9, legY + legH - 1, 4, 1, C.sandal);
    } else if (duck) {
      p(3, legY, 11, legH - 1, dh);
      p(3, legY, 11, 1, C.goldD);
      p(3, legY + legH - 1, 5, 1, C.sandal);
      p(9, legY + legH - 1, 5, 1, C.sandal);
    } else {
      p(3, legY, 11, 1, dh);                     // dhoti hem
      var pose;
      if (o.state === 'jump') pose = [2, 9];
      else if (o.state === 'walk') pose = [[4, 9], [1, 10], [5, 8], [1, 10]][o.frame % 4];
      else pose = [4, 9];
      p(pose[0], legY + 1, 3, legH - 1, sk);
      p(pose[1], legY + 1, 3, legH - 1, sk);
      p(pose[0] - 1, legY + legH - 1, 4, 1, C.sandal);
      p(pose[1], legY + legH - 1, 4, 1, C.sandal);
    }
  }

  /* ---------------- Rakshasa (walking demon) ---------------- */

  function drawRakshasa(ctx, x, y, frame, dir, squashed) {
    var p = makePen(ctx, x, y, 16, dir < 0);
    if (squashed) {
      p(1, 10, 14, 4, C.demonD);
      p(3, 8, 10, 2, C.demon);
      p(2, 8, 1, 2, C.bone); p(13, 8, 1, 2, C.bone);
      p(4, 11, 2, 1, C.eyeY); p(10, 11, 2, 1, C.eyeY);
      return;
    }
    // horns
    p(2, 0, 1, 1, C.bone); p(2, 1, 2, 3, C.bone);
    p(13, 0, 1, 1, C.bone); p(12, 1, 2, 3, C.bone);
    // body
    p(3, 3, 10, 9, C.demon);
    p(2, 5, 12, 6, C.demon);
    p(3, 10, 10, 2, C.demonD);
    p(2, 4, 1, 1, C.demonD); p(13, 4, 1, 1, C.demonD);
    // face
    p(4, 5, 3, 1, C.demonD); p(9, 5, 3, 1, C.demonD);
    p(4, 6, 3, 2, C.eyeY); p(9, 6, 3, 2, C.eyeY);
    p(5, 7, 1, 1, C.black); p(10, 7, 1, 1, C.black);
    p(5, 9, 6, 2, '#2a1220');
    p(5, 9, 1, 1, C.white); p(10, 9, 1, 1, C.white);
    // feet
    var f = frame % 2;
    if (f) { p(1, 12, 5, 4, C.demonD); p(10, 12, 5, 4, C.demonD); }
    else   { p(2, 12, 5, 4, C.demonD); p(9, 12, 5, 4, C.demonD); }
    p(1, 15, 5, 1, '#1d3a18'); p(10, 15, 5, 1, '#1d3a18');
  }

  /* ---------------- Maricha, the golden deer ---------------- */

  function drawDeer(ctx, x, y, frame, dir) {
    var p = makePen(ctx, x, y, 16, dir < 0);
    // antlers
    p(9, 0, 1, 3, C.deerD); p(8, 1, 1, 1, C.deerD); p(10, 1, 1, 1, C.deerD);
    p(12, 0, 1, 3, C.deerD); p(13, 1, 1, 1, C.deerD);
    // head + neck
    p(9, 3, 5, 5, C.deer);
    p(13, 6, 3, 2, C.deerL);
    p(15, 6, 1, 1, C.black);
    p(11, 4, 1, 1, C.black);
    p(8, 7, 3, 4, C.deer);
    // body
    p(2, 9, 11, 7, C.deer);
    p(2, 14, 11, 2, C.deerD);
    p(4, 11, 1, 1, C.white); p(7, 10, 1, 1, C.white); p(9, 12, 1, 1, C.white);
    p(1, 9, 2, 3, C.deerL);            // tail
    // legs
    var f = frame % 2;
    if (f) { p(2, 16, 2, 6, C.deerD); p(11, 16, 2, 6, C.deerD); }
    else   { p(4, 16, 2, 6, C.deerD); p(9, 16, 2, 6, C.deerD); }
    p(2, 21, 3, 1, '#6b4611'); p(9, 21, 3, 1, '#6b4611');
  }

  /* Curled-up deer: the shell you can kick. */
  function drawDeerShell(ctx, x, y, frame, spinning) {
    var p = makePen(ctx, x, y, 16, false);
    p(3, 1, 10, 3, C.deer);
    p(1, 3, 14, 8, C.deer);
    p(1, 10, 14, 3, C.deerD);
    p(2, 0, 1, 2, C.deerD); p(13, 0, 1, 2, C.deerD);      // antler nubs
    var o = spinning ? (frame % 4) : 0;
    p(3 + o, 5, 2, 2, C.white);
    p(8 + o, 7, 2, 2, C.white);
    p(11 - o, 4, 1, 1, C.deerL);
    p(1, 3, 14, 1, C.deerL);
  }

  /* ---------------- Kakasura, the crow demon ---------------- */

  function drawCrow(ctx, x, y, frame, dir) {
    var p = makePen(ctx, x, y, 16, dir < 0);
    var up = (frame % 2) === 0;
    if (up) { p(2, 0, 7, 4, C.crowL); p(1, 2, 4, 2, C.crow); }
    else    { p(1, 7, 8, 4, C.crowL); p(2, 6, 5, 2, C.crow); }
    p(4, 4, 8, 6, C.crow);
    p(9, 2, 5, 4, C.crow);
    p(13, 4, 3, 2, C.beak);
    p(11, 3, 1, 1, C.red);
    p(0, 5, 4, 2, C.crow);              // tail
    p(6, 9, 2, 3, C.beak);              // talons
  }

  /* ---------------- Ravana (boss, 32x44) ---------------- */

  function drawRavana(ctx, x, y, o) {
    var p = makePen(ctx, x, y, 32, o.dir < 0);
    var skin = o.flash ? '#ffd7d7' : C.ravSkin;
    var robe = o.flash ? '#ffb0b0' : C.rav;
    // the ten heads: a back row of nine plus the crowned central face
    for (var i = 0; i < 5; i++) {
      var hx = 1 + i * 6;
      p(hx, 4, 5, 6, C.ravD);
      p(hx + 1, 5, 3, 4, skin);
      p(hx + 1, 6, 1, 1, C.red); p(hx + 3, 6, 1, 1, C.red);
      p(hx, 3, 5, 1, C.gold);
    }
    for (var j = 0; j < 4; j++) {
      var bx = 4 + j * 6;
      p(bx, 0, 5, 5, C.ravD);
      p(bx + 1, 1, 3, 3, skin);
      p(bx + 1, 2, 1, 1, C.red); p(bx + 3, 2, 1, 1, C.red);
    }
    // central head
    p(11, 6, 10, 10, C.ravD);
    p(12, 8, 8, 7, skin);
    p(11, 5, 10, 2, C.gold);
    p(13, 4, 6, 1, C.gold);
    p(15, 5, 2, 1, C.red);
    p(13, 10, 2, 2, C.red); p(17, 10, 2, 2, C.red);       // burning eyes
    p(12, 13, 8, 1, C.black);                             // moustache
    p(14, 14, 4, 1, C.white);                             // bared teeth
    // torso
    var f = o.frame % 2;
    p(7, 16, 18, 3, C.gold);                              // shoulder plate
    p(8, 19, 16, 9, robe);
    p(8, 19, 1, 9, C.ravD); p(23, 19, 1, 9, C.ravD);      // edge shading
    p(10, 20, 12, 1, C.goldD);
    p(14, 21, 4, 4, C.gold);                              // chest jewel
    p(15, 22, 2, 2, C.red);
    p(8, 26, 16, 2, C.goldD);                             // waist sash
    p(4, 18, 4, 8, skin);  p(24, 18, 4, 8, skin);         // arms
    p(4, 17, 4, 1, C.gold); p(24, 17, 4, 1, C.gold);
    p(3, 25, 5, 4, C.ravD); p(24, 25, 5, 4, C.ravD);      // fists
    // mace, swung with the walk cycle
    p(27, 10 + f, 3, 16, '#6f6f7d');
    p(25, 6 + f, 7, 6, '#9aa0b0');
    p(26, 5 + f, 5, 1, '#c9d0dd');
    p(24, 8 + f, 1, 2, '#6f6f7d'); p(31, 8 + f, 1, 2, '#6f6f7d');
    // legs
    p(9, 28, 6, 12 + (f ? 0 : 1), robe);
    p(17, 28, 6, 13 - (f ? 0 : 1), robe);
    p(9, 28, 1, 12, C.ravD); p(22, 28, 1, 12, C.ravD);
    p(8, 40, 8, 4, C.ravD); p(16, 40, 8, 4, C.ravD);
    p(8, 43, 8, 1, C.gold); p(16, 43, 8, 1, C.gold);
  }

  /* ---------------- Sita ---------------- */

  function drawSita(ctx, x, y, t) {
    var p = makePen(ctx, x, y, 16, false);
    var bob = (Math.floor(t / 20) % 2);
    y += bob;
    p = makePen(ctx, x, y, 16, false);
    p(4, 0, 8, 3, C.hair);
    p(3, 2, 10, 2, C.hair);
    p(4, 3, 8, 6, '#f0c08a');
    p(4, 3, 2, 6, C.hair); p(11, 3, 2, 5, C.hair);
    p(7, 5, 1, 1, C.black); p(10, 5, 1, 1, C.black);
    p(8, 4, 1, 1, C.red);
    p(5, 2, 6, 1, C.gold);
    p(4, 9, 8, 2, C.gold);                     // necklace
    p(3, 10, 10, 8, C.sari);
    p(3, 10, 10, 2, C.sariR);
    p(9, 12, 4, 6, C.sariR);                   // pallu
    p(3, 17, 10, 1, C.gold);
    p(2, 12, 2, 4, '#f0c08a'); p(12, 12, 2, 4, '#f0c08a');
    p(5, 18, 3, 3, C.sari); p(9, 18, 3, 3, C.sari);
    p(5, 21, 3, 1, '#f0c08a'); p(9, 21, 3, 1, '#f0c08a');
  }

  /* ---------------- items ---------------- */

  function drawSanjeevani(ctx, x, y) {          // grow power-up
    var p = makePen(ctx, x, y, 16, false);
    p(4, 2, 8, 2, '#5fbf4a');
    p(2, 4, 12, 5, '#5fbf4a');
    p(2, 4, 12, 1, '#8ee06f');
    p(1, 6, 2, 3, '#3f9633'); p(13, 6, 2, 3, '#3f9633');
    p(6, 5, 4, 3, C.red);
    p(7, 5, 1, 1, '#ff9a94');
    p(3, 9, 10, 2, '#3f9633');
    p(6, 11, 4, 3, '#c98f56');
    p(4, 14, 8, 2, '#8b5a2b');
    p(4, 14, 8, 1, '#b87c42');
  }

  function drawBow(ctx, x, y, t) {             // Kodanda -- shoot arrows
    var p = makePen(ctx, x, y, 16, false);
    var g = ((t >> 3) % 2) ? C.goldL : C.gold;
    // the limb, curving away from the string
    p(6, 0, 3, 1, g);
    p(4, 1, 2, 1, g);
    p(3, 2, 2, 2, g);
    p(2, 4, 2, 8, g);
    p(3, 12, 2, 2, g);
    p(4, 14, 2, 1, g);
    p(6, 15, 3, 1, g);
    p(2, 6, 1, 4, C.goldL);                    // highlight
    p(3, 7, 3, 2, C.goldD);                    // grip
    // string
    p(9, 1, 1, 14, '#efe6cc');
    // nocked arrow
    p(6, 7, 8, 2, '#c98f56');
    p(13, 6, 3, 4, '#dfe4ec');
    p(6, 6, 1, 1, C.white); p(6, 9, 1, 1, C.white);
  }

  function drawBlessing(ctx, x, y, t) {        // Hanuman's blessing -- star
    var p = makePen(ctx, x, y, 16, false);
    var pulse = (t >> 2) % 4;
    var a = ['#ff8a2b', '#ffb347', '#ffd042', '#ff6a3d'][pulse];
    var b = ['#ffd042', '#fff2b0', '#ff8a2b', '#ffd042'][pulse];
    p(7, 0, 2, 3, a);
    p(6, 3, 4, 2, a);
    p(1, 5, 14, 2, a);
    p(2, 7, 12, 2, b);
    p(3, 9, 10, 2, a);
    p(2, 11, 4, 3, a); p(10, 11, 4, 3, a);
    p(1, 14, 3, 2, a); p(12, 14, 3, 2, a);
    p(6, 6, 4, 4, C.white);
    p(7, 7, 2, 2, '#c8501e');                  // tiny Hanuman face mark
  }

  var COIN_W = [8, 6, 4, 2, 4, 6];
  function drawCoin(ctx, x, y, frame) {
    var w = COIN_W[((frame % COIN_W.length) + COIN_W.length) % COIN_W.length];
    var cx = x + 8 - Math.floor(w / 2);
    if (w > 2) {                                 // bevelled top and bottom
      ctx.fillStyle = C.goldD;
      ctx.fillRect(cx + 1, y + 2, w - 2, 1);
      ctx.fillRect(cx + 1, y + 13, w - 2, 1);
    }
    ctx.fillStyle = C.goldD; ctx.fillRect(cx, y + 3, w, 10);
    ctx.fillStyle = C.gold;  ctx.fillRect(cx, y + 4, w, 8);
    if (w > 3) {
      ctx.fillStyle = C.goldL; ctx.fillRect(cx + 1, y + 4, 1, 8);
      ctx.fillStyle = C.goldD; ctx.fillRect(cx + Math.floor(w / 2), y + 6, 1, 4);
    }
  }

  function drawArrow(ctx, x, y, dir) {
    var p = makePen(ctx, x, y, 8, dir < 0);
    p(0, 3, 6, 2, '#c98f56');
    p(6, 2, 2, 4, '#dfe4ec');
    p(0, 1, 2, 2, C.white); p(0, 5, 2, 2, C.white);
    p(0, 3, 6, 1, '#e0b783');
  }

  function drawFireball(ctx, x, y, t) {
    var p = makePen(ctx, x, y, 10, false);
    var f = (t >> 2) % 2;
    p(2, 2, 6, 6, '#ff8a2b');
    p(3, 3, 4, 4, '#ffd042');
    p(4, 4, 2, 2, C.white);
    p(f ? 0 : 1, 3, 2, 4, '#e0403a');
    p(8, f ? 2 : 4, 2, 3, '#e0403a');
  }

  /* ---------------- tiles ---------------- */

  var THEME = {
    forest: { dirt: '#9c5a2b', dirtD: '#6d3d1b', top: '#4aa83f', topD: '#2f7a2b',
              brick: '#c1682f', brickD: '#8a4520', stone: '#a9a29a', stoneD: '#6f6a63' },
    mountain: { dirt: '#7d7b8c', dirtD: '#535163', top: '#b8b3c6', topD: '#7d7b8c',
              brick: '#8d8598', brickD: '#5d566b', stone: '#b0aab8', stoneD: '#6f6a7a' },
    lanka:  { dirt: '#4a2b3a', dirtD: '#2c1723', top: '#7a2f3c', topD: '#4a1a24',
              brick: '#7b3140', brickD: '#4d1c27', stone: '#6a5a72', stoneD: '#3f3547' },
    /* the stepwells: cut sandstone seen by lamplight */
    cave:   { dirt: '#4a4064', dirtD: '#2b2440', top: '#5d5280', topD: '#3a3158',
              brick: '#4f4470', brickD: '#2e2748', stone: '#655a86', stoneD: '#3b3358' }
  };

  /* nb: bit 0 set when the matching tile sits to the left (this is the
     right half), bit 1 set when one sits above (this is a lower row). */
  function drawTile(ctx, x, y, ch, theme, t, openAbove, nb) {
    var T = THEME[theme] || THEME.forest;
    var f;
    switch (ch) {
      case '#':
        ctx.fillStyle = T.dirt; ctx.fillRect(x, y, 16, 16);
        ctx.fillStyle = T.dirtD;
        ctx.fillRect(x, y + 15, 16, 1); ctx.fillRect(x + 7, y + 4, 2, 2);
        ctx.fillRect(x + 2, y + 10, 2, 2); ctx.fillRect(x + 12, y + 8, 2, 2);
        if (openAbove) {
          ctx.fillStyle = T.top; ctx.fillRect(x, y, 16, 5);
          ctx.fillStyle = T.topD; ctx.fillRect(x, y + 5, 16, 1);
          ctx.fillStyle = T.top;
          ctx.fillRect(x + 1, y - 2, 2, 2); ctx.fillRect(x + 6, y - 3, 2, 3);
          ctx.fillRect(x + 12, y - 2, 2, 2);
        }
        break;
      case 'S':
        ctx.fillStyle = T.stone; ctx.fillRect(x, y, 16, 16);
        ctx.fillStyle = T.stoneD;
        ctx.fillRect(x, y, 16, 1); ctx.fillRect(x, y + 15, 16, 1);
        ctx.fillRect(x, y, 1, 16); ctx.fillRect(x + 15, y, 1, 16);
        ctx.fillRect(x + 3, y + 3, 10, 1); ctx.fillRect(x + 3, y + 12, 10, 1);
        ctx.fillStyle = '#ffffff22'; ctx.fillRect(x + 2, y + 5, 12, 6);
        break;
      case 'B':
        ctx.fillStyle = T.brick; ctx.fillRect(x, y, 16, 16);
        ctx.fillStyle = T.brickD;
        ctx.fillRect(x, y, 16, 1);
        ctx.fillRect(x, y + 7, 16, 1);
        ctx.fillRect(x, y + 15, 16, 1);
        ctx.fillRect(x + 7, y + 1, 1, 6);
        ctx.fillRect(x + 3, y + 8, 1, 7);
        ctx.fillRect(x + 11, y + 8, 1, 7);
        break;
      case '?': case 'M': case 'W': case 'T':
        f = (t >> 3) % 4;
        ctx.fillStyle = f === 3 ? '#d99b1c' : C.gold;
        ctx.fillRect(x, y, 16, 16);
        ctx.fillStyle = C.goldD;
        ctx.fillRect(x, y, 16, 1); ctx.fillRect(x, y + 15, 16, 1);
        ctx.fillRect(x, y, 1, 16); ctx.fillRect(x + 15, y, 1, 16);
        ctx.fillRect(x + 1, y + 1, 2, 2); ctx.fillRect(x + 13, y + 1, 2, 2);
        ctx.fillRect(x + 1, y + 13, 2, 2); ctx.fillRect(x + 13, y + 13, 2, 2);
        // a lotus mark instead of the question mark
        ctx.fillStyle = f === 3 ? '#8a5f0c' : '#a3711a';
        ctx.fillRect(x + 7, y + 4, 2, 4);
        ctx.fillRect(x + 4, y + 6, 8, 2);
        ctx.fillRect(x + 5, y + 5, 2, 2); ctx.fillRect(x + 9, y + 5, 2, 2);
        ctx.fillRect(x + 5, y + 8, 6, 2);
        ctx.fillRect(x + 6, y + 10, 4, 1);
        break;
      case 'U':
        ctx.fillStyle = T.stoneD; ctx.fillRect(x, y, 16, 16);
        ctx.fillStyle = '#00000044';
        ctx.fillRect(x, y, 16, 2); ctx.fillRect(x, y + 14, 16, 2);
        ctx.fillStyle = '#ffffff18'; ctx.fillRect(x + 2, y + 3, 12, 10);
        break;
      case 'P': case 'p':
        // temple pillar; 'P' is a capital (top) tile, 'p' is the shaft
        ctx.fillStyle = '#cfc6b0'; ctx.fillRect(x, y, 16, 16);
        ctx.fillStyle = '#9c9078'; ctx.fillRect(x + 13, y, 3, 16);
        ctx.fillStyle = '#efe8d5'; ctx.fillRect(x + 2, y, 3, 16);
        if (ch === 'P') {
          ctx.fillStyle = '#b8a878'; ctx.fillRect(x - 1, y, 18, 5);
          ctx.fillStyle = C.gold;    ctx.fillRect(x - 1, y + 1, 18, 1);
          ctx.fillStyle = '#8d7f58'; ctx.fillRect(x - 1, y + 5, 18, 1);
        } else {
          ctx.fillStyle = '#9c9078';
          ctx.fillRect(x, y + 5, 16, 1); ctx.fillRect(x, y + 11, 16, 1);
        }
        break;
      case '=':
        ctx.fillStyle = '#8b5a2b'; ctx.fillRect(x, y, 16, 6);
        ctx.fillStyle = '#b87c42'; ctx.fillRect(x, y, 16, 2);
        ctx.fillStyle = '#5d3a18'; ctx.fillRect(x, y + 5, 16, 1);
        ctx.fillRect(x + 5, y + 2, 1, 3); ctx.fillRect(x + 11, y + 2, 1, 3);
        break;
      case 'D': {
        // mouth of a stepwell: a stone kerb with steps disappearing into it
        var right = !!(nb & 1);
        ctx.fillStyle = '#0b0a14'; ctx.fillRect(x, y, 16, 16);
        ctx.fillStyle = '#cfc6b0'; ctx.fillRect(x, y, 16, 4);
        ctx.fillStyle = C.gold;   ctx.fillRect(x, y + 1, 16, 1);
        ctx.fillStyle = '#8d7f58'; ctx.fillRect(x, y + 4, 16, 1);
        var ox = right ? 12 : 0;
        ctx.fillStyle = '#b8a878'; ctx.fillRect(x + ox, y + 4, 4, 12);
        ctx.fillStyle = '#efe8d5'; ctx.fillRect(x + (right ? 15 : 0), y + 4, 1, 12);
        // a couple of steps down into the dark
        ctx.fillStyle = '#5b5270';
        ctx.fillRect(x + (right ? 8 : 4), y + 7, 4, 2);
        ctx.fillStyle = '#443c58';
        ctx.fillRect(x + (right ? 6 : 6), y + 11, 4, 2);
        break;
      }
      case 'E': {
        // lit archway leading back to the surface
        var r = !!(nb & 1), low = !!(nb & 2);
        ctx.fillStyle = '#2b2440'; ctx.fillRect(x, y, 16, 16);
        var gx = r ? 0 : 4, gw = 12;
        var glow = ctx.createLinearGradient(0, y, 0, y + 16);
        if (low) { glow.addColorStop(0, '#ffb347'); glow.addColorStop(1, '#fff0c0'); }
        else     { glow.addColorStop(0, '#6b4a2a'); glow.addColorStop(1, '#ffb347'); }
        ctx.fillStyle = glow;
        ctx.fillRect(x + gx, y + (low ? 0 : 4), gw, low ? 16 : 12);
        if (!low) {                          // the curve of the arch head
          ctx.fillStyle = '#2b2440';
          ctx.fillRect(x + (r ? 12 : 0), y + 4, 4, 3);
          ctx.fillRect(x + (r ? 13 : 0), y + 7, 3, 2);
        }
        ctx.fillStyle = '#cfc6b0';           // jamb
        ctx.fillRect(x + (r ? 14 : 0), y, 2, 16);
        if (!low) { ctx.fillStyle = '#b8a878'; ctx.fillRect(x, y, 16, 3);
                    ctx.fillStyle = C.gold;   ctx.fillRect(x, y + 1, 16, 1); }
        break;
      }
      case '~':
        var deep = theme === 'lanka' ? '#8e1f12' : '#1e4f9c';
        var mid  = theme === 'lanka' ? '#c8321e' : '#2f6fd0';
        var crest = theme === 'lanka' ? '#ff8a2b' : '#5fa0f0';
        ctx.fillStyle = openAbove ? mid : deep;
        ctx.fillRect(x, y, 16, 16);
        if (openAbove) {
          f = Math.round(Math.sin((t + x) / 11) * 1.5);
          ctx.fillStyle = crest;
          ctx.fillRect(x, y + 1 + f, 16, 3);
          ctx.fillStyle = theme === 'lanka' ? '#ffd042' : '#a8d0ff';
          ctx.fillRect(x + ((t >> 2) % 13), y + 2 + f, 3, 1);
          ctx.fillStyle = mid;
          ctx.fillRect(x, y + 4 + f, 16, 12 - f);
        }
        break;
    }
  }

  /* Debris thrown out when a brick is smashed. */
  function drawChunk(ctx, x, y, theme, rot) {
    var T = THEME[theme] || THEME.forest;
    ctx.fillStyle = T.brick; ctx.fillRect(x, y, 6, 6);
    ctx.fillStyle = T.brickD;
    ctx.fillRect(x, y, 6, 1);
    ctx.fillRect(x + (rot % 2 ? 1 : 4), y + 2, 1, 4);
  }

  /* ---------------- the goal shrine ---------------- */

  /* The goal shrine: a 48x152 gopuram, anchored bottom-left. It is built
     tall on purpose -- it is the last thing in the stage and has to read as
     taller than the staircase that climbs up to it. */
  function drawShrine(ctx, x, y, t, lit) {
    var top = y - 152;
    var band = ['#f0e6cd', '#e0d3b2'];

    // plinth
    ctx.fillStyle = '#b8a878'; ctx.fillRect(x, y - 10, 48, 10);
    ctx.fillStyle = '#8d7f58'; ctx.fillRect(x, y - 2, 48, 2);
    ctx.fillStyle = '#d9cfae'; ctx.fillRect(x + 2, y - 10, 44, 2);

    // main body with its doorway
    ctx.fillStyle = '#e8dfc8'; ctx.fillRect(x + 3, top + 84, 42, 58);
    ctx.fillStyle = '#c9bd9c'; ctx.fillRect(x + 3, top + 84, 42, 3);
    ctx.fillStyle = '#d3c7a4'; ctx.fillRect(x + 3, top + 84, 3, 58);
    ctx.fillStyle = '#f2ead6'; ctx.fillRect(x + 42, top + 84, 3, 58);
    // pilasters
    ctx.fillStyle = '#cdbf9a';
    ctx.fillRect(x + 9, top + 92, 3, 50);
    ctx.fillRect(x + 36, top + 92, 3, 50);
    // doorway
    ctx.fillStyle = '#c9bd9c'; ctx.fillRect(x + 15, top + 100, 18, 42);
    ctx.fillStyle = '#3a2246'; ctx.fillRect(x + 17, top + 104, 14, 38);
    ctx.fillStyle = lit ? '#ffd042' : '#6b4a8a';
    ctx.fillRect(x + 21, top + 112, 6, 12);            // lamp in the sanctum
    if (lit) { ctx.fillStyle = '#fff2b0'; ctx.fillRect(x + 22, top + 114, 4, 6); }

    // six receding tiers
    for (var i = 0; i < 6; i++) {
      var tw = 40 - i * 5, ty = top + 84 - (i + 1) * 12;
      var tx = x + 24 - tw / 2;
      ctx.fillStyle = band[i % 2];
      ctx.fillRect(tx, ty, tw, 12);
      ctx.fillStyle = '#c9bd9c';
      ctx.fillRect(tx, ty + 10, tw, 2);
      ctx.fillStyle = '#b3a47e';
      for (var n = 0; n < 3; n++) ctx.fillRect(tx + 3 + n * (tw - 8) / 2, ty + 3, 3, 5);
    }

    // kalasha finial
    ctx.fillStyle = '#e0d3b2'; ctx.fillRect(x + 18, top + 6, 12, 6);
    ctx.fillStyle = C.gold;    ctx.fillRect(x + 20, top, 8, 7);
    ctx.fillStyle = C.goldL;   ctx.fillRect(x + 23, top - 5, 2, 6);
    ctx.fillStyle = C.gold;    ctx.fillRect(x + 22, top - 7, 4, 2);

    // banner on a pole beside the tower
    var wave = Math.round(Math.sin(t / 8) * 1.5);
    ctx.fillStyle = '#8d7f58'; ctx.fillRect(x + 45, top + 30, 2, 60);
    ctx.fillStyle = C.red;     ctx.fillRect(x + 47, top + 34 + wave, 12, 9);
    ctx.fillStyle = C.gold;    ctx.fillRect(x + 49, top + 37 + wave, 8, 2);
  }

  /* ---------------- backdrops ---------------- */

  function hash(n) { var s = Math.sin(n * 127.1) * 43758.5453; return s - Math.floor(s); }

  function background(ctx, theme, camX, t) {
    if (theme === 'cave') {
      // a baoli: tier on tier of stone arches, most of it lost in the dark
      ctx.fillStyle = '#0b0a14';
      ctx.fillRect(0, 0, 256, 240);
      var off = (camX * 0.4) % 64;
      for (var a = -1; a < 6; a++) {
        var ax = a * 64 - off;
        for (var row = 0; row < 3; row++) {
          var ay = 40 + row * 46;
          ctx.fillStyle = row === 0 ? '#1d1830' : (row === 1 ? '#181428' : '#131020');
          ctx.fillRect(ax, ay, 56, 38);
          ctx.fillStyle = '#0b0a14';
          ctx.fillRect(ax + 8, ay + 12, 40, 26);
          ctx.fillRect(ax + 12, ay + 6, 32, 8);
          ctx.fillStyle = row === 0 ? '#2a2340' : '#1d1830';
          ctx.fillRect(ax, ay, 56, 3);
        }
      }
      // oil lamps set into the walls
      for (var l = -1; l < 5; l++) {
        var lx = l * 64 - off + 28;
        var flick = ((t + l * 13) >> 3) % 3;
        ctx.fillStyle = 'rgba(255,170,60,' + (0.05 + flick * 0.012) + ')';
        ctx.fillRect(lx - 20, 74, 44, 44);
        ctx.fillStyle = '#8a4a24'; ctx.fillRect(lx - 3, 96, 7, 3);
        ctx.fillStyle = '#ffd042'; ctx.fillRect(lx - 1, 91 - (flick === 1 ? 1 : 0), 3, 5);
        ctx.fillStyle = '#fff3c4'; ctx.fillRect(lx, 93, 1, 2);
      }
      return;
    }
    if (theme === 'lanka') {
      var g = ctx.createLinearGradient(0, 0, 0, 240);
      g.addColorStop(0, '#160a1e'); g.addColorStop(0.6, '#3a1024'); g.addColorStop(1, '#6b1a1e');
      ctx.fillStyle = g; ctx.fillRect(0, 0, 256, 240);
      // moon
      ctx.fillStyle = '#f6d9a0';
      ctx.beginPath(); ctx.arc(206 - camX * 0.02, 40, 14, 0, 7); ctx.fill();
      ctx.fillStyle = '#3a1024';
      ctx.beginPath(); ctx.arc(200 - camX * 0.02, 35, 12, 0, 7); ctx.fill();
      // palace silhouettes
      var off = (camX * 0.3) % 96;
      for (var i = -1; i < 4; i++) {
        var bx = i * 96 - off;
        ctx.fillStyle = '#22101f';
        ctx.fillRect(bx + 8, 150, 30, 60);
        ctx.fillRect(bx + 46, 130, 22, 80);
        ctx.fillRect(bx + 74, 160, 26, 50);
        ctx.beginPath();
        ctx.moveTo(bx + 46, 130); ctx.lineTo(bx + 57, 108); ctx.lineTo(bx + 68, 130); ctx.fill();
        ctx.fillStyle = '#ffb347';
        ctx.fillRect(bx + 14, 160, 4, 5); ctx.fillRect(bx + 26, 160, 4, 5);
        ctx.fillRect(bx + 52, 142, 4, 5); ctx.fillRect(bx + 82, 172, 4, 5);
      }
      // embers
      for (var e = 0; e < 18; e++) {
        var ex = (hash(e) * 256 + t * (0.2 + hash(e + 9) * 0.3)) % 256;
        var ey = 220 - ((t * (0.4 + hash(e) * 0.5) + hash(e + 3) * 200) % 220);
        ctx.fillStyle = e % 3 ? '#ff8a2b' : '#ffd042';
        ctx.fillRect(Math.floor(ex), Math.floor(ey), 2, 2);
      }
      return;
    }

    if (theme === 'mountain') {
      var g2 = ctx.createLinearGradient(0, 0, 0, 240);
      g2.addColorStop(0, '#2a2a5e'); g2.addColorStop(0.45, '#7a4a7a');
      g2.addColorStop(0.8, '#e07a4a'); g2.addColorStop(1, '#f0a860');
      ctx.fillStyle = g2; ctx.fillRect(0, 0, 256, 240);
      ctx.fillStyle = '#ffe9c0';
      ctx.beginPath(); ctx.arc(60 - camX * 0.02, 54, 11, 0, 7); ctx.fill();
      for (var s = 0; s < 22; s++) {
        ctx.fillStyle = '#ffffff' + (s % 2 ? '99' : 'cc');
        ctx.fillRect(Math.floor(hash(s) * 256), Math.floor(hash(s + 40) * 70), 1, 1);
      }
      var mo = (camX * 0.25) % 128;
      for (var m = -1; m < 4; m++) {
        var mx = m * 128 - mo;
        ctx.fillStyle = '#4a3a6e';
        ctx.beginPath();
        ctx.moveTo(mx - 10, 210); ctx.lineTo(mx + 40, 96); ctx.lineTo(mx + 90, 210); ctx.fill();
        ctx.beginPath();
        ctx.moveTo(mx + 60, 210); ctx.lineTo(mx + 100, 120); ctx.lineTo(mx + 140, 210); ctx.fill();
        ctx.fillStyle = '#d8d0e8';
        ctx.beginPath();
        ctx.moveTo(mx + 28, 122); ctx.lineTo(mx + 40, 96); ctx.lineTo(mx + 52, 122); ctx.fill();
      }
      ctx.fillStyle = '#33254f'; ctx.fillRect(0, 200, 256, 40);
      return;
    }

    // forest (default)
    var g3 = ctx.createLinearGradient(0, 0, 0, 240);
    g3.addColorStop(0, '#5aa8f0'); g3.addColorStop(0.7, '#9ed3f7'); g3.addColorStop(1, '#d8f0c8');
    ctx.fillStyle = g3; ctx.fillRect(0, 0, 256, 240);
    ctx.fillStyle = '#fff3b0';
    ctx.beginPath(); ctx.arc(212 - camX * 0.02, 36, 16, 0, 7); ctx.fill();
    ctx.fillStyle = '#fffbd8';
    ctx.beginPath(); ctx.arc(212 - camX * 0.02, 36, 11, 0, 7); ctx.fill();
    // clouds
    var co = (camX * 0.18) % 120;
    for (var c = -1; c < 4; c++) {
      var cx = c * 120 - co;
      cloud(ctx, cx + 10, 30 + Math.sin(t / 60 + c) * 2);
      cloud(ctx, cx + 74, 62 + Math.sin(t / 50 + c) * 2);
    }
    // tree line
    var to = (camX * 0.45) % 64;
    for (var tr = -1; tr < 6; tr++) {
      var tx = tr * 64 - to;
      tree(ctx, tx + 6, 150, 1);
      tree(ctx, tx + 38, 162, 0.8);
    }
    ctx.fillStyle = '#25611f'; ctx.fillRect(0, 206, 256, 34);
  }

  function cloud(ctx, x, y) {
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(x + 6, y, 20, 8);
    ctx.fillRect(x, y + 5, 34, 8);
    ctx.fillRect(x + 12, y - 4, 12, 6);
    ctx.fillStyle = '#dceaf7';
    ctx.fillRect(x, y + 11, 34, 2);
  }

  /* Muted on purpose: the tree line is scenery and must not compete with
     the tiles and characters drawn in front of it. */
  function tree(ctx, x, y, s) {
    var h = Math.round(46 * s), w = Math.round(34 * s);
    ctx.fillStyle = '#4a3018';
    ctx.fillRect(x + w / 2 - 3, y + h - 20, 6, 26);
    ctx.fillStyle = '#245c2c';
    ctx.fillRect(x + 4, y + 12, w - 8, h - 26);
    ctx.fillRect(x, y + 20, w, h - 36);
    ctx.fillStyle = '#2d7136';
    ctx.fillRect(x + 6, y + 6, w - 12, 16);
    ctx.fillRect(x + 10, y, w - 20, 10);
    ctx.fillStyle = '#3d8a44';
    ctx.fillRect(x + 12, y + 2, 8, 5);
  }

  return {
    C: C,
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
