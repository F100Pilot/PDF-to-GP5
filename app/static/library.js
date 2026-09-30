"use strict";

// Library: the converted songs with their report, the audio chosen for them and the cover, to be
// played again without converting. One entry per song ("artist - title"): converting it again
// replaces it (keeping its audio and cover).
//
// Where: in a folder on disk, through the server (/api/library), when the app is open on the
// computer it runs on — it does not depend on the browser or the port. Otherwise (the app
// published on a server), in this browser (IndexedDB), as before. Songs found in the browser
// while the folder is available are moved to the folder. The PDFs' file handles (to save an MP3
// next to them) can only be kept by the browser: they stay in IndexedDB either way.
(() => {
  const DB_NAME = "pdf-to-gp5";
  const STORE = "songs";
  const HANDLES = "handles";
  const list = document.getElementById("library-list");
  const empty = document.getElementById("library-empty");
  const statusLine = document.getElementById("library-status");
  const search = document.getElementById("library-search");
  const usage = document.getElementById("library-usage");
  let songs = []; // summaries (no file contents), newest first
  let currentKey = null; // the song open now
  let restoring = false; // reopening a song: its audio is already stored
  let database = null;
  let folder = null; // the library folder on disk, or null: kept in the browser
  let ready = null; // resolves once the storage is known (and browser songs moved to disk)

  function setStatus(text) {
    statusLine.textContent = text;
    statusLine.hidden = !text;
  }

  function songKey(title, artist) {
    return `${(artist || "").trim()} - ${(title || "").trim()}`.toLowerCase();
  }

  // --- Browser storage (IndexedDB) ----------------------------------------------------------
  function openDatabase() {
    if (!window.indexedDB) return Promise.reject(new Error("IndexedDB indisponível"));
    if (!database) {
      database = new Promise((resolve, reject) => {
        const request = indexedDB.open(DB_NAME, 2);
        request.onupgradeneeded = () => {
          const db = request.result;
          if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE, { keyPath: "key" });
          if (!db.objectStoreNames.contains(HANDLES)) db.createObjectStore(HANDLES, { keyPath: "key" });
        };
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
    }
    return database;
  }

  // Run `work(store)` in one transaction; resolves with the result of the request it returns.
  async function transaction(storeName, mode, work) {
    const db = await openDatabase();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(storeName, mode);
      const request = work(tx.objectStore(storeName));
      tx.oncomplete = () => resolve(request ? request.result : undefined);
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error);
    });
  }

  const browserSong = (key) => transaction(STORE, "readonly", (store) => store.get(key));
  const browserPut = (song) => transaction(STORE, "readwrite", (store) => store.put(song));
  const browserDelete = (key) => transaction(STORE, "readwrite", (store) => store.delete(key));
  const browserAll = () => transaction(STORE, "readonly", (store) => store.getAll());

  async function getHandle(key) {
    const entry = await transaction(HANDLES, "readonly", (store) => store.get(key)).catch(() => null);
    return entry ? entry.handle : null;
  }

  function putHandle(key, handle) {
    if (!handle) return Promise.resolve();
    return transaction(HANDLES, "readwrite", (store) => store.put({ key, handle })).catch(() => {});
  }

  // --- Folder on disk (server) ----------------------------------------------------------------
  const songPath = (id, part = "") => `/api/library/${encodeURIComponent(id)}${part ? `/${part}` : ""}`;

  async function request(path, options) {
    const response = await fetch(path, options);
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `HTTP ${response.status}`);
    }
    return response;
  }

  const diskId = (key) => (songs.find((song) => song.key === key) || {}).id;

  async function diskSave(record) {
    const { gp5, ...meta } = record;
    const form = new FormData();
    form.append("meta", JSON.stringify(meta));
    form.append("gp5", gp5, record.filename || "musica.gp5");
    return (await request("/api/library", { method: "POST", body: form })).json();
  }

  function diskPutFile(id, kind, blob, name) {
    const headers = { "Content-Type": blob.type || "application/octet-stream" };
    if (name) headers["X-Filename"] = encodeURIComponent(name);
    return request(songPath(id, kind), { method: "PUT", body: blob, headers });
  }

  // --- Storage used by the page (disk or browser) ---------------------------------------------
  async function listSongs() {
    if (folder !== null) {
      const { songs: found } = await (await request("/api/library")).json();
      return found.map((song) => ({
        ...song,
        coverSrc: song.cover ? `${songPath(song.id, "cover")}?v=${song.coverVersion}` : null,
      }));
    }
    const all = await browserAll();
    return all
      .map(({ key, title, artist, tempo, measures, trackNames, savedAt, audio, cover }) => ({
        key, title, artist, tempo, measures, trackNames, savedAt, audioName: audio ? audio.name : "", coverSrc: cover || null,
      }))
      .sort((a, b) => b.savedAt - a.savedAt);
  }

  // { gp5: ArrayBuffer, filename, report, audio: File | null, pdfHandle }
  async function loadSong(key) {
    const pdfHandle = await getHandle(key);
    if (folder !== null) {
      const id = diskId(key);
      if (!id) return null;
      const song = await (await request(songPath(id))).json();
      const gp5 = await (await request(songPath(id, "gp5"))).arrayBuffer();
      let audio = null;
      if (song.audioName) {
        const blob = await (await request(songPath(id, "audio"))).blob();
        audio = new File([blob], song.audioName, { type: blob.type });
      }
      return { gp5, filename: song.filename, report: song.report, audio, pdfHandle };
    }
    const song = await browserSong(key);
    if (!song) return null;
    return {
      gp5: await song.gp5.arrayBuffer(),
      filename: song.filename,
      report: song.report,
      audio: song.audio ? new File([song.audio.blob], song.audio.name, { type: song.audio.type }) : null,
      pdfHandle: pdfHandle || song.pdfHandle || null,
    };
  }

  // A converted song (its audio and cover, if it was already stored, stay). Returns whether it
  // already had a cover.
  async function saveSong(record) {
    if (folder !== null) {
      const saved = await diskSave(record);
      return saved.cover;
    }
    const previous = await browserSong(record.key);
    await browserPut({
      ...record,
      gp5: record.gp5,
      audio: previous ? previous.audio : null,
      cover: previous ? previous.cover || null : null,
    });
    return Boolean(previous && previous.cover);
  }

  async function setAudio(key, file) {
    if (folder !== null) {
      const id = diskId(key);
      if (!id) return;
      if (file) await diskPutFile(id, "audio", file, file.name);
      else await request(songPath(id, "audio"), { method: "DELETE" });
      return;
    }
    const song = await browserSong(key);
    if (!song) return;
    song.audio = file ? { name: file.name, type: file.type, blob: file } : null;
    await browserPut(song);
  }

  async function setCoverImage(key, blob) {
    if (folder !== null) {
      const id = diskId(key);
      if (id) await diskPutFile(id, "cover", blob);
      return;
    }
    const song = await browserSong(key);
    if (!song) return;
    song.cover = blob;
    await browserPut(song);
  }

  async function removeSong(key) {
    if (folder !== null) {
      const id = diskId(key);
      if (id) await request(songPath(id), { method: "DELETE" });
      return;
    }
    await browserDelete(key);
  }

  // Songs kept in this browser (before the folder existed, or at another address) go to the
  // folder; each leaves the browser once it is safely on disk.
  async function moveBrowserSongs() {
    const stored = await browserAll().catch(() => []);
    if (!stored.length) return 0;
    const onDisk = new Map(songs.map((song) => [song.key, song]));
    let moved = 0;
    for (const song of stored) {
      try {
        const existing = onDisk.get(song.key);
        if (!existing || existing.savedAt < song.savedAt) {
          const { audio, cover, pdfHandle, gp5, ...meta } = song;
          const saved = await diskSave({ ...meta, gp5 });
          if (audio) await diskPutFile(saved.id, "audio", audio.blob, audio.name);
          if (cover) await diskPutFile(saved.id, "cover", cover);
        }
        if (song.pdfHandle) await putHandle(song.key, song.pdfHandle);
        await browserDelete(song.key);
        moved += 1;
      } catch {
        // stays in the browser; tried again next time the page opens
      }
    }
    return moved;
  }

  async function start() {
    try {
      const response = await fetch("/api/library");
      if (response.ok) {
        ({ folder, songs } = await response.json());
        const moved = await moveBrowserSongs();
        if (moved) setStatus(`${moved} ${moved === 1 ? "música passou" : "músicas passaram"} do browser para a pasta da biblioteca.`);
      }
    } catch {
      folder = null; // no server answer: the browser keeps the songs
    }
  }

  // --- Page -----------------------------------------------------------------------------------
  async function refresh() {
    await ready;
    try {
      songs = await listSongs();
      render();
      showUsage();
    } catch (error) {
      songs = [];
      render();
      setStatus(folder !== null
        ? `Não foi possível ler a pasta da biblioteca (${error.message}).`
        : "A biblioteca não está disponível neste browser (por exemplo, numa janela privada).");
    }
  }

  function showUsage() {
    if (folder !== null) {
      usage.textContent = `Pasta da biblioteca: ${folder}`;
      return;
    }
    usage.textContent = "Guardada neste browser (a aplicação não está aberta no computador onde corre o servidor).";
    if (!navigator.storage || !navigator.storage.estimate) return;
    navigator.storage.estimate().then(({ usage: used }) => {
      if (used) usage.textContent += ` Espaço usado: ${(used / 1048576).toFixed(1).replace(".", ",")} MB.`;
    }).catch(() => {});
  }

  const normalize = (text) => text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

  // Covers: the album cover from the internet (iTunes, through the server) or an image chosen here.
  const COVER_TYPES = ["image/jpeg", "image/png", "image/webp"];
  const MAX_COVER_BYTES = 5 * 1024 * 1024;
  let coverUrls = []; // object URLs of the covers on screen, released on the next render

  async function setCover(key, blob) {
    await setCoverImage(key, blob);
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
    if (song.coverSrc) {
      const image = document.createElement("img");
      let url = song.coverSrc;
      if (typeof url !== "string") { // a Blob kept in the browser
        url = URL.createObjectURL(url);
        coverUrls.push(url);
      }
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
    const find = document.createElement("button");
    find.type = "button";
    find.className = "link-button";
    find.textContent = song.coverSrc ? "Procurar outra vez" : "Procurar capa";
    find.addEventListener("click", () => findCover(song.key, song.artist, song.title, false));
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
    row.append(find, choose, input);
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
      await removeSong(song.key).catch(() => setStatus("Não foi possível remover a música."));
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
    await ready;
    const song = await loadSong(key).catch(() => null);
    if (!song) {
      setStatus("Não foi possível abrir a música.");
      return;
    }
    restoring = true;
    try {
      const loaded = new Promise((resolve) => {
        document.addEventListener("score-loaded", resolve, { once: true });
        setTimeout(resolve, 60000);
      });
      window.App.openSong(new Uint8Array(song.gp5), song.filename, song.report, true, song.pdfHandle || null);
      window.location.hash = "#/tocar";
      if (song.audio) {
        await loaded;
        await window.AudioSync.useFile(song.audio);
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
    await ready;
    try {
      const hadCover = await saveSong({
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
      });
      // The first PDF's file handle (Chrome): the MP3 can be saved in its folder later.
      await putHandle(currentKey, pdfHandle);
      if (folder === null && navigator.storage && navigator.storage.persist) navigator.storage.persist().catch(() => {});
      await refresh();
      if (!hadCover) findCover(currentKey, artist, title, true);
    } catch {
      setStatus(folder !== null
        ? "Não foi possível guardar a música na pasta da biblioteca."
        : "Não foi possível guardar a música na biblioteca.");
    }
  });

  // The audio chosen (or removed) for the open song goes with it.
  document.addEventListener("song-audio", async (event) => {
    if (restoring || !currentKey) return;
    try {
      await setAudio(currentKey, event.detail.file);
      refresh();
    } catch {
      setStatus(folder !== null
        ? "Não foi possível guardar o áudio na pasta da biblioteca."
        : "Não foi possível guardar o áudio na biblioteca (espaço do browser?).");
    }
  });

  search.addEventListener("input", render);
  ready = start();
  refresh();

  window.Library = {
    songs: () => songs.map(({ key, title, artist }) => ({ key, title, artist })),
    open: openSong,
  };
})();
