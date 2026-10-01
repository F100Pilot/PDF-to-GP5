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

  let noMatchShown = false; // the status line shows the "no song matches" message

  function setStatus(text, noMatch = false) {
    statusLine.textContent = text;
    statusLine.hidden = !text;
    noMatchShown = Boolean(text) && noMatch;
  }

  function songKey(title, artist) {
    return `${(artist || "").trim()} - ${(title || "").trim()}`.toLowerCase();
  }

  // --- Browser storage (IndexedDB) ----------------------------------------------------------
  function openDatabase() {
    if (!window.indexedDB) return Promise.reject(new Error("IndexedDB indisponível")); // i18n-skip: technical error, never shown
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
        if (moved) setStatus(moved === 1
          ? T("{n} música passou do browser para a pasta da biblioteca.", { n: moved })
          : T("{n} músicas passaram do browser para a pasta da biblioteca.", { n: moved }));
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
        ? T("Não foi possível ler a pasta da biblioteca ({error}).", { error: error.message })
        : T("A biblioteca não está disponível neste browser (por exemplo, numa janela privada)."));
    }
  }

  function showUsage() {
    if (folder !== null) {
      usage.textContent = T("Pasta da biblioteca: {folder}", { folder });
      return;
    }
    usage.textContent = T("Guardada neste browser (a aplicação não está aberta no computador onde corre o servidor).");
    if (!navigator.storage || !navigator.storage.estimate) return;
    navigator.storage.estimate().then(({ usage: used }) => {
      if (used) usage.textContent += " " + T("Espaço usado: {size} MB.", { size: (used / 1048576).toFixed(1).replace(".", ",") });
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
      if (!quiet) setStatus(T("Sem artista e título não é possível procurar a capa: escolha uma imagem."));
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
        setStatus(response.status === 404
          ? T("Capa não encontrada: pode escolher uma imagem.")
          : T("Não foi possível procurar a capa (sem ligação à internet?): pode escolher uma imagem."));
      }
    } catch {
      if (!quiet) setStatus(T("Não foi possível procurar a capa (sem ligação ao servidor)."));
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
      image.alt = song.title ? T("Capa de {title}", { title: song.title }) : T("Capa da música");
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
    find.textContent = song.coverSrc ? T("Procurar outra vez") : T("Procurar capa");
    find.addEventListener("click", () => findCover(song.key, song.artist, song.title, false));
    const input = document.createElement("input");
    input.type = "file";
    input.accept = COVER_TYPES.join(",");
    input.hidden = true;
    input.addEventListener("change", () => {
      const file = input.files && input.files[0];
      if (!file) return;
      if (!COVER_TYPES.includes(file.type) || file.size > MAX_COVER_BYTES) {
        setStatus(T("A capa tem de ser uma imagem JPEG, PNG ou WebP até 5 MB."));
        return;
      }
      setCover(song.key, file).then(() => setStatus("")).catch(() => setStatus(T("Não foi possível guardar a capa.")));
    });
    const choose = document.createElement("button");
    choose.type = "button";
    choose.className = "link-button";
    choose.textContent = T("Escolher imagem");
    choose.addEventListener("click", () => input.click());
    row.append(find, choose, input);
    return row;
  }

  function card(song) {
    const item = document.createElement("li");
    const article = document.createElement("article");
    article.className = "card song-card";
    const title = document.createElement("h2");
    title.textContent = song.title || T("Sem título");
    const artist = document.createElement("span");
    artist.className = "muted";
    artist.textContent = song.artist || T("Artista desconhecido");
    const tags = document.createElement("div");
    tags.className = "song-tags";
    const labels = [
      song.trackNames.length === 1 ? T("{n} track", { n: 1 }) : T("{n} tracks", { n: song.trackNames.length }),
      T("{n} compassos", { n: song.measures }),
      song.tempo ? `${song.tempo} BPM` : "",
      song.audioName ? T("com áudio") : "",
      song.key === currentKey ? T("aberta") : "",
    ];
    for (const label of labels.filter(Boolean)) {
      const tag = document.createElement("span");
      tag.textContent = label;
      tags.appendChild(tag);
    }
    const when = document.createElement("span");
    when.className = "hint";
    when.textContent = T("Guardada em {date} · {tracks}", { date: new Date(song.savedAt).toLocaleDateString(LANG === "pt" ? "pt-PT" : LANG), tracks: song.trackNames.join(", ") });
    const actions = document.createElement("div");
    actions.className = "song-actions";
    const play = document.createElement("button");
    play.type = "button";
    play.textContent = T("Tocar");
    play.addEventListener("click", () => openSong(song.key));
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "danger";
    remove.textContent = T("Remover");
    remove.setAttribute("aria-label", song.title ? T("Remover {title} da biblioteca", { title: song.title }) : T("Remover a música da biblioteca"));
    let confirmTimer = null;
    remove.addEventListener("click", async () => {
      if (!remove.classList.contains("confirm")) { // two steps: nothing is removed by a stray click
        remove.classList.add("confirm");
        remove.textContent = T("Confirmar");
        confirmTimer = setTimeout(() => {
          remove.classList.remove("confirm");
          remove.textContent = T("Remover");
        }, 4000);
        return;
      }
      clearTimeout(confirmTimer);
      await removeSong(song.key).catch(() => setStatus(T("Não foi possível remover a música.")));
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
    if (songs.length && !shown.length) setStatus(T("Nenhuma música corresponde à procura."), true);
    else if (noMatchShown) setStatus("");
  }

  // Open a stored song: its result and score, then its audio once the score is loaded (the audio
  // settings are remembered per song and must apply to this one).
  // `keepPage`: stay on the page shown (reopened after a language switch), not go to Tocar.
  async function openSong(key, keepPage = false) {
    await ready;
    const song = await loadSong(key).catch(() => null);
    if (!song) {
      setStatus(T("Não foi possível abrir a música."));
      return;
    }
    restoring = true;
    try {
      const loaded = new Promise((resolve) => {
        document.addEventListener("score-loaded", resolve, { once: true });
        setTimeout(resolve, 60000);
      });
      window.App.openSong(new Uint8Array(song.gp5), song.filename, song.report, true, song.pdfHandle || null);
      if (!keepPage) window.location.hash = "#/tocar";
      if (song.audio) {
        await loaded;
        await window.AudioSync.useFile(song.audio);
      }
    } catch {
      setStatus(T("Não foi possível abrir a música."));
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
        ? T("Não foi possível guardar a música na pasta da biblioteca.")
        : T("Não foi possível guardar a música na biblioteca."));
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
        ? T("Não foi possível guardar o áudio na pasta da biblioteca.")
        : T("Não foi possível guardar o áudio na biblioteca (espaço do browser?)."));
    }
  });

  // --- Export / import (to the library on another computer) ----------------------------------
  // A ZIP of chosen songs, without the audio, with each song's settings kept by this browser:
  // where bar 1 starts in the audio and the tempo (audio.js), the YouTube video and its offset
  // (video.js). Those are stored under "artist - title" as the score names the song.
  const exportButton = document.getElementById("library-export");
  const importButton = document.getElementById("library-import");
  const importFile = document.getElementById("library-import-file");
  const dialog = document.getElementById("transfer");
  const dialogTitle = document.getElementById("transfer-title");
  const dialogIntro = document.getElementById("transfer-intro");
  const dialogList = document.getElementById("transfer-list");
  const dialogGo = document.getElementById("transfer-go");
  let onGo = null;

  const settingKeys = (title, artist) => ({
    audio: `pdf-to-gp5.audio.${[artist, title].filter(Boolean).join(" - ")}`,
    video: `pdf-to-gp5.video.${artist} - ${title}`,
  });

  function readSettings(title, artist) {
    const out = {};
    for (const [group, key] of Object.entries(settingKeys(title, artist))) {
      try {
        const value = JSON.parse(localStorage.getItem(key) || "null");
        if (value && typeof value === "object") out[group] = value;
      } catch { /* storage unavailable or damaged */ }
    }
    return out;
  }

  function writeSettings(title, artist, settings) {
    for (const [group, key] of Object.entries(settingKeys(title, artist))) {
      if (!settings || !settings[group]) continue;
      try { localStorage.setItem(key, JSON.stringify(settings[group])); } catch { /* storage unavailable */ }
    }
  }

  const when = (time) => new Date(time).toLocaleString(LANG === "pt" ? "pt-PT" : LANG, { dateStyle: "short", timeStyle: "short" });
  const songName = (song) => [song.title || T("Sem título"), song.artist].filter(Boolean).join(" — ");

  // One row: a check box to take the song; `existing`: also whether to replace the library's copy.
  function row(song, existing) {
    const item = document.createElement("li");
    const label = document.createElement("label");
    const take = document.createElement("input");
    take.type = "checkbox";
    take.checked = true;
    take.className = "take";
    take.value = song.key;
    const name = document.createElement("span");
    name.textContent = songName(song);
    label.append(take, name);
    const details = document.createElement("span");
    details.className = "muted";
    details.textContent = T("Guardada em {date} · {tracks}", { date: when(song.savedAt), tracks: song.trackNames.join(", ") });
    item.append(label, details);
    if (existing) {
      const newer = song.savedAt > existing.savedAt ? T("a do ficheiro") : song.savedAt < existing.savedAt ? T("a da biblioteca") : "";
      const note = document.createElement("span");
      note.className = "exists";
      note.textContent = T("Já existe nesta biblioteca (guardada em {here}).", { here: when(existing.savedAt) }) + " ";
      const strong = document.createElement("strong");
      strong.textContent = newer ? T("Mais recente: {which}.", { which: newer }) : T("As duas têm a mesma data.");
      note.appendChild(strong);
      const replace = document.createElement("label");
      replace.className = "replace";
      const box = document.createElement("input");
      box.type = "checkbox";
      box.className = "replace-box";
      box.value = song.key;
      replace.append(box, document.createTextNode(T("Substituir a música da biblioteca (o áudio dela fica)")));
      take.addEventListener("change", () => { box.disabled = !take.checked; });
      item.append(note, replace);
    }
    return item;
  }

  function openDialog(title, intro, action, rows, go) {
    dialogTitle.textContent = title;
    dialogIntro.textContent = intro;
    dialogGo.textContent = action;
    dialogList.replaceChildren(...rows);
    onGo = go;
    dialog.showModal();
  }

  const checked = (selector) => [...dialogList.querySelectorAll(selector)].filter((box) => box.checked && !box.disabled).map((box) => box.value);
  function checkAll(on) {
    for (const box of dialogList.querySelectorAll("input.take")) {
      box.checked = on;
      box.dispatchEvent(new Event("change"));
    }
  }
  document.getElementById("transfer-all").addEventListener("click", () => checkAll(true));
  document.getElementById("transfer-none").addEventListener("click", () => checkAll(false));
  dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
  dialogGo.addEventListener("click", async () => {
    if (!onGo) return;
    dialogGo.disabled = true;
    try {
      if (await onGo()) dialog.close();
    } finally {
      dialogGo.disabled = false;
    }
  });

  function download(blob, name) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  }

  exportButton.addEventListener("click", () => {
    if (!songs.length) {
      setStatus(T("A biblioteca está vazia: não há músicas para exportar."));
      return;
    }
    openDialog(
      T("Exportar músicas"),
      T("Escolha as músicas a guardar num ficheiro ZIP, para importar na biblioteca de outro computador. O áudio (MP3) não vai; vão o GP5, a capa e as definições de cada música (início do compasso 1 no áudio, tempo, vídeo do YouTube)."),
      T("Exportar"),
      songs.map((song) => row(song, null)),
      async () => {
        const keys = new Set(checked("input.take"));
        const chosen = songs.filter((song) => keys.has(song.key));
        if (!chosen.length) return false;
        try {
          const response = await request("/api/library/export", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ songs: chosen.map((song) => ({ id: song.id, settings: readSettings(song.title, song.artist) })) }),
          });
          const date = new Date().toISOString().slice(0, 10);
          download(await response.blob(), `biblioteca-pdf-to-gp5-${date}.zip`);
          setStatus(chosen.length === 1 ? T("1 música exportada.") : T("{n} músicas exportadas.", { n: chosen.length }));
          return true;
        } catch (error) {
          setStatus(T("Não foi possível exportar: {error}", { error: error.message }));
          return true;
        }
      },
    );
  });

  importButton.addEventListener("click", () => importFile.click());
  importFile.addEventListener("change", async () => {
    const file = importFile.files && importFile.files[0];
    importFile.value = "";
    if (!file) return;
    const send = (choices) => {
      const form = new FormData();
      form.append("file", file);
      if (choices) form.append("choices", JSON.stringify(choices));
      return request("/api/library/import", { method: "POST", body: form }).then((response) => response.json());
    };
    let found;
    try {
      ({ songs: found } = await send(null));
    } catch (error) {
      setStatus(T("Não foi possível ler o ficheiro: {error}", { error: error.message }));
      return;
    }
    const existing = found.filter((song) => song.existing).length;
    openDialog(
      T("Importar músicas"),
      existing
        ? T("{n} música(s) do ficheiro já existem nesta biblioteca: marque \"Substituir\" nas que quer trocar pela do ficheiro; as outras ficam como estão.", { n: existing })
        : T("Escolha as músicas a juntar à biblioteca."),
      T("Importar"),
      found.map((song) => row(song, song.existing)),
      async () => {
        const chosen = checked("input.take");
        if (!chosen.length) return false;
        try {
          const done = await send({ chosen, replace: checked("input.replace-box") });
          for (const song of done.imported) writeSettings(song.title, song.artist, song.settings);
          const added = done.imported.filter((song) => !song.replaced).length;
          const replaced = done.imported.length - added;
          setStatus(T("Importação: {added} nova(s), {replaced} substituída(s), {kept} mantida(s) como estavam.", {
            added, replaced, kept: done.skipped.length,
          }));
        } catch (error) {
          setStatus(T("Não foi possível importar: {error}", { error: error.message }));
        }
        refresh();
        return true;
      },
    );
  });

  search.addEventListener("input", render);
  ready = start();
  ready.then(() => {
    // Only with the library folder on this computer (the server makes and reads the ZIP).
    exportButton.hidden = folder === null;
    importButton.hidden = folder === null;
  });
  refresh();

  // Switching the language reloads the page: the song open then (already in the library, saved
  // when it was converted) is opened again, on the same page.
  const REOPEN_KEY = "pdf-to-gp5.reopen";
  window.addEventListener("lang-reload", () => {
    try {
      if (currentKey) sessionStorage.setItem(REOPEN_KEY, currentKey);
    } catch { /* storage unavailable */ }
  });
  let reopen = null;
  try {
    reopen = sessionStorage.getItem(REOPEN_KEY);
    sessionStorage.removeItem(REOPEN_KEY);
  } catch { /* storage unavailable */ }
  if (reopen) openSong(reopen, true);

  window.Library = {
    songs: () => songs.map(({ key, title, artist }) => ({ key, title, artist })),
    open: openSong,
  };
})();
