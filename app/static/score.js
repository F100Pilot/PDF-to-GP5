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

  let loading = null;
  let api = null;
  let colors = [];
  let shown = new Set();
  let notice = ""; // message kept on screen after the notation is redrawn (e.g. no WebGL)
  let timedLyrics = null; // complete lyrics from the PDF with their place in the music
  let notationView = viewSelect.value === "3D" ? "Default" : viewSelect.value; // last notation (non-3D) view

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
      window.VideoSync.setSong(`${score.artist} - ${score.title}`, (muted) => {
        api.masterVolume = muted ? 0 : 1; // listen to the video only
      }, [score.artist, score.title].filter(Boolean).join(" "));
      buildTrackBar(score);
      buildHighwayTracks(score);
      if (in3D()) showHighway();
    });
    api.playerPositionChanged.on((e) => {
      window.Highway3D.setPosition(e.currentTick, e.modifiedTempo, e.isSeek);
      window.VideoSync.position(e.currentTime, api.playbackSpeed, e.isSeek);
    });
    api.soundFontLoad.on((e) => {
      if (e.total) setStatus(`A carregar os sons… ${Math.round((100 * e.loaded) / e.total)}%`);
    });
    api.playerReady.on(() => {
      playButton.disabled = false;
      stopButton.disabled = false;
      setStatus("");
    });
    api.playerStateChanged.on((e) => {
      const playing = e.state === alphaTab.synth.PlayerState.Playing;
      playButton.textContent = playing ? "❚❚ Pausa" : "▶ Tocar";
      window.Highway3D.setPlaying(playing);
      window.VideoSync.playing(playing);
    });
  }

  function renderShown() {
    const tracks = api.score.tracks.filter((track) => shown.has(track.index));
    api.renderTracks(tracks);
  }

  function buildTrackBar(score) {
    trackBar.replaceChildren();
    score.tracks.forEach((track) => {
      const item = document.createElement("div");
      item.className = "score-track";
      if (colors.length) item.style.setProperty("--track", colors[track.index % colors.length]);

      const label = document.createElement("label");
      const check = document.createElement("input");
      check.type = "checkbox";
      check.checked = shown.has(track.index);
      check.addEventListener("change", () => {
        if (check.checked) shown.add(track.index);
        else if (shown.size > 1) shown.delete(track.index);
        else check.checked = true; // keep at least one track on the page
        renderShown();
      });
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
    highwayTrack.replaceChildren(...score.tracks.map((track) => {
      const option = document.createElement("option");
      option.value = String(track.index);
      option.textContent = `${track.index + 1}. ${track.name}`;
      return option;
    }));
    if (previous && Number(previous) < score.tracks.length) highwayTrack.value = previous;
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
    if (api && api.score && in3D()) showHighway();
  });
  playButton.addEventListener("click", () => api && api.playPause());
  stopButton.addEventListener("click", () => api && api.stop());
  speedSelect.addEventListener("change", () => {
    if (api) api.playbackSpeed = Number(speedSelect.value);
    window.VideoSync.speed(Number(speedSelect.value));
  });

  // Show the score of a converted file. `bytes`: GP5 file; `trackColors`: one CSS colour per track position;
  // `lyrics`: the complete lyrics from the PDF with their place in the music (report.timed_lyrics).
  async function show(bytes, trackCount, trackColors, lyrics) {
    colors = trackColors || [];
    timedLyrics = Array.isArray(lyrics) ? lyrics : null;
    notice = "";
    box.hidden = false;
    playButton.disabled = true;
    stopButton.disabled = true;
    playButton.textContent = "▶ Tocar";
    setStatus("A carregar o visualizador…");
    try {
      await loadAlphaTab();
      if (!api) createApi();
      else api.stop();
      shown = new Set(Array.from({ length: trackCount }, (_, i) => i));
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

  window.ScoreView = { show, hide };
})();
