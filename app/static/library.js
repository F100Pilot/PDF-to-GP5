"use strict";

// Library: the songs converted in this browser, kept in IndexedDB with their report and the
// audio chosen for them, to be played again without converting. Nothing leaves the computer.
// One entry per song ("artist - title"): converting it again replaces it (keeping its audio).
(() => {
  const DB_NAME = "pdf-to-gp5";
  const STORE = "songs";
  const list = document.getElementById("library-list");
  const empty = document.getElementById("library-empty");
  const statusLine = document.getElementById("library-status");
  const search = document.getElementById("library-search");
  const usage = document.getElementById("library-usage");
  let songs = []; // summaries (no file contents), newest first
  let currentKey = null; // the song open now
  let restoring = false; // reopening a song: its audio is already stored
  let database = null;

  function setStatus(text) {
    statusLine.textContent = text;
    statusLine.hidden = !text;
  }

  function songKey(title, artist) {
    return `${(artist || "").trim()} - ${(title || "").trim()}`.toLowerCase();
  }

  function openDatabase() {
    if (!window.indexedDB) return Promise.reject(new Error("IndexedDB indisponível"));
    if (!database) {
      database = new Promise((resolve, reject) => {
        const request = indexedDB.open(DB_NAME, 1);
        request.onupgradeneeded = () => request.result.createObjectStore(STORE, { keyPath: "key" });
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
    }
    return database;
  }

  // Run `work(store)` in one transaction; resolves with the result of the request it returns.
  async function transaction(mode, work) {
    const db = await openDatabase();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, mode);
      const request = work(tx.objectStore(STORE));
      tx.oncomplete = () => resolve(request ? request.result : undefined);
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error);
    });
  }

  const getSong = (key) => transaction("readonly", (store) => store.get(key));
  const putSong = (song) => transaction("readwrite", (store) => store.put(song));
  const deleteSong = (key) => transaction("readwrite", (store) => store.delete(key));

  async function refresh() {
    try {
      const all = await transaction("readonly", (store) => store.getAll());
      songs = all
        .map(({ key, title, artist, tempo, measures, trackNames, savedAt, audio, cover }) => ({
          key, title, artist, tempo, measures, trackNames, savedAt, audioName: audio ? audio.name : "", cover: cover || null,
        }))
        .sort((a, b) => b.savedAt - a.savedAt);
      render();
      showUsage();
    } catch {
      songs = [];
      render();
      setStatus("A biblioteca não está disponível neste browser (por exemplo, numa janela privada).");
    }
  }

  function showUsage() {
    if (!navigator.storage || !navigator.storage.estimate) return;
    navigator.storage.estimate().then(({ usage: used }) => {
      if (used) usage.textContent = `Espaço usado por esta aplicação no browser: ${(used / 1048576).toFixed(1).replace(".", ",")} MB.`;
    }).catch(() => {});
  }

  const normalize = (text) => text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

  // Covers: the album cover from the internet (iTunes, through the server) or an image chosen here.
  const COVER_TYPES = ["image/jpeg", "image/png", "image/webp"];
  const MAX_COVER_BYTES = 5 * 1024 * 1024;
  let coverUrls = []; // object URLs of the covers on screen, released on the next render

  async function setCover(key, blob) {
    const song = await getSong(key);
    if (!song) return;
    song.cover = blob;
    await putSong(song);
    refresh();
  }

  // Look the cover up by artist and title; `quiet`: after a conversion, no message when not found.
  async function findCover(key, artist, title, quiet) {
    if (!artist || !title) {
      if (!quiet) setStatus("Sem artista e título não é possível procurar a capa: escolha uma imagem.");
      return;
    }
    try {
      const response = await fetch(`/api/cover?${new URLSearchParams({ artist, title })}`);
      if (response.ok) {
        const blob = await response.blob();
        if (COVER_TYPES.includes(blob.type)) {
          await setCover(key, blob);
          if (!quiet) setStatus("");
          return;
        }
      }
      if (!quiet) {
        const reason = response.status === 404 ? "Capa não encontrada" : "Não foi possível procurar a capa (sem ligação à internet?)";
        setStatus(`${reason}: pode escolher uma imagem.`);
      }
    } catch {
      if (!quiet) setStatus("Não foi possível procurar a capa (sem ligação ao servidor).");
    }
  }

  function coverFigure(song) {
    const figure = document.createElement("div");
    figure.className = "song-cover";
    if (song.cover) {
      const image = document.createElement("img");
      const url = URL.createObjectURL(song.cover);
      coverUrls.push(url);
      image.src = url;
      image.alt = `Capa de ${song.title || "a música"}`;
      figure.appendChild(image);
    } else {
      const initials = document.createElement("span");
      initials.setAttribute("aria-hidden", "true");
      initials.textContent = (song.title || "?").trim().slice(0, 1).toUpperCase();
      figure.appendChild(initials);
    }
    return figure;
  }

  function coverActions(song) {
    const row = document.createElement("div");
    row.className = "song-cover-actions";
    const search = document.createElement("button");
    search.type = "button";
    search.className = "link-button";
    search.textContent = song.cover ? "Procurar outra vez" : "Procurar capa";
    search.addEventListener("click", () => findCover(song.key, song.artist, song.title, false));
    const input = document.createElement("input");
    input.type = "file";
    input.accept = COVER_TYPES.join(",");
    input.hidden = true;
    input.addEventListener("change", () => {
      const file = input.files && input.files[0];
      if (!file) return;
      if (!COVER_TYPES.includes(file.type) || file.size > MAX_COVER_BYTES) {
        setStatus("A capa tem de ser uma imagem JPEG, PNG ou WebP até 5 MB.");
        return;
      }
      setCover(song.key, file).then(() => setStatus("")).catch(() => setStatus("Não foi possível guardar a capa."));
    });
    const choose = document.createElement("button");
    choose.type = "button";
    choose.className = "link-button";
    choose.textContent = "Escolher imagem";
    choose.addEventListener("click", () => input.click());
    row.append(search, choose, input);
    return row;
  }

  function card(song) {
    const item = document.createElement("li");
    const article = document.createElement("article");
    article.className = "card song-card";
    const title = document.createElement("h2");
    title.textContent = song.title || "Sem título";
    const artist = document.createElement("span");
    artist.className = "muted";
    artist.textContent = song.artist || "Artista desconhecido";
    const tags = document.createElement("div");
    tags.className = "song-tags";
    const labels = [
      `${song.trackNames.length} ${song.trackNames.length === 1 ? "track" : "tracks"}`,
      `${song.measures} compassos`,
      song.tempo ? `${song.tempo} BPM` : "",
      song.audioName ? "com áudio" : "",
      song.key === currentKey ? "aberta" : "",
    ];
    for (const label of labels.filter(Boolean)) {
      const tag = document.createElement("span");
      tag.textContent = label;
      tags.appendChild(tag);
    }
    const when = document.createElement("span");
    when.className = "hint";
    when.textContent = `Guardada em ${new Date(song.savedAt).toLocaleDateString("pt-PT")} · ${song.trackNames.join(", ")}`;
    const actions = document.createElement("div");
    actions.className = "song-actions";
    const play = document.createElement("button");
    play.type = "button";
    play.textContent = "Tocar";
    play.addEventListener("click", () => openSong(song.key));
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "danger";
    remove.textContent = "Remover";
    remove.setAttribute("aria-label", `Remover ${song.title || "a música"} da biblioteca`);
    let confirmTimer = null;
    remove.addEventListener("click", async () => {
      if (!remove.classList.contains("confirm")) { // two steps: nothing is removed by a stray click
        remove.classList.add("confirm");
        remove.textContent = "Confirmar";
        confirmTimer = setTimeout(() => {
          remove.classList.remove("confirm");
          remove.textContent = "Remover";
        }, 4000);
        return;
      }
      clearTimeout(confirmTimer);
      await deleteSong(song.key).catch(() => setStatus("Não foi possível remover a música."));
      refresh();
    });
    actions.append(play, remove);
    article.append(coverFigure(song), title, artist, tags, when, coverActions(song), actions);
    item.appendChild(article);
    return item;
  }

  function render() {
    const query = normalize(search.value.trim());
    const shown = songs.filter((song) => !query || normalize(`${song.title} ${song.artist}`).includes(query));
    for (const url of coverUrls) URL.revokeObjectURL(url);
    coverUrls = [];
    list.replaceChildren(...shown.map(card));
    empty.hidden = songs.length > 0;
    if (songs.length && !shown.length) setStatus("Nenhuma música corresponde à procura.");
    else if (statusLine.textContent === "Nenhuma música corresponde à procura.") setStatus("");
  }

  // Open a stored song: its result and score, then its audio once the score is loaded (the audio
  // settings are remembered per song and must apply to this one).
  async function openSong(key) {
    const song = await getSong(key).catch(() => null);
    if (!song) {
      setStatus("Não foi possível abrir a música.");
      return;
    }
    restoring = true;
    try {
      const gp5 = new Uint8Array(await song.gp5.arrayBuffer());
      const loaded = new Promise((resolve) => {
        document.addEventListener("score-loaded", resolve, { once: true });
        setTimeout(resolve, 60000);
      });
      window.App.openSong(gp5, song.filename, song.report, true, song.pdfHandle || null);
      window.location.hash = "#/tocar";
      if (song.audio) {
        await loaded;
        await window.AudioSync.useFile(new File([song.audio.blob], song.audio.name, { type: song.audio.type }));
      }
    } catch {
      setStatus("Não foi possível abrir a música.");
    } finally {
      restoring = false;
    }
  }

  document.addEventListener("song-converted", async (event) => {
    const { title, artist, tempo, gp5, filename, report, fromLibrary, pdfHandle } = event.detail;
    currentKey = songKey(title || filename, artist); // untitled songs: by file name
    if (fromLibrary || !gp5) {
      render();
      return;
    }
    try {
      const previous = await getSong(currentKey);
      await putSong({
        key: currentKey,
        title: title || "",
        artist: artist || "",
        tempo: tempo || null,
        measures: report.measures,
        trackNames: report.tracks.map((track) => track.name),
        savedAt: Date.now(),
        filename,
        gp5: new Blob([gp5], { type: "application/octet-stream" }),
        report,
        audio: previous ? previous.audio : null,
        cover: previous ? previous.cover || null : null,
        // The first PDF's file handle (Chrome): the MP3 can be saved in its folder later.
        pdfHandle: pdfHandle || (previous ? previous.pdfHandle || null : null),
      });
      if (navigator.storage && navigator.storage.persist) navigator.storage.persist().catch(() => {});
      refresh();
      if (!previous || !previous.cover) findCover(currentKey, artist, title, true);
    } catch {
      setStatus("Não foi possível guardar a música na biblioteca.");
    }
  });

  // The audio chosen (or removed) for the open song goes with it.
  document.addEventListener("song-audio", async (event) => {
    if (restoring || !currentKey) return;
    const { file } = event.detail;
    try {
      const song = await getSong(currentKey);
      if (!song) return;
      song.audio = file ? { name: file.name, type: file.type, blob: file } : null;
      await putSong(song);
      refresh();
    } catch {
      setStatus("Não foi possível guardar o áudio na biblioteca (espaço do browser?).");
    }
  });

  search.addEventListener("input", render);
  refresh();

  window.Library = {
    songs: () => songs.map(({ key, title, artist }) => ({ key, title, artist })),
    open: openSong,
  };
})();
