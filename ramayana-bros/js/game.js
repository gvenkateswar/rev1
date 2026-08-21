/* ------------------------------------------------------------------
 * Ramayana Bros. -- engine, entities and game loop.
 *
 * A side-scrolling platformer in the shape of the 1985 classic, cast
 * with characters from the Ramayana. Rama runs east through Dandaka,
 * over Kishkindha and into Lanka; the sanjeevani herb makes him tall,
 * the Kodanda bow lets him shoot, and Hanuman's blessing makes him
 * briefly untouchable. Ravana holds the last gate.
 * ------------------------------------------------------------------ */

(function () {
  'use strict';

  var TILE = 16, VW = 256, VH = 240, ROWS = 15;

  /* physics (units are pixels per 1/60s frame) */
  /* Three gravities, as in the original: light while the jump button is
   * held, heavier once it is released, heaviest on the way down. A tap
   * clears about two tiles, a held jump about three and a half.        */
  var GRAV_HOLD = 0.22, GRAV_RISE = 0.34, GRAV_FALL = 0.5, MAX_FALL = 7.2;
  var ACC = 0.14, AIR_ACC = 0.10, FRICTION = 0.17;
  var MAX_WALK = 1.7, MAX_RUN = 2.8;
  var JUMP_V = -4.9, JUMP_RUN_V = -5.4;
  var ENEMY_SPEED = 0.45, SHELL_SPEED = 3.1;
  var STAR_TIME = 660, HURT_TIME = 100, SHELL_WAKE = 380;

  var canvas = document.getElementById('screen');
  var ctx = canvas.getContext('2d', { alpha: false });
  ctx.imageSmoothingEnabled = false;

  /* ============================ text ============================
   * A 5x7 bitmap face, so the HUD reads as part of the picture
   * rather than as browser text sitting on top of it.            */

  var GLYPHS = {
    '0': '.###.#...##..###.#.###..##...#.###.',
    '1': '..#...##....#....#....#....#...###.',
    '2': '.###.#...#....#...#...#...#...#####',
    '3': '####.....#....#.###.....#....#####.',
    '4': '...#...##..#.#.#..#.#####...#....#.',
    '5': '######....####.....#....##...#.###.',
    '6': '.###.#...##....####.#...##...#.###.',
    '7': '#####....#...#...#...#....#....#...',
    '8': '.###.#...##...#.###.#...##...#.###.',
    '9': '.###.#...##...#.####....##...#.###.',
    A: '.###.#...##...#######...##...##...#',
    B: '####.#...##...#####.#...##...#####.',
    C: '.###.#...##....#....#....#...#.###.',
    D: '####.#...##...##...##...##...#####.',
    E: '######....#....####.#....#....#####',
    F: '######....#....####.#....#....#....',
    G: '.###.#...##....#.####...##...#.###.',
    H: '#...##...##...#######...##...##...#',
    I: '#####..#....#....#....#....#..#####',
    J: '..###...#....#....#.#..#.#..#..##..',
    K: '#...##..#.#.#..##...#.#..#..#.#...#',
    L: '#....#....#....#....#....#....#####',
    M: '#...###.###.#.##.#.##...##...##...#',
    N: '#...###..##.#.##..###...##...##...#',
    O: '.###.#...##...##...##...##...#.###.',
    P: '####.#...##...#####.#....#....#....',
    Q: '.###.#...##...##...##.#.##..#..##.#',
    R: '####.#...##...#####.#.#..#..#.#...#',
    S: '.#####....#.....###.....#....#####.',
    T: '#####..#....#....#....#....#....#..',
    U: '#...##...##...##...##...##...#.###.',
    V: '#...##...##...##...##...#.#.#...#..',
    W: '#...##...##...##.#.##.#.###.###...#',
    X: '#...##...#.#.#...#...#.#.#...##...#',
    Y: '#...##...#.#.#...#....#....#....#..',
    Z: '#####....#...#...#...#...#....#####',
    '-': '...............#####...............',
    '.': '..........................##...##..',
    ',': '.....................##...##...#...',
    '!': '..#....#....#....#....#.........#..',
    '?': '.###.#...#....#...#...#.........#..',
    ':': '......##...##........##...##.......',
    "'": '..#....#...........................',
    '/': '....#....#...#...#...#...#....#....',
    '+': '.......#....#..#####..#....#.......',
    '*': '.....#.#.#.###.#####.###.#.#.#.....',
    ' ': '...................................'
  };
  /* Glyph strings are trusted to be 35 chars; pad/trim defensively. */
  (function () {
    for (var k in GLYPHS) {
      var s = GLYPHS[k];
      while (s.length < 35) s += '.';
      GLYPHS[k] = s.slice(0, 35);
    }
  })();

  function textWidth(s, sc) { return s.length * 6 * (sc || 1) - (sc || 1); }

  function text(str, x, y, color, sc, shadow) {
    sc = sc || 1;
    str = String(str).toUpperCase();
    for (var i = 0; i < str.length; i++) {
      var g = GLYPHS[str[i]];
      if (!g) continue;
      var gx = x + i * 6 * sc;
      for (var r = 0; r < 7; r++) {
        for (var c = 0; c < 5; c++) {
          if (g[r * 5 + c] !== '#') continue;
          if (shadow) {
            ctx.fillStyle = shadow;
            ctx.fillRect(gx + c * sc + sc, y + r * sc + sc, sc, sc);
          }
          ctx.fillStyle = color;
          ctx.fillRect(gx + c * sc, y + r * sc, sc, sc);
        }
      }
    }
  }

  function textC(str, y, color, sc, shadow) {
    text(str, Math.round((VW - textWidth(String(str), sc)) / 2), y, color, sc, shadow);
  }

  /* ============================ input ============================ */

  var keys = {}, pressed = {};
  var KEYMAP = {
    ArrowLeft: 'left', KeyA: 'left',
    ArrowRight: 'right', KeyD: 'right',
    ArrowDown: 'down', KeyS: 'down',
    ArrowUp: 'up', KeyW: 'up',
    KeyZ: 'jump', Space: 'jump', KeyK: 'jump',
    KeyX: 'run', ShiftLeft: 'run', ShiftRight: 'run', KeyJ: 'run',
    Enter: 'start', KeyP: 'pause', KeyM: 'mute', Escape: 'pause'
  };

  function setKey(name, down) {
    if (!name) return;
    if (down && !keys[name]) pressed[name] = true;
    keys[name] = down;
  }

  window.addEventListener('keydown', function (e) {
    var n = KEYMAP[e.code];
    if (n) { e.preventDefault(); setKey(n, true); Sound.unlock(); }
  });
  window.addEventListener('keyup', function (e) {
    var n = KEYMAP[e.code];
    if (n) { e.preventDefault(); setKey(n, false); }
  });
  window.addEventListener('blur', function () { for (var k in keys) keys[k] = false; });

  (function touchSetup() {
    var pad = document.getElementById('touch');
    if (!pad) return;
    if (!('ontouchstart' in window) && !navigator.maxTouchPoints) return;
    pad.classList.remove('hidden');
    var btns = pad.querySelectorAll('.tbtn');
    Array.prototype.forEach.call(btns, function (b) {
      var name = b.getAttribute('data-key');
      function on(e) { e.preventDefault(); b.classList.add('pressed'); setKey(name, true); setKey('start', true); Sound.unlock(); }
      function off(e) { e.preventDefault(); b.classList.remove('pressed'); setKey(name, false); }
      b.addEventListener('touchstart', on, { passive: false });
      b.addEventListener('touchend', off, { passive: false });
      b.addEventListener('touchcancel', off, { passive: false });
      b.addEventListener('mousedown', on);
      b.addEventListener('mouseup', off);
      b.addEventListener('mouseleave', off);
    });
  })();

  canvas.addEventListener('pointerdown', function () { Sound.unlock(); setKey('start', true); });
  canvas.addEventListener('pointerup', function () { setKey('start', false); });

  /* ============================ state ============================ */

  var G = {
    state: 'title', stateT: 0, t: 0,
    levelIndex: 0, level: null,
    tiles: [], w: 0, theme: 'forest',
    player: null, enemies: [], items: [], shots: [], fx: [], bumps: [],
    camX: 0, goal: null, sita: null, boss: null, bossDefeated: false,
    lives: 3, score: 0, coins: 0, time: 0, timeAcc: 0,
    shake: 0, hurry: false, best: 0, ending: 0
  };

  try { G.best = parseInt(localStorage.getItem('ramayana-bros-best') || '0', 10) || 0; } catch (e) { G.best = 0; }
  function saveBest() {
    if (G.score > G.best) {
      G.best = G.score;
      try { localStorage.setItem('ramayana-bros-best', String(G.best)); } catch (e) {}
    }
  }

  /* ============================ tiles ============================ */

  var SOLIDS = '#SBUP?MWTp';

  function tileChar(cx, cy) {
    if (cx < 0) return '#';                       // an invisible wall at the start
    if (cy < 0 || cy >= ROWS || cx >= G.w) return ' ';
    return G.tiles[cy][cx];
  }
  function isSolidChar(ch) {
    if (ch === 'G') return !G.bossDefeated;
    return ch !== ' ' && SOLIDS.indexOf(ch) >= 0;
  }
  function isSolid(cx, cy) { return isSolidChar(tileChar(cx, cy)); }
  function setTile(cx, cy, ch) {
    if (cy >= 0 && cy < ROWS && cx >= 0 && cx < G.w) G.tiles[cy][cx] = ch;
  }

  /* ============================ loading ============================ */

  function loadLevel(index) {
    var L = Levels.list[index];
    G.level = L;
    G.theme = L.theme;
    G.w = L.grid[0].length;
    G.tiles = L.grid.map(function (r) { return r.split(''); });
    G.enemies = []; G.items = []; G.shots = []; G.fx = []; G.bumps = [];
    G.camX = 0; G.goal = null; G.sita = null; G.boss = null; G.bossDefeated = false;
    G.time = L.time; G.timeAcc = 0; G.shake = 0; G.hurry = false;

    for (var y = 0; y < ROWS; y++) {
      for (var x = 0; x < G.w; x++) {
        var ch = G.tiles[y][x];
        if ('gdcR'.indexOf(ch) >= 0) { spawnEnemy(ch, x, y); setTile(x, y, ' '); }
        else if (ch === 'F') { G.goal = { x: x * TILE, y: (y + 1) * TILE }; setTile(x, y, ' '); }
        else if (ch === 'I') { G.sita = { x: x * TILE, y: (y + 1) * TILE - 22 }; setTile(x, y, ' '); }
      }
    }
    G.player = makePlayer(2 * TILE, (ROWS - 3) * TILE - 15, G.player);
    Sound.music.play(L.music);
  }

  /* ============================ player ============================ */

  function makePlayer(x, y, old) {
    return {
      x: x, y: y, w: 12, h: 15, vx: 0, vy: 0,
      dir: 1, onGround: false, jumping: false, frame: 0, animT: 0,
      big: old ? old.big : false, bow: old ? old.bow : false,
      star: 0, hurt: 0, morph: 0, morphTo: false,
      dead: false, deadT: 0, ducking: false, autoWalk: 0, hidden: false,
      coyote: 0, jumpBuf: 0
    };
  }

  function playerBox(p) {
    p.w = 12;
    p.h = p.big ? (p.ducking ? 17 : 27) : 15;
  }

  function grow(p) {
    if (p.big) return;
    p.morph = 34; p.morphTo = true;
    p.y -= 12; p.big = true; playerBox(p);
    Sound.fx.powerup();
  }
  function shrink(p) {
    p.morph = 34; p.morphTo = false;
    p.big = false; p.bow = false; p.ducking = false;
    playerBox(p);
    p.hurt = HURT_TIME;
    Sound.fx.shrink();
  }
  function hurtPlayer(p) {
    if (p.dead || p.hurt > 0 || p.star > 0 || p.morph > 0) return;
    if (p.big) shrink(p); else killPlayer(p);
  }
  function killPlayer(p) {
    if (p.dead) return;
    p.dead = true; p.deadT = 0; p.vy = -5.2; p.vx = 0;
    p.big = false; p.bow = false; p.star = 0;
    playerBox(p);
    Sound.music.stop();
    Sound.fx.die();
  }

  function updatePlayer(p) {
    if (p.dead) {
      p.deadT++;
      if (p.deadT > 24) { p.y += p.vy; p.vy = Math.min(p.vy + 0.32, MAX_FALL); }
      if (p.deadT > 190) loseLife();
      return;
    }

    if (p.morph > 0) { p.morph--; playerBox(p); return; }

    var left = keys.left && !p.autoWalk;
    var right = (keys.right || p.autoWalk > 0);
    var run = keys.run;

    p.ducking = p.big && p.onGround && keys.down && !p.autoWalk;
    playerBox(p);

    var max = run ? MAX_RUN : MAX_WALK;
    var acc = p.onGround ? ACC : AIR_ACC;

    if (p.ducking) {
      p.vx *= 0.88;
    } else if (left && !right) {
      p.vx -= acc; p.dir = -1;
      if (p.vx < -max) p.vx = Math.max(p.vx + FRICTION * 0.5, -max);
    } else if (right && !left) {
      p.vx += acc; p.dir = 1;
      if (p.vx > max) p.vx = Math.min(p.vx - FRICTION * 0.5, max);
    } else if (p.onGround) {
      if (Math.abs(p.vx) < FRICTION) p.vx = 0;
      else p.vx -= FRICTION * Math.sign(p.vx);
    }

    // jump, with a few frames of leniency at both ends: a press just
    // before landing still fires, and a press just after running off a
    // ledge still counts
    if (pressed.jump) p.jumpBuf = 8;
    if (p.jumpBuf > 0) p.jumpBuf--;
    if (p.jumpBuf > 0 && p.coyote > 0 && !p.ducking) {
      p.vy = Math.abs(p.vx) > MAX_WALK + 0.2 ? JUMP_RUN_V : JUMP_V;
      p.jumping = true; p.onGround = false;
      p.jumpBuf = 0; p.coyote = 0;
      if (p.big) Sound.fx.bigJump(); else Sound.fx.jump();
    }
    if (!keys.jump || p.vy > 0) p.jumping = false;
    if (p.vy < 0) p.vy += p.jumping ? GRAV_HOLD : GRAV_RISE;
    else p.vy += GRAV_FALL;
    if (p.vy > MAX_FALL) p.vy = MAX_FALL;

    // shoot
    if (pressed.run && p.bow && !p.autoWalk && countShots() < 2) {
      G.shots.push({
        x: p.x + (p.dir > 0 ? p.w : -8), y: p.y + (p.big ? 8 : 4),
        w: 8, h: 8, vx: 5 * p.dir, vy: 0.4, dir: p.dir, life: 200, kind: 'arrow'
      });
      Sound.fx.arrow();
    }

    var prevBottom = p.y + p.h;
    p.x += p.vx;
    resolveX(p);
    p.y += p.vy;
    resolveY(p, prevBottom, true);
    if (p.onGround) p.coyote = 6; else if (p.coyote > 0) p.coyote--;

    if (p.headHit) { bumpBlock(p, p.headHit.x, p.headHit.y); p.headHit = null; }

    // timers
    if (p.star > 0) { p.star--; if (p.star === 0 && !G.boss) Sound.music.play(G.level.music); }
    if (p.hurt > 0) p.hurt--;
    if (p.autoWalk > 0) p.autoWalk--;

    // animation
    if (!p.onGround) p.frame = 0;
    else if (Math.abs(p.vx) > 0.1) {
      p.animT += Math.abs(p.vx);
      if (p.animT > 6) { p.animT = 0; p.frame = (p.frame + 1) % 4; }
    } else { p.frame = 0; p.animT = 0; }

    collectTiles(p);

    if (p.y > VH + 32) killPlayer(p);
  }

  function countShots() {
    var n = 0;
    for (var i = 0; i < G.shots.length; i++) if (G.shots[i].kind === 'arrow') n++;
    return n;
  }

  /* Coins, water and the goal are all read straight off the tile map. */
  function collectTiles(p) {
    var x1 = Math.floor(p.x / TILE), x2 = Math.floor((p.x + p.w - 1) / TILE);
    var y1 = Math.floor(p.y / TILE), y2 = Math.floor((p.y + p.h - 1) / TILE);
    for (var y = y1; y <= y2; y++) {
      for (var x = x1; x <= x2; x++) {
        var ch = tileChar(x, y);
        if (ch === 'o') { setTile(x, y, ' '); takeCoin(x * TILE, y * TILE); }
        else if (ch === '~') { killPlayer(p); return; }
      }
    }
    if (G.goal && !p.autoWalk && p.x + p.w > G.goal.x + 6) startClear();
    if (G.sita && G.bossDefeated &&
        p.x + p.w > G.sita.x - 4 && p.x < G.sita.x + 18 &&
        p.y + p.h > G.sita.y - 4) startWin();
  }

  function takeCoin(x, y) {
    G.coins++; G.score += 200;
    if (G.coins % 100 === 0) { G.lives++; Sound.fx.oneUp(); popup(x, y, '1UP'); }
    else Sound.fx.coin();
    G.fx.push({ kind: 'spark', x: x + 4, y: y, life: 16 });
  }

  /* Hitting a block from underneath. */
  function bumpBlock(p, cx, cy) {
    var ch = tileChar(cx, cy);
    if (ch === '?' || ch === 'M' || ch === 'W' || ch === 'T') {
      setTile(cx, cy, 'U');
      G.bumps.push({ x: cx, y: cy, t: 0 });
      if (ch === '?') {
        G.fx.push({ kind: 'coin', x: cx * TILE, y: cy * TILE, vy: -3.4, life: 46 });
        takeCoin(cx * TILE, cy * TILE - 8);
      } else {
        var type = ch === 'M' ? (p.big ? 'bless' : 'herb') : (ch === 'W' ? 'bow' : 'bless');
        spawnItem(type, cx * TILE, cy * TILE);
        Sound.fx.sprout();
      }
    } else if (ch === 'B') {
      if (p.big) {
        setTile(cx, cy, ' ');
        G.score += 50;
        Sound.fx.brick();
        for (var i = 0; i < 4; i++) {
          G.fx.push({
            kind: 'chunk', x: cx * TILE + (i % 2) * 8, y: cy * TILE + (i > 1 ? 8 : 0),
            vx: (i % 2 ? 1.3 : -1.3), vy: (i > 1 ? -2.2 : -3.4), rot: i, life: 100
          });
        }
      } else {
        G.bumps.push({ x: cx, y: cy, t: 0 });
        Sound.fx.bump();
      }
    } else if (isSolidChar(ch)) {
      Sound.fx.bump();
    }
    // anything standing on the block gets flipped
    for (var e = 0; e < G.enemies.length; e++) {
      var en = G.enemies[e];
      if (en.dying || en.type === 'ravana') continue;
      if (en.x + en.w > cx * TILE && en.x < (cx + 1) * TILE &&
          Math.abs((en.y + en.h) - cy * TILE) < 6) flipEnemy(en, en.x < p.x ? -1 : 1);
    }
  }

  /* ============================ collision ============================ */

  function resolveX(e) {
    var y1 = Math.floor(e.y / TILE), y2 = Math.floor((e.y + e.h - 1) / TILE);
    var cx, y;
    if (e.vx > 0) {
      cx = Math.floor((e.x + e.w - 1) / TILE);
      for (y = y1; y <= y2; y++) {
        if (isSolid(cx, y)) { e.x = cx * TILE - e.w; e.vx = 0; e.bump = 1; return; }
      }
    } else if (e.vx < 0) {
      cx = Math.floor(e.x / TILE);
      for (y = y1; y <= y2; y++) {
        if (isSolid(cx, y)) { e.x = (cx + 1) * TILE; e.vx = 0; e.bump = -1; return; }
      }
    }
  }

  function resolveY(e, prevBottom, wantsHead) {
    var x1 = Math.floor(e.x / TILE), x2 = Math.floor((e.x + e.w - 1) / TILE);
    var cy, x;
    e.onGround = false;
    if (e.vy >= 0) {
      // probe the row the feet rest on, so resting flush on a tile still
      // reads as "on the ground" instead of flickering every frame
      cy = Math.floor((e.y + e.h) / TILE);
      for (x = x1; x <= x2; x++) {
        var ch = tileChar(x, cy);
        var oneWay = (ch === '=') && prevBottom <= cy * TILE + 3;
        if (isSolidChar(ch) || oneWay) {
          e.y = cy * TILE - e.h; e.vy = 0; e.onGround = true; return;
        }
      }
    } else {
      cy = Math.floor(e.y / TILE);
      var best = -1, bestD = 99, cxc = (e.x + e.w / 2) / TILE;
      for (x = x1; x <= x2; x++) {
        if (isSolid(x, cy)) {
          var d = Math.abs(x + 0.5 - cxc);
          if (d < bestD) { bestD = d; best = x; }
        }
      }
      if (best >= 0) {
        e.y = (cy + 1) * TILE; e.vy = 0;
        if (wantsHead) e.headHit = { x: best, y: cy };
      }
    }
  }

  function overlaps(a, b) {
    return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
  }

  /* ============================ enemies ============================ */

  function spawnEnemy(ch, cx, cy) {
    var e;
    if (ch === 'g') {
      e = { type: 'rakshasa', w: 14, h: 14, sw: 16, sh: 16, ox: -1, oy: -2,
            vx: -ENEMY_SPEED, vy: 0, gravity: true };
    } else if (ch === 'd') {
      e = { type: 'deer', w: 13, h: 20, sw: 16, sh: 22, ox: -2, oy: -2,
            vx: -ENEMY_SPEED, vy: 0, gravity: true, shell: 0, wake: 0 };
    } else if (ch === 'c') {
      // a deliberately forgiving hitbox -- the wings are decoration
      e = { type: 'crow', w: 12, h: 8, sw: 16, sh: 14, ox: -2, oy: -3,
            vx: -0.75, vy: 0, gravity: false };
    } else {
      e = { type: 'ravana', w: 28, h: 42, sw: 32, sh: 44, ox: -2, oy: -2,
            vx: -0.32, vy: 0, gravity: true, hp: 6, flash: 0, fireT: 90, jumpT: 200 };
    }
    e.x = cx * TILE + (TILE - e.w) / 2;
    e.y = (cy + 1) * TILE - e.h;
    e.baseY = e.y;
    e.homeX = e.x;
    e.dir = -1; e.frame = 0; e.animT = 0;
    e.dying = 0; e.squash = 0; e.active = false;
    G.enemies.push(e);
    if (e.type === 'ravana') G.boss = e;
    return e;
  }

  function flipEnemy(e, dir) {
    if (e.type === 'ravana') return;
    e.dying = 1; e.vy = -3.6; e.vx = 0.8 * dir; e.flip = true;
    G.score += 200;
    popup(e.x, e.y, '200');
    Sound.fx.kick();
  }

  function updateEnemy(e) {
    if (!e.active) {
      if (e.x < G.camX + VW + 24) e.active = true;
      else return;
    }
    if (e.dying) {
      e.vy += 0.3; e.y += e.vy; e.x += e.vx;
      e.dying++;
      if (e.y > VH + 40 || e.dying > 200) e.remove = true;
      return;
    }
    if (e.squash > 0) {
      e.squash--;
      if (e.squash === 0) e.remove = true;
      return;
    }

    if (e.type === 'ravana') { updateRavana(e); return; }

    if (e.type === 'crow') {
      // Kakasura circles the perch he was placed on rather than drifting
      // off across the level, so a crow stays the obstacle it was drawn as
      e.x += e.vx;
      if (e.x < e.homeX - 44 || e.x > e.homeX + 44) { e.vx = -e.vx; e.x += e.vx * 2; }
      var cx = Math.floor((e.vx > 0 ? e.x + e.w : e.x) / TILE);
      var cyy = Math.floor((e.y + e.h / 2) / TILE);
      if (isSolid(cx, cyy)) { e.vx = -e.vx; e.x += e.vx * 2; }
      e.dir = e.vx > 0 ? 1 : -1;
      e.frame = Math.floor(G.t / 7) % 2;
      e.y = e.baseY + Math.sin((G.t + e.homeX) / 26) * 12;
      return;
    }

    if (e.type === 'deer' && e.shell) {
      if (e.shellMoving) {
        e.vx = SHELL_SPEED * e.shellDir;
      } else {
        e.vx = 0;
        e.wake--;
        if (e.wake <= 0) {                     // Maricha shakes himself awake
          e.shell = 0; e.h = 20; e.sh = 22; e.oy = -2; e.y -= 7;
          e.vx = -ENEMY_SPEED; e.dir = -1;
        }
      }
    }

    e.vy += 0.35;
    if (e.vy > MAX_FALL) e.vy = MAX_FALL;
    var prevBottom = e.y + e.h;
    e.bump = 0;
    e.x += e.vx;
    resolveX(e);
    if (e.bump) {
      if (e.shellMoving) { e.shellDir = -e.shellDir; Sound.fx.bump(); }
      else { e.vx = Math.abs(e.vx) * (e.bump > 0 ? -1 : 1); }
    }
    e.y += e.vy;
    resolveY(e, prevBottom, false);
    e.dir = e.vx === 0 ? e.dir : (e.vx > 0 ? 1 : -1);

    e.animT += Math.abs(e.vx) + 0.35;
    if (e.animT > 8) { e.animT = 0; e.frame = (e.frame + 1) % 2; }

    // drowning / falling out of the world
    var mid = Math.floor((e.x + e.w / 2) / TILE);
    var foot = Math.floor((e.y + e.h - 2) / TILE);
    if (tileChar(mid, foot) === '~') { e.dying = 1; e.vy = -1; }
    if (e.y > VH + 40) e.remove = true;

    // a spinning shell scatters whatever it meets
    if (e.shellMoving) {
      for (var i = 0; i < G.enemies.length; i++) {
        var o = G.enemies[i];
        if (o === e || o.dying || o.squash || o.type === 'ravana') continue;
        if (overlaps(e, o)) { flipEnemy(o, e.shellDir); }
      }
      if (G.boss && !G.boss.dying && overlaps(e, G.boss)) {
        damageBoss(G.boss, e.shellDir); e.shellDir = -e.shellDir;
      }
    }
  }

  function stompEnemy(e, p) {
    p.vy = keys.jump ? -4.6 : -3.4;
    if (e.type === 'rakshasa') {
      e.squash = 30; e.h = 8; e.y += 6; e.oy = 0;
      G.score += 100; popup(e.x, e.y, '100');
      Sound.fx.stomp();
    } else if (e.type === 'crow') {
      flipEnemy(e, p.dir);
      Sound.fx.stomp();
    } else if (e.type === 'deer') {
      if (!e.shell) {
        e.shell = 1; e.shellMoving = false; e.wake = SHELL_WAKE;
        e.h = 13; e.sh = 14; e.oy = -1; e.y += 7;
        e.vx = 0;
        G.score += 100; popup(e.x, e.y, '100');
        Sound.fx.stomp();
      } else if (e.shellMoving) {
        e.shellMoving = false; e.wake = SHELL_WAKE; e.vx = 0;
        Sound.fx.stomp();
      } else {
        kickShell(e, p.x + p.w / 2 < e.x + e.w / 2 ? 1 : -1);
      }
    }
  }

  function kickShell(e, dir) {
    e.shellMoving = true; e.shellDir = dir; e.wake = SHELL_WAKE;
    G.score += 100; popup(e.x, e.y, '100');
    Sound.fx.kick();
  }

  function playerVsEnemies(p) {
    if (p.dead || p.morph > 0) return;
    for (var i = 0; i < G.enemies.length; i++) {
      var e = G.enemies[i];
      if (e.dying || e.squash || !e.active || e.remove) continue;
      if (!overlaps(p, e)) continue;

      if (p.star > 0) {
        if (e.type === 'ravana') damageBoss(e, p.dir);
        else flipEnemy(e, p.vx >= 0 ? 1 : -1);
        continue;
      }

      var stomping = p.vy > 0 && (p.y + p.h) - e.y < 12;

      if (e.type === 'ravana') {
        if (stomping) { damageBoss(e, p.dir); p.vy = -4.6; }
        else hurtPlayer(p);
        continue;
      }

      if (stomping) { stompEnemy(e, p); continue; }

      if (e.type === 'deer' && e.shell && !e.shellMoving) {
        kickShell(e, p.x + p.w / 2 < e.x + e.w / 2 ? 1 : -1);
        continue;
      }
      hurtPlayer(p);
    }
  }

  /* ============================ Ravana ============================ */

  function updateRavana(e) {
    var p = G.player;
    e.flash = Math.max(0, e.flash - 1);
    e.iframes = Math.max(0, (e.iframes || 0) - 1);

    var toward = (p.x + p.w / 2) < (e.x + e.w / 2) ? -1 : 1;
    e.dir = toward;
    e.vx = 0.42 * toward;

    e.jumpT--;
    if (e.jumpT <= 0 && e.onGround) {
      e.vy = -5.6; e.jumpT = 150 + Math.floor(Math.random() * 120);
      Sound.fx.bossRoar();
    }
    e.fireT--;
    if (e.fireT <= 0) {
      e.fireT = 95 + Math.floor(Math.random() * 70);
      G.shots.push({
        kind: 'fire', x: e.x + (toward > 0 ? e.w : -10), y: e.y + 14,
        w: 10, h: 10, vx: 2.6 * toward, vy: -0.6, life: 320
      });
      Sound.fx.fire();
    }

    e.vy += 0.4;
    if (e.vy > MAX_FALL) e.vy = MAX_FALL;
    var prevBottom = e.y + e.h;
    e.bump = 0;
    e.x += e.vx; resolveX(e);
    e.y += e.vy; resolveY(e, prevBottom, false);

    e.animT += 1;
    if (e.animT > 10) { e.animT = 0; e.frame = (e.frame + 1) % 2; }
  }

  function damageBoss(e, dir) {
    if (e.iframes > 0 || e.dying) return;
    e.hp--;
    e.flash = 26; e.iframes = 34;
    G.shake = 10;
    if (e.hp <= 0) {
      e.dying = 1; e.vy = -3; e.vx = 0.6 * dir;
      G.bossDefeated = true;
      G.score += 5000;
      popup(e.x, e.y, '5000');
      Sound.fx.bossHit();
      Sound.music.play(G.level.music);
      for (var i = 0; i < 26; i++) {
        G.fx.push({
          kind: 'burst', x: e.x + 14 + (Math.random() - 0.5) * 26,
          y: e.y + 20 + (Math.random() - 0.5) * 36,
          vx: (Math.random() - 0.5) * 4, vy: -Math.random() * 4 - 0.5,
          life: 40 + Math.random() * 30,
          color: ['#ffd042', '#ff8a2b', '#e0403a', '#ffffff'][i % 4]
        });
      }
    } else {
      G.score += 500;
      popup(e.x, e.y, '500');
      Sound.fx.bossHit();
    }
  }

  /* ============================ items & shots ============================ */

  /* Items rise out of the block they were hidden in, then make their own
   * way down to Rama: the herb walks, the blessing bounces, and the bow
   * slides. Nothing waits on top of a block where it can't be reached. */
  function spawnItem(type, x, y) {
    G.items.push({
      type: type, x: x, y: y, w: 14, h: 14,
      vx: type === 'herb' ? 0.9 : (type === 'bless' ? 1.3 : 0.7),
      vy: 0, rise: 16, born: 0
    });
  }

  function updateItem(it) {
    it.born++;
    if (it.rise > 0) { it.y -= 1; it.rise--; return; }
    it.vy += it.type === 'bless' ? 0.32 : 0.34;
    if (it.vy > MAX_FALL) it.vy = MAX_FALL;
    var prevBottom = it.y + it.h;
    it.bump = 0;
    it.x += it.vx; resolveX(it);
    if (it.bump) it.vx = -it.vx;
    it.y += it.vy; resolveY(it, prevBottom, false);
    if (it.onGround && it.type === 'bless') it.vy = -3.6;
    if (it.y > VH + 20) it.remove = true;
    var mid = Math.floor((it.x + it.w / 2) / TILE);
    var foot = Math.floor((it.y + it.h - 2) / TILE);
    if (tileChar(mid, foot) === '~') it.remove = true;
  }

  function playerVsItems(p) {
    for (var i = 0; i < G.items.length; i++) {
      var it = G.items[i];
      if (it.rise > 0 || it.remove) continue;
      if (!overlaps(p, it)) continue;
      it.remove = true;
      if (it.type === 'herb') { G.score += 1000; popup(it.x, it.y, '1000'); grow(p); }
      else if (it.type === 'bow') {
        G.score += 1000; popup(it.x, it.y, '1000');
        if (!p.big) grow(p); else Sound.fx.powerup();
        p.bow = true;
      } else {
        G.score += 1000; popup(it.x, it.y, '1000');
        p.star = STAR_TIME;
        Sound.fx.powerup();
        Sound.music.play('boss');
      }
    }
  }

  function updateShot(s) {
    s.life--;
    if (s.life <= 0) { s.remove = true; return; }
    s.vy += s.kind === 'arrow' ? 0.13 : 0.11;
    if (s.vy > 5) s.vy = 5;
    var prevBottom = s.y + s.h;
    s.bump = 0;
    s.x += s.vx; resolveX(s);
    if (s.bump) {
      if (s.kind === 'arrow') { s.remove = true; puff(s.x, s.y); }
      else s.vx = -s.vx;
    }
    s.y += s.vy; resolveY(s, prevBottom, false);
    if (s.onGround) s.vy = s.kind === 'arrow' ? -2.1 : -2.6;
    if (s.x < G.camX - 32 || s.x > G.camX + VW + 32 || s.y > VH + 20) s.remove = true;

    if (s.kind === 'arrow') {
      for (var i = 0; i < G.enemies.length; i++) {
        var e = G.enemies[i];
        if (e.dying || e.squash || !e.active || e.remove) continue;
        if (!overlaps(s, e)) continue;
        s.remove = true;
        if (e.type === 'ravana') damageBoss(e, s.vx > 0 ? 1 : -1);
        else flipEnemy(e, s.vx > 0 ? 1 : -1);
        puff(s.x, s.y);
        break;
      }
    } else {
      if (overlaps(s, G.player) && !G.player.dead) { hurtPlayer(G.player); s.remove = true; }
    }
  }

  /* ============================ effects ============================ */

  function popup(x, y, str) { G.fx.push({ kind: 'text', x: x, y: y, str: str, life: 46 }); }
  function puff(x, y) {
    for (var i = 0; i < 4; i++) {
      G.fx.push({ kind: 'burst', x: x + 4, y: y + 4, vx: (Math.random() - 0.5) * 2.4,
                  vy: (Math.random() - 0.5) * 2.4, life: 16, color: '#ffe9b0' });
    }
  }

  function updateFx(f) {
    f.life--;
    if (f.life <= 0) { f.remove = true; return; }
    if (f.kind === 'text') { f.y -= 0.55; }
    else if (f.kind === 'chunk') { f.vy += 0.3; f.x += f.vx; f.y += f.vy; }
    else if (f.kind === 'coin') { f.vy += 0.28; f.y += f.vy; }
    else if (f.kind === 'burst') { f.vy += 0.14; f.x += f.vx; f.y += f.vy; }
  }

  function prune(list) {
    for (var i = list.length - 1; i >= 0; i--) if (list[i].remove) list.splice(i, 1);
  }

  /* ============================ flow ============================ */

  function startGame() {
    G.lives = 3; G.score = 0; G.coins = 0; G.levelIndex = 0;
    G.player = null;
    loadLevel(0);
    G.state = 'intro'; G.stateT = 0;
  }

  function loseLife() {
    G.lives--;
    saveBest();
    if (G.lives < 0) {
      G.state = 'gameover'; G.stateT = 0;
      Sound.music.stop();
      return;
    }
    var keep = G.player;
    keep.big = false; keep.bow = false;
    loadLevel(G.levelIndex);
    G.state = 'intro'; G.stateT = 0;
  }

  function startClear() {
    if (G.state !== 'play') return;
    G.state = 'clear'; G.stateT = 0;
    G.player.autoWalk = 240;
    G.player.star = 0;
    G.score += 1000;
    Sound.music.stop();
    Sound.fx.flag();
  }

  function startWin() {
    G.state = 'win'; G.stateT = 0; G.ending = 0;
    G.score += 10000;
    saveBest();
    Sound.music.stop();
    Sound.fx.flag();
  }

  function nextLevel() {
    G.levelIndex++;
    if (G.levelIndex >= Levels.list.length) { startWin(); return; }
    loadLevel(G.levelIndex);
    G.state = 'intro'; G.stateT = 0;
  }

  /* ============================ update ============================ */

  function updatePlay() {
    var p = G.player;
    updatePlayer(p);

    if (!p.dead && p.morph === 0) {
      playerVsEnemies(p);
      playerVsItems(p);
    }

    var i;
    for (i = 0; i < G.enemies.length; i++) updateEnemy(G.enemies[i]);
    for (i = 0; i < G.items.length; i++) updateItem(G.items[i]);
    for (i = 0; i < G.shots.length; i++) updateShot(G.shots[i]);
    for (i = 0; i < G.fx.length; i++) updateFx(G.fx[i]);
    for (i = 0; i < G.bumps.length; i++) { G.bumps[i].t++; if (G.bumps[i].t > 10) G.bumps[i].remove = true; }
    prune(G.enemies); prune(G.items); prune(G.shots); prune(G.fx); prune(G.bumps);

    // boss music once the court is entered
    if (G.boss && !G.bossDefeated && !G.boss.dying && p.star === 0 &&
        p.x > G.boss.x - 200) Sound.music.play('boss');

    // camera: follows, and like the original never scrolls back
    var target = p.x + p.w / 2 - 110;
    if (target > G.camX) G.camX = target;
    G.camX = Math.max(0, Math.min(G.camX, G.w * TILE - VW));

    if (G.shake > 0) G.shake--;

    // clock
    if (!p.dead) {
      G.timeAcc++;
      if (G.timeAcc >= 25) {
        G.timeAcc = 0;
        G.time--;
        if (G.time === 100) { G.hurry = true; Sound.fx.pause(); }
        if (G.time <= 0) { G.time = 0; killPlayer(p); }
      }
    }
  }

  function updateClear() {
    G.stateT++;
    var p = G.player;
    if (G.stateT < 120) {
      p.autoWalk = 4;
      updatePlayer(p);
      var target = p.x + p.w / 2 - 110;
      if (target > G.camX) G.camX = target;
      G.camX = Math.max(0, Math.min(G.camX, G.w * TILE - VW));
      if (G.goal && p.x > G.goal.x + 12) p.hidden = true;
    } else if (G.time > 0 && G.stateT % 2 === 0) {
      var step = Math.min(G.time, 5);
      G.time -= step; G.score += step * 50;
      Sound.fx.coin();
    }
    for (var i = 0; i < G.fx.length; i++) updateFx(G.fx[i]);
    prune(G.fx);
    if (G.stateT > 200 && G.time <= 0) nextLevel();
  }

  function update() {
    G.t++;

    if (pressed.mute) { Sound.toggleMute(); }

    switch (G.state) {
      case 'title':
        G.stateT++;
        if (pressed.start || pressed.jump) { Sound.unlock(); startGame(); }
        break;
      case 'intro':
        G.stateT++;
        if (G.stateT > 130 || pressed.start || pressed.jump) { G.state = 'play'; G.stateT = 0; }
        break;
      case 'play':
        if (pressed.pause) { G.state = 'paused'; Sound.fx.pause(); break; }
        updatePlay();
        break;
      case 'paused':
        if (pressed.pause || pressed.start) { G.state = 'play'; Sound.fx.pause(); }
        break;
      case 'clear':
        updateClear();
        break;
      case 'gameover':
        G.stateT++;
        if (G.stateT > 90 && (pressed.start || pressed.jump)) { G.state = 'title'; G.stateT = 0; }
        break;
      case 'win':
        G.stateT++;
        if (G.stateT > 150 && (pressed.start || pressed.jump)) { G.state = 'title'; G.stateT = 0; }
        break;
    }

    for (var k in pressed) pressed[k] = false;
    Sound.music.update();
  }

  /* ============================ rendering ============================ */

  function drawTiles() {
    var x0 = Math.floor(G.camX / TILE), x1 = x0 + 17;
    for (var y = 0; y < ROWS; y++) {
      for (var x = x0; x <= x1; x++) {
        var ch = tileChar(x, y);
        if (ch === ' ' || ch === 'o') continue;
        var px = x * TILE - Math.round(G.camX), py = y * TILE;
        if (ch === 'G') {
          if (G.bossDefeated) continue;
          var glow = (Math.sin(G.t / 9 + y) + 1) * 0.5;
          ctx.fillStyle = 'rgba(180,60,220,' + (0.45 + glow * 0.35) + ')';
          ctx.fillRect(px + 2, py, 12, 16);
          ctx.fillStyle = 'rgba(255,210,255,' + (0.4 + glow * 0.5) + ')';
          ctx.fillRect(px + 5, py + ((G.t * 2 + y * 5) % 16), 6, 3);
          continue;
        }
        var bump = 0;
        for (var b = 0; b < G.bumps.length; b++) {
          if (G.bumps[b].x === x && G.bumps[b].y === y) {
            bump = -Math.round(Math.sin(G.bumps[b].t / 10 * Math.PI) * 7);
          }
        }
        var above = tileChar(x, y - 1);
        Sprites.tile(ctx, px, py + bump, ch, G.theme, G.t, above !== ch && !isSolidChar(above));
      }
    }
    // loose coins
    for (var yy = 0; yy < ROWS; yy++) {
      for (var xx = x0; xx <= x1; xx++) {
        if (tileChar(xx, yy) === 'o') {
          Sprites.coin(ctx, xx * TILE - Math.round(G.camX), yy * TILE, Math.floor(G.t / 6) + xx);
        }
      }
    }
  }

  function drawPlayer(p) {
    if (p.hidden) return;
    if (p.hurt > 0 && Math.floor(p.hurt / 3) % 2) return;
    var state = 'stand';
    if (p.dead) state = 'dead';
    else if (p.morph > 0) state = 'stand';
    else if (!p.onGround) state = 'jump';
    else if (p.ducking) state = 'duck';
    else if (Math.abs(p.vx) > 0.1) state = 'walk';

    var big = p.big;
    if (p.morph > 0) big = (Math.floor(p.morph / 4) % 2) ? p.morphTo : !p.morphTo;

    var sz = Sprites.heroSize({ big: big, state: state });
    var px = Math.round(p.x - Math.round(G.camX) - (16 - p.w) / 2);
    var py = Math.round(p.y + p.h - sz.h);
    Sprites.hero(ctx, px, py, {
      big: big, bow: p.bow, state: state, frame: p.frame, dir: p.dir,
      star: p.star > 0, t: G.t
    });
    if (p.star > 0 && G.t % 3 === 0) {
      G.fx.push({ kind: 'burst', x: p.x + Math.random() * 12, y: p.y + Math.random() * sz.h,
                  vx: (Math.random() - 0.5), vy: -0.5, life: 14, color: '#ffd042' });
    }
  }

  function drawEnemies() {
    for (var i = 0; i < G.enemies.length; i++) {
      var e = G.enemies[i];
      if (!e.active) continue;
      var x = Math.round(e.x + e.ox - Math.round(G.camX));
      var y = Math.round(e.y + e.oy);
      if (x < -48 || x > VW + 48) continue;
      ctx.save();
      if (e.dying && e.flip) { ctx.translate(x + 8, y + 8); ctx.scale(1, -1); ctx.translate(-x - 8, -y - 8); }
      if (e.type === 'rakshasa') Sprites.rakshasa(ctx, x, y, e.frame, e.dir, e.squash > 0);
      else if (e.type === 'crow') Sprites.crow(ctx, x, y, e.frame, e.dir);
      else if (e.type === 'deer') {
        if (e.shell) Sprites.shell(ctx, x, y, Math.floor(G.t / 4), e.shellMoving || e.wake < 90);
        else Sprites.deer(ctx, x, y, e.frame, e.dir);
      } else if (e.type === 'ravana') {
        Sprites.ravana(ctx, x, y, { frame: e.frame, dir: e.dir, flash: e.flash > 0 && (G.t % 4 < 2) });
      }
      ctx.restore();
    }
  }

  function drawItems() {
    for (var i = 0; i < G.items.length; i++) {
      var it = G.items[i];
      var x = Math.round(it.x - 1 - Math.round(G.camX)), y = Math.round(it.y - 2);
      if (it.rise > 0) ctx.save(), ctx.beginPath(),
        ctx.rect(x - 8, y - 16 + it.rise, 32, 32 - it.rise), ctx.clip();
      if (it.type === 'herb') Sprites.sanjeevani(ctx, x, y);
      else if (it.type === 'bow') Sprites.bow(ctx, x, y, G.t);
      else Sprites.blessing(ctx, x, y, G.t);
      if (it.rise > 0) ctx.restore();
    }
  }

  function drawShots() {
    for (var i = 0; i < G.shots.length; i++) {
      var s = G.shots[i];
      var x = Math.round(s.x - Math.round(G.camX)), y = Math.round(s.y);
      if (s.kind === 'arrow') Sprites.arrow(ctx, x, y, s.vx > 0 ? 1 : -1);
      else Sprites.fireball(ctx, x, y, G.t);
    }
  }

  function drawFx() {
    for (var i = 0; i < G.fx.length; i++) {
      var f = G.fx[i];
      var x = Math.round(f.x - Math.round(G.camX)), y = Math.round(f.y);
      if (f.kind === 'text') text(f.str, x, y, '#ffffff', 1, '#00000088');
      else if (f.kind === 'chunk') Sprites.chunk(ctx, x, y, G.theme, f.rot);
      else if (f.kind === 'coin') Sprites.coin(ctx, x, y, Math.floor(G.t / 3));
      else if (f.kind === 'spark') {
        ctx.fillStyle = '#fff6c9';
        var r = 16 - f.life;
        ctx.fillRect(x - r, y + 6, 2, 2); ctx.fillRect(x + r, y + 6, 2, 2);
        ctx.fillRect(x, y - r + 6, 2, 2);
      } else if (f.kind === 'burst') {
        ctx.fillStyle = f.color || '#ffd042';
        ctx.fillRect(x, y, 2, 2);
      }
    }
  }

  function drawHud() {
    var sh = '#00000099';
    text('RAMA', 8, 8, '#ffffff', 1, sh);
    text(pad6(G.score), 8, 17, '#ffffff', 1, sh);

    Sprites.coin(ctx, 62, 1, 0);
    text(pad2(G.coins), 80, 8, '#ffffff', 1, sh);
    for (var i = 0; i < Math.min(G.lives, 4); i++) {
      var lx = 63 + i * 9;
      ctx.fillStyle = '#00000099';
      ctx.fillRect(lx + 1, 20, 7, 6);
      ctx.fillStyle = '#ffd042';
      ctx.fillRect(lx, 22, 7, 3);
      ctx.fillRect(lx, 19, 1, 3); ctx.fillRect(lx + 3, 18, 1, 4); ctx.fillRect(lx + 6, 19, 1, 3);
      ctx.fillStyle = '#c8901a'; ctx.fillRect(lx, 24, 7, 1);
    }
    if (G.lives > 4) text('+' + (G.lives - 4), 63 + 4 * 9, 19, '#ffd042', 1, sh);

    text('KANDA', 140, 8, '#ffffff', 1, sh);
    text(G.level ? G.level.id : '1-1', 146, 17, '#ffffff', 1, sh);

    text('TIME', 204, 8, '#ffffff', 1, sh);
    text(pad3(G.time), 207, 17, G.hurry && G.t % 20 < 10 ? '#ff6a3d' : '#ffffff', 1, sh);
  }

  function pad2(n) { n = String(n); return n.length >= 2 ? n : '0'.repeat(2 - n.length) + n; }
  function pad3(n) { n = String(Math.max(0, n)); return n.length >= 3 ? n : '0'.repeat(3 - n.length) + n; }
  function pad6(n) { n = String(n); return n.length >= 6 ? n : '0'.repeat(6 - n.length) + n; }

  function drawScene() {
    Sprites.background(ctx, G.theme, G.camX, G.t);
    ctx.save();
    if (G.shake > 0) ctx.translate((Math.random() - 0.5) * 3, (Math.random() - 0.5) * 3);
    drawTiles();
    if (G.goal) Sprites.shrine(ctx, G.goal.x - Math.round(G.camX) - 8, G.goal.y, G.t, G.state === 'clear');
    if (G.sita) Sprites.sita(ctx, Math.round(G.sita.x - Math.round(G.camX)), Math.round(G.sita.y), G.t);
    drawItems();
    drawEnemies();
    drawShots();
    if (G.player) drawPlayer(G.player);
    drawFx();
    ctx.restore();
    drawHud();
  }

  /* ---- full-screen cards ---- */

  function dim(a) { ctx.fillStyle = 'rgba(0,0,0,' + a + ')'; ctx.fillRect(0, 0, VW, VH); }

  function drawTitle() {
    Sprites.background(ctx, 'forest', G.t * 0.4, G.t);
    dim(0.25);
    ctx.fillStyle = 'rgba(20,10,30,0.62)';
    ctx.fillRect(14, 30, VW - 28, 92);
    ctx.fillStyle = '#ffd042'; ctx.fillRect(14, 30, VW - 28, 2);
    ctx.fillRect(14, 120, VW - 28, 2);

    textC('RAMAYANA', 44, '#ffd042', 3, '#5a2a00');
    textC('BROS.', 74, '#ffffff', 3, '#5a2a00');
    textC('THE LANKA RUN', 104, '#8fc4f5', 1, '#001028');

    Sprites.hero(ctx, 40, 150, { big: true, bow: false, state: 'walk',
      frame: Math.floor(G.t / 8) % 4, dir: 1, star: false, t: G.t });
    Sprites.rakshasa(ctx, 110, 162, Math.floor(G.t / 12) % 2, -1, false);
    Sprites.deer(ctx, 150, 156, Math.floor(G.t / 12) % 2, -1);
    Sprites.blessing(ctx, 196, 162, G.t);

    if (Math.floor(G.t / 26) % 2) textC('PRESS ENTER OR TAP', 196, '#ffffff', 1, '#000000aa');
    textC('TOP ' + pad6(G.best), 212, '#ffd042', 1, '#000000aa');
    textC('ARROWS MOVE   Z JUMP   X RUN-SHOOT', 226, '#cfd6e0', 1, '#000000aa');
  }

  function drawIntro() {
    ctx.fillStyle = '#000000'; ctx.fillRect(0, 0, VW, VH);
    var L = G.level;
    textC('KANDA ' + L.id, 60, '#ffffff', 2, '#333333');
    textC(L.name, 92, '#ffd042', 1);
    textC(L.blurb, 108, '#8fc4f5', 1);
    Sprites.hero(ctx, 104, 140, { big: G.player.big, bow: G.player.bow, state: 'stand',
      frame: 0, dir: 1, star: false, t: G.t });
    text('X  ' + Math.max(0, G.lives), 128, 152, '#ffffff', 1);
  }

  function drawPaused() {
    drawScene();
    dim(0.55);
    textC('PAUSED', 100, '#ffffff', 2, '#000000');
    textC('P TO RESUME   M TO MUTE', 130, '#ffd042', 1, '#000000');
  }

  function drawGameOver() {
    ctx.fillStyle = '#000000'; ctx.fillRect(0, 0, VW, VH);
    textC('GAME OVER', 80, '#ffffff', 2, '#552222');
    textC('THE FOREST KEEPS ITS SECRETS', 112, '#8fc4f5', 1);
    textC('SCORE ' + pad6(G.score), 136, '#ffd042', 1);
    textC('TOP   ' + pad6(G.best), 148, '#ffd042', 1);
    if (G.stateT > 90 && Math.floor(G.t / 26) % 2) textC('PRESS ENTER', 180, '#ffffff', 1);
  }

  function drawWin() {
    Sprites.background(ctx, 'forest', G.t * 0.3, G.t);
    dim(0.35);
    ctx.fillStyle = 'rgba(20,10,30,0.6)'; ctx.fillRect(10, 20, VW - 20, 200);
    textC('RAVANA HAS FALLEN', 36, '#ffd042', 1, '#000000');
    textC('SITA IS FREE', 52, '#ffffff', 2, '#5a2a00');

    Sprites.hero(ctx, 92, 120, { big: true, bow: true, state: 'stand', frame: 0, dir: 1,
      star: false, t: G.t });
    Sprites.sita(ctx, 116, 124, G.t);
    for (var i = 0; i < 10; i++) {
      var fx = (i * 26 + G.t * 0.6) % VW;
      var fy = 90 + Math.sin((G.t + i * 40) / 30) * 6;
      ctx.fillStyle = i % 2 ? '#ffd042' : '#ff8a2b';
      ctx.fillRect(Math.floor(fx), Math.floor(fy), 2, 2);
    }
    textC('AYODHYA LIGHTS THE LAMPS', 160, '#8fc4f5', 1, '#000000');
    textC('SCORE ' + pad6(G.score), 180, '#ffffff', 1, '#000000');
    textC('TOP   ' + pad6(G.best), 192, '#ffd042', 1, '#000000');
    if (G.stateT > 150 && Math.floor(G.t / 26) % 2) textC('PRESS ENTER', 208, '#ffffff', 1, '#000000');
  }

  function render() {
    switch (G.state) {
      case 'title': drawTitle(); break;
      case 'intro': drawIntro(); break;
      case 'paused': drawPaused(); break;
      case 'gameover': drawGameOver(); break;
      case 'win': drawWin(); break;
      default:
        drawScene();
        if (G.state === 'clear') {
          if (G.stateT > 110) textC('KANDA CLEAR', 70, '#ffffff', 2, '#000000');
        }
    }
    if (Sound.isMuted()) text('MUTED', VW - 40, VH - 12, '#ffffff88', 1);
  }

  /* ============================ loop ============================ */

  function resize() {
    var sx = window.innerWidth / VW;
    var sy = (window.innerHeight - 60) / VH;
    var s = Math.max(1, Math.min(Math.floor(Math.min(sx, sy)), 5));
    canvas.style.width = (VW * s) + 'px';
    canvas.style.height = (VH * s) + 'px';
  }
  window.addEventListener('resize', resize);
  resize();

  /* Exposed for debugging and level authoring from the console:
   *   RamayanaBros.warp(2)  -> jump straight to Lanka
   *   RamayanaBros.player.big = true                                  */
  G.warp = function (i) {
    G.levelIndex = Math.max(0, Math.min(i, Levels.list.length - 1));
    loadLevel(G.levelIndex);
    G.state = 'play'; G.stateT = 0;
  };
  window.RamayanaBros = G;

  var last = 0, acc = 0, STEP = 1000 / 60;
  function frame(ts) {
    if (!last) last = ts;
    acc += Math.min(ts - last, 200);
    last = ts;
    var guard = 0;
    while (acc >= STEP && guard++ < 5) { update(); acc -= STEP; }
    render();
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
})();
