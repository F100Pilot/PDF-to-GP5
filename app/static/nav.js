"use strict";

// Pages of the app, one per subject, addressed by the URL hash (#/converter, #/tocar…): the
// browser's back/forward buttons and bookmarks work, and nothing is reloaded between pages.
// Every page lives in index.html; only the current one is shown. Playback (score, audio,
// video) keeps going while another page is open.
(() => {
  const PAGES = {
    converter: T("Converter"),
    resultado: T("Resultado"),
    tocar: T("Tocar"),
    audio: T("Áudio"),
    biblioteca: T("Biblioteca"),
    definicoes: T("Definições"),
  };
  const DEFAULT_PAGE = "converter";
  const result = document.getElementById("result");
  const railSong = document.getElementById("rail-song");
  let current = null;

  function pageFromHash() {
    const match = /^#\/([a-z]+)$/.exec(window.location.hash);
    return match && match[1] in PAGES ? match[1] : null;
  }

  function show(page, moveFocus) {
    current = page;
    for (const section of document.querySelectorAll("[data-page]")) {
      section.hidden = section.dataset.page !== page;
    }
    for (const link of document.querySelectorAll("[data-nav]")) {
      if (link.dataset.nav === page) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    }
    document.title = T("{page} · PDF → GP5", { page: PAGES[page] });
    if (moveFocus) {
      // Screen readers announce the new page; keyboard users continue from its title.
      const heading = document.getElementById(`h-${page}`);
      if (heading) heading.focus({ preventScroll: true });
      window.scrollTo(0, 0);
    }
    // The score and the 3D highway measure their width when shown.
    window.dispatchEvent(new Event("resize"));
  }

  window.addEventListener("hashchange", () => {
    const page = pageFromHash();
    if (page && page !== current) show(page, true); // other hashes (#page: skip link) are anchors
  });
  show(pageFromHash() || DEFAULT_PAGE, false);

  // Pages that need a converted song show an empty state until there is one.
  function songChanged() {
    const hasSong = !result.hidden;
    for (const element of document.querySelectorAll("[data-empty]")) element.hidden = hasSong;
    for (const element of document.querySelectorAll("[data-needs-song]")) element.hidden = !hasSong;
  }
  new MutationObserver(songChanged).observe(result, { attributes: true, attributeFilter: ["hidden"] });
  songChanged();

  // app.js announces each converted song: name it everywhere and open its result.
  document.addEventListener("song-converted", (event) => {
    const { title, artist, tracks, tempo } = event.detail;
    const name = [title || T("Sem título"), artist].filter(Boolean).join(" — ");
    for (const line of document.querySelectorAll("[data-song-line]")) line.textContent = name;
    document.getElementById("rail-song-title").textContent = title || T("Sem título");
    const details = [artist, tracks === 1 ? T("{n} track", { n: tracks }) : T("{n} tracks", { n: tracks }), tempo ? `${tempo} BPM` : ""];
    document.getElementById("rail-song-meta").textContent = details.filter(Boolean).join(" · ");
    railSong.hidden = false;
    if (current === "converter") window.location.hash = "#/resultado";
  });

  // Server status (Definições, and the dot at the foot of the menu).
  const dot = document.getElementById("server-dot");
  const dotText = document.getElementById("server-text");
  const list = document.getElementById("health-list");

  // A missing piece shows how to fix it, when the page is open on the server's own computer:
  // "Instalar" (the app's Python packages, as the start scripts install them) or, for automatic
  // video search, a field to paste the YouTube key.
  let installing = false;

  function row(name, ok, problem, fix = null, canFix = false) {
    const item = document.createElement("li");
    const mark = document.createElement("span");
    mark.className = ok ? "dot ok" : "dot warn";
    mark.setAttribute("aria-hidden", "true");
    const label = document.createElement("span");
    label.className = "health-name";
    label.textContent = name;
    const state = document.createElement("span");
    state.className = "muted";
    state.textContent = ok ? T("disponível") : problem || T("indisponível");
    item.append(mark, label, state);
    if (!ok && canFix && fix === "install") item.append(installButton());
    if (!ok && canFix && fix === "key") item.append(...keyForm());
    return item;
  }

  const installNote = document.createElement("p");
  installNote.className = "hint health-note";
  installNote.setAttribute("role", "status");
  installNote.hidden = true;
  const installLog = document.createElement("pre");
  installLog.className = "health-log";
  installLog.hidden = true;

  function installButton() {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "button secondary health-fix install-fix";
    button.textContent = installing ? T("A instalar…") : T("Instalar");
    button.disabled = installing;
    button.title = T("Instala os pacotes que faltam no ambiente Python da aplicação (pip), como o start.bat faz; não precisa de administrador.");
    button.addEventListener("click", startInstall);
    return button;
  }

  async function startInstall() {
    installing = true;
    installLog.hidden = true;
    installNote.hidden = false;
    installNote.textContent = T("A instalar o que falta… pode demorar alguns minutos (o OCR e o Deno são grandes).");
    for (const button of list.querySelectorAll(".install-fix")) {
      button.disabled = true;
      button.textContent = T("A instalar…");
    }
    try {
      let status = await (await fetch("/api/install", { method: "POST" })).json();
      while (status.state === "running") {
        await new Promise((resolve) => setTimeout(resolve, 1500));
        status = await (await fetch("/api/install")).json();
      }
      installing = false;
      if (status.state === "done") {
        installNote.textContent = T("Instalação concluída.");
      } else {
        installNote.textContent = T("A instalação falhou (sem ligação à internet, ou um proxy da empresa?). Últimas linhas do pip:");
        installLog.textContent = (status.log || []).join("\n");
        installLog.hidden = false;
      }
    } catch {
      installing = false;
      installNote.textContent = T("Não foi possível instalar (sem ligação ao servidor).");
    }
    loadHealth();
  }

  function keyForm() {
    const open = document.createElement("button");
    open.type = "button";
    open.className = "button secondary health-fix";
    open.textContent = T("Configurar chave");
    const form = document.createElement("form");
    form.className = "health-key";
    form.hidden = true;
    const input = document.createElement("input");
    input.type = "password";
    input.autocomplete = "off";
    input.spellcheck = false;
    input.placeholder = "AIza…";
    input.setAttribute("aria-label", T("Chave da API do YouTube"));
    const save = document.createElement("button");
    save.type = "submit";
    save.className = "button";
    save.textContent = T("Guardar");
    const note = document.createElement("span");
    note.className = "hint";
    note.textContent = T("Chave da YouTube Data API v3, criada na Google Cloud Console (ver docs/CHAVE_YOUTUBE.md). Fica no ficheiro youtube_api_key.txt deste computador.");
    form.append(input, save, note);
    open.addEventListener("click", () => {
      form.hidden = false;
      open.hidden = true;
      input.focus();
    });
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      save.disabled = true;
      try {
        const response = await fetch("/api/youtube-key", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ key: input.value }),
        });
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          note.textContent = typeof body.detail === "string" ? body.detail : T("Não foi possível guardar a chave.");
          return;
        }
        input.value = "";
        loadHealth();
      } catch {
        note.textContent = T("Não foi possível guardar a chave.");
      } finally {
        save.disabled = false;
      }
    });
    return [open, form];
  }

  function loadHealth() {
    return fetch("/api/health")
      .then((response) => (response.ok ? response.json() : Promise.reject(response.status)))
      .then((health) => {
        dot.className = "dot ok";
        dotText.textContent = T("Servidor ligado · {host}", { host: window.location.host });
        const fix = health.can_install;
        list.replaceChildren(
          row(T("Conversão de PDF"), true),
          row(T("Tabs em imagem (OCR)"), health.ocr, health.ocr_problem, "install", fix),
          row(T("Áudio de um endereço (URL → MP3)"), health.audio_download, health.audio_download_problem, "install", fix),
          row(T("Vídeos do YouTube no URL → MP3"), health.audio_youtube, health.audio_youtube_problem, "install", fix),
          row(T("Pesquisa automática do vídeo"), health.video_search, health.video_search_problem, "key", fix),
        );
        list.after(installNote);
        installNote.after(installLog);
      })
      .catch(() => {
        dot.className = "dot warn";
        dotText.textContent = T("Sem ligação ao servidor");
        list.replaceChildren(row(T("Servidor"), false, T("sem resposta")));
      });
  }
  loadHealth();
})();
