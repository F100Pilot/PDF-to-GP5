// The song's audio (mp3/ogg/wav) chosen by the user.
// * It plays in step with the score, like the video: Tocar (here or on the score), pause, stop,
//   the time bar and the speed drive both. Bar 1 starts "offset" seconds into the audio. Its
//   controls (with the music's and the notes' volumes) sit beside the score.
// * With it, the download is a Guitar Pro 7/8 file (.gp) carrying the audio as its audio track,
//   built in the browser (the audio never leaves this computer); without it, the GP5 file.
(() => {
  "use strict";

  const MAX_AUDIO_BYTES = 100 * 1024 * 1024;
  const DRIFT_S = 0.25; // re-sync the audio when it drifts more than this from the score
  const DRIFT_CHECK_MS = 1000;
  const download = document.getElementById("download");
  const fileInput = document.getElementById("audio-file");
  const chooseButton = document.getElementById("audio-choose");
  const removeButton = document.getElementById("audio-remove");
  const nameLabel = document.getElementById("audio-name");
  const panel = document.getElementById("audio-panel");
  const stageBox = document.getElementById("score-stage");
  const panelName = document.getElementById("audio-panel-name");
  const musicVolume = document.getElementById("music-volume");
  const notesVolume = document.getElementById("notes-volume");
  const player = document.getElementById("audio-preview");
  const playButton = document.getElementById("audio-play");
  const timeLabel = document.getElementById("audio-time");
  const offsetInput = document.getElementById("audio-offset");
  const tempoInput = document.getElementById("audio-tempo");
  const syncInput = document.getElementById("audio-sync");
  const statusLine = document.getElementById("audio-status");
  const lastLabel = document.getElementById("audio-last");
  const panelBody = document.getElementById("audio-panel-body");
  const collapseButton = document.getElementById("audio-collapse");
  const hideButton = document.getElementById("audio-hide");
  const toggleButton = document.getElementById("audio-toggle");
  const reopenButton = document.getElementById("audio-reopen");
  const COLLAPSED_KEY = "pdf-to-gp5.audio-panel-collapsed";
  const MUSIC_KEY = "pdf-to-gp5.music-volume";
  const NOTES_KEY = "pdf-to-gp5.notes-volume";

  let audio = null; // Uint8Array of the chosen file
  let playerUrl = null;
  let building = false;
  let lastDriftFix = 0;
  let waiting = false; // playing, but bar 1 is set before the audio starts: the audio waits
  let baseTempo = 120; // the score's printed tempo
  const song = { ms: 0, speed: 1, playing: false }; // score position (song time), the audio's speed, state
  const MIN_OFFSET = -60;
  const MAX_OFFSET = 3600;

  function setStatus(text) {
    statusLine.textContent = text;
    statusLine.hidden = !text;
  }

  // Known audio containers by their first bytes (the file name alone may lie).
  function isAudio(bytes) {
    const ascii = (start, text) => [...text].every((ch, i) => bytes[start + i] === ch.charCodeAt(0));
    return (
      ascii(0, "ID3") || // mp3 with tags
      (bytes[0] === 0xff && (bytes[1] & 0xe0) === 0xe0) || // mp3 frame
      ascii(0, "OggS") ||
      (ascii(0, "RIFF") && ascii(8, "WAVE"))
    );
  }

  function formatTime(seconds) {
    const whole = Math.max(0, Math.floor(seconds || 0));
    return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
  }

  // Where bar 1 starts in the audio (seconds); negative: before the audio starts.
  function offset() {
    const value = Number(offsetInput.value);
    return Number.isFinite(value) ? Math.min(Math.max(value, MIN_OFFSET), MAX_OFFSET) : 0;
  }

  // The audio follows the score only when there is audio and "Tocar com a partitura" is on.
  function following() {
    return Boolean(audio) && syncInput.checked;
  }

  // Where the audio should be for the current score position (a score set to another tempo than
  // the printed one covers the recording at that rate).
  function expectedTime() {
    return offset() + song.ms / 1000 / window.ScoreView.tempoFactor();
  }

  function seekAudio() {
    const target = expectedTime();
    if (target < 0) {
      // The score starts before the audio: hold the audio at its start until its time comes.
      player.currentTime = 0;
      waiting = true;
      if (!player.paused) player.pause();
      return;
    }
    waiting = false;
    player.currentTime = Number.isFinite(player.duration) ? Math.min(target, player.duration) : target;
  }

  function startAudio() {
    if (waiting) return; // position() starts it when the score reaches the audio's start
    player.playbackRate = song.speed;
    player.play().catch(() => setStatus("O browser não deixou tocar o áudio: carregue outra vez em Tocar."));
  }

  function showState() {
    const playing = following() ? song.playing : !player.paused && !waiting;
    playButton.querySelector(".audio-play-icon").textContent = playing ? "❚❚" : "▶";
    playButton.querySelector(".audio-play-label").textContent = playing ? "Pausa" : "Tocar";
    playButton.setAttribute("aria-label", playing ? "Pausa" : "Tocar");
    timeLabel.textContent = `${formatTime(player.currentTime)} / ${formatTime(player.duration)}`;
  }

  // The panel sits in the column beside the score (with the video panel, when open). `loaded`:
  // there is audio; the user may still hide the panel (the audio keeps playing) and bring it
  // back with the tab on the score's edge or "Mostrar áudio", or collapse it to a strip.
  let panelHidden = false;

  const videoPanel = document.getElementById("video-panel");

  // Collapsed, the panel folds to a narrow strip at the side (Tocar and expand) and the score
  // takes the width; with the video panel also open the column stays wide for it, and the audio
  // panel shrinks to its title row and Tocar.
  function layoutStage() {
    const narrow = !panel.hidden && panel.classList.contains("collapsed") && videoPanel.hidden;
    if (stageBox.classList.contains("side-collapsed") === narrow) return;
    stageBox.classList.toggle("side-collapsed", narrow);
    window.dispatchEvent(new Event("resize")); // let the score / highway take the new width
  }

  function showPanel(loaded) {
    const open = loaded && !panelHidden;
    toggleButton.hidden = !loaded;
    toggleButton.setAttribute("aria-pressed", String(open));
    toggleButton.textContent = open ? "Esconder áudio" : "Mostrar áudio";
    // Closed with ✕: a tab at the score's right edge brings the panel back.
    reopenButton.hidden = !loaded || open;
    if (panel.hidden === !open) return;
    panel.hidden = !open;
    stageBox.classList.toggle("with-side", open || !videoPanel.hidden);
    layoutStage();
    window.dispatchEvent(new Event("resize")); // let the score / highway take the new width
  }

  function setCollapsed(collapsed) {
    panelBody.hidden = collapsed;
    panel.classList.toggle("collapsed", collapsed);
    collapseButton.textContent = collapsed ? "◂" : "▸";
    collapseButton.setAttribute("aria-expanded", String(!collapsed));
    collapseButton.title = collapsed ? "Expandir o painel do áudio" : "Recolher o painel para o lado (a partitura fica mais larga)";
    collapseButton.setAttribute("aria-label", collapsed ? "Expandir o painel do áudio" : "Recolher o painel do áudio");
    layoutStage();
    try {
      localStorage.setItem(COLLAPSED_KEY, collapsed ? "1" : "0");
    } catch {
      // storage blocked: the choice lasts until the page is reloaded
    }
  }

  // The video panel opening or closing changes how a collapsed audio panel is laid out.
  new MutationObserver(layoutStage).observe(videoPanel, { attributes: true, attributeFilter: ["hidden"] });
  collapseButton.addEventListener("click", () => setCollapsed(!panel.classList.contains("collapsed")));
  hideButton.addEventListener("click", () => {
    panelHidden = true;
    showPanel(Boolean(audio));
    reopenButton.focus();
  });
  toggleButton.addEventListener("click", () => {
    panelHidden = !panelHidden;
    showPanel(Boolean(audio));
  });
  reopenButton.addEventListener("click", () => {
    panelHidden = false;
    showPanel(Boolean(audio));
    hideButton.focus();
  });
  try {
    setCollapsed(localStorage.getItem(COLLAPSED_KEY) === "1");
  } catch {
    setCollapsed(false);
  }

  // Volumes (0–100), remembered in this browser; the notes' volume applies while there is audio.
  function stored(key, fallback) {
    try {
      const value = Number(localStorage.getItem(key));
      return localStorage.getItem(key) !== null && Number.isFinite(value) ? Math.min(Math.max(value, 0), 100) : fallback;
    } catch {
      return fallback;
    }
  }

  function applyVolumes() {
    player.volume = Number(musicVolume.value) / 100;
    document.getElementById("music-volume-value").textContent = `${musicVolume.value}%`;
    document.getElementById("notes-volume-value").textContent = `${notesVolume.value}%`;
    window.ScoreView.setNotesVolume(audio ? Number(notesVolume.value) / 100 : 1);
  }

  for (const [input, key] of [[musicVolume, MUSIC_KEY], [notesVolume, NOTES_KEY]]) {
    input.value = String(stored(key, Number(input.value)));
    input.addEventListener("input", () => {
      applyVolumes();
      try {
        localStorage.setItem(key, input.value);
      } catch { /* storage unavailable */ }
    });
  }

  applyVolumes();

  function updateLink() {
    download.textContent = audio ? "Descarregar .gp (com áudio)" : "Descarregar .gp5";
  }

  // Loudness of the audio every WAVE_STEP seconds (0…1), drawn on the 3D highway's floor.
  const WAVE_STEP = 0.05;

  async function waveform(bytes) {
    const context = new OfflineAudioContext(1, 1, 44100);
    const buffer = await context.decodeAudioData(bytes.slice().buffer); // decoding takes the buffer
    const size = Math.max(1, Math.round(buffer.sampleRate * WAVE_STEP));
    const channels = Array.from({ length: buffer.numberOfChannels }, (_, c) => buffer.getChannelData(c));
    const peaks = new Float32Array(Math.ceil(buffer.length / size));
    let loudest = 0;
    for (let i = 0; i < peaks.length; i += 1) {
      let peak = 0;
      const end = Math.min(buffer.length, (i + 1) * size);
      for (const data of channels) {
        for (let j = i * size; j < end; j += 4) peak = Math.max(peak, Math.abs(data[j]));
      }
      peaks[i] = peak;
      loudest = Math.max(loudest, peak);
    }
    if (loudest > 0) for (let i = 0; i < peaks.length; i += 1) peaks[i] /= loudest;
    return { peaks, step: WAVE_STEP };
  }

  function clearAudio() {
    window.Highway3D.setWaveform(null);
    player.pause();
    audio = null;
    fileInput.value = "";
    player.removeAttribute("src");
    player.load();
    if (playerUrl) URL.revokeObjectURL(playerUrl);
    playerUrl = null;
    showPanel(false);
    removeButton.hidden = true;
    nameLabel.textContent = "Nenhum ficheiro";
    showLastFile();
    applyVolumes();
    setStatus("");
    updateLink();
  }

  chooseButton.addEventListener("click", () => fileInput.click());
  removeButton.addEventListener("click", () => {
    clearAudio();
    document.dispatchEvent(new CustomEvent("song-audio", { detail: { file: null } }));
  });

  fileInput.addEventListener("change", () => {
    const file = fileInput.files && fileInput.files[0];
    if (file) useAudioFile(file);
  });

  // Use `file` (chosen here, or obtained from a URL) as the song's audio.
  async function useAudioFile(file) {
    if (file.size > MAX_AUDIO_BYTES) {
      clearAudio();
      setStatus(`O áudio tem ${Math.round(file.size / 1048576)} MB; o máximo é ${MAX_AUDIO_BYTES / 1048576} MB.`);
      return;
    }
    const bytes = new Uint8Array(await file.arrayBuffer());
    if (!isAudio(bytes)) {
      clearAudio();
      setStatus("O ficheiro não parece ser áudio mp3, ogg ou wav.");
      return;
    }
    player.pause();
    audio = bytes;
    if (playerUrl) URL.revokeObjectURL(playerUrl);
    playerUrl = URL.createObjectURL(file);
    player.src = playerUrl;
    nameLabel.textContent = file.name;
    nameLabel.title = file.name;
    remember({ file: file.name.slice(0, 200) });
    showLastFile();
    panelName.textContent = file.name;
    panelName.title = file.name;
    panelHidden = false; // a new audio shows its panel
    showPanel(true);
    removeButton.hidden = false;
    applyVolumes();
    setStatus("");
    updateLink();
    window.Highway3D.setWaveformSync(offset(), window.ScoreView.tempoFactor());
    document.dispatchEvent(new CustomEvent("song-audio", { detail: { file } })); // kept in the library
    waveform(bytes)
      .then((data) => {
        if (audio === bytes) window.Highway3D.setWaveform(data);
      })
      .catch(() => setSyncStatus("Não foi possível desenhar o áudio na pista 3D (formato não suportado pelo browser)."));
    if (following() && song.playing) {
      seekAudio();
      startAudio();
    }
    showState();
  }

  // Tocar here: the score (and so the audio) when they play together, else the audio alone.
  playButton.addEventListener("click", () => {
    if (following() && window.ScoreView.ready()) {
      window.ScoreView.playPause();
    } else if (player.paused) {
      startAudio();
    } else {
      player.pause();
    }
  });

  player.addEventListener("timeupdate", showState);
  player.addEventListener("loadedmetadata", showState);
  player.addEventListener("play", showState);
  player.addEventListener("pause", showState);
  player.addEventListener("ended", () => {
    if (following() && song.playing) window.ScoreView.playPause(); // the recording is over
  });

  syncInput.addEventListener("change", () => {
    if (!audio) return;
    if (following() && song.playing) {
      seekAudio();
      startAudio();
    } else if (following()) {
      player.pause();
    }
    showState();
  });

  const syncStatus = document.getElementById("audio-sync-status");

  function setSyncStatus(text) {
    syncStatus.textContent = text;
    syncStatus.hidden = !text;
  }

  const decimal = (value) => value.toFixed(2).replace(".", ",");

  // Per song (artist - title), remembered in this browser: where bar 1 starts in the audio, the
  // score's tempo and the audio file's name (a file cannot be reopened by the page itself).
  let songKey = "";

  function remembered() {
    try {
      const saved = songKey ? JSON.parse(localStorage.getItem(`pdf-to-gp5.audio.${songKey}`) || "null") : null;
      return saved && typeof saved === "object" ? saved : null;
    } catch {
      return null;
    }
  }

  function remember(changes) {
    if (!songKey) return;
    try {
      localStorage.setItem(`pdf-to-gp5.audio.${songKey}`, JSON.stringify({ ...remembered(), ...changes }));
    } catch { /* storage unavailable */ }
  }

  function showLastFile() {
    const saved = remembered();
    lastLabel.hidden = Boolean(audio) || !saved || typeof saved.file !== "string";
    lastLabel.textContent = lastLabel.hidden ? "" : `(da última vez: ${saved.file})`;
  }

  // The start is shown and kept to the hundredth of a second.
  function showOffset(seconds) {
    offsetInput.value = (Math.round(Math.min(Math.max(seconds, MIN_OFFSET), MAX_OFFSET) * 100) / 100).toFixed(2);
  }

  function setOffset(seconds) {
    showOffset(seconds);
    remember({ offset: offset() });
    if (following() && song.playing) {
      seekAudio();
      startAudio();
    }
    window.Highway3D.setWaveformSync(offset(), window.ScoreView.tempoFactor());
  }

  // Delaying the score = bar 1 later in the audio (the audio is ahead of the score by more).
  function nudgeScore(seconds) {
    const before = offset();
    setOffset(before + seconds);
    const moved = offset() - before;
    const where = offset() < 0 ? `${decimal(-offset())} s antes do início do áudio` : `aos ${decimal(offset())} s do áudio`;
    setSyncStatus(
      moved === 0
        ? "Limite do acerto atingido."
        : `Partitura ${moved > 0 ? "atrasada" : "adiantada"} ${decimal(Math.abs(moved))} s (compasso 1 ${where}).`,
    );
  }

  // Tempo the score plays at, to follow a recording that is not exactly at the printed tempo.
  function setTempo(bpm) {
    const value = Math.min(Math.max(Math.round(bpm * 10) / 10, 20), 400);
    tempoInput.value = String(value);
    window.ScoreView.setTempo(value);
    remember({ tempo: value });
    if (following() && song.playing) seekAudio();
    window.Highway3D.setWaveformSync(offset(), window.ScoreView.tempoFactor());
    setSyncStatus(
      value === baseTempo
        ? `Tempo do PDF (${String(baseTempo).replace(".", ",")} BPM).`
        : `Partitura a ${String(value).replace(".", ",")} BPM (no PDF: ${String(baseTempo).replace(".", ",")}).`,
    );
  }

  tempoInput.addEventListener("change", () => setTempo(Number(tempoInput.value) || baseTempo));
  for (const button of document.querySelectorAll("[data-tempo-nudge]")) {
    button.addEventListener("click", () => setTempo((Number(tempoInput.value) || baseTempo) + Number(button.dataset.tempoNudge)));
  }
  document.getElementById("audio-tempo-reset").addEventListener("click", () => setTempo(baseTempo));

  offsetInput.addEventListener("change", () => setOffset(offset()));
  tempoInput.value = String(baseTempo);
  // "Marcar início": bar 1 starts at the audio's current time; the score restarts there.
  document.getElementById("audio-mark").addEventListener("click", () => {
    showOffset(player.currentTime);
    remember({ offset: offset() });
    if (following()) window.ScoreView.restart();
    window.Highway3D.setWaveformSync(offset(), window.ScoreView.tempoFactor());
    setSyncStatus(`Início marcado aos ${offset().toFixed(2).replace(".", ",")} s do áudio.`);
  });
  for (const button of document.querySelectorAll("[data-audio-nudge]")) {
    button.addEventListener("click", () => nudgeScore(Number(button.dataset.audioNudge)));
  }

  window.AudioSync = {
    useFile: (file) => useAudioFile(file),
    // Show the panel again after it was closed with ✕ (the tab by the score and "Mostrar áudio" do the same).
    showPanel() {
      panelHidden = false;
      showPanel(Boolean(audio));
    },
    hasAudio: () => Boolean(audio),
    // Delay (+) or advance (−) the score by `seconds` against the audio (keyboard [ and ]).
    nudge(seconds) {
      if (audio) nudgeScore(seconds);
    },
    // A new song: its printed tempo, which the score plays at until the tempo is adjusted.
    // `key`: "artist - title", under which this song's start and tempo are remembered.
    songLoaded(tempo, key) {
      baseTempo = tempo > 0 ? tempo : 120;
      songKey = key || "";
      const saved = remembered() || {};
      const savedOffset = Number(saved.offset);
      showOffset(Number.isFinite(savedOffset) ? savedOffset : 0);
      const savedTempo = Number(saved.tempo);
      const tempoToUse = Number.isFinite(savedTempo) && savedTempo >= 20 && savedTempo <= 400 ? savedTempo : baseTempo;
      tempoInput.value = String(tempoToUse);
      if (tempoToUse !== baseTempo) window.ScoreView.setTempo(tempoToUse);
      window.Highway3D.setWaveformSync(offset(), window.ScoreView.tempoFactor());
      const notes = [];
      if (offset() > 0) notes.push(`início aos ${decimal(offset())} s do áudio`);
      if (offset() < 0) notes.push(`início ${decimal(-offset())} s antes do áudio`);
      if (tempoToUse !== baseTempo) notes.push(`tempo ${String(tempoToUse).replace(".", ",")} BPM`);
      setSyncStatus(notes.length ? `Acerto guardado desta música: ${notes.join(", ")}.` : "");
      showLastFile();
    },
    // Score position: `realMs` as reported by alphaTab (scaled by the speed), `scoreSpeed` the
    // score's playback speed (the chosen speed times the tempo adjustment).
    position(realMs, scoreSpeed, isSeek) {
      song.ms = realMs * (scoreSpeed || 1);
      if (!following()) return;
      const now = performance.now();
      if (isSeek) {
        seekAudio();
        if (song.playing) startAudio();
      } else if (waiting) {
        if (song.playing && expectedTime() >= 0) {
          seekAudio(); // the score has reached the audio's start
          startAudio();
        }
      } else if (song.playing && now - lastDriftFix > DRIFT_CHECK_MS && Math.abs(player.currentTime - expectedTime()) > DRIFT_S) {
        lastDriftFix = now;
        seekAudio();
      }
    },
    playing(isPlaying) {
      song.playing = isPlaying;
      if (following()) {
        if (isPlaying) {
          seekAudio();
          startAudio();
        } else {
          waiting = false;
          player.pause();
        }
      }
      showState();
    },
    speed(rate) {
      song.speed = rate;
      player.playbackRate = rate;
    },
  };

  // --- Audio from a URL: the server gets it (yt-dlp) and converts it to MP3 (FFmpeg) ---
  // Only content that may be downloaded is processed (the server checks: direct file, Creative
  // Commons / public domain, or a declared own site). Progress is polled; the MP3 is fetched once
  // (the server then deletes it) and used here, with a link to save it.
  const urlBox = document.getElementById("audio-url-box");
  const urlForm = document.getElementById("audio-url-form");
  const urlInput = document.getElementById("audio-url");
  const bitrateSelect = document.getElementById("audio-bitrate");
  const authorizedInput = document.getElementById("audio-authorized");
  const startButton = document.getElementById("audio-url-start");
  const cancelButton = document.getElementById("audio-url-cancel");
  const progressBox = document.getElementById("audio-url-progress");
  const progressBar = document.getElementById("audio-url-bar");
  const progressText = document.getElementById("audio-url-percent");
  const urlStatus = document.getElementById("audio-url-status");
  const saveLink = document.getElementById("audio-url-save");
  const POLL_MS = 700;
  let urlJob = null; // id of the job in progress
  let urlCancelled = false;
  let savedUrl = null;

  function setUrlStatus(text, error = false) {
    urlStatus.textContent = text;
    urlStatus.hidden = !text;
    urlStatus.classList.toggle("error-text", error);
  }

  function setProgress(percent) {
    progressBox.hidden = percent === null;
    progressBar.value = percent || 0;
    progressText.textContent = `${percent || 0}%`;
  }

  function busy(on) {
    startButton.disabled = on;
    urlInput.disabled = on;
    bitrateSelect.disabled = on;
    cancelButton.hidden = !on;
  }

  async function detail(response, fallback) {
    const body = await response.json().catch(() => ({}));
    return typeof body.detail === "string" ? body.detail : fallback;
  }

  fetch("/api/health")
    .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
    .then((health) => {
      if (!health.audio_download) {
        const note = document.getElementById("audio-url-unavailable");
        note.textContent = `Indisponível neste servidor: ${health.audio_download_problem || "falta o yt-dlp ou o FFmpeg"}.`;
        note.hidden = false;
        urlForm.hidden = true;
      } else if (!health.audio_youtube) {
        const note = document.getElementById("audio-url-youtube");
        note.textContent = `Vídeos do YouTube: ${health.audio_youtube_problem || "indisponíveis"}. Os outros endereços funcionam.`;
        note.hidden = false;
      }
    })
    .catch(() => {});

  urlForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (urlJob) return;
    const url = urlInput.value.trim();
    // YouTube: only the video id is sent (the server checks it again and builds the address).
    const video = window.VideoSync && window.VideoSync.parseVideo(url);
    if (!video && !/^https?:\/\/\S+$/i.test(url)) {
      setUrlStatus("Indique um endereço que comece por http:// ou https://, ou o ID de um vídeo do YouTube.", true);
      return;
    }
    if (!authorizedInput.checked) {
      setUrlStatus("Confirme que é para uso pessoal ou que tem autorização para descarregar este conteúdo.", true);
      return;
    }
    saveLink.hidden = true;
    if (savedUrl) URL.revokeObjectURL(savedUrl);
    savedUrl = null;
    busy(true);
    urlCancelled = false;
    setProgress(0);
    setUrlStatus("A pedir ao servidor…");
    try {
      const response = await fetch("/api/audio/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: video ? video.id : url, bitrate: Number(bitrateSelect.value), authorized: true }),
      });
      if (!response.ok) throw new Error(await detail(response, "O pedido foi recusado."));
      urlJob = (await response.json()).id;
      await followJob(urlJob);
    } catch (error) {
      if (urlCancelled) setUrlStatus("Cancelado.");
      else setUrlStatus(error instanceof Error ? error.message : "Não foi possível obter o áudio.", true);
      setProgress(null);
    } finally {
      urlJob = null;
      busy(false);
    }
  });

  async function followJob(id) {
    for (;;) {
      const response = await fetch(`/api/audio/jobs/${encodeURIComponent(id)}`);
      if (!response.ok) throw new Error(await detail(response, "A tarefa terminou sem resultado."));
      const job = await response.json();
      setProgress(job.progress);
      if (job.status === "done") {
        setUrlStatus("A receber o MP3…");
        const file = await fetch(`/api/audio/jobs/${encodeURIComponent(id)}/file`);
        if (!file.ok) throw new Error(await detail(file, "Não foi possível receber o MP3."));
        const blob = await file.blob();
        const name = job.filename || "audio.mp3";
        savedUrl = URL.createObjectURL(blob);
        saveLink.href = savedUrl;
        saveLink.download = name;
        savedMp3 = { blob, name };
        const folder = window.App && window.App.pdfFolder();
        saveLink.textContent = folder && window.showSaveFilePicker ? "Guardar o MP3 na pasta das partituras" : "Guardar o MP3";
        saveLink.hidden = false;
        setUrlStatus(`Pronto: ${name}. Já está a ser usado com a partitura.`);
        await useAudioFile(new File([blob], name, { type: "audio/mpeg" }));
        return;
      }
      if (job.status === "error" || job.status === "cancelled") throw new Error(job.message);
      setUrlStatus(job.message);
      await new Promise((resolve) => setTimeout(resolve, POLL_MS));
    }
  }

  // Save the MP3 next to the song's PDFs: the save dialog opens in their folder with the name
  // filled in (Chrome); without a known folder the link is a plain download.
  let savedMp3 = null;
  saveLink.addEventListener("click", async (event) => {
    const folder = window.App && window.App.pdfFolder();
    if (!folder || !window.showSaveFilePicker || !savedMp3) return;
    event.preventDefault();
    try {
      const target = await window.showSaveFilePicker({
        suggestedName: savedMp3.name,
        startIn: folder,
        types: [{ description: "Áudio MP3", accept: { "audio/mpeg": [".mp3"] } }],
      });
      const writable = await target.createWritable();
      await writable.write(savedMp3.blob);
      await writable.close();
      setUrlStatus(`MP3 guardado: ${target.name}.`);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      saveLink.textContent = "Guardar o MP3";
      setUrlStatus("Não foi possível guardar na pasta das partituras; carregue outra vez para descarregar.", true);
      savedMp3 = null;
    }
  });

  cancelButton.addEventListener("click", () => {
    if (!urlJob) return;
    urlCancelled = true;
    fetch(`/api/audio/jobs/${encodeURIComponent(urlJob)}`, { method: "DELETE" }).catch(() => {});
  });
  urlBox.addEventListener("toggle", () => {
    if (urlBox.open) urlInput.focus();
  });

  // With audio: build the .gp now and save it under the GP5's name with the .gp extension.
  download.addEventListener("click", async (event) => {
    if (!audio) return; // the GP5 link works as is
    event.preventDefault();
    if (building) return;
    building = true;
    setStatus("A preparar o ficheiro .gp…");
    try {
      const bytes = await window.ScoreView.exportGp(audio, offset() * 1000);
      const url = URL.createObjectURL(new Blob([bytes], { type: "application/octet-stream" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = (download.download || "musica.gp5").replace(/\.gp5$/i, "") + ".gp";
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
      setStatus("");
    } catch (error) {
      setStatus(error instanceof Error ? `Não foi possível criar o .gp: ${error.message}` : "Não foi possível criar o .gp.");
    } finally {
      building = false;
    }
  });
})();
