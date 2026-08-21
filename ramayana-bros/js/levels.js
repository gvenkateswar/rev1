/* ------------------------------------------------------------------
 * Ramayana Bros. -- level data.
 *
 * Levels are 15-row tile grids built through a tiny helper so every
 * feature lands on an exact column instead of hand-aligned ASCII.
 *
 * Geometry rules the layouts stick to (a full jump clears ~54px, a
 * running jump ~66px, and the floor is row 13):
 *   - blocks meant to be punched from the ground sit on row 9
 *   - a second storey of blocks only ever sits above a row-9 cluster
 *   - pillars are 2-3 tiles tall (cap on row 10 or 11) so they can be
 *     climbed rather than blocking the road
 *   - floating platforms start on row 10/11 and step up by <= 2 rows
 *
 * Legend
 *   #  earth (solid)        S  carved stone (solid)
 *   B  brick (big Rama smashes it)
 *   ?  block -> coin        M  block -> sanjeevani herb
 *   W  block -> Kodanda bow T  block -> Hanuman's blessing
 *   U  spent block          P/p temple pillar (cap / shaft)
 *   =  rope bridge (stand on top only)
 *   ~  water / molten rock (deadly)
 *   G  Ravana's ward (solid until the demon king falls)
 *   o  loose coin
 *   g  rakshasa   d  Maricha the golden deer   c  Kakasura the crow
 *   R  Ravana     F  goal shrine               I  Sita
 * ------------------------------------------------------------------ */

