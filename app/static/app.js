"use strict";

(() => {
  const form = document.getElementById("form");
  const fileInput = document.getElementById("file");
  const drop = document.getElementById("drop");
  const dropText = document.getElementById("drop-text");
  const submit = document.getElementById("submit");
  const status = document.getElementById("status");
  const result = document.getElementById("result");
  const download = document.getElementById("download");
  const meta = document.getElementById("meta");
  const inspectStatus = document.getElementById("inspect-status");
  const timeSignature = document.getElementById("time_signature");
  const tracksBox = document.getElementById("tracks-box");
  const trackList = document.getElementById("tracks");
  // Files the converter reads: PDFs and pictures of tabs (OCR).
  const ACCEPTED = /\.(?:pdf|png|jpe?g|webp)$/i;
  const ACCEPTED_TYPES = ["application/pdf", "image/png", "image/jpeg", "image/webp"];
  const DROP_HINT = T("Arraste os PDFs ou imagens da música (um por track) ou clique para escolher");
  let objectUrl = null;
  let maxBytes = 10 * 1024 * 1024;
  let maxTotalBytes = 40 * 1024 * 1024;
  let maxTracks = 7;
  let trackColors = []; // one per track position, same as in the GP5 file
  let inspecting = false;
  let tunings = ["auto"];
  let instruments = ["auto"];
  let tracks = []; // { file, name, tuning, instrument, info }
  let inspection = 0; // ignores answers for a selection that was replaced
  // The first chosen PDF as a file handle (Chrome's file picker / drag and drop), and the one of
  // the open song: a "save" dialog can then open in the folder of the song's PDFs.
  let selectionHandle = null;
  let songHandle = null;

  const TUNING_LABELS = {
    auto: T("Automática (do PDF)"), standard: "Standard (EADGBE)", drop_d: "Drop D", eb_standard: T("Mib (½ tom abaixo)"),
    d_standard: T("Ré standard"), drop_c: "Drop C", open_g: "Open G", open_d: "Open D",
    dadgad: "DADGAD", standard_7: T("7 cordas standard"),
    bass_4: T("Baixo 4 cordas"), bass_5: T("Baixo 5 cordas"), custom: T("Personalizada"),
  };
  const INSTRUMENT_LABELS = {
    auto: T("Automático"), nylon: T("Guitarra clássica"), steel: T("Guitarra acústica"), clean: T("Guitarra elétrica limpa"),
    overdrive: "Overdrive", distortion: T("Distorção"), bass: T("Baixo"),
  };

  fetch("/api/options")
    .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
    .then((opts) => {
      tunings = opts.tunings;
      instruments = opts.instruments;
      maxBytes = opts.max_upload_mb * 1024 * 1024;
      maxTracks = opts.max_tracks || maxTracks;
      trackColors = opts.track_colors || [];
      maxTotalBytes = (opts.max_total_upload_mb || 40) * 1024 * 1024;
      renderTracks();
    })
    .catch(() => showStatus(T("Não foi possível carregar as opções do servidor."), true));

  function showStatus(message, isError) {
    status.hidden = false;
    status.textContent = message;
    status.classList.toggle("error", Boolean(isError));
  }

  function makeSelect(values, labels, selected, onChange, ariaLabel) {
    const select = document.createElement("select");
    select.setAttribute("aria-label", ariaLabel);
    for (const value of values) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = labels[value] || value;
      select.appendChild(option);
    }
    select.value = selected;
    select.addEventListener("change", () => onChange(select.value));
    return select;
  }

  function button(label, title, onClick, disabled) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "icon";
    b.textContent = label;
    b.title = title;
    b.setAttribute("aria-label", title);
    b.disabled = Boolean(disabled);
    b.addEventListener("click", onClick);
    return b;
  }

  function move(index, delta) {
    const target = index + delta;
    [tracks[index], tracks[target]] = [tracks[target], tracks[index]];
    renderTracks();
  }

  // Reorder by dragging a track by its handle (the ↑/↓ buttons do the same from the keyboard).
  let dragFrom = null;

  function dropTarget(li, event) {
    const box = li.getBoundingClientRect();
    return event.clientY < box.top + box.height / 2 ? "before" : "after";
  }

  function makeDraggable(li, index, grip) {
    grip.addEventListener("pointerdown", () => { li.draggable = true; });
    li.addEventListener("dragstart", (event) => {
      dragFrom = index;
      li.classList.add("dragging");
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", String(index));
    });
    li.addEventListener("dragend", () => {
      dragFrom = null;
      li.draggable = false;
      for (const item of trackList.children) item.classList.remove("dragging", "drop-before", "drop-after");
    });
    li.addEventListener("dragover", (event) => {
      if (dragFrom === null) return;
      event.preventDefault();
      const side = dropTarget(li, event);
      li.classList.toggle("drop-before", side === "before" && dragFrom !== index);
      li.classList.toggle("drop-after", side === "after" && dragFrom !== index);
    });
    li.addEventListener("dragleave", () => li.classList.remove("drop-before", "drop-after"));
    li.addEventListener("drop", (event) => {
      if (dragFrom === null) return;
      event.preventDefault();
      let target = dropTarget(li, event) === "before" ? index : index + 1;
      if (dragFrom < target) target -= 1;
      if (target !== dragFrom) {
        const [moved] = tracks.splice(dragFrom, 1);
        tracks.splice(target, 0, moved);
      }
      dragFrom = null;
      renderTracks();
    });
  }

  // Colour the element (border and number badge) with the colour of track position `index`.
  function paintTrack(element, index) {
    const color = trackColors.length ? trackColors[index % trackColors.length] : "";
    if (color) element.style.setProperty("--track", color);
    const badge = document.createElement("span");
    badge.className = "track-num";
    badge.textContent = String(index + 1);
    return badge;
  }

  function renderTracks() {
    trackList.replaceChildren();
    tracksBox.hidden = tracks.length === 0;
    tracks.forEach((track, index) => {
      const li = document.createElement("li");
      li.className = "track";
      const grip = document.createElement("span");
      grip.className = "track-grip";
      grip.textContent = "⠿";
      grip.title = T("Arrastar para mudar a ordem");
      grip.setAttribute("aria-hidden", "true"); // from the keyboard: the ↑/↓ buttons
      if (tracks.length > 1) makeDraggable(li, index, grip);
      else grip.hidden = true;
      const badge = paintTrack(li, index);
      const head = document.createElement("div");
      head.className = "track-head";
      const file = document.createElement("span");
      file.className = "track-file";
      file.textContent = track.file.name;
      const info = document.createElement("span");
      info.className = "hint";
      if (track.error) info.textContent = track.error;
      else if (track.info) info.textContent = T("{n} cordas · {tuning}", { n: track.info.strings, tuning: TUNING_LABELS[track.info.tuning] || track.info.tuning });
      else {
        info.textContent = T("A analisar…");
        if (track.inspecting) { // the file being read now: its progress
          const bar = document.createElement("progress");
          bar.className = "job-progress";
          bar.max = 100;
          bar.value = track.progress || 0;
          bar.setAttribute("aria-label", T("Progresso da análise"));
          track.bar = bar;
          info.append(" ", bar);
        }
      }
      const actions = document.createElement("span");
      actions.className = "track-actions";
      actions.append(
        button("↑", T("Mover para cima"), () => move(index, -1), index === 0),
        button("↓", T("Mover para baixo"), () => move(index, 1), index === tracks.length - 1),
        button("✕", T("Remover"), () => { tracks.splice(index, 1); renderTracks(); }),
      );
      head.append(grip, badge, file, info, actions);

      const fields = document.createElement("div");
      fields.className = "grid";
      const nameLabel = document.createElement("label");
      nameLabel.textContent = T("Nome");
      const name = document.createElement("input");
      name.maxLength = 40;
      name.value = track.name;
      name.placeholder = T("Track {n}", { n: index + 1 });
      name.addEventListener("input", () => { track.name = name.value; });
      nameLabel.appendChild(name);
      const tuningLabel = document.createElement("label");
      tuningLabel.textContent = T("Afinação");
      tuningLabel.appendChild(makeSelect(tunings, TUNING_LABELS, track.tuning, (v) => { track.tuning = v; }, T("Afinação")));
      const instrumentLabel = document.createElement("label");
      instrumentLabel.textContent = T("Som");
      instrumentLabel.appendChild(
        makeSelect(instruments, INSTRUMENT_LABELS, track.instrument, (v) => { track.instrument = v; }, T("Som")));
      fields.append(nameLabel, tuningLabel, instrumentLabel);
      li.append(head, fields);
      trackList.appendChild(li);
    });
    dropText.textContent = tracks.length
      ? T("{n} PDF(s) selecionado(s) — clique ou arraste para substituir", { n: tracks.length })
      : DROP_HINT;
  }

  function setField(name, value) {
    form.elements[name].value = value === null || value === undefined ? "" : String(value);
  }

  function selectTimeSignature(value) {
    if (value && ![...timeSignature.options].some((o) => o.value === value)) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value;
      timeSignature.appendChild(option);
    }
    timeSignature.value = value || "auto";
  }

  // Same rule as the server's track_name_from_filename: "Artist - Song - Bass.pdf" -> "Bass".
  function nameFromFile(filename, title, artist) {
    const normalize = (text) => text.toLowerCase().replace(/[^a-z0-9]+/g, "");
    const known = new Set([title, artist].filter(Boolean).map(normalize));
    const stem = filename.replace(/\.(?:pdf|png|jpe?g|webp)$/i, "").replace(/_/g, " ");
    const parts = stem.split(/\s+-\s+|\s*[–—]\s*/).map((p) => p.trim()).filter(Boolean);
    return parts.filter((p) => !known.has(normalize(p))).join(" - ").slice(0, 40);
  }

  // Progress of a job on the server, for the progress bars: the request carries a random id and
  // the page polls /api/progress/{id} until it is answered. Returns the function that stops it.
  function newProgressId() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return [...crypto.getRandomValues(new Uint8Array(16))].map((b) => b.toString(16).padStart(2, "0")).join("");
  }

  function watchProgress(id, onPercent) {
    let stopped = false;
    (async () => {
      while (!stopped) {
        await new Promise((resolve) => setTimeout(resolve, 500));
        if (stopped) break;
        try {
          const { percent } = await (await fetch(`/api/progress/${id}`)).json();
          if (!stopped && typeof percent === "number") onPercent(percent);
        } catch { /* the next poll may answer */ }
      }
    })();
    return () => { stopped = true; };
  }

  async function inspectOne(file, onPercent) {
    const body = new FormData();
    body.append("file", file);
    const id = newProgressId();
    const stop = watchProgress(id, onPercent);
    const response = await fetch("/api/inspect", { method: "POST", body, headers: { "X-Progress-Id": id } }).finally(stop);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : T("Não foi possível analisar."));
    return payload;
  }

  // Converting while PDFs are still being inspected would compete for the same server slots.
  function setInspecting(active) {
    inspecting = active;
    submit.disabled = active;
  }

  async function selectFiles(fileList, handle = null) {
    selectionHandle = handle;
    const files = [...fileList].filter((f) => ACCEPTED.test(f.name) || ACCEPTED_TYPES.includes(f.type));
    const token = ++inspection;
    result.hidden = true;
    status.hidden = true;
    // Any new selection replaces the previous one, even when it is rejected below.
    tracks = [];
    meta.hidden = true;
    inspectStatus.hidden = true;
    setInspecting(false);
    renderTracks();
    if (!files.length) return;
    if (files.length > maxTracks) {
      showStatus(T("Máximo de {n} PDFs (tracks) por música.", { n: maxTracks }), true);
      return;
    }
    const tooBig = files.find((f) => f.size > maxBytes);
    if (tooBig) { showStatus(T("{name} excede {mb} MB.", { name: tooBig.name, mb: maxBytes / 1024 / 1024 }), true); return; }
    if (files.reduce((sum, f) => sum + f.size, 0) > maxTotalBytes) {
      showStatus(T("Os PDFs juntos excedem {mb} MB.", { mb: maxTotalBytes / 1024 / 1024 }), true);
      return;
    }
    setInspecting(true);
    tracks = files.map((file) => ({ file, name: "", tuning: "auto", instrument: "auto", info: null, error: "" }));
    renderTracks();
    meta.hidden = true;
    inspectStatus.hidden = false;
    inspectStatus.textContent = T("A analisar os PDFs…");
    const detected = {};
    for (const track of [...tracks]) { // one at a time: the server limits concurrent jobs
      track.inspecting = true;
      renderTracks();
      try {
        const info = await inspectOne(track.file, (percent) => {
          track.progress = percent;
          if (track.bar) track.bar.value = percent;
        });
        if (token !== inspection) return;
        track.info = info;
        if (!track.name && info.part_name) track.name = info.part_name;
        for (const key of ["title", "artist", "tempo", "time_signature"]) {
          if (detected[key] == null && info[key] != null) detected[key] = info[key];
        }
      } catch (error) {
        if (token !== inspection) return;
        track.error = error instanceof Error ? error.message : T("Não foi possível analisar.");
      }
      track.inspecting = false;
      renderTracks();
    }
    if (token !== inspection) return;
    setInspecting(false);
    for (const track of tracks) {
      if (!track.name) track.name = nameFromFile(track.file.name, detected.title, detected.artist);
    }
    renderTracks();
    inspectStatus.hidden = true;
    setField("title", detected.title);
    setField("artist", detected.artist);
    setField("tempo", detected.tempo);
    selectTimeSignature(detected.time_signature);
    meta.hidden = false;
  }

  fileInput.addEventListener("change", () => selectFiles(fileInput.files));
  // Chrome: choose the PDFs with the File System Access picker to know their folder (nothing
  // is read from it but the chosen files); elsewhere the plain file input.
  let nativePicker = false; // falling back to the plain file input (its click reaches this label too)
  drop.addEventListener("click", async (event) => {
    if (!window.showOpenFilePicker || nativePicker) {
      nativePicker = false;
      return;
    }
    event.preventDefault();
    try {
      const handles = await window.showOpenFilePicker({
        id: "pdfs",
        multiple: true,
        types: [{
          description: T("PDF ou imagem"),
          accept: { "application/pdf": [".pdf"], "image/png": [".png"], "image/jpeg": [".jpg", ".jpeg"], "image/webp": [".webp"] },
        }],
      });
      const files = await Promise.all(handles.map((handle) => handle.getFile()));
      selectFiles(files, handles[0] || null);
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) {
        nativePicker = true;
        fileInput.click();
      }
    }
  });
  ["dragenter", "dragover"].forEach((type) =>
    drop.addEventListener(type, (event) => { event.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((type) =>
    drop.addEventListener(type, (event) => { event.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", async (event) => {
    if (!event.dataTransfer || !event.dataTransfer.files.length) return;
    const files = [...event.dataTransfer.files];
    // The handles must be asked for during the drop event, before any await.
    const pending = [...event.dataTransfer.items]
      .filter((item) => item.kind === "file" && item.getAsFileSystemHandle)
      .map((item) => item.getAsFileSystemHandle().catch(() => null));
    const handles = (await Promise.all(pending)).filter((handle) => handle && handle.kind === "file");
    selectFiles(files, handles[0] || null);
  });

  function summaryList(items) {
    const dl = document.createElement("dl");
    dl.className = "summary";
    for (const [label, value] of items) {
      const wrap = document.createElement("div");
      const dt = document.createElement("dt");
      const dd = document.createElement("dd");
      dt.textContent = label;
      dd.textContent = String(value);
      wrap.append(dt, dd);
      dl.appendChild(wrap);
    }
    return dl;
  }

  function renderTrackResult(track, index) {
    const details = document.createElement("details");
    details.className = "track-result";
    details.open = index === 0;
    const summary = document.createElement("summary");
    summary.append(paintTrack(details, index), ` ${track.name}`);
    const rhythm = track.rhythm_from_notation
      ? T("lido em {n}/{m} compassos", { n: track.rhythm_from_notation, m: track.rhythm_from_notation + track.rhythm_estimated })
      : T("estimado");
    details.append(summary, summaryList([
      [T("Ficheiro"), track.filename || "—"], [T("Compassos"), track.measures], [T("Notas"), track.notes],
      [T("Cordas"), track.strings], [T("Afinação"), TUNING_LABELS[track.tuning] || track.tuning],
      [T("Som"), INSTRUMENT_LABELS[track.instrument] || track.instrument], [T("Ritmo"), rhythm],
      [T("Formato"), track.sources.map((s) => (s === "ascii" ? T("texto") : s === "image" ? T("imagem (OCR)") : T("gravada"))).join(", ")],
    ]));
    const table = document.createElement("table");
    table.className = "systems";
    const head = document.createElement("tr");
    for (const title of ["#", T("Página"), T("Notas"), T("Compassos")]) {
      const th = document.createElement("th");
      th.textContent = title;
      head.appendChild(th);
    }
    const thead = document.createElement("thead");
    thead.appendChild(head);
    const tbody = document.createElement("tbody");
    track.systems_detail.forEach((system, i) => {
      const tr = document.createElement("tr");
      for (const value of [i + 1, system.page, system.notes, system.measures ?? "—"]) {
        const td = document.createElement("td");
        td.textContent = String(value);
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    });
    table.append(thead, tbody);
    const systems = document.createElement("details");
    const systemsTitle = document.createElement("summary");
    systemsTitle.textContent = T("Linhas de tab detetadas");
    systems.append(systemsTitle, table);
    details.append(systems);
    // The plain-text preview is for proofreading a tab read from text; an engraved tab has the score.
    if (track.sources.every((source) => source === "ascii")) {
      const preview = document.createElement("pre");
      preview.textContent = track.preview;
      details.append(preview);
    }
    return details;
  }

  const LYRICS_TRACK = "Letra (voz)"; // i18n-skip: the silent track carrying the lyrics (app/converter.py)

  // Guitar Pro names of the navigation marks, as printed in scores.
  const NAVIGATION = {
    "Da Capo": "D.C.", "Da Capo al Coda": "D.C. al Coda", "Da Capo al Fine": "D.C. al Fine", // i18n-skip: data keys
    "Da Segno": "D.S.", "Da Segno al Coda": "D.S. al Coda", "Da Segno al Fine": "D.S. al Fine", // i18n-skip
    "Da Coda": "To Coda", // i18n-skip
  };

  function renderResult(report) {
    const auto = (key, value) => (report.auto && report.auto[key] ? T("{value} (auto)", { value }) : String(value));
    const expanded = (value) => (report.repeats_expanded ? T("{value} (por extenso)", { value }) : String(value));
    document.getElementById("summary").replaceWith(Object.assign(summaryList([
      [T("Título"), auto("title", report.title || "—")], [T("Artista"), auto("artist", report.artist || "—")],
      ["BPM", auto("tempo", report.tempo)], [T("Compasso"), auto("time_signature", report.time_signature)],
      // Later time signatures ("3/4 no c. 17") and repeats, when the PDF has them.
      ...((report.time_signature_changes || []).length
        ? [[T("Mudanças de compasso"),
          report.time_signature_changes.map((c) => T("{value} no c. {bar}", { value: c.time_signature, bar: c.bar })).join(", ")]]
        : []),
      ...((report.tempo_changes || []).length
        ? [[T("Mudanças de tempo"),
          report.tempo_changes.map((c) => T("{value} no c. {bar}", { value: c.tempo, bar: c.bar })).join(", ")]]
        : []),
      ...((report.navigation || []).length
        ? [[T("Navegação"), expanded(report.navigation.map((n) => T("{name} (c. {bar})", { name: NAVIGATION[n.name] || n.name, bar: n.bar })).join(", "))]]
        : []),
      ...(report.repeats ? [[T("Repetições"), expanded(report.repeats)]] : []),
      [T("Tracks"), report.tracks.length], [T("Compassos"), report.measures], [T("Notas"), report.notes],
      [T("Secções"), report.sections && report.sections.length ? report.sections.length : "—"],
      // The lyrics go to the silent "Letra (voz)" track (a name inside the GP5) or to a played track.
      [T("Letra"), report.lyrics ? (report.lyrics.track === LYRICS_TRACK ? T("Letra (voz)") : `${report.lyrics.track}`) : "—"],
    ]), { id: "summary" }));
    const list = document.getElementById("warnings");
    list.replaceChildren();
    for (const warning of report.warnings) {
      const li = document.createElement("li");
      li.textContent = warning;
      list.appendChild(li);
    }
    document.getElementById("warnings-box").hidden = report.warnings.length === 0;
    document.getElementById("track-results").replaceChildren(...report.tracks.map(renderTrackResult));
  }

  // Show a converted song: its result, its score and the file to download. `fromLibrary`: reopened
  // from the library (library.js), so not saved there again.
  function openSong(gp5, filename, report, fromLibrary = false, pdfHandle = null) {
    songHandle = pdfHandle;
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = URL.createObjectURL(new Blob([gp5], { type: "application/octet-stream" }));
    download.href = objectUrl;
    download.download = filename;
    renderResult(report);
    status.hidden = true;
    result.hidden = false;
    const { title, artist, tempo } = report;
    document.dispatchEvent(new CustomEvent("song-converted", {
      detail: { title, artist, tempo, tracks: report.tracks.length, gp5, filename, report, fromLibrary, pdfHandle },
    }));
    if (window.ScoreView) {
      const lyricsTrack = Boolean(report.lyrics && report.lyrics.track === LYRICS_TRACK);
      window.ScoreView.show(gp5, report.tracks.length, trackColors, report.timed_lyrics, lyricsTrack);
    }
  }
  window.App = { openSong, pdfFolder: () => songHandle };

  function base64ToBytes(b64) {
    const binary = atob(b64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
    return bytes;
  }

  // Remember the "repeats written out" choice (e.g. always on for Rocksmith).
  const expandRepeats = document.getElementById("expand_repeats");
  const EXPAND_KEY = "pdf-to-gp5.expand-repeats";
  try {
    expandRepeats.checked = localStorage.getItem(EXPAND_KEY) === "1";
  } catch { /* storage unavailable */ }
  expandRepeats.addEventListener("change", () => {
    try {
      localStorage.setItem(EXPAND_KEY, expandRepeats.checked ? "1" : "0");
    } catch { /* storage unavailable */ }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (inspecting) return showStatus(T("Aguarde o fim da análise dos PDFs."), false);
    if (!tracks.length) return showStatus(T("Escolha pelo menos um ficheiro PDF."), true);
    if (!form.reportValidity()) return undefined;

    const body = new FormData(form);
    for (const key of ["title", "artist", "tempo"]) {
      if (!String(body.get(key) || "").trim()) body.delete(key); // empty = detect from the PDF
    }
    for (const track of tracks) {
      body.append("file", track.file);
      body.append("track_name", track.name.trim());
      body.append("tuning", track.tuning);
      body.append("instrument", track.instrument);
    }
    submit.disabled = true;
    result.hidden = true;
    if (window.ScoreView) window.ScoreView.hide();
    const working = tracks.length > 1 ? T("A converter {n} tracks…", { n: tracks.length }) : T("A converter…");
    showStatus(working, false);
    const bar = document.getElementById("convert-progress");
    bar.value = 0;
    bar.hidden = false;
    const id = newProgressId();
    const stop = watchProgress(id, (percent) => {
      bar.value = percent;
      status.textContent = `${working} ${percent} %`;
    });
    try {
      const response = await fetch("/api/convert", { method: "POST", body, headers: { "X-Progress-Id": id } }).finally(() => {
        stop();
        bar.hidden = true;
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(typeof payload.detail === "string" ? payload.detail : T("Pedido inválido."));
      }
      openSong(base64ToBytes(payload.gp5_base64), payload.filename, payload.report, false, selectionHandle);
    } catch (error) {
      showStatus(error instanceof Error ? error.message : T("Erro inesperado."), true);
    } finally {
      submit.disabled = false;
    }
    return undefined;
  });

  const SEEN_KEY = "pdf-to-gp5.seen-version";

  function readSeen() {
    try { return localStorage.getItem(SEEN_KEY); } catch { return null; }
  }

  function writeSeen(version) {
    try { localStorage.setItem(SEEN_KEY, version); } catch { /* storage unavailable */ }
  }

  function compareVersions(a, b) {
    const pa = a.split(".").map(Number);
    const pb = b.split(".").map(Number);
    for (let i = 0; i < 3; i += 1) if (pa[i] !== pb[i]) return pa[i] - pb[i];
    return 0;
  }

  // Changelog text may contain `code` spans; build them as elements, never as HTML.
  function appendRich(parent, text) {
    text.split("`").forEach((part, index) => {
      if (!part) return;
      if (index % 2) {
        const code = document.createElement("code");
        code.textContent = part;
        parent.appendChild(code);
      } else {
        parent.appendChild(document.createTextNode(part));
      }
    });
  }

  function showNews(data) {
    const seen = readSeen();
    if (seen === data.version) return;
    // First visit: only the current release; otherwise every release newer than the last one seen.
    const releases = data.releases.filter((r) =>
      seen ? compareVersions(r.version, seen) > 0 : r.version === data.version);
    if (!releases.length) { writeSeen(data.version); return; }
    const body = document.getElementById("news-body");
    body.replaceChildren();
    for (const release of releases) {
      const heading = document.createElement("h3");
      heading.textContent = release.date
        ? T("Versão {version} · {date}", { version: release.version, date: release.date })
        : T("Versão {version}", { version: release.version });
      body.appendChild(heading);
      for (const section of release.sections) {
        const name = document.createElement("h4");
        name.textContent = section.name;
        const list = document.createElement("ul");
        for (const item of section.items) {
          const li = document.createElement("li");
          appendRich(li, item);
          list.appendChild(li);
        }
        body.append(name, list);
      }
    }
    const news = document.getElementById("news");
    news.hidden = false;
    document.getElementById("news-close").addEventListener("click", () => {
      writeSeen(data.version);
      news.hidden = true;
    }, { once: true });
  }

  fetch("/api/changelog")
    .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
    .then(showNews)
    .catch(() => {});

  // Local launcher only: tell the server this page is open, so it can stop
  // a few seconds after the last page is closed.
  function reportPresence(pageId, state) {
    const body = JSON.stringify({ id: pageId, state });
    if (state === "gone" && navigator.sendBeacon) {
      navigator.sendBeacon("/api/presence", new Blob([body], { type: "application/json" }));
      return;
    }
    fetch("/api/presence", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      keepalive: true,
    }).catch(() => {});
  }

  function watchPresence() {
    const pageId = window.crypto && crypto.randomUUID
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    let timer = null;
    const alive = () => reportPresence(pageId, "alive");
    const start = () => {
      alive();
      if (timer === null) timer = setInterval(alive, 15000);
    };
    window.addEventListener("pagehide", () => {
      clearInterval(timer);
      timer = null;
      reportPresence(pageId, "gone");
    });
    window.addEventListener("pageshow", (event) => {
      if (event.persisted) start(); // page restored from the back/forward cache
    });
    start();
  }

  fetch("/api/health")
    .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
    .then((health) => {
      document.getElementById("version").textContent = health.revision
        ? T("Versão {version} ({revision})", { version: health.version, revision: health.revision })
        : T("Versão {version}", { version: health.version });
      if (health.close_with_browser) watchPresence();
    })
    .catch(() => {});
})();
