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
  let objectUrl = null;
  let maxBytes = 10 * 1024 * 1024;

  const TUNING_LABELS = {
    standard: "Standard (EADGBE)", drop_d: "Drop D", eb_standard: "Mib (½ tom abaixo)",
    d_standard: "Ré standard", drop_c: "Drop C", open_g: "Open G", open_d: "Open D",
    dadgad: "DADGAD", standard_7: "7 cordas standard", standard_8: "8 cordas standard",
    bass_4: "Baixo 4 cordas", bass_5: "Baixo 5 cordas",
  };
  const INSTRUMENT_LABELS = {
    nylon: "Guitarra clássica", steel: "Guitarra acústica", clean: "Guitarra elétrica limpa",
    overdrive: "Overdrive", distortion: "Distorção", bass: "Baixo",
  };

  function addOptions(select, values, labels) {
    for (const value of values) {
      if (value === "auto") continue;
      const option = document.createElement("option");
      option.value = value;
      option.textContent = labels[value] || value;
      select.appendChild(option);
    }
  }

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

  fetch("/api/health")
    .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
    .then((health) => { document.getElementById("version").textContent = `Versão ${health.version}`; })
    .catch(() => {});

  fetch("/api/options")
    .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
    .then((opts) => {
      addOptions(document.getElementById("tuning"), opts.tunings, TUNING_LABELS);
      addOptions(document.getElementById("instrument"), opts.instruments, INSTRUMENT_LABELS);
      maxBytes = opts.max_upload_mb * 1024 * 1024;
    })
    .catch(() => showStatus("Não foi possível carregar as opções do servidor.", true));

  function showStatus(message, isError) {
    status.hidden = false;
    status.textContent = message;
    status.classList.toggle("error", Boolean(isError));
  }

  function selectedFile() {
    return fileInput.files && fileInput.files[0];
  }

  function updateDropText() {
    const file = selectedFile();
    dropText.textContent = file ? `${file.name} (${(file.size / 1024).toFixed(0)} KB)` : "Arraste um PDF para aqui ou clique para escolher";
  }

  const meta = document.getElementById("meta");
  const inspectStatus = document.getElementById("inspect-status");
  const timeSignature = document.getElementById("time_signature");
  let inspection = 0; // ignores answers for a file that is no longer selected

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

  async function inspectFile() {
    const file = selectedFile();
    const token = ++inspection;
    meta.hidden = true;
    result.hidden = true;
    status.hidden = true;
    if (!file) { inspectStatus.hidden = true; return; }
    inspectStatus.hidden = false;
    inspectStatus.textContent = "A analisar o PDF…";
    let detected = {};
    try {
      const body = new FormData();
      body.append("file", file);
      const response = await fetch("/api/inspect", { method: "POST", body });
      const payload = await response.json().catch(() => ({}));
      if (token !== inspection) return;
      if (!response.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : "Pedido inválido.");
      detected = payload;
      inspectStatus.hidden = true;
    } catch (error) {
      if (token !== inspection) return;
      inspectStatus.textContent = error instanceof Error ? error.message : "Não foi possível analisar o PDF.";
    }
    setField("title", detected.title);
    setField("artist", detected.artist);
    setField("tempo", detected.tempo);
    selectTimeSignature(detected.time_signature);
    meta.hidden = false;
  }

  fileInput.addEventListener("change", () => { updateDropText(); inspectFile(); });
  ["dragenter", "dragover"].forEach((type) =>
    drop.addEventListener(type, (event) => { event.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((type) =>
    drop.addEventListener(type, (event) => { event.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (event) => {
    if (event.dataTransfer && event.dataTransfer.files.length) {
      fileInput.files = event.dataTransfer.files;
      updateDropText();
      inspectFile();
    }
  });

  function renderSummary(report) {
    const summary = document.getElementById("summary");
    summary.replaceChildren();
    const auto = (key) => (report.auto && report.auto[key] ? " (auto)" : "");
    const rhythm = report.rhythm_from_notation
      ? `lido em ${report.rhythm_from_notation}/${report.rhythm_from_notation + report.rhythm_estimated} compassos`
      : "estimado";
    const items = [
      ["Título", (report.title || "—") + auto("title")], ["Artista", (report.artist || "—") + auto("artist")],
      ["BPM", report.tempo + auto("tempo")], ["Compasso", report.time_signature + auto("time_signature")],
      ["Ritmo", rhythm], ["Compassos", report.measures], ["Notas", report.notes], ["Cordas", report.strings],
      ["Afinação", TUNING_LABELS[report.tuning] || report.tuning], ["Linhas de tab", report.systems],
      ["Formato", report.sources.map((s) => (s === "ascii" ? "texto" : "gravada")).join(", ")],
    ];
    for (const [label, value] of items) {
      const wrap = document.createElement("div");
      const dt = document.createElement("dt");
      const dd = document.createElement("dd");
      dt.textContent = label;
      dd.textContent = String(value);
      wrap.append(dt, dd);
      summary.appendChild(wrap);
    }
    const list = document.getElementById("warnings");
    list.replaceChildren();
    for (const warning of report.warnings) {
      const li = document.createElement("li");
      li.textContent = warning;
      list.appendChild(li);
    }
    document.getElementById("warnings-box").hidden = report.warnings.length === 0;
    const rows = document.getElementById("systems");
    rows.replaceChildren();
    (report.systems_detail || []).forEach((system, index) => {
      const tr = document.createElement("tr");
      for (const value of [index + 1, system.page, system.notes, system.measures ?? "—"]) {
        const td = document.createElement("td");
        td.textContent = String(value);
        tr.appendChild(td);
      }
      rows.appendChild(tr);
    });
    document.getElementById("preview").textContent = report.preview;
  }

  function base64ToBlob(b64) {
    const binary = atob(b64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
    return new Blob([bytes], { type: "application/octet-stream" });
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const file = selectedFile();
    if (!file) return showStatus("Escolha um ficheiro PDF.", true);
    if (file.size > maxBytes) return showStatus(`O ficheiro excede ${maxBytes / 1024 / 1024} MB.`, true);
    if (!form.reportValidity()) return undefined;

    submit.disabled = true;
    result.hidden = true;
    showStatus("A converter…", false);
    try {
      const body = new FormData(form);
      for (const key of ["title", "artist", "tempo"]) {
        if (!String(body.get(key) || "").trim()) body.delete(key); // empty = detect from the PDF
      }
      const response = await fetch("/api/convert", { method: "POST", body });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = typeof payload.detail === "string" ? payload.detail : "Pedido inválido.";
        throw new Error(detail);
      }
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      objectUrl = URL.createObjectURL(base64ToBlob(payload.gp5_base64));
      download.href = objectUrl;
      download.download = payload.filename;
      renderSummary(payload.report);
      status.hidden = true;
      result.hidden = false;
    } catch (error) {
      showStatus(error instanceof Error ? error.message : "Erro inesperado.", true);
    } finally {
      submit.disabled = false;
    }
    return undefined;
  });
})();
