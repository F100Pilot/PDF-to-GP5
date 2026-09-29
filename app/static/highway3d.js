// Rocksmith-style 3D note highway for one track. Drawn with three.js (vendored, loaded on first use)
// and driven by the alphaTab player position, so it follows the same audio, speed and seeking.
(() => {
  "use strict";

  const THREE_URL = "/vendor/three/three.module.js";
  const TICKS_PER_QUARTER = 960; // alphaTab MIDI resolution
  const Z_PER_TICK = 4 / TICKS_PER_QUARTER; // highway length of a quarter note: 4 units
  const VIEW_AHEAD = 16 * TICKS_PER_QUARTER; // notes shown this far ahead of the strike line
  const SUSTAIN_MIN = TICKS_PER_QUARTER; // shorter notes get no sustain trail
  const ANCHOR_BEFORE = TICKS_PER_QUARTER; // fret window that the camera follows
  const ANCHOR_AFTER = 3 * TICKS_PER_QUARTER;
  const MIN_ANCHOR_WIDTH = 4;
  const FRETS = 24;
  const STRING_GAP = 0.42;
  const BEND_RISE = STRING_GAP / 4; // trail height per quarter tone: a full-tone bend reaches the next string
  // Rocksmith string colours, lowest string first; a 7th (low) string gets grey.
  const STRING_COLORS = [0xe53935, 0xfdd835, 0x1e88e5, 0xfb8c00, 0x43a047, 0x8e24aa];
  const EXTRA_LOW_COLOR = 0x9e9e9e;
  const INLAYS = [3, 5, 7, 9, 12, 15, 17, 19, 21, 24];

  let THREE = null;
  let loading = null;
  let stage = null; // renderer, scene, camera and the static parts of the highway
  let song = null; // the current track: notes, anchors and the moving lane
  const clock = { tick: 0, time: 0, rate: 0, playing: false };
  let running = false;
  let tilt = 0.5; // 0 = eye level with the strings … 1 = steep, from above
  let side = 0; // -1 = from the left … 1 = from the right (diagonal view)

  function loadThree() {
    if (THREE) return Promise.resolve(THREE);
    if (!loading) {
      loading = import(THREE_URL).then((module) => {
        THREE = module;
        return THREE;
      }, (error) => {
        loading = null;
        throw error;
      });
    }
    return loading;
  }

  function stringColor(string, count) {
    if (count <= STRING_COLORS.length) return STRING_COLORS[string - 1];
    return string === 1 ? EXTRA_LOW_COLOR : STRING_COLORS[string - 2];
  }

  // Lowest string on top, as in Rocksmith.
  function stringY(string, count) {
    return 0.6 + (count - string) * STRING_GAP;
  }

  function fretX(fret) {
    return fret - 0.5; // centre of the space behind fret wire `fret`
  }

  // Notes disappear once they pass the strike line (sustain trails shrink as they are played).
  let strikeClip = null;
  function laneClip() {
    if (!strikeClip) strikeClip = [new THREE.Plane(new THREE.Vector3(0, 0, -1), 0.15)];
    return strikeClip;
  }

  const labelCache = new Map();
  function labelMaterial(text, clipped, color) {
    const key = `${clipped ? "lane" : "fixed"}:${color}:${text}`;
    if (!labelCache.has(key)) {
      const canvas = document.createElement("canvas");
      canvas.height = 128;
      canvas.width = text.length > 2 ? 256 : 128;
      const ctx = canvas.getContext("2d");
      let size = 84;
      ctx.font = `bold ${size}px system-ui, sans-serif`;
      const fit = (canvas.width - 20) / ctx.measureText(text).width;
      if (fit < 1) size = Math.floor(size * fit);
      ctx.font = `bold ${size}px system-ui, sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.lineWidth = 12;
      ctx.strokeStyle = "#000000";
      ctx.strokeText(text, canvas.width / 2, 68);
      ctx.fillStyle = color;
      ctx.fillText(text, canvas.width / 2, 68);
      const texture = new THREE.CanvasTexture(canvas);
      texture.colorSpace = THREE.SRGBColorSpace;
      const material = new THREE.SpriteMaterial({ map: texture, transparent: true, depthWrite: false });
      if (clipped) material.clippingPlanes = laneClip();
      labelCache.set(key, material);
    }
    return labelCache.get(key);
  }

  // Text that always faces the camera; `height` in highway units.
  function label(text, height, clipped = false, color = "#ffffff") {
    const material = labelMaterial(text, clipped, color);
    const sprite = new THREE.Sprite(material);
    sprite.scale.set((height * material.map.image.width) / 128, height, 1);
    return sprite;
  }

  function createStage(host) {
    let renderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true });
    } catch {
      throw new Error("Este browser não tem WebGL (aceleração gráfica) ativo: a pista 3D não está disponível.");
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.localClippingEnabled = true;

    // Overlay: current bar / section and a progress bar, so progress shows even without notes.
    const hud = document.createElement("div");
    hud.className = "hw-hud";
    const position = document.createElement("span");
    const progress = document.createElement("div");
    progress.className = "hw-progress";
    const fill = document.createElement("div");
    fill.className = "hw-progress-fill";
    progress.appendChild(fill);
    hud.append(position, progress);
    const lyricsLine = document.createElement("div");
    lyricsLine.className = "hw-lyrics";
    host.replaceChildren(renderer.domElement, hud, lyricsLine);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0b0d14);
    const far = VIEW_AHEAD * Z_PER_TICK;
    scene.fog = new THREE.Fog(0x0b0d14, far * 0.55, far);
    scene.add(new THREE.AmbientLight(0xffffff, 0.9));
    const sun = new THREE.DirectionalLight(0xffffff, 1.6);
    sun.position.set(4, 10, 6);
    scene.add(sun);

    const camera = new THREE.PerspectiveCamera(55, 16 / 9, 0.1, far + 20);
    const resize = () => {
      const width = host.clientWidth || 800;
      const height = host.clientHeight || 450;
      renderer.setSize(width, height, false);
      renderer.domElement.style.width = "100%";
      renderer.domElement.style.height = "100%";
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(host);
    resize();

    // Floor with fret wires, inlays and fret numbers at the strike line.
    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(FRETS + 1, far + 4),
      new THREE.MeshStandardMaterial({ color: 0x151a26, roughness: 1 }),
    );
    floor.rotation.x = -Math.PI / 2;
    floor.position.set((FRETS - 1) / 2, 0, -far / 2 + 2);
    scene.add(floor);

    const wires = [];
    for (let fret = 0; fret <= FRETS; fret += 1) wires.push(fret, 0.01, 2, fret, 0.01, -far);
    const wireGeometry = new THREE.BufferGeometry();
    wireGeometry.setAttribute("position", new THREE.Float32BufferAttribute(wires, 3));
    scene.add(new THREE.LineSegments(wireGeometry, new THREE.LineBasicMaterial({ color: 0x3a4254 })));

    const inlayMaterial = new THREE.MeshBasicMaterial({ color: 0x2c3447 });
    for (const fret of INLAYS) {
      const offsets = fret % 12 === 0 ? [-0.18, 0.18] : [0];
      for (const offset of offsets) {
        const dot = new THREE.Mesh(new THREE.CircleGeometry(0.12, 20), inlayMaterial);
        dot.rotation.x = -Math.PI / 2;
        dot.position.set(fretX(fret) + offset, 0.02, 1.2);
        scene.add(dot);
      }
    }
    for (let fret = 1; fret <= FRETS; fret += 1) {
      // Just in front of the strike line, so they stay in view at every camera tilt.
      const number = label(String(fret), 0.4);
      number.position.set(fretX(fret), 0.14, 0.3);
      scene.add(number);
    }

    // Region of the neck being played (the "anchor"), lit on the floor.
    const anchor = new THREE.Mesh(
      new THREE.PlaneGeometry(1, far + 4),
      new THREE.MeshBasicMaterial({ color: 0x2b3a5c, transparent: true, opacity: 0.55, depthWrite: false }),
    );
    anchor.rotation.x = -Math.PI / 2;
    anchor.position.set(0, 0.015, -far / 2 + 2);
    scene.add(anchor);

    return { host, renderer, scene, camera, observer, anchor, strings: [], cameraX: 5, hud: { position, fill, bar: -1, percent: -1, lyrics: lyricsLine, line: -1, sung: -2 }, effects: [] };
  }

  function buildStrings(count) {
    for (const bar of stage.strings) {
      if (!bar) continue; // indexed by string number, from 1
      stage.scene.remove(bar.mesh);
      bar.mesh.geometry.dispose();
      bar.material.dispose();
    }
    stage.strings = [];
    for (let string = 1; string <= count; string += 1) {
      const material = new THREE.MeshStandardMaterial({
        color: stringColor(string, count),
        emissive: stringColor(string, count),
        emissiveIntensity: 0.25,
      });
      const mesh = new THREE.Mesh(new THREE.BoxGeometry(FRETS + 1, 0.05, 0.05), material);
      mesh.position.set((FRETS - 1) / 2, stringY(string, count), 0);
      stage.scene.add(mesh);
      stage.strings[string] = { mesh, material, glow: 0 };
    }
  }

  // alphaTab enum values (model.*Type), kept numeric so no internal namespace is needed.
  const SLIDE_OUT = { shift: 1, legato: 2, outUp: 3, outDown: 4, pickDown: 5, pickUp: 6 };
  const SLIDE_IN = { fromBelow: 1, fromAbove: 2 };
  const BEND = { bend: 2, release: 3, bendRelease: 4, hold: 5, prebend: 6, prebendBend: 7, prebendRelease: 8 };
  const HARMONIC_TAGS = { 2: "AH", 3: "PH", 4: "TH", 5: "SH", 6: "FB" }; // natural (1) is shown by the shape only
  const BRUSH = { up: 1, down: 2 };

  // "½", "1", "1½": bend amount in tones from alphaTab's quarter-tone value.
  function bendAmount(quarterTones) {
    const tones = quarterTones / 4;
    const whole = Math.floor(tones);
    const rest = { 0: "", 0.25: "¼", 0.5: "½", 0.75: "¾" }[tones - whole] ?? "";
    return whole ? `${whole}${rest}` : rest || "¼";
  }

  function bendText(note) {
    if (!note.hasBend || note.bendType === BEND.hold) return "";
    const amount = bendAmount(note.maxBendPoint ? note.maxBendPoint.value : 4);
    switch (note.bendType) {
      case BEND.release: return "↓";
      case BEND.bendRelease: return `↑↓${amount}`;
      case BEND.prebend: return `PB${amount}`;
      case BEND.prebendBend: return `PB↑${amount}`;
      case BEND.prebendRelease: return `PB↓${amount}`;
      default: return `↑${amount}`;
    }
  }

  // Bend height along a note and the notes tied to it: [{ tick, value }] in quarter tones, or null
  // when nothing in the chain is bent. A tied note without bend points keeps the previous height.
  function bendCurve(chain) {
    if (!chain.some((part) => part.hasBend)) return null;
    const curve = [];
    let value = 0;
    for (const part of chain) {
      const start = part.beat.absolutePlaybackStart;
      const duration = part.beat.playbackDuration;
      const points = part.hasBend && part.bendPoints ? part.bendPoints : [];
      if (!points.length) {
        curve.push({ tick: start, value }, { tick: start + duration, value });
        continue;
      }
      for (const point of points) {
        value = point.value;
        curve.push({ tick: start + (point.offset / 60) * duration, value });
      }
    }
    return curve;
  }

  const NOTE_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"];
  // Chord types by intervals above the root, most usual first (earlier wins when two names fit).
  const CHORD_TYPES = [
    ["", [0, 4, 7]], ["m", [0, 3, 7]], ["5", [0, 7]], ["7", [0, 4, 7, 10]], ["m7", [0, 3, 7, 10]],
    ["maj7", [0, 4, 7, 11]], ["sus4", [0, 5, 7]], ["sus2", [0, 2, 7]], ["add9", [0, 2, 4, 7]],
    ["m(add9)", [0, 2, 3, 7]], ["6", [0, 4, 7, 9]], ["m6", [0, 3, 7, 9]], ["7sus4", [0, 5, 7, 10]],
    ["dim", [0, 3, 6]], ["aug", [0, 4, 8]], ["m7b5", [0, 3, 6, 10]], ["dim7", [0, 3, 6, 9]],
  ].map(([name, intervals]) => [name, intervals.join(",")]);

  // Name of the chord formed by MIDI `pitches` ("A", "F#m", "E5", "D/F#"); "" when no known chord fits
  // exactly, so nothing is invented for partial or unusual voicings.
  function chordName(pitches) {
    const pcs = [...new Set(pitches.map((pitch) => ((pitch % 12) + 12) % 12))];
    if (pcs.length < 2) return "";
    const bass = ((Math.min(...pitches) % 12) + 12) % 12;
    let best = null;
    for (const root of pcs) {
      const intervals = pcs.map((pc) => (pc - root + 12) % 12).sort((a, b) => a - b).join(",");
      const type = CHORD_TYPES.findIndex(([, known]) => known === intervals);
      if (type < 0) continue;
      const rank = (root === bass ? 0 : 100) + type;
      if (!best || rank < best.rank) {
        const slash = root === bass ? "" : `/${NOTE_NAMES[bass]}`;
        best = { rank, name: `${NOTE_NAMES[root]}${CHORD_TYPES[type][0]}${slash}` };
      }
    }
    return best ? best.name : "";
  }

  // Lyric syllables of the song (alphaTab spreads GP5 lyrics over the beats of the lyrics track).
  function collectLyrics(score) {
    const syllables = [];
    for (const track of score.tracks) {
      for (const bar of track.staves[0].bars) {
        for (const voice of bar.voices) {
          for (const beat of voice.beats) {
            const text = beat.lyrics ? beat.lyrics.filter(Boolean).join(" ").trim() : "";
            if (text) syllables.push({ tick: beat.absolutePlaybackStart, text });
          }
        }
      }
    }
    return syllables.sort((a, b) => a.tick - b.tick);
  }

  // Playable notes of the track with their techniques; ties are folded into the sustain of the
  // note they continue.
  function collectNotes(track) {
    const notes = [];
    const chords = [];
    for (const bar of track.staves[0].bars) {
      for (const voice of bar.voices) {
        for (const beat of voice.beats) {
          if (beat.isRest || !beat.notes.length) continue;
          const tick = beat.absolutePlaybackStart;
          const struck = beat.notes.filter((note) => !note.isTieDestination);
          for (const note of struck) {
            const chain = [note];
            for (let next = note.tieDestination; next; next = next.tieDestination) chain.push(next);
            const length = chain.reduce((sum, part) => sum + part.beat.playbackDuration, 0);
            const target = note.slideTarget;
            const legatoFrom = note.isHammerPullDestination && note.hammerPullOrigin;
            notes.push({
              tick,
              fret: note.fret,
              string: note.string,
              dead: note.isDead,
              length,
              ghost: note.isGhost,
              palmMute: note.isPalmMute,
              harmonic: note.harmonicType,
              vibrato: note.vibrato,
              tap: beat.tap,
              bend: bendText(note),
              bendCurve: bendCurve(chain),
              slideOut: note.slideOutType,
              slideIn: note.slideInType,
              slideTo: target ? { tick: target.beat.absolutePlaybackStart, fret: target.fret } : null,
              // Not picked: reached by a legato slide or a hammer-on / pull-off.
              unpicked: Boolean(legatoFrom) || Boolean(note.slideOrigin && note.slideOrigin.slideOutType === SLIDE_OUT.legato),
              legato: legatoFrom ? (note.fret >= legatoFrom.fret ? "H" : "P") : "",
            });
          }
          const fretted = struck.filter((note) => !note.isDead && note.fret > 0);
          if (struck.length > 1 && fretted.length) {
            chords.push({
              tick,
              low: Math.min(...fretted.map((note) => note.fret)),
              high: Math.max(...fretted.map((note) => note.fret)),
              brush: beat.brushType === BRUSH.down ? "↓" : beat.brushType === BRUSH.up ? "↑" : "",
              name: chordName(struck.filter((note) => !note.isDead).map((note) => note.realValue)),
            });
          }
        }
      }
    }
    notes.sort((a, b) => a.tick - b.tick);
    return { notes, chords };
  }

  // For each note: the fret window [low, high] played around it (open strings ignored).
  function computeAnchors(notes) {
    let previous = { low: 1, high: MIN_ANCHOR_WIDTH };
    let start = 0;
    return notes.map((note) => {
      while (notes[start].tick < note.tick - ANCHOR_BEFORE) start += 1;
      let low = Infinity;
      let high = -Infinity;
      for (let i = start; i < notes.length && notes[i].tick <= note.tick + ANCHOR_AFTER; i += 1) {
        if (notes[i].fret > 0 && !notes[i].dead) {
          low = Math.min(low, notes[i].fret);
          high = Math.max(high, notes[i].fret);
        }
      }
      if (low === Infinity) return previous;
      if (high - low + 1 < MIN_ANCHOR_WIDTH) high = Math.min(FRETS, low + MIN_ANCHOR_WIDTH - 1);
      previous = { low, high };
      return previous;
    });
  }

  // Free the GPU resources of the previous track (label materials are shared and kept).
  function disposeSong() {
    if (!song) return;
    clearEffects(); // effects share the chord frame geometry disposed below
    stage.scene.remove(song.lane);
    song.lane.traverse((object) => {
      if (object.geometry && !object.isSprite) object.geometry.dispose(); // sprites share one geometry
    });
    for (const material of song.materials) material.dispose();
    song = null;
  }

  function buildSong(score, trackIndex) {
    disposeSong();
    const track = score.tracks[trackIndex];
    const count = track.staves[0].tuning.length;
    buildStrings(count);
    const { notes, chords } = collectNotes(track);
    const anchors = computeAnchors(notes);
    const lane = new THREE.Group();

    const gem = new THREE.BoxGeometry(0.8, 0.26, 0.26);
    const diamond = new THREE.OctahedronGeometry(0.22);
    const unit = new THREE.BoxGeometry(1, 1, 1);
    const gemMaterials = [];
    const unpickedMaterials = [];
    const trailMaterials = [];
    for (let string = 1; string <= count; string += 1) {
      const color = stringColor(string, count);
      gemMaterials[string] = new THREE.MeshStandardMaterial({
        color, emissive: color, emissiveIntensity: 0.35, roughness: 0.35, clippingPlanes: laneClip(),
      });
      unpickedMaterials[string] = new THREE.MeshStandardMaterial({
        color, emissive: color, emissiveIntensity: 0.2, transparent: true, opacity: 0.4, clippingPlanes: laneClip(),
      });
      trailMaterials[string] = new THREE.MeshBasicMaterial({
        color, transparent: true, opacity: 0.45, depthWrite: false, clippingPlanes: laneClip(),
      });
    }
    const deadMaterial = new THREE.MeshStandardMaterial({ color: 0x8a8f99, roughness: 0.6, clippingPlanes: laneClip() });
    const chordMaterial = new THREE.LineBasicMaterial({
      color: 0xffffff, transparent: true, opacity: 0.55, clippingPlanes: laneClip(),
    });

    // A flat ribbon between two points of the lane (sustain trails and slides).
    const ribbon = (material, x0, z0, x1, z1, y) => {
      const dx = x1 - x0;
      const dz = z1 - z0;
      const mesh = new THREE.Mesh(unit, material);
      mesh.scale.set(0.16, 0.06, Math.hypot(dx, dz));
      mesh.rotation.y = Math.atan2(dx, dz);
      mesh.position.set((x0 + x1) / 2, y, (z0 + z1) / 2);
      lane.add(mesh);
    };
    // Sustain as a tube: rises with the bend curve (Rocksmith style) and wiggles with vibrato.
    const sustainTube = (material, x, y, note, lengthTicks) => {
      const curve = note.bendCurve || [{ tick: note.tick, value: 0 }, { tick: note.tick + lengthTicks, value: 0 }];
      const amplitude = note.vibrato === 2 ? 0.22 : note.vibrato ? 0.12 : 0;
      const points = [];
      for (let i = 0; i + 1 < curve.length; i += 1) {
        const a = curve[i];
        const b = curve[i + 1];
        const steps = Math.max(2, Math.round((b.tick - a.tick) * Z_PER_TICK * 6));
        for (let step = i ? 1 : 0; step <= steps; step += 1) {
          const t = step / steps;
          const tick = a.tick + (b.tick - a.tick) * t;
          const z = -tick * Z_PER_TICK;
          points.push(new THREE.Vector3(
            x + Math.sin(z * 4) * amplitude,
            y + (a.value + (b.value - a.value) * t) * BEND_RISE,
            z,
          ));
        }
      }
      if (points.length < 2 || points[0].distanceTo(points[points.length - 1]) < 0.01) return;
      const path = new THREE.CatmullRomCurve3(points, false, "centripetal");
      lane.add(new THREE.Mesh(new THREE.TubeGeometry(path, points.length * 2, note.bendCurve ? 0.06 : 0.045, 6), material));
    };
    const tag = (text, x, y, z, color) => {
      const sprite = label(text, 0.3, true, color);
      sprite.position.set(x, y, z + 0.2);
      lane.add(sprite);
    };

    notes.forEach((note, i) => {
      const y = stringY(note.string, count);
      const z = -note.tick * Z_PER_TICK;
      const material = note.dead ? deadMaterial : note.unpicked ? unpickedMaterials[note.string] : gemMaterials[note.string];
      let x;
      if (note.fret === 0 && !note.dead) {
        // Open string: a bar across the fret window being played.
        const { low, high } = anchors[i];
        const bar = new THREE.Mesh(unit, material);
        bar.scale.set(high - low + 1, 0.16, 0.22);
        x = (fretX(low) + fretX(high)) / 2;
        bar.position.set(x, y, z);
        lane.add(bar);
      } else {
        x = fretX(note.fret);
        const mesh = new THREE.Mesh(note.harmonic && !note.dead ? diamond : gem, material);
        mesh.position.set(x, y, z);
        lane.add(mesh);
      }
      const fretText = note.dead ? "X" : note.ghost ? `(${note.fret})` : String(note.fret);
      const text = label(fretText, 0.42, true);
      text.position.set(x, y + 0.02, z + 0.2);
      lane.add(text);

      // Technique marks above the note.
      const marks = [note.legato, note.tap ? "T" : "", HARMONIC_TAGS[note.harmonic] || "", note.palmMute ? "PM" : ""]
        .filter(Boolean)
        .join(" ");
      if (marks) tag(marks, x, y + 0.34, z, "#e6edf3");
      if (note.bend) tag(note.bend, x, y + (marks ? 0.62 : 0.34), z, "#ffd54f");

      if (note.dead) return;
      const length = Math.max(note.length, note.vibrato ? SUSTAIN_MIN : 0) * Z_PER_TICK;
      const trailY = y - 0.06;
      if (note.slideIn === SLIDE_IN.fromBelow || note.slideIn === SLIDE_IN.fromAbove) {
        const from = note.fret + (note.slideIn === SLIDE_IN.fromBelow ? -3 : 3);
        ribbon(trailMaterials[note.string], fretX(Math.max(0, from)), z + 1.2, x, z, trailY);
      }
      if ((note.slideOut === SLIDE_OUT.shift || note.slideOut === SLIDE_OUT.legato) && note.slideTo) {
        // Slide to the next note: the trail runs to the target fret at the target's time.
        ribbon(trailMaterials[note.string], x, z, fretX(note.slideTo.fret), -note.slideTo.tick * Z_PER_TICK, trailY);
      } else if (note.slideOut >= SLIDE_OUT.outUp) {
        const up = note.slideOut === SLIDE_OUT.outUp || note.slideOut === SLIDE_OUT.pickUp;
        const to = Math.min(FRETS, Math.max(0, note.fret + (up ? 4 : -4)));
        ribbon(trailMaterials[note.string], x, z, fretX(to), z - Math.max(length, 2), trailY);
      } else if (note.bendCurve || note.vibrato) {
        sustainTube(trailMaterials[note.string], x, trailY, note, length / Z_PER_TICK);
      } else if (note.length >= SUSTAIN_MIN) {
        ribbon(trailMaterials[note.string], x, z, x, z - length, trailY);
      }
    });

    // Bar lines (bright) and beat lines (dim) across the highway, bar numbers and section names
    // beside the fret window played at that time.
    const barMaterial = new THREE.MeshBasicMaterial({ color: 0xcfd8e3, transparent: true, opacity: 0.85, clippingPlanes: laneClip() });
    const beatMaterial = new THREE.MeshBasicMaterial({ color: 0x5b667a, transparent: true, opacity: 0.7, clippingPlanes: laneClip() });
    const bars = [];
    for (const masterBar of score.masterBars) {
      const beatTicks = (TICKS_PER_QUARTER * 4) / masterBar.timeSignatureDenominator;
      for (let beat = 0; beat < masterBar.timeSignatureNumerator; beat += 1) {
        const line = new THREE.Mesh(unit, beat ? beatMaterial : barMaterial);
        line.scale.set(FRETS + 1, beat ? 0.01 : 0.02, beat ? 0.03 : 0.08);
        line.position.set((FRETS - 1) / 2, 0.03, -(masterBar.start + beat * beatTicks) * Z_PER_TICK);
        lane.add(line);
      }
      const section = masterBar.section && masterBar.section.text ? masterBar.section.text : "";
      bars.push({ tick: masterBar.start, section });
      const nearest = Math.min(indexOf(notes, masterBar.start), notes.length - 1);
      const zone = anchors[nearest] || { low: 1, high: MIN_ANCHOR_WIDTH };
      const x = fretX(zone.low) - 1.3;
      const z = -masterBar.start * Z_PER_TICK;
      const number = label(String(masterBar.index + 1), 0.5, true, "#cfd8e3");
      number.position.set(x, 0.35, z);
      lane.add(number);
      if (section) {
        const name = label(section, 0.55, true, "#ffd54f");
        name.position.set(x, stringY(1, count) + 0.7, z);
        lane.add(name);
      }
    }
    const last = score.masterBars[score.masterBars.length - 1];
    const endTick = last ? last.start + (TICKS_PER_QUARTER * 4 * last.timeSignatureNumerator) / last.timeSignatureDenominator : 1;

    const top = stringY(1, count) + 0.2;
    const bottom = stringY(count, count) - 0.2;
    let lastName = "";
    let lastTick = -Infinity;
    for (const chord of chords) {
      const width = chord.high - chord.low + 1;
      chord.x = (fretX(chord.low) + fretX(chord.high)) / 2;
      chord.frame = new THREE.EdgesGeometry(new THREE.BoxGeometry(width, top - bottom, 0.02));
      const frame = new THREE.LineSegments(chord.frame, chordMaterial);
      frame.position.set(chord.x, (top + bottom) / 2, -chord.tick * Z_PER_TICK);
      lane.add(frame);
      // Chord name on top, when it changes (or comes back after more than a bar).
      if (chord.name && (chord.name !== lastName || chord.tick - lastTick > 4 * TICKS_PER_QUARTER)) {
        const name = label(chord.name, 0.5, true, "#ffffff");
        name.position.set(chord.x, top + 0.4, -chord.tick * Z_PER_TICK);
        lane.add(name);
      }
      if (chord.name) {
        lastName = chord.name;
        lastTick = chord.tick;
      }
      if (chord.brush) {
        const arrow = label(chord.brush, 0.7, true, "#ffd54f");
        arrow.position.set(fretX(chord.low) - 0.9, (top + bottom) / 2, -chord.tick * Z_PER_TICK);
        lane.add(arrow);
      }
    }

    stage.scene.add(lane);
    const materials = [
      ...gemMaterials, ...unpickedMaterials, ...trailMaterials, deadMaterial, chordMaterial, barMaterial, beatMaterial,
    ].filter(Boolean);
    clearEffects();
    song = {
      lane, notes, anchors, count, materials, bars, endTick, chords, top, bottom,
      lyrics: collectLyrics(score), nextHit: 0, nextChord: 0,
    };
    stage.hud.bar = -1;
    stage.hud.line = -1;
    seekHits(currentTick());
  }

  // Hit effects at the strike line: when a note reaches the strings its number stays there, with a
  // glow on the note (and on the chord frame), while it rings; then it fades out.
  let glowTexture = null;
  function glowMap() {
    if (!glowTexture) {
      const canvas = document.createElement("canvas");
      canvas.width = 128;
      canvas.height = 128;
      const ctx = canvas.getContext("2d");
      const gradient = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
      gradient.addColorStop(0, "rgba(255,255,255,1)");
      gradient.addColorStop(0.35, "rgba(255,255,255,0.55)");
      gradient.addColorStop(1, "rgba(255,255,255,0)");
      ctx.fillStyle = gradient;
      ctx.fillRect(0, 0, 128, 128);
      glowTexture = new THREE.CanvasTexture(canvas);
    }
    return glowTexture;
  }

  const FADE_MS = 300;
  let hitGem = null;

  function addEffect(parts, until) {
    for (const part of parts) stage.scene.add(part);
    stage.effects.push({ parts, until, fadeStart: 0 });
  }

  function spawnNoteHit(note, index) {
    const color = stringColor(note.string, song.count);
    const y = stringY(note.string, song.count);
    const { low, high } = song.anchors[index] || { low: 1, high: MIN_ANCHOR_WIDTH };
    const x = note.fret === 0 && !note.dead ? (fretX(low) + fretX(high)) / 2 : fretX(note.fret);
    if (!hitGem) hitGem = new THREE.BoxGeometry(0.86, 0.3, 0.3);
    const gem = new THREE.Mesh(hitGem, new THREE.MeshBasicMaterial({ color, transparent: true }));
    gem.position.set(x, y, 0);
    if (note.fret === 0 && !note.dead) gem.scale.set(high - low + 1.2, 0.55, 1);
    const glow = new THREE.Sprite(new THREE.SpriteMaterial({
      map: glowMap(), color, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    }));
    glow.scale.set(note.fret === 0 ? high - low + 3 : 2, 1.2, 1);
    glow.position.set(x, y, 0.1);
    const text = new THREE.Sprite(labelMaterial(note.dead ? "X" : String(note.fret), false, "#ffffff").clone());
    text.scale.set(0.55, 0.55, 1);
    text.position.set(x, y + 0.02, 0.3);
    addEffect([glow, gem, text], note.tick + Math.max(note.length, TICKS_PER_QUARTER / 2));
  }

  function spawnChordHit(chord) {
    const frame = new THREE.LineSegments(chord.frame, new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true }));
    frame.position.set(chord.x, (song.top + song.bottom) / 2, 0.02);
    frame.scale.set(1.04, 1.04, 1);
    const glow = new THREE.Sprite(new THREE.SpriteMaterial({
      map: glowMap(), color: 0xffffff, transparent: true, opacity: 0.35, depthWrite: false, blending: THREE.AdditiveBlending,
    }));
    glow.scale.set(chord.high - chord.low + 3, song.top - song.bottom + 1.5, 1);
    glow.position.set(chord.x, (song.top + song.bottom) / 2, 0.05);
    addEffect([frame, glow], chord.tick + TICKS_PER_QUARTER / 2);
  }

  function updateEffects(tick) {
    const now = performance.now();
    stage.effects = stage.effects.filter((effect) => {
      let opacity = 0.75 + 0.25 * Math.sin(now / 90); // gentle pulse while the note rings
      if (tick >= effect.until) {
        if (!effect.fadeStart) effect.fadeStart = now;
        opacity = 1 - (now - effect.fadeStart) / FADE_MS;
      }
      if (opacity <= 0) {
        for (const part of effect.parts) {
          stage.scene.remove(part);
          part.material.dispose(); // own materials; geometries and textures are shared
        }
        return false;
      }
      for (const part of effect.parts) {
        const base = part.material.userData.base ?? (part.material.userData.base = part.material.opacity);
        part.material.opacity = base * Math.min(1, opacity);
      }
      return true;
    });
  }

  function clearEffects() {
    if (!stage) return;
    for (const effect of stage.effects) {
      for (const part of effect.parts) {
        stage.scene.remove(part);
        part.material.dispose();
      }
    }
    stage.effects = [];
  }

  function currentTick() {
    if (!clock.playing) return clock.tick;
    return clock.tick + (performance.now() - clock.time) * clock.rate;
  }

  // First index of `items` (sorted by tick) whose tick is not before `tick`.
  function indexOf(items, tick) {
    let low = 0;
    let high = items.length;
    while (low < high) {
      const mid = (low + high) >> 1;
      if (items[mid].tick < tick) low = mid + 1;
      else high = mid;
    }
    return low;
  }

  function indexAt(tick) {
    return indexOf(song.notes, tick);
  }

  function updateLyrics(tick, bar) {
    const hud = stage.hud;
    if (!song.lyrics.length) {
      if (hud.line !== -2) hud.lyrics.replaceChildren();
      hud.line = -2;
      return;
    }
    const line = Math.floor(bar / 2);
    const from = song.bars[line * 2] ? song.bars[line * 2].tick : 0;
    const to = song.bars[line * 2 + 2] ? song.bars[line * 2 + 2].tick : Infinity;
    const sung = indexOf(song.lyrics, tick + 1) - 1;
    if (line === hud.line && sung === hud.sung) return;
    hud.line = line;
    hud.sung = sung;
    const parts = [];
    song.lyrics.forEach((syllable, i) => {
      if (syllable.tick < from || syllable.tick >= to) return;
      const span = document.createElement("span");
      const joined = syllable.text.endsWith("-"); // "hap-" + "pened"
      span.textContent = joined ? syllable.text.slice(0, -1) : syllable.text;
      if (i === sung) span.className = "now";
      else if (i < sung) span.className = "sung";
      parts.push(span, document.createTextNode(joined ? "" : " "));
    });
    hud.lyrics.replaceChildren(...parts);
  }

  function updateHud(tick) {
    const hud = stage.hud;
    const bar = Math.max(0, indexOf(song.bars, tick + 1) - 1);
    if (bar !== hud.bar && song.bars.length) {
      hud.bar = bar;
      let section = "";
      for (let i = bar; i >= 0 && !section; i -= 1) section = song.bars[i].section;
      hud.position.textContent = `Compasso ${bar + 1} / ${song.bars.length}${section ? ` · ${section}` : ""}`;
    }
    updateLyrics(tick, bar);
    const percent = Math.round((1000 * Math.min(Math.max(tick, 0), song.endTick)) / song.endTick) / 10;
    if (percent !== hud.percent) {
      hud.percent = percent;
      hud.fill.style.width = `${percent}%`;
    }
  }

  function seekHits(tick) {
    if (!song) return;
    song.nextHit = indexAt(tick);
    song.nextChord = indexOf(song.chords, tick);
    clearEffects();
  }

  function frame() {
    if (!running) return;
    requestAnimationFrame(frame);
    if (!song) return;
    const tick = currentTick();
    song.lane.position.z = tick * Z_PER_TICK;

    // Notes reaching the strike line: light their string, keep their number there with a glow.
    while (song.nextHit < song.notes.length && song.notes[song.nextHit].tick <= tick) {
      const note = song.notes[song.nextHit];
      const bar = stage.strings[note.string];
      if (clock.playing) {
        if (bar) bar.glow = 1;
        spawnNoteHit(note, song.nextHit);
      }
      song.nextHit += 1;
    }
    while (song.nextChord < song.chords.length && song.chords[song.nextChord].tick <= tick) {
      if (clock.playing) spawnChordHit(song.chords[song.nextChord]);
      song.nextChord += 1;
    }
    updateEffects(tick);
    for (const bar of stage.strings) {
      if (!bar) continue;
      bar.glow *= 0.9;
      bar.material.emissiveIntensity = 0.25 + 1.5 * bar.glow;
    }

    // Camera and floor highlight follow the fret window of the upcoming notes.
    const index = Math.min(indexAt(tick), song.notes.length - 1);
    const { low, high } = song.anchors[index] || { low: 1, high: MIN_ANCHOR_WIDTH };
    const centre = (fretX(low) + fretX(high)) / 2;
    stage.cameraX += (centre - stage.cameraX) * 0.04;
    stage.anchor.scale.x = high - low + 1;
    stage.anchor.position.x += (centre - stage.anchor.position.x) * 0.15;
    const midY = stringY(Math.ceil(song.count / 2), song.count);
    // Tilt chosen by the user: low shows string heights (and bends rising) best, high shows further ahead.
    // Side angle: the camera moves sideways and keeps looking down the highway (diagonal view).
    stage.camera.position.set(stage.cameraX + 7 * side, midY + 0.8 + 5.2 * tilt, 7 + 2 * tilt - 1.5 * Math.abs(side));
    stage.camera.lookAt(stage.cameraX - 1.5 * side, midY - 2.6 * tilt, -20);
    updateHud(tick);
    stage.renderer.render(stage.scene, stage.camera);
  }

  // Show `trackIndex` of an alphaTab score inside `host`. Rejects when WebGL is unavailable.
  async function show(host, score, trackIndex) {
    await loadThree();
    if (!stage || stage.host !== host) stage = createStage(host);
    buildSong(score, trackIndex);
    if (!running) {
      running = true;
      requestAnimationFrame(frame);
    }
  }

  function hide() {
    running = false;
  }

  // Player position from alphaTab: `tick` now, `tempo` in BPM (already scaled by the playback speed).
  function setPosition(tick, tempo, isSeek) {
    clock.tick = tick;
    clock.time = performance.now();
    clock.rate = (tempo * TICKS_PER_QUARTER) / 60000;
    if (isSeek) seekHits(tick);
  }

  function setPlaying(playing) {
    clock.tick = currentTick();
    clock.time = performance.now();
    clock.playing = playing;
  }

  function setTilt(value) {
    tilt = Math.min(1, Math.max(0, value));
  }

  function setSide(value) {
    side = Math.min(1, Math.max(-1, value));
  }

  window.Highway3D = { show, hide, setPosition, setPlaying, setTilt, setSide };
})();
