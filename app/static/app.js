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
  const DROP_HINT = "Arraste os PDFs da música (um por track) ou clique para escolher";
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

  const TUNING_LABELS = {
    auto: "Automática (do PDF)", standard: "Standard (EADGBE)", drop_d: "Drop D", eb_standard: "Mib (½ tom abaixo)",
    d_standard: "Ré standard", drop_c: "Drop C", open_g: "Open G", open_d: "Open D",
    dadgad: "DADGAD", standard_7: "7 cordas standard",
    bass_4: "Baixo 4 cordas", bass_5: "Baixo 5 cordas", custom: "Personalizada",
  };
  const INSTRUMENT_LABELS = {
    auto: "Automático", nylon: "Guitarra clássica", steel: "Guitarra acústica", clean: "Guitarra elétrica limpa",
    overdrive: "Overdrive", distortion: "Distorção", bass: "Baixo",
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
    .catch(() => showStatus("Não foi possível carregar as opções do servidor.", true));

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
      const badge = paintTrack(li, index);
      const head = document.createElement("div");
      head.className = "track-head";
      const file = document.createElement("span");
      file.className = "track-file";
      file.textContent = track.file.name;
      const info = document.createElement("span");
      info.className = "hint";
      if (track.error) info.textContent = track.error;
      else if (track.info) info.textContent = `${track.info.strings} cordas · ${TUNING_LABELS[track.info.tuning] || track.info.tuning}`;
      else info.textContent = "A analisar…";
      const actions = document.createElement("span");
      actions.className = "track-actions";
      actions.append(
        button("↑", "Mover para cima", () => move(index, -1), index === 0),
        button("↓", "Mover para baixo", () => move(index, 1), index === tracks.length - 1),
        button("✕", "Remover", () => { tracks.splice(index, 1); renderTracks(); }),
      );
      head.append(badge, file, info, actions);

      const fields = document.createElement("div");
      fields.className = "grid";
      const nameLabel = document.createElement("label");
      nameLabel.textContent = "Nome";
      const name = document.createElement("input");
      name.maxLength = 40;
      name.value = track.name;
      name.placeholder = `Track ${index + 1}`;
      name.addEventListener("input", () => { track.name = name.value; });
      nameLabel.appendChild(name);
      const tuningLabel = document.createElement("label");
      tuningLabel.textContent = "Afinação";
      tuningLabel.appendChild(makeSelect(tunings, TUNING_LABELS, track.tuning, (v) => { track.tuning = v; }, "Afinação"));
      const instrumentLabel = document.createElement("label");
      instrumentLabel.textContent = "Som";
      instrumentLabel.appendChild(
        makeSelect(instruments, INSTRUMENT_LABELS, track.instrument, (v) => { track.instrument = v; }, "Som"));
      fields.append(nameLabel, tuningLabel, instrumentLabel);
      li.append(head, fields);
      trackList.appendChild(li);
    });
    dropText.textContent = tracks.length
      ? `${tracks.length} PDF(s) selecionado(s) — clique ou arraste para substituir`
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
    const stem = filename.replace(/\.pdf$/i, "").replace(/_/g, " ");
    const parts = stem.split(/\s+-\s+|\s*[–—]\s*/).map((p) => p.trim()).filter(Boolean);
    return parts.filter((p) => !known.has(normalize(p))).join(" - ").slice(0, 40);
  }

  async function inspectOne(file) {
    const body = new FormData();
    body.append("file", file);
    const response = await fetch("/api/inspect", { method: "POST", body });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : "Não foi possível analisar.");
    return payload;
  }

  // Converting while PDFs are still being inspected would compete for the same server slots.
  function setInspecting(active) {
    inspecting = active;
    submit.disabled = active;
  }

  async function selectFiles(fileList) {
    const files = [...fileList].filter((f) => f.name.toLowerCase().endsWith(".pdf") || f.type === "application/pdf");
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
      showStatus(`Máximo de ${maxTracks} PDFs (tracks) por música.`, true);
      return;
    }
    const tooBig = files.find((f) => f.size > maxBytes);
    if (tooBig) { showStatus(`${tooBig.name} excede ${maxBytes / 1024 / 1024} MB.`, true); return; }
    if (files.reduce((sum, f) => sum + f.size, 0) > maxTotalBytes) {
      showStatus(`Os PDFs juntos excedem ${maxTotalBytes / 1024 / 1024} MB.`, true);
      return;
    }
    setInspecting(true);
    tracks = files.map((file) => ({ file, name: "", tuning: "auto", instrument: "auto", info: null, error: "" }));
    renderTracks();
    meta.hidden = true;
    inspectStatus.hidden = false;
    inspectStatus.textContent = "A analisar os PDFs…";
    const detected = {};
    for (const track of [...tracks]) { // one at a time: the server limits concurrent jobs
      try {
        const info = await inspectOne(track.file);
        if (token !== inspection) return;
        track.info = info;
        if (!track.name && info.part_name) track.name = info.part_name;
        for (const key of ["title", "artist", "tempo", "time_signature"]) {
          if (detected[key] == null && info[key] != null) detected[key] = info[key];
        }
      } catch (error) {
        if (token !== inspection) return;
        track.error = error instanceof Error ? error.message : "Não foi possível analisar.";
      }
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
  ["dragenter", "dragover"].forEach((type) =>
    drop.addEventListener(type, (event) => { event.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((type) =>
    drop.addEventListener(type, (event) => { event.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (event) => {
    if (event.dataTransfer && event.dataTransfer.files.length) selectFiles(event.dataTransfer.files);
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
      ? `lido em ${track.rhythm_from_notation}/${track.rhythm_from_notation + track.rhythm_estimated} compassos`
      : "estimado";
    details.append(summary, summaryList([
      ["Ficheiro", track.filename || "—"], ["Compassos", track.measures], ["Notas", track.notes],
      ["Cordas", track.strings], ["Afinação", TUNING_LABELS[track.tuning] || track.tuning],
      ["Som", INSTRUMENT_LABELS[track.instrument] || track.instrument], ["Ritmo", rhythm],
      ["Formato", track.sources.map((s) => (s === "ascii" ? "texto" : "gravada")).join(", ")],
    ]));
    const table = document.createElement("table");
    table.className = "systems";
    const head = document.createElement("tr");
    for (const title of ["#", "Página", "Notas", "Compassos"]) {
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
    systemsTitle.textContent = "Linhas de tab detetadas";
    systems.append(systemsTitle, table);
    const preview = document.createElement("pre");
    preview.textContent = track.preview;
    details.append(systems, preview);
    return details;
  }

  const LYRICS_TRACK = "Letra (voz)"; // the silent track carrying the lyrics (app/converter.py)

  // Guitar Pro names of the navigation marks, as printed in scores.
  const NAVIGATION = {
    "Da Capo": "D.C.", "Da Capo al Coda": "D.C. al Coda", "Da Capo al Fine": "D.C. al Fine",
    "Da Segno": "D.S.", "Da Segno al Coda": "D.S. al Coda", "Da Segno al Fine": "D.S. al Fine",
    "Da Coda": "To Coda",
  };

  function renderResult(report) {
    const auto = (key) => (report.auto && report.auto[key] ? " (auto)" : "");
    document.getElementById("summary").replaceWith(Object.assign(summaryList([
      ["Título", (report.title || "—") + auto("title")], ["Artista", (report.artist || "—") + auto("artist")],
      ["BPM", report.tempo + auto("tempo")], ["Compasso", report.time_signature + auto("time_signature")],
      // Later time signatures ("3/4 no c. 17") and repeats, when the PDF has them.
      ...((report.time_signature_changes || []).length
        ? [["Mudanças de compasso", report.time_signature_changes.map((c) => `${c.time_signature} no c. ${c.bar}`).join(", ")]]
        : []),
      ...((report.tempo_changes || []).length
        ? [["Mudanças de tempo", report.tempo_changes.map((c) => `${c.tempo} no c. ${c.bar}`).join(", ")]]
        : []),
      ...((report.navigation || []).length
        ? [["Navegação", report.navigation.map((n) => `${NAVIGATION[n.name] || n.name} (c. ${n.bar})`).join(", ")
          + (report.repeats_expanded ? " (por extenso)" : "")]]
        : []),
      ...(report.repeats ? [["Repetições", `${report.repeats}${report.repeats_expanded ? " (por extenso)" : ""}`]] : []),
      ["Tracks", report.tracks.length], ["Compassos", report.measures], ["Notas", report.notes],
      ["Secções", report.sections && report.sections.length ? report.sections.length : "—"],
      ["Letra", report.lyrics ? `${report.lyrics.track}` : "—"],
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
    if (inspecting) return showStatus("Aguarde o fim da análise dos PDFs.", false);
    if (!tracks.length) return showStatus("Escolha pelo menos um ficheiro PDF.", true);
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
    showStatus(tracks.length > 1 ? `A converter ${tracks.length} tracks…` : "A converter…", false);
    try {
      const response = await fetch("/api/convert", { method: "POST", body });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(typeof payload.detail === "string" ? payload.detail : "Pedido inválido.");
      }
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      const gp5 = base64ToBytes(payload.gp5_base64);
      objectUrl = URL.createObjectURL(new Blob([gp5], { type: "application/octet-stream" }));
      download.href = objectUrl;
      download.download = payload.filename;
      renderResult(payload.report);
      status.hidden = true;
      result.hidden = false;
      if (window.ScoreView) {
        const lyricsTrack = Boolean(payload.report.lyrics && payload.report.lyrics.track === LYRICS_TRACK);
        window.ScoreView.show(gp5, payload.report.tracks.length, trackColors, payload.report.timed_lyrics, lyricsTrack);
      }
    } catch (error) {
      showStatus(error instanceof Error ? error.message : "Erro inesperado.", true);
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
      heading.textContent = `Versão ${release.version}${release.date ? ` · ${release.date}` : ""}`;
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
      const revision = health.revision ? ` (${health.revision})` : "";
      document.getElementById("version").textContent = `Versão ${health.version}${revision}`;
      if (health.close_with_browser) watchPresence();
    })
    .catch(() => {});
})();
