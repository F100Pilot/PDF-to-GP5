"use strict";

// Pages of the app, one per subject, addressed by the URL hash (#/converter, #/tocar…): the
// browser's back/forward buttons and bookmarks work, and nothing is reloaded between pages.
// Every page lives in index.html; only the current one is shown. Playback (score, audio,
// video) keeps going while another page is open.
(() => {
  const PAGES = {
    converter: "Converter",
    resultado: "Resultado",
    tocar: "Tocar",
    audio: "Áudio",
    definicoes: "Definições",
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
    document.title = `${PAGES[page]} · PDF → GP5`;
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
    const name = [title || "Sem título", artist].filter(Boolean).join(" — ");
    for (const line of document.querySelectorAll("[data-song-line]")) line.textContent = name;
    document.getElementById("rail-song-title").textContent = title || "Sem título";
    const details = [artist, `${tracks} ${tracks === 1 ? "track" : "tracks"}`, tempo ? `${tempo} BPM` : ""];
    document.getElementById("rail-song-meta").textContent = details.filter(Boolean).join(" · ");
    railSong.hidden = false;
    if (current === "converter") window.location.hash = "#/resultado";
  });

  // Server status (Definições, and the dot at the foot of the menu).
  const dot = document.getElementById("server-dot");
  const dotText = document.getElementById("server-text");
  const list = document.getElementById("health-list");

  function row(name, ok, problem) {
    const item = document.createElement("li");
    const mark = document.createElement("span");
    mark.className = ok ? "dot ok" : "dot warn";
    mark.setAttribute("aria-hidden", "true");
    const label = document.createElement("span");
    label.className = "health-name";
    label.textContent = name;
    const state = document.createElement("span");
    state.className = "muted";
    state.textContent = ok ? "disponível" : problem || "indisponível";
    item.append(mark, label, state);
    return item;
  }

  fetch("/api/health")
    .then((response) => (response.ok ? response.json() : Promise.reject(response.status)))
    .then((health) => {
      dot.className = "dot ok";
      dotText.textContent = `Servidor ligado · ${window.location.host}`;
      list.replaceChildren(
        row("Conversão de PDF", true),
        row("Áudio de um endereço (URL → MP3)", health.audio_download, health.audio_download_problem),
        row("Vídeos do YouTube no URL → MP3", health.audio_youtube, health.audio_youtube_problem),
        row("Pesquisa automática do vídeo", health.video_search, health.video_search_problem),
      );
    })
    .catch(() => {
      dot.className = "dot warn";
      dotText.textContent = "Sem ligação ao servidor";
      list.replaceChildren(row("Servidor", false, "sem resposta"));
    });
})();
