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
  const TREMOLO_STEP = 0.25; // highway length of one stroke of a tremolo picking zigzag
  const SLIDE_IN_RUN = 1.2; // highway length of a slide into a note from nowhere
  const SLIDE_BLEND = 0.25; // share of a slide's length its curved ends take…
  const SLIDE_BLEND_MAX = 0.6; // …at most this long on the highway (a small curve)
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
  // A note comes tilted NOTE_ROLL_DEG (its right side up) and, over its last NOTE_ROLL_S of the
  // song before the strings, turns clockwise at a constant rate to lie level as it strikes. A
  // chord turns as one piece, around its frame's centre. An open string (the bar across the hand's
  // frets) always lies level, and so does a chord with one.
  const NOTE_ROLL_DEG = 30;
  const NOTE_ROLL_S = 3;
  const noteRoll = (seconds) => (seconds <= 0 ? 0 : ((NOTE_ROLL_DEG * Math.PI) / 180) * Math.min(1, seconds / NOTE_ROLL_S));

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
  // Turned, moved and zoomed with the mouse over the highway: turns around the strings at the
  // strike line (yaw, pitch) and about the line of sight (roll), up to 60° each way (120° on each
  // axis); an offset across the screen (highway units); a lens zoom. A double click puts it back.
  const view = { x: 0, y: 0, zoom: 1, yaw: 0, pitch: 0, roll: 0 };
  const MAX_TURN = Math.PI / 3;
  const MIN_ZOOM = 0.5;
  const MAX_ZOOM = 4;

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

  // Rocksmith's notehead symbols (its "Notehead and tail guide"), drawn rather than written:
  // hammer-on ▼, pull-off ▲, harmonic (a ring with a dot), pinch harmonic (palm mute is a cross
  // inside the note: palmMuteCross)
  // (an eye), tap (a wide V), and a bend's strength as stacked chevrons (1 half step, 2 a whole
  // step, 3 more; one pointing down for a release).
  const ICONS = {
    hammer: (ctx) => { ctx.moveTo(24, 34); ctx.lineTo(104, 34); ctx.lineTo(64, 100); ctx.closePath(); },
    pull: (ctx) => { ctx.moveTo(24, 96); ctx.lineTo(104, 96); ctx.lineTo(64, 30); ctx.closePath(); },
    harmonic: (ctx) => { ring(ctx, 42); ring(ctx, 30); ring(ctx, 12); },
    pinch: (ctx) => {
      ctx.moveTo(10, 64); ctx.quadraticCurveTo(64, 6, 118, 64); ctx.quadraticCurveTo(64, 122, 10, 64); ctx.closePath();
      ring(ctx, 22); ring(ctx, 11);
    },
    tap: (ctx) => { ctx.moveTo(14, 36); ctx.lineTo(64, 100); ctx.lineTo(114, 36); ctx.lineTo(90, 36); ctx.lineTo(64, 70); ctx.lineTo(38, 36); ctx.closePath(); },
    // Slap: a block with a notch in its top; pop: a block with a peak (the string pulled up).
    slap: (ctx) => { ctx.moveTo(10, 44); ctx.lineTo(64, 74); ctx.lineTo(118, 44); ctx.lineTo(118, 96); ctx.lineTo(10, 96); ctx.closePath(); },
    pop: (ctx) => { ctx.moveTo(10, 72); ctx.lineTo(64, 36); ctx.lineTo(118, 72); ctx.lineTo(118, 96); ctx.lineTo(10, 96); ctx.closePath(); },
  };
  function ring(ctx, radius) {
    ctx.moveTo(64 + radius, 64);
    ctx.arc(64, 64, radius, 0, 2 * Math.PI);
  }
  // `count` chevrons stacked upwards (or one pointing down), 14 px thick.
  function chevrons(count, down) {
    return (ctx) => {
      const dir = down ? -1 : 1; // the tip is above the arms for up
      const start = down ? 57 : 104 - (3 - count) * 14; // centre the stack
      for (let i = 0; i < count; i += 1) {
        const arms = start - i * 28;
        const tip = arms - dir * 30;
        ctx.moveTo(24, arms); ctx.lineTo(64, tip); ctx.lineTo(104, arms);
        ctx.lineTo(104, arms + dir * 16); ctx.lineTo(64, tip + dir * 16); ctx.lineTo(24, arms + dir * 16);
        ctx.closePath();
      }
    };
  }
  const iconCache = new Map();
  function iconMaterial(kind, color) {
    const key = `${kind}:${color}`;
    if (!iconCache.has(key)) {
      const canvas = document.createElement("canvas");
      canvas.width = canvas.height = 128;
      const ctx = canvas.getContext("2d");
      const [name, count] = kind.split(":");
      const draw = name === "bend" ? chevrons(Number(count), false) : name === "release" ? chevrons(1, true) : ICONS[name];
      ctx.beginPath();
      draw(ctx);
      ctx.lineJoin = "round";
      ctx.lineWidth = 8;
      ctx.strokeStyle = "#000000";
      ctx.stroke();
      ctx.fillStyle = color;
      ctx.fill("evenodd");
      const texture = new THREE.CanvasTexture(canvas);
      texture.colorSpace = THREE.SRGBColorSpace;
      const material = new THREE.SpriteMaterial({ map: texture, transparent: true, depthWrite: false });
      material.clippingPlanes = laneClip();
      iconCache.set(key, material);
    }
    return iconCache.get(key);
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

  // A note is see-through, as in Rocksmith: a glowing outline in the string's colour around a
  // faint fill. Shapes shared by size (notes, open-string bars and their hit copies).
  function roundedRect(width, height, radius) {
    const x = -width / 2;
    const y = -height / 2;
    const shape = new THREE.Shape();
    shape.moveTo(x + radius, y);
    shape.lineTo(x + width - radius, y);
    shape.quadraticCurveTo(x + width, y, x + width, y + radius);
    shape.lineTo(x + width, y + height - radius);
    shape.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
    shape.lineTo(x + radius, y + height);
    shape.quadraticCurveTo(x, y + height, x, y + height - radius);
    shape.lineTo(x, y + radius);
    shape.quadraticCurveTo(x, y, x + radius, y);
    return shape;
  }
  const outlineCache = new Map();
  function outlineShapes(width, height) {
    const key = [width, height].map((value) => value.toFixed(2)).join(":");
    if (!outlineCache.has(key)) {
      const radius = Math.min(0.11, height / 2 - 0.01);
      const thick = 0.05;
      const ring = roundedRect(width, height, radius);
      ring.holes.push(roundedRect(width - 2 * thick, height - 2 * thick, Math.max(0.02, radius - thick)));
      const halo = roundedRect(width + 0.14, height + 0.14, radius + 0.07);
      halo.holes.push(roundedRect(width - 0.02, height - 0.02, radius));
      outlineCache.set(key, {
        ring: shared(new THREE.ShapeGeometry(ring, 8)),
        halo: shared(new THREE.ShapeGeometry(halo, 8)),
        fill: shared(new THREE.ShapeGeometry(roundedRect(width - thick, height - thick, Math.max(0.02, radius - thick / 2)), 8)),
      });
    }
    return outlineCache.get(key);
  }
  // Palm mute: a translucent cross from corner to corner inside the note's outline, in the string's
  // colour. Two bars, each clipped to the inner rectangle; cached per size.
  const crossCache = new Map();
  function palmMuteCross(width, height, material, z) {
    const key = [width, height].map((value) => value.toFixed(2)).join(":");
    if (!crossCache.has(key)) {
      const a = width / 2 - 0.05; // inside the ring
      const b = height / 2 - 0.05;
      const slope = b / a;
      const dx = (0.03 * Math.hypot(1, slope)) / slope; // half a bar 0.06 wide, measured along x
      const bar = (sign) => {
        const shape = new THREE.Shape();
        shape.moveTo(-a, -sign * b);
        shape.lineTo(-a + dx, -sign * b);
        shape.lineTo(a, sign * (b - dx * slope));
        shape.lineTo(a, sign * b);
        shape.lineTo(a - dx, sign * b);
        shape.lineTo(-a, -sign * (b - dx * slope));
        shape.closePath();
        return shape;
      };
      crossCache.set(key, shared(new THREE.ShapeGeometry([bar(1), bar(-1)])));
    }
    const mesh = new THREE.Mesh(crossCache.get(key), material);
    mesh.position.z = z;
    return mesh;
  }

  // `look`: { ring, halo, fill } opacities. Clipped materials are the lane's; unclipped ones are
  // copies for a hit, which the caller fades.
  function outlineMaterials(color, look, clipped = true) {
    const make = (opacity, glow) => new THREE.MeshBasicMaterial({
      color, transparent: true, opacity, depthWrite: false,
      blending: glow ? THREE.AdditiveBlending : THREE.NormalBlending,
      clippingPlanes: clipped ? laneClip() : null,
    });
    return { ring: make(look.ring), halo: make(look.halo, true), fill: make(look.fill) };
  }
  const NOTE_LOOK = { ring: 1, halo: 0.3, fill: 0.12 };
  const UNPICKED_LOOK = { ring: 0.5, halo: 0.12, fill: 0.05 }; // reached by a slide or a hammer-on / pull-off
  const HIT_LOOK = { ring: 1, halo: 0.55, fill: 0.3 };
  // The outline's three meshes, centred on (x, y, z).
  function outlineMeshes(shapes, materials, x, y, z) {
    const fill = new THREE.Mesh(shapes.fill, materials.fill);
    const halo = new THREE.Mesh(shapes.halo, materials.halo);
    const ring = new THREE.Mesh(shapes.ring, materials.ring);
    fill.position.set(x, y, z - 0.01);
    halo.position.set(x, y, z - 0.005);
    ring.position.set(x, y, z);
    return [fill, halo, ring];
  }

  // Fret number (or symbol) printed on the front face of a gem (a sprite would cut through the gem
  // when the camera is tilted). Clipped decals are shared; unclipped ones are copies the caller may fade.
  let decalPlane = null;
  const decalCache = new Map();
  function faceDecal(key, map, width, height, clipped) {
    if (!decalPlane) decalPlane = shared(new THREE.PlaneGeometry(1, 1));
    let material = decalCache.get(key);
    if (!material) {
      material = new THREE.MeshBasicMaterial({
        map,
        transparent: true,
        depthWrite: false,
        polygonOffset: true,
        polygonOffsetFactor: -2,
        polygonOffsetUnits: -2,
        clippingPlanes: laneClip(),
      });
      decalCache.set(key, material);
    }
    if (!clipped) {
      material = material.clone();
      material.clippingPlanes = null;
    }
    const mesh = new THREE.Mesh(decalPlane, material);
    mesh.scale.set(width, height, 1);
    return mesh;
  }
  function faceLabel(text, height, clipped = true) {
    const map = labelMaterial(text, false, "#ffffff").map;
    return faceDecal(`text:${text}`, map, (height * map.image.width) / 128, height, clipped);
  }
  function faceIcon(kind, size, clipped = true) {
    return faceDecal(`icon:${kind}`, iconMaterial(kind, "#ffffff").map, size, size, clipped);
  }

  // Accent: a glowing double frame around the note (Rocksmith's), as a decal on its front face.
  let accentMap = null;
  function accentFrame(width, height, clipped = true) {
    if (!accentMap) {
      const canvas = document.createElement("canvas");
      canvas.width = 256;
      canvas.height = 128;
      const ctx = canvas.getContext("2d");
      ctx.strokeStyle = "#ffffff";
      ctx.shadowColor = "#ffd54f";
      ctx.shadowBlur = 10;
      ctx.lineWidth = 7;
      ctx.beginPath();
      ctx.roundRect(8, 8, 240, 112, 18);
      ctx.stroke();
      ctx.lineWidth = 4;
      ctx.beginPath();
      ctx.roundRect(22, 22, 212, 84, 12);
      ctx.stroke();
      accentMap = new THREE.CanvasTexture(canvas);
      accentMap.colorSpace = THREE.SRGBColorSpace;
    }
    return faceDecal("accent", accentMap, width, height, clipped);
  }

  // What is printed on a note's face. As in Rocksmith the note carries no fret number (the
  // neck's fret number lights up instead, see lightFretNumbers): only X for a dead note, "( )" for
  // a ghost note and the hammer-on / pull-off arrow — on the face, so it stays readable while the
  // note strikes the string, however fast the passage. Returns the parts.
  const LEGATO_ICONS = { H: "hammer", P: "pull" };
  function noteFace(note, height, x, y, z, clipped) {
    const parts = [];
    if (note.dead) parts.push(faceLabel("X", height, clipped));
    else if (note.ghost) parts.push(faceLabel("( )", height, clipped));
    const kind = LEGATO_ICONS[note.legato];
    if (kind) parts.push(faceIcon(kind, height * 0.8, clipped));
    parts.forEach((part) => part.position.set(x, y, z));
    return parts;
  }

  // Amber halo behind a fret number of the neck (Rocksmith's lit fret).
  function fretGlowMap(text) {
    const canvas = document.createElement("canvas");
    canvas.width = text.length > 2 ? 256 : 128;
    canvas.height = 128;
    const ctx = canvas.getContext("2d");
    ctx.font = "bold 84px system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.shadowColor = "#ff9d00";
    ctx.shadowBlur = 30;
    ctx.fillStyle = "#ffb43a";
    for (let pass = 0; pass < 4; pass += 1) ctx.fillText(text, canvas.width / 2, 68); // stacked: a stronger halo
    const texture = new THREE.CanvasTexture(canvas);
    texture.colorSpace = THREE.SRGBColorSpace;
    return texture;
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
      throw new Error(T("Este browser não tem WebGL (aceleração gráfica) ativo: a pista 3D não está disponível."));
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
    progress.title = T("Clique para avançar ou recuar");
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
    dragToMove(renderer.domElement);

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
    const fretNumbers = [];
    for (let fret = 1; fret <= FRETS; fret += 1) {
      // Just in front of the strike line, so they stay in view at every camera tilt. Each has its
      // own material: it turns amber and glows as a note on its fret comes (see lightFretNumbers).
      const number = label(String(fret), 0.4);
      number.material = number.material.clone();
      number.position.set(fretX(fret), 0.14, 0.3);
      const glow = new THREE.Sprite(new THREE.SpriteMaterial({ map: fretGlowMap(String(fret)), transparent: true, opacity: 0, depthWrite: false }));
      glow.position.set(fretX(fret), 0.14, 0.29);
      glow.scale.set(number.scale.x * 1.15, number.scale.y * 1.15, 1);
      scene.add(glow, number);
      fretNumbers[fret] = { number, glow, lit: -1 };
    }

    // Region of the neck being played (the "anchor"), lit on the floor.
    const anchor = new THREE.Mesh(
      new THREE.PlaneGeometry(1, far + 4),
      new THREE.MeshBasicMaterial({ color: 0x2b3a5c, transparent: true, opacity: 0.55, depthWrite: false }),
    );
    anchor.rotation.x = -Math.PI / 2;
    anchor.position.set(0, 0.015, -far / 2 + 2);
    scene.add(anchor);

    return { host, renderer, scene, camera, observer, anchor, fretNumbers, strings: [], cameraX: 5, fogNear: far * 0.55, fogFar: far, hud: { position, fill, time, bar: -1, percent: -1, lyrics: lyricsLine, line: -1, sung: -2 }, effects: [], headstock: null };
  }

  // Headstock at the left of the strings: wooden head with a rounded tip, a bone nut where the
  // neck starts, a tuning peg per string (the strings run from it) and the open-string note name
  // beside each peg in the string colour ("E A D G B e"). Local x: nut at 0, pegs and names left.
  const PEG_X = -0.6;
  const NAME_X = -1.15;

  // Drag to move the view, wheel to zoom in and out, double click to put it back. Only on the
  // picture itself: the progress bar keeps its click.
  function dragToMove(canvas) {
    canvas.classList.add("hw-canvas");
    canvas.title = T("Arraste para rodar a vista (até 120° em cada eixo); Ctrl + arrastar roda sobre o eixo da vista; Shift ou botão direito + arrastar move a vista; roda do rato aproxima ou afasta; duplo clique repõe a vista.");
    const turn = (angle) => Math.min(MAX_TURN, Math.max(-MAX_TURN, angle));
    let drag = null;
    // Highway units per pixel at the strings (the strike line), so they follow the mouse.
    const perPixel = () => {
      const distance = Math.hypot(cameraPosition.y, cameraPosition.z) || 1;
      const visible = (2 * distance * Math.tan((stage.camera.fov * Math.PI) / 360)) / view.zoom;
      return visible / Math.max(canvas.clientHeight, 1);
    };
    canvas.addEventListener("pointerdown", (event) => {
      if (event.button !== 0 && event.button !== 2) return;
      const mode = event.button === 2 || event.shiftKey ? "move" : event.ctrlKey || event.altKey ? "roll" : "turn";
      drag = { id: event.pointerId, x: event.clientX, y: event.clientY, mode };
      canvas.setPointerCapture(event.pointerId);
      canvas.classList.add("dragging");
    });
    canvas.addEventListener("pointermove", (event) => {
      if (!drag || event.pointerId !== drag.id || !stage) return;
      const dx = event.clientX - drag.x;
      const dy = event.clientY - drag.y;
      if (drag.mode === "move") {
        const unit = perPixel();
        view.x -= dx * unit;
        view.y += dy * unit;
      } else if (drag.mode === "roll") {
        view.roll = turn(view.roll + (dx / Math.max(canvas.clientWidth, 1)) * 2 * MAX_TURN);
      } else {
        // across the whole picture: the full 120°
        view.yaw = turn(view.yaw - (dx / Math.max(canvas.clientWidth, 1)) * 2 * MAX_TURN);
        view.pitch = turn(view.pitch + (dy / Math.max(canvas.clientHeight, 1)) * 2 * MAX_TURN);
      }
      drag.x = event.clientX;
      drag.y = event.clientY;
    });
    const end = (event) => {
      if (!drag || event.pointerId !== drag.id) return;
      drag = null;
      canvas.classList.remove("dragging");
    };
    canvas.addEventListener("pointerup", end);
    canvas.addEventListener("pointercancel", end);
    canvas.addEventListener("contextmenu", (event) => event.preventDefault()); // right button: move
    canvas.addEventListener("wheel", (event) => {
      event.preventDefault(); // zoom the highway, not scroll the page
      if (!stage) return;
      const steps = event.deltaMode === 0 ? event.deltaY / 100 : event.deltaY / 3; // pixels or lines
      const before = perPixel();
      view.zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, view.zoom * Math.exp(-0.15 * steps)));
      // Towards the mouse, as on a map: the point under it stays under it.
      const box = canvas.getBoundingClientRect();
      const shift = before - perPixel();
      view.x += (event.clientX - box.left - box.width / 2) * shift;
      view.y -= (event.clientY - box.top - box.height / 2) * shift;
    }, { passive: false });
    canvas.addEventListener("dblclick", () => {
      Object.assign(view, { x: 0, y: 0, zoom: 1, yaw: 0, pitch: 0, roll: 0 });
    });
  }

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
  const ACCENTS = [1, 2]; // alphaTab AccentuationType: normal, heavy (tenuto 3 is not an accent)
  const PINCH_HARMONIC = 3; // alphaTab HarmonicType: natural 1, artificial 2, pinch 3, tapped 4, semi 5, feedback 6
  const BRUSH = { up: 1, down: 2 };

  // A slide into a note while the note before it on the same string is still sounding starts from
  // that note's trail, at its fret, instead of from nowhere three frets away; that trail is cut
  // where the slide leaves it. Only when the earlier note lies on the side the slide comes from
  // (below for a slide up), is fretted, has a trail, no bend and no slide of its own. Returns, per
  // note, what changes: { fromFret, run } (run in ticks) for the sliding one and { cutTicks } (its
  // trail's new length) for the one it leaves.
  function joinedSlidesIn(notes) {
    const out = new Map();
    const last = new Map(); // string -> the latest note on it so far
    const gap = TICKS_PER_QUARTER / 2; // a sustain ending this close before the note still meets it
    for (const note of [...notes].sort((a, b) => a.tick - b.tick)) {
      const before = last.get(note.string);
      last.set(note.string, note);
      const up = note.slideIn === SLIDE_IN.fromBelow;
      if (!before || !(up || note.slideIn === SLIDE_IN.fromAbove)) continue;
      const usable = !before.dead && before.fret > 0 && !before.bendCurve && !before.slideOut && before.tick < note.tick;
      const side = up ? before.fret < note.fret : before.fret > note.fret;
      if (!usable || !side || before.length < SUSTAIN_MIN || before.tick + before.length < note.tick - gap) continue;
      const run = Math.min(SLIDE_IN_RUN / Z_PER_TICK, (note.tick - before.tick) / 2);
      out.set(note, { ...out.get(note), fromFret: before.fret, run });
      out.set(before, { ...out.get(before), cutTicks: note.tick - run - before.tick });
    }
    return out;
  }

  // A bend's notehead mark, as Rocksmith shows its strength: "bend:1" (a half step or less),
  // "bend:2" (a whole step), "bend:3" (more); "release" for a release alone; "" for none. The
  // trail shows the rest (rising, held, coming back).
  function bendMark(note) {
    if (!note.hasBend || note.bendType === BEND.hold) return "";
    if (note.bendType === BEND.release) return "release";
    const quarterTones = note.maxBendPoint ? note.maxBendPoint.value : 4;
    return `bend:${quarterTones <= 2 ? 1 : quarterTones <= 4 ? 2 : 3}`;
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
      // The inverse: time (ms from bar 1) of the playback `tick`.
      tickToMs(tick) {
        if (!tempoMap.length) return 0;
        let low = 0;
        let high = tempoMap.length - 1;
        while (low < high) {
          const mid = (low + high + 1) >> 1;
          if (tempoMap[mid].tick <= tick) low = mid;
          else high = mid - 1;
        }
        const entry = tempoMap[low];
        return entry.ms + ((tick - entry.tick) * 60000) / (entry.tempo * TICKS_PER_QUARTER);
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
              slap: beat.slap,
              pop: beat.pop,
              tremolo: beat.isTremolo,
              accent: ACCENTS.includes(note.accentuated),
              bend: bendMark(note),
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
              // With an open string (a level bar across the hand's frets) the chord comes level.
              rolls: !struck.some((note) => note.fret === 0 && !note.isDead),
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

    const noteShapes = outlineShapes(0.8, 0.36);
    const unit = new THREE.BoxGeometry(1, 1, 1);
    const noteMaterials = [];
    const unpickedMaterials = [];
    const trailMaterials = [];
    for (let string = 1; string <= count; string += 1) {
      const color = stringColor(string, count);
      noteMaterials[string] = outlineMaterials(color, NOTE_LOOK);
      unpickedMaterials[string] = outlineMaterials(color, UNPICKED_LOOK);
      trailMaterials[string] = new THREE.MeshBasicMaterial({
        color, transparent: true, opacity: 0.45, depthWrite: false, clippingPlanes: laneClip(),
      });
    }
    const deadMaterials = outlineMaterials(0x8a8f99, NOTE_LOOK);
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
    // A slide's trail: straight in the middle, with a small curve where it leaves the trail before
    // it (``from``) and where it meets the note's own trail after it (``into``), so the trails flow
    // into one another instead of meeting at a corner. As wide and flat as the other trails (a
    // tube flattened to their height).
    const slideRibbon = (material, x0, z0, x1, z1, y, from = true, into = true) => {
      const start = new THREE.Vector3(x0, 0, z0);
      const end = new THREE.Vector3(x1, 0, z1);
      const run = Math.min(SLIDE_BLEND * Math.abs(z1 - z0), SLIDE_BLEND_MAX) * Math.sign(z1 - z0);
      const leave = from ? new THREE.Vector3(x0, 0, z0 + run) : start.clone().lerp(end, 1 / 3);
      const meet = into ? new THREE.Vector3(x1, 0, z1 - run) : start.clone().lerp(end, 2 / 3);
      const curve = new THREE.CubicBezierCurve3(start, leave, meet, end);
      const mesh = new THREE.Mesh(new THREE.TubeGeometry(curve, 24, 0.08, 8), material);
      mesh.scale.y = 0.06 / 0.16;
      mesh.position.y = y;
      lane.add(mesh);
    };
    // Sustain as a tube: rises with the bend curve (Rocksmith style) and wiggles with vibrato.
    // Tremolo picking makes it a zigzag (straight strokes between the corners).
    const sustainTube = (material, x, y, note, lengthTicks) => {
      const curve = note.bendCurve || [{ tick: note.tick, value: 0 }, { tick: note.tick + lengthTicks, value: 0 }];
      const amplitude = note.vibrato === 2 ? 0.22 : note.vibrato ? 0.12 : 0;
      const points = [];
      if (note.tremolo) {
        const start = curve[0].tick;
        const end = Math.max(curve[curve.length - 1].tick, start + lengthTicks);
        const corners = Math.max(2, Math.round(((end - start) * Z_PER_TICK) / TREMOLO_STEP));
        for (let k = 0; k <= corners; k += 1) {
          const tick = start + ((end - start) * k) / corners;
          const side = k === 0 ? 0 : k % 2 ? 0.14 : -0.14;
          points.push(new THREE.Vector3(x + side, y + bendValueAt(curve, tick) * BEND_RISE, -tick * Z_PER_TICK));
        }
        const zigzag = new THREE.CatmullRomCurve3(points, false, "catmullrom", 0); // tension 0: straight strokes
        lane.add(new THREE.Mesh(new THREE.TubeGeometry(zigzag, points.length * 8, 0.05, 6), material));
        return;
      }
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
    const icon = (parent, kind, x, y, z, color) => {
      const sprite = new THREE.Sprite(iconMaterial(kind, color));
      sprite.scale.set(0.4, 0.4, 1);
      sprite.position.set(x, y, z + 0.2);
      parent.add(sprite);
    };
    // The frame around a chord's notes spans every string; the chord turns around its centre.
    const top = stringY(1, count) + 0.2;
    const bottom = stringY(count, count) - 0.2;
    const chordAt = new Map();
    for (const chord of chords) {
      chord.x = (fretX(chord.low) + fretX(chord.high)) / 2;
      chordAt.set(chord.tick, chord);
    }

    const slidesIn = joinedSlidesIn(notes);
    notes.forEach((note, i) => {
      const stringLine = stringY(note.string, count);
      // A pre-bent note starts already off its string, where the bend holds it (Rocksmith's).
      const y = stringLine + (note.bendCurve ? note.bendCurve[0].value * BEND_RISE : 0);
      const z = -note.tick * Z_PER_TICK;
      const materials = note.dead ? deadMaterials : note.unpicked ? unpickedMaterials[note.string] : noteMaterials[note.string];
      const open = note.fret === 0 && !note.dead;
      // Open string: a bar across the fret window being played.
      const x = open ? (fretX(anchors[i].low) + fretX(anchors[i].high)) / 2 : fretX(note.fret);
      // The note itself (outline, face, symbols) turns as it comes, around its own centre or, in a
      // chord, the chord's; its trail does not.
      const chord = chordAt.get(note.tick);
      const pivotX = chord ? chord.x : x;
      const pivotY = chord ? (top + bottom) / 2 : y;
      const head = new THREE.Group();
      head.position.set(pivotX, pivotY, z);
      const dx = x - pivotX;
      const dy = y - pivotY;
      head.add(...outlineMeshes(open ? outlineShapes(anchors[i].open, 0.24) : noteShapes, materials, dx, dy, 0));
      if (note.palmMute && !note.dead) {
        const cross = palmMuteCross(open ? anchors[i].open : 0.8, open ? 0.24 : 0.36, trailMaterials[note.string], 0.002);
        cross.position.x = dx;
        cross.position.y = dy;
        head.add(cross);
      }
      const face = noteFace(note, open ? 0.2 : 0.28, dx, dy, 0.005, true);
      if (note.accent) {
        const frame = accentFrame(open ? anchors[i].open + 0.4 : 1.2, 0.62);
        frame.position.set(dx, dy, 0.003);
        face.push(frame);
      }
      if (face.length) head.add(...face);

      // Other technique symbols above the note, side by side, and a bend's chevrons above them.
      const marks = [
        note.tap ? "tap" : "",
        note.harmonic && !note.dead ? (note.harmonic === PINCH_HARMONIC ? "pinch" : "harmonic") : "",
        note.slap ? "slap" : "",
        note.pop ? "pop" : "",
      ].filter(Boolean);
      marks.forEach((kind, k) => icon(head, kind, dx + (k - (marks.length - 1) / 2) * 0.42, dy + 0.38, 0, "#ffffff"));
      if (note.bend) icon(head, note.bend, dx, dy + (marks.length ? 0.78 : 0.38), 0, "#ffd54f");
      note.rolls = !open && (!chord || chord.rolls);
      head.rotation.z = note.rolls ? noteRoll(Infinity) : 0;
      lane.add(head);
      note.head = head;
      note.ms = timeline.tickToMs(note.tick);
      note.parts = [head]; // hidden when the note reaches the strings (a glowing copy takes over)

      if (note.dead) return;
      let length = Math.max(note.length, note.vibrato || note.tremolo ? SUSTAIN_MIN : 0) * Z_PER_TICK;
      const joined = slidesIn.get(note);
      if (joined && joined.cutTicks !== undefined) length = Math.min(length, joined.cutTicks * Z_PER_TICK);
      const trailY = stringLine - 0.06; // the bend curve lifts the trail itself
      if (note.slideIn === SLIDE_IN.fromBelow || note.slideIn === SLIDE_IN.fromAbove) {
        if (joined && joined.fromFret !== undefined) {
          // From the end of the previous note's trail on this string (cut short to meet it).
          slideRibbon(trailMaterials[note.string], fretX(joined.fromFret), z + joined.run * Z_PER_TICK, x, z, trailY);
        } else {
          const from = note.fret + (note.slideIn === SLIDE_IN.fromBelow ? -3 : 3);
          slideRibbon(trailMaterials[note.string], fretX(Math.max(0, from)), z + SLIDE_IN_RUN, x, z, trailY, false);
        }
      }
      if ((note.slideOut === SLIDE_OUT.shift || note.slideOut === SLIDE_OUT.legato) && note.slideTo) {
        // Slide to the next note: the trail runs to the target fret at the target's time.
        slideRibbon(trailMaterials[note.string], x, z, fretX(note.slideTo.fret), -note.slideTo.tick * Z_PER_TICK, trailY);
      } else if (note.slideOut >= SLIDE_OUT.outUp) {
        const up = note.slideOut === SLIDE_OUT.outUp || note.slideOut === SLIDE_OUT.pickUp;
        const to = Math.min(FRETS, Math.max(0, note.fret + (up ? 4 : -4)));
        slideRibbon(trailMaterials[note.string], x, z, fretX(to), z - Math.max(length, 2), trailY, true, false);
      } else if (note.bendCurve || note.vibrato || note.tremolo) {
        sustainTube(trailMaterials[note.string], x, trailY, note, length / Z_PER_TICK);
      } else if (note.length >= SUSTAIN_MIN && length > 0) {
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

    let lastName = "";
    let lastTick = -Infinity;
    for (const chord of chords) {
      const width = chord.high - chord.low + 1;
      chord.frame = new THREE.EdgesGeometry(new THREE.BoxGeometry(width, top - bottom, 0.02));
      const frame = new THREE.LineSegments(chord.frame, chordMaterial);
      frame.position.set(chord.x, (top + bottom) / 2, -chord.tick * Z_PER_TICK);
      frame.rotation.z = chord.rolls ? noteRoll(Infinity) : 0;
      lane.add(frame);
      chord.mesh = frame;
      chord.ms = timeline.tickToMs(chord.tick);
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
      ...[...noteMaterials, ...unpickedMaterials, deadMaterials].filter(Boolean).flatMap((set) => [set.ring, set.halo, set.fill]),
      ...trailMaterials, chordMaterial, barMaterial, beatMaterial,
    ].filter(Boolean);
    clearEffects();
    song = {
      lane, notes, anchors, count, materials, bars, endTick, chords, top, bottom, barCount: score.masterBars.length,
      msToTick: timeline.msToTick, tickToMs: timeline.tickToMs, waveMesh: null,
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

  // `string`: the string a struck note's effect sits on (null for a chord frame).
  function addEffect(parts, until, bendCurve = null, string = null) {
    for (const part of parts) stage.scene.add(part);
    const baseY = parts.map((part) => part.position.y);
    stage.effects.push({ parts, until, fadeStart: 0, bendCurve, baseY, string });
  }

  function removeEffect(effect) {
    for (const part of effect.parts) {
      stage.scene.remove(part);
      part.material.dispose(); // own materials; geometries and textures are shared
    }
  }

  // A string sounds one note at a time: the note struck now ends the number and glow still
  // shown there (a short note keeps them at least an eighth, then fades — in a fast passage the
  // next note on that string would land on top of them).
  function clearString(string) {
    stage.effects = stage.effects.filter((effect) => {
      if (effect.string !== string) return true;
      removeEffect(effect);
      return false;
    });
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
    const x = open ? (fretX(anchor.low) + fretX(anchor.high)) / 2 : fretX(note.fret);
    // The same outline, brighter, with its own materials so it can fade; its ring stays at full
    // while the note rings.
    const outline = outlineMeshes(open ? outlineShapes(anchor.open + 0.1, 0.26) : outlineShapes(0.86, 0.4), outlineMaterials(color, HIT_LOOK, false), x, y, 0);
    outline[2].material.userData.solid = true;
    const glow = new THREE.Sprite(new THREE.SpriteMaterial({
      // Soft halo; normal blending so the halos of a chord do not add up to white.
      map: glowMap(), color, transparent: true, opacity: 0.6, depthWrite: false,
    }));
    glow.scale.set(open ? anchor.open + 1.2 : 1.8, 1, 1);
    glow.position.set(x, y, 0.1);
    const face = noteFace(note, open ? 0.22 : 0.3, x, y, 0.02, false);
    if (note.palmMute && !note.dead) {
      const material = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.55, depthWrite: false });
      const cross = palmMuteCross(open ? anchor.open + 0.1 : 0.86, open ? 0.26 : 0.4, material, 0.01);
      cross.position.x = x;
      cross.position.y = y;
      face.push(cross);
    }
    if (note.accent) {
      const frame = accentFrame(open ? anchor.open + 0.6 : 1.3, 0.66, false);
      frame.position.set(x, y, 0.015);
      face.push(frame);
    }
    clearString(note.string);
    addEffect([glow, ...outline, ...face], note.tick + Math.max(note.length, TICKS_PER_QUARTER / 2), note.bendCurve, note.string);
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
        removeEffect(effect);
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
      const position = T("Compasso {bar} / {total}", { bar: song.bars[bar].number, total: song.barCount });
      hud.position.textContent = section ? `${position} · ${section}` : position;
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
      note.head.rotation.z = note.rolls ? noteRoll(Infinity) : 0;
    });
    for (const chord of song.chords) chord.mesh.rotation.z = chord.rolls ? noteRoll(Infinity) : 0;
    rollNotes(tick);
    clearEffects();
  }

  // A fret number of the neck lights up (amber, with a halo; same place and size) as a note on that
  // fret comes, fully when the note strikes; it stays lit while the note rings, then fades.
  const FRET_RAMP = 4 * TICKS_PER_QUARTER;
  const FRET_FADE = TICKS_PER_QUARTER / 2;
  let fretShades = null; // [white, amber], made once three.js is loaded
  function lightFretNumbers(tick) {
    if (!fretShades) fretShades = [new THREE.Color(1, 1, 1), new THREE.Color(1, 0.7, 0.25)];
    const light = new Array(FRETS + 1).fill(0);
    const notes = song.notes;
    const see = (note) => {
      if (note.dead || note.fret < 1 || note.fret > FRETS) return;
      let level;
      if (note.tick > tick) level = (1 - (note.tick - tick) / FRET_RAMP) ** 2;
      else {
        const end = note.tick + Math.max(note.length, TICKS_PER_QUARTER / 2);
        level = tick <= end ? 1 : 1 - (tick - end) / FRET_FADE;
      }
      if (level > light[note.fret]) light[note.fret] = level;
    };
    for (let i = song.nextHit; i < notes.length && notes[i].tick <= tick + FRET_RAMP; i += 1) see(notes[i]);
    for (let i = song.nextHit - 1; i >= 0 && i >= song.nextHit - 48; i -= 1) see(notes[i]); // ringing or fading
    stage.fretNumbers.forEach((fret, f) => {
      if (!fret) return;
      const level = Math.max(0, Math.min(1, light[f]));
      if (Math.abs(level - fret.lit) < 0.005) return;
      fret.lit = level;
      fret.number.material.color.lerpColors(fretShades[0], fretShades[1], level);
      fret.glow.material.opacity = level;
    });
  }

  // Turn the notes (and chord frames) of the next NOTE_ROLL_S of the song towards level; the
  // ones further ahead keep the full tilt they were built with.
  function rollNotes(tick) {
    const now = song.tickToMs(tick);
    for (let i = song.nextHit; i < song.notes.length; i += 1) {
      const seconds = (song.notes[i].ms - now) / 1000;
      if (seconds > NOTE_ROLL_S) break;
      if (song.notes[i].rolls) song.notes[i].head.rotation.z = noteRoll(seconds);
    }
    for (let i = song.nextChord; i < song.chords.length; i += 1) {
      const seconds = (song.chords[i].ms - now) / 1000;
      if (seconds > NOTE_ROLL_S) break;
      if (song.chords[i].rolls) song.chords[i].mesh.rotation.z = noteRoll(seconds);
    }
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
    rollNotes(tick);
    updateEffects(tick);
    lightFretNumbers(tick);
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
    const target = new THREE.Vector3(cameraTarget.x, cameraTarget.y, cameraTarget.z);
    if (view.yaw || view.pitch) {
      // Turned with the mouse: camera, the point it looks at and its up all turn around the
      // strings at the strike line, sideways (about the vertical) and up/down (about the
      // camera's own left-right axis).
      const pivot = new THREE.Vector3(stage.cameraX, midY, 0);
      const forward = target.clone().sub(stage.camera.position);
      const across = forward.cross(stage.camera.up).normalize();
      const turnBy = new THREE.Quaternion()
        .setFromAxisAngle(new THREE.Vector3(0, 1, 0), view.yaw)
        .multiply(new THREE.Quaternion().setFromAxisAngle(across, view.pitch));
      stage.camera.position.sub(pivot).applyQuaternion(turnBy).add(pivot);
      target.sub(pivot).applyQuaternion(turnBy).add(pivot);
      stage.camera.up.applyQuaternion(turnBy);
    }
    stage.camera.lookAt(target);
    if (view.roll) stage.camera.rotateZ(view.roll);
    if (view.x || view.y) {
      // The view moved with the mouse: camera and the point it looks at shift together, across
      // the screen, so the angle stays the same.
      stage.camera.updateMatrixWorld();
      const right = new THREE.Vector3().setFromMatrixColumn(stage.camera.matrixWorld, 0).multiplyScalar(view.x);
      const up = new THREE.Vector3().setFromMatrixColumn(stage.camera.matrixWorld, 1).multiplyScalar(view.y);
      stage.camera.position.add(right).add(up);
    }
    if (stage.camera.zoom !== view.zoom) {
      stage.camera.zoom = view.zoom;
      stage.camera.updateProjectionMatrix();
    }
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
