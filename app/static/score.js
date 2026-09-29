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

  let loading = null;
  let api = null;
  let colors = [];
  let shown = new Set();

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
      display: { staveProfile: viewSelect.value, scale: 0.9 },
      notation: { rhythmMode: rhythmModeFor(viewSelect.value) },
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
    api.renderFinished.on(() => setStatus(""));
    api.scoreLoaded.on((score) => buildTrackBar(score));
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

  viewSelect.addEventListener("change", () => {
    if (!api) return;
    api.settings.display.staveProfile = alphaTab.StaveProfile[viewSelect.value];
    api.settings.notation.rhythmMode = rhythmModeFor(viewSelect.value);
    api.updateSettings();
    api.render();
  });
  playButton.addEventListener("click", () => api && api.playPause());
  stopButton.addEventListener("click", () => api && api.stop());
  speedSelect.addEventListener("change", () => {
    if (api) api.playbackSpeed = Number(speedSelect.value);
  });

  // Show the score of a converted file. `bytes`: GP5 file; `trackColors`: one CSS colour per track position.
  async function show(bytes, trackCount, trackColors) {
    colors = trackColors || [];
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
    box.hidden = true;
  }

  window.ScoreView = { show, hide };
})();
