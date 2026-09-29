// Rocksmith-style 3D note highway for one track. Drawn with three.js (vendored, loaded on first use)
// and driven by the alphaTab player position, so it follows the same audio, speed and seeking.
(() => {
  "use strict";

  const THREE_URL = "/vendor/three/three.module.js";
  const ROUNDED_BOX_URL = "/vendor/three/RoundedBoxGeometry.js";
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
  let RoundedBox = null;
  let loading = null;
  let stage = null; // renderer, scene, camera and the static parts of the highway
  let song = null; // the current track: notes, anchors and the moving lane
  const clock = { tick: 0, time: 0, rate: 0, playing: false };
  let running = false;
  let tilt = 0.5; // 0 = eye level with the strings … 1 = steep … 1.5 = straight from above
  const MAX_TILT = 1.5;
  // Straight-down view (tilt 1.5): the time axis without perspective, from the strike line (at
  // the bottom) to more than one 4/4 bar ahead, to line up the notes with the audio drawn on the floor.
  const TOP_HEIGHT = 20;
  const TOP_Z = -8;
  const cameraPosition = { x: 0, y: 0, z: 0 };
  const cameraTarget = { x: 0, y: 0, z: 0 };
  let side = 0; // -1 = from the left … 1 = from the right (diagonal view)

  function loadThree() {
    if (THREE) return Promise.resolve(THREE);
    if (!loading) {
      loading = Promise.all([import(THREE_URL), import(ROUNDED_BOX_URL)]).then(([module, rounded]) => {
        THREE = module;
        RoundedBox = rounded.RoundedBoxGeometry;
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

  // Shared geometries (kept across tracks, never disposed with a song).
  function shared(geometry) {
    geometry.userData.shared = true;
    return geometry;
  }

  const roundedCache = new Map();
  // Box with rounded edges, shared by size (gems, open-string bars and their hit copies).
  function roundedBox(width, height, depth, radius) {
    const key = [width, height, depth, radius].map((value) => value.toFixed(2)).join(":");
    if (!roundedCache.has(key)) roundedCache.set(key, shared(new RoundedBox(width, height, depth, 4, radius)));
    return roundedCache.get(key);
  }

  // Fret number printed on the front face of a gem (a sprite would cut through the gem when the
  // camera is tilted). Clipped decals are shared; unclipped ones are copies the caller may fade.
  let decalPlane = null;
  const decalCache = new Map();
  function faceLabel(text, height, clipped = true) {
    if (!decalPlane) decalPlane = shared(new THREE.PlaneGeometry(1, 1));
    let material = decalCache.get(text);
    if (!material) {
      material = new THREE.MeshBasicMaterial({
        map: labelMaterial(text, false, "#ffffff").map,
        transparent: true,
        depthWrite: false,
        polygonOffset: true,
        polygonOffsetFactor: -2,
        polygonOffsetUnits: -2,
        clippingPlanes: laneClip(),
      });
      decalCache.set(text, material);
    }
    if (!clipped) {
      material = material.clone();
      material.clippingPlanes = null;
    }
    const mesh = new THREE.Mesh(decalPlane, material);
    mesh.scale.set((height * material.map.image.width) / 128, height, 1);
    return mesh;
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
    progress.title = "Clique para avançar ou recuar";
    progress.addEventListener("pointerdown", (event) => {
      const box = progress.getBoundingClientRect();
      if (box.width > 0) onSeek(Math.min(Math.max((event.clientX - box.left) / box.width, 0), 1));
    });
    const time = document.createElement("span");
    time.className = "hw-time";
    hud.append(position, progress, time);
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

    const camera = new THREE.PerspectiveCamera(55, 16 / 9, 0.1, far + 20 + TOP_HEIGHT);
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

    return { host, renderer, scene, camera, observer, anchor, strings: [], cameraX: 5, fogNear: far * 0.55, fogFar: far, hud: { position, fill, time, bar: -1, percent: -1, lyrics: lyricsLine, line: -1, sung: -2 }, effects: [], headstock: null };
  }

  // Headstock at the left of the strings: wooden head with a rounded tip, a bone nut where the
  // neck starts, a tuning peg per string (the strings run from it) and the open-string note name
  // beside each peg in the string colour ("E A D G B e"). Local x: nut at 0, pegs and names left.
  const PEG_X = -0.6;
  const NAME_X = -1.15;

  function buildHeadstock(tuning, count) {
    if (stage.headstock) {
      stage.scene.remove(stage.headstock);
      stage.headstock.traverse((object) => {
        if (object.isSprite) return; // label materials are cached
        if (object.geometry) object.geometry.dispose();
        if (object.material) object.material.dispose();
      });
    }
    const group = new THREE.Group();
    const top = stringY(1, count) + 0.35;
    const bottom = stringY(count, count) - 0.35;
    const middle = (top + bottom) / 2;

    const outline = new THREE.Shape();
    outline.moveTo(0.05, bottom);
    outline.lineTo(-1.35, bottom - 0.12);
    outline.quadraticCurveTo(-1.95, middle, -1.35, top + 0.12);
    outline.lineTo(0.05, top);
    outline.closePath();
    const head = new THREE.Mesh(
      new THREE.ExtrudeGeometry(outline, { depth: 0.08, bevelEnabled: true, bevelThickness: 0.03, bevelSize: 0.03, bevelSegments: 3 }),
      new THREE.MeshStandardMaterial({ color: 0x3a2618, roughness: 0.55, metalness: 0.05 }),
    );
    head.position.z = -0.2;
    group.add(head);

    const nut = new THREE.Mesh(
      roundedBox(0.1, top - bottom - 0.2, 0.14, 0.03).clone(),
      new THREE.MeshStandardMaterial({ color: 0xe9e2cc, roughness: 0.4 }),
    );
    nut.position.set(0, middle, -0.05);
    group.add(nut);

    const pegGeometry = new THREE.CylinderGeometry(0.12, 0.12, 0.08, 24);
    pegGeometry.rotateX(Math.PI / 2); // face the camera
    const pegMaterial = new THREE.MeshStandardMaterial({ color: 0xc9ccd2, metalness: 0.85, roughness: 0.3 });
    const names = [];
    for (let string = 1; string <= count; string += 1) {
      const midi = tuning[count - string]; // alphaTab lists the tuning from the top (highest) string
      names[string] = midi === undefined ? "" : NOTE_NAMES[((midi % 12) + 12) % 12];
    }
    if (count > 1 && names[1] && names[1] === names[count]) names[count] = names[count].toLowerCase();
    for (let string = 1; string <= count; string += 1) {
      const y = stringY(string, count);
      const peg = new THREE.Mesh(pegGeometry, pegMaterial);
      peg.position.set(PEG_X, y, -0.08);
      group.add(peg);
      if (!names[string]) continue;
      const color = `#${stringColor(string, count).toString(16).padStart(6, "0")}`;
      const name = label(names[string], 0.4, false, color);
      name.position.set(NAME_X, y, 0.02);
      group.add(name);
    }
    group.position.x = 0; // nut on fret wire 0, like on a guitar
    stage.scene.add(group);
    stage.headstock = group;
    // The strings run from the pegs to the end of the neck.
    const length = FRETS + 0.5 - PEG_X;
    for (const bar of stage.strings) {
      if (!bar) continue;
      bar.mesh.scale.x = length / (FRETS + 1);
      bar.mesh.position.x = PEG_X + length / 2;
    }
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

  // Lyric syllables of the song. Preferably the complete lyrics as printed in the PDF, each with
  // its bar and place in the bar ([bar, position 0..1, syllable, joins_next]); otherwise the GP5
  // lyrics, which Guitar Pro can only attach to played notes of one track.
  function collectLyrics(score, timed, timeline) {
    if (Array.isArray(timed) && timed.length) {
      const placed = [];
      for (const [bar, position, text, joins] of timed) {
        const masterBar = score.masterBars[bar - 1];
        if (!masterBar || typeof text !== "string") continue;
        const tick = masterBar.start + Number(position) * barLength(masterBar);
        placed.push({ tick, text: joins ? `${text}-` : text });
      }
      return timeline.unroll(placed).sort((a, b) => a.tick - b.tick);
    }
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
    return timeline.unroll(syllables).sort((a, b) => a.tick - b.tick);
  }

  function barLength(masterBar) {
    return (TICKS_PER_QUARTER * 4 * masterBar.timeSignatureNumerator) / masterBar.timeSignatureDenominator;
  }

  const MAX_PLAYED_BARS = 20000;

  // The bars in the order they are played, with repeats and voltas unrolled as alphaTab plays
  // them, each with its start in playback ticks (the player reports positions in these ticks).
  // alphaTab's Direction values (model.Direction) for D.C. / D.S. / Coda / Fine.
  const DIRECTION = {
    fine: 0, segno: 1, coda: 3, daCapo: 5, daCapoAlCoda: 6, daCapoAlFine: 8,
    dalSegno: 9, dalSegnoAlCoda: 10, dalSegnoAlFine: 12, toCoda: 17,
  };
  const JUMPS = new Map([
    [DIRECTION.daCapo, { toSegno: false, until: "" }],
    [DIRECTION.daCapoAlCoda, { toSegno: false, until: "coda" }],
    [DIRECTION.daCapoAlFine, { toSegno: false, until: "fine" }],
    [DIRECTION.dalSegno, { toSegno: true, until: "" }],
    [DIRECTION.dalSegnoAlCoda, { toSegno: true, until: "coda" }],
    [DIRECTION.dalSegnoAlFine, { toSegno: true, until: "fine" }],
  ]);
  const has = (bar, direction) => Boolean(bar.directions && bar.directions.has(direction));

  // The bars in the order they are played, as alphaTab plays them (the same rules as the server's
  // app/repeats.py): a repeat end without a start goes back to the song's start; repeats can nest,
  // and a repeat inside a repeated passage is played again on every pass; a D.C. / D.S. jump is
  // taken once (a D.S. without a Segno is ignored); after it repeats and voltas no longer count,
  // "To Coda" goes to the Coda and "Fine" ends the song.
  function playbackOrder(masterBars) {
    const order = [];
    const jumps = masterBars.map(() => 0); // times each repeat end has sent playback back
    const starts = [0]; // open repeats: the bar each goes back to (innermost last)
    const segno = masterBars.findIndex((bar) => has(bar, DIRECTION.segno));
    const coda = masterBars.findIndex((bar) => has(bar, DIRECTION.coda));
    let jumped = null; // the D.C. / D.S. jump taken
    let tick = 0;
    let pass = 0; // 0 the first time through a repeat, 1 the second… (chooses the volta)
    for (let i = 0, guard = 0; i < masterBars.length && guard < MAX_PLAYED_BARS; guard += 1) {
      const bar = masterBars[i];
      if (!jumped) {
        if (bar.isRepeatStart && i !== starts[starts.length - 1]) {
          starts.push(i);
          pass = 0;
        }
        if (bar.alternateEndings !== 0 && (bar.alternateEndings & (1 << pass)) === 0) {
          i += 1; // a volta for another pass
          continue;
        }
      }
      order.push({ masterBar: bar, tick });
      tick += barLength(bar);
      if (!jumped && bar.repeatCount > 1) {
        if (jumps[i] < bar.repeatCount - 1) {
          jumps[i] += 1;
          pass = jumps[i];
          i = starts[starts.length - 1];
          continue;
        }
        jumps[i] = 0;
        pass = 0;
        if (starts.length > 1) starts.pop();
      }
      if (jumped) {
        if (jumped.until === "fine" && has(bar, DIRECTION.fine)) break;
        if (jumped.until === "coda" && has(bar, DIRECTION.toCoda) && coda >= 0) {
          i = coda;
          continue;
        }
      } else {
        const jump = [...JUMPS].find(([direction, kind]) => has(bar, direction) && (!kind.toSegno || segno >= 0));
        if (jump) {
          jumped = jump[1];
          i = jumped.toSegno ? segno : 0;
          continue;
        }
      }
      i += 1;
    }
    return order;
  }

  // Maps things placed in score time (ticks from alphaTab's score model) to playback time: an
  // item in a repeated bar appears once per time the bar is played.
  function makeTimeline(score) {
    const masterBars = score.masterBars;
    const order = playbackOrder(masterBars);
    const offsets = masterBars.map(() => []);
    for (const { masterBar, tick } of order) offsets[masterBar.index].push(tick - masterBar.start);
    const linear = order.length === masterBars.length && offsets.every((list) => list.length === 1 && list[0] === 0);
    const last = order[order.length - 1];
    // Playback time (ms, at the printed tempo) of each played bar, for placing the song's audio.
    const tempoMap = [];
    let tempo = score.tempo || 120;
    let ms = 0;
    for (const { masterBar, tick } of order) {
      const automations = masterBar.tempoAutomations || [];
      for (const automation of automations) if (automation.ratioPosition <= 0.001) tempo = automation.value;
      tempoMap.push({ tick, ms, tempo });
      ms += ((barLength(masterBar) / TICKS_PER_QUARTER) * 60000) / tempo;
      for (const automation of automations) if (automation.ratioPosition > 0.001) tempo = automation.value;
    }
    const barOf = (tick) => {
      let low = 0;
      let high = masterBars.length - 1;
      while (low < high) {
        const mid = (low + high + 1) >> 1;
        if (masterBars[mid].start <= tick) low = mid;
        else high = mid - 1;
      }
      return low;
    };
    return {
      order,
      endTick: last ? last.tick + barLength(last.masterBar) : 1,
      // Playback tick at `time` ms from bar 1 (before bar 1 and after the end: at the nearest tempo).
      msToTick(time) {
        if (!tempoMap.length) return 0;
        let low = 0;
        let high = tempoMap.length - 1;
        while (low < high) {
          const mid = (low + high + 1) >> 1;
          if (tempoMap[mid].ms <= time) low = mid;
          else high = mid - 1;
        }
        const entry = tempoMap[low];
        return entry.tick + ((time - entry.ms) * entry.tempo * TICKS_PER_QUARTER) / 60000;
      },
      // Copies of `items` ({ tick, … }) for every time their bar is played; `shift(item, offset)`
      // moves an item's other ticks too.
      unroll(items, shift = (item, offset) => ({ ...item, tick: item.tick + offset })) {
        if (linear) return items;
        return items.flatMap((item) => (masterBars.length ? offsets[barOf(item.tick)] : [0]).map((offset) => shift(item, offset)));
      },
    };
  }

  function shiftNote(note, offset) {
    return {
      ...note,
      tick: note.tick + offset,
      bendCurve: note.bendCurve && note.bendCurve.map((point) => ({ tick: point.tick + offset, value: point.value })),
      slideTo: note.slideTo && { ...note.slideTo, tick: note.slideTo.tick + offset },
    };
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
              // What is played, to spot the same chord struck again (drawn as a frame only).
              shape: struck.map((note) => `${note.string}:${note.isDead ? "x" : note.fret}`).sort().join(","),
              palmMute: struck.some((note) => note.isPalmMute),
            });
          }
        }
      }
    }
    notes.sort((a, b) => a.tick - b.tick);
    return { notes, chords };
  }

  // Frets spanned by the fretted notes struck together with each note (1 when alone or open).
  function chordSpans(notes) {
    const spans = new Array(notes.length).fill(1);
    for (let first = 0; first < notes.length; ) {
      let last = first;
      while (last + 1 < notes.length && notes[last + 1].tick === notes[first].tick) last += 1;
      const frets = notes.slice(first, last + 1).filter((n) => n.fret > 0 && !n.dead).map((n) => n.fret);
      const span = frets.length ? Math.max(...frets) - Math.min(...frets) + 1 : 1;
      spans.fill(span, first, last + 1);
      first = last + 1;
    }
    return spans;
  }

  // For each note: the fret window [low, high] played around it (open strings ignored), and
  // `open`, the width of an open-string bar there: as wide as the widest hand position in the
  // window (at least MIN_ANCHOR_WIDTH), never wider than the window. The window itself spans
  // the notes of several beats, so it is often wider than any one hand position.
  function computeAnchors(notes) {
    let previous = { low: 1, high: MIN_ANCHOR_WIDTH, open: MIN_ANCHOR_WIDTH };
    const spans = chordSpans(notes);
    let start = 0;
    return notes.map((note) => {
      while (notes[start].tick < note.tick - ANCHOR_BEFORE) start += 1;
      let low = Infinity;
      let high = -Infinity;
      let widest = 1;
      for (let i = start; i < notes.length && notes[i].tick <= note.tick + ANCHOR_AFTER; i += 1) {
        if (notes[i].fret > 0 && !notes[i].dead) {
          low = Math.min(low, notes[i].fret);
          high = Math.max(high, notes[i].fret);
          widest = Math.max(widest, spans[i]);
        }
      }
      if (low === Infinity) return previous;
      if (high - low + 1 < MIN_ANCHOR_WIDTH) high = Math.min(FRETS, low + MIN_ANCHOR_WIDTH - 1);
      previous = { low, high, open: Math.min(high - low + 1, Math.max(MIN_ANCHOR_WIDTH, widest)) };
      return previous;
    });
  }

  // Free the GPU resources of the previous track (label materials are shared and kept).
  function disposeSong() {
    if (!song) return;
    clearEffects(); // effects share the chord frame geometry disposed below
    stage.scene.remove(song.lane);
    song.lane.traverse((object) => {
      // Sprites share one geometry; rounded boxes and decal planes are shared too.
      if (object.geometry && !object.isSprite && !object.geometry.userData.shared) object.geometry.dispose();
    });
    for (const material of song.materials) material.dispose();
    song = null;
  }

  function buildSong(score, trackIndex, timedLyrics) {
    disposeSong();
    const track = score.tracks[trackIndex];
    const count = track.staves[0].tuning.length;
    buildStrings(count);
    buildHeadstock(track.staves[0].tuning, count);
    const timeline = makeTimeline(score);
    const collected = collectNotes(track);
    const notes = timeline.unroll(collected.notes, shiftNote).sort((a, b) => a.tick - b.tick);
    const chords = timeline.unroll(collected.chords).sort((a, b) => a.tick - b.tick);
    const anchors = computeAnchors(notes);
    const lane = new THREE.Group();

    // Chord frames: at least 2 frets wide. A chord struck again right after the same chord (no
    // other note between, within a bar) is a repeat: only its frame is drawn (Rocksmith style).
    const chordAt = new Map();
    let previousChord = null;
    for (const chord of chords) {
      if (chord.high - chord.low < 1) {
        if (chord.high < FRETS) chord.high += 1;
        else chord.low -= 1;
      }
      chord.width = chord.high - chord.low + 1;
      chord.x = (fretX(chord.low) + fretX(chord.high)) / 2;
      chord.repeat = Boolean(
        previousChord &&
          previousChord.shape === chord.shape &&
          chord.tick - previousChord.tick <= 4 * TICKS_PER_QUARTER &&
          indexOf(notes, previousChord.tick + 1) === indexOf(notes, chord.tick),
      );
      chordAt.set(chord.tick, chord);
      previousChord = chord;
    }

    const gem = roundedBox(0.8, 0.28, 0.28, 0.09);
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
      const chord = chordAt.get(note.tick);
      const open = note.fret === 0 && !note.dead;
      if (open) {
        // Open string: a bar across the chord it belongs to, else across the fret window played.
        const { low, high } = anchors[i];
        note.openWidth = chord ? chord.width : anchors[i].open;
        note.openX = chord ? chord.x : (fretX(low) + fretX(high)) / 2;
      }
      note.parts = [];
      if (chord && chord.repeat) return; // the frame stands for it (the notes still light up when played)
      let x;
      let body;
      let front; // distance from the gem centre to its front face
      if (open) {
        body = new THREE.Mesh(roundedBox(note.openWidth, 0.18, 0.22, 0.07), material);
        x = note.openX;
        front = 0.11;
      } else {
        x = fretX(note.fret);
        const harmonic = note.harmonic && !note.dead;
        body = new THREE.Mesh(harmonic ? diamond : gem, material);
        front = harmonic ? 0.22 : 0.14;
      }
      body.position.set(x, y, z);
      const fretText = note.dead ? "X" : note.ghost ? `(${note.fret})` : String(note.fret);
      lane.add(body);
      note.parts = [body]; // hidden when the note reaches the strings (a glowing copy takes over)
      if (!(open && chord)) {
        // In a chord the open strings are the bars inside its frame: no "0" to read.
        const text = faceLabel(fretText, open ? 0.3 : 0.36);
        text.position.set(x, y, z + front + 0.005);
        lane.add(text);
        note.parts.push(text);
      }

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
    for (const { masterBar, tick: barStart } of timeline.order) {
      const beatTicks = (TICKS_PER_QUARTER * 4) / masterBar.timeSignatureDenominator;
      for (let beat = 0; beat < masterBar.timeSignatureNumerator; beat += 1) {
        const line = new THREE.Mesh(unit, beat ? beatMaterial : barMaterial);
        line.scale.set(FRETS + 1, beat ? 0.01 : 0.02, beat ? 0.03 : 0.08);
        line.position.set((FRETS - 1) / 2, 0.03, -(barStart + beat * beatTicks) * Z_PER_TICK);
        lane.add(line);
      }
      const section = masterBar.section && masterBar.section.text ? masterBar.section.text : "";
      bars.push({ tick: barStart, section, number: masterBar.index + 1 });
      const nearest = Math.min(indexOf(notes, barStart), notes.length - 1);
      const zone = anchors[nearest] || { low: 1, high: MIN_ANCHOR_WIDTH };
      const x = fretX(zone.low) - 1.3;
      const z = -barStart * Z_PER_TICK;
      const number = label(String(masterBar.index + 1), 0.5, true, "#cfd8e3");
      number.position.set(x, 0.35, z);
      lane.add(number);
      if (section) {
        const name = label(section, 0.55, true, "#ffd54f");
        name.position.set(x, stringY(1, count) + 0.7, z);
        lane.add(name);
      }
    }
    const endTick = timeline.endTick;

    const top = stringY(1, count) + 0.2;
    const bottom = stringY(count, count) - 0.2;
    let lastName = "";
    let lastTick = -Infinity;
    const repeatMaterial = new THREE.MeshBasicMaterial({
      color: 0xffffff, transparent: true, opacity: 0.1, depthWrite: false, side: THREE.DoubleSide, clippingPlanes: laneClip(),
    });
    for (const chord of chords) {
      chord.frame = new THREE.EdgesGeometry(new THREE.BoxGeometry(chord.width, top - bottom, 0.02));
      const frame = new THREE.LineSegments(chord.frame, chordMaterial);
      frame.position.set(chord.x, (top + bottom) / 2, -chord.tick * Z_PER_TICK);
      lane.add(frame);
      if (chord.repeat) {
        // Same chord again: a see-through panel in the frame instead of its notes.
        const panel = new THREE.Mesh(unit, repeatMaterial);
        panel.scale.set(chord.width, top - bottom, 0.01);
        panel.position.copy(frame.position);
        lane.add(panel);
        if (chord.palmMute) tag("PM", chord.x, top + 0.3, -chord.tick * Z_PER_TICK, "#e6edf3");
      }
      // Chord name on top, when it changes (or comes back after more than a bar).
      if (chord.name && (chord.name !== lastName || chord.tick - lastTick > 4 * TICKS_PER_QUARTER)) {
        const name = label(chord.name, 0.6, true, "#ffffff");
        name.position.set(chord.x, top + 1.1, -chord.tick * Z_PER_TICK); // well above the notes
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
      ...gemMaterials, ...unpickedMaterials, ...trailMaterials, deadMaterial, chordMaterial, repeatMaterial, barMaterial, beatMaterial,
    ].filter(Boolean);
    clearEffects();
    song = {
      lane, notes, anchors, count, materials, bars, endTick, chords, top, bottom, barCount: score.masterBars.length,
      msToTick: timeline.msToTick, waveMesh: null,
      lyrics: collectLyrics(score, timedLyrics, timeline), nextHit: 0, nextChord: 0,
    };
    stage.hud.bar = -1;
    stage.hud.line = -1;
    drawWaveform();
    seekHits(currentTick());
  }

  // The song's audio drawn on the floor of the highway (loudness along time), placed with the same
  // start and tempo as the audio playback, so its beats can be lined up with the notes.
  let wave = null; // { peaks: Float32Array (0…1), step: seconds per peak }
  const waveSync = { offset: 0, factor: 1 }; // bar 1 in the audio (s); score tempo ÷ printed tempo
  let waveMaterial = null;
  const WAVE_Y = 0.012; // just above the floor, under the bar lines

  function drawWaveform() {
    if (!song) return;
    if (song.waveMesh) {
      song.lane.remove(song.waveMesh);
      song.waveMesh.geometry.dispose();
      song.waveMesh = null;
    }
    if (!wave) return;
    const count = wave.peaks.length;
    const positions = new Float32Array(count * 6);
    const center = (FRETS - 1) / 2;
    const half = ((FRETS + 1) / 2) * 0.9;
    for (let i = 0; i < count; i += 1) {
      const scoreMs = (i * wave.step - waveSync.offset) * waveSync.factor * 1000;
      const z = -song.msToTick(scoreMs) * Z_PER_TICK;
      const amplitude = Math.max(0.02, wave.peaks[i]) * half;
      positions.set([center - amplitude, WAVE_Y, z, center + amplitude, WAVE_Y, z], i * 6);
    }
    const indices = [];
    for (let i = 0; i + 1 < count; i += 1) {
      const a = 2 * i;
      indices.push(a, a + 1, a + 2, a + 1, a + 3, a + 2);
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    geometry.setIndex(indices);
    if (!waveMaterial) {
      waveMaterial = new THREE.MeshBasicMaterial({
        color: 0x38bdf8, transparent: true, opacity: 0.22, depthWrite: false, side: THREE.DoubleSide, clippingPlanes: laneClip(),
      });
    }
    song.waveMesh = new THREE.Mesh(geometry, waveMaterial);
    song.waveMesh.renderOrder = -1;
    song.lane.add(song.waveMesh);
  }

  // `data`: { peaks, step } of the chosen audio, or null to remove it.
  function setWaveform(data) {
    wave = data && data.peaks && data.peaks.length > 1 ? data : null;
    drawWaveform();
  }

  function setWaveformSync(offset, factor) {
    waveSync.offset = Number(offset) || 0;
    waveSync.factor = factor > 0 ? factor : 1;
    drawWaveform();
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

  function addEffect(parts, until, bendCurve = null) {
    for (const part of parts) stage.scene.add(part);
    const baseY = parts.map((part) => part.position.y);
    stage.effects.push({ parts, until, fadeStart: 0, bendCurve, baseY });
  }

  // Bend height (quarter tones) at `tick` along a bend curve, linear between its points.
  function bendValueAt(curve, tick) {
    if (tick <= curve[0].tick) return curve[0].value;
    for (let i = 1; i < curve.length; i += 1) {
      const b = curve[i];
      if (tick <= b.tick) {
        const a = curve[i - 1];
        const span = b.tick - a.tick;
        return span > 0 ? a.value + ((b.value - a.value) * (tick - a.tick)) / span : b.value;
      }
    }
    return curve[curve.length - 1].value;
  }

  function spawnNoteHit(note, index) {
    const color = stringColor(note.string, song.count);
    const y = stringY(note.string, song.count);
    const anchor = song.anchors[index] || { low: 1, high: MIN_ANCHOR_WIDTH, open: MIN_ANCHOR_WIDTH };
    const open = note.fret === 0 && !note.dead;
    const openWidth = note.openWidth || anchor.open;
    const x = open ? note.openX ?? (fretX(anchor.low) + fretX(anchor.high)) / 2 : fretX(note.fret);
    const shape = open ? roundedBox(openWidth + 0.2, 0.2, 0.26, 0.08) : roundedBox(0.86, 0.3, 0.3, 0.1);
    // Opaque while the note rings: a see-through box shows its own back faces and the trail inside.
    const gem = new THREE.Mesh(shape, new THREE.MeshBasicMaterial({ color }));
    gem.material.userData.solid = true;
    gem.position.set(x, y, 0);
    const glow = new THREE.Sprite(new THREE.SpriteMaterial({
      // Soft halo; normal blending so the halos of a chord do not add up to white.
      map: glowMap(), color, transparent: true, opacity: 0.6, depthWrite: false,
    }));
    glow.scale.set(open ? openWidth + 1.2 : 1.8, 1, 1);
    glow.position.set(x, y, 0.1);
    const text = faceLabel(note.dead ? "X" : String(note.fret), open ? 0.34 : 0.42, false);
    text.position.set(x, y, open ? 0.14 : 0.16);
    addEffect([glow, gem, text], note.tick + Math.max(note.length, TICKS_PER_QUARTER / 2), note.bendCurve);
  }

  function spawnChordHit(chord) {
    const frame = new THREE.LineSegments(chord.frame, new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true }));
    frame.position.set(chord.x, (song.top + song.bottom) / 2, 0.02);
    frame.scale.set(1.04, 1.04, 1);
    const glow = new THREE.Sprite(new THREE.SpriteMaterial({
      map: glowMap(), color: 0xffffff, transparent: true, opacity: 0.18, depthWrite: false,
    }));
    glow.scale.set(chord.high - chord.low + 2, song.top - song.bottom + 0.8, 1);
    glow.position.set(chord.x, (song.top + song.bottom) / 2, 0.05);
    addEffect([frame, glow], chord.tick + TICKS_PER_QUARTER / 2);
  }

  function updateEffects(tick) {
    const now = performance.now();
    stage.effects = stage.effects.filter((effect) => {
      let opacity = 0.75 + 0.25 * Math.sin(now / 90); // gentle pulse (glow and frames) while the note rings
      if (tick >= effect.until) {
        if (!effect.fadeStart) {
          effect.fadeStart = now;
          for (const part of effect.parts) {
            if (!part.material.userData.solid) continue;
            part.material.transparent = true; // only now, to fade out
            part.material.needsUpdate = true;
          }
        }
        opacity = 1 - (now - effect.fadeStart) / FADE_MS;
      }
      if (opacity <= 0) {
        for (const part of effect.parts) {
          stage.scene.remove(part);
          part.material.dispose(); // own materials; geometries and textures are shared
        }
        return false;
      }
      // A bent note rises (and comes back on release) in real time while it rings.
      const rise = effect.bendCurve && !effect.fadeStart ? bendValueAt(effect.bendCurve, tick) * BEND_RISE : null;
      effect.parts.forEach((part, i) => {
        const base = part.material.userData.base ?? (part.material.userData.base = part.material.opacity);
        const solid = part.material.userData.solid && !effect.fadeStart;
        part.material.opacity = solid ? 1 : base * Math.min(1, opacity);
        if (rise !== null) part.position.y = effect.baseY[i] + rise;
      });
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
      hud.position.textContent = `Compasso ${song.bars[bar].number} / ${song.barCount}${section ? ` · ${section}` : ""}`;
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
    song.notes.forEach((note, i) => {
      for (const part of note.parts) part.visible = i >= song.nextHit;
    });
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
        for (const part of note.parts) part.visible = false;
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
      bar.material.emissiveIntensity = 0.25 + 1.1 * bar.glow;
    }

    // Camera and floor highlight follow the fret window of the upcoming notes.
    const index = Math.min(indexAt(tick), song.notes.length - 1);
    const { low, high } = song.anchors[index] || { low: 1, high: MIN_ANCHOR_WIDTH };
    const centre = (fretX(low) + fretX(high)) / 2;
    stage.cameraX += (centre - stage.cameraX) * 0.04;
    stage.anchor.scale.x = high - low + 1;
    stage.anchor.position.x += (centre - stage.anchor.position.x) * 0.15;
    // Tuning names stay just left of the fret window being played.
    const midY = stringY(Math.ceil(song.count / 2), song.count);
    // Tilt chosen by the user: low shows string heights (and bends rising) best, high shows further
    // ahead; past 1 it turns towards a view from straight above (no side angle there).
    // Side angle: the camera moves sideways and keeps looking down the highway (diagonal view).
    const steep = Math.min(tilt, 1);
    const top = Math.min(1, Math.max(0, (tilt - 1) / (MAX_TILT - 1)));
    const sideways = side * (1 - top);
    const blend = (a, b) => a + (b - a) * top;
    cameraPosition.x = stage.cameraX + 7 * sideways;
    cameraPosition.y = blend(midY + 0.8 + 5.2 * steep, TOP_HEIGHT);
    cameraPosition.z = blend(7 + 2 * steep - 1.5 * Math.abs(sideways), TOP_Z);
    cameraTarget.x = stage.cameraX - 1.5 * sideways;
    cameraTarget.y = blend(midY - 2.6 * steep, 0);
    cameraTarget.z = blend(-20, TOP_Z - 0.01);
    stage.camera.up.set(0, 1 - top, -top).normalize(); // from above: upcoming notes at the top
    stage.camera.position.set(cameraPosition.x, cameraPosition.y, cameraPosition.z);
    stage.camera.lookAt(cameraTarget.x, cameraTarget.y, cameraTarget.z);
    stage.scene.fog.near = blend(stage.fogNear, stage.fogNear + TOP_HEIGHT);
    stage.scene.fog.far = blend(stage.fogFar, stage.fogFar + TOP_HEIGHT);
    updateHud(tick);
    stage.renderer.render(stage.scene, stage.camera);
  }

  // Show `trackIndex` of an alphaTab score inside `host` (with the PDF's timed lyrics, if any).
  // Rejects when WebGL is unavailable.
  async function show(host, score, trackIndex, timedLyrics = null) {
    await loadThree();
    if (!stage || stage.host !== host) stage = createStage(host);
    buildSong(score, trackIndex, timedLyrics);
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
    tilt = Math.min(MAX_TILT, Math.max(0, value));
  }

  function setSide(value) {
    side = Math.min(1, Math.max(-1, value));
  }

  // Song time shown beside the progress bar ("0:42 / 3:51"), and who handles a click on the bar
  // (`fraction` 0…1 of the song).
  let onSeek = () => {};

  function setTime(text) {
    if (stage && stage.hud.time.textContent !== text) stage.hud.time.textContent = text;
  }

  function setSeekHandler(handler) {
    onSeek = handler;
  }

  window.Highway3D = {
    show, hide, setPosition, setPlaying, setTilt, setSide, setTime, setSeekHandler, setWaveform, setWaveformSync,
  };
})();
