// Score viewer: draws the converted GP5 (notation + tab, all tracks) with alphaTab and plays it back.
// alphaTab is vendored under vendor/alphatab/ and loaded on first use only.
(() => {
  "use strict";

  const VENDOR = "/vendor/alphatab/";
  const box = document.getElementById("score-box");
  const container = document.getElementById("score");
  const trackBar = document.getElementById("score-tracks");
  const viewSelect = document.getElementById("score-view");
  const playButton = document.getElementById("score-play");
  const stopButton = document.getElementById("score-stop");
  const speedSelect = document.getElementById("score-speed");
  const statusLine = document.getElementById("score-status");
  const highway = document.getElementById("highway");
  const highwayLegend = document.getElementById("highway-legend");
  const highwayTrackLabel = document.getElementById("score-3d-track-label");
  const highwayTrack = document.getElementById("score-3d-track");
  const tiltLabel = document.getElementById("score-3d-tilt-label");
  const tiltInput = document.getElementById("score-3d-tilt");
  const TILT_KEY = "pdf-to-gp5.highway-tilt";
  const sideLabel = document.getElementById("score-3d-side-label");
  const sideInput = document.getElementById("score-3d-side");
  const SIDE_KEY = "pdf-to-gp5.highway-side";
  const seekInput = document.getElementById("score-seek");
  const timeLabel = document.getElementById("score-time");
  const SEEK_STEPS = Number(seekInput.max);
  const sectionsBar = document.getElementById("score-sections");
  const loopButton = document.getElementById("score-loop");
  const metronomeInput = document.getElementById("score-metronome");
  const countInInput = document.getElementById("score-count-in");
  const trainerInput = document.getElementById("score-trainer");
  const TRAINER_STEP = 0.05; // each round of the A–B loop this much faster…
  const TRAINER_TOP = 1; // …up to normal speed
  const LOOP_LABEL = T("Loop A–B");
  const editButton = document.getElementById("score-edit");
  const undoButton = document.getElementById("score-undo");
  const editHint = document.getElementById("note-edit-hint");
  const editor = document.getElementById("note-editor");
  const editorWhere = document.getElementById("note-editor-where");
  const editorFret = document.getElementById("note-editor-fret");
  const editorLength = document.getElementById("note-editor-length");
  const editorDotted = document.getElementById("note-editor-dotted");
  const editorTriplet = document.getElementById("note-editor-triplet");
  const editorDelete = document.getElementById("note-editor-delete");
  const editorClose = document.getElementById("note-editor-close");
  const MAX_UNDO = 50;

  let loading = null;
  let api = null;
  let colors = [];
  let shown = new Set();
  let notice = ""; // message kept on screen after the notation is redrawn (e.g. no WebGL)
  let timedLyrics = null; // complete lyrics from the PDF with their place in the music
  let lastBytes = null; // the converted GP5 file
  let drawn = false; // the loaded score has been drawn (alphaTab skips drawing while its page is hidden)
  const mutedBy = new Set(); // "video": the score's own sounds are silenced for it
  let notesVolume = 1; // volume of the score's sounds (0…1), set beside the song's audio
  // Tempo the score plays at ÷ its printed tempo, to follow a recording at another tempo.
  let tempoFactor = 1;
  let editing = false; // "Corrigir notas" is on: a click on a note opens the note editor
  let picked = null; // the note in the editor
  let pointer = { x: 0, y: 0 }; // where the score was last clicked, to place the editor there
  let undoStack = []; // the file as it was before each correction
  // While a corrected file replaces the one shown: where the page and the player were, to stay there.
  let reloading = null;

  function applySpeed() {
    if (api) api.playbackSpeed = Number(speedSelect.value) * tempoFactor;
  }

  // The playback speed (0.5 = 50 %), as the Velocidade menu sets it; a speed the menu lacks (the
  // loop trainer goes up 5 % at a time) is added to it.
  function setSpeed(value) {
    const rounded = Math.round(value * 100) / 100;
    const text = String(rounded);
    if (![...speedSelect.options].some((option) => Number(option.value) === rounded)) {
      const option = new Option(`${Math.round(rounded * 100)}%`, text);
      const after = [...speedSelect.options].find((o) => Number(o.value) > rounded);
      speedSelect.add(option, after || null);
    }
    speedSelect.value = [...speedSelect.options].find((o) => Number(o.value) === rounded).value;
    speedSelect.dispatchEvent(new Event("change"));
  }

  // Metronome and count-in (one bar of clicks before playing), as chosen; the count-in only when
  // neither the song's audio nor its video plays along (they would start a bar before the score).
  function applyClicks() {
    if (!api) return;
    api.metronomeVolume = metronomeInput.checked ? 1 : 0;
    const along = window.AudioSync.following() || window.VideoSync.following();
    api.countInVolume = countInInput.checked && !along ? 1 : 0;
  }

  // The score's printed tempo (BPM at the start).
  function baseTempo() {
    return api && api.score ? api.score.tempo : 120;
  }

  // Play the score at `bpm` (its printed tempo scaled; tempo changes keep their proportion).
  function setTempo(bpm) {
    tempoFactor = bpm > 0 ? bpm / baseTempo() : 1;
    applySpeed();
  }

  function applyVolume() {
    if (api) api.masterVolume = mutedBy.size ? 0 : notesVolume;
  }

  // Silence the score's sounds while the video plays instead.
  function muteFor(source, muted) {
    if (muted) mutedBy.add(source);
    else mutedBy.delete(source);
    applyVolume();
  }

  function setNotesVolume(volume) {
    notesVolume = Math.min(Math.max(volume, 0), 1);
    applyVolume();
  }
  let notationView = viewSelect.value === "3D" ? "Default" : viewSelect.value; // last notation (non-3D) view
  // Last player position (alphaTab ticks; song time in ms, as at 100% speed) and whether the
  // time bar is being dragged (its thumb then follows the mouse, not the player).
  let timeline = { tick: 0, endTick: 0, time: 0, endTime: 0 };
  let dragging = false;
  // Bars in playing order (repeats unrolled; alphaTab ticks) and the song's sections over them.
  let bars = [];
  let sections = []; // { start, end, button }
  let loopStart = null; // tick of A while waiting for B

  function formatTime(ms) {
    const seconds = Math.max(0, Math.floor(ms / 1000));
    return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  }

  function showTime(ms) {
    const text = `${formatTime(ms)} / ${formatTime(timeline.endTime)}`;
    timeLabel.textContent = text;
    window.Highway3D.setTime(text);
  }

  function updateTimeline(e) {
    // alphaTab reports real playing time (longer at 50%); show the song's own time instead.
    const speed = api.playbackSpeed || 1;
    timeline = { tick: e.currentTick, endTick: e.endTick, time: e.currentTime * speed, endTime: e.endTime * speed };
    if (dragging) return;
    seekInput.value = String(e.endTick > 0 ? Math.round((SEEK_STEPS * e.currentTick) / e.endTick) : 0);
    showTime(timeline.time);
    markSection(e.currentTick);
  }

  // The song's sections (Intro, Verse…) as a strip over the time bar, in playing order: each is
  // as wide as it lasts and jumps there when clicked.
  function buildSections() {
    const lookup = api.tickCache;
    bars = lookup && lookup.masterBars
      ? lookup.masterBars.map((bar) => ({
        start: bar.start,
        end: bar.end,
        index: bar.masterBar ? bar.masterBar.index : -1,
        name: bar.masterBar && bar.masterBar.section ? bar.masterBar.section.text : "",
      }))
      : [];
    sections = [];
    for (const bar of bars) {
      const last = sections[sections.length - 1];
      if (!last || bar.name) sections.push({ start: bar.start, end: bar.end, name: bar.name || T("Início") });
      else last.end = bar.end;
    }
    const total = bars.length ? bars[bars.length - 1].end - bars[0].start : 0;
    sectionsBar.replaceChildren(...sections.map((section) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = section.name;
      button.title = T("{name}: tocar a partir daqui", { name: section.name });
      button.style.flexGrow = String(section.end - section.start);
      button.addEventListener("click", () => { api.tickPosition = section.start; });
      section.button = button;
      return button;
    }));
    sectionsBar.hidden = sections.length < 2 || !total;
    markSection(timeline.tick);
  }

  function markSection(tick) {
    for (const section of sections) {
      const current = tick >= section.start && tick < section.end;
      section.button.classList.toggle("played", tick >= section.end);
      if (current) section.button.setAttribute("aria-current", "true");
      else section.button.removeAttribute("aria-current");
    }
  }

  // Previous / next bar (in playing order).
  function stepBar(delta) {
    if (!api || playButton.disabled || !bars.length) return;
    const tick = timeline.tick;
    let index = bars.findIndex((bar) => tick >= bar.start && tick < bar.end);
    if (index < 0) index = tick >= bars[bars.length - 1].end ? bars.length - 1 : 0;
    const target = bars[Math.min(Math.max(index + delta, 0), bars.length - 1)];
    api.tickPosition = target.start;
  }

  // Loop A–B: first press marks A, the second B (the stretch then repeats), the third ends it.
  function setLoopState(state, label) {
    loopButton.setAttribute("aria-pressed", state);
    loopButton.textContent = label;
  }

  // Loop trainer: when the A–B loop jumps back from its end to its start, the next round plays a
  // step faster, until normal speed.
  let lastTick = 0;
  function loopRound(tick) {
    const range = api && api.isLooping && trainerInput.checked ? api.playbackRange : null;
    const next = window.Practice.nextLoopSpeed(range, lastTick, tick, Number(speedSelect.value), TRAINER_STEP, TRAINER_TOP);
    if (next !== null) {
      setSpeed(next);
      setStatus(T("Loop: volta seguinte a {percent}%.", { percent: Math.round(next * 100) }));
    }
    lastTick = tick;
  }

  function clearLoop() {
    loopStart = null;
    if (api) {
      api.isLooping = false;
      api.playbackRange = null;
    }
    setLoopState("false", LOOP_LABEL);
  }

  function toggleLoop() {
    if (!api || playButton.disabled) return;
    if (api.playbackRange) {
      clearLoop();
      setStatus("");
    } else if (loopStart === null) {
      loopStart = timeline.tick;
      setLoopState("mixed", T("Marcar fim (B)"));
      setStatus(T("Início do trecho (A) em {time}: carregue outra vez no fim (B).", { time: formatTime(timeline.time) }));
    } else {
      const [start, end] = [loopStart, timeline.tick].sort((a, b) => a - b);
      if (end - start < 480) return; // under a beat: wait for a real end
      const range = new alphaTab.synth.PlaybackRange();
      range.startTick = start;
      range.endTick = end;
      api.playbackRange = range;
      api.isLooping = true;
      loopStart = null;
      setLoopState("true", T("Loop ligado ✓"));
      setStatus(T("A repetir o trecho A–B. Carregue em Loop para desligar."));
      if (timeline.tick >= end || timeline.tick < start) api.tickPosition = start;
    }
  }

  // Jump to `fraction` (0…1) of the song; the video and the 3D highway follow (isSeek position).
  function seekTo(fraction) {
    if (!api || !timeline.endTick) return;
    api.tickPosition = Math.round(Math.min(Math.max(fraction, 0), 1) * timeline.endTick);
  }

  function in3D() {
    return viewSelect.value === "3D";
  }

  // Tab-only view: print the rhythm under the tab, as the PDFs and Guitar Pro do.
  function rhythmModeFor(view) {
    return view === "Tab" ? alphaTab.TabRhythmMode.ShowWithBars : alphaTab.TabRhythmMode.Automatic;
  }

  function setStatus(text) {
    statusLine.textContent = text;
    statusLine.hidden = !text;
  }

  function loadAlphaTab() {
    if (window.alphaTab) return Promise.resolve();
    if (!loading) {
      loading = new Promise((resolve, reject) => {
        const script = document.createElement("script");
        script.src = `${VENDOR}alphaTab.min.js`;
        script.onload = () => resolve();
        script.onerror = () => {
          loading = null;
          reject(new Error(T("Não foi possível carregar o visualizador de partitura.")));
        };
        document.head.appendChild(script);
      });
    }
    return loading;
  }

  function createApi() {
    api = new alphaTab.AlphaTabApi(container, {
      // Canvas rendering: the SVG engine writes inline style attributes, which the page's CSP forbids.
      core: { engine: "html5", fontDirectory: `${VENDOR}font/`, useWorkers: true, includeNoteBounds: true },
      display: { staveProfile: notationView, scale: 0.9 },
      notation: { rhythmMode: rhythmModeFor(notationView) },
      player: {
        playerMode: alphaTab.PlayerMode.EnabledSynthesizer,
        soundFont: `${VENDOR}soundfont/sonivox.sf3`,
        scrollOffsetY: -80,
      },
    });
    api.error.on((error) => {
      setStatus(T("Erro na partitura: {error}", { error: error && error.message ? error.message : error }));
    });
    api.renderStarted.on(() => {
      drawn = true;
      setStatus(T("A desenhar a partitura…"));
    });
    api.renderFinished.on(() => {
      setStatus(notice);
      if (reloading && reloading.scroll !== null) {
        window.scrollTo(window.scrollX, reloading.scroll);
        reloading.scroll = null;
        if (reloading.tick === null) reloading = null;
      }
    });
    // midiLoad fires once the playing order (tickCache) is built. Not midiLoaded: subscribing to it
    // recurses forever inside alphaTab 1.8.4 (loadedMidiInfo) and the score never loads.
    api.midiLoad.on(() => buildSections());
    api.noteMouseDown.on((note) => {
      if (editing && note) openEditor(note);
    });
    api.scoreLoaded.on((score) => {
      drawn = false;
      applyVolume();
      applyClicks();
      if (!reloading) tempoFactor = 1; // a corrected file is the same song: its sync stays
      applySpeed();
      if (!reloading) {
        window.AudioSync.songLoaded(score.tempo, [score.artist, score.title].filter(Boolean).join(" - "));
        window.VideoSync.setSong(`${score.artist} - ${score.title}`, (muted) => muteFor("video", muted),
          [score.artist, score.title].filter(Boolean).join(" "));
      }
      buildTrackBar(score);
      buildHighwayTracks(score);
      if (in3D()) showHighway();
      document.dispatchEvent(new CustomEvent("score-loaded"));
    });
    api.playerPositionChanged.on((e) => {
      loopRound(e.currentTick);
      updateTimeline(e);
      window.Highway3D.setPosition(e.currentTick, e.modifiedTempo, e.isSeek);
      window.VideoSync.position(e.currentTime, api.playbackSpeed, e.isSeek);
      window.AudioSync.position(e.currentTime, api.playbackSpeed, e.isSeek);
    });
    api.soundFontLoad.on((e) => {
      if (e.total) setStatus(T("A carregar os sons… {percent}%", { percent: Math.round((100 * e.loaded) / e.total) }));
    });
    api.playerReady.on(() => {
      if (reloading && reloading.tick !== null) { // a corrected file: the player stays where it was
        api.tickPosition = reloading.tick;
        reloading.tick = null;
        if (reloading.scroll === null) reloading = null;
      }
      playButton.disabled = false;
      stopButton.disabled = false;
      seekInput.disabled = false;
      loopButton.disabled = false;
      setStatus("");
    });
    api.playerStateChanged.on((e) => {
      const playing = e.state === alphaTab.synth.PlayerState.Playing;
      playButton.textContent = playing ? T("❚❚ Pausa") : T("▶ Tocar");
      window.Highway3D.setPlaying(playing);
      window.VideoSync.playing(playing);
      window.AudioSync.playing(playing);
    });
  }

  function renderShown() {
    const tracks = api.score.tracks.filter((track) => shown.has(track.index));
    api.renderTracks(tracks);
  }

  const LYRICS_TRACK = "Letra (voz)"; // i18n-skip: track name inside the GP5 (data), shown through T() below; the silent track carrying the lyrics (app/converter.py)
  const isLyrics = (track) => track.name === LYRICS_TRACK;
  let lyricsIndex = -1; // index of the lyrics track, if the file has one

  // One instrument track on the page (and on the 3D highway) at a time; the lyrics track can be
  // shown with it.
  function showTrack(index) {
    shown = new Set([index, ...[...shown].filter((i) => i === lyricsIndex)]);
    for (const radio of trackBar.querySelectorAll('input[type="radio"]')) radio.checked = Number(radio.value) === index;
    if (highwayTrack.value !== String(index)) {
      highwayTrack.value = String(index);
      if (in3D()) showHighway();
    }
    renderShown();
  }

  function buildTrackBar(score) {
    trackBar.replaceChildren();
    lyricsIndex = score.tracks.findIndex(isLyrics);
    score.tracks.forEach((track) => {
      const item = document.createElement("div");
      item.className = "score-track";
      if (colors.length) item.style.setProperty("--track", colors[track.index % colors.length]);

      const label = document.createElement("label");
      const check = document.createElement("input");
      check.checked = shown.has(track.index);
      if (isLyrics(track)) {
        check.type = "checkbox"; // the lyrics go with whichever track is shown
        check.title = T("Mostrar a letra com a track escolhida");
        check.addEventListener("change", () => {
          if (check.checked) shown.add(track.index);
          else shown.delete(track.index);
          renderShown();
        });
      } else {
        check.type = "radio";
        check.name = "score-track";
        check.value = String(track.index);
        check.title = T("Mostrar esta track");
        check.addEventListener("change", () => check.checked && showTrack(track.index));
      }
      const badge = document.createElement("span");
      badge.className = "track-num";
      badge.textContent = String(track.index + 1);
      label.append(check, badge, ` ${isLyrics(track) ? T("Letra (voz)") : track.name}`);

      const mute = document.createElement("button");
      mute.type = "button";
      mute.className = "icon";
      mute.textContent = "🔊";
      mute.title = T("Silenciar esta track");
      mute.setAttribute("aria-pressed", "false");
      mute.addEventListener("click", () => {
        const muted = mute.getAttribute("aria-pressed") !== "true";
        api.changeTrackMute([track], muted);
        mute.setAttribute("aria-pressed", String(muted));
        mute.textContent = muted ? "🔇" : "🔊";
        mute.title = muted ? T("Voltar a ouvir esta track") : T("Silenciar esta track");
      });
      item.append(label, mute);
      trackBar.appendChild(item);
    });
  }

  function buildHighwayTracks(score) {
    const previous = highwayTrack.value;
    highwayTrack.replaceChildren(...score.tracks.filter((track) => !isLyrics(track)).map((track) => {
      const option = document.createElement("option");
      option.value = String(track.index);
      option.textContent = `${track.index + 1}. ${track.name}`;
      return option;
    }));
    const first = [...shown].find((index) => index !== lyricsIndex);
    highwayTrack.value = first !== undefined ? String(first) : previous || "0";
  }

  // The 3D highway replaces the notation on the page; alphaTab keeps playing and drives it.
  async function showHighway() {
    container.hidden = true;
    highway.hidden = false;
    highwayLegend.hidden = false;
    highwayTrackLabel.hidden = false;
    tiltLabel.hidden = false;
    sideLabel.hidden = false;
    window.Highway3D.setTilt(Number(tiltInput.value) / 100);
    window.Highway3D.setSide(Number(sideInput.value) / 100);
    api.settings.player.scrollMode = alphaTab.ScrollMode.Off; // nothing to follow on the hidden notation
    api.updateSettings();
    try {
      await window.Highway3D.show(highway, api.score, Number(highwayTrack.value || 0), timedLyrics);
      showTime(timeline.time);
      notice = "";
      setStatus("");
    } catch (error) {
      console.error(error);
      notice = error instanceof Error && error.message.includes("WebGL")
        ? error.message
        : T("Não foi possível mostrar a pista 3D.");
      viewSelect.value = notationView;
      showNotation();
    }
  }

  function showNotation() {
    window.Highway3D.hide();
    highway.hidden = true;
    highwayLegend.hidden = true;
    highwayTrackLabel.hidden = true;
    tiltLabel.hidden = true;
    sideLabel.hidden = true;
    container.hidden = false;
    api.settings.player.scrollMode = alphaTab.ScrollMode.Continuous;
    api.settings.display.staveProfile = alphaTab.StaveProfile[notationView];
    api.settings.notation.rhythmMode = rhythmModeFor(notationView);
    api.updateSettings();
    api.render();
  }

  // Converted while another page was showing: alphaTab skipped drawing (no width) and does not always
  // draw once the page shows. The menu sends "resize" when it shows a page.
  window.addEventListener("resize", () => {
    if (api && api.score && !drawn && !in3D() && container.offsetWidth > 0) api.render();
  });

  viewSelect.addEventListener("change", () => {
    if (!in3D()) notationView = viewSelect.value;
    editButton.hidden = in3D(); // notes are corrected on the notation
    if (in3D()) setEditing(false);
    if (!api || !api.score) return;
    if (in3D()) showHighway();
    else showNotation();
  });
  // Camera sliders, remembered per browser.
  function cameraControl(input, key, apply) {
    try {
      const saved = localStorage.getItem(key);
      if (saved !== null) input.value = saved;
    } catch { /* storage unavailable */ }
    input.addEventListener("input", () => {
      apply(Number(input.value) / 100);
      try { localStorage.setItem(key, input.value); } catch { /* storage unavailable */ }
    });
  }
  cameraControl(tiltInput, TILT_KEY, (value) => window.Highway3D.setTilt(value));
  cameraControl(sideInput, SIDE_KEY, (value) => window.Highway3D.setSide(value));
  highwayTrack.addEventListener("change", () => {
    if (!api || !api.score) return;
    if (in3D()) showHighway();
    showTrack(Number(highwayTrack.value)); // the same track on the page
  });
  playButton.addEventListener("click", playPause);
  seekInput.addEventListener("input", () => {
    dragging = true; // show where the thumb is; seek when it is released
    showTime((Number(seekInput.value) / SEEK_STEPS) * timeline.endTime);
  });
  seekInput.addEventListener("change", () => {
    dragging = false;
    seekTo(Number(seekInput.value) / SEEK_STEPS);
  });
  window.Highway3D.setSeekHandler(seekTo);
  stopButton.addEventListener("click", () => api && api.stop());
  loopButton.addEventListener("click", toggleLoop);
  // The practice choices, remembered in this browser.
  for (const [input, key] of [
    [metronomeInput, "pdf-to-gp5.metronome"],
    [countInInput, "pdf-to-gp5.count-in"],
    [trainerInput, "pdf-to-gp5.loop-trainer"],
  ]) {
    try { input.checked = localStorage.getItem(key) === "1"; } catch { /* storage unavailable */ }
    input.addEventListener("change", () => {
      try { localStorage.setItem(key, input.checked ? "1" : "0"); } catch { /* storage unavailable */ }
      applyClicks();
    });
  }
  speedSelect.addEventListener("change", () => {
    applySpeed();
    window.VideoSync.speed(Number(speedSelect.value));
    window.AudioSync.speed(Number(speedSelect.value));
  });

  // Show the score of a converted file. `bytes`: GP5 file; `trackColors`: one CSS colour per track position;
  // `lyrics`: the complete lyrics from the PDF with their place in the music (report.timed_lyrics);
  // `lyricsTrack`: the file ends with the lyrics track (after the `trackCount` instrument tracks).
  async function show(bytes, trackCount, trackColors, lyrics, lyricsTrack = false) {
    lastBytes = bytes;
    reloading = null;
    undoStack = [];
    undoButton.hidden = true;
    setEditing(false);
    editButton.disabled = !editable(bytes);
    editButton.title = editButton.disabled
      ? T("Só é possível corrigir notas em ficheiros .gp5, .gp4 ou .gp3.")
      : T("Clicar num número da tab para o mudar ou apagar");
    colors = trackColors || [];
    timedLyrics = Array.isArray(lyrics) ? lyrics : null;
    notice = "";
    box.hidden = false;
    playButton.disabled = true;
    stopButton.disabled = true;
    seekInput.disabled = true;
    loopButton.disabled = true;
    clearLoop();
    sectionsBar.hidden = true;
    seekInput.value = "0";
    timeline = { tick: 0, endTick: 0, time: 0, endTime: 0 };
    showTime(0);
    playButton.textContent = T("▶ Tocar");
    setStatus(T("A carregar o visualizador…"));
    try {
      await loadAlphaTab();
      if (!api) createApi();
      else api.stop();
      // The first instrument track, with the lyrics under it.
      shown = new Set(lyricsTrack ? [0, trackCount] : [0]);
      api.load(bytes, [...shown]);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : T("Erro ao mostrar a partitura."));
    }
  }

  function hide() {
    setEditing(false);
    if (api) api.stop();
    window.Highway3D.hide();
    box.hidden = true;
  }

  // Correcting notes ("Corrigir notas"). The server changes the file (PyGuitarPro, app/gp_edit.py)
  // and the page shows the corrected file; the download and the library get it too ("song-edited").

  // Guitar Pro 3/4/5 (their header names the version): the files the server can correct.
  function editable(bytes) {
    const head = String.fromCharCode(...bytes.subarray(0, 23));
    return /^\x18FICHIER GUITAR PRO v[345]\./.test(head); // i18n-skip: file header
  }

  function setEditing(on) {
    editing = Boolean(on) && !editButton.disabled;
    editButton.setAttribute("aria-pressed", String(editing));
    container.classList.toggle("editing", editing);
    editHint.hidden = !editing;
    if (!editing) closeEditor();
  }

  function closeEditor() {
    editor.hidden = true;
    picked = null;
  }

  function openEditor(note) {
    const staff = note.beat.voice.bar.staff;
    if (staff.isPercussion || note.beat.graceType !== alphaTab.model.GraceType.None) {
      setStatus(T("Esta nota não pode ser corrigida aqui."));
      return;
    }
    picked = note;
    editorWhere.textContent = T("Compasso {bar}, corda {string}", {
      bar: note.beat.voice.bar.index + 1,
      string: staff.tuning.length - note.string + 1, // 1 = the highest string, as in Guitar Pro
    });
    editorFret.value = String(note.fret);
    const length = beatLength(note.beat);
    for (const control of [editorLength, editorDotted, editorTriplet]) {
      control.disabled = !length;
      control.title = length ? "" : T("Esta duração não pode ser mudada aqui (quiáltera que não é tercina).");
    }
    if (length) {
      editorLength.value = String(length.value);
      editorDotted.checked = length.dotted;
      editorTriplet.checked = length.triplet;
    }
    editor.hidden = false;
    const area = editor.offsetParent.getBoundingClientRect();
    const left = Math.min(Math.max(pointer.x - area.left - 24, 0), Math.max(area.width - editor.offsetWidth, 0));
    editor.style.left = `${left}px`;
    editor.style.top = `${pointer.y - area.top + 16}px`;
    editorFret.focus();
    editorFret.select();
  }

  // Where `note` is in the file, as the server finds it (app/gp_edit.py: NoteEdit). alphaTab numbers the
  // strings from the lowest (1) and adds grace notes as beats of their own; Guitar Pro numbers them
  // from the highest and keeps grace notes inside the beat.
  function noteEdit(note, fret) {
    const beat = note.beat;
    const voice = beat.voice;
    const staff = voice.bar.staff;
    const plain = voice.beats.filter((b) => b.graceType === alphaTab.model.GraceType.None);
    return {
      track: staff.track.index,
      bar: voice.bar.index,
      voice: voice.index,
      beat: plain.indexOf(beat),
      string: staff.tuning.length - note.string + 1,
      expected: note.fret,
      fret,
    };
  }

  const LENGTHS = [1, 2, 4, 8, 16, 32];

  // The beat's length as the server sets it (app/gp_edit.py: Length), or null for one it cannot
  // (a tuplet other than a triplet, a double dot).
  function beatLength(beat) {
    const triplet = beat.tupletNumerator === 3 && beat.tupletDenominator === 2;
    const plain = !beat.hasTuplet;
    if (!LENGTHS.includes(beat.duration) || beat.dots > 1 || !(triplet || plain)) return null;
    return { value: beat.duration, dotted: beat.dots === 1, triplet };
  }

  // A new length for the note's beat: the bar stays whole on the server (rests at its end give
  // or take the time).
  function lengthEdit(note, length) {
    const { track, bar, voice, beat } = noteEdit(note, null);
    return { track, bar, voice, beat, expected_length: beatLength(note.beat), length };
  }

  // `edits`: what the server applies, in order (app/gp_edit.py).
  async function correct(edits) {
    if (!picked || !lastBytes || !edits.length) return;
    const body = new FormData();
    body.append("file", new Blob([lastBytes], { type: "application/octet-stream" }), "song.gp5");
    body.append("edits", JSON.stringify(edits));
    for (const control of editor.elements) control.disabled = true;
    setStatus(T("A corrigir a nota…"));
    try {
      const response = await fetch("/api/edit", { method: "POST", body });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(typeof payload.detail === "string" ? payload.detail : T("Não foi possível corrigir a nota."));
      }
      undoStack.push(lastBytes);
      if (undoStack.length > MAX_UNDO) undoStack.shift();
      replaceFile(new Uint8Array(await response.arrayBuffer()));
    } catch (error) {
      setStatus(error instanceof Error ? error.message : T("Não foi possível corrigir a nota."));
    } finally {
      for (const control of editor.elements) control.disabled = false;
    }
  }

  // Show `bytes` (the same song, corrected) where the page and the player are now.
  function replaceFile(bytes) {
    closeEditor();
    lastBytes = bytes;
    undoButton.hidden = undoStack.length === 0;
    if (api.playerState === alphaTab.synth.PlayerState.Playing) api.pause();
    reloading = { scroll: window.scrollY, tick: api.tickPosition };
    api.load(bytes, [...shown]);
    document.dispatchEvent(new CustomEvent("song-edited", { detail: { gp5: bytes } }));
  }

  container.addEventListener("pointerdown", (event) => {
    pointer = { x: event.clientX, y: event.clientY };
  }, true);
  editButton.addEventListener("click", () => setEditing(!editing));
  undoButton.addEventListener("click", () => {
    if (undoStack.length && api) replaceFile(undoStack.pop());
  });
  editor.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!picked) return;
    const edits = [];
    const fret = Number(editorFret.value);
    if (fret !== picked.fret) edits.push(noteEdit(picked, fret));
    const now = beatLength(picked.beat);
    const wanted = { value: Number(editorLength.value), dotted: editorDotted.checked, triplet: editorTriplet.checked };
    if (now && JSON.stringify(now) !== JSON.stringify(wanted)) edits.push(lengthEdit(picked, wanted));
    if (edits.length) correct(edits);
    else closeEditor();
  });
  editorDelete.addEventListener("click", () => picked && correct([noteEdit(picked, null)]));
  editorClose.addEventListener("click", closeEditor);
  editor.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && event.target === editorLength) {
      event.preventDefault(); // a select does not submit its form on Enter
      editor.requestSubmit();
      return;
    }
    if (event.key === "Escape") {
      event.stopPropagation();
      closeEditor();
    }
  });

  // The converted song as a Guitar Pro 7/8 file (.gp) with `audio` (mp3/ogg/wav bytes) as its audio
  // track, bar 1 starting `offsetMs` into the audio (one sync point; Guitar Pro follows the tempo,
  // which is the one set for the recording).
  async function exportGp(audio, offsetMs) {
    if (!lastBytes) throw new Error(T("Converta primeiro uma música."));
    await loadAlphaTab();
    const settings = new alphaTab.Settings();
    const score = alphaTab.importer.ScoreLoader.loadScoreFromBytes(lastBytes, settings);
    if (tempoFactor !== 1) {
      const scale = (bpm) => Math.round(bpm * tempoFactor * 100) / 100;
      score.tempo = scale(score.tempo);
      for (const masterBar of score.masterBars) {
        for (const automation of masterBar.tempoAutomations) automation.value = scale(automation.value);
      }
    }
    score.backingTrack = new alphaTab.model.BackingTrack();
    score.backingTrack.rawAudioFile = audio;
    score.applyFlatSyncPoints([{ barIndex: 0, barOccurence: 0, barPosition: 0, millisecondOffset: Math.round(offsetMs) }]);
    const gp = new alphaTab.exporter.Gp7Exporter().export(score, settings);
    // The audio as "backing-track.mp3" (alphaTab writes it with no extension), as in Guitar Pro's files.
    return window.GpZip.nameBackingTrack(gp, audio);
  }

  // For the song's audio controls: play / pause the score, restart it at bar 1 (keeps playing).
  function playPause() {
    if (!api || playButton.disabled) return;
    applyClicks();
    api.playPause();
  }

  function restart() {
    if (api && !playButton.disabled) api.tickPosition = 0;
  }

  // Change the view (Default, Tab, Score or 3D), as the Vista menu does.
  function setView(view) {
    if (![...viewSelect.options].some((option) => option.value === view) || viewSelect.value === view) return;
    viewSelect.value = view;
    viewSelect.dispatchEvent(new Event("change"));
  }

  function stop() {
    if (api && !playButton.disabled) api.stop();
  }

  // Put the player at bar `number` (1-based, as the file numbers its bars; its first pass) and show it.
  function goToBar(number) {
    const bar = bars.find((b) => b.index === number - 1);
    if (!api || !bar) return;
    api.tickPosition = bar.start;
    if (typeof api.scrollToCursor === "function") setTimeout(() => api.scrollToCursor(), 300); // once the page shows
  }

  const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]; // i18n-skip: note names

  // A Guitar Pro file opened as it is (.gp, .gpx, .gp5, .gp4, .gp3): read by alphaTab, and summed
  // up in the shape of a conversion report, so the result, the library and the rest of the page
  // treat it like a converted song. Throws when alphaTab cannot read it.
  async function describe(bytes, filename) {
    await loadAlphaTab();
    const score = alphaTab.importer.ScoreLoader.loadScoreFromBytes(bytes, new alphaTab.Settings());
    const bars = score.masterBars;
    const signature = (bar) => `${bar.timeSignatureNumerator}/${bar.timeSignatureDenominator}`;
    const changes = [];
    bars.forEach((bar, index) => {
      if (index > 0 && signature(bar) !== signature(bars[index - 1])) {
        changes.push({ bar: index + 1, time_signature: signature(bar) });
      }
    });
    const tempos = [];
    bars.forEach((bar, index) => {
      for (const automation of bar.tempoAutomations || []) {
        if (index > 0 || automation.ratioPosition > 0) tempos.push({ bar: index + 1, tempo: Math.round(automation.value) });
      }
    });
    let total = 0;
    const tracks = score.tracks.map((track) => {
      const staff = track.staves[0];
      let notes = 0;
      for (const bar of staff.bars) {
        for (const voice of bar.voices) for (const beat of voice.beats) notes += beat.isRest ? 0 : beat.notes.length;
      }
      total += notes;
      const tuning = staff.isPercussion ? [] : [...staff.tuning].reverse(); // low string first
      return {
        name: track.name || T("Track {n}", { n: track.index + 1 }),
        filename,
        measures: staff.bars.length,
        notes,
        strings: tuning.length,
        tuning: tuning.map((midi) => NOTE_NAMES[midi % 12]).join(" ") || "—",
        instrument: "—",
        rhythm_from_notation: staff.bars.length,
        rhythm_estimated: 0,
        sources: ["guitarpro"],
        systems_detail: [],
        preview: "",
        warnings: [],
      };
    });
    return {
      title: score.title || "",
      artist: score.artist || "",
      tempo: score.tempo,
      time_signature: bars.length ? signature(bars[0]) : "4/4",
      time_signature_changes: changes,
      tempo_changes: tempos,
      navigation: [],
      repeats: bars.filter((bar) => bar.isRepeatStart).length,
      auto: {},
      measures: bars.length,
      notes: total,
      sections: bars.filter((bar) => bar.section).map((bar) => bar.section.text),
      lyrics: null,
      timed_lyrics: [],
      warnings: [],
      tracks,
      source: "guitarpro",
    };
  }

  window.ScoreView = {
    show, hide, exportGp, describe, setNotesVolume, playPause, restart, setTempo,
    stop, stepBar, toggleLoop, setView, goToBar,
    tempoFactor: () => tempoFactor,
    ready: () => Boolean(api) && !playButton.disabled,
  };
})();
