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

  let loading = null;
  let api = null;
  let colors = [];
  let shown = new Set();
  let notice = ""; // message kept on screen after the notation is redrawn (e.g. no WebGL)
  let timedLyrics = null; // complete lyrics from the PDF with their place in the music
  let lastBytes = null; // the converted GP5 file
  const mutedBy = new Set(); // "video": the score's own sounds are silenced for it
  let notesVolume = 1; // volume of the score's sounds (0…1), set beside the song's audio
  // Tempo the score plays at ÷ its printed tempo, to follow a recording at another tempo.
  let tempoFactor = 1;

  function applySpeed() {
    if (api) api.playbackSpeed = Number(speedSelect.value) * tempoFactor;
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
          reject(new Error("Não foi possível carregar o visualizador de partitura."));
        };
        document.head.appendChild(script);
      });
    }
    return loading;
  }

  function createApi() {
    api = new alphaTab.AlphaTabApi(container, {
      // Canvas rendering: the SVG engine writes inline style attributes, which the page's CSP forbids.
      core: { engine: "html5", fontDirectory: `${VENDOR}font/`, useWorkers: true },
      display: { staveProfile: notationView, scale: 0.9 },
      notation: { rhythmMode: rhythmModeFor(notationView) },
      player: {
        playerMode: alphaTab.PlayerMode.EnabledSynthesizer,
        soundFont: `${VENDOR}soundfont/sonivox.sf3`,
        scrollOffsetY: -80,
      },
    });
    api.error.on((error) => {
      setStatus(`Erro na partitura: ${error && error.message ? error.message : error}`);
    });
    api.renderStarted.on(() => setStatus("A desenhar a partitura…"));
    api.renderFinished.on(() => setStatus(notice));
    api.scoreLoaded.on((score) => {
      applyVolume();
      tempoFactor = 1;
      applySpeed();
      window.AudioSync.songLoaded(score.tempo, [score.artist, score.title].filter(Boolean).join(" - "));
      window.VideoSync.setSong(`${score.artist} - ${score.title}`, (muted) => muteFor("video", muted),
        [score.artist, score.title].filter(Boolean).join(" "));
      buildTrackBar(score);
      buildHighwayTracks(score);
      if (in3D()) showHighway();
    });
    api.playerPositionChanged.on((e) => {
      updateTimeline(e);
      window.Highway3D.setPosition(e.currentTick, e.modifiedTempo, e.isSeek);
      window.VideoSync.position(e.currentTime, api.playbackSpeed, e.isSeek);
      window.AudioSync.position(e.currentTime, api.playbackSpeed, e.isSeek);
    });
    api.soundFontLoad.on((e) => {
      if (e.total) setStatus(`A carregar os sons… ${Math.round((100 * e.loaded) / e.total)}%`);
    });
    api.playerReady.on(() => {
      playButton.disabled = false;
      stopButton.disabled = false;
      seekInput.disabled = false;
      setStatus("");
    });
    api.playerStateChanged.on((e) => {
      const playing = e.state === alphaTab.synth.PlayerState.Playing;
      playButton.textContent = playing ? "❚❚ Pausa" : "▶ Tocar";
      window.Highway3D.setPlaying(playing);
      window.VideoSync.playing(playing);
      window.AudioSync.playing(playing);
    });
  }

  function renderShown() {
    const tracks = api.score.tracks.filter((track) => shown.has(track.index));
    api.renderTracks(tracks);
  }

  const LYRICS_TRACK = "Letra (voz)"; // the silent track carrying the lyrics (app/converter.py)
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
        check.title = "Mostrar a letra com a track escolhida";
        check.addEventListener("change", () => {
          if (check.checked) shown.add(track.index);
          else shown.delete(track.index);
          renderShown();
        });
      } else {
        check.type = "radio";
        check.name = "score-track";
        check.value = String(track.index);
        check.title = "Mostrar esta track";
        check.addEventListener("change", () => check.checked && showTrack(track.index));
      }
      const badge = document.createElement("span");
      badge.className = "track-num";
      badge.textContent = String(track.index + 1);
      label.append(check, badge, ` ${track.name}`);

      const mute = document.createElement("button");
      mute.type = "button";
      mute.className = "icon";
      mute.textContent = "🔊";
      mute.title = "Silenciar esta track";
      mute.setAttribute("aria-pressed", "false");
      mute.addEventListener("click", () => {
        const muted = mute.getAttribute("aria-pressed") !== "true";
        api.changeTrackMute([track], muted);
        mute.setAttribute("aria-pressed", String(muted));
        mute.textContent = muted ? "🔇" : "🔊";
        mute.title = muted ? "Voltar a ouvir esta track" : "Silenciar esta track";
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
        : "Não foi possível mostrar a pista 3D.";
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

  viewSelect.addEventListener("change", () => {
    if (!in3D()) notationView = viewSelect.value;
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
  playButton.addEventListener("click", () => api && api.playPause());
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
    colors = trackColors || [];
    timedLyrics = Array.isArray(lyrics) ? lyrics : null;
    notice = "";
    box.hidden = false;
    playButton.disabled = true;
    stopButton.disabled = true;
    seekInput.disabled = true;
    seekInput.value = "0";
    timeline = { tick: 0, endTick: 0, time: 0, endTime: 0 };
    showTime(0);
    playButton.textContent = "▶ Tocar";
    setStatus("A carregar o visualizador…");
    try {
      await loadAlphaTab();
      if (!api) createApi();
      else api.stop();
      // The first instrument track, with the lyrics under it.
      shown = new Set(lyricsTrack ? [0, trackCount] : [0]);
      api.load(bytes, [...shown]);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Erro ao mostrar a partitura.");
    }
  }

  function hide() {
    if (api) api.stop();
    window.Highway3D.hide();
    box.hidden = true;
  }

  // The converted song as a Guitar Pro 7/8 file (.gp) with `audio` (mp3/ogg/wav bytes) as its audio
  // track, bar 1 starting `offsetMs` into the audio (one sync point; Guitar Pro follows the tempo,
  // which is the one set for the recording).
  async function exportGp(audio, offsetMs) {
    if (!lastBytes) throw new Error("Converta primeiro uma música.");
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
    return new alphaTab.exporter.Gp7Exporter().export(score, settings);
  }

  // For the song's audio controls: play / pause the score, restart it at bar 1 (keeps playing).
  function playPause() {
    if (api && !playButton.disabled) api.playPause();
  }

  function restart() {
    if (api && !playButton.disabled) api.tickPosition = 0;
  }

  window.ScoreView = {
    show, hide, exportGp, muteFor, setNotesVolume, playPause, restart, setTempo, baseTempo,
    tempoFactor: () => tempoFactor,
    ready: () => Boolean(api) && !playButton.disabled,
  };
})();
