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
    host.replaceChildren(renderer.domElement);

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
      const number = label(String(fret), 0.45);
      number.position.set(fretX(fret), 0.25, 1.6);
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

    return { host, renderer, scene, camera, observer, anchor, strings: [], cameraX: 5 };
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

    const top = stringY(1, count) + 0.2;
    const bottom = stringY(count, count) - 0.2;
    for (const chord of chords) {
      const width = chord.high - chord.low + 1;
      const frame = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(width, top - bottom, 0.02)), chordMaterial);
      frame.position.set((fretX(chord.low) + fretX(chord.high)) / 2, (top + bottom) / 2, -chord.tick * Z_PER_TICK);
      lane.add(frame);
      if (chord.brush) {
        const arrow = label(chord.brush, 0.7, true, "#ffd54f");
        arrow.position.set(fretX(chord.low) - 0.9, (top + bottom) / 2, -chord.tick * Z_PER_TICK);
        lane.add(arrow);
      }
    }

    stage.scene.add(lane);
    const materials = [...gemMaterials, ...unpickedMaterials, ...trailMaterials, deadMaterial, chordMaterial].filter(Boolean);
    song = { lane, notes, anchors, count, materials, nextHit: 0 };
    seekHits(currentTick());
  }

  function currentTick() {
    if (!clock.playing) return clock.tick;
    return clock.tick + (performance.now() - clock.time) * clock.rate;
  }

  function indexAt(tick) {
    let low = 0;
    let high = song.notes.length;
    while (low < high) {
      const mid = (low + high) >> 1;
      if (song.notes[mid].tick < tick) low = mid + 1;
      else high = mid;
    }
    return low;
  }

  function seekHits(tick) {
    if (song) song.nextHit = indexAt(tick);
  }

  function frame() {
    if (!running) return;
    requestAnimationFrame(frame);
    if (!song) return;
    const tick = currentTick();
    song.lane.position.z = tick * Z_PER_TICK;

    // Light the string of every note reaching the strike line.
    while (song.nextHit < song.notes.length && song.notes[song.nextHit].tick <= tick) {
      const bar = stage.strings[song.notes[song.nextHit].string];
      if (bar && clock.playing) bar.glow = 1;
      song.nextHit += 1;
    }
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
    // Fairly low, Rocksmith-like camera: string heights (and bends rising) stay readable.
    stage.camera.position.set(stage.cameraX, midY + 1.7, 7.5);
    stage.camera.lookAt(stage.cameraX, midY - 0.4, -20);
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

  window.Highway3D = { show, hide, setPosition, setPlaying };
})();