var Levels = (function () {
  var H = 15, FLOOR = 13;

  function Grid(w) {
    this.w = w; this.h = H;
    this.g = [];
    for (var y = 0; y < H; y++) {
      var row = [];
      for (var x = 0; x < w; x++) row.push(' ');
      this.g.push(row);
    }
  }
  Grid.prototype.set = function (x, y, ch) {
    if (x >= 0 && x < this.w && y >= 0 && y < H) this.g[y][x] = ch;
    return this;
  };
  Grid.prototype.rect = function (x, y, w, h, ch) {
    for (var j = 0; j < h; j++) for (var i = 0; i < w; i++) this.set(x + i, y + j, ch);
    return this;
  };
  Grid.prototype.ground = function (x, w) { return this.rect(x, FLOOR, w, H - FLOOR, '#'); };
  Grid.prototype.liquid = function (x, w) { return this.rect(x, FLOOR, w, H - FLOOR, '~'); };
  /* A horizontal strip written as a short string; '.' leaves a hole. */
  Grid.prototype.put = function (x, y, s) {
    for (var i = 0; i < s.length; i++) if (s[i] !== '.') this.set(x + i, y, s[i]);
    return this;
  };
  Grid.prototype.pillar = function (x, top, w) {
    w = w || 2;
    this.rect(x, top, w, 1, 'P');
    this.rect(x, top + 1, w, FLOOR - top - 1, 'p');
    return this;
  };
  /* Staircase of stone blocks; dir 1 climbs to the right, -1 to the left. */
  Grid.prototype.stair = function (x, n, dir) {
    for (var i = 0; i < n; i++) {
      var col = dir > 0 ? x + i : x - i;
      this.rect(col, FLOOR - 1 - i, 1, i + 1, 'S');
    }
    return this;
  };
  Grid.prototype.coins = function (x, y, n) {
    for (var i = 0; i < n; i++) this.set(x + i, y, 'o');
    return this;
  };
  Grid.prototype.rows = function () {
    var out = [];
    for (var y = 0; y < H; y++) out.push(this.g[y].join(''));
    return out;
  };

  /* ================= 1-1  Dandaka Forest ================= */
  function kanda1() {
    var g = new Grid(214);
    // three gaps, each two tiles wide. A walking jump carries just under
    // four tiles, so the opening stage leaves room to mistime the take-off
    // rather than demanding it from the very edge.
    g.ground(0, 68);            // gap 68-69
    g.ground(70, 45);           // gap 115-116
    g.ground(117, 46);          // gap 163-164
    g.ground(165, 49);

    g.put(16, 9, 'B?BMB');
    g.coins(17, 6, 3);
    g.set(24, 12, 'g');
    g.pillar(34, 11);
    g.set(40, 12, 'd');
    g.pillar(42, 10);
    g.coins(46, 10, 3);
    g.set(50, 12, 'g');
    g.pillar(52, 11);
    g.coins(56, 10, 3);
    g.put(60, 9, 'BB?BB');
    g.set(62, 5, 'M');
    g.set(66, 12, 'g');
    g.coins(68, 9, 2);

    g.put(74, 9, 'B?B');
    g.set(78, 12, 'g');
    g.put(84, 9, 'B??B');
    g.put(84, 6, 'BBBB');
    g.coins(88, 7, 3);
    g.set(91, 12, 'd');
    g.rect(94, 10, 4, 1, '=');
    g.coins(94, 9, 4);
    g.set(100, 12, 'g');
    g.rect(101, 8, 4, 1, '=');
    g.set(103, 4, '?');
    g.pillar(109, 10);
    g.coins(115, 9, 2);

    g.put(120, 9, 'BTB');
    g.set(124, 12, 'g');
    g.stair(126, 4, 1);
    g.set(128, 6, 'c');
    g.stair(134, 4, -1);
    g.coins(136, 10, 3);
    g.put(140, 9, 'B?BB?B');
    g.set(147, 12, 'g');
    g.put(150, 9, 'BMB');
    g.set(150, 10, 'c');
    g.set(155, 12, 'g');
    g.pillar(159, 11);
    g.coins(163, 10, 2);

    g.set(168, 12, 'd');
    g.put(170, 9, 'B?B');
    g.set(174, 12, 'g');
    g.pillar(176, 10);
    g.put(180, 9, 'BB?BB');
    g.set(182, 5, '?');
    g.set(186, 12, 'g');
    g.stair(188, 8, 1);
    g.rect(196, 5, 1, 8, 'S');
    g.set(203, 12, 'F');
    return {
      id: '1-1', name: 'DANDAKA FOREST', theme: 'forest', music: 'forest',
      time: 320, grid: g.rows(),
      blurb: 'Rama walks south through the great forest.'
    };
  }

  /* ================= 1-2  Kishkindha Heights ================= */
  function kanda2() {
    var g = new Grid(220);
    g.ground(0, 26);   g.liquid(26, 14);
    g.ground(40, 26);  g.liquid(66, 10);
    g.ground(76, 34);  g.liquid(110, 12);
    g.ground(122, 30); g.liquid(152, 14);
    g.ground(166, 54);

    g.put(8, 9, 'BMB');
    g.set(12, 12, 'g');
    g.coins(14, 10, 3);
    g.stair(19, 3, 1);

    g.rect(26, 11, 14, 1, '=');          // rope bridge
    g.coins(28, 10, 3);
    g.set(31, 8, 'c');
    g.coins(34, 10, 3);
    g.set(37, 8, 'c');

    g.put(44, 9, 'B?B?B');
    g.set(46, 12, 'd');
    g.pillar(52, 10);
    g.set(56, 12, 'g');
    g.coins(56, 10, 3);
    g.put(60, 9, 'BBBB');
    g.set(61, 8, 'c');
    g.set(64, 12, 'g');

    g.rect(66, 11, 4, 1, '=');
    g.coins(66, 10, 4);
    g.rect(72, 9, 4, 1, '=');
    g.coins(72, 8, 4);

    g.put(80, 9, 'BWB');                 // the Kodanda bow
    g.set(84, 12, 'g');
    g.set(86, 12, 'g');
    g.stair(90, 5, 1);
    g.rect(95, 8, 5, 1, 'S');
    g.coins(95, 7, 5);
    g.set(97, 5, 'c');
    g.stair(104, 5, -1);
    g.set(107, 12, 'd');

    g.rect(110, 11, 5, 1, '=');
    g.coins(110, 10, 4);
    g.set(115, 7, 'c');
    g.rect(117, 9, 5, 1, '=');
    g.coins(117, 8, 4);

    g.put(126, 9, 'B?BTB');
    g.set(131, 12, 'g');
    g.pillar(134, 10);
    g.coins(137, 10, 4);
    g.set(140, 12, 'd');
    g.pillar(142, 11);
    g.put(145, 9, 'BB?BB');
    g.set(147, 5, '?');
    g.set(150, 12, 'g');

    g.rect(152, 11, 6, 1, '=');
    g.coins(153, 10, 4);
    g.set(158, 9, 'c');
    g.rect(160, 11, 6, 1, '=');
    g.coins(161, 10, 4);

    g.put(170, 9, 'BMB');
    g.set(174, 12, 'g');
    g.set(176, 12, 'd');
    g.rect(180, 10, 5, 1, '=');
    g.coins(180, 9, 5);
    g.set(186, 12, 'g');
    g.put(190, 9, 'B?B');
    g.stair(196, 8, 1);
    g.rect(204, 5, 1, 8, 'S');
    g.set(210, 12, 'F');
    return {
      id: '1-2', name: 'KISHKINDHA HEIGHTS', theme: 'mountain', music: 'mountain',
      time: 340, grid: g.rows(),
      blurb: 'Across the monkey kingdom, down to the southern sea.'
    };
  }

  /* ================= 1-3  Lanka ================= */
  function kanda3() {
    var g = new Grid(212);
    g.ground(0, 30);  g.liquid(30, 8);
    g.ground(38, 28); g.liquid(66, 10);
    g.ground(76, 32); g.liquid(108, 10);
    g.ground(118, 94);

    g.put(9, 9, 'BMB');
    g.set(13, 12, 'g');
    g.set(16, 12, 'd');
    g.coins(18, 10, 4);
    g.put(22, 9, 'B?B');
    g.set(26, 10, 'c');

    g.rect(30, 11, 4, 1, '=');
    g.coins(30, 10, 4);
    g.rect(35, 10, 3, 1, '=');
    g.coins(35, 9, 3);

    g.put(42, 9, 'BWB');                 // bow, for anyone who missed it
    g.set(46, 12, 'g');
    g.set(48, 12, 'g');
    g.set(50, 12, 'd');
    g.pillar(52, 10);
    g.coins(55, 10, 3);
    g.put(58, 9, 'BB?BB');
    g.set(60, 5, '?');
    g.set(64, 12, 'g');

    g.rect(66, 11, 4, 1, '=');
    g.coins(66, 10, 4);
    g.set(70, 7, 'c');
    g.rect(72, 9, 4, 1, '=');
    g.coins(72, 8, 4);

    g.put(80, 9, 'B?BTB');               // blessing before the hard run
    g.set(86, 12, 'g');
    g.stair(88, 5, 1);
    g.rect(93, 8, 5, 1, 'S');
    g.coins(93, 7, 5);
    g.set(95, 5, 'c');
    g.stair(102, 5, -1);
    g.set(104, 12, 'g');
    g.set(105, 12, 'd');

    g.rect(108, 11, 5, 1, '=');
    g.coins(108, 10, 5);
    g.rect(114, 10, 4, 1, '=');
    g.coins(115, 9, 2);
    g.set(112, 7, 'c');

    g.put(122, 9, 'BMB');
    g.set(126, 12, 'g');
    g.set(128, 12, 'd');
    g.pillar(132, 10);
    g.coins(135, 10, 4);
    g.set(140, 12, 'g');
    g.put(142, 9, 'BB?BB');
    g.set(144, 5, '?');
    g.set(148, 12, 'd');

    // the gate of Lanka
    g.pillar(152, 11);
    g.rect(152, 6, 16, 1, 'S');
    g.rect(152, 5, 16, 1, 'S');
    g.pillar(166, 11);
    g.put(156, 9, 'BWB');                // last chance at the bow
    g.set(160, 12, 'g');
    g.set(163, 10, 'c');

    // Ravana's court
    g.put(172, 9, 'B?B');
    g.put(178, 9, 'BWB');                // a bow inside the arena
    g.set(186, 11, 'R');
    g.coins(190, 10, 5);
    g.rect(200, 5, 1, 8, 'G');           // ward -- falls with Ravana
    g.set(206, 12, 'I');                 // Sita, in the ashoka grove
    return {
      id: '1-3', name: 'LANKA', theme: 'lanka', music: 'lanka',
      time: 400, grid: g.rows(),
      blurb: 'The island fortress. Ravana waits on his throne.'
    };
  }

  return { list: [kanda1(), kanda2(), kanda3()] };
})();
