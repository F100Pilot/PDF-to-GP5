// Optional audio (mp3/ogg/wav) of the song: with it, the download is a Guitar Pro 7/8 file (.gp)
// carrying the audio as its audio track, built in the browser (the audio never leaves this computer);
// without it, the GP5 file from the server.
(() => {
  "use strict";

  const MAX_AUDIO_BYTES = 100 * 1024 * 1024;
  const download = document.getElementById("download");
  const fileInput = document.getElementById("audio-file");
  const tools = document.getElementById("audio-tools");
  const player = document.getElementById("audio-preview");
  const offsetInput = document.getElementById("audio-offset");
  const statusLine = document.getElementById("audio-status");
  const help = document.getElementById("audio-help");

  let audio = null; // Uint8Array of the chosen file
  let playerUrl = null;
  let building = false;

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

  function offsetSeconds() {
    const value = Number(offsetInput.value);
    return Number.isFinite(value) && value > 0 ? value : 0;
  }

  function updateLink() {
    download.textContent = audio ? "Descarregar .gp (com áudio)" : "Descarregar .gp5";
  }

  function clearAudio() {
    audio = null;
    fileInput.value = "";
    player.removeAttribute("src");
    if (playerUrl) URL.revokeObjectURL(playerUrl);
    playerUrl = null;
    tools.hidden = true;
    help.hidden = true;
    setStatus("");
    updateLink();
  }

  fileInput.addEventListener("change", async () => {
    const file = fileInput.files && fileInput.files[0];
    if (!file) {
      clearAudio();
      return;
    }
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
    audio = bytes;
    if (playerUrl) URL.revokeObjectURL(playerUrl);
    playerUrl = URL.createObjectURL(file);
    player.src = playerUrl;
    tools.hidden = false;
    help.hidden = false;
    setStatus("");
    updateLink();
  });

  document.getElementById("audio-remove").addEventListener("click", clearAudio);
  document.getElementById("audio-mark").addEventListener("click", () => {
    offsetInput.value = String(Math.round(player.currentTime * 100) / 100);
    setStatus(`Início marcado aos ${Number(offsetInput.value).toFixed(2)} s do áudio.`);
  });

  // With audio: build the .gp now and save it under the GP5's name with the .gp extension.
  download.addEventListener("click", async (event) => {
    if (!audio) return; // the GP5 link works as is
    event.preventDefault();
    if (building) return;
    building = true;
    setStatus("A preparar o ficheiro .gp…");
    try {
      const bytes = await window.ScoreView.exportGp(audio, offsetSeconds() * 1000);
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
