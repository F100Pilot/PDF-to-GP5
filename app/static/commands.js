"use strict";

// Keyboard shortcuts, the command palette (Ctrl K) and the theme choice (Definições).
(() => {
  const THEME_KEY = "pdf-to-gp5.theme";
  const VIEWS = [
    ["Default", "Pauta e tab"],
    ["Tab", "Só tab"],
    ["Score", "Só pauta"],
    ["3D", "Pista 3D"],
  ];
  const PAGES = [
    ["converter", "Converter"],
    ["resultado", "Resultado"],
    ["tocar", "Tocar"],
    ["audio", "Áudio"],
    ["biblioteca", "Biblioteca"],
    ["definicoes", "Definições"],
  ];

  // --- Theme --------------------------------------------------------------------------------
  const themeButtons = document.querySelectorAll("[data-theme-choice]");

  function currentTheme() {
    return document.documentElement.dataset.theme || "system";
  }

  function setTheme(choice) {
    if (choice === "light" || choice === "dark") document.documentElement.dataset.theme = choice;
    else delete document.documentElement.dataset.theme;
    try {
      if (choice === "light" || choice === "dark") localStorage.setItem(THEME_KEY, choice);
      else localStorage.removeItem(THEME_KEY);
    } catch {
      // storage blocked: the choice lasts until the page is reloaded
    }
    for (const button of themeButtons) button.setAttribute("aria-pressed", String(button.dataset.themeChoice === currentTheme()));
  }

  for (const button of themeButtons) button.addEventListener("click", () => setTheme(button.dataset.themeChoice));
  setTheme(currentTheme());

  // --- Commands -----------------------------------------------------------------------------
  const score = () => window.ScoreView;
  const playerReady = () => Boolean(score() && score().ready());

  function commands() {
    const list = PAGES.map(([page, name]) => ({
      label: `Ir para ${name}`,
      group: "Página",
      run: () => { window.location.hash = `#/${page}`; },
    }));
    if (playerReady()) {
      list.push(
        { label: "Tocar / pausa", group: "Leitor", keys: "Espaço", run: () => score().playPause() },
        { label: "Parar", group: "Leitor", run: () => score().stop() },
        { label: "Loop A–B", group: "Leitor", keys: "L", run: () => score().toggleLoop() },
        { label: "Compasso seguinte", group: "Leitor", keys: "→", run: () => score().stepBar(1) },
        { label: "Compasso anterior", group: "Leitor", keys: "←", run: () => score().stepBar(-1) },
        ...VIEWS.map(([view, name], index) => ({
          label: `Vista: ${name}`,
          group: "Leitor",
          keys: String(index + 1),
          run: () => {
            score().setView(view);
            window.location.hash = "#/tocar";
          },
        })),
      );
    }
    list.push(
      { label: "Tema: do sistema", group: "Aparência", run: () => setTheme("system") },
      { label: "Tema: claro", group: "Aparência", run: () => setTheme("light") },
      { label: "Tema: escuro", group: "Aparência", run: () => setTheme("dark") },
    );
    const songs = window.Library ? window.Library.songs() : [];
    for (const song of songs) {
      list.push({
        label: `Abrir ${[song.title || "Sem título", song.artist].filter(Boolean).join(" — ")}`,
        group: "Biblioteca",
        run: () => window.Library.open(song.key),
      });
    }
    return list;
  }

  // --- Palette ------------------------------------------------------------------------------
  const dialog = document.getElementById("palette");
  const input = document.getElementById("palette-input");
  const listbox = document.getElementById("palette-list");
  let shown = [];
  let active = 0;
  let returnFocus = null;

  const normalize = (text) => text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

  function filter() {
    const words = normalize(input.value).split(/\s+/).filter(Boolean);
    shown = commands().filter((command) => {
      const text = normalize(`${command.label} ${command.group}`);
      return words.every((word) => text.includes(word));
    });
    active = 0;
    render();
  }

  function render() {
    if (!shown.length) {
      const none = document.createElement("li");
      none.className = "none";
      none.textContent = "Nada encontrado.";
      listbox.replaceChildren(none);
      input.removeAttribute("aria-activedescendant");
      return;
    }
    listbox.replaceChildren(...shown.map((command, index) => {
      const option = document.createElement("li");
      option.id = `palette-option-${index}`;
      option.setAttribute("role", "option");
      option.setAttribute("aria-selected", String(index === active));
      const label = document.createElement("span");
      label.textContent = command.label;
      option.appendChild(label);
      if (command.keys) {
        const keys = document.createElement("kbd");
        keys.textContent = command.keys;
        option.appendChild(keys);
      }
      const group = document.createElement("span");
      group.className = "group";
      group.textContent = command.group;
      option.appendChild(group);
      option.addEventListener("click", () => run(index));
      option.addEventListener("mousemove", () => {
        if (active !== index) setActive(index);
      });
      return option;
    }));
    input.setAttribute("aria-activedescendant", `palette-option-${active}`);
  }

  function setActive(index) {
    active = (index + shown.length) % shown.length;
    for (const [i, option] of [...listbox.children].entries()) option.setAttribute("aria-selected", String(i === active));
    input.setAttribute("aria-activedescendant", `palette-option-${active}`);
    const option = listbox.children[active];
    if (option) option.scrollIntoView({ block: "nearest" });
  }

  function run(index) {
    const command = shown[index];
    closePalette();
    if (command) command.run();
  }

  function openPalette() {
    if (dialog.open) return;
    returnFocus = document.activeElement;
    input.value = "";
    filter();
    dialog.showModal();
    input.focus();
  }

  function closePalette() {
    if (dialog.open) dialog.close();
  }

  dialog.addEventListener("close", () => {
    if (returnFocus && document.contains(returnFocus)) returnFocus.focus();
  });
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) closePalette(); // click on the backdrop
  });
  input.addEventListener("input", filter);
  input.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown" && shown.length) {
      event.preventDefault();
      setActive(active + 1);
    } else if (event.key === "ArrowUp" && shown.length) {
      event.preventDefault();
      setActive(active - 1);
    } else if (event.key === "Enter") {
      event.preventDefault();
      run(active);
    }
  });
  document.getElementById("palette-open").addEventListener("click", openPalette);

  // --- Shortcuts ----------------------------------------------------------------------------
  function typing(target) {
    return target instanceof HTMLElement
      && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName));
  }

  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && !event.altKey && event.key.toLowerCase() === "k") {
      event.preventDefault();
      if (dialog.open) closePalette();
      else openPalette();
      return;
    }
    if (dialog.open || event.ctrlKey || event.metaKey || event.altKey || typing(event.target)) return;
    // Space and Enter keep their own meaning on buttons and links.
    const onControl = event.target instanceof HTMLElement && ["BUTTON", "A", "SUMMARY"].includes(event.target.tagName);
    const key = event.key;
    let handled = true;
    if (key === " " && !onControl) {
      if (!playerReady()) return;
      score().playPause();
    } else if (key === "ArrowRight" && playerReady()) {
      score().stepBar(1);
    } else if (key === "ArrowLeft" && playerReady()) {
      score().stepBar(-1);
    } else if (/^[1-4]$/.test(key) && playerReady()) {
      score().setView(VIEWS[Number(key) - 1][0]);
    } else if (key === "[" && window.AudioSync) {
      window.AudioSync.nudge(0.1); // delay the score
    } else if (key === "]" && window.AudioSync) {
      window.AudioSync.nudge(-0.1); // advance the score
    } else if ((key === "l" || key === "L") && playerReady()) {
      score().toggleLoop();
    } else {
      handled = false;
    }
    if (handled) event.preventDefault();
  });
})();
