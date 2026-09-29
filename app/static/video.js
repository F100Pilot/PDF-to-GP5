// YouTube video beside the score / 3D highway, kept in step with the score playback.
// The official embed player is driven through its postMessage protocol (enablejsapi=1), so no
// YouTube script runs in this page; only the embed frame itself is allowed by the CSP (frame-src).
(() => {
  "use strict";

  // Embed players, tried in this order: the privacy-enhanced one first; the regular one when the
  // first refuses to play in this page (some browsers' tracking protection breaks it).
  const PLAYER_HOSTS = ["https://www.youtube-nocookie.com", "https://www.youtube.com"];
  const RETRY_CODES = new Set([5, 152, 153]); // player / configuration errors, not the video owner's choice
  const OWNER_BLOCKED = new Set([101, 150]); // the owner does not allow the video outside YouTube
  const READY_TIMEOUT_MS = 10000;
  const ID_RE = /^[A-Za-z0-9_-]{11}$/;
  const DRIFT_S = 0.35; // re-sync the video when it drifts more than this from the score
  const DRIFT_CHECK_MS = 2000;

  const panel = document.getElementById("video-panel");
  const toggle = document.getElementById("video-toggle");
  const stageBox = document.getElementById("score-stage");
  const urlInput = document.getElementById("video-url");
  const loadButton = document.getElementById("video-load");
  const frameBox = document.getElementById("video-frame");
  const offsetInput = document.getElementById("video-offset");
  const syncInput = document.getElementById("video-sync");
  const muteInput = document.getElementById("video-mute-score");
  const statusLine = document.getElementById("video-status");
  const resultsLabel = document.getElementById("video-results-label");
  const resultsSelect = document.getElementById("video-results");
  const manualHint = document.getElementById("video-manual");
  const searchLink = document.getElementById("video-search-link");

  // The server can search YouTube only when it has an API key (see README).
  let canSearch = false;
  fetch("/api/health")
    .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
    .then((health) => {
      canSearch = Boolean(health.video_search);
      const reason = document.getElementById("video-manual-reason");
      reason.textContent = health.video_search_problem ? ` (${health.video_search_problem})` : "";
    })
    .catch(() => {});

  let frame = null;
  let origin = PLAYER_HOSTS[0];
  let current = null; // { id, host } of the video in the frame
  let readyTimer = 0;
  const openLink = document.getElementById("video-open");
  let ready = false;
  let songKey = "";
  let onMuteScore = () => {};
  const song = { ms: 0, speed: 1, playing: false }; // score position (song time) and state
  let lastDriftFix = 0;
  // Last time reported by the player: { time (s), at (performance.now()), playing, rate }.
  let video = null;

  // Why the embed player refused the video (YouTube IFrame player error codes).
  const PLAYER_ERRORS = {
    2: "Endereço de vídeo inválido.",
    5: "O leitor do YouTube não conseguiu reproduzir este vídeo.",
    100: "O vídeo não existe ou é privado.",
    101: "O dono do vídeo não permite vê-lo fora do YouTube. Escolha outro vídeo (por exemplo um lyric video ou só áudio).",
    150: "O dono do vídeo não permite vê-lo fora do YouTube. Escolha outro vídeo (por exemplo um lyric video ou só áudio).",
    152: "O YouTube recusou o leitor nesta página.",
    153: "O YouTube recusou o leitor nesta página (configuração do leitor). Tente outro browser ou abra o vídeo no YouTube.",
  };

  // Current video time, extrapolated from the player's last report; null when never reported.
  function videoTime() {
    if (!video) return null;
    const elapsed = video.playing ? ((performance.now() - video.at) / 1000) * video.rate : 0;
    return video.time + elapsed;
  }

  function setStatus(text) {
    statusLine.textContent = text;
    statusLine.hidden = !text;
  }

  // "https://www.youtube.com/watch?v=ID&t=12s", "https://youtu.be/ID", "/embed/ID", "/shorts/ID" or the
  // bare 11-character ID -> { id, start } (start in seconds from a "t" parameter), or null.
  function parseVideo(text) {
    const value = text.trim();
    if (ID_RE.test(value)) return { id: value, start: null };
    let url;
    try {
      url = new URL(value);
    } catch {
      return null;
    }
    const host = url.hostname.replace(/^(www|m|music)\./, "");
    let id = null;
    if (host === "youtu.be") id = url.pathname.slice(1);
    else if (host === "youtube.com" || host === "youtube-nocookie.com") {
      id = url.searchParams.get("v") || (url.pathname.match(/^\/(?:embed|shorts|live)\/([^/?#]+)/) || [])[1];
    }
    if (!id || !ID_RE.test(id)) return null;
    const t = url.searchParams.get("t") || url.searchParams.get("start");
    const start = t && /^\d+s?$/.test(t) ? Number.parseInt(t, 10) : null;
    return { id, start };
  }

  function send(func, args = []) {
    if (!frame || !frame.contentWindow) return;
    frame.contentWindow.postMessage(JSON.stringify({ event: "command", func, args }), origin);
  }

  function offset() {
    const value = Number(offsetInput.value);
    return Number.isFinite(value) ? value : 0;
  }

  // Where the video should be for the current score position (song time, independent of speed).
  function expectedTime() {
    return Math.max(0, offset() + song.ms / 1000);
  }

  function seekVideo() {
    send("seekTo", [expectedTime(), true]);
  }

  function saveSettings() {
    if (!songKey) return;
    try {
      localStorage.setItem(`pdf-to-gp5.video.${songKey}`, JSON.stringify({ url: urlInput.value, offset: offset() }));
    } catch { /* storage unavailable */ }
  }

  // Link to watch the video on youtube.com (from the start of the song) when it cannot play here.
  function offerOpenOnYouTube(show) {
    openLink.hidden = !show || !current;
    if (current) {
      const params = new URLSearchParams({ v: current.id });
      if (offset() > 0) params.set("t", `${Math.floor(offset())}s`);
      openLink.href = `https://www.youtube.com/watch?${params}`;
    }
  }

  function playerFailed(message) {
    clearTimeout(readyTimer);
    if (current && current.host + 1 < PLAYER_HOSTS.length) {
      showPlayer(current.id, current.host + 1); // try the regular player
      return;
    }
    setStatus(message);
    offerOpenOnYouTube(true);
  }

  function showPlayer(id, host) {
    clearTimeout(readyTimer);
    current = { id, host };
    origin = PLAYER_HOSTS[host];
    ready = false;
    video = null;
    offerOpenOnYouTube(false);
    frame = document.createElement("iframe");
    frame.title = "Vídeo do YouTube";
    frame.allow = "autoplay; encrypted-media; picture-in-picture; fullscreen";
    frame.referrerPolicy = "strict-origin-when-cross-origin"; // the embed needs to know the page origin
    const params = new URLSearchParams({ enablejsapi: "1", origin: window.location.origin, rel: "0", playsinline: "1" });
    frame.src = `${origin}/embed/${id}?${params}`;
    const thisFrame = frame;
    frame.addEventListener("load", () => {
      // Ask the player to report its state and time (infoDelivery messages).
      thisFrame.contentWindow.postMessage(JSON.stringify({ event: "listening", id, channel: "widget" }), PLAYER_HOSTS[host]);
    });
    frameBox.replaceChildren(frame);
    setStatus("A carregar o vídeo… (precisa de ligação à internet)");
    readyTimer = setTimeout(() => {
      if (!ready && frame === thisFrame) playerFailed("O leitor do YouTube não respondeu nesta página (bloqueio do browser ou da rede?).");
    }, READY_TIMEOUT_MS);
  }

  function loadVideo() {
    const parsed = parseVideo(urlInput.value);
    if (!parsed) {
      setStatus("Endereço do YouTube não reconhecido. Exemplo: https://www.youtube.com/watch?v=…");
      return;
    }
    if (parsed.start !== null && !Number(offsetInput.value)) offsetInput.value = String(parsed.start);
    showPlayer(parsed.id, 0);
    saveSettings();
  }

  window.addEventListener("message", (event) => {
    if (!frame || event.origin !== origin || event.source !== frame.contentWindow) return;
    let data;
    try {
      data = typeof event.data === "string" ? JSON.parse(event.data) : event.data;
    } catch {
      return;
    }
    if (!data || typeof data !== "object") return;
    if (data.event === "onError") {
      const code = Number(data.info);
      const message = PLAYER_ERRORS[code] || `O leitor do YouTube indicou um erro (${code}).`;
      if (RETRY_CODES.has(code)) {
        playerFailed(message);
      } else if (OWNER_BLOCKED.has(code) && tryNextResult()) {
        // another search result is loading
      } else {
        clearTimeout(readyTimer);
        setStatus(message);
        offerOpenOnYouTube(true);
      }
      return;
    }
    if (data.event === "onReady" || (data.event === "infoDelivery" && !ready)) {
      ready = true;
      clearTimeout(readyTimer);
      setStatus("");
      send("setPlaybackRate", [song.speed]);
    }
    const info = data.event === "infoDelivery" && data.info && typeof data.info === "object" ? data.info : null;
    const time = info ? info.currentTime : undefined;
    if (info) {
      const previous = video || { time: 0, playing: false, rate: 1 };
      video = {
        time: typeof time === "number" ? time : videoTime() ?? previous.time,
        at: performance.now(),
        playing: typeof info.playerState === "number" ? info.playerState === 1 : previous.playing,
        rate: typeof info.playbackRate === "number" && info.playbackRate > 0 ? info.playbackRate : previous.rate,
      };
    }
    if (typeof time === "number" && song.playing && syncInput.checked) {
      const now = performance.now();
      if (now - lastDriftFix > DRIFT_CHECK_MS && Math.abs(time - expectedTime()) > DRIFT_S) {
        lastDriftFix = now;
        seekVideo();
      }
    }
  });

  function showPanel(open) {
    panel.hidden = !open;
    stageBox.classList.toggle("with-video", open);
    toggle.setAttribute("aria-pressed", String(open));
    window.dispatchEvent(new Event("resize")); // let the score / highway take the new width
  }

  function watchUrl(id) {
    return `https://www.youtube.com/watch?v=${id}`;
  }

  // Search results already tried in this page (skipped when the owner blocks embedding).
  const tried = new Set();

  function tryNextResult() {
    if (!current) return false;
    tried.add(current.id);
    const next = Array.from(resultsSelect.options).find((option) => !tried.has(option.value));
    if (!next) return false;
    resultsSelect.value = next.value;
    urlInput.value = watchUrl(next.value);
    setStatus("O dono deste vídeo não permite vê-lo fora do YouTube: a tentar o resultado seguinte…");
    showPlayer(next.value, 0);
    saveSettings();
    return true;
  }

  // Find the song's video ("artist title") and show the first result; the others stay selectable.
  async function findVideo(query) {
    resultsLabel.hidden = true;
    tried.clear();
    if (!canSearch || !query) return false;
    setStatus("A procurar o vídeo no YouTube…");
    try {
      const response = await fetch(`/api/video-search?${new URLSearchParams({ q: query })}`);
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : "Pesquisa falhou.");
      const results = Array.isArray(payload.results) ? payload.results.filter((r) => ID_RE.test(r.id)) : [];
      if (!results.length) {
        setStatus("Nenhum vídeo encontrado. Pode colar o endereço de um vídeo.");
        return false;
      }
      resultsSelect.replaceChildren(...results.map((result) => {
        const option = document.createElement("option");
        option.value = result.id;
        option.textContent = result.channel ? `${result.title} — ${result.channel}` : result.title;
        return option;
      }));
      resultsLabel.hidden = results.length < 2;
      urlInput.value = watchUrl(results[0].id);
      loadVideo();
      return true;
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Pesquisa falhou.");
      return false;
    }
  }

  toggle.addEventListener("click", () => showPanel(panel.hidden));
  resultsSelect.addEventListener("change", () => {
    urlInput.value = watchUrl(resultsSelect.value);
    offsetInput.value = "0";
    loadVideo();
  });
  loadButton.addEventListener("click", loadVideo);
  urlInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      loadVideo();
    }
  });
  function setOffset(seconds) {
    offsetInput.value = String(Math.max(0, Math.round(seconds * 100) / 100));
    saveSettings();
    if (syncInput.checked && song.playing) seekVideo();
  }

  offsetInput.addEventListener("change", () => {
    saveSettings();
    if (syncInput.checked) seekVideo();
  });
  // "Marcar início": the video time now is where bar 1 starts.
  document.getElementById("video-mark").addEventListener("click", () => {
    const now = videoTime();
    if (now === null) {
      setStatus("O leitor ainda não indicou o tempo do vídeo: ponha o vídeo a tocar e volte a carregar.");
      return;
    }
    setOffset(now);
    setStatus(`Início marcado aos ${Number(offsetInput.value).toFixed(2)} s.`);
  });
  for (const button of document.querySelectorAll("[data-nudge]")) {
    button.addEventListener("click", () => setOffset(offset() + Number(button.dataset.nudge)));
  }
  muteInput.addEventListener("change", () => onMuteScore(muteInput.checked));

  window.VideoSync = {
    // Called by the score viewer.
    // A new song: reuse the video chosen for it before, else search YouTube for "artist title".
    async setSong(key, muteScore, query) {
      songKey = key || "";
      onMuteScore = muteScore;
      onMuteScore(muteInput.checked);
      searchLink.href = `https://www.youtube.com/results?${new URLSearchParams({ search_query: query || "" })}`;
      manualHint.hidden = canSearch;
      let saved = null;
      try {
        saved = JSON.parse(localStorage.getItem(`pdf-to-gp5.video.${songKey}`) || "null");
      } catch { /* storage unavailable or bad data */ }
      if (saved && typeof saved.url === "string" && parseVideo(saved.url)) {
        urlInput.value = saved.url;
        offsetInput.value = String(Number(saved.offset) || 0);
        showPanel(true);
        loadVideo();
      } else if (await findVideo(query)) {
        offsetInput.value = "0";
        showPanel(true);
      }
    },
    // Score position: `realMs` as reported by alphaTab (scaled by the speed), `speed` the playback speed.
    position(realMs, speed, isSeek) {
      song.speed = speed || 1;
      song.ms = realMs * song.speed;
      if (isSeek && syncInput.checked) seekVideo();
    },
    playing(isPlaying) {
      song.playing = isPlaying;
      if (!syncInput.checked) return;
      if (isPlaying) {
        seekVideo();
        send("playVideo");
      } else {
        send("pauseVideo");
      }
    },
    speed(rate) {
      song.speed = rate;
      send("setPlaybackRate", [rate]);
    },
    parseVideo, // exposed for tests
  };
})();
