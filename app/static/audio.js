// The song's audio (mp3/ogg/wav) chosen by the user.
// * It plays in step with the score, like the video: Tocar (here or on the score), pause, stop,
//   the time bar and the speed drive both. Bar 1 starts "offset" seconds into the audio.
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
  const tools = document.getElementById("audio-tools");
  const player = document.getElementById("audio-preview");
  const playButton = document.getElementById("audio-play");
  const timeLabel = document.getElementById("audio-time");
  const offsetInput = document.getElementById("audio-offset");
  const syncInput = document.getElementById("audio-sync");
  const muteInput = document.getElementById("audio-mute-score");
  const statusLine = document.getElementById("audio-status");
  const help = document.getElementById("audio-help");

  let audio = null; // Uint8Array of the chosen file
  let playerUrl = null;
  let building = false;
  let lastDriftFix = 0;
  const song = { ms: 0, speed: 1, playing: false }; // score position (song time) and state

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

  function offset() {
    const value = Number(offsetInput.value);
    return Number.isFinite(value) && value > 0 ? value : 0;
  }

  // The audio follows the score only when there is audio and "Tocar com a partitura" is on.
  function following() {
    return Boolean(audio) && syncInput.checked;
  }

  // Where the audio should be for the current score position.
  function expectedTime() {
    return offset() + song.ms / 1000;
  }

  function seekAudio() {
    const target = expectedTime();
    player.currentTime = Number.isFinite(player.duration) ? Math.min(target, player.duration) : target;
  }

  function startAudio() {
    player.playbackRate = song.speed;
    player.play().catch(() => setStatus("O browser não deixou tocar o áudio: carregue outra vez em Tocar."));
  }

  function showState() {
    const playing = following() ? song.playing : !player.paused;
    playButton.textContent = playing ? "❚❚ Pausa" : "▶ Tocar";
    timeLabel.textContent = `${formatTime(player.currentTime)} / ${formatTime(player.duration)}`;
  }

  function updateLink() {
    download.textContent = audio ? "Descarregar .gp (com áudio)" : "Descarregar .gp5";
  }

  function clearAudio() {
    player.pause();
    audio = null;
    fileInput.value = "";
    player.removeAttribute("src");
    player.load();
    if (playerUrl) URL.revokeObjectURL(playerUrl);
    playerUrl = null;
    tools.hidden = true;
    help.hidden = true;
    removeButton.hidden = true;
    nameLabel.textContent = "Nenhum ficheiro";
    window.ScoreView.muteFor("audio", false);
    setStatus("");
    updateLink();
  }

  chooseButton.addEventListener("click", () => fileInput.click());
  removeButton.addEventListener("click", clearAudio);

  fileInput.addEventListener("change", async () => {
    const file = fileInput.files && fileInput.files[0];
    if (!file) return;
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
    tools.hidden = false;
    help.hidden = false;
    removeButton.hidden = false;
    window.ScoreView.muteFor("audio", muteInput.checked);
    setStatus("");
    updateLink();
    if (following() && song.playing) {
      seekAudio();
      startAudio();
    }
    showState();
  });

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
  muteInput.addEventListener("change", () => window.ScoreView.muteFor("audio", Boolean(audio) && muteInput.checked));

  function setOffset(seconds) {
    offsetInput.value = String(Math.max(0, Math.round(seconds * 100) / 100));
    if (following() && song.playing) seekAudio();
  }

  offsetInput.addEventListener("change", () => setOffset(offset()));
  // "Marcar início": bar 1 starts at the audio's current time; the score restarts there.
  document.getElementById("audio-mark").addEventListener("click", () => {
    offsetInput.value = String(Math.round(player.currentTime * 100) / 100);
    if (following()) window.ScoreView.restart();
    setStatus(`Início marcado aos ${offset().toFixed(2)} s do áudio.`);
  });
  for (const button of document.querySelectorAll("[data-audio-nudge]")) {
    button.addEventListener("click", () => setOffset(offset() + Number(button.dataset.audioNudge)));
  }

  window.AudioSync = {
    // Score position: `realMs` as reported by alphaTab (scaled by the speed), `speed` the playback speed.
    position(realMs, speed, isSeek) {
      song.speed = speed || 1;
      song.ms = realMs * song.speed;
      if (!following()) return;
      const now = performance.now();
      if (isSeek) {
        seekAudio();
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
