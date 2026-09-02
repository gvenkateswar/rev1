/* ------------------------------------------------------------------
 * Ramayana Bros. -- sound.
 *
 * Everything is synthesised with WebAudio: no asset files, no loading.
 * Sound.fx.*() plays a one-shot blip; Sound.music.play(name) starts a
 * looping two-voice tune that must be pumped from the game loop with
 * Sound.music.update().
 * ------------------------------------------------------------------ */

var Sound = (function () {
  var ac = null;
  var master = null;
  var muted = false;
  var ready = false;

  function init() {
    if (ac) return;
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    ac = new AC();
    master = ac.createGain();
    master.gain.value = 0.22;
    master.connect(ac.destination);
    ready = true;
  }

  /* Browsers only allow audio after a gesture; call this from input. */
  function unlock() {
    init();
    if (ac && ac.state === 'suspended') ac.resume();
  }

  function now() { return ac.currentTime; }

  /* A single enveloped oscillator note. */
  function note(o) {
    if (!ready || muted) return;
    var t0 = (o.at || now()) + (o.delay || 0);
    var dur = o.dur || 0.12;
    var osc = ac.createOscillator();
    var g = ac.createGain();
    osc.type = o.type || 'square';
    osc.frequency.setValueAtTime(o.freq, t0);
    if (o.to && o.to !== o.freq) {
      if (o.slide === 'linear') osc.frequency.linearRampToValueAtTime(o.to, t0 + dur);
      else osc.frequency.exponentialRampToValueAtTime(Math.max(1, o.to), t0 + dur);
    }
    var vol = o.vol == null ? 0.3 : o.vol;
    g.gain.setValueAtTime(0.0001, t0);
    g.gain.exponentialRampToValueAtTime(vol, t0 + 0.008);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    osc.connect(g);
    g.connect(o.bus || master);
    osc.start(t0);
    osc.stop(t0 + dur + 0.02);
  }

  /* Filtered white noise -- used for thuds, breaks and explosions. */
  function noise(o) {
    if (!ready || muted) return;
    var t0 = (o.at || now()) + (o.delay || 0);
    var dur = o.dur || 0.15;
    var frames = Math.max(1, Math.floor(ac.sampleRate * dur));
    var buf = ac.createBuffer(1, frames, ac.sampleRate);
    var data = buf.getChannelData(0);
    for (var i = 0; i < frames; i++) data[i] = (Math.random() * 2 - 1) * (1 - i / frames);
    var src = ac.createBufferSource();
    src.buffer = buf;
    var flt = ac.createBiquadFilter();
    flt.type = o.filter || 'bandpass';
    flt.frequency.setValueAtTime(o.freq || 900, t0);
    if (o.to) flt.frequency.exponentialRampToValueAtTime(Math.max(20, o.to), t0 + dur);
    flt.Q.value = o.q == null ? 1.2 : o.q;
    var g = ac.createGain();
    g.gain.setValueAtTime(o.vol == null ? 0.35 : o.vol, t0);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    src.connect(flt); flt.connect(g); g.connect(master);
    src.start(t0);
  }

  var fx = {
    jump:      function () { note({ freq: 300, to: 720, dur: 0.16, type: 'square', vol: 0.22 }); },
    bigJump:   function () { note({ freq: 240, to: 660, dur: 0.22, type: 'square', vol: 0.24 }); },
    coin:      function () { note({ freq: 988, dur: 0.06, vol: 0.2, type: 'square' });
                             note({ freq: 1319, dur: 0.24, vol: 0.2, type: 'square', delay: 0.06 }); },
    stomp:     function () { noise({ freq: 500, to: 120, dur: 0.12, vol: 0.3 });
                             note({ freq: 180, to: 60, dur: 0.1, type: 'triangle', vol: 0.25 }); },
    bump:      function () { note({ freq: 180, to: 90, dur: 0.09, type: 'square', vol: 0.22 }); },
    brick:     function () { noise({ freq: 2200, to: 300, dur: 0.22, vol: 0.35, filter: 'highpass' }); },
    sprout:    function () { note({ freq: 262, to: 1047, dur: 0.5, type: 'triangle', vol: 0.2, slide: 'linear' }); },
    powerup:   function () { var s = [523, 659, 784, 1047, 1319];
                             for (var i = 0; i < s.length; i++)
                               note({ freq: s[i], dur: 0.12, vol: 0.22, delay: i * 0.07, type: 'square' }); },
    arrow:     function () { note({ freq: 1400, to: 500, dur: 0.09, type: 'sawtooth', vol: 0.14 }); },
    hit:       function () { note({ freq: 500, to: 120, dur: 0.25, type: 'sawtooth', vol: 0.2 }); },
    shrink:    function () { note({ freq: 700, to: 200, dur: 0.3, type: 'square', vol: 0.2 }); },
    kick:      function () { note({ freq: 260, to: 620, dur: 0.08, type: 'square', vol: 0.2 }); },
    die:       function () { var s = [523, 392, 330, 262, 196];
                             for (var i = 0; i < s.length; i++)
                               note({ freq: s[i], dur: 0.18, vol: 0.24, delay: i * 0.13, type: 'square' }); },
    oneUp:     function () { var s = [784, 1047, 1319, 1568];
                             for (var i = 0; i < s.length; i++)
                               note({ freq: s[i], dur: 0.12, vol: 0.2, delay: i * 0.08, type: 'triangle' }); },
    bossHit:   function () { noise({ freq: 1400, to: 200, dur: 0.3, vol: 0.4 });
                             note({ freq: 160, to: 50, dur: 0.35, type: 'sawtooth', vol: 0.25 }); },
    bossRoar:  function () { note({ freq: 110, to: 55, dur: 0.7, type: 'sawtooth', vol: 0.28 });
                             noise({ freq: 300, to: 80, dur: 0.7, vol: 0.25, filter: 'lowpass' }); },
    fire:      function () { noise({ freq: 1200, to: 400, dur: 0.18, vol: 0.16 }); },
    charge:    function () { note({ freq: 90, to: 220, dur: 0.26, type: 'sawtooth', vol: 0.24, slide: 'linear' });
                             noise({ freq: 400, to: 120, dur: 0.26, vol: 0.18, filter: 'lowpass' }); },
    spear:     function () { note({ freq: 900, to: 260, dur: 0.14, type: 'square', vol: 0.16 });
                             noise({ freq: 1800, to: 700, dur: 0.1, vol: 0.12 }); },
    /* each stomp in a chain rings a step higher than the last */
    chain:     function (n) { note({ freq: 523 * Math.pow(1.122, Math.min(n, 8) * 2),
                             dur: 0.1, vol: 0.22, type: 'square' }); },
    spring:    function () { note({ freq: 300, to: 1100, dur: 0.18, type: 'square', vol: 0.22, slide: 'linear' }); },
    crumble:   function () { noise({ freq: 900, to: 200, dur: 0.3, vol: 0.24, filter: 'lowpass' }); },
    checkpoint:function () { var s = [523, 784, 1047];
                             for (var i = 0; i < s.length; i++)
                               note({ freq: s[i], dur: 0.16, vol: 0.22, delay: i * 0.09, type: 'triangle' }); },
    pipe:      function () { note({ freq: 620, to: 130, dur: 0.34, type: 'square', vol: 0.22, slide: 'linear' });
                             noise({ freq: 700, to: 160, dur: 0.34, vol: 0.14, filter: 'lowpass' }); },
    pause:     function () { note({ freq: 660, dur: 0.08, vol: 0.18, type: 'square' });
                             note({ freq: 440, dur: 0.1, vol: 0.18, type: 'square', delay: 0.08 }); },
    flag:      function () { var s = [392, 523, 659, 784, 1047, 1319];
                             for (var i = 0; i < s.length; i++)
                               note({ freq: s[i], dur: 0.11, vol: 0.2, delay: i * 0.06, type: 'triangle' }); }
  };

  /* ---------------- music ----------------
   * Tunes are written on a pentatonic scale (Mohanam-flavoured) so the
   * loops sit somewhere between a Ramayana serial title card and a NES
   * overworld theme. Notes are [scaleDegree, beats]; null = rest.
   * Degrees index SCALE; +7 jumps an octave.                         */

  var SCALE = [0, 2, 4, 7, 9];           // semitone offsets, pentatonic
  function deg(d, base) {
    var oct = Math.floor(d / SCALE.length);
    var s = SCALE[((d % SCALE.length) + SCALE.length) % SCALE.length];
    return base * Math.pow(2, (s + 12 * oct) / 12);
  }

  var TUNES = {
    forest: {
      tempo: 152, base: 261.63, lead: 'square', bass: 'triangle',
      melody: [[5,1],[4,1],[5,1],[7,1],[6,1],[5,1],[4,2],[2,1],[4,1],[5,1],[4,1],[2,1],[1,1],[2,2],
               [5,1],[7,1],[9,1],[7,1],[6,1],[5,1],[4,2],[4,1],[2,1],[1,1],[0,1],[1,2],[2,2]],
      bassline: [[0,2],[2,2],[4,2],[2,2],[0,2],[3,2],[2,2],[1,2]]
    },
    mountain: {
      tempo: 138, base: 220.00, lead: 'square', bass: 'triangle',
      melody: [[2,2],[4,1],[5,1],[7,2],[5,2],[4,1],[2,1],[1,2],[2,2],
               [7,2],[9,1],[7,1],[6,2],[5,2],[4,2],[2,4]],
      bassline: [[0,2],[0,2],[3,2],[3,2],[4,2],[4,2],[2,2],[0,2]]
    },
    lanka: {
      tempo: 168, base: 196.00, lead: 'sawtooth', bass: 'square',
      melody: [[0,1],[1,1],[0,1],[-1,1],[0,2],[3,2],[2,1],[1,1],[0,1],[-1,1],[0,4],
               [5,1],[4,1],[3,1],[2,1],[1,2],[0,2]],
      bassline: [[0,1],[0,1],[3,1],[0,1],[-2,1],[-2,1],[1,1],[-2,1]]
    },
    /* underground: sparse, low, and a little echoing */
    cave: {
      tempo: 118, base: 174.61, lead: 'triangle', bass: 'triangle',
      melody: [[0,2],[null,2],[2,2],[null,2],[4,2],[3,2],[2,4],
               [1,2],[null,2],[3,2],[2,2],[0,4],[null,4]],
      bassline: [[0,4],[-2,4],[1,4],[0,4]]
    },
    boss: {
      tempo: 186, base: 174.61, lead: 'sawtooth', bass: 'square',
      melody: [[0,1],[0,1],[1,1],[0,1],[3,1],[2,1],[1,1],[0,1],
               [-1,1],[-1,1],[0,1],[-1,1],[2,1],[1,1],[0,1],[-1,1]],
      bassline: [[0,1],[0,1],[0,1],[1,1],[-1,1],[-1,1],[-1,1],[0,1]]
    }
  };

  var cur = null, curName = null, nextTime = 0, mi = 0, bi = 0, mAcc = 0, bAcc = 0;
  var LOOKAHEAD = 0.25;

  var music = {
    play: function (name) {
      init();
      if (curName === name) return;
      curName = name;
      cur = TUNES[name] || null;
      mi = bi = 0; mAcc = bAcc = 0;
      nextTime = ready ? now() + 0.05 : 0;
    },
    stop: function () { cur = null; curName = null; },
    /* Schedules a little ahead of the clock; safe to call every frame. */
    update: function () {
      if (!ready || !cur || muted) return;
      var beat = 60 / cur.tempo / 2;          // an eighth note
      var t = now();
      if (nextTime < t) nextTime = t + 0.02;
      while (nextTime < t + LOOKAHEAD) {
        if (mAcc <= 0) {
          var m = cur.melody[mi % cur.melody.length];
          mi++;
          mAcc = m[1];
          if (m[0] !== null) {
            note({ freq: deg(m[0], cur.base), dur: beat * m[1] * 0.85, type: cur.lead,
                   vol: 0.075, at: nextTime });
          }
        }
        if (bAcc <= 0) {
          var b = cur.bassline[bi % cur.bassline.length];
          bi++;
          bAcc = b[1];
          note({ freq: deg(b[0], cur.base) / 2, dur: beat * b[1] * 0.9, type: cur.bass,
                 vol: 0.09, at: nextTime });
        }
        mAcc--; bAcc--;
        nextTime += beat;
      }
    }
  };

  return {
    unlock: unlock,
    fx: fx,
    music: music,
    isMuted: function () { return muted; },
    toggleMute: function () {
      muted = !muted;
      if (master) master.gain.value = muted ? 0 : 0.22;
      if (!muted) { nextTime = ready ? now() + 0.05 : 0; }
      return muted;
    }
  };
})();
